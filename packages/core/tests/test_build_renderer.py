from __future__ import annotations

from pathlib import Path

import pytest

from liftwork_core.build.language import Language
from liftwork_core.build.renderer import (
    DockerfileTemplateError,
    render_dockerfile,
)


def test_python_renders_uv_branch() -> None:
    out = render_dockerfile(
        Language.python,
        context={"package_manager": "uv", "port": 9000, "command": ["uvicorn", "main:app"]},
    )
    assert "FROM python:" in out
    assert "uv export" in out
    assert "EXPOSE 9000" in out
    assert '["uvicorn", "main:app"]' in out
    assert "USER 1000:1000" in out


def test_python_renders_pip_default() -> None:
    out = render_dockerfile(
        Language.python,
        context={"package_manager": "pip", "port": 8080, "command": None},
    )
    assert "pip install --prefix=/install -r requirements.txt" in out
    assert 'CMD ["python", "-m", "app"]' in out


def test_node_renders_pnpm_branch() -> None:
    out = render_dockerfile(
        Language.node,
        context={"package_manager": "pnpm", "port": 4000, "command": None, "build_command": None},
    )
    assert "pnpm install --frozen-lockfile" in out
    assert "EXPOSE 4000" in out


def test_go_renders_distroless_runtime() -> None:
    out = render_dockerfile(
        Language.go,
        context={"port": 8080, "command": None, "build_path": "./cmd/app"},
    )
    assert "gcr.io/distroless/static-debian12:nonroot" in out
    assert "go build" in out
    assert "./cmd/app" in out


def test_renderer_writes_to_disk(tmp_path: Path) -> None:
    out_path = tmp_path / "subdir" / "Dockerfile"
    render_dockerfile(
        Language.go,
        context={"port": 8080, "command": None},
        output_path=out_path,
    )
    assert out_path.exists()
    assert "FROM golang:" in out_path.read_text(encoding="utf-8")


def test_renderer_rejects_unknown_language() -> None:
    with pytest.raises(DockerfileTemplateError):
        render_dockerfile(Language.unknown, context={})


def test_renderer_rejects_missing_template_var() -> None:
    # `command` is required by the python template (Jinja StrictUndefined).
    with pytest.raises(Exception):  # noqa: B017,PT011 — UndefinedError
        render_dockerfile(Language.python, context={"package_manager": "pip"})
