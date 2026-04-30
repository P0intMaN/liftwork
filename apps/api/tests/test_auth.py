from __future__ import annotations

from typing import Any


async def test_login_happy_path(client: Any, admin_user: Any) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "admin-password"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20


async def test_login_rejects_wrong_password(client: Any, admin_user: Any) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": admin_user.email, "password": "wrong"},
    )
    assert resp.status_code == 401


async def test_login_rejects_unknown_user(client: Any) -> None:
    resp = await client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "x"},
    )
    assert resp.status_code == 401


async def test_me_requires_bearer(client: Any) -> None:
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(client: Any, member_user: Any, headers_for: Any) -> None:
    resp = await client.get("/auth/me", headers=headers_for(member_user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == member_user.email
    assert body["role"] == "member"
    assert body["is_active"] is True


async def test_invalid_token_rejected(client: Any) -> None:
    resp = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
