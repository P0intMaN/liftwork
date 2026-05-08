"""Prometheus metrics catalog for liftwork.

All instruments are module-level and registered against the shared
`PROMETHEUS_REGISTRY` in `liftwork_core.telemetry`. Both the API and the
worker expose them at `/metrics` (the worker on its `health_port`).

**Cardinality discipline:** every label below is bounded by an enum or
small finite set (Language, BuildStatus, RolloutOutcome, k8s verbs,
cluster names). Don't add free-form labels like `app_slug` to anything
that gets observed per-event — use traces for high-cardinality drilldown.

**Naming convention:** `liftwork_<subject>_<unit>` per Prom best
practices. Counters end in `_total`. Histograms in `_seconds` /
`_bytes`. Gauges have no suffix.
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

from liftwork_core.telemetry import PROMETHEUS_REGISTRY

# Bucket sets tuned to liftwork's actual ranges so p95/p99 are meaningful
# rather than landing in the +Inf bucket.
_DURATION_BUCKETS_SHORT = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1,
    2.5,
    5,
    10,
)  # k8s API calls, registry pings, etc.

_DURATION_BUCKETS_BUILD = (
    1,
    5,
    10,
    30,
    60,
    120,
    300,
    600,
    1200,
    1800,
)  # builds: 1s → 30min cap

_DURATION_BUCKETS_DEPLOY = (
    0.5,
    1,
    2.5,
    5,
    10,
    30,
    60,
    120,
    300,
    600,
)  # deploys: half-second → 10min cap

_BYTE_BUCKETS_IMAGE = (
    1_000_000,  # 1 MB
    10_000_000,  # 10 MB
    50_000_000,  # 50 MB
    100_000_000,  # 100 MB
    500_000_000,  # 500 MB
    1_000_000_000,  # 1 GB
    2_500_000_000,  # 2.5 GB
)


# ---------------------------------------------------------------------------
# Build lifecycle
# ---------------------------------------------------------------------------

BUILDS_STARTED = Counter(
    "liftwork_builds_started_total",
    "Builds that transitioned out of `queued` into `running`.",
    labelnames=("language", "source"),  # source ∈ webhook|manual|api|retry
    registry=PROMETHEUS_REGISTRY,
)

BUILDS_FINISHED = Counter(
    "liftwork_builds_finished_total",
    "Builds reaching a terminal status.",
    labelnames=("language", "status"),  # status ∈ succeeded|failed|cancelled
    registry=PROMETHEUS_REGISTRY,
)

BUILD_DURATION = Histogram(
    "liftwork_build_duration_seconds",
    "Wall-clock duration from build start to terminal status.",
    labelnames=("language", "status"),
    buckets=_DURATION_BUCKETS_BUILD,
    registry=PROMETHEUS_REGISTRY,
)

BUILD_IMAGE_BYTES = Histogram(
    "liftwork_build_image_bytes",
    "Compressed size of the built image as reported by the executor.",
    labelnames=("language",),
    buckets=_BYTE_BUCKETS_IMAGE,
    registry=PROMETHEUS_REGISTRY,
)

ACTIVE_BUILDS = Gauge(
    "liftwork_active_builds",
    "Builds currently in flight on this worker (running|building|pushing).",
    registry=PROMETHEUS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Deploy lifecycle
# ---------------------------------------------------------------------------

DEPLOYS_STARTED = Counter(
    "liftwork_deploys_started_total",
    "Deploys picked up by the worker.",
    labelnames=("cluster",),
    registry=PROMETHEUS_REGISTRY,
)

DEPLOYS_FINISHED = Counter(
    "liftwork_deploys_finished_total",
    "Deploys reaching a terminal status.",
    labelnames=("cluster", "outcome"),  # outcome ∈ succeeded|failed|rolled_back
    registry=PROMETHEUS_REGISTRY,
)

DEPLOY_DURATION = Histogram(
    "liftwork_deploy_duration_seconds",
    "Wall-clock duration from deploy start to terminal status.",
    labelnames=("cluster", "outcome"),
    buckets=_DURATION_BUCKETS_DEPLOY,
    registry=PROMETHEUS_REGISTRY,
)

ACTIVE_DEPLOYS = Gauge(
    "liftwork_active_deploys",
    "Deploys currently in flight on this worker (applying|rolling_out).",
    registry=PROMETHEUS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Image registry
# ---------------------------------------------------------------------------

REGISTRY_PUSH_DURATION = Histogram(
    "liftwork_registry_push_duration_seconds",
    "Time spent pushing an image layer set to the registry.",
    buckets=_DURATION_BUCKETS_DEPLOY,
    registry=PROMETHEUS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Kubernetes API
# ---------------------------------------------------------------------------

K8S_API_LATENCY = Histogram(
    "liftwork_k8s_api_latency_seconds",
    "Latency of Kubernetes API calls issued by the worker.",
    labelnames=("verb", "resource"),  # verb ∈ get|list|create|patch|delete|watch
    buckets=_DURATION_BUCKETS_SHORT,
    registry=PROMETHEUS_REGISTRY,
)

K8S_API_ERRORS = Counter(
    "liftwork_k8s_api_errors_total",
    "Kubernetes API errors keyed by HTTP status class.",
    labelnames=("verb", "resource", "status"),  # status ∈ 4xx|5xx|conflict|notfound
    registry=PROMETHEUS_REGISTRY,
)

CLUSTER_HEALTHY = Gauge(
    "liftwork_cluster_healthy",
    "1 if the most recent health probe to the cluster succeeded, else 0.",
    labelnames=("cluster",),
    registry=PROMETHEUS_REGISTRY,
)

CLUSTER_LAST_PROBE_AGE = Gauge(
    "liftwork_cluster_last_probe_age_seconds",
    "Seconds since the most recent successful health probe per cluster.",
    labelnames=("cluster",),
    registry=PROMETHEUS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Job queue (Redis / arq)
# ---------------------------------------------------------------------------

QUEUE_DEPTH = Gauge(
    "liftwork_queue_depth",
    "Pending arq jobs by job name.",
    labelnames=("job",),  # job ∈ run_build|run_deploy
    registry=PROMETHEUS_REGISTRY,
)

JOBS_COMPLETED = Counter(
    "liftwork_jobs_completed_total",
    "Arq jobs completed by name and outcome.",
    labelnames=("job", "outcome"),  # outcome ∈ success|failure|skipped
    registry=PROMETHEUS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Webhooks
# ---------------------------------------------------------------------------

WEBHOOKS_RECEIVED = Counter(
    "liftwork_webhooks_received_total",
    "Inbound GitHub webhooks classified by event and resulting action.",
    labelnames=("event", "action"),
    # event ∈ push|ping|pull_request|installation|...
    # action ∈ enqueued|deduped|ignored|invalid_signature|app_not_found
    registry=PROMETHEUS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Errors (cross-cutting)
# ---------------------------------------------------------------------------

ERRORS = Counter(
    "liftwork_errors_total",
    "Categorised errors across the build/deploy pipeline.",
    labelnames=("category", "stage"),
    # category ∈ git_clone | config_invalid | build_failed | image_push_failed |
    #            k8s_apply_failed | rollout_timeout | probe_failed |
    #            image_pull_failed | crash_loop | unknown
    # stage    ∈ webhook | build | deploy | rollout
    registry=PROMETHEUS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Helpers — keep the call sites short and consistent.
# ---------------------------------------------------------------------------


def record_build_started(*, language: str, source: str) -> None:
    BUILDS_STARTED.labels(language=language, source=source).inc()
    ACTIVE_BUILDS.inc()


def record_build_finished(
    *,
    language: str,
    status: str,
    duration_seconds: float,
    image_bytes: int | None = None,
) -> None:
    BUILDS_FINISHED.labels(language=language, status=status).inc()
    BUILD_DURATION.labels(language=language, status=status).observe(duration_seconds)
    if image_bytes is not None and image_bytes > 0:
        BUILD_IMAGE_BYTES.labels(language=language).observe(image_bytes)
    ACTIVE_BUILDS.dec()


def record_deploy_started(*, cluster: str) -> None:
    DEPLOYS_STARTED.labels(cluster=cluster).inc()
    ACTIVE_DEPLOYS.inc()


def record_deploy_finished(
    *,
    cluster: str,
    outcome: str,
    duration_seconds: float,
) -> None:
    DEPLOYS_FINISHED.labels(cluster=cluster, outcome=outcome).inc()
    DEPLOY_DURATION.labels(cluster=cluster, outcome=outcome).observe(duration_seconds)
    ACTIVE_DEPLOYS.dec()


def record_error(*, category: str, stage: str) -> None:
    """Bump the cross-cutting error counter. Use sparingly — only on
    classified failure events the user could plausibly act on."""
    ERRORS.labels(category=category, stage=stage).inc()


def record_k8s_call(
    *,
    verb: str,
    resource: str,
    duration_seconds: float,
    error_status: str | None = None,
) -> None:
    K8S_API_LATENCY.labels(verb=verb, resource=resource).observe(duration_seconds)
    if error_status is not None:
        K8S_API_ERRORS.labels(verb=verb, resource=resource, status=error_status).inc()
