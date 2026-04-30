"""LocalDockerExecutor — wraps `docker buildx build` for local dev.

Streams stdout+stderr to the supplied LogSink and reads the resulting
manifest digest from `--metadata-file`.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import ClassVar

import anyio

from liftwork_core.build.protocols import BuildContext, BuildResult, LogSink

_DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}")


class LocalDockerError(RuntimeError):
    pass


class LocalDockerExecutor:
    name: ClassVar[str] = "local-docker"

    def __init__(self, *, docker_bin: str = "docker") -> None:
        if shutil.which(docker_bin) is None:
            msg = f"docker binary not found on PATH (looked for {docker_bin!r})"
            raise LocalDockerError(msg)
        self._docker = docker_bin

    async def build(self, ctx: BuildContext, *, log_sink: LogSink) -> BuildResult:
        with NamedTemporaryFile(suffix=".meta.json", delete=False) as meta_fp:
            metadata_path = Path(meta_fp.name)
        try:
            cmd: list[str] = [
                self._docker,
                "buildx",
                "build",
                "--progress=plain",
                "--metadata-file",
                str(metadata_path),
                "-t",
                ctx.image_ref,
                "-f",
                str(ctx.dockerfile_path),
            ]
            if ctx.target:
                cmd.extend(["--target", ctx.target])
            for k, v in ctx.build_args.items():
                cmd.extend(["--build-arg", f"{k}={v}"])
            for cache_ref in ctx.cache_from:
                cmd.extend(["--cache-from", f"type=registry,ref={cache_ref}"])
            if ctx.cache_to:
                cmd.extend(["--cache-to", ctx.cache_to])
            for k, v in ctx.labels.items():
                cmd.extend(["--label", f"{k}={v}"])
            cmd.append("--push" if ctx.push else "--load")
            cmd.append(str(ctx.workspace_path))

            await log_sink.write(f"$ {' '.join(cmd)}")
            start = time.perf_counter()

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            assert proc.stdout is not None
            async for raw in proc.stdout:
                await log_sink.write(raw.decode("utf-8", errors="replace").rstrip())
            rc = await proc.wait()
            duration = time.perf_counter() - start

            if rc != 0:
                msg = f"docker buildx exited rc={rc}"
                raise LocalDockerError(msg)

            digest = _read_digest(metadata_path)
            return BuildResult(
                image_ref=ctx.image_ref,
                image_digest=digest,
                duration_seconds=round(duration, 3),
            )
        finally:
            await anyio.Path(metadata_path).unlink(missing_ok=True)


def _read_digest(metadata_path: Path) -> str:
    try:
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"could not read buildx metadata file: {exc}"
        raise LocalDockerError(msg) from exc

    digest = meta.get("containerimage.digest")
    if isinstance(digest, str) and _DIGEST_RE.fullmatch(digest):
        return digest

    # Fallback: grep any sha256 from the metadata blob.
    for value in _walk(meta):
        if isinstance(value, str):
            match = _DIGEST_RE.search(value)
            if match:
                return match.group(0)

    msg = "could not extract sha256 digest from buildx metadata"
    raise LocalDockerError(msg)


def _walk(obj: object):  # type: ignore[no-untyped-def]
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)
    else:
        yield obj
