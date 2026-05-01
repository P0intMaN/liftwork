"""Read-only deployment endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.auth import CurrentUser
from liftwork_api.dependencies import get_db
from liftwork_api.schemas import DeploymentOut
from liftwork_core.repositories import (
    ApplicationRepository,
    DeploymentRepository,
)

router = APIRouter(
    prefix="/applications/{application_id}/deployments",
    tags=["deployments"],
)


@router.get("", response_model=list[DeploymentOut])
async def list_deployments(
    application_id: UUID,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[DeploymentOut]:
    if await ApplicationRepository(session).get_by_id(application_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="application not found")
    runs = await DeploymentRepository(session).list_for_application(application_id)
    return [DeploymentOut.model_validate(r) for r in runs]


detail_router = APIRouter(prefix="/deployments", tags=["deployments"])


@detail_router.get("/{deployment_id}", response_model=DeploymentOut)
async def get_deployment(
    deployment_id: UUID,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DeploymentOut:
    dep = await DeploymentRepository(session).get_by_id(deployment_id)
    if dep is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="deployment not found")
    return DeploymentOut.model_validate(dep)
