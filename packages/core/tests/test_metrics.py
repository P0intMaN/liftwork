"""Smoke + label-shape tests for the prometheus metrics catalog."""

from __future__ import annotations

from prometheus_client import generate_latest

from liftwork_core import metrics
from liftwork_core.telemetry import PROMETHEUS_REGISTRY


def test_all_named_instruments_present() -> None:
    # Counters/Gauges/Histograms only show in /metrics output once they
    # have an observation, so introspect the registry directly.
    expected = {
        "liftwork_builds_started",  # Counter family — `_total` is suffix-only at scrape time
        "liftwork_builds_finished",
        "liftwork_build_duration_seconds",
        "liftwork_build_image_bytes",
        "liftwork_active_builds",
        "liftwork_deploys_started",
        "liftwork_deploys_finished",
        "liftwork_deploy_duration_seconds",
        "liftwork_active_deploys",
        "liftwork_registry_push_duration_seconds",
        "liftwork_k8s_api_latency_seconds",
        "liftwork_k8s_api_errors",
        "liftwork_cluster_healthy",
        "liftwork_cluster_last_probe_age_seconds",
        "liftwork_queue_depth",
        "liftwork_jobs_completed",
        "liftwork_webhooks_received",
        "liftwork_errors",
    }
    seen = {m.name for m in PROMETHEUS_REGISTRY.collect()}
    missing = expected - seen
    assert not missing, f"metrics not registered: {missing}"


def test_record_helpers_exercise_labels_without_explosion() -> None:
    # Cardinality smoke: each helper emits well-formed labels and the
    # registry can render them without raising.
    metrics.record_build_started(language="python", source="webhook")
    metrics.record_build_finished(
        language="python",
        status="succeeded",
        duration_seconds=12.3,
        image_bytes=42_000_000,
    )
    metrics.record_deploy_started(cluster="kind-dev")
    metrics.record_deploy_finished(cluster="kind-dev", outcome="succeeded", duration_seconds=4.5)
    metrics.record_error(category="git_clone", stage="build")
    metrics.record_k8s_call(verb="patch", resource="deployments", duration_seconds=0.08)
    metrics.record_k8s_call(
        verb="get",
        resource="pods",
        duration_seconds=0.5,
        error_status="5xx",
    )
    text = generate_latest(PROMETHEUS_REGISTRY).decode("utf-8")
    assert 'language="python"' in text
    assert 'cluster="kind-dev"' in text
    assert 'category="git_clone"' in text
    assert 'verb="patch"' in text
