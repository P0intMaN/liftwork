"""Deploy executor protocol + request/result models."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, ClassVar, Protocol, runtime_checkable

from liftwork_core.build.config import DeploySpec
from liftwork_core.build.protocols import LogSink


class RolloutOutcome(enum.StrEnum):
    succeeded = "succeeded"
    failed = "failed"
    timed_out = "timed_out"


@dataclass(frozen=True)
class DeployTarget:
    cluster_name: str
    namespace: str


@dataclass(frozen=True)
class DeployRequest:
    target: DeployTarget
    application_slug: str  # k8s-safe; resource names derive from this
    application_id: str  # uuid for labeling
    image_ref: str  # full ref, prefer digest-pinned
    image_digest: str | None
    image_tag: str
    deploy_spec: DeploySpec
    revision: int
    commit_sha: str
    branch: str
    image_pull_secret: str | None = None


@dataclass(frozen=True)
class DeployResult:
    revision: int
    deployment_name: str
    service_name: str
    ingress_name: str | None
    outcome: RolloutOutcome
    duration_seconds: float
    error: str | None = None


@runtime_checkable
class DeployExecutor(Protocol):
    name: ClassVar[str]

    async def apply_manifests(
        self,
        manifests: list[dict[str, Any]],
        *,
        namespace: str,
        log_sink: LogSink,
    ) -> None: ...

    async def wait_for_rollout(
        self,
        *,
        namespace: str,
        deployment_name: str,
        target_replicas: int,
        log_sink: LogSink,
    ) -> RolloutOutcome: ...
