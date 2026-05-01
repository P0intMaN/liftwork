"""K8s deploy executor — create-or-update + rollout watching.

The kubernetes-python client (v31) doesn't yet ship native
server-side-apply ergonomics on the typed Apis (you can do it through
the DynamicClient but that pulls in OpenAPI schema discovery and is
fiddly). For v1 we do the simpler create-or-replace dance on Deployment
/ Service / Ingress / ConfigMap. Field manager is recorded on every
write so we can swap to SSA later without renaming managed fields.
"""

from __future__ import annotations

import asyncio
import time
from functools import partial
from typing import Any, ClassVar, Final

import anyio
from kubernetes.client.exceptions import ApiException

from liftwork_core.build.protocols import LogSink
from liftwork_core.deploy.labels import LIFTWORK_FIELD_MANAGER
from liftwork_core.deploy.protocols import RolloutOutcome
from liftwork_worker.deploy.rollout import (
    RolloutSnapshot,
    evaluate_rollout,
    format_progress,
    from_deployment_status,
)
from liftwork_worker.k8s import K8sClients

_NOT_FOUND: Final[int] = 404
_CONFLICT: Final[int] = 409


class DeployExecutorError(RuntimeError):
    pass


class K8sDeployExecutor:
    name: ClassVar[str] = "k8s-create-or-update"

    def __init__(
        self,
        clients: K8sClients,
        *,
        field_manager: str = LIFTWORK_FIELD_MANAGER,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self._clients = clients
        self._field_manager = field_manager
        self._poll_interval = poll_interval_seconds

    async def apply_manifests(
        self,
        manifests: list[dict[str, Any]],
        *,
        namespace: str,
        log_sink: LogSink,
    ) -> None:
        for manifest in manifests:
            kind = manifest["kind"]
            name = manifest["metadata"]["name"]
            await log_sink.write(
                f"applying {kind}/{name} (fieldManager={self._field_manager})"
            )
            try:
                await anyio.to_thread.run_sync(partial(self._apply_one, manifest, namespace))
            except ApiException as exc:
                body = (exc.body or "")[:500] if isinstance(exc.body, str) else ""
                msg = (
                    f"apply failed for {kind}/{name}: {exc.reason} ({exc.status}) — {body}"
                )
                raise DeployExecutorError(msg) from exc

    def _apply_one(self, manifest: dict[str, Any], namespace: str) -> None:
        kind = manifest["kind"]
        name = manifest["metadata"]["name"]
        fm = self._field_manager

        if kind == "Deployment":
            create = self._clients.apps_v1.create_namespaced_deployment
            replace = self._clients.apps_v1.replace_namespaced_deployment
        elif kind == "Service":
            create = self._clients.core_v1.create_namespaced_service
            replace = self._clients.core_v1.replace_namespaced_service
        elif kind == "Ingress":
            create = self._clients.networking_v1.create_namespaced_ingress
            replace = self._clients.networking_v1.replace_namespaced_ingress
        elif kind == "ConfigMap":
            create = self._clients.core_v1.create_namespaced_config_map
            replace = self._clients.core_v1.replace_namespaced_config_map
        else:
            msg = f"unsupported manifest kind: {kind}"
            raise DeployExecutorError(msg)

        try:
            create(namespace=namespace, body=manifest, field_manager=fm)
            return
        except ApiException as exc:
            if exc.status != _CONFLICT:
                raise
        # Already exists — fetch resourceVersion (and clusterIP for Services,
        # which is immutable) so the replace doesn't reject the new spec.
        existing = self._read_existing(kind=kind, name=name, namespace=namespace)
        if existing is not None:
            manifest["metadata"]["resourceVersion"] = existing.metadata.resource_version
            if kind == "Service":
                manifest.setdefault("spec", {})["clusterIP"] = existing.spec.cluster_ip
        replace(name=name, namespace=namespace, body=manifest, field_manager=fm)

    def _read_existing(self, *, kind: str, name: str, namespace: str) -> Any:
        if kind == "Deployment":
            return self._clients.apps_v1.read_namespaced_deployment(
                name=name, namespace=namespace
            )
        if kind == "Service":
            return self._clients.core_v1.read_namespaced_service(
                name=name, namespace=namespace
            )
        if kind == "Ingress":
            return self._clients.networking_v1.read_namespaced_ingress(
                name=name, namespace=namespace
            )
        if kind == "ConfigMap":
            return self._clients.core_v1.read_namespaced_config_map(
                name=name, namespace=namespace
            )
        return None

    async def wait_for_rollout(
        self,
        *,
        namespace: str,
        deployment_name: str,
        target_replicas: int,
        log_sink: LogSink,
        timeout_seconds: int = 600,
    ) -> RolloutOutcome:
        start = time.monotonic()
        last_progress: str | None = None

        while True:
            elapsed = time.monotonic() - start
            if elapsed > timeout_seconds:
                await log_sink.write(f"rollout: timed out after {int(elapsed)}s")
                return RolloutOutcome.timed_out

            try:
                deployment = await anyio.to_thread.run_sync(
                    partial(
                        self._clients.apps_v1.read_namespaced_deployment,
                        name=deployment_name,
                        namespace=namespace,
                    )
                )
            except ApiException as exc:
                if exc.status == _NOT_FOUND:
                    await log_sink.write(
                        f"rollout: Deployment/{deployment_name} not found yet — retrying"
                    )
                    await asyncio.sleep(self._poll_interval)
                    continue
                msg = f"rollout: API error reading Deployment/{deployment_name}: {exc.reason}"
                raise DeployExecutorError(msg) from exc

            snapshot: RolloutSnapshot = from_deployment_status(
                deployment, fallback_replicas=target_replicas
            )
            outcome = evaluate_rollout(snapshot, target_replicas=target_replicas)

            progress = format_progress(snapshot, target_replicas=target_replicas)
            if progress != last_progress:
                await log_sink.write(f"rollout: {progress}")
                last_progress = progress

            if outcome is RolloutOutcome.succeeded:
                await log_sink.write("rollout: ready")
                return RolloutOutcome.succeeded
            if outcome is RolloutOutcome.failed:
                await log_sink.write(f"rollout: failed — {snapshot.progressing_failed_reason}")
                return RolloutOutcome.failed

            await asyncio.sleep(self._poll_interval)
