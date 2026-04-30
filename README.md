# liftwork
![liftwork logo](https://github.com/user-attachments/assets/fefe241b-b87d-4414-93f6-55094ae3a9fa)

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
make dev-api         # http://localhost:7878/docs
# in another shell:
make dev-worker
```

## Real e2e against a kind cluster

The default `make dev-worker` runs in **mock mode** — it walks every state
transition (queued → running → succeeded → deploy succeeded) without
touching a registry or a Kubernetes cluster. To exercise the real
BuildKit-in-pod + server-side-apply path against a local kind cluster:

```bash
# 0. one-time: stand up the kind cluster (3 nodes, k8s 1.31)
kind create cluster --name kubedeploy-dev --config deploy/kind-cluster.yaml

# 1. apply liftwork ns + RBAC + in-cluster registry, patch every node's
#    containerd to mirror registry.liftwork.svc.cluster.local:5000 through
#    the registry's NodePort at http://localhost:30500. Idempotent.
make kind-prereqs

# 2. flip the worker into kind mode by exporting these before make dev-worker:
export LIFTWORK_WORKER__EXECUTOR=kind
export LIFTWORK_K8S__KUBE_CONTEXT=kind-kubedeploy-dev
export LIFTWORK_REGISTRY__HOST=registry.liftwork.svc.cluster.local:5000
export LIFTWORK_REGISTRY__INSECURE=true
make dev-worker
```

After that, a `git push` to a connected application will:

1. arq picks up the `run_build` job
2. worker `git clone --depth 1` the target branch into a tempdir
3. orchestrator detects language and renders `Dockerfile.liftwork` (unless
   the repo committed its own `Dockerfile`)
4. `K8sBuildKitExecutor` creates a ConfigMap with the rendered Dockerfile,
   submits a `batch/v1` Job running `moby/buildkit:rootless`, tails its
   pod logs, parses the sha256 digest from the trailing `LIFTWORK_DIGEST=`
   marker
5. Image is pushed (over HTTP, `registry.insecure=true`) to the in-cluster
   `registry:2`; status transitions to `succeeded`
6. `auto_deploy=true` → `run_deploy` is enqueued
7. `K8sDeployExecutor` does server-side apply of Deployment + Service
   (+ optional Ingress) into the application's target namespace; watches
   the rollout via `apps_v1.read_namespaced_deployment` until ready /
   timed-out / failed

`make kind-down` tears the liftwork namespace back down.

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
