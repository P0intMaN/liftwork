"""High-level build orchestration.

Wires the language detector, the Dockerfile renderer, the registry
helpers, and a chosen `BuildExecutor` into one async function. The
caller (Phase 4 arq job handler) only needs to provide repo metadata
and an executor.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from liftwork_core.build import (
    BuildContext,
    BuildExecutor,
    BuildResult,
    Language,
    LiftworkConfig,
    LogSink,
    detect_language,
    load_liftwork_config,
    render_dockerfile,
)
from liftwork_core.build.config import LiftworkConfigError
from liftwork_core.build.language import DetectionResult
from liftwork_core.build.renderer import DEFAULT_TEMPLATES, DockerfileTemplateError
from liftwork_core.registry import image_ref, tag_for_commit
from liftwork_core.registry.protocols import ImageRef


class OrchestrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BuildRequest:
    workspace: Path  # checked-out repo on disk
    repo_owner: str
    repo_name: str
    branch: str
    commit_sha: str
    image_repository: str  # e.g. "p0intman/my-app"
    registry_host: str = "ghcr.io"
    push: bool = True


@dataclass(frozen=True)
class OrchestrationResult:
    detection: DetectionResult
    config: LiftworkConfig
    image: ImageRef
    build: BuildResult
    duration_seconds: float


_GENERATED_DOCKERFILE_NAME = "Dockerfile.liftwork"


async def orchestrate_build(
    request: BuildRequest,
    *,
    executor: BuildExecutor,
    log_sink: LogSink,
) -> OrchestrationResult:
    started = time.perf_counter()

    if not request.workspace.exists():
        msg = f"workspace does not exist: {request.workspace}"
        raise OrchestrationError(msg)

    try:
        config = load_liftwork_config(request.workspace / "liftwork.yaml") or LiftworkConfig()
    except LiftworkConfigError as exc:
        raise OrchestrationError(str(exc)) from exc

    detection = detect_language(request.workspace)
    chosen_language: Language = config.language or detection.language
    await log_sink.write(
        f"detected language={detection.language.value} "
        f"(signals={','.join(detection.signals) or '-'}); "
        f"using language={chosen_language.value}"
    )

    dockerfile_path = _resolve_dockerfile(
        workspace=request.workspace,
        config=config,
        chosen_language=chosen_language,
        log_sink=log_sink,
        detection=detection,
    )
    await log_sink.write(f"dockerfile={dockerfile_path}")

    image = ImageRef(
        registry=request.registry_host,
        repository=request.image_repository,
        tag=tag_for_commit(branch=request.branch, sha=request.commit_sha),
    )
    full_ref = image_ref(
        registry_host=image.registry,
        repository=image.repository,
        tag=image.tag,
    )
    await log_sink.write(f"image_ref={full_ref}")

    build_ctx = BuildContext(
        workspace_path=request.workspace,
        image_ref=full_ref,
        dockerfile_path=dockerfile_path,
        build_args=config.build.args,
        target=config.build.target,
        cache_from=config.build.cache_from,
        push=request.push,
        labels={
            "liftwork.io/repo": f"{request.repo_owner}/{request.repo_name}",
            "liftwork.io/branch": request.branch,
            "liftwork.io/commit": request.commit_sha,
        },
    )

    result = await executor.build(build_ctx, log_sink=log_sink)
    image_with_digest = image.model_copy(update={"digest": result.image_digest})

    return OrchestrationResult(
        detection=detection,
        config=config,
        image=image_with_digest,
        build=result,
        duration_seconds=round(time.perf_counter() - started, 3),
    )


async def await_log(log_sink: LogSink, line: str) -> None:
    """Trivial helper to keep type-checkers happy at call sites."""
    await log_sink.write(line)


def _resolve_dockerfile(
    *,
    workspace: Path,
    config: LiftworkConfig,
    chosen_language: Language,
    log_sink: LogSink,  # noqa: ARG001 — reserved for future logging hooks
    detection: DetectionResult,
) -> Path:
    """Return the path to the Dockerfile to feed BuildKit."""
    # 1. explicit override in liftwork.yaml
    if config.build.dockerfile:
        candidate = (workspace / config.build.dockerfile).resolve()
        if not candidate.is_file():
            msg = f"build.dockerfile does not exist: {candidate}"
            raise OrchestrationError(msg)
        return candidate

    # 2. user-committed Dockerfile at repo root
    for name in ("Dockerfile", "Containerfile"):
        candidate = workspace / name
        if candidate.is_file():
            return candidate

    # 3. otherwise generate one from the language template
    if chosen_language not in DEFAULT_TEMPLATES:
        msg = (
            f"no committed Dockerfile and no template available for language="
            f"{chosen_language.value}. Add a Dockerfile or set `language:` in liftwork.yaml."
        )
        raise OrchestrationError(msg)

    output_path = workspace / _GENERATED_DOCKERFILE_NAME
    try:
        render_dockerfile(
            chosen_language,
            context={
                "package_manager": detection.package_manager.value,
                "port": config.deploy.port,
                "command": config.deploy.command,
            },
            output_path=output_path,
        )
    except DockerfileTemplateError as exc:
        raise OrchestrationError(str(exc)) from exc
    return output_path
