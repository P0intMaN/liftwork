"""ORM entities (v1).

Schema overview:
    users         — local accounts (v1 single-tenant; OIDC in v2)
    secrets       — at-rest encrypted blobs (kubeconfigs, registry tokens, webhook secrets)
    clusters      — registered target k8s clusters
    applications  — connected repos and their build/deploy config
    build_runs    — every build attempt
    deployments   — every rollout attempt
    audit_logs    — immutable audit trail
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from liftwork_core.db.base import Base, IdMixin, TimestampMixin


class UserRole(enum.StrEnum):
    admin = "admin"
    member = "member"


class ClusterStatus(enum.StrEnum):
    unknown = "unknown"
    healthy = "healthy"
    unreachable = "unreachable"


class SecretScope(enum.StrEnum):
    cluster = "cluster"
    application = "application"
    registry = "registry"
    global_ = "global"


class BuildStatus(enum.StrEnum):
    queued = "queued"
    running = "running"
    building = "building"
    pushing = "pushing"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class BuildSource(enum.StrEnum):
    webhook = "webhook"
    manual = "manual"
    api = "api"
    retry = "retry"


class DeploymentStatus(enum.StrEnum):
    pending = "pending"
    applying = "applying"
    rolling_out = "rolling_out"
    succeeded = "succeeded"
    failed = "failed"
    rolled_back = "rolled_back"


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"),
        default=UserRole.member,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Secret(IdMixin, TimestampMixin, Base):
    __tablename__ = "secrets"
    __table_args__ = (
        UniqueConstraint("scope", "scope_id", "name", name="uq_secrets_scope_id_name"),
    )

    scope: Mapped[SecretScope] = mapped_column(
        Enum(SecretScope, name="secret_scope"),
        nullable=False,
    )
    scope_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class Cluster(IdMixin, TimestampMixin, Base):
    __tablename__ = "clusters"

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    in_cluster: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    kubeconfig_secret_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("secrets.id", ondelete="SET NULL"),
        nullable=True,
    )
    default_namespace: Mapped[str] = mapped_column(String(63), default="default", nullable=False)
    status: Mapped[ClusterStatus] = mapped_column(
        Enum(ClusterStatus, name="cluster_status"),
        default=ClusterStatus.unknown,
        nullable=False,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Application(IdMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint(
            "repo_owner",
            "repo_name",
            "default_branch",
            name="uq_applications_repo_owner_name_branch",
        ),
    )

    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(512), nullable=False)
    repo_owner: Mapped[str] = mapped_column(String(128), nullable=False)
    repo_name: Mapped[str] = mapped_column(String(128), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    cluster_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    namespace: Mapped[str] = mapped_column(String(63), nullable=False)
    image_repository: Mapped[str] = mapped_column(String(512), nullable=False)
    webhook_secret_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("secrets.id", ondelete="SET NULL"),
        nullable=True,
    )
    build_config_yaml: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_deploy: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class BuildRun(IdMixin, TimestampMixin, Base):
    __tablename__ = "build_runs"
    __table_args__ = (
        Index("ix_build_runs_application_id_created_at", "application_id", "created_at"),
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[BuildSource] = mapped_column(
        Enum(BuildSource, name="build_source"),
        nullable=False,
    )
    status: Mapped[BuildStatus] = mapped_column(
        Enum(BuildStatus, name="build_status"),
        default=BuildStatus.queued,
        nullable=False,
    )
    image_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    log_object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Deployment(IdMixin, TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index("ix_deployments_application_id_created_at", "application_id", "created_at"),
    )

    application_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    build_run_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("build_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    cluster_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clusters.id", ondelete="RESTRICT"),
        nullable=False,
    )
    namespace: Mapped[str] = mapped_column(String(63), nullable=False)
    image_tag: Mapped[str] = mapped_column(String(255), nullable=False)
    image_digest: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[DeploymentStatus] = mapped_column(
        Enum(DeploymentStatus, name="deployment_status"),
        default=DeploymentStatus.pending,
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(IdMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
