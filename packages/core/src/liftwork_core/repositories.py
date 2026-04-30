"""Thin async repositories over SQLAlchemy 2.0.

Repositories are the only layer that touches the ORM directly. API
routers and worker job handlers depend on these — never on the session.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_core.db.models import (
    Application,
    BuildRun,
    BuildSource,
    BuildStatus,
    Cluster,
    User,
    UserRole,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def count(self) -> int:
        result = await self.session.execute(select(User.id))
        return len(result.all())

    async def create(self, *, email: str, password_hash: str, role: str = "member") -> User:
        user = User(
            email=email.lower(),
            password_hash=password_hash,
            role=UserRole(role),
            is_active=True,
        )
        self.session.add(user)
        await self.session.flush()
        return user


class ClusterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self) -> list[Cluster]:
        result = await self.session.execute(select(Cluster).order_by(Cluster.name))
        return list(result.scalars())

    async def get_by_id(self, cluster_id: UUID) -> Cluster | None:
        return await self.session.get(Cluster, cluster_id)

    async def get_by_name(self, name: str) -> Cluster | None:
        result = await self.session.execute(select(Cluster).where(Cluster.name == name))
        return result.scalar_one_or_none()

    async def create(self, **fields: Any) -> Cluster:
        cluster = Cluster(**fields)
        self.session.add(cluster)
        await self.session.flush()
        return cluster


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_all(self, *, limit: int = 100) -> list[Application]:
        result = await self.session.execute(
            select(Application).order_by(Application.slug).limit(limit)
        )
        return list(result.scalars())

    async def get_by_id(self, app_id: UUID) -> Application | None:
        return await self.session.get(Application, app_id)

    async def get_by_slug(self, slug: str) -> Application | None:
        result = await self.session.execute(select(Application).where(Application.slug == slug))
        return result.scalar_one_or_none()

    async def find_for_push(
        self,
        *,
        owner: str,
        name: str,
        branch: str,
    ) -> Application | None:
        """Match a push event back to a registered application."""
        result = await self.session.execute(
            select(Application).where(
                Application.repo_owner == owner.lower(),
                Application.repo_name == name.lower(),
                Application.default_branch == branch,
            )
        )
        return result.scalar_one_or_none()

    async def create(self, **fields: Any) -> Application:
        if "repo_owner" in fields:
            fields["repo_owner"] = fields["repo_owner"].lower()
        if "repo_name" in fields:
            fields["repo_name"] = fields["repo_name"].lower()
        app = Application(**fields)
        self.session.add(app)
        await self.session.flush()
        return app

    async def delete(self, app: Application) -> None:
        await self.session.delete(app)
        await self.session.flush()


class BuildRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, build_id: UUID) -> BuildRun | None:
        return await self.session.get(BuildRun, build_id)

    async def list_for_application(
        self,
        application_id: UUID,
        *,
        limit: int = 50,
    ) -> list[BuildRun]:
        result = await self.session.execute(
            select(BuildRun)
            .where(BuildRun.application_id == application_id)
            .order_by(BuildRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def find_existing(
        self,
        *,
        application_id: UUID,
        commit_sha: str,
        branch: str,
    ) -> BuildRun | None:
        """Used to dedupe webhook redeliveries."""
        result = await self.session.execute(
            select(BuildRun).where(
                BuildRun.application_id == application_id,
                BuildRun.commit_sha == commit_sha,
                BuildRun.branch == branch,
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        application_id: UUID,
        commit_sha: str,
        branch: str,
        source: BuildSource,
        commit_message: str | None = None,
    ) -> BuildRun:
        run = BuildRun(
            application_id=application_id,
            commit_sha=commit_sha,
            branch=branch,
            source=source,
            commit_message=commit_message,
            status=BuildStatus.queued,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def update_status(
        self,
        run: BuildRun,
        *,
        status: BuildStatus,
        error: str | None = None,
        image_tag: str | None = None,
        image_digest: str | None = None,
    ) -> BuildRun:
        run.status = status
        if error is not None:
            run.error = error
        if image_tag is not None:
            run.image_tag = image_tag
        if image_digest is not None:
            run.image_digest = image_digest
        if status is BuildStatus.running and run.started_at is None:
            run.started_at = _utcnow()
        if status in (BuildStatus.succeeded, BuildStatus.failed, BuildStatus.cancelled):
            run.finished_at = _utcnow()
        await self.session.flush()
        return run
