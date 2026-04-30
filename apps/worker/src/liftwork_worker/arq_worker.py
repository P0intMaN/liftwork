"""arq WorkerSettings — entrypoint for `python -m arq liftwork_worker.arq_worker.WorkerSettings`."""

from __future__ import annotations

from typing import Any, ClassVar

import redis.asyncio as redis_asyncio
import structlog
from arq.connections import RedisSettings

from liftwork_api import __version__
from liftwork_core.build.protocols import BuildExecutor
from liftwork_core.config import Settings, get_settings
from liftwork_core.db import make_engine, make_session_factory
from liftwork_core.deploy.protocols import DeployExecutor
from liftwork_core.logging import configure_logging
from liftwork_core.telemetry import configure_telemetry
from liftwork_worker.deploy.k8s_executor import K8sDeployExecutor
from liftwork_worker.executors.buildkit_pod import K8sBuildKitExecutor
from liftwork_worker.jobs import run_build, run_deploy
from liftwork_worker.k8s import load_kube_clients
from liftwork_worker.mock_executors import MockBuildExecutor, MockDeployExecutor
from liftwork_worker.state import STATE_KEY, WorkerState


def _redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings.from_dsn(str(s.redis.url))


def _make_executors(
    settings: Settings,
    log: structlog.stdlib.BoundLogger,
) -> tuple[BuildExecutor, DeployExecutor]:
    if settings.worker.executor == "mock":
        log.info("executors_selected", build="mock", deploy="mock")
        return MockBuildExecutor(), MockDeployExecutor()

    # "kind" — load real kubeconfig and wire the real executors
    clients = load_kube_clients(settings.k8s)
    build_executor = K8sBuildKitExecutor(
        clients=clients,
        namespace=settings.worker.builder_namespace,
        service_account=settings.worker.builder_service_account,
    )
    deploy_executor = K8sDeployExecutor(
        clients=clients,
        field_manager=settings.worker.deploy_field_manager,
    )
    log.info(
        "executors_selected",
        build=build_executor.name,
        deploy=deploy_executor.name,
        kube_context=settings.k8s.kube_context,
        in_cluster=settings.k8s.in_cluster,
    )
    return build_executor, deploy_executor


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.use_json_logs)
    configure_telemetry(
        settings.telemetry,
        service_name="liftwork-worker",
        service_version=__version__,
    )
    log = structlog.get_logger("liftwork.worker.lifespan")

    engine = make_engine(settings.database)
    session_factory = make_session_factory(engine)
    redis_client: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        str(settings.redis.url),
        encoding="utf-8",
        decode_responses=True,
    )

    build_exec, deploy_exec = _make_executors(settings, log)

    ctx[STATE_KEY] = WorkerState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis_client,
        build_executor=build_exec,
        deploy_executor=deploy_exec,
    )
    log.info("worker_started", env=settings.env, executor=settings.worker.executor)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    state = ctx.get(STATE_KEY)
    if state is None:
        return
    await state.redis.aclose()
    await state.engine.dispose()
    structlog.get_logger("liftwork.worker.lifespan").info("worker_stopped")


class WorkerSettings:
    """arq picks these class attributes up by reflection."""

    functions: ClassVar[list[Any]] = [run_build, run_deploy]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings: RedisSettings = _redis_settings()
    max_jobs = 10
    job_timeout = 1800  # 30 min hard cap per job
    keep_result = 3600  # 1 hour
