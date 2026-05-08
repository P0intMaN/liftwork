# Installing liftwork via Helm

Liftwork ships as a single Helm chart at `charts/liftwork`. One install
gives you the API, worker, and dashboard in any namespace you choose.

## Prerequisites

- Kubernetes 1.27+
- Helm 3.13+
- An ingress controller (optional, for in-cluster URLs)
- A container registry the cluster can pull from (`ghcr.io`, ECR, GAR, in-cluster)

For a true zero-deps install on dev: enable the bundled Postgres + Redis
subcharts (`postgresql.enabled=true,redis.enabled=true`).

## Quick start (dev)

```bash
helm dep update charts/liftwork
helm upgrade --install lw charts/liftwork \
  --namespace liftwork --create-namespace \
  -f charts/liftwork/values.dev.yaml
```

That installs:
- Three Deployments (`lw-api`, `lw-worker`, `lw-dashboard`)
- A `pre-install` Job that runs `alembic upgrade head` against the bundled Postgres
- Bundled `lw-postgresql` (StatefulSet) + `lw-redis-master` (StatefulSet)
- A worker `Role` + `RoleBinding` for BuildKit pod orchestration

Once the migrate Job completes (~30s), the API + dashboard become Ready.

## Reaching the dashboard

**Option A — port-forward** (no ingress needed):
```bash
kubectl --namespace liftwork port-forward svc/lw-dashboard 8080:80
open http://localhost:8080
```

**Option B — ingress**:
```bash
helm upgrade --install lw charts/liftwork \
  --namespace liftwork \
  --set ingress.enabled=true \
  --set ingress.host=liftwork.example.com \
  --set ingress.className=nginx \
  -f charts/liftwork/values.dev.yaml
```
The ingress routes `/api/*` to the API and `/*` to the dashboard.

## Required values

| Value | Required | Default |
|---|---|---|
| `secrets.jwtSecret` | ✅ (≥32 bytes) | _(none — install fails fast)_ |
| `secrets.bootstrapAdminPassword` | for first login | empty (skip bootstrap) |
| `externalDatabase.url` **or** `postgresql.enabled=true` | ✅ | _(none)_ |
| `externalRedis.url` **or** `redis.enabled=true` | ✅ | _(none)_ |
| `registry.host` | ✅ at runtime | empty |

Use `--set secrets.existingSecret=<name>` to point at an externally-managed
Secret (recommended for prod) — must contain
`LIFTWORK_JWT__SECRET`, `LIFTWORK_DATABASE__URL`, `LIFTWORK_REDIS__URL`,
and optionally `LIFTWORK_GITHUB__WEBHOOK_SECRET`.

## Per-tenant install (multi-tenant control plane)

```bash
helm upgrade --install lw-team-alpha charts/liftwork \
  --namespace tenants \
  --set namespace=team-alpha \
  --set namespaceCreate=true \
  -f team-alpha-values.yaml
```

The chart respects `.Values.namespace` over `.Release.Namespace`, so a
single Helm release can manage its own isolated namespace. With
`namespaceCreate=true`, the chart also creates the Namespace resource
itself.

## Observability

```bash
helm upgrade --install lw charts/liftwork \
  --set serviceMonitor.enabled=true \
  --set telemetry.otlp.endpoint=http://otel-collector.monitoring:4317
```

- `serviceMonitor.enabled=true` registers ServiceMonitors so kube-prometheus-stack
  scrapes `/metrics` on the API + worker.
- The two Grafana dashboards in `charts/liftwork/dashboards/*.json` are
  ready to import.
- Set `telemetry.otlp.endpoint` to ship traces + metrics to any OTLP collector
  (Datadog Agent, Tempo, HyperDX, vendor of choice).

See [`docs/observability.md`](observability.md) for the full metrics catalog.

## Production defaults to flip

```yaml
# values.prod.yaml
secrets:
  existingSecret: liftwork-prod-secrets   # managed by your secrets operator

api:
  replicaCount: 3
  autoscaling:
    enabled: true
    minReplicas: 3
    maxReplicas: 10

worker:
  replicaCount: 1                         # do not raise — see values.yaml comment
  concurrency: 8

postgresql:
  enabled: false                          # use managed Postgres
externalDatabase:
  url: postgresql+asyncpg://liftwork:****@db.internal:5432/liftwork

redis:
  enabled: false
externalRedis:
  url: redis://redis.internal:6379/0

ingress:
  enabled: true
  className: nginx
  host: liftwork.your-company.com
  tls:
    enabled: true
    secretName: liftwork-tls

serviceMonitor:
  enabled: true

telemetry:
  otlp:
    endpoint: http://otel-collector.monitoring:4317
```

## Uninstall

```bash
helm uninstall lw --namespace liftwork
```

Bundled Postgres + Redis PVCs are *not* deleted automatically — `kubectl
delete pvc -n liftwork -l app.kubernetes.io/instance=lw` to reclaim
storage.

## Validation + tests

```bash
make helm-lint        # helm lint with required values stubbed
make helm-template    # full render of every kind we ship
uv run pytest charts/liftwork/tests/   # 11 helm-template assertions
```
