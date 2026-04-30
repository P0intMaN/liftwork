"""Redis pub/sub log sink.

Writes each log line as a separate message to `liftwork:build:{build_id}`.
The API's SSE endpoint subscribes to this channel and forwards lines to
the dashboard in real time.

Pub/sub is fire-and-forget — there's no replay if no one is subscribed.
For permanent archival we also persist the full transcript to the
`build_runs.error` / `log_object_key` fields once the build terminates.
"""

from __future__ import annotations

from typing import ClassVar
from uuid import UUID

import redis.asyncio as redis_asyncio


def channel_for_build(build_id: UUID | str) -> str:
    return f"liftwork:build:{build_id}"


def channel_for_deploy(deploy_id: UUID | str) -> str:
    return f"liftwork:deploy:{deploy_id}"


END_MARKER = "__LIFTWORK_END__"


class RedisPubSubLogSink:
    name: ClassVar[str] = "redis-pubsub"

    def __init__(self, redis: redis_asyncio.Redis, channel: str) -> None:
        self._redis = redis
        self._channel = channel
        self._closed = False

    async def write(self, line: str) -> None:
        if self._closed:
            return
        await self._redis.publish(self._channel, line)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._redis.publish(self._channel, END_MARKER)
