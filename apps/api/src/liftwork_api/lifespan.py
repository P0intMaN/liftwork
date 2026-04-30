"""FastAPI lifespan: telemetry init, DB engine, Redis client, graceful shutdown."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import redis.asyncio as redis_asyncio
from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from liftwork_api import __version__
from liftwork_core.config import BootstrapSettings, Settings, get_settings
from liftwork_core.db import SessionFactory, make_engine, make_session_factory
from liftwork_core.logging import configure_logging, get_logger
from liftwork_core.repositories import UserRepository
from liftwork_core.security import hash_password
from liftwork_core.telemetry import configure_telemetry


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    session_factory: SessionFactory
    redis: redis_asyncio.Redis
    arq_pool: ArqRedis


def get_app_state(app: FastAPI) -> AppState:
    state = getattr(app.state, "liftwork", None)
    if state is None:  # pragma: no cover - defensive
        raise RuntimeError("Application state not initialised; lifespan did not run.")
    return state  # type: ignore[no-any-return]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.use_json_logs)
    configure_telemetry(
        settings.telemetry,
        service_name="liftwork-api",
        service_version=__version__,
    )
    log = get_logger("liftwork.api.lifespan")

    engine = make_engine(settings.database)
    session_factory = make_session_factory(engine)
    redis_client: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        str(settings.redis.url),
        encoding="utf-8",
        decode_responses=True,
    )
    arq_pool = await create_pool(RedisSettings.from_dsn(str(settings.redis.url)))

    app.state.liftwork = AppState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis_client,
        arq_pool=arq_pool,
    )

    await _bootstrap_admin(session_factory, settings.bootstrap, log)

    log.info("api_started", env=settings.env, version=__version__)
    try:
        yield
    finally:
        await arq_pool.aclose()
        await redis_client.aclose()
        await engine.dispose()
        log.info("api_stopped")


async def _bootstrap_admin(
    session_factory: SessionFactory,
    bootstrap: BootstrapSettings,
    log: object,
) -> None:
    """Seed an initial admin user the first time liftwork boots.

    No-op unless both `bootstrap.admin_email` and `bootstrap.admin_password`
    are set, AND the users table is empty.
    """
    if bootstrap.admin_email is None or bootstrap.admin_password is None:
        return
    async with session_factory() as session:
        repo = UserRepository(session)
        if await repo.count() > 0:
            return
        await repo.create(
            email=bootstrap.admin_email,
            password_hash=hash_password(bootstrap.admin_password.get_secret_value()),
            role="admin",
        )
        await session.commit()
    log.info("admin_bootstrapped", email=bootstrap.admin_email)  # type: ignore[attr-defined]
