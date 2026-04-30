"""Shallow git clone helper.

Used by the LocalDocker executor (workers running on the host) and as
a fallback when the BuildKit Job's git frontend isn't available.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import anyio

from liftwork_core.build.protocols import LogSink


class GitCloneError(RuntimeError):
    pass


async def shallow_clone(
    *,
    repo_url: str,
    branch: str,
    target_dir: Path,
    log_sink: LogSink,
    depth: int = 1,
    timeout_seconds: int = 120,
) -> None:
    """Clone `repo_url@branch` into `target_dir` (which must not yet exist)."""
    target = anyio.Path(target_dir)
    if await target.exists():
        async for _ in target.iterdir():
            msg = f"target_dir already exists and is not empty: {target_dir}"
            raise GitCloneError(msg)
    await anyio.Path(target_dir.parent).mkdir(parents=True, exist_ok=True)

    cmd = [
        "git",
        "clone",
        "--depth",
        str(depth),
        "--branch",
        branch,
        "--single-branch",
        repo_url,
        str(target_dir),
    ]
    await log_sink.write(f"$ {' '.join(cmd)}")

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    try:
        async with asyncio.timeout(timeout_seconds):
            assert proc.stdout is not None  # for type-checker
            async for raw in proc.stdout:
                await log_sink.write(raw.decode("utf-8", errors="replace").rstrip())
            rc = await proc.wait()
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        msg = f"git clone timed out after {timeout_seconds}s"
        raise GitCloneError(msg) from exc

    if rc != 0:
        msg = f"git clone exited with rc={rc}"
        raise GitCloneError(msg)
