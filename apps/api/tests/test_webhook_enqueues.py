"""Verifies the webhook actually enqueues to arq in addition to inserting the DB row.

Uses arq's queue helpers — we don't run a worker; we just check the
queue length grew by 1 after the call.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest

WEBHOOK_SECRET = "test-webhook-secret"


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
            "head_commit": {"id": sha, "message": "feat: enqueue test"},
            "installation": {"id": 1234},
        }
    ).encode()


@pytest.fixture
async def application(app: Any, cluster: Any) -> Any:
    from liftwork_core.repositories import ApplicationRepository

    factory = app.state.liftwork.session_factory
    async with factory() as session:
        application = await ApplicationRepository(session).create(
            slug="enq-app",
            display_name="Enq App",
            repo_url="https://github.com/acme/enq.git",
            repo_owner="acme",
            repo_name="enq",
            default_branch="main",
            cluster_id=cluster.id,
            namespace="acme",
            image_repository="acme/enq",
            auto_deploy=True,
        )
        await session.commit()
        await session.refresh(application)
        return application


async def _arq_queue_size(app: Any) -> int:
    pool = app.state.liftwork.arq_pool
    # arq stores pending jobs in a Redis sorted set named `arq:queue`.
    return int(await pool.zcard("arq:queue"))


async def test_webhook_enqueues_run_build(
    client: Any,
    app: Any,
    application: Any,  # noqa: ARG001
) -> None:
    before = await _arq_queue_size(app)
    body = _push_body("acme", "enq", "main", "5" * 40)
    resp = await client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": _sign(body),
            "X-GitHub-Delivery": "enq-1",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["action"] == "build_enqueued"
    after = await _arq_queue_size(app)
    assert after == before + 1


async def test_manual_trigger_enqueues_run_build(
    client: Any,
    app: Any,
    application: Any,
    member_user: Any,
    headers_for: Any,
) -> None:
    before = await _arq_queue_size(app)
    resp = await client.post(
        f"/applications/{application.id}/builds",
        headers=headers_for(member_user),
    )
    assert resp.status_code == 202, resp.text
    assert resp.json()["status"] == "queued"
    after = await _arq_queue_size(app)
    assert after == before + 1
