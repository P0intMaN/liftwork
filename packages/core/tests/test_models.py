"""Smoke checks on ORM metadata: every entity registers a sane table."""

from __future__ import annotations

from liftwork_core.db import Base
from liftwork_core.db import models as m


def test_all_tables_registered() -> None:
    expected = {
        "users",
        "secrets",
        "clusters",
        "applications",
        "build_runs",
        "deployments",
        "audit_logs",
    }
    actual = set(Base.metadata.tables.keys())
    assert expected.issubset(actual), actual ^ expected


def test_application_has_unique_repo_constraint() -> None:
    table = Base.metadata.tables["applications"]
    constraint_names = {c.name for c in table.constraints}
    assert "uq_applications_repo_owner_name_branch" in constraint_names


def test_build_run_status_enum_complete() -> None:
    assert {s.value for s in m.BuildStatus} == {
        "queued",
        "running",
        "building",
        "pushing",
        "succeeded",
        "failed",
        "cancelled",
    }


def test_deployment_status_enum_complete() -> None:
    assert {s.value for s in m.DeploymentStatus} == {
        "pending",
        "applying",
        "rolling_out",
        "succeeded",
        "failed",
        "rolled_back",
    }
