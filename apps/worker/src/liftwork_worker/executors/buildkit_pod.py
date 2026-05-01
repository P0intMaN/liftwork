"""BuildKit-in-pod executor.

Spawns a Kubernetes Job that:

  * init container clones the target repo into an emptyDir volume
  * main container runs `buildctl-daemonless.sh` (BuildKit rootless),
    builds the rendered Dockerfile, and pushes to the destination
    registry; for authed registries the docker-config is mounted from
    a Secret, for the dev in-cluster registry we set `registry.insecure=true`
    instead and skip the secret entirely
  * trailing parser pulls the manifest sha256 out of buildctl's
    `--metadata-file` and prints it under a stable marker that the
    executor parses out of pod logs

Two public surfaces:

  * `build_buildkit_job_spec(JobSpecInputs)` — pure dict factory used
    by snapshot tests
  * `K8sBuildKitExecutor` — the real `BuildExecutor` impl that talks
    to the kubernetes client; injected via the worker's `WorkerState`
    when `LIFTWORK_BUILD__EXECUTOR=buildkit-pod`
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from functools import partial
from typing import Any, ClassVar, Final
from uuid import uuid4

import anyio
from kubernetes.client.exceptions import ApiException

from liftwork_core.build.protocols import BuildContext, BuildResult, LogSink
from liftwork_worker.k8s import K8sClients

DIGEST_MARKER: Final[str] = "LIFTWORK_DIGEST="
_DIGEST_LINE_RE = re.compile(rf"{DIGEST_MARKER}(sha256:[0-9a-f]{{64}})")
META_BEGIN_MARKER: Final[str] = "LIFTWORK_META_BEGIN"
META_END_MARKER: Final[str] = "LIFTWORK_META_END"
DEFAULT_BUILDKIT_IMAGE: Final[str] = "moby/buildkit:v0.16.0-rootless"
DEFAULT_GIT_IMAGE: Final[str] = "alpine/git:2.45.2"
DEFAULT_NAMESPACE: Final[str] = "liftwork"
DEFAULT_REGISTRY_SECRET_NAME: Final[str] = "liftwork-registry-creds"  # noqa: S105 — k8s resource name, not a credential
_NOT_FOUND: Final[int] = 404
_CONFLICT: Final[int] = 409
_POLL_INTERVAL_SECONDS: Final[float] = 2.0


@dataclass(frozen=True)
class JobSpecInputs:
    build_id: str
    repo_url: str
    branch: str
    dockerfile_configmap: str  # name of ConfigMap that carries the rendered Dockerfile
    image_ref: str
    cache_ref: str | None = None
    namespace: str = DEFAULT_NAMESPACE
    buildkit_image: str = DEFAULT_BUILDKIT_IMAGE
    git_image: str = DEFAULT_GIT_IMAGE
    registry_secret_name: str = DEFAULT_REGISTRY_SECRET_NAME
    registry_insecure: bool = False  # dev path — skip secret mount, push over HTTP
    service_account: str = "liftwork-builder"
    cpu_request: str = "500m"
    memory_request: str = "1Gi"
    cpu_limit: str = "2"
    memory_limit: str = "4Gi"
    build_timeout_seconds: int = 1800


def _job_name(build_id: str) -> str:
    safe = re.sub(r"[^a-z0-9-]", "-", build_id.lower()).strip("-")
    return f"liftwork-build-{safe}"[:63]


def _output_flag(image_ref: str, *, registry_insecure: bool) -> str:
    parts = [f"type=image,name={image_ref}", "push=true"]
    if registry_insecure:
        parts.append("registry.insecure=true")
    return "--output=" + ",".join(parts)


def build_buildkit_job_spec(spec: JobSpecInputs) -> dict[str, Any]:
    """Return a Kubernetes Job manifest (as a dict) for one build."""
    name = _job_name(spec.build_id)

    buildctl_args = [
        "build",
        "--frontend=dockerfile.v0",
        "--local=context=/workspace",
        "--local=dockerfile=/dockerfile",
        _output_flag(spec.image_ref, registry_insecure=spec.registry_insecure),
        "--metadata-file=/tmp/meta.json",
    ]
    if spec.cache_ref:
        buildctl_args.extend(
            [
                f"--export-cache=type=registry,ref={spec.cache_ref},mode=max",
                f"--import-cache=type=registry,ref={spec.cache_ref}",
            ]
        )

    # We can't reliably extract `containerimage.digest` with sh tools alone
    # (sed/awk + JSON quoting collide with the surrounding shell + ConfigMap
    # serialization). Instead, dump the raw metadata JSON between marker
    # lines and let the executor parse it in Python.
    main_command = [
        "sh",
        "-ec",
        "buildctl-daemonless.sh "
        + " ".join(buildctl_args)
        + f" && echo {META_BEGIN_MARKER}"
        + " && cat /tmp/meta.json"
        + f" && echo && echo {META_END_MARKER}",
    ]

    container_volume_mounts: list[dict[str, Any]] = [
        {"name": "workspace", "mountPath": "/workspace"},
        {"name": "dockerfile", "mountPath": "/dockerfile", "readOnly": True},
        {"name": "buildkit-cache", "mountPath": "/home/user/.local/share/buildkit"},
    ]
    volumes: list[dict[str, Any]] = [
        {"name": "workspace", "emptyDir": {}},
        {
            "name": "dockerfile",
            "configMap": {
                "name": spec.dockerfile_configmap,
                "items": [{"key": "Dockerfile", "path": "Dockerfile"}],
            },
        },
        {"name": "buildkit-cache", "emptyDir": {}},
    ]
    env_vars: list[dict[str, Any]] = [
        {
            "name": "BUILDKITD_FLAGS",
            "value": "--oci-worker-no-process-sandbox",
        },
    ]

    if not spec.registry_insecure:
        # Authed push needs ~/.docker/config.json
        container_volume_mounts.append(
            {
                "name": "docker-config",
                "mountPath": "/home/user/.docker",
                "readOnly": True,
            }
        )
        volumes.append(
            {
                "name": "docker-config",
                "secret": {
                    "secretName": spec.registry_secret_name,
                    "items": [{"key": ".dockerconfigjson", "path": "config.json"}],
                },
            }
        )
        env_vars.append({"name": "DOCKER_CONFIG", "value": "/home/user/.docker"})

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": name,
            "namespace": spec.namespace,
            "labels": {
                "app.kubernetes.io/name": "liftwork",
                "app.kubernetes.io/component": "builder",
                "liftwork.io/build-id": spec.build_id,
            },
        },
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 600,
            "activeDeadlineSeconds": spec.build_timeout_seconds,
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/name": "liftwork",
                        "app.kubernetes.io/component": "builder",
                        "liftwork.io/build-id": spec.build_id,
                    },
                },
                "spec": {
                    "restartPolicy": "Never",
                    "serviceAccountName": spec.service_account,
                    "automountServiceAccountToken": False,
                    "initContainers": [
                        {
                            "name": "git-clone",
                            "image": spec.git_image,
                            "command": ["sh", "-ec"],
                            "args": [
                                "git clone --depth 1 --single-branch "
                                f"--branch {spec.branch} {spec.repo_url} /workspace"
                            ],
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/workspace"},
                            ],
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                "allowPrivilegeEscalation": False,
                                "readOnlyRootFilesystem": False,
                                "capabilities": {"drop": ["ALL"]},
                            },
                        },
                    ],
                    "containers": [
                        {
                            "name": "buildkit",
                            "image": spec.buildkit_image,
                            "command": main_command,
                            "env": env_vars,
                            "volumeMounts": container_volume_mounts,
                            "resources": {
                                "requests": {
                                    "cpu": spec.cpu_request,
                                    "memory": spec.memory_request,
                                },
                                "limits": {
                                    "cpu": spec.cpu_limit,
                                    "memory": spec.memory_limit,
                                },
                            },
                            "securityContext": {
                                "runAsUser": 1000,
                                "runAsGroup": 1000,
                                "runAsNonRoot": True,
                                # MUST be true so /usr/bin/newuidmap can elevate
                                # via its setuid bit. With no_new_privs (false),
                                # rootless BuildKit fails with
                                # "newuidmap: Could not set caps".
                                "allowPrivilegeEscalation": True,
                                "seccompProfile": {"type": "Unconfined"},
                            },
                        },
                    ],
                    "volumes": volumes,
                },
            },
        },
    }


def parse_digest(line: str) -> str | None:
    """Legacy single-line marker parser (still used by tests)."""
    match = _DIGEST_LINE_RE.search(line)
    return match.group(1) if match else None


def extract_manifest_digest(metadata_json: str) -> str | None:
    """Pick `containerimage.digest` (the manifest sha256) out of BuildKit's
    --metadata-file JSON. Returns None on parse error or missing key."""
    try:
        meta = json.loads(metadata_json)
    except (ValueError, TypeError):
        return None
    digest = meta.get("containerimage.digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        return digest
    return None


# ---------------------------------------------------------------------------
# Real executor
# ---------------------------------------------------------------------------


class BuildKitExecutorError(RuntimeError):
    pass


class K8sBuildKitExecutor:
    """Concrete `BuildExecutor` that actually drives a kind / k8s cluster."""

    name: ClassVar[str] = "k8s-buildkit"

    def __init__(
        self,
        *,
        clients: K8sClients,
        namespace: str = DEFAULT_NAMESPACE,
        registry_secret_name: str = DEFAULT_REGISTRY_SECRET_NAME,
        service_account: str = "liftwork-builder",
        buildkit_image: str = DEFAULT_BUILDKIT_IMAGE,
        git_image: str = DEFAULT_GIT_IMAGE,
        build_timeout_seconds: int = 1800,
    ) -> None:
        self._clients = clients
        self._namespace = namespace
        self._registry_secret = registry_secret_name
        self._service_account = service_account
        self._buildkit_image = buildkit_image
        self._git_image = git_image
        self._build_timeout = build_timeout_seconds

    async def build(self, ctx: BuildContext, *, log_sink: LogSink) -> BuildResult:
        if ctx.repo_url is None or ctx.branch is None:
            msg = "K8sBuildKitExecutor requires ctx.repo_url and ctx.branch"
            raise BuildKitExecutorError(msg)

        # Truncate to 24 chars; collapse UUID dashes first so we never end
        # on a hyphen (k8s label values must end alphanumerically).
        raw = ctx.build_id or uuid4().hex
        build_id = raw.replace("-", "")[:24] or "build"
        cm_name = f"liftwork-build-{build_id}-df"[:63].rstrip("-")
        spec = JobSpecInputs(
            build_id=build_id,
            repo_url=ctx.repo_url,
            branch=ctx.branch,
            dockerfile_configmap=cm_name,
            image_ref=ctx.image_ref,
            namespace=self._namespace,
            buildkit_image=self._buildkit_image,
            git_image=self._git_image,
            registry_secret_name=self._registry_secret,
            registry_insecure=ctx.registry_insecure,
            service_account=self._service_account,
            build_timeout_seconds=self._build_timeout,
        )
        job_manifest = build_buildkit_job_spec(spec)
        job_name = job_manifest["metadata"]["name"]
        dockerfile_text = ctx.dockerfile_path.read_text(encoding="utf-8")

        await log_sink.write(
            f"[buildkit] submit job={job_name} ns={self._namespace} "
            f"image={ctx.image_ref} insecure={ctx.registry_insecure}"
        )

        await self._create_dockerfile_configmap(cm_name, dockerfile_text)
        submitted = False
        try:
            await self._submit_job(job_manifest)
            submitted = True
            start = time.perf_counter()

            pod_name = await self._find_pod_for_build(build_id=build_id)
            await log_sink.write(f"[buildkit] pod={pod_name} (init)")

            # Init container does git clone first; the buildkit container
            # only enters Running once that succeeds. Until then,
            # read_namespaced_pod_log returns 400.
            await self._wait_for_container_started(
                pod_name=pod_name, container="buildkit"
            )
            await log_sink.write(f"[buildkit] streaming pod={pod_name}")

            digest = await self._stream_pod_logs(
                pod_name=pod_name, log_sink=log_sink
            )
            success = await self._wait_for_completion(job_name=job_name)
            duration = time.perf_counter() - start

            if not success:
                msg = f"BuildKit Job {job_name} did not complete successfully"
                raise BuildKitExecutorError(msg)
            if digest is None:
                msg = (
                    f"BuildKit Job {job_name} finished but no LIFTWORK_DIGEST "
                    "marker was found in pod logs"
                )
                raise BuildKitExecutorError(msg)

            await log_sink.write(f"[buildkit] done digest={digest}")
            return BuildResult(
                image_ref=ctx.image_ref,
                image_digest=digest,
                duration_seconds=round(duration, 3),
            )
        finally:
            # Block until the Job is in a terminal state — otherwise
            # deleting the ConfigMap unmounts it from a still-running Pod.
            if submitted:
                await self._wait_for_job_terminal(job_name=job_name, timeout_seconds=30)
            await self._delete_configmap(cm_name)

    # ---- k8s I/O helpers (each blocking call goes via to_thread) ----

    async def _create_dockerfile_configmap(self, name: str, dockerfile: str) -> None:
        body = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": name,
                "namespace": self._namespace,
                "labels": {
                    "app.kubernetes.io/name": "liftwork",
                    "app.kubernetes.io/component": "builder",
                },
            },
            "data": {"Dockerfile": dockerfile},
        }
        try:
            await anyio.to_thread.run_sync(
                partial(
                    self._clients.core_v1.create_namespaced_config_map,
                    namespace=self._namespace,
                    body=body,
                )
            )
        except ApiException as exc:
            if exc.status == _CONFLICT:  # already exists — replace
                await anyio.to_thread.run_sync(
                    partial(
                        self._clients.core_v1.replace_namespaced_config_map,
                        name=name,
                        namespace=self._namespace,
                        body=body,
                    )
                )
                return
            cm_body = (exc.body or "")[:600] if isinstance(exc.body, str) else ""
            msg = f"failed to create ConfigMap/{name}: {exc.reason} ({exc.status}) — {cm_body}"
            raise BuildKitExecutorError(msg) from exc

    async def _submit_job(self, manifest: dict[str, Any]) -> None:
        try:
            await anyio.to_thread.run_sync(
                partial(
                    self._clients.batch_v1.create_namespaced_job,
                    namespace=self._namespace,
                    body=manifest,
                )
            )
        except ApiException as exc:
            body = (exc.body or "")[:600] if isinstance(exc.body, str) else ""
            msg = (
                f"failed to submit Job/{manifest['metadata']['name']}: "
                f"{exc.reason} ({exc.status}) — {body}"
            )
            raise BuildKitExecutorError(msg) from exc

    async def _delete_configmap(self, name: str) -> None:
        try:
            await anyio.to_thread.run_sync(
                partial(
                    self._clients.core_v1.delete_namespaced_config_map,
                    name=name,
                    namespace=self._namespace,
                )
            )
        except ApiException as exc:
            if exc.status == _NOT_FOUND:
                return
            # cleanup failure is non-fatal — log and move on
            return

    async def _find_pod_for_build(self, *, build_id: str) -> str:
        """Wait until the Job has produced a Pod, then return its name."""
        deadline = time.monotonic() + 60.0
        label_selector = f"liftwork.io/build-id={build_id}"
        while time.monotonic() < deadline:
            try:
                pods = await anyio.to_thread.run_sync(
                    partial(
                        self._clients.core_v1.list_namespaced_pod,
                        namespace=self._namespace,
                        label_selector=label_selector,
                    )
                )
            except ApiException as exc:
                msg = f"could not list pods for build_id={build_id}: {exc.reason}"
                raise BuildKitExecutorError(msg) from exc
            if pods.items:
                return str(pods.items[0].metadata.name)
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        msg = f"timed out waiting for a Pod for build_id={build_id}"
        raise BuildKitExecutorError(msg)

    async def _wait_for_container_started(
        self,
        *,
        pod_name: str,
        container: str,
        timeout_seconds: int = 180,
    ) -> None:
        """Block until `container` in `pod_name` is past the Waiting state.

        Init containers can take a while (git clone over the network) and
        `read_namespaced_pod_log` returns HTTP 400 until the requested
        container has actually started. Polling pod status is the safe
        signal.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                pod = await anyio.to_thread.run_sync(
                    partial(
                        self._clients.core_v1.read_namespaced_pod,
                        name=pod_name,
                        namespace=self._namespace,
                    )
                )
            except ApiException as exc:
                msg = f"failed to read pod {pod_name}: {exc.reason}"
                raise BuildKitExecutorError(msg) from exc
            for cs in pod.status.container_statuses or []:
                if cs.name == container and (
                    cs.state.running is not None or cs.state.terminated is not None
                ):
                    return
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        msg = f"container {container} in pod {pod_name} never started"
        raise BuildKitExecutorError(msg)

    async def _wait_for_job_terminal(
        self, *, job_name: str, timeout_seconds: int = 30
    ) -> None:
        """Wait until the Job has at least one succeeded or failed pod.

        Soft cap: if the Job is still in flight after `timeout_seconds`,
        return anyway — the caller is in a finally block and we don't want
        to mask the real exception.
        """
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            try:
                job = await anyio.to_thread.run_sync(
                    partial(
                        self._clients.batch_v1.read_namespaced_job_status,
                        name=job_name,
                        namespace=self._namespace,
                    )
                )
            except ApiException:
                return
            status = job.status
            if (status.succeeded and status.succeeded >= 1) or (
                status.failed and status.failed >= 1
            ):
                return
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    async def _stream_pod_logs(
        self,
        *,
        pod_name: str,
        log_sink: LogSink,
    ) -> str | None:
        """Tail pod logs to the sink; return the parsed digest or None."""
        digest: str | None = None

        # We call read_namespaced_pod_log with follow=True; it returns a
        # urllib3 response we iterate line-by-line on a worker thread.
        def _read() -> Any:
            return self._clients.core_v1.read_namespaced_pod_log(
                name=pod_name,
                namespace=self._namespace,
                follow=True,
                _preload_content=False,
                container="buildkit",
                _request_timeout=self._build_timeout,
            )

        try:
            stream = await anyio.to_thread.run_sync(_read)
        except ApiException as exc:
            msg = f"failed to stream logs from {pod_name}: {exc.reason}"
            raise BuildKitExecutorError(msg) from exc

        meta_buffer: list[str] = []
        in_meta = False
        try:
            while True:
                line = await anyio.to_thread.run_sync(stream.readline)
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                await log_sink.write(text)
                # Capture the metadata JSON dumped between markers.
                if META_BEGIN_MARKER in text:
                    in_meta = True
                    continue
                if META_END_MARKER in text:
                    in_meta = False
                    digest = extract_manifest_digest("".join(meta_buffer))
                    continue
                if in_meta:
                    meta_buffer.append(text + "\n")
                # Legacy single-line marker (kept for back-compat / mocks).
                if digest is None:
                    digest = parse_digest(text)
        finally:
            await anyio.to_thread.run_sync(stream.release_conn)
        return digest

    async def _wait_for_completion(self, *, job_name: str) -> bool:
        deadline = time.monotonic() + self._build_timeout
        while time.monotonic() < deadline:
            try:
                job = await anyio.to_thread.run_sync(
                    partial(
                        self._clients.batch_v1.read_namespaced_job_status,
                        name=job_name,
                        namespace=self._namespace,
                    )
                )
            except ApiException as exc:
                msg = f"failed to read status of Job/{job_name}: {exc.reason}"
                raise BuildKitExecutorError(msg) from exc
            status = job.status
            if status.succeeded and status.succeeded >= 1:
                return True
            if status.failed and status.failed >= 1:
                return False
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        msg = f"timed out waiting for Job/{job_name}"
        raise BuildKitExecutorError(msg)


# Back-compat alias — the old tests imported this name.
BuildKitInPodExecutor = K8sBuildKitExecutor
