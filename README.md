# liftwork

> Plug-and-play Kubernetes build & deploy platform.
> Self-hosted "internal Heroku" — drop in a Helm chart, point at a repo, get a deploy.

[![ci](https://github.com/P0intMaN/liftwork/actions/workflows/ci.yaml/badge.svg)](https://github.com/P0intMaN/liftwork/actions/workflows/ci.yaml)
[![license](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

---

## What it solves

Today, getting any repo onto Kubernetes is a 10-step ordeal: write a Dockerfile, build the image, push to a registry, write manifests or a Helm chart, set up RBAC, manage secrets, apply, watch the rollout. ArgoCD/Flux assume you've already done that work. Heroku/Render/Railway lock you into their cloud.

**liftwork** closes that gap. Install once into your cluster, connect a repo, and `git push` becomes a deploy.

## Architecture

```
React/shadcn UI ── FastAPI API ── Postgres
                       │
                       └── Redis (arq) ── Worker(s) ── Build engine (BuildKit rootless, in-cluster)
                                                  └── Deploy engine (k8s python client)
                                                  └── OTel + Prometheus
```

All of this is packaged as one Helm chart (`charts/liftwork`) with optional bundled Postgres/Redis subcharts.

## Project layout

```
liftwork/
├── apps/
│   ├── api/          FastAPI service: REST + webhooks + dashboard backend
│   ├── worker/       arq worker: build + deploy job runner
│   └── dashboard/    Vite + React + shadcn (Phase 5)
├── packages/
│   └── core/         Shared: settings, db (SQLAlchemy 2.0 async), telemetry, models
├── charts/liftwork/  Helm chart (Phase 6)
├── deploy/           docker-compose for local dev
└── .github/workflows
```

## Quick start (local dev)

Prereqs (WSL2 Ubuntu): Python 3.12, [uv](https://docs.astral.sh/uv/), Node 20+, pnpm, Docker, kubectl, Helm.

```bash
git clone git@github.com:P0intMaN/liftwork.git
cd liftwork
make bootstrap       # uv sync + pnpm install + pre-commit install
cp .env.example .env

make dev-up          # postgres + redis via docker-compose
make dev-api         # http://localhost:8000/docs
# in another shell:
make dev-worker
```

## Tech choices (v1)

| Concern | Choice | Why |
|---|---|---|
| Web framework | FastAPI + uvicorn | async, OpenAPI, OTel-first |
| ORM | SQLAlchemy 2.0 async + Alembic | industry standard, mature async |
| Queue | Redis + arq | asyncio-native, light, OTel-friendly; abstracted for v2 swap to Temporal |
| Build executor | BuildKit rootless (in-cluster `Job`) | no privileged containers; cache + multi-arch + secret mounts |
| Registry | GHCR (interface stubbed for ECR/Quay/Hub later) | repo-native; works out of the box |
| Auth (v1) | local password + JWT | OIDC arrives in v2 |
| Telemetry | structlog + OpenTelemetry + Prometheus | OTLP-exportable to Datadog / HyperDX / Grafana |

## License

Apache 2.0 — see [LICENSE](LICENSE).
