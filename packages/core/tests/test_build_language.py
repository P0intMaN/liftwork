from __future__ import annotations

from pathlib import Path

import pytest

from liftwork_core.build.language import Language, PackageManager, detect_language


def _touch(p: Path, name: str, content: str = "") -> None:
    (p / name).write_text(content, encoding="utf-8")


def test_dockerfile_wins_over_everything(tmp_path: Path) -> None:
    _touch(tmp_path, "Dockerfile", "FROM scratch")
    _touch(tmp_path, "package.json", "{}")
    _touch(tmp_path, "go.mod", "module x")
    result = detect_language(tmp_path)
    assert result.language is Language.static
    assert "Dockerfile" in result.signals


def test_python_with_uv(tmp_path: Path) -> None:
    _touch(tmp_path, "pyproject.toml", "")
    _touch(tmp_path, "uv.lock", "")
    result = detect_language(tmp_path)
    assert result.language is Language.python
    assert result.package_manager is PackageManager.uv


def test_python_with_poetry(tmp_path: Path) -> None:
    _touch(tmp_path, "pyproject.toml", "")
    _touch(tmp_path, "poetry.lock", "")
    result = detect_language(tmp_path)
    assert result.language is Language.python
    assert result.package_manager is PackageManager.poetry


def test_python_requirements_only(tmp_path: Path) -> None:
    _touch(tmp_path, "requirements.txt", "")
    result = detect_language(tmp_path)
    assert result.language is Language.python
    assert result.package_manager is PackageManager.pip


def test_node_with_pnpm(tmp_path: Path) -> None:
    _touch(tmp_path, "package.json", "{}")
    _touch(tmp_path, "pnpm-lock.yaml", "")
    result = detect_language(tmp_path)
    assert result.language is Language.node
    assert result.package_manager is PackageManager.pnpm


def test_node_with_yarn(tmp_path: Path) -> None:
    _touch(tmp_path, "package.json", "{}")
    _touch(tmp_path, "yarn.lock", "")
    result = detect_language(tmp_path)
    assert result.language is Language.node
    assert result.package_manager is PackageManager.yarn


def test_node_default_npm(tmp_path: Path) -> None:
    _touch(tmp_path, "package.json", "{}")
    result = detect_language(tmp_path)
    assert result.language is Language.node
    assert result.package_manager is PackageManager.npm


def test_go(tmp_path: Path) -> None:
    _touch(tmp_path, "go.mod", "module x")
    assert detect_language(tmp_path).language is Language.go


def test_rust(tmp_path: Path) -> None:
    _touch(tmp_path, "Cargo.toml", "")
    assert detect_language(tmp_path).language is Language.rust


def test_java_gradle_kotlin(tmp_path: Path) -> None:
    _touch(tmp_path, "build.gradle.kts", "")
    assert detect_language(tmp_path).language is Language.java


def test_dotnet(tmp_path: Path) -> None:
    _touch(tmp_path, "MyApp.csproj", "")
    assert detect_language(tmp_path).language is Language.dotnet


def test_unknown(tmp_path: Path) -> None:
    _touch(tmp_path, "README.md", "")
    assert detect_language(tmp_path).language is Language.unknown


def test_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="repo_root"):
        detect_language(tmp_path / "does-not-exist")
