"""Read-only build endpoints. Triggering happens via webhook or POST below."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.auth import CurrentUser
from liftwork_api.dependencies import get_db
from liftwork_api.schemas import BuildEnqueuedResponse, BuildRunOut
from liftwork_core.db.models import BuildSource
from liftwork_core.repositories import ApplicationRepository, BuildRunRepository

router = APIRouter(prefix="/applications/{application_id}/builds", tags=["builds"])


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
) -> BuildEnqueuedResponse:
    """Manual trigger — re-build current HEAD of the configured default branch."""
    app = await ApplicationRepository(session).get_by_id(application_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="application not found")

    repo = BuildRunRepository(session)
    # For a manual trigger we record a placeholder commit_sha; the worker will
    # resolve HEAD via the GitHub App token once that path lands in Phase 4b.
    run = await repo.create(
        application_id=app.id,
        commit_sha="HEAD",
        branch=app.default_branch,
        source=BuildSource.manual,
    )
    await session.commit()
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
