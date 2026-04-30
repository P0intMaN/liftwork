"""Build endpoints — list, trigger, get, follow logs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

import redis.asyncio as redis_asyncio
from arq.connections import ArqRedis
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.auth import CurrentUser
from liftwork_api.dependencies import get_arq_pool, get_db, get_redis
from liftwork_api.schemas import BuildEnqueuedResponse, BuildRunOut
from liftwork_core.db.models import BuildSource
from liftwork_core.repositories import ApplicationRepository, BuildRunRepository

router = APIRouter(prefix="/applications/{application_id}/builds", tags=["builds"])

_BUILD_CHANNEL_PREFIX = "liftwork:build:"
_END_MARKER = "__LIFTWORK_END__"
_HEARTBEAT_TIMEOUT = 15.0


@router.get("", response_model=list[BuildRunOut])
async def list_builds(
    application_id: UUID,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[BuildRunOut]:
    if await ApplicationRepository(session).get_by_id(application_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="application not found")
    runs = await BuildRunRepository(session).list_for_application(application_id)
    return [BuildRunOut.model_validate(r) for r in runs]


@router.post(
    "",
    response_model=BuildEnqueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_build(
    application_id: UUID,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    arq_pool: Annotated[ArqRedis, Depends(get_arq_pool)],
) -> BuildEnqueuedResponse:
    """Manual trigger — re-build current HEAD of the configured default branch."""
    app = await ApplicationRepository(session).get_by_id(application_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="application not found")

    repo = BuildRunRepository(session)
    # For a manual trigger we record a placeholder commit_sha; the worker will
    # resolve HEAD via the GitHub App token in Phase 4b-2.
    run = await repo.create(
        application_id=app.id,
        commit_sha="HEAD",
        branch=app.default_branch,
        source=BuildSource.manual,
    )
    await session.commit()

    await arq_pool.enqueue_job("run_build", build_run_id=str(run.id))
    return BuildEnqueuedResponse(build_id=run.id, status=run.status.value)


detail_router = APIRouter(prefix="/builds", tags=["builds"])


@detail_router.get("/{build_id}", response_model=BuildRunOut)
async def get_build(
    build_id: UUID,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BuildRunOut:
    run = await BuildRunRepository(session).get_by_id(build_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="build not found")
    return BuildRunOut.model_validate(run)


@detail_router.get(
    "/{build_id}/logs",
    summary="Server-Sent Events stream of live build logs",
)
async def stream_build_logs(
    build_id: UUID,
    request: Request,
    _user: CurrentUser,
    redis: Annotated[redis_asyncio.Redis, Depends(get_redis)],
) -> StreamingResponse:
    channel = f"{_BUILD_CHANNEL_PREFIX}{build_id}"

    async def event_stream() -> AsyncIterator[bytes]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            yield f": subscribed {channel}\n\n".encode()
            while True:
                if await request.is_disconnected():
                    return
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=_HEARTBEAT_TIMEOUT,
                )
                if message is None:
                    yield b": keepalive\n\n"
                    continue
                payload = message.get("data")
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8", errors="replace")
                if payload == _END_MARKER:
                    yield b"event: end\ndata: complete\n\n"
                    return
                # Escape newlines per the SSE spec — multi-line frames need
                # one `data:` line each. Worker emits one log line per call.
                for line in str(payload).splitlines() or [""]:
                    yield f"data: {line}\n".encode()
                yield b"\n"
        except asyncio.CancelledError:
            raise
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()  # type: ignore[no-untyped-call]

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
