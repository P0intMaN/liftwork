"""Tests for `infer_deploy_defaults` — language/EXPOSE-based heuristics."""

from __future__ import annotations

from pathlib import Path

import pytest

from liftwork_core.build.defaults import DeployDefaults, infer_deploy_defaults


@pytest.mark.parametrize(
    ("filename", "contents", "expected_port", "expected_source_substr"),
    [
        ("package.json", '{"name":"x"}', 3000, "node"),
        ("requirements.txt", "fastapi\n", 8000, "python"),
        ("pyproject.toml", "[project]\nname='x'\n", 8000, "python"),
        ("go.mod", "module example.com/x\n", 8080, "go"),
        ("Cargo.toml", "[package]\nname='x'\nversion='0.1.0'\n", 8080, "rust"),
        ("Gemfile", "source 'https://rubygems.org'\n", 3000, "ruby"),
        ("composer.json", '{"name":"a/b"}', 8080, "php"),
        ("pom.xml", "<project></project>", 8080, "java"),
    ],
)
def test_per_language_default_port(
    tmp_path: Path,
    filename: str,
    contents: str,
    expected_port: int,
    expected_source_substr: str,
) -> None:
    (tmp_path / filename).write_text(contents, encoding="utf-8")
    result = infer_deploy_defaults(tmp_path)
    assert result.port == expected_port
    assert expected_source_substr in result.source


def test_dockerfile_expose_overrides_language(tmp_path: Path) -> None:
    # Even with package.json present, Dockerfile EXPOSE wins.
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM node:20\nEXPOSE 4000\n", encoding="utf-8")
    result = infer_deploy_defaults(tmp_path)
    assert result.port == 4000
    assert "EXPOSE" in result.source


@pytest.mark.parametrize(
    ("expose_line", "expected"),
    [
        ("EXPOSE 8080\n", 8080),
        ("EXPOSE 8080/tcp\n", 8080),
        ("EXPOSE 8080 9090\n", 8080),  # first port wins
        ("expose 7777\n", 7777),  # case-insensitive
        ("# EXPOSE 1234\nEXPOSE 5555\n", 5555),  # skips commented
    ],
)
def test_expose_parser_variants(tmp_path: Path, expose_line: str, expected: int) -> None:
    (tmp_path / "Dockerfile").write_text(f"FROM scratch\n{expose_line}", encoding="utf-8")
    assert infer_deploy_defaults(tmp_path).port == expected


def test_no_signals_falls_back_to_8080(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# nothing\n", encoding="utf-8")
    result = infer_deploy_defaults(tmp_path)
    assert result.port == 8080
    assert result.source == "fallback"


def test_health_path_is_always_root(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name":"x"}', encoding="utf-8")
    assert infer_deploy_defaults(tmp_path).health_check_path == "/"


def test_containerfile_recognized_as_dockerfile(tmp_path: Path) -> None:
    (tmp_path / "Containerfile").write_text("FROM scratch\nEXPOSE 6543\n", encoding="utf-8")
    assert infer_deploy_defaults(tmp_path).port == 6543


def test_round_trip_via_dict() -> None:
    original = DeployDefaults(port=3000, health_check_path="/", source="node convention")
    restored = DeployDefaults.from_dict(original.to_dict())
    assert restored == original
