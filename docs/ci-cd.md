# CI/CD

Three GitHub Actions workflows live at `.github/workflows/`:

## `ci.yaml` — PR validation

Triggered on every `pull_request` and `push: main`. Three jobs run in parallel:

| Job | What it runs | ~time |
|---|---|---|
| **python** | `uv sync`, `ruff check`, `ruff format --check`, `mypy`, `pytest` against ephemeral `postgres:16` + `redis:7` service containers | 4-6 min |
| **dashboard** | `npm ci`, `tsc --noEmit`, `npm run build` | 2-3 min |
| **helm** | `helm dep update`, `helm lint`, `helm template`, the 11 chart-render assertions | 2 min |

Concurrency is grouped per branch with `cancel-in-progress`, so a force-push
during CI cancels the stale run. No paths-filter today — fast enough not to
need one yet; revisit if minutes get tight.

## `release.yaml` — packaging + publishing

Triggered on `git tag v*`. Four jobs in series:

1. **images** — multi-arch (`linux/amd64,linux/arm64`) builds of
   `liftwork-api`, `liftwork-worker`, `liftwork-dashboard` via
   `docker/build-push-action`. Each image gets:
   - SBOM + provenance attestations (`sbom: true, provenance: true`)
   - cosign keyless signature (sigstore via GitHub OIDC — no key material)
   - Tags: `vX.Y.Z`, `X.Y.Z`, `X.Y`, `latest`
2. **chart** — packages `charts/liftwork`, pushes to GHCR as an OCI
   artifact (`oci://ghcr.io/<owner>/liftwork`), signs with cosign keyless,
   uploads the `.tgz` as a workflow artifact for the next job.
3. **smoke** — pulls the just-published chart into a fresh kind cluster,
   waits for all three Deployments to reach Available, then port-forwards
   and hits `/healthz`. **Fails the release if anything's broken** — no
   silently-bad tags shipping.
4. **github-release** — creates the GitHub Release with auto-generated
   notes (`generate_release_notes: true`) and attaches the chart `.tgz`.

To cut a release:
```bash
git tag v0.2.0
git push --tags
```
The workflow handles everything else.

## `e2e.yaml` — full integration test

Triggered nightly (03:00 UTC), on `workflow_dispatch`, and on PRs **only
when the `e2e` label is set** (saves CI minutes on docs PRs).

Spins up:
- A kind cluster (default config)
- Locally-built images (`docker build` + `kind load`) so we don't depend
  on registry access
- The in-cluster registry + RBAC + containerd mirror config from
  `scripts/setup-kind-registry.sh`
- The chart via `helm install`

Then runs `scripts/e2e_smoke.py`, which:
1. Logs in with bootstrap admin
2. Creates a Cluster row (`in_cluster=true`)
3. Creates an Application backed by `docker/welcome-to-docker`
4. Triggers a manual build
5. Polls until both build + deploy reach a terminal status
6. Asserts they succeeded

If any step fails, the workflow dumps `kubectl describe pods`, the API +
worker logs, and the namespace's events for the last hour — the exact
data needed to triage.

## Required repository secrets / settings

| Setting | Why |
|---|---|
| `GITHUB_TOKEN` | Auto-provided. Used for GHCR push + Release create. |
| Repository: Settings → Actions → Workflow permissions → "Read and write" | Otherwise `contents: write` and `packages: write` fail. |

cosign signing uses GitHub's OIDC token — no additional secrets needed.

## Triggering an e2e on a PR

Add the `e2e` label to the PR. The workflow re-runs on `synchronize`, so
subsequent pushes will keep running e2e while the label is present.
Remove the label to skip on later pushes.
