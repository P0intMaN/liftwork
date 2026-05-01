"""Repo-root conftest: provision the test database before any test runs.

Tests target a *separate* `liftwork_test` Postgres database so they can
TRUNCATE freely without ever touching the dev DB (and your bootstrap
admin). On first session use we:

  1. Connect to the `postgres` admin DB
  2. CREATE DATABASE liftwork_test if missing
  3. Run alembic migrations against it via `alembic upgrade head`

Subsequent runs skip steps 1–3 (migrations are idempotent anyway).
Skipped silently when Postgres isn't reachable.
"""
# ruff: noqa: S603, S607, S608, PLW1510
# Subprocess args + DB name are hard-coded at module scope here, not user-controlled.

from __future__ import annotations

import os
import socket
import subprocess
from pathlib import Path

# IMPORTANT: must run BEFORE any sub-conftest imports liftwork_core.config.
TEST_DB = "liftwork_test"
ADMIN_DSN = "postgresql://liftwork:liftwork@localhost:5432/postgres"
TEST_URL = f"postgresql+asyncpg://liftwork:liftwork@localhost:5432/{TEST_DB}"

# Tell child conftests where to point.
os.environ.setdefault("LIFTWORK_DATABASE__URL", TEST_URL)


def _pg_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 5432), timeout=0.5):
            return True
    except OSError:
        return False


def _ensure_test_db() -> None:
    if not _pg_up():
        return
    # We use the docker compose `liftwork-postgres` container to issue the
    # CREATE DATABASE — avoids needing libpq on the host.
    check = subprocess.run(
        [
            "docker",
            "exec",
            "liftwork-postgres",
            "psql",
            "-U",
            "liftwork",
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname='{TEST_DB}'",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if check.returncode == 0 and check.stdout.strip() == "1":
        return  # already exists
    subprocess.run(
        [
            "docker",
            "exec",
            "liftwork-postgres",
            "psql",
            "-U",
            "liftwork",
            "-d",
            "postgres",
            "-c",
            f"CREATE DATABASE {TEST_DB}",
        ],
        check=False,
        timeout=10,
    )


def _run_migrations() -> None:
    if not _pg_up():
        return
    repo_root = Path(__file__).resolve().parent
    env = os.environ.copy()
    env["LIFTWORK_DATABASE__URL"] = TEST_URL
    # Hard-set required Settings fields so alembic env.py imports cleanly.
    env.setdefault("LIFTWORK_REDIS__URL", "redis://localhost:6379/0")
    env.setdefault(
        "LIFTWORK_JWT__SECRET",
        "test-secret-not-for-production-32-bytes-min-please",
    )
    env.setdefault("LIFTWORK_TELEMETRY__OTEL_ENABLED", "false")
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"],
        cwd=str(repo_root),
        env=env,
        check=False,
        capture_output=True,
        timeout=120,
    )


_ensure_test_db()
_run_migrations()
