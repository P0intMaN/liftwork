from __future__ import annotations

from dataclasses import dataclass

from liftwork_core.deploy.protocols import RolloutOutcome
from liftwork_worker.deploy.rollout import (
    RolloutSnapshot,
    evaluate_rollout,
    format_progress,
    from_deployment_status,
)


@dataclass
class _FakeCondition:
    type: str
    status: str
    reason: str = ""
    message: str = ""


@dataclass
class _FakeStatus:
    observed_generation: int = 0
    updated_replicas: int = 0
    available_replicas: int = 0
    ready_replicas: int = 0
    conditions: list[_FakeCondition] | None = None


@dataclass
class _FakeMeta:
    generation: int = 1


@dataclass
class _FakeSpec:
    replicas: int | None = 2


@dataclass
class _FakeDeployment:
    metadata: _FakeMeta
    spec: _FakeSpec
    status: _FakeStatus


def _dep(**status_kwargs: object) -> _FakeDeployment:
    return _FakeDeployment(
        metadata=_FakeMeta(generation=1),
        spec=_FakeSpec(replicas=2),
        status=_FakeStatus(**status_kwargs),  # type: ignore[arg-type]
    )


def test_in_flight_returns_none() -> None:
    snap = from_deployment_status(_dep(observed_generation=0))
    assert evaluate_rollout(snap, target_replicas=2) is None


def test_succeeded_when_all_replicas_ready() -> None:
    snap = from_deployment_status(
        _dep(observed_generation=1, updated_replicas=2, available_replicas=2, ready_replicas=2)
    )
    assert evaluate_rollout(snap, target_replicas=2) is RolloutOutcome.succeeded


def test_failed_when_progressing_false() -> None:
    snap = from_deployment_status(
        _dep(
            observed_generation=1,
            updated_replicas=1,
            available_replicas=0,
            ready_replicas=0,
            conditions=[
                _FakeCondition(
                    type="Progressing",
                    status="False",
                    reason="ProgressDeadlineExceeded",
                    message="ReplicaSet has timed out progressing.",
                )
            ],
        )
    )
    assert snap.progressing_failed_reason is not None
    assert evaluate_rollout(snap, target_replicas=2) is RolloutOutcome.failed


def test_observed_generation_lagging() -> None:
    snap = RolloutSnapshot(
        generation=5,
        observed_generation=4,
        replicas=3,
        updated_replicas=3,
        available_replicas=3,
        ready_replicas=3,
    )
    assert evaluate_rollout(snap, target_replicas=3) is None


def test_partial_progress() -> None:
    snap = RolloutSnapshot(
        generation=1,
        observed_generation=1,
        replicas=3,
        updated_replicas=2,
        available_replicas=2,
        ready_replicas=2,
    )
    assert evaluate_rollout(snap, target_replicas=3) is None


def test_target_replicas_zero_falls_back_to_spec() -> None:
    snap = RolloutSnapshot(
        generation=1,
        observed_generation=1,
        replicas=3,
        updated_replicas=3,
        available_replicas=3,
        ready_replicas=3,
    )
    assert evaluate_rollout(snap, target_replicas=0) is RolloutOutcome.succeeded


def test_format_progress_is_human_readable() -> None:
    snap = RolloutSnapshot(
        generation=2,
        observed_generation=2,
        replicas=2,
        updated_replicas=1,
        available_replicas=1,
        ready_replicas=1,
    )
    text = format_progress(snap, target_replicas=2)
    assert "gen=2" in text
    assert "updated=1/2" in text
    assert "ready=1/2" in text
