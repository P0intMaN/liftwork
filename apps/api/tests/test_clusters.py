from __future__ import annotations

from typing import Any


async def test_list_requires_auth(client: Any) -> None:
    resp = await client.get("/clusters")
    assert resp.status_code == 401


async def test_create_requires_admin(client: Any, member_user: Any, headers_for: Any) -> None:
    resp = await client.post(
        "/clusters",
        json={"name": "kind-x", "display_name": "kind x"},
        headers=headers_for(member_user),
    )
    assert resp.status_code == 403


async def test_admin_can_create(client: Any, admin_user: Any, headers_for: Any) -> None:
    resp = await client.post(
        "/clusters",
        json={
            "name": "kind-foo",
            "display_name": "kind foo",
            "default_namespace": "team-a",
        },
        headers=headers_for(admin_user),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "kind-foo"
    assert body["default_namespace"] == "team-a"
    assert body["status"] == "unknown"


async def test_create_dedupes_by_name(client: Any, admin_user: Any, headers_for: Any) -> None:
    h = headers_for(admin_user)
    payload = {"name": "kind-dup", "display_name": "dup"}
    first = await client.post("/clusters", json=payload, headers=h)
    second = await client.post("/clusters", json=payload, headers=h)
    assert first.status_code == 201
    assert second.status_code == 409
