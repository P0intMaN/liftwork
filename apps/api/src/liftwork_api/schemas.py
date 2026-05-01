"""Pydantic request/response schemas for the API surface."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr

# ----- Auth ------------------------------------------------------------------


class LoginRequest(BaseModel):
    email: EmailStr
    password: SecretStr


class TokenResponse(BaseModel):
    access_token: str
    # OAuth2 token_type literal, not a credential — silence bandit hardcoded-pw heuristic
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class CurrentUser(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: str
    is_active: bool


# ----- Cluster ---------------------------------------------------------------


class ClusterCreate(BaseModel):
    name: Annotated[str, Field(min_length=2, max_length=128)]
    display_name: Annotated[str, Field(min_length=1, max_length=255)]
    in_cluster: bool = False
    default_namespace: str = "default"


class ClusterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str
    in_cluster: bool
    default_namespace: str
    status: str
    created_at: datetime
    updated_at: datetime


# ----- Application -----------------------------------------------------------


class ApplicationCreate(BaseModel):
    slug: Annotated[str, Field(min_length=2, max_length=128, pattern=r"^[a-z0-9-]+$")]
    display_name: Annotated[str, Field(min_length=1, max_length=255)]
    repo_url: Annotated[str, Field(min_length=8, max_length=512)]
    repo_owner: Annotated[str, Field(min_length=1, max_length=128)]
    repo_name: Annotated[str, Field(min_length=1, max_length=128)]
    default_branch: str = "main"
    cluster_id: UUID
    namespace: Annotated[str, Field(min_length=1, max_length=63)]
    image_repository: Annotated[str, Field(min_length=1, max_length=512)]
    auto_deploy: bool = True


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    display_name: str
    repo_url: str
    repo_owner: str
    repo_name: str
    default_branch: str
    cluster_id: UUID
    namespace: str
    image_repository: str
    auto_deploy: bool
    created_at: datetime
    updated_at: datetime


# ----- Build / Deployment ----------------------------------------------------


class BuildRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    commit_sha: str
    commit_message: str | None
    branch: str
    source: str
    status: str
    image_tag: str | None
    image_digest: str | None
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class BuildEnqueuedResponse(BaseModel):
    build_id: UUID
    status: str
    deduplicated: bool = False


class DeploymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_id: UUID
    build_run_id: UUID | None
    cluster_id: UUID
    namespace: str
    image_tag: str
    image_digest: str | None
    status: str
    revision: int
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


# ----- Dashboard analytics ---------------------------------------------------


class CountTriple(BaseModel):
    total: int
    succeeded: int
    failed: int


class BuildsSummary(CountTriple):
    in_flight: int
    avg_duration_seconds: float
    since_days: int


class DeploysSummary(CountTriple):
    since_days: int


class TimeseriesPoint(BaseModel):
    day: str
    total: int
    succeeded: int
    failed: int


class MetricsSummary(BaseModel):
    builds: BuildsSummary
    deploys: DeploysSummary
    applications: int
    clusters: int


class ActivityItem(BaseModel):
    """Unified row across BuildRun + Deployment for a single timeline."""

    kind: str               # "build" | "deploy"
    id: UUID
    application_id: UUID
    application_slug: str | None
    status: str
    detail: str | None      # commit message / image tag / etc.
    created_at: datetime


# ----- Webhooks --------------------------------------------------------------


class WebhookAck(BaseModel):
    received: bool = True
    event: str
    delivery_id: str | None = None
    action: str = "ignored"
    build_id: UUID | None = None
    detail: str | None = None
