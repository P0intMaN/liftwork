"""LogSink implementations.

InMemoryLogSink — collects everything for tests / DB persistence.
NullLogSink     — drops everything; used when caller already forwards logs.
TeeLogSink      — fan-out to multiple sinks.
"""

from __future__ import annotations

from collections.abc import Sequence


class InMemoryLogSink:
    name = "in-memory"

    def __init__(self, *, max_lines: int = 50_000) -> None:
        self._lines: list[str] = []
        self._max_lines = max_lines

    @property
    def lines(self) -> list[str]:
        return list(self._lines)

    @property
    def text(self) -> str:
        return "\n".join(self._lines)

    def excerpt(self, last_n: int = 200) -> str:
        return "\n".join(self._lines[-last_n:])

    async def write(self, line: str) -> None:
        if len(self._lines) >= self._max_lines:
            self._lines.pop(0)
        self._lines.append(line.rstrip("\n"))

    async def close(self) -> None:
        return None


class NullLogSink:
    name = "null"

    async def write(self, line: str) -> None:  # noqa: ARG002 — sink-shaped no-op
        return None

    async def close(self) -> None:
        return None


class TeeLogSink:
    name = "tee"

    def __init__(self, sinks: Sequence[object]) -> None:
        self._sinks = list(sinks)

    async def write(self, line: str) -> None:
        for sink in self._sinks:
            await sink.write(line)  # type: ignore[attr-defined]

    async def close(self) -> None:
        for sink in self._sinks:
            await sink.close()  # type: ignore[attr-defined]
