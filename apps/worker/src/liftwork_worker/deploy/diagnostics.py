"""Classify rollout failures into actionable, fix-this-thing diagnoses.

Pure-ish: takes already-fetched lists of pods and events and returns a
structured `RolloutDiagnostic` (or None if the rollout still looks
healthy). The k8s I/O of fetching those lists lives in `k8s_executor`.

Why split it: the watcher polls every few seconds; we want failures
classified deterministically without a real cluster, so the same module
that classifies them in prod is the one we unit-test against hand-crafted
V1Pod / V1Event fixtures.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any

# Reasons in `pod.status.containerStatuses[*].state.waiting.reason` that we
# treat as terminal — no amount of waiting will fix them.
_TERMINAL_PULL_REASONS = {"ErrImagePull", "ImagePullBackOff", "ImagePullError"}
_TERMINAL_CONFIG_REASONS = {
    "CreateContainerConfigError",
    "RunContainerError",
    "InvalidImageName",
    "CreateContainerError",
}
_HTTP_5XX_CODES = ("500", "501", "502", "503", "504", "505")


class DiagnosisCategory(enum.StrEnum):
    image_pull_failed = "image_pull_failed"
    crash_loop = "crash_loop"
    config_error = "config_error"
    port_mismatch = "port_mismatch"
    health_path_404 = "health_path_404"
    health_path_5xx = "health_path_5xx"
    not_scheduled = "not_scheduled"


@dataclass(frozen=True)
class RolloutDiagnostic:
    category: DiagnosisCategory
    message: str  # actionable, fix-this-specific-thing message
    is_terminal: bool  # True ⇒ bail immediately; False ⇒ require N consecutive observations


def diagnose_rollout(
    *,
    pods: list[Any],
    events: list[Any],
    deploy_port: int,
    deploy_health_path: str,
) -> RolloutDiagnostic | None:
    """Inspect pods + events; return the most-actionable diagnosis we find.

    Order of precedence (terminal signals first, soft signals after):
      1. Image pull failures (terminal — kubelet won't recover)
      2. Container config errors (terminal — bad spec)
      3. CrashLoopBackOff (terminal — container exits on start)
      4. Readiness probe — connection refused (port mismatch, soft)
      5. Readiness probe — HTTP 404 (health path wrong, soft)
      6. Readiness probe — HTTP 5xx (app unhealthy, soft)
      7. FailedScheduling (soft — cluster capacity)
    """
    diag = _diagnose_pods(pods)
    if diag is not None:
        return diag
    return _diagnose_events(
        events,
        deploy_port=deploy_port,
        deploy_health_path=deploy_health_path,
    )


def _diagnose_pods(pods: list[Any]) -> RolloutDiagnostic | None:
    for pod in pods:
        statuses = getattr(getattr(pod, "status", None), "container_statuses", None) or []
        for cs in statuses:
            waiting = getattr(getattr(cs, "state", None), "waiting", None)
            reason = getattr(waiting, "reason", None) if waiting else None
            message = getattr(waiting, "message", "") if waiting else ""
            image = getattr(cs, "image", "<unknown>")

            if reason in _TERMINAL_PULL_REASONS:
                return RolloutDiagnostic(
                    DiagnosisCategory.image_pull_failed,
                    (
                        f"image '{image}' couldn't be pulled "
                        f"({reason}). Check `image_repository` on the Application "
                        f"and that the registry is reachable from the cluster."
                    ),
                    is_terminal=True,
                )
            if reason in _TERMINAL_CONFIG_REASONS:
                return RolloutDiagnostic(
                    DiagnosisCategory.config_error,
                    f"container failed to start ({reason}): {message or 'no detail'}",
                    is_terminal=True,
                )
            if reason == "CrashLoopBackOff":
                last_terminated = getattr(getattr(cs, "last_state", None), "terminated", None)
                exit_code = getattr(last_terminated, "exit_code", None)
                exit_reason = getattr(last_terminated, "reason", None)
                detail = (
                    f"exit code {exit_code}"
                    if exit_code is not None
                    else (exit_reason or "no detail")
                )
                return RolloutDiagnostic(
                    DiagnosisCategory.crash_loop,
                    (
                        f"container is crash-looping ({detail}). Check the "
                        f"container logs — your app exits on start."
                    ),
                    is_terminal=True,
                )
    return None


def _diagnose_events(
    events: list[Any],
    *,
    deploy_port: int,
    deploy_health_path: str,
) -> RolloutDiagnostic | None:
    # Filter to Warning-class events; Normal events (e.g. Pulled, Created)
    # are noise here.
    warnings = [e for e in events if (getattr(e, "type", "") or "") == "Warning"]

    for event in warnings:
        message = (getattr(event, "message", "") or "").lower()
        if "readiness probe failed" not in message:
            continue
        if "connection refused" in message:
            return RolloutDiagnostic(
                DiagnosisCategory.port_mismatch,
                (
                    f"container is up but isn't listening on port {deploy_port}. "
                    f"Set `deploy.port` in liftwork.yaml to your app's actual "
                    f"port (or update the Dockerfile EXPOSE)."
                ),
                is_terminal=False,
            )
        if "statuscode: 404" in message:
            return RolloutDiagnostic(
                DiagnosisCategory.health_path_404,
                (
                    f"container responds on :{deploy_port} but `{deploy_health_path}` "
                    f"returned 404. Set `deploy.health_check.path` in liftwork.yaml "
                    f"to your real health endpoint."
                ),
                is_terminal=False,
            )
        for code in _HTTP_5XX_CODES:
            if f"statuscode: {code}" in message:
                return RolloutDiagnostic(
                    DiagnosisCategory.health_path_5xx,
                    (
                        f"container responds on :{deploy_port} but `{deploy_health_path}` "
                        f"returned {code}. Container is up but the app reports unhealthy."
                    ),
                    is_terminal=False,
                )

    for event in warnings:
        if getattr(event, "reason", "") == "FailedScheduling":
            return RolloutDiagnostic(
                DiagnosisCategory.not_scheduled,
                (f"pod could not be scheduled: {getattr(event, 'message', '') or 'no detail'}"),
                is_terminal=False,
            )
    return None
