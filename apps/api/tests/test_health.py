"""Tests for liveness, readiness, identity, and metrics endpoints.

Readiness requires Postgres + Redis from `make dev-up`. Tests skip when
the dependencies are unreachable so unit-only runs stay green.
"""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


def _service_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


pg_up = _service_reachable("127.0.0.1", 5432)
redis_up = _service_reachable("127.0.0.1", 6379)
deps_up = pg_up and redis_up


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    from liftwork_api.main import app

    with TestClient(app) as c:
        yield c


def test_root_identity(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "liftwork-api"
    assert body["version"]


def test_healthz_is_unconditional(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.skipif(not deps_up, reason="postgres+redis not reachable on localhost")
def test_readyz_when_deps_up(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"


def test_metrics_exposition(client: TestClient) -> None:
    # Hit a known endpoint first so a labelled sample exists.
    client.get("/healthz")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "liftwork_http_requests_total" in r.text
    assert "liftwork_http_request_duration_seconds" in r.text


def test_request_id_echoed(client: TestClient) -> None:
    r = client.get("/healthz", headers={"x-request-id": "abc-123"})
    assert r.status_code == 200
    assert r.headers.get("x-request-id") == "abc-123"
