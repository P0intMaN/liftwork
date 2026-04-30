"""Live tests against a real Redis (pub/sub).

Skipped when redis isn't reachable on localhost.
"""

from __future__ import annotations

import asyncio
import os
import socket

import pytest
import redis.asyncio as redis_asyncio

from liftwork_worker.redis_log import (
    END_MARKER,
    RedisPubSubLogSink,
    channel_for_build,
    channel_for_deploy,
)


def _redis_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=0.5):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_up(),
    reason="redis not reachable on localhost:6379",
)

_REDIS_URL = os.environ.get(
    "LIFTWORK_REDIS__URL",
    "redis://localhost:6379/0",
)


def test_channel_naming_is_stable() -> None:
    assert channel_for_build("11111111-1111-1111-1111-111111111111") == (
        "liftwork:build:11111111-1111-1111-1111-111111111111"
    )
    assert channel_for_deploy("dep-1") == "liftwork:deploy:dep-1"


async def test_publish_and_subscribe_round_trip() -> None:
    channel = "liftwork:test:" + os.urandom(4).hex()

    publisher: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=True
    )
    subscriber: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=True
    )
    pubsub = subscriber.pubsub()
    try:
        await pubsub.subscribe(channel)
        sink = RedisPubSubLogSink(publisher, channel)

        async def reader() -> list[str]:
            received: list[str] = []
            async for msg in pubsub.listen():
                if msg["type"] != "message":
                    continue
                received.append(msg["data"])
                if msg["data"] == END_MARKER:
                    return received
            return received

        reader_task = asyncio.create_task(reader())
        # Wait until the subscription is actually registered server-side
        # (PUBSUB NUMSUB returns ['<channel>', <count>]).
        for _ in range(50):
            res = await publisher.execute_command("PUBSUB", "NUMSUB", channel)
            if isinstance(res, list) and len(res) >= 2 and int(res[1]) > 0:
                break
            await asyncio.sleep(0.05)

        await sink.write("line one")
        await sink.write("line two")
        await sink.write("line three")
        await sink.close()

        received = await asyncio.wait_for(reader_task, timeout=5.0)
        assert received == ["line one", "line two", "line three", END_MARKER]
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()  # type: ignore[no-untyped-call]
        await publisher.aclose()
        await subscriber.aclose()


async def test_close_is_idempotent() -> None:
    channel = "liftwork:test:" + os.urandom(4).hex()
    redis: redis_asyncio.Redis = redis_asyncio.from_url(  # type: ignore[no-untyped-call]
        _REDIS_URL, decode_responses=True
    )
    try:
        sink = RedisPubSubLogSink(redis, channel)
        await sink.close()
        await sink.close()  # must not raise
        # writes after close are silently dropped
        await sink.write("ignored")
    finally:
        await redis.aclose()
