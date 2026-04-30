"""Liveness, readiness, and identity endpoints."""

from __future__ import annotations

from typing import Annotated

import redis.asyncio as redis_asyncio
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api import __version__
from liftwork_api.dependencies import get_db, get_redis

router = APIRouter(tags=["meta"])

DBSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[redis_asyncio.Redis, Depends(get_redis)]


@router.get("/", summary="Service identity")
async def root() -> dict[str, str]:
    return {"service": "liftwork-api", "version": __version__}


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict[str, str]:
    """Process-level liveness. Cheap and unconditional — never touches deps."""
    return {"status": "ok"}


@router.get("/readyz", summary="Readiness probe")
async def readyz(
    response: Response,
    session: DBSession,
    redis: RedisClient,
) -> dict[str, object]:
    """Readiness — verifies DB and Redis are reachable."""
    checks: dict[str, str] = {}
    healthy = True

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001 — we want to record any failure
        checks["database"] = f"error: {exc.__class__.__name__}"
        healthy = False

    try:
        pong = await redis.ping()
        checks["redis"] = "ok" if pong else "error: no pong"
        if not pong:
            healthy = False
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}"
        healthy = False

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {"status": "ready" if healthy else "degraded", "checks": checks}
