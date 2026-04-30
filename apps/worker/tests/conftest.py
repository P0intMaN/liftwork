"""Test-time env defaults for liftwork-worker tests."""

from __future__ import annotations

import os

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
