"""CRUD for `Cluster` records (read + create; full edits are v2)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.auth import AdminUser, CurrentUser
from liftwork_api.dependencies import get_db
from liftwork_api.schemas import ClusterCreate, ClusterOut
from liftwork_core.repositories import ClusterRepository

router = APIRouter(prefix="/clusters", tags=["clusters"])


@router.get("", response_model=list[ClusterOut])
async def list_clusters(
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ClusterOut]:
    clusters = await ClusterRepository(session).list_all()
    return [ClusterOut.model_validate(c) for c in clusters]


@router.post(
    "",
    response_model=ClusterOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_cluster(
    body: ClusterCreate,
    _admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ClusterOut:
    repo = ClusterRepository(session)
    if await repo.get_by_name(body.name) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"cluster name already in use: {body.name}",
        )
    cluster = await repo.create(**body.model_dump())
    await session.commit()
    await session.refresh(cluster)
    return ClusterOut.model_validate(cluster)
