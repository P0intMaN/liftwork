from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from liftwork_core.build.config import DeploySpec, IngressSpec
from liftwork_core.build.protocols import LogSink
from liftwork_core.deploy import DeployRequest, DeployTarget
from liftwork_core.deploy.protocols import RolloutOutcome
from liftwork_worker.deploy.orchestrator import orchestrate_deploy
from liftwork_worker.log_sinks import InMemoryLogSink


@dataclass
class _MockExecutor:
    name: ClassVar[str] = "mock"
    outcome: RolloutOutcome = RolloutOutcome.succeeded
    apply_should_raise: Exception | None = None
    captured_manifests: list[list[dict[str, Any]]] = field(default_factory=list)
    apply_calls: int = 0
    wait_calls: int = 0

    async def apply_manifests(
        self,
        manifests: list[dict[str, Any]],
        *,
        namespace: str,  # noqa: ARG002
        log_sink: LogSink,
    ) -> None:
        self.apply_calls += 1
        self.captured_manifests.append(list(manifests))
        if self.apply_should_raise is not None:
            raise self.apply_should_raise
        await log_sink.write(f"applied {len(manifests)} manifests")

    async def wait_for_rollout(
        self,
        *,
        namespace: str,  # noqa: ARG002
        deployment_name: str,  # noqa: ARG002
        target_replicas: int,  # noqa: ARG002
        log_sink: LogSink,  # noqa: ARG002
    ) -> RolloutOutcome:
        self.wait_calls += 1
        return self.outcome


def _make_request(**overrides: object) -> DeployRequest:
    base: dict[str, object] = {
        "target": DeployTarget(cluster_name="kind-kubedeploy-dev", namespace="acme"),
        "application_slug": "acme-api",
        "application_id": "11111111-2222-3333-4444-555555555555",
        "image_ref": "ghcr.io/acme/api@sha256:" + "a" * 64,
        "image_digest": "sha256:" + "a" * 64,
        "image_tag": "main-abc1234",
        "deploy_spec": DeploySpec(port=8080, replicas=2),
        "revision": 1,
        "commit_sha": "abc1234",
        "branch": "main",
    }
    base.update(overrides)
    return DeployRequest(**base)  # type: ignore[arg-type]


async def test_happy_path_applies_and_returns_succeeded() -> None:
    sink = InMemoryLogSink()
    executor = _MockExecutor(outcome=RolloutOutcome.succeeded)

    result = await orchestrate_deploy(
        _make_request(),
        executor=executor,
        log_sink=sink,
    )

    assert result.outcome is RolloutOutcome.succeeded
    assert result.deployment_name == "acme-api"
    assert result.service_name == "acme-api"
    assert result.ingress_name is None
    assert result.error is None
    assert executor.apply_calls == 1
    assert executor.wait_calls == 1

    kinds = [m["kind"] for m in executor.captured_manifests[0]]
    assert kinds == ["Deployment", "Service"]


async def test_includes_ingress_when_enabled() -> None:
    request = _make_request(
        deploy_spec=DeploySpec(
            port=8080,
            replicas=1,
            ingress=IngressSpec(enabled=True, host="api.example.com"),
        ),
    )
    executor = _MockExecutor()
    result = await orchestrate_deploy(request, executor=executor, log_sink=InMemoryLogSink())
    assert result.ingress_name == "acme-api"
    kinds = [m["kind"] for m in executor.captured_manifests[0]]
    assert kinds == ["Deployment", "Service", "Ingress"]


async def test_apply_failure_short_circuits_and_records_error() -> None:
    executor = _MockExecutor(apply_should_raise=RuntimeError("api server timeout"))
    sink = InMemoryLogSink()
    result = await orchestrate_deploy(_make_request(), executor=executor, log_sink=sink)

    assert result.outcome is RolloutOutcome.failed
    assert result.error is not None
    assert "api server timeout" in result.error
    assert executor.wait_calls == 0  # never reached
    assert any("deploy: error" in line for line in sink.lines)


async def test_rollout_timeout_propagates_outcome() -> None:
    executor = _MockExecutor(outcome=RolloutOutcome.timed_out)
    result = await orchestrate_deploy(
        _make_request(),
        executor=executor,
        log_sink=InMemoryLogSink(),
    )
    assert result.outcome is RolloutOutcome.timed_out
    assert result.error is None  # no exception, just an outcome
