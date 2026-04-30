"""BuildKit-in-pod executor.

Spawns a Kubernetes Job that:

  * init container clones the target repo into an emptyDir volume
  * main container runs `buildctl-daemonless.sh` (BuildKit rootless),
    builds the rendered Dockerfile, and pushes to the destination
    registry using docker creds mounted from a Secret
  * trailing `cat` prints the build metadata (incl. sha256 digest) to
    stdout with a stable marker we parse out

This module's pure function `build_buildkit_job_spec` returns a plain
dict of the manifest — that's what the executor submits and what the
unit test snapshots.
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass
from typing import Any, ClassVar, Final

from liftwork_core.build.protocols import BuildContext, BuildResult, LogSink

DIGEST_MARKER: Final[str] = "LIFTWORK_DIGEST="
_DIGEST_LINE_RE = re.compile(rf"{DIGEST_MARKER}(sha256:[0-9a-f]{{64}})")
DEFAULT_BUILDKIT_IMAGE: Final[str] = "moby/buildkit:v0.16.0-rootless"
DEFAULT_GIT_IMAGE: Final[str] = "alpine/git:2.45.2"
DEFAULT_NAMESPACE: Final[str] = "liftwork"
DEFAULT_REGISTRY_SECRET_NAME: Final[str] = "liftwork-registry-creds"  # noqa: S105 — k8s resource name, not a credential


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
    service_account: str = "liftwork-builder"
    cpu_request: str = "500m"
    memory_request: str = "1Gi"
    cpu_limit: str = "2"
    memory_limit: str = "4Gi"
    build_timeout_seconds: int = 1800


def _job_name(build_id: str) -> str:
    safe = re.sub(r"[^a-z0-9-]", "-", build_id.lower()).strip("-")
    return f"liftwork-build-{safe}"[:63]


def build_buildkit_job_spec(spec: JobSpecInputs) -> dict[str, Any]:
    """Return a Kubernetes Job manifest (as a dict) for one build."""
    name = _job_name(spec.build_id)

    buildctl_args = [
        "build",
        "--frontend=dockerfile.v0",
        "--local=context=/workspace",
        "--local=dockerfile=/dockerfile",
        f"--output=type=image,name={spec.image_ref},push=true",
        "--metadata-file=/tmp/meta.json",
    ]
    if spec.cache_ref:
        buildctl_args.extend(
            [
                f"--export-cache=type=registry,ref={spec.cache_ref},mode=max",
                f"--import-cache=type=registry,ref={spec.cache_ref}",
            ]
        )

    main_command = [
        "sh",
        "-ec",
        "buildctl-daemonless.sh "
        + " ".join(buildctl_args)
        + ' && DIGEST=$(grep -oE "sha256:[0-9a-f]{64}" /tmp/meta.json | head -n1)'
        + f' && echo "{DIGEST_MARKER}${{DIGEST}}"',
    ]

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
                            "env": [
                                {
                                    "name": "BUILDKITD_FLAGS",
                                    "value": "--oci-worker-no-process-sandbox",
                                },
                                {"name": "DOCKER_CONFIG", "value": "/home/user/.docker"},
                            ],
                            "volumeMounts": [
                                {"name": "workspace", "mountPath": "/workspace"},
                                {
                                    "name": "dockerfile",
                                    "mountPath": "/dockerfile",
                                    "readOnly": True,
                                },
                                {
                                    "name": "docker-config",
                                    "mountPath": "/home/user/.docker",
                                    "readOnly": True,
                                },
                                {
                                    "name": "buildkit-cache",
                                    "mountPath": "/home/user/.local/share/buildkit",
                                },
                            ],
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
                                "allowPrivilegeEscalation": False,
                                "seccompProfile": {"type": "Unconfined"},
                            },
                        },
                    ],
                    "volumes": [
                        {"name": "workspace", "emptyDir": {}},
                        {
                            "name": "dockerfile",
                            "configMap": {
                                "name": spec.dockerfile_configmap,
                                "items": [{"key": "Dockerfile", "path": "Dockerfile"}],
                            },
                        },
                        {
                            "name": "docker-config",
                            "secret": {
                                "secretName": spec.registry_secret_name,
                                "items": [{"key": ".dockerconfigjson", "path": "config.json"}],
                            },
                        },
                        {"name": "buildkit-cache", "emptyDir": {}},
                    ],
                },
            },
        },
    }


def parse_digest(line: str) -> str | None:
    """Return the sha256 digest if `line` carries our marker."""
    match = _DIGEST_LINE_RE.search(line)
    return match.group(1) if match else None


class BuildKitInPodExecutor:
    """Submit and watch a BuildKit-in-pod Job.

    The executor is intentionally *thin*: the orchestrator owns config
    map provisioning, registry secret management, and cleanup. This
    class focuses on submission, log tailing, and digest extraction.
    """

    name: ClassVar[str] = "buildkit-in-pod"

    def __init__(
        self,
        *,
        submit_job: object,
        stream_logs: object,
        wait_for_completion: object,
        spec_factory: object = build_buildkit_job_spec,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        # The executor depends on three callables (submit / stream / wait)
        # so the orchestrator can wire in real k8s clients in production
        # and stubs in tests, without this module taking a hard k8s import
        # of its own.
        self._submit = submit_job
        self._stream = stream_logs
        self._wait = wait_for_completion
        self._spec_factory = spec_factory
        self._poll_interval = poll_interval_seconds

    async def build(self, ctx: BuildContext, *, log_sink: LogSink) -> BuildResult:
        # The orchestrator embeds JobSpecInputs in BuildContext.labels
        # under the `liftwork.io/job-spec-*` namespace. For Phase 2 the
        # executor expects the orchestrator to instead call the helper
        # `build_buildkit_job_spec` directly and pass the rendered Job
        # via a side channel; this class is sketched out and exercised
        # by snapshot tests until Phase 4 wires the real I/O path.
        msg = "BuildKitInPodExecutor.build is wired in Phase 4 (worker job runner)"
        raise NotImplementedError(msg)

    async def _stream_until_done(
        self,
        *,
        namespace: str,
        job_name: str,
        log_sink: LogSink,
    ) -> tuple[bool, str | None]:
        digest: str | None = None
        async for line in self._stream(namespace=namespace, job_name=job_name):  # type: ignore[operator]
            await log_sink.write(line)
            if digest is None:
                digest = parse_digest(line)
        succeeded: bool = await self._wait(namespace=namespace, job_name=job_name)  # type: ignore[operator]
        return succeeded, digest

    @staticmethod
    def _now() -> float:
        return time.perf_counter()

    @staticmethod
    async def _sleep(seconds: float) -> None:
        await asyncio.sleep(seconds)
