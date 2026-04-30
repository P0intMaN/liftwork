"""Pure rollout-state evaluation, separated from k8s I/O for testability.

The async `wait_for_rollout` lives in `k8s_executor.py` and calls into
`evaluate_rollout` after each poll cycle.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from liftwork_core.deploy.protocols import RolloutOutcome


@dataclass(frozen=True)
class RolloutSnapshot:
    generation: int
    observed_generation: int
    replicas: int
    updated_replicas: int
    available_replicas: int
    ready_replicas: int
    progressing_failed_reason: str | None = None  # set when Progressing=False


def from_deployment_status(deployment: Any, *, fallback_replicas: int = 1) -> RolloutSnapshot:
    """Translate a kubernetes V1Deployment object into a RolloutSnapshot."""
    metadata = deployment.metadata
    status = deployment.status
    spec = deployment.spec

    progressing_failed: str | None = None
    for cond in status.conditions or []:
        is_progressing = getattr(cond, "type", None) == "Progressing"
        is_false = getattr(cond, "status", None) == "False"
        if is_progressing and is_false:
            reason = getattr(cond, "reason", "")
            message = getattr(cond, "message", "")
            progressing_failed = f"{reason}: {message}".strip(": ").strip()
            break

    return RolloutSnapshot(
        generation=metadata.generation or 0,
        observed_generation=status.observed_generation or 0,
        replicas=spec.replicas if spec.replicas is not None else fallback_replicas,
        updated_replicas=status.updated_replicas or 0,
        available_replicas=status.available_replicas or 0,
        ready_replicas=status.ready_replicas or 0,
        progressing_failed_reason=progressing_failed,
    )


def evaluate_rollout(snapshot: RolloutSnapshot, *, target_replicas: int) -> RolloutOutcome | None:
    """Decide rollout state from a snapshot.

    Returns:
        - RolloutOutcome.succeeded if the rollout finished cleanly
        - RolloutOutcome.failed   if Progressing=False (stuck)
        - None                    if still in flight
    """
    if snapshot.progressing_failed_reason is not None:
        return RolloutOutcome.failed

    if snapshot.observed_generation < snapshot.generation:
        return None

    target = target_replicas if target_replicas > 0 else snapshot.replicas
    if (
        snapshot.updated_replicas >= target
        and snapshot.available_replicas >= target
        and snapshot.ready_replicas >= target
    ):
        return RolloutOutcome.succeeded

    return None


def format_progress(snapshot: RolloutSnapshot, *, target_replicas: int) -> str:
    return (
        f"gen={snapshot.generation} observed={snapshot.observed_generation} "
        f"updated={snapshot.updated_replicas}/{target_replicas} "
        f"available={snapshot.available_replicas}/{target_replicas} "
        f"ready={snapshot.ready_replicas}/{target_replicas}"
    )
