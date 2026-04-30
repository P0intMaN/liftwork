"""Reusable FastAPI dependencies."""

from __future__ import annotations

from collections.abc import AsyncIterator

import redis.asyncio as redis_asyncio
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.lifespan import AppState, get_app_state
from liftwork_core.config import Settings


def app_state(request: Request) -> AppState:
    return get_app_state(request.app)


def get_settings_dep(request: Request) -> Settings:
    return get_app_state(request.app).settings


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = get_app_state(request.app).session_factory
    async with factory() as session:
        yield session


def get_redis(request: Request) -> redis_asyncio.Redis:
    return get_app_state(request.app).redis
