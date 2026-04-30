"""Shared test fixtures for liftwork-api.

Sets predictable env vars *before* `liftwork_core.config` is imported
elsewhere, so `Settings()` resolves cleanly during collection.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Set env vars before any import that triggers Settings() construction.
os.environ.setdefault("LIFTWORK_ENV", "dev")
os.environ.setdefault("LIFTWORK_LOG_LEVEL", "WARNING")
os.environ.setdefault(
    "LIFTWORK_DATABASE__URL",
    "postgresql+asyncpg://liftwork:liftwork@localhost:5432/liftwork",
)
os.environ.setdefault("LIFTWORK_REDIS__URL", "redis://localhost:6379/0")
os.environ.setdefault(
    "LIFTWORK_JWT__SECRET",
    "test-secret-not-for-production-32-bytes-min-please",
)
os.environ.setdefault("LIFTWORK_TELEMETRY__OTEL_ENABLED", "false")


@pytest.fixture(scope="session", autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    from liftwork_core.config import reset_settings_cache

    reset_settings_cache()
    yield
    reset_settings_cache()
