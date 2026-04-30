"""Build executor / log sink protocols.

The orchestrator (Phase 4) wires concrete executor implementations
(LocalDocker for dev, BuildKit-in-pod for prod) behind these protocols
so build logic stays portable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field, SecretStr


class RegistryAuth(BaseModel):
    server: str
    username: str
    password: SecretStr


class BuildContext(BaseModel):
    workspace_path: Path
    image_ref: str
    dockerfile_path: Path
    build_args: dict[str, str] = Field(default_factory=dict)
    target: str | None = None
    cache_from: list[str] = Field(default_factory=list)
    cache_to: str | None = None
    push: bool = True
    registry_auth: RegistryAuth | None = None
    labels: dict[str, str] = Field(default_factory=dict)


class BuildResult(BaseModel):
    image_ref: str
    image_digest: str  # sha256:abcd…
    duration_seconds: float
    log_excerpt: str = ""


@runtime_checkable
class LogSink(Protocol):
    """Async log consumer. Executors call `write` for each line of output."""

    async def write(self, line: str) -> None: ...

    async def close(self) -> None: ...


@runtime_checkable
class BuildExecutor(Protocol):
    """Builds and (optionally) pushes a container image."""

    name: str

    async def build(self, ctx: BuildContext, *, log_sink: LogSink) -> BuildResult: ...
