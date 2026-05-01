"""Shared test fixtures for liftwork-api.

Sets predictable env vars *before* `liftwork_core.config` is imported
elsewhere, so `Settings()` resolves cleanly during collection. Provides
DB cleanup, app/client wiring, and auth token helpers for the route
tests.

We use `httpx.AsyncClient` over `ASGITransport`, plus `asgi_lifespan`'s
`LifespanManager`, instead of FastAPI's sync `TestClient`. This keeps
**all** test machinery (lifespan, requests, DB fixtures) inside the
single pytest-asyncio event loop — the sync TestClient runs lifespan in
its own anyio portal loop and the SQLAlchemy async engine then refuses
to clean up connections across loops.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest

# Set env vars before any import that triggers Settings() construction.
os.environ.setdefault("LIFTWORK_ENV", "dev")
os.environ.setdefault("LIFTWORK_LOG_LEVEL", "WARNING")
os.environ.setdefault(
    "LIFTWORK_DATABASE__URL",
    "postgresql+asyncpg://liftwork:liftwork@localhost:5432/liftwork_test",
)
os.environ.setdefault("LIFTWORK_REDIS__URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "LIFTWORK_JWT__SECRET",
    "test-secret-not-for-production-32-bytes-min-please",
)
os.environ.setdefault("LIFTWORK_TELEMETRY__OTEL_ENABLED", "false")
os.environ.setdefault("LIFTWORK_GITHUB__WEBHOOK_SECRET", "test-webhook-secret")


def _service_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


_PG_UP = _service_reachable("127.0.0.1", 5432)
_REDIS_UP = _service_reachable("127.0.0.1", 6379)
_DEPS_UP = _PG_UP and _REDIS_UP


@pytest.fixture(scope="session", autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    from liftwork_core.config import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()


# ---------------------------------------------------------------------------
# App + client. The lifespan is driven via asgi-lifespan and an httpx
# AsyncClient so every test stays inside pytest-asyncio's single loop.
# Fixtures are function-scoped because we TRUNCATE the DB between tests.
# ---------------------------------------------------------------------------


@pytest.fixture
async def app() -> AsyncIterator[Any]:
    if not _DEPS_UP:
        pytest.skip("postgres+redis not reachable; skipping API integration tests")
    from asgi_lifespan import LifespanManager

    from liftwork_api.main import create_app

    application = create_app()
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app: Any) -> AsyncIterator[Any]:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        # Scrub the DB at the *start* of each test so leftover state from a
        # previous run doesn't leak in.
        await _truncate(app)
        yield c


_TRUNCATE_SQL = (
    "TRUNCATE TABLE applications, clusters, build_runs, deployments, "
    "secrets, audit_logs, users RESTART IDENTITY CASCADE"
)


async def _truncate(app: Any) -> None:
    from sqlalchemy import text

    factory = app.state.liftwork.session_factory
    async with factory() as session:
        await session.execute(text(_TRUNCATE_SQL))
        await session.commit()


# ---------------------------------------------------------------------------
# User + auth helpers
# ---------------------------------------------------------------------------


async def _create_user(app: Any, *, email: str, password: str, role: str) -> Any:
    from liftwork_core.repositories import UserRepository
    from liftwork_core.security import hash_password

    factory = app.state.liftwork.session_factory
    async with factory() as session:
        user = await UserRepository(session).create(
            email=email,
            password_hash=hash_password(password),
            role=role,
        )
        await session.commit()
        await session.refresh(user)
        return user


@pytest.fixture
async def admin_user(app: Any, client: Any) -> Any:  # noqa: ARG001 — depend on client to ensure truncate
    return await _create_user(
        app, email="admin@example.com", password="admin-password", role="admin"
    )


@pytest.fixture
async def member_user(app: Any, client: Any) -> Any:  # noqa: ARG001
    return await _create_user(
        app, email="member@example.com", password="member-password", role="member"
    )


@pytest.fixture
def headers_for(app: Any) -> Callable[[Any], dict[str, str]]:
    from liftwork_core.security import issue_jwt

    def _headers(user: Any) -> dict[str, str]:
        token = issue_jwt(
            subject=str(user.id),
            settings=app.state.liftwork.settings.jwt,
            claims={"role": user.role.value},
        )
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
async def cluster(app: Any, client: Any) -> Any:  # noqa: ARG001
    from liftwork_core.repositories import ClusterRepository

    factory = app.state.liftwork.session_factory
    async with factory() as session:
        c = await ClusterRepository(session).create(
            name="kind-kubedeploy-dev",
            display_name="Local kind cluster",
            in_cluster=False,
            default_namespace="default",
        )
        await session.commit()
        await session.refresh(c)
        return c
