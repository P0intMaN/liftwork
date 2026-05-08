# Observability

Liftwork emits **logs**, **metrics**, and **traces** for every meaningful
event in the build/deploy pipeline. Bring your own collectors — there is
no embedded observability stack today (a `liftwork-observability`
subchart lands in Phase 6).

## Channels

| Signal | Source | Endpoint | Format |
|---|---|---|---|
| **Structured logs** | API + worker | stdout | JSON (`structlog`) — set `LIFTWORK_USE_JSON_LOGS=true` |
| **Prometheus metrics** | API | `:7878/metrics` | Prometheus exposition |
| **Prometheus metrics** | Worker | `:7879/metrics` (worker `health_port`) | Prometheus exposition |
| **OTLP traces + metrics** | API + worker | gRPC → `LIFTWORK_TELEMETRY__OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP/gRPC |

Set `LIFTWORK_TELEMETRY__OTEL_ENABLED=true` and point
`LIFTWORK_TELEMETRY__OTEL_EXPORTER_OTLP_ENDPOINT` at any OTel collector
(Datadog Agent, HyperDX, Grafana Tempo, Honeycomb, the OpenTelemetry
Collector).

## Metrics catalog

All instruments are defined in
[`packages/core/src/liftwork_core/metrics.py`](../packages/core/src/liftwork_core/metrics.py).
Names follow Prometheus conventions: `liftwork_<subject>_<unit>`.

### Build lifecycle

- `liftwork_builds_started_total{language, source}` — counter
- `liftwork_builds_finished_total{language, status}` — counter
- `liftwork_build_duration_seconds{language, status}` — histogram
- `liftwork_build_image_bytes{language}` — histogram (compressed image size)
- `liftwork_active_builds` — gauge

### Deploy lifecycle

- `liftwork_deploys_started_total{cluster}` — counter
- `liftwork_deploys_finished_total{cluster, outcome}` — counter
- `liftwork_deploy_duration_seconds{cluster, outcome}` — histogram
- `liftwork_active_deploys` — gauge

### Kubernetes API

- `liftwork_k8s_api_latency_seconds{verb, resource}` — histogram
- `liftwork_k8s_api_errors_total{verb, resource, status}` — counter
- `liftwork_cluster_healthy{cluster}` — gauge (1 = last probe ok)
- `liftwork_cluster_last_probe_age_seconds{cluster}` — gauge

### Image registry

- `liftwork_registry_push_duration_seconds` — histogram

### Job queue (arq)

- `liftwork_queue_depth{job}` — gauge
- `liftwork_jobs_completed_total{job, outcome}` — counter

### Webhooks

- `liftwork_webhooks_received_total{event, action}` — counter

### Cross-cutting errors

- `liftwork_errors_total{category, stage}` — counter
  - **categories:** `git_clone`, `config_invalid`, `build_failed`,
    `image_push_failed`, `k8s_apply_failed`, `rollout_timeout`,
    `probe_failed`, `image_pull_failed`, `crash_loop`, `deploy_failed`,
    `unknown`
  - **stages:** `webhook`, `build`, `deploy`, `rollout`

### Cardinality

Every label is bounded by an enum or a small finite set
(Language, BuildStatus, RolloutOutcome, k8s verbs, cluster names). No
free-form labels (no `app_slug` on metrics) — that's what traces are for.

## Tracing

Job-level OTel spans:

- **`build.run`** — root span per `run_build` invocation. Attributes:
  `liftwork.build_id`, `liftwork.application_slug`, `liftwork.branch`,
  `liftwork.commit_sha`, `liftwork.language`.
- **`deploy.run`** — root span per `run_deploy`. Attributes:
  `liftwork.build_id`, `liftwork.application_slug`, `liftwork.cluster`,
  `liftwork.namespace`.

Child spans across orchestration stages (git.clone, image.push, k8s.apply,
rollout.watch) are on the polish list.

## Grafana dashboards

Two ready-to-import dashboards live at
[`charts/liftwork/dashboards/`](../charts/liftwork/dashboards/):

- **`liftwork-operations.json`** — operator view: build/deploy success
  rate, p50/p95/p99 duration by language and cluster, throughput,
  outcome breakdown, image footprint, webhook activity, top error
  categories. Default time range 6h.
- **`liftwork-sre.json`** — SRE view: cluster availability + heartbeat
  per cluster, k8s API latency by verb/resource, k8s error rate by
  status class, active jobs gauges, queue depth, registry push p95,
  HTTP route latency. Default time range 3h. Cluster filter variable.

Both dashboards use a `${datasource}` Prometheus variable so they work
against any Prom-compatible source. Import via Grafana UI:
*Dashboards → New → Import → Upload JSON file*.
