from __future__ import annotations

from typing import Any


def _create_payload(cluster_id: str, **overrides: Any) -> dict[str, Any]:
    body = {
        "slug": "acme-api",
        "display_name": "Acme API",
        "repo_url": "https://github.com/acme/api.git",
        "repo_owner": "acme",
        "repo_name": "api",
        "default_branch": "main",
        "cluster_id": cluster_id,
        "namespace": "acme",
        "image_repository": "acme/api",
        "auto_deploy": True,
    }
    body.update(overrides)
    return body


async def test_list_requires_auth(client: Any) -> None:
    resp = await client.get("/applications")
    assert resp.status_code == 401


async def test_list_empty(client: Any, member_user: Any, headers_for: Any) -> None:
    resp = await client.get("/applications", headers=headers_for(member_user))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_and_get_application(
    client: Any,
    member_user: Any,
    headers_for: Any,
    cluster: Any,
) -> None:
    create = await client.post(
        "/applications",
        json=_create_payload(str(cluster.id)),
        headers=headers_for(member_user),
    )
    assert create.status_code == 201, create.text
    created = create.json()
    assert created["slug"] == "acme-api"
    assert created["repo_owner"] == "acme"

    listed = await client.get("/applications", headers=headers_for(member_user))
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = await client.get(f"/applications/{created['id']}", headers=headers_for(member_user))
    assert fetched.status_code == 200
    assert fetched.json()["slug"] == "acme-api"


async def test_create_rejects_unknown_cluster(
    client: Any, member_user: Any, headers_for: Any
) -> None:
    resp = await client.post(
        "/applications",
        json=_create_payload("00000000-0000-0000-0000-000000000000"),
        headers=headers_for(member_user),
    )
    assert resp.status_code == 400
    assert "cluster" in resp.text.lower()


async def test_create_rejects_duplicate_slug(
    client: Any, member_user: Any, headers_for: Any, cluster: Any
) -> None:
    h = headers_for(member_user)
    first = await client.post("/applications", json=_create_payload(str(cluster.id)), headers=h)
    assert first.status_code == 201

    second = await client.post(
        "/applications",
        json=_create_payload(str(cluster.id), repo_name="api2"),
        headers=h,
    )
    assert second.status_code == 409


async def test_get_404(client: Any, member_user: Any, headers_for: Any) -> None:
    resp = await client.get(
        "/applications/00000000-0000-0000-0000-000000000000",
        headers=headers_for(member_user),
    )
    assert resp.status_code == 404


async def test_delete_application(
    client: Any, member_user: Any, headers_for: Any, cluster: Any
) -> None:
    created = await client.post(
        "/applications",
        json=_create_payload(str(cluster.id)),
        headers=headers_for(member_user),
    )
    app_id = created.json()["id"]
    delete = await client.delete(
        f"/applications/{app_id}",
        headers=headers_for(member_user),
    )
    assert delete.status_code == 204
    fetched = await client.get(f"/applications/{app_id}", headers=headers_for(member_user))
    assert fetched.status_code == 404


async def test_create_validates_slug_pattern(
    client: Any, member_user: Any, headers_for: Any, cluster: Any
) -> None:
    resp = await client.post(
        "/applications",
        json=_create_payload(str(cluster.id), slug="Bad Slug!"),
        headers=headers_for(member_user),
    )
    assert resp.status_code == 422
