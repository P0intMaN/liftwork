"""In-memory mock executors for Phase 4b-1.

These simulate a build/deploy pipeline end-to-end without touching k8s
or a registry. Phase 4b-2 swaps `MockBuildExecutor` for the real
BuildKit-in-pod executor and `MockDeployExecutor` for `K8sDeployExecutor`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, ClassVar

from liftwork_core.build.protocols import BuildContext, BuildResult, LogSink
from liftwork_core.deploy.protocols import RolloutOutcome


@dataclass
class MockBuildExecutor:
    name: ClassVar[str] = "mock-build"
    digest: str = "sha256:" + "f" * 64
    duration_seconds: float = 0.05
    captured: list[BuildContext] = field(default_factory=list)
    fail_with: str | None = None  # set in tests to simulate a failure

    async def build(self, ctx: BuildContext, *, log_sink: LogSink) -> BuildResult:
        self.captured.append(ctx)
        await log_sink.write(f"[mock-build] start image_ref={ctx.image_ref}")
        await asyncio.sleep(self.duration_seconds)
        if self.fail_with is not None:
            await log_sink.write(f"[mock-build] FAIL — {self.fail_with}")
            raise RuntimeError(self.fail_with)
        await log_sink.write(f"[mock-build] pushed digest={self.digest}")
        return BuildResult(
            image_ref=ctx.image_ref,
            image_digest=self.digest,
            duration_seconds=self.duration_seconds,
        )


@dataclass
class MockDeployExecutor:
    name: ClassVar[str] = "mock-deploy"
    outcome: RolloutOutcome = RolloutOutcome.succeeded
    apply_latency_seconds: float = 0.01
    rollout_latency_seconds: float = 0.02
    captured_manifests: list[list[dict[str, Any]]] = field(default_factory=list)
    apply_calls: int = 0
    wait_calls: int = 0

    async def apply_manifests(
        self,
        manifests: list[dict[str, Any]],
        *,
        namespace: str,
        log_sink: LogSink,
    ) -> None:
        self.apply_calls += 1
        self.captured_manifests.append(list(manifests))
        await log_sink.write(f"[mock-deploy] applying {len(manifests)} manifests in {namespace}")
        await asyncio.sleep(self.apply_latency_seconds)
        await log_sink.write("[mock-deploy] applied")

    async def wait_for_rollout(
        self,
        *,
        namespace: str,  # noqa: ARG002
        deployment_name: str,
        target_replicas: int,
        log_sink: LogSink,
    ) -> RolloutOutcome:
        self.wait_calls += 1
        await log_sink.write(
            f"[mock-deploy] waiting for rollout {deployment_name} target={target_replicas}"
        )
        await asyncio.sleep(self.rollout_latency_seconds)
        await log_sink.write(f"[mock-deploy] rollout outcome={self.outcome.value}")
        return self.outcome
