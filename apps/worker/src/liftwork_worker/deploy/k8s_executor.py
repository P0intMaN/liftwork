"""K8s deploy executor — server-side apply + rollout watching.

Server-side apply is preferred over create-or-update because it is the
recommended pattern for managed resources and avoids spurious diffs
when controllers (HPA, mutating admission) touch the same object.
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


class DeployExecutorError(RuntimeError):
    pass


class K8sDeployExecutor:
    name: ClassVar[str] = "k8s-server-side-apply"

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
                f"applying {kind}/{name} (ssa, fieldManager={self._field_manager})"
            )
            try:
                await anyio.to_thread.run_sync(partial(self._apply_one, manifest, namespace))
            except ApiException as exc:
                msg = f"server-side apply failed for {kind}/{name}: {exc.reason}"
                raise DeployExecutorError(msg) from exc

    def _apply_one(self, manifest: dict[str, Any], namespace: str) -> None:
        kind = manifest["kind"]
        api = self._clients.api_client
        params = {
            "field_manager": self._field_manager,
            "force": True,
        }
        if kind == "Deployment":
            self._clients.apps_v1.patch_namespaced_deployment(
                name=manifest["metadata"]["name"],
                namespace=namespace,
                body=manifest,
                **params,
                _content_type="application/apply-patch+yaml",
            )
        elif kind == "Service":
            self._clients.core_v1.patch_namespaced_service(
                name=manifest["metadata"]["name"],
                namespace=namespace,
                body=manifest,
                **params,
                _content_type="application/apply-patch+yaml",
            )
        elif kind == "Ingress":
            self._clients.networking_v1.patch_namespaced_ingress(
                name=manifest["metadata"]["name"],
                namespace=namespace,
                body=manifest,
                **params,
                _content_type="application/apply-patch+yaml",
            )
        elif kind == "ConfigMap":
            self._clients.core_v1.patch_namespaced_config_map(
                name=manifest["metadata"]["name"],
                namespace=namespace,
                body=manifest,
                **params,
                _content_type="application/apply-patch+yaml",
            )
        else:
            msg = f"unsupported manifest kind: {kind}"
            raise DeployExecutorError(msg)
        # silence the unused-var warning for `api` — reserved for future
        # generic server-side apply via dynamic client.
        _ = api

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
