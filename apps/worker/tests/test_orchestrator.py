from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

import pytest

from liftwork_core.build.protocols import BuildContext, BuildResult, LogSink
from liftwork_worker.log_sinks import InMemoryLogSink
from liftwork_worker.orchestrator import (
    BuildRequest,
    OrchestrationError,
    orchestrate_build,
)


@dataclass
class _MockExecutor:
    name: ClassVar[str] = "mock"
    digest: str = "sha256:" + "a" * 64
    captured: list[BuildContext] = field(default_factory=list)

    async def build(self, ctx: BuildContext, *, log_sink: LogSink) -> BuildResult:
        self.captured.append(ctx)
        await log_sink.write("mock build start")
        await log_sink.write("mock build done")
        return BuildResult(
            image_ref=ctx.image_ref,
            image_digest=self.digest,
            duration_seconds=0.01,
        )


def _make_python_repo(root: Path, *, files: Iterable[tuple[str, str]] = ()) -> None:
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    for name, content in files:
        (root / name).write_text(content, encoding="utf-8")


async def test_orchestrate_python_repo_renders_dockerfile(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _make_python_repo(workspace, files=[("uv.lock", "")])

    sink = InMemoryLogSink()
    executor = _MockExecutor()

    result = await orchestrate_build(
        BuildRequest(
            workspace=workspace,
            repo_owner="acme",
            repo_name="api",
            branch="main",
            commit_sha="0123456789abcdef" * 2 + "01234567",
            image_repository="acme/api",
            registry_host="ghcr.io",
        ),
        executor=executor,
        log_sink=sink,
    )

    assert result.image.registry == "ghcr.io"
    assert result.image.repository == "acme/api"
    assert result.image.tag.startswith("main-")
    assert result.image.digest == executor.digest
    assert result.detection.language.value == "python"

    # Dockerfile.liftwork should have been rendered into the workspace.
    rendered = workspace / "Dockerfile.liftwork"
    assert rendered.exists()
    body = rendered.read_text(encoding="utf-8")
    assert "FROM python:" in body
    assert "uv export" in body  # uv branch picked because uv.lock is present

    # Executor saw a single BuildContext.
    assert len(executor.captured) == 1
    ctx = executor.captured[0]
    assert ctx.dockerfile_path == rendered
    assert ctx.image_ref == "ghcr.io/acme/api:" + result.image.tag
    assert ctx.labels["liftwork.io/repo"] == "acme/api"

    # Sink received language detection log line and executor lines.
    assert any("detected language=python" in line for line in sink.lines)
    assert "mock build done" in sink.lines


async def test_orchestrate_uses_committed_dockerfile(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

    sink = InMemoryLogSink()
    executor = _MockExecutor()
    result = await orchestrate_build(
        BuildRequest(
            workspace=workspace,
            repo_owner="acme",
            repo_name="api",
            branch="main",
            commit_sha="abcdef0" + "0" * 33,
            image_repository="acme/api",
        ),
        executor=executor,
        log_sink=sink,
    )
    assert executor.captured[0].dockerfile_path == workspace / "Dockerfile"
    assert not (workspace / "Dockerfile.liftwork").exists()
    assert result.detection.language.value == "static"


async def test_orchestrate_unknown_language_without_dockerfile_errors(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "README.md").write_text("hi", encoding="utf-8")

    with pytest.raises(OrchestrationError, match="no committed Dockerfile"):
        await orchestrate_build(
            BuildRequest(
                workspace=workspace,
                repo_owner="acme",
                repo_name="api",
                branch="main",
                commit_sha="abcdef0" + "0" * 33,
                image_repository="acme/api",
            ),
            executor=_MockExecutor(),
            log_sink=InMemoryLogSink(),
        )


async def test_orchestrate_respects_liftwork_yaml_overrides(tmp_path: Path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _make_python_repo(workspace)
    (workspace / "Dockerfile.dev").write_text("FROM scratch", encoding="utf-8")
    (workspace / "liftwork.yaml").write_text(
        'version: "1"\nbuild:\n  dockerfile: ./Dockerfile.dev\n  args: { FOO: bar }\n',
        encoding="utf-8",
    )

    executor = _MockExecutor()
    await orchestrate_build(
        BuildRequest(
            workspace=workspace,
            repo_owner="acme",
            repo_name="api",
            branch="main",
            commit_sha="abcdef0" + "0" * 33,
            image_repository="acme/api",
        ),
        executor=executor,
        log_sink=InMemoryLogSink(),
    )
    ctx = executor.captured[0]
    assert ctx.dockerfile_path == (workspace / "Dockerfile.dev").resolve()
    assert ctx.build_args == {"FOO": "bar"}
