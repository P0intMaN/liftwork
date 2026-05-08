"""Hand-crafted V1Pod / V1Event fixtures → diagnose_rollout outputs."""

from __future__ import annotations

from dataclasses import dataclass, field

from liftwork_worker.deploy.diagnostics import (
    DiagnosisCategory,
    diagnose_rollout,
)

# ---------------------------------------------------------------------------
# Tiny duck-typed fakes — diagnose_rollout uses getattr so we don't have to
# import the real kubernetes models.
# ---------------------------------------------------------------------------


@dataclass
class _Waiting:
    reason: str | None = None
    message: str = ""


@dataclass
class _Terminated:
    exit_code: int | None = None
    reason: str | None = None


@dataclass
class _State:
    waiting: _Waiting | None = None


@dataclass
class _LastState:
    terminated: _Terminated | None = None


@dataclass
class _ContainerStatus:
    state: _State = field(default_factory=_State)
    last_state: _LastState = field(default_factory=_LastState)
    image: str = "registry.local/app:abc"


@dataclass
class _PodStatus:
    container_statuses: list[_ContainerStatus] = field(default_factory=list)


@dataclass
class _Pod:
    status: _PodStatus = field(default_factory=_PodStatus)


@dataclass
class _Event:
    type: str = "Warning"
    reason: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _waiting_pod(reason: str, *, message: str = "", image: str = "img:tag") -> _Pod:
    return _Pod(
        status=_PodStatus(
            container_statuses=[
                _ContainerStatus(
                    state=_State(waiting=_Waiting(reason=reason, message=message)),
                    image=image,
                )
            ]
        )
    )


def _crashloop_pod(*, exit_code: int = 1) -> _Pod:
    return _Pod(
        status=_PodStatus(
            container_statuses=[
                _ContainerStatus(
                    state=_State(waiting=_Waiting(reason="CrashLoopBackOff")),
                    last_state=_LastState(terminated=_Terminated(exit_code=exit_code)),
                )
            ]
        )
    )


def _diagnose(pods: list[_Pod], events: list[_Event] | None = None):
    return diagnose_rollout(
        pods=pods,
        events=events or [],
        deploy_port=8080,
        deploy_health_path="/healthz",
    )


# ---------------------------------------------------------------------------
# Pod-status diagnoses (terminal)
# ---------------------------------------------------------------------------


def test_image_pull_backoff_is_terminal() -> None:
    diag = _diagnose([_waiting_pod("ImagePullBackOff", image="registry.local/foo:bad")])
    assert diag is not None
    assert diag.category is DiagnosisCategory.image_pull_failed
    assert diag.is_terminal is True
    assert "registry.local/foo:bad" in diag.message
    assert "ImagePullBackOff" in diag.message


def test_err_image_pull_is_terminal() -> None:
    diag = _diagnose([_waiting_pod("ErrImagePull")])
    assert diag is not None
    assert diag.category is DiagnosisCategory.image_pull_failed
    assert diag.is_terminal


def test_crashloop_is_terminal_with_exit_code() -> None:
    diag = _diagnose([_crashloop_pod(exit_code=137)])
    assert diag is not None
    assert diag.category is DiagnosisCategory.crash_loop
    assert diag.is_terminal
    assert "137" in diag.message


def test_create_container_config_error_is_terminal() -> None:
    diag = _diagnose(
        [_waiting_pod("CreateContainerConfigError", message="secret not found")]
    )
    assert diag is not None
    assert diag.category is DiagnosisCategory.config_error
    assert diag.is_terminal
    assert "secret not found" in diag.message


def test_run_container_error_is_terminal() -> None:
    diag = _diagnose([_waiting_pod("RunContainerError", message="container won't run")])
    assert diag is not None
    assert diag.category is DiagnosisCategory.config_error
    assert diag.is_terminal


# ---------------------------------------------------------------------------
# Event-driven diagnoses (soft)
# ---------------------------------------------------------------------------


def test_probe_connection_refused_is_port_mismatch() -> None:
    events = [
        _Event(
            type="Warning",
            reason="Unhealthy",
            message=(
                'Readiness probe failed: Get "http://10.0.0.1:8080/healthz": '
                "dial tcp 10.0.0.1:8080: connect: connection refused"
            ),
        )
    ]
    diag = _diagnose(pods=[], events=events)
    assert diag is not None
    assert diag.category is DiagnosisCategory.port_mismatch
    assert diag.is_terminal is False
    assert "8080" in diag.message
    assert "liftwork.yaml" in diag.message


def test_probe_404_is_health_path_mismatch() -> None:
    events = [
        _Event(
            type="Warning",
            reason="Unhealthy",
            message="Readiness probe failed: HTTP probe failed with statuscode: 404",
        )
    ]
    diag = _diagnose(pods=[], events=events)
    assert diag is not None
    assert diag.category is DiagnosisCategory.health_path_404
    assert diag.is_terminal is False
    assert "/healthz" in diag.message


def test_probe_503_is_health_path_5xx() -> None:
    events = [
        _Event(
            type="Warning",
            reason="Unhealthy",
            message="Readiness probe failed: HTTP probe failed with statuscode: 503",
        )
    ]
    diag = _diagnose(pods=[], events=events)
    assert diag is not None
    assert diag.category is DiagnosisCategory.health_path_5xx
    assert diag.is_terminal is False
    assert "503" in diag.message


def test_failed_scheduling_event() -> None:
    events = [
        _Event(
            type="Warning",
            reason="FailedScheduling",
            message="0/3 nodes are available: 3 Insufficient memory.",
        )
    ]
    diag = _diagnose(pods=[], events=events)
    assert diag is not None
    assert diag.category is DiagnosisCategory.not_scheduled
    assert diag.is_terminal is False
    assert "Insufficient memory" in diag.message


def test_normal_events_are_ignored() -> None:
    events = [
        _Event(type="Normal", reason="Pulled", message="Successfully pulled image"),
        _Event(type="Normal", reason="Created", message="Created container"),
    ]
    assert _diagnose(pods=[], events=events) is None


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


def test_pod_signal_takes_precedence_over_event_signal() -> None:
    pods = [_waiting_pod("ImagePullBackOff")]
    events = [
        _Event(
            type="Warning",
            reason="Unhealthy",
            message="Readiness probe failed: connection refused",
        ),
    ]
    diag = _diagnose(pods=pods, events=events)
    assert diag is not None
    assert diag.category is DiagnosisCategory.image_pull_failed


def test_no_signal_returns_none() -> None:
    """A still-progressing rollout with no warnings yields no diagnosis."""
    assert _diagnose([], []) is None


def test_pod_with_no_status_is_safe() -> None:
    pod = _Pod(status=_PodStatus(container_statuses=[]))
    assert _diagnose([pod], []) is None
