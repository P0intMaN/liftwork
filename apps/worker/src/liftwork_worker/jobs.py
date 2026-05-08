"""arq job handlers — `run_build` and `run_deploy`.

These are thin wrappers around the orchestrators in
`liftwork_worker.orchestrator` and `liftwork_worker.deploy.orchestrator`.
They own state-machine transitions (queued → running → succeeded/failed)
and Redis log fan-out, but defer all the actual build/deploy work to
the executor protocols.
"""

from __future__ import annotations

import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from opentelemetry import trace
from sqlalchemy import func, select

from liftwork_core import metrics
from liftwork_core.build.config import LiftworkConfigError
from liftwork_core.build.defaults import DeployDefaults, infer_deploy_defaults
from liftwork_core.build.diagnostics import classify_build_error
from liftwork_core.build.effective import effective_deploy_spec, parse_liftwork_yaml
from liftwork_core.build.language import detect_language
from liftwork_core.db.models import (
    Application,
    BuildRun,
    BuildStatus,
    Deployment,
    DeploymentStatus,
)
from liftwork_core.deploy import (
    DeployRequest,
    DeployTarget,
    RolloutOutcome,
)
from liftwork_core.repositories import (
    ApplicationRepository,
    BuildRunRepository,
    ClusterRepository,
)
from liftwork_worker.deploy.orchestrator import orchestrate_deploy
from liftwork_worker.git import GitCloneError, shallow_clone
from liftwork_worker.log_sinks import InMemoryLogSink, TeeLogSink
from liftwork_worker.orchestrator import BuildRequest, orchestrate_build
from liftwork_worker.redis_log import (
    RedisPubSubLogSink,
    channel_for_build,
    channel_for_deploy,
)
from liftwork_worker.state import WorkerState, get_state

log = structlog.get_logger("liftwork.worker.jobs")
tracer = trace.get_tracer("liftwork.worker.jobs")


# ---------------------------------------------------------------------------
# Build job
# ---------------------------------------------------------------------------


@dataclass
class _BuildMetricsState:
    """Mutable per-build metrics scratchpad. ACTIVE_BUILDS is incremented
    immediately so even early bail-outs decrement it; the rest of the
    metrics are emitted on `flush()` from the run_build finally block."""

    started_at: float = field(default_factory=time.perf_counter)
    source: str = "unknown"
    language: str = "unknown"
    status: str = "failed"  # default — overridden on success path
    image_bytes: int | None = None
    _started: bool = False

    def __post_init__(self) -> None:
        metrics.ACTIVE_BUILDS.inc()
        self._started = True

    def flush(self) -> None:
        if not self._started:
            return
        elapsed = time.perf_counter() - self.started_at
        metrics.BUILDS_STARTED.labels(language=self.language, source=self.source).inc()
        metrics.BUILDS_FINISHED.labels(language=self.language, status=self.status).inc()
        metrics.BUILD_DURATION.labels(
            language=self.language,
            status=self.status,
        ).observe(elapsed)
        if self.image_bytes is not None and self.image_bytes > 0:
            metrics.BUILD_IMAGE_BYTES.labels(language=self.language).observe(self.image_bytes)
        metrics.ACTIVE_BUILDS.dec()
        self._started = False


@dataclass
class _DeployMetricsState:
    started_at: float = field(default_factory=time.perf_counter)
    cluster: str = "unknown"
    outcome: str = "failed"
    _started: bool = False

    def __post_init__(self) -> None:
        metrics.ACTIVE_DEPLOYS.inc()
        self._started = True

    def flush(self) -> None:
        if not self._started:
            return
        elapsed = time.perf_counter() - self.started_at
        metrics.DEPLOYS_STARTED.labels(cluster=self.cluster).inc()
        metrics.DEPLOYS_FINISHED.labels(cluster=self.cluster, outcome=self.outcome).inc()
        metrics.DEPLOY_DURATION.labels(
            cluster=self.cluster,
            outcome=self.outcome,
        ).observe(elapsed)
        metrics.ACTIVE_DEPLOYS.dec()
        self._started = False


async def run_build(ctx: dict[str, Any], build_run_id: str) -> dict[str, Any]:  # noqa: PLR0915
    """Execute one queued BuildRun. Idempotent on repeated calls."""
    with tracer.start_as_current_span("build.run") as span:
        span.set_attribute("liftwork.build_id", build_run_id)
        return await _run_build_impl(ctx, build_run_id, span)


async def _run_build_impl(  # noqa: PLR0915
    ctx: dict[str, Any],
    build_run_id: str,
    span: trace.Span,
) -> dict[str, Any]:
    state = get_state(ctx)
    run_id = UUID(build_run_id)
    arq_pool = ctx.get("redis")  # arq sets this
    log.info("build.start", build_id=str(run_id))

    archive_sink = InMemoryLogSink()
    pubsub_sink = RedisPubSubLogSink(state.redis, channel_for_build(run_id))
    sink = TeeLogSink([archive_sink, pubsub_sink])

    workspace = Path(tempfile.mkdtemp(prefix=f"liftwork-build-{run_id}-"))
    # Metrics state — set as we learn it, emitted in the outer finally.
    metrics_state = _BuildMetricsState()
    try:
        run, application = await _claim_build(state, run_id)
        if run is None:
            await sink.write(f"[build] {run_id} not found — nothing to do")
            return {"status": "missing"}

        metrics_state.source = run.source.value
        span.set_attribute("liftwork.application_slug", application.slug)
        span.set_attribute("liftwork.branch", run.branch)
        span.set_attribute("liftwork.commit_sha", run.commit_sha)
        await sink.write(f"[build] {run.commit_sha[:7]}@{run.branch} app={application.slug}")

        is_real = state.settings.worker.executor != "mock"
        if is_real:
            # Real path: clone the repo so the orchestrator's language
            # detector + Dockerfile renderer have files to work with. The
            # BuildKit Job re-clones inside its init container (wasteful
            # but simple — workspace tarball mounting comes later).
            try:
                await shallow_clone(
                    repo_url=application.repo_url,
                    branch=run.branch,
                    target_dir=workspace / "repo",
                    log_sink=sink,
                )
                workspace_for_orch = workspace / "repo"
            except GitCloneError as exc:
                metrics.record_error(category="git_clone", stage="build")
                await _mark_build(
                    state,
                    run_id,
                    status=BuildStatus.failed,
                    error=f"git clone failed: {exc}",
                    log_excerpt=archive_sink.excerpt(),
                )
                await sink.write(f"[build] git clone failed — {exc}")
                return {"status": "failed", "error": str(exc)}

            # File wins: capture liftwork.yaml from the cloned repo so the
            # deploy job has authoritative config. Validation failures fail
            # the build immediately with a clean error.
            try:
                yaml_text = _read_and_validate_liftwork_yaml(workspace_for_orch)
            except LiftworkConfigError as exc:
                metrics.record_error(category="config_invalid", stage="build")
                await _mark_build(
                    state,
                    run_id,
                    status=BuildStatus.failed,
                    error=str(exc),
                    log_excerpt=archive_sink.excerpt(),
                )
                await sink.write(f"[build] {exc}")
                return {"status": "failed", "error": str(exc)}
            if yaml_text is not None:
                await sink.write("[build] parsed liftwork.yaml")
        else:
            # Mock path: the mock executor ignores the workspace; we just
            # need *something* the orchestrator's language detector can
            # resolve. A bare `Dockerfile` makes it pick `static`.
            (workspace / "Dockerfile").write_text(
                "# placeholder — mock executor mode\nFROM scratch\n",
                encoding="utf-8",
            )
            workspace_for_orch = workspace
            yaml_text = None

        metrics_state.language = detect_language(workspace_for_orch).language.value
        span.set_attribute("liftwork.language", metrics_state.language)
        await _capture_build_inputs(
            state,
            run_id,
            workspace=workspace_for_orch,
            yaml_text=yaml_text,
            sink=sink,
        )

        try:
            result = await orchestrate_build(
                BuildRequest(
                    workspace=workspace_for_orch,
                    repo_owner=application.repo_owner,
                    repo_name=application.repo_name,
                    branch=run.branch,
                    commit_sha=run.commit_sha,
                    image_repository=application.image_repository,
                    registry_host=state.settings.registry.host,
                    push=is_real,
                    repo_url=application.repo_url,
                    build_id=str(run_id),
                    registry_insecure=state.settings.registry.insecure,
                ),
                executor=state.build_executor,
                log_sink=sink,
            )
        except Exception as exc:  # noqa: BLE001 — capture and persist any failure
            log_tail = archive_sink.excerpt()
            diagnosis = classify_build_error(
                error_text=str(exc),
                log_excerpt=log_tail,
            )
            if diagnosis is not None:
                metrics.record_error(category=diagnosis.category.value, stage="build")
                error_text = f"{diagnosis.message}\n\n--- raw ---\n{exc}"
                await sink.write(f"[build] {diagnosis.message}")
            else:
                metrics.record_error(category="build_failed", stage="build")
                error_text = str(exc)
            await _mark_build(
                state,
                run_id,
                status=BuildStatus.failed,
                error=error_text,
                log_excerpt=log_tail,
            )
            await sink.write(f"[build] FAILED — {exc}")
            log.warning("build.failed", build_id=str(run_id), error=str(exc))
            return {"status": "failed", "error": error_text}

        metrics_state.status = "succeeded"
        metrics_state.image_bytes = getattr(result.image, "size_bytes", None)
        await _mark_build(
            state,
            run_id,
            status=BuildStatus.succeeded,
            image_tag=result.image.tag,
            image_digest=result.image.digest,
            log_excerpt=archive_sink.excerpt(),
        )
        await sink.write(f"[build] succeeded image={result.image.reference}")
        log.info(
            "build.succeeded",
            build_id=str(run_id),
            digest=result.image.digest,
            tag=result.image.tag,
        )

        if application.auto_deploy and arq_pool is not None:
            await arq_pool.enqueue_job("run_deploy", build_run_id=str(run_id))
            await sink.write(f"[build] enqueued run_deploy for {run_id}")

        return {
            "status": "succeeded",
            "image_tag": result.image.tag,
            "image_digest": result.image.digest,
        }
    finally:
        metrics_state.flush()
        await sink.close()
        shutil.rmtree(workspace, ignore_errors=True)


async def _claim_build(state: WorkerState, run_id: UUID) -> tuple[BuildRun | None, Application]:
    async with state.session_factory() as session:
        runs = BuildRunRepository(session)
        run = await runs.get_by_id(run_id)
        if run is None:
            return None, _placeholder_application()
        apps = ApplicationRepository(session)
        application = await apps.get_by_id(run.application_id)
        if application is None:
            return None, _placeholder_application()

        run = await runs.update_status(run, status=BuildStatus.running)
        await session.commit()
        await session.refresh(run)
        await session.refresh(application)
        # Detach from session — caller uses these objects post-commit.
        session.expunge(run)
        session.expunge(application)
        return run, application


def _placeholder_application() -> Application:
    return Application(
        slug="<missing>",
        display_name="<missing>",
        repo_url="",
        repo_owner="",
        repo_name="",
        default_branch="main",
        cluster_id=UUID("00000000-0000-0000-0000-000000000000"),
        namespace="default",
        image_repository="",
    )


def _read_and_validate_liftwork_yaml(workspace: Path) -> str | None:
    """Return the raw text of `<workspace>/liftwork.yaml`, or None if absent."""
    yaml_path = workspace / "liftwork.yaml"
    if not yaml_path.is_file():
        return None
    text = yaml_path.read_text(encoding="utf-8")
    parse_liftwork_yaml(text)  # raises LiftworkConfigError on bad input
    return text


async def _capture_build_inputs(
    state: WorkerState,
    run_id: UUID,
    *,
    workspace: Path,
    yaml_text: str | None,
    sink: TeeLogSink,
) -> None:
    """Infer language/EXPOSE defaults and persist them + liftwork.yaml on the run."""
    defaults = infer_deploy_defaults(workspace)
    await sink.write(
        f"[build] inferred port={defaults.port} health={defaults.health_check_path}"
        f" (source={defaults.source})"
    )
    async with state.session_factory() as session:
        runs = BuildRunRepository(session)
        run = await runs.get_by_id(run_id)
        if run is None:
            return
        await runs.set_deploy_config_yaml(run, yaml_text=yaml_text)
        await runs.set_inferred_defaults(run, defaults=defaults.to_dict())
        await session.commit()


async def _mark_build(
    state: WorkerState,
    run_id: UUID,
    *,
    status: BuildStatus,
    error: str | None = None,
    image_tag: str | None = None,
    image_digest: str | None = None,
    log_excerpt: str | None = None,
) -> None:
    async with state.session_factory() as session:
        runs = BuildRunRepository(session)
        run = await runs.get_by_id(run_id)
        if run is None:
            return
        await runs.update_status(
            run,
            status=status,
            error=error,
            image_tag=image_tag,
            image_digest=image_digest,
        )
        # store a compact log excerpt on the row so the UI can show the tail
        # even when the SSE channel has gone silent.
        if log_excerpt is not None and run.log_object_key is None:
            run.log_object_key = "memory:archive"
        await session.commit()


# ---------------------------------------------------------------------------
# Deploy job
# ---------------------------------------------------------------------------


async def run_deploy(ctx: dict[str, Any], build_run_id: str) -> dict[str, Any]:
    with tracer.start_as_current_span("deploy.run") as span:
        span.set_attribute("liftwork.build_id", build_run_id)
        return await _run_deploy_impl(ctx, build_run_id, span)


async def _run_deploy_impl(  # noqa: PLR0915
    ctx: dict[str, Any],
    build_run_id: str,
    span: trace.Span,
) -> dict[str, Any]:
    state = get_state(ctx)
    run_id = UUID(build_run_id)
    log.info("deploy.start", build_id=str(run_id))

    archive_sink = InMemoryLogSink()
    metrics_state = _DeployMetricsState()

    async with state.session_factory() as session:
        runs = BuildRunRepository(session)
        run = await runs.get_by_id(run_id)
        if run is None or run.image_tag is None or run.image_digest is None:
            log.warning("deploy.skipped_no_image", build_id=str(run_id))
            metrics_state.outcome = "skipped"
            metrics_state.flush()
            return {"status": "skipped", "reason": "build incomplete"}
        apps = ApplicationRepository(session)
        application = await apps.get_by_id(run.application_id)
        if application is None:
            metrics_state.outcome = "skipped"
            metrics_state.flush()
            return {"status": "skipped", "reason": "application missing"}
        clusters = ClusterRepository(session)
        cluster = await clusters.get_by_id(application.cluster_id)
        if cluster is None:
            metrics_state.outcome = "skipped"
            metrics_state.flush()
            return {"status": "skipped", "reason": "cluster missing"}
        metrics_state.cluster = cluster.name
        span.set_attribute("liftwork.application_slug", application.slug)
        span.set_attribute("liftwork.cluster", cluster.name)
        span.set_attribute("liftwork.namespace", application.namespace)

        revision = await _next_revision(session, application_id=application.id)
        deployment = Deployment(
            application_id=application.id,
            build_run_id=run.id,
            cluster_id=cluster.id,
            namespace=application.namespace,
            image_tag=run.image_tag,
            image_digest=run.image_digest,
            revision=revision,
            status=DeploymentStatus.pending,
        )
        session.add(deployment)
        await session.commit()
        await session.refresh(deployment)
        await session.refresh(application)
        await session.refresh(cluster)
        session.expunge(deployment)
        session.expunge(application)
        session.expunge(cluster)

    pubsub_sink = RedisPubSubLogSink(state.redis, channel_for_deploy(deployment.id))
    sink = TeeLogSink([archive_sink, pubsub_sink])

    try:
        # File-wins: build the spec from the parsed liftwork.yaml if the
        # build captured one. Falls back to the inferred defaults stamped
        # at build time, then to the Application row's columns for
        # legacy builds that predate the inference pass.
        inferred = (
            DeployDefaults.from_dict(run.inferred_defaults_json)
            if run.inferred_defaults_json
            else None
        )
        deploy_spec = effective_deploy_spec(
            application=application,
            inferred_defaults=inferred,
            liftwork_yaml=run.deploy_config_yaml,
        )
        deploy_request = DeployRequest(
            target=DeployTarget(cluster_name=cluster.name, namespace=application.namespace),
            application_slug=application.slug,
            application_id=str(application.id),
            # Digest-pinned ref so kubelet always pulls the exact image
            # this build produced (mutable tags + IfNotPresent caching can
            # otherwise serve a stale layer).
            image_ref=(
                f"{state.settings.registry.host}/{application.image_repository}@{run.image_digest}"
            ),
            image_digest=run.image_digest,
            image_tag=run.image_tag,
            deploy_spec=deploy_spec,
            revision=revision,
            commit_sha=run.commit_sha,
            branch=run.branch,
        )
        result = await orchestrate_deploy(
            deploy_request,
            executor=state.deploy_executor,
            log_sink=sink,
        )

        await _mark_deploy(
            state,
            deployment.id,
            outcome=result.outcome,
            error=result.error,
        )
        metrics_state.outcome = result.outcome.value
        if result.outcome is not RolloutOutcome.succeeded:
            metrics.record_error(category="deploy_failed", stage="deploy")
        await sink.write(f"[deploy] outcome={result.outcome.value} revision={revision}")
        return {
            "status": result.outcome.value,
            "deployment_id": str(deployment.id),
            "revision": revision,
        }
    finally:
        metrics_state.flush()
        await sink.close()


async def _next_revision(session: Any, *, application_id: UUID) -> int:
    result = await session.execute(
        select(func.coalesce(func.max(Deployment.revision), 0)).where(
            Deployment.application_id == application_id,
        )
    )
    return int(result.scalar() or 0) + 1


async def _mark_deploy(
    state: WorkerState,
    deployment_id: UUID,
    *,
    outcome: RolloutOutcome,
    error: str | None,
) -> None:
    async with state.session_factory() as session:
        deployment = await session.get(Deployment, deployment_id)
        if deployment is None:
            return
        deployment.status = (
            DeploymentStatus.succeeded
            if outcome is RolloutOutcome.succeeded
            else DeploymentStatus.failed
        )
        if error is not None:
            deployment.error = error
        deployment.finished_at = datetime.now(UTC)
        await session.commit()
