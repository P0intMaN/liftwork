from fastapi.testclient import TestClient

from liftwork_api.main import app

client = TestClient(app)


def test_healthz() -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz() -> None:
    r = client.get("/readyz")
    assert r.status_code == 200


def test_root_identity() -> None:
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "liftwork-api"
    assert "version" in body
