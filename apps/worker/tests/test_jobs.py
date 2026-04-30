"""End-to-end tests for the build / deploy job handlers.

These run against the live Postgres + Redis services from `make dev-up`,
using mock executors. Skipped when those services aren't reachable.
"""

from __future__ import annotations

import os
import socket
from typing import Any
from uuid import UUID

import pytest
import redis.asyncio as redis_asyncio
from sqlalchemy import text

from liftwork_core.config import get_settings, reset_settings_cache
from liftwork_core.db import make_engine, make_session_factory
from liftwork_core.db.models import (
    Application,
    BuildRun,
    BuildSource,
    BuildStatus,
    Cluster,
    Deployment,
    DeploymentStatus,
)
from liftwork_core.deploy.protocols import RolloutOutcome
from liftwork_core.repositories import (
    ApplicationRepository,
    BuildRunRepository,
    ClusterRepository,
)
from liftwork_worker.jobs import run_build, run_deploy
from liftwork_worker.mock_executors import MockBuildExecutor, MockDeployExecutor
from liftwork_worker.state import STATE_KEY, WorkerState


def _service_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


_DEPS_UP = _service_reachable("127.0.0.1", 5432) and _service_reachable("127.0.0.1", 6379)

pytestmark = pytest.mark.skipif(not _DEPS_UP, reason="postgres+redis not reachable")


_TRUNCATE = (
    "TRUNCATE TABLE applications, clusters, build_runs, deployments, "
    "secrets, audit_logs, users RESTART IDENTITY CASCADE"
)


@pytest.fixture
async def state() -> WorkerState:
    os.environ.setdefault(
        "LIFTWORK_DATABASE__URL",
        "postgresql+asyncpg://liftwork:liftwork@localhost:5432/liftwork",
    )
    os.environ.setdefault("LIFTWORK_REDIS__URL", "redis://localhost:6379/0")
    os.environ.setdefault(
        "LIFTWORK_JWT__SECRET",
        "test-secret-not-for-production-32-bytes-min-please",
    )
    os.environ.setdefault("LIFTWORK_TELEMETRY__OTEL_ENABLED", "false")
    reset_settings_cache()
    settings = get_settings()

    engine = make_engine(settings.database)
    session_factory = make_session_factory(engine)
    redis_client: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        str(settings.redis.url), decode_responses=True
    )
    async with session_factory() as session:
        await session.execute(text(_TRUNCATE))
        await session.commit()
    return WorkerState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis_client,
        build_executor=MockBuildExecutor(),
        deploy_executor=MockDeployExecutor(),
    )


async def _seed(state: WorkerState, *, auto_deploy: bool = True) -> tuple[UUID, UUID, UUID]:
    """Seed cluster + app + queued build_run, return their ids."""
    async with state.session_factory() as session:
        cluster = await ClusterRepository(session).create(
            name="kind-jobs-test",
            display_name="kind for jobs",
            in_cluster=False,
            default_namespace="default",
        )
        await session.flush()
        app = await ApplicationRepository(session).create(
            slug="acme-jobs",
            display_name="Acme Jobs",
            repo_url="https://example.com/acme/api.git",
            repo_owner="acme",
            repo_name="api",
            default_branch="main",
            cluster_id=cluster.id,
            namespace="acme",
            image_repository="acme/api",
            auto_deploy=auto_deploy,
        )
        await session.flush()
        run = await BuildRunRepository(session).create(
            application_id=app.id,
            commit_sha="0123456789abcdef" * 2 + "01234567",
            branch="main",
            source=BuildSource.webhook,
        )
        await session.commit()
        return cluster.id, app.id, run.id


class _FakeArqPool:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []

    async def enqueue_job(self, name: str, **kwargs: Any) -> None:
        self.enqueued.append((name, kwargs))


async def test_run_build_succeeds_and_chains_deploy(state: WorkerState) -> None:
    _, _, run_id = await _seed(state, auto_deploy=True)
    pool = _FakeArqPool()
    ctx = {STATE_KEY: state, "redis": pool}

    result = await run_build(ctx, str(run_id))

    assert result["status"] == "succeeded"
    assert result["image_digest"].startswith("sha256:")
    assert result["image_tag"].startswith("main-")

    async with state.session_factory() as session:
        run = await session.get(BuildRun, run_id)
        assert run is not None
        assert run.status is BuildStatus.succeeded
        assert run.image_digest == result["image_digest"]
        assert run.image_tag == result["image_tag"]
        assert run.error is None
        assert run.started_at is not None
        assert run.finished_at is not None

    # Deploy was enqueued
    assert ("run_deploy", {"build_run_id": str(run_id)}) in pool.enqueued


async def test_run_build_records_failure(state: WorkerState) -> None:
    state.build_executor = MockBuildExecutor(fail_with="kaniko-style boom")  # type: ignore[assignment]
    _, _, run_id = await _seed(state, auto_deploy=True)
    pool = _FakeArqPool()
    ctx = {STATE_KEY: state, "redis": pool}

    result = await run_build(ctx, str(run_id))

    assert result["status"] == "failed"
    assert "boom" in result["error"]

    async with state.session_factory() as session:
        run = await session.get(BuildRun, run_id)
        assert run is not None
        assert run.status is BuildStatus.failed
        assert run.error is not None and "boom" in run.error
        assert run.finished_at is not None
    assert pool.enqueued == []  # no deploy chained


async def test_run_build_no_chain_when_auto_deploy_off(state: WorkerState) -> None:
    _, _, run_id = await _seed(state, auto_deploy=False)
    pool = _FakeArqPool()
    ctx = {STATE_KEY: state, "redis": pool}

    result = await run_build(ctx, str(run_id))
    assert result["status"] == "succeeded"
    assert pool.enqueued == []


async def test_run_build_handles_missing_row(state: WorkerState) -> None:
    pool = _FakeArqPool()
    ctx = {STATE_KEY: state, "redis": pool}
    result = await run_build(ctx, "00000000-0000-0000-0000-000000000000")
    assert result["status"] == "missing"


async def test_run_deploy_creates_deployment_and_marks_succeeded(
    state: WorkerState,
) -> None:
    _, app_id, run_id = await _seed(state, auto_deploy=True)
    # The build job needs to have produced an image first.
    await run_build({STATE_KEY: state, "redis": _FakeArqPool()}, str(run_id))

    result = await run_deploy({STATE_KEY: state}, str(run_id))
    assert result["status"] == "succeeded"
    assert result["revision"] == 1

    async with state.session_factory() as session:
        deployment_id = UUID(result["deployment_id"])
        deployment = await session.get(Deployment, deployment_id)
        assert deployment is not None
        assert deployment.status is DeploymentStatus.succeeded
        assert deployment.application_id == app_id
        assert deployment.build_run_id == run_id
        assert deployment.image_digest is not None


async def test_run_deploy_records_failure(state: WorkerState) -> None:
    state.deploy_executor = MockDeployExecutor(outcome=RolloutOutcome.failed)  # type: ignore[assignment]
    _, _, run_id = await _seed(state, auto_deploy=True)
    await run_build({STATE_KEY: state, "redis": _FakeArqPool()}, str(run_id))

    result = await run_deploy({STATE_KEY: state}, str(run_id))
    assert result["status"] == "failed"

    async with state.session_factory() as session:
        deployment = await session.get(Deployment, UUID(result["deployment_id"]))
        assert deployment is not None
        assert deployment.status is DeploymentStatus.failed


async def test_run_deploy_skips_if_build_incomplete(state: WorkerState) -> None:
    _, _, run_id = await _seed(state, auto_deploy=True)
    # No build run, so image_tag/digest are still NULL on the row.
    result = await run_deploy({STATE_KEY: state}, str(run_id))
    assert result["status"] == "skipped"
    assert "incomplete" in result["reason"]


async def test_revisions_increment_per_application(state: WorkerState) -> None:
    _, app_id, run_id = await _seed(state, auto_deploy=True)
    await run_build({STATE_KEY: state, "redis": _FakeArqPool()}, str(run_id))
    first = await run_deploy({STATE_KEY: state}, str(run_id))
    second = await run_deploy({STATE_KEY: state}, str(run_id))
    assert first["revision"] == 1
    assert second["revision"] == 2

    async with state.session_factory() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Deployment.revision).where(Deployment.application_id == app_id)
        )
        revisions = sorted(result.scalars())
        assert revisions == [1, 2]


# Silence unused-import warnings for re-exports we use in fixture seeding.
_UNUSED_IMPORTS = (Application, BuildRun, Cluster)
