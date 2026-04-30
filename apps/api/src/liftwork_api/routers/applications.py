"""CRUD for `Application` records."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.auth import CurrentUser
from liftwork_api.dependencies import get_db
from liftwork_api.schemas import ApplicationCreate, ApplicationOut
from liftwork_core.repositories import ApplicationRepository, ClusterRepository

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("", response_model=list[ApplicationOut])
async def list_applications(
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApplicationOut]:
    apps = await ApplicationRepository(session).list_all()
    return [ApplicationOut.model_validate(a) for a in apps]


@router.post(
    "",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_application(
    body: ApplicationCreate,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationOut:
    if await ClusterRepository(session).get_by_id(body.cluster_id) is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"cluster {body.cluster_id} does not exist",
        )

    repo = ApplicationRepository(session)
    if await repo.get_by_slug(body.slug) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"slug already in use: {body.slug}",
        )

    try:
        created = await repo.create(**body.model_dump())
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="application with this repo+branch already exists",
        ) from exc
    await session.refresh(created)
    return ApplicationOut.model_validate(created)


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(
    application_id: UUID,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ApplicationOut:
    app = await ApplicationRepository(session).get_by_id(application_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="application not found")
    return ApplicationOut.model_validate(app)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: UUID,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    repo = ApplicationRepository(session)
    app = await repo.get_by_id(application_id)
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="application not found")
    await repo.delete(app)
    await session.commit()
