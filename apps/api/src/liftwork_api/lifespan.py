"""FastAPI lifespan: telemetry init, DB engine, Redis client, graceful shutdown."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import redis.asyncio as redis_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from liftwork_api import __version__
from liftwork_core.config import Settings, get_settings
from liftwork_core.db import SessionFactory, make_engine, make_session_factory
from liftwork_core.logging import configure_logging, get_logger
from liftwork_core.telemetry import configure_telemetry


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    session_factory: SessionFactory
    redis: redis_asyncio.Redis


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

    app.state.liftwork = AppState(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        redis=redis_client,
    )

    log.info("api_started", env=settings.env, version=__version__)
    try:
        yield
    finally:
        await redis_client.aclose()
        await engine.dispose()
        log.info("api_stopped")
