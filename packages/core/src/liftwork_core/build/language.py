"""Language detection from a checked-out repository on disk.

Heuristics are intentionally simple and ordered: the first match wins.
A repo can override detection by committing a `liftwork.yaml` with an
explicit `language:` field, or by committing its own `Dockerfile`.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path


class Language(enum.StrEnum):
    python = "python"
    node = "node"
    go = "go"
    rust = "rust"
    java = "java"
    ruby = "ruby"
    php = "php"
    dotnet = "dotnet"
    static = "static"  # repo ships its own Dockerfile or is a static site
    unknown = "unknown"


class PackageManager(enum.StrEnum):
    # python
    uv = "uv"
    poetry = "poetry"
    pip = "pip"
    # node
    pnpm = "pnpm"
    yarn = "yarn"
    npm = "npm"
    # other
    none = "none"


@dataclass(frozen=True)
class DetectionResult:
    language: Language
    package_manager: PackageManager = PackageManager.none
    signals: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_known(self) -> bool:
        return self.language is not Language.unknown


def _has(root: Path, *names: str) -> tuple[str, ...]:
    return tuple(n for n in names if (root / n).exists())


def _glob(root: Path, pattern: str) -> bool:
    return any(root.glob(pattern))


def _detect_static(p: Path) -> DetectionResult | None:
    sigs = _has(p, "Dockerfile", "Containerfile")
    if sigs:
        return DetectionResult(Language.static, PackageManager.none, sigs)
    return None


def _detect_python(p: Path) -> DetectionResult | None:
    sigs = _has(p, "pyproject.toml", "requirements.txt", "Pipfile", "setup.py")
    if not sigs:
        return None
    pm = PackageManager.pip
    if (p / "uv.lock").exists():
        pm = PackageManager.uv
    elif (p / "poetry.lock").exists():
        pm = PackageManager.poetry
    return DetectionResult(Language.python, pm, sigs)


def _detect_node(p: Path) -> DetectionResult | None:
    if not (p / "package.json").exists():
        return None
    pm = PackageManager.npm
    if (p / "pnpm-lock.yaml").exists():
        pm = PackageManager.pnpm
    elif (p / "yarn.lock").exists():
        pm = PackageManager.yarn
    return DetectionResult(Language.node, pm, ("package.json",))


def _detect_go(p: Path) -> DetectionResult | None:
    if (p / "go.mod").exists():
        return DetectionResult(Language.go, PackageManager.none, ("go.mod",))
    return None


def _detect_rust(p: Path) -> DetectionResult | None:
    if (p / "Cargo.toml").exists():
        return DetectionResult(Language.rust, PackageManager.none, ("Cargo.toml",))
    return None


def _detect_java(p: Path) -> DetectionResult | None:
    sigs = _has(p, "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle")
    if sigs:
        return DetectionResult(Language.java, PackageManager.none, sigs)
    return None


def _detect_ruby(p: Path) -> DetectionResult | None:
    if (p / "Gemfile").exists():
        return DetectionResult(Language.ruby, PackageManager.none, ("Gemfile",))
    return None


def _detect_php(p: Path) -> DetectionResult | None:
    if (p / "composer.json").exists():
        return DetectionResult(Language.php, PackageManager.none, ("composer.json",))
    return None


def _detect_dotnet(p: Path) -> DetectionResult | None:
    if _glob(p, "*.csproj") or _glob(p, "*.sln") or _glob(p, "*.fsproj"):
        return DetectionResult(Language.dotnet, PackageManager.none, ("csproj/sln",))
    return None


# Ordered detection chain — first non-None match wins.
_DETECTORS: tuple[Callable[[Path], DetectionResult | None], ...] = (
    _detect_static,
    _detect_python,
    _detect_node,
    _detect_go,
    _detect_rust,
    _detect_java,
    _detect_ruby,
    _detect_php,
    _detect_dotnet,
)


def detect_language(repo_root: Path) -> DetectionResult:
    """Inspect `repo_root` and return the most likely build language."""
    if not repo_root.exists() or not repo_root.is_dir():
        msg = f"repo_root does not exist or is not a directory: {repo_root}"
        raise ValueError(msg)

    for detector in _DETECTORS:
        result = detector(repo_root)
        if result is not None:
            return result
    return DetectionResult(Language.unknown)
