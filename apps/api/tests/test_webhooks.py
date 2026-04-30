from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest

WEBHOOK_SECRET = "test-webhook-secret"  # matches conftest env override


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _push_body(repo_owner: str, repo_name: str, branch: str, sha: str) -> bytes:
    return json.dumps(
        {
            "ref": f"refs/heads/{branch}",
            "after": sha,
            "repository": {
                "name": repo_name,
                "full_name": f"{repo_owner}/{repo_name}",
                "owner": {"login": repo_owner},
                "clone_url": f"https://github.com/{repo_owner}/{repo_name}.git",
            },
            "head_commit": {"id": sha, "message": "wip"},
            "installation": {"id": 1234},
        }
    ).encode()


@pytest.fixture
async def application(app: Any, cluster: Any) -> Any:
    from liftwork_core.repositories import ApplicationRepository

    factory = app.state.liftwork.session_factory
    async with factory() as session:
        application = await ApplicationRepository(session).create(
            slug="acme-api",
            display_name="Acme API",
            repo_url="https://github.com/acme/api.git",
            repo_owner="acme",
            repo_name="api",
            default_branch="main",
            cluster_id=cluster.id,
            namespace="acme",
            image_repository="acme/api",
            auto_deploy=True,
        )
        await session.commit()
        await session.refresh(application)
        return application


async def test_rejects_missing_signature(client: Any) -> None:
    body = _push_body("acme", "api", "main", "a" * 40)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Event": "push"},
    )
    assert resp.status_code == 401


async def test_rejects_bad_signature(client: Any) -> None:
    body = _push_body("acme", "api", "main", "a" * 40)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
            "X-GitHub-Delivery": "delivery-1",
        },
    )
    assert resp.status_code == 401


async def test_ping_event_returns_pong(client: Any) -> None:
    body = b"{}"
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Delivery": "ping-1",
        },
    )
    assert resp.status_code == 200
    body_json = resp.json()
    assert body_json["event"] == "ping"
    assert body_json["action"] == "pong"


async def test_unhandled_event_acked(client: Any) -> None:
    body = b"{}"
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "issues",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["action"] == "ignored"


async def test_push_with_no_matching_app_acked(client: Any) -> None:
    body = _push_body("nobody", "nothing", "main", "a" * 40)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    body_json = resp.json()
    assert body_json["build_id"] is None
    assert "no application matches" in body_json["detail"]


async def test_branch_delete_is_ignored(client: Any) -> None:
    body = _push_body("acme", "api", "main", "0" * 40)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert "branch-deletion" in resp.json()["detail"]


async def test_push_creates_build_run(client: Any, application: Any) -> None:  # noqa: ARG001
    sha = "1" * 40
    body = _push_body("acme", "api", "main", sha)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Delivery": "delivery-good",
        },
    )
    assert resp.status_code == 200, resp.text
    body_json = resp.json()
    assert body_json["action"] == "build_enqueued"
    assert body_json["build_id"] is not None


async def test_push_dedupes_duplicate_delivery(client: Any, application: Any) -> None:  # noqa: ARG001
    sha = "2" * 40
    body = _push_body("acme", "api", "main", sha)
    headers = {
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": _sign(body),
    }
    first = await client.post("/webhooks/github", content=body, headers=headers)
    second = await client.post("/webhooks/github", content=body, headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["action"] == "build_enqueued"
    assert second.json()["action"] == "deduplicated"
    assert first.json()["build_id"] == second.json()["build_id"]


async def test_push_to_unmatched_branch_is_ignored(
    client: Any,
    application: Any,  # noqa: ARG001
) -> None:
    body = _push_body("acme", "api", "feature/x", "3" * 40)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    assert "no application matches" in resp.json()["detail"]


async def test_auto_deploy_disabled_skips_enqueue(client: Any, app: Any, application: Any) -> None:
    factory = app.state.liftwork.session_factory
    from sqlalchemy import update

    from liftwork_core.db.models import Application

    async with factory() as session:
        await session.execute(
            update(Application).where(Application.id == application.id).values(auto_deploy=False)
        )
        await session.commit()

    body = _push_body("acme", "api", "main", "4" * 40)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
        },
    )
    assert resp.status_code == 200
    body_json = resp.json()
    assert body_json["build_id"] is None
    assert "auto_deploy disabled" in body_json["detail"]
