"""SSE log-stream integration test.

Subscribes via the API while a separate Redis client publishes to the
build's pub/sub channel; verifies the stream forwards lines and ends
on the END marker.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
import redis.asyncio as redis_asyncio


@pytest.fixture
async def application(app: Any, cluster: Any) -> Any:
    from liftwork_core.repositories import ApplicationRepository

    factory = app.state.liftwork.session_factory
    async with factory() as session:
        application = await ApplicationRepository(session).create(
            slug="logs-app",
            display_name="Logs App",
            repo_url="https://example.com/x/y.git",
            repo_owner="x",
            repo_name="y",
            default_branch="main",
            cluster_id=cluster.id,
            namespace="default",
            image_repository="x/y",
        )
        await session.commit()
        await session.refresh(application)
        return application


async def test_sse_forwards_published_lines(
    client: Any,
    app: Any,
    application: Any,  # noqa: ARG001
    member_user: Any,
    headers_for: Any,
) -> None:
    build_id = uuid4()
    channel = f"liftwork:build:{build_id}"

    publisher: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        str(app.state.liftwork.settings.redis.url),
        decode_responses=True,
    )

    async def publish_after_subscribe() -> None:
        # Wait until the API has subscribed (a real subscriber exists).
        for _ in range(50):
            count = await publisher.execute_command("PUBSUB", "NUMSUB", channel)
            # PUBSUB NUMSUB returns [channel, count]
            if isinstance(count, list) and len(count) >= 2 and int(count[1]) > 0:
                break
            await asyncio.sleep(0.05)
        await publisher.publish(channel, "first line")
        await publisher.publish(channel, "second line")
        await publisher.publish(channel, "__LIFTWORK_END__")

    publish_task = asyncio.create_task(publish_after_subscribe())

    received: list[str] = []
    try:
        async with client.stream(
            "GET",
            f"/builds/{build_id}/logs",
            headers=headers_for(member_user),
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/event-stream")
            async for chunk in response.aiter_lines():
                received.append(chunk)
                if "complete" in chunk:
                    break
    finally:
        await publish_task
        await publisher.aclose()

    joined = "\n".join(received)
    assert "data: first line" in joined
    assert "data: second line" in joined
    assert "event: end" in joined
    assert "data: complete" in joined


async def test_sse_requires_auth(client: Any) -> None:
    resp = await client.get(f"/builds/{uuid4()}/logs")
    assert resp.status_code == 401
