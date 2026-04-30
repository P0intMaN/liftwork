"""Per-worker process state shared across jobs.

`WorkerState` is built once in `on_startup` and stored on arq's `ctx`
dict under the key `"liftwork"`. Job handlers retrieve it via
`get_state(ctx)` so they never reach into ctx directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from liftwork_core.build.protocols import BuildExecutor
from liftwork_core.config import Settings
from liftwork_core.db import SessionFactory
from liftwork_core.deploy.protocols import DeployExecutor

STATE_KEY = "liftwork"


@dataclass
class WorkerState:
    settings: Settings
    engine: AsyncEngine
    session_factory: SessionFactory
    redis: redis_asyncio.Redis
    build_executor: BuildExecutor
    deploy_executor: DeployExecutor


def get_state(ctx: dict[str, Any]) -> WorkerState:
    state = ctx.get(STATE_KEY)
    if state is None:
        msg = "WorkerState missing from arq context — on_startup did not run"
        raise RuntimeError(msg)
    return state  # type: ignore[no-any-return]
