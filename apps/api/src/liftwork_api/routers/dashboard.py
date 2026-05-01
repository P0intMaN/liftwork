"""Aggregate metrics + activity feed that powers the dashboard."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.auth import CurrentUser
from liftwork_api.dependencies import get_db
from liftwork_api.schemas import (
    ActivityItem,
    BuildsSummary,
    DeploysSummary,
    MetricsSummary,
    TimeseriesPoint,
)
from liftwork_core.db.models import Application, BuildRun, Cluster, Deployment
from liftwork_core.repositories import AnalyticsRepository

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=MetricsSummary)
async def summary(
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    since_days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> MetricsSummary:
    repo = AnalyticsRepository(session)
    builds = await repo.builds_summary(since_days=since_days)
    deploys = await repo.deploys_summary(since_days=since_days)
    apps = await repo.application_count()
    cluster_count = (await session.execute(select(func.count(Cluster.id)))).scalar() or 0

    return MetricsSummary(
        builds=BuildsSummary(**builds),
        deploys=DeploysSummary(**deploys),
        applications=apps,
        clusters=int(cluster_count),
    )


@router.get("/builds/timeseries", response_model=list[TimeseriesPoint])
async def builds_timeseries(
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> list[TimeseriesPoint]:
    rows = await AnalyticsRepository(session).builds_per_day(days=days)
    return [TimeseriesPoint(**r) for r in rows]


@router.get("/deploys/timeseries", response_model=list[TimeseriesPoint])
async def deploys_timeseries(
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    days: Annotated[int, Query(ge=1, le=90)] = 30,
) -> list[TimeseriesPoint]:
    rows = await AnalyticsRepository(session).deploys_per_day(days=days)
    return [TimeseriesPoint(**r) for r in rows]


@router.get("/activity", response_model=list[ActivityItem])
async def activity_feed(
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ActivityItem]:
    """Unified feed of recent build + deploy events, newest-first."""
    builds = (
        await session.execute(
            select(BuildRun, Application.slug)
            .join(Application, Application.id == BuildRun.application_id)
            .order_by(BuildRun.created_at.desc())
            .limit(limit)
        )
    ).all()
    deploys = (
        await session.execute(
            select(Deployment, Application.slug)
            .join(Application, Application.id == Deployment.application_id)
            .order_by(Deployment.created_at.desc())
            .limit(limit)
        )
    ).all()

    items: list[ActivityItem] = []
    for build, slug in builds:
        items.append(
            ActivityItem(
                kind="build",
                id=build.id,
                application_id=build.application_id,
                application_slug=slug,
                status=build.status.value,
                detail=(build.commit_message or build.commit_sha[:12]),
                created_at=build.created_at,
            )
        )
    for deployment, slug in deploys:
        items.append(
            ActivityItem(
                kind="deploy",
                id=deployment.id,
                application_id=deployment.application_id,
                application_slug=slug,
                status=deployment.status.value,
                detail=f"rev {deployment.revision} · {deployment.image_tag}",
                created_at=deployment.created_at,
            )
        )
    items.sort(key=lambda x: x.created_at, reverse=True)
    return items[:limit]
