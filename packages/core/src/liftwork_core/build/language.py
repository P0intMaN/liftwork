"""Language detection from a checked-out repository on disk.

Heuristics are intentionally simple and ordered: the first match wins.
A repo can override detection by committing a `liftwork.yaml` with an
explicit `language:` field, or by committing its own `Dockerfile`.
"""

from __future__ import annotations

import enum
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
    static = "static"   # repo ships its own Dockerfile or is a static site
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


def detect_language(repo_root: Path) -> DetectionResult:
    """Inspect `repo_root` and return the most likely build language."""
    if not repo_root.exists() or not repo_root.is_dir():
        msg = f"repo_root does not exist or is not a directory: {repo_root}"
        raise ValueError(msg)

    # User-authored Dockerfile always wins.
    dockerfile_signals = _has(repo_root, "Dockerfile", "Containerfile")
    if dockerfile_signals:
        return DetectionResult(
            language=Language.static,
            package_manager=PackageManager.none,
            signals=dockerfile_signals,
        )

    # Python
    py_signals = _has(repo_root, "pyproject.toml", "requirements.txt", "Pipfile", "setup.py")
    if py_signals:
        pm = PackageManager.pip
        if (repo_root / "uv.lock").exists():
            pm = PackageManager.uv
        elif (repo_root / "poetry.lock").exists():
            pm = PackageManager.poetry
        return DetectionResult(Language.python, pm, py_signals)

    # Node
    if (repo_root / "package.json").exists():
        pm = PackageManager.npm
        if (repo_root / "pnpm-lock.yaml").exists():
            pm = PackageManager.pnpm
        elif (repo_root / "yarn.lock").exists():
            pm = PackageManager.yarn
        return DetectionResult(Language.node, pm, ("package.json",))

    # Go
    if (repo_root / "go.mod").exists():
        return DetectionResult(Language.go, PackageManager.none, ("go.mod",))

    # Rust
    if (repo_root / "Cargo.toml").exists():
        return DetectionResult(Language.rust, PackageManager.none, ("Cargo.toml",))

    # Java / JVM
    java_signals = _has(repo_root, "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle")
    if java_signals:
        return DetectionResult(Language.java, PackageManager.none, java_signals)

    # Ruby
    if (repo_root / "Gemfile").exists():
        return DetectionResult(Language.ruby, PackageManager.none, ("Gemfile",))

    # PHP
    if (repo_root / "composer.json").exists():
        return DetectionResult(Language.php, PackageManager.none, ("composer.json",))

    # .NET
    if _glob(repo_root, "*.csproj") or _glob(repo_root, "*.sln") or _glob(repo_root, "*.fsproj"):
        return DetectionResult(Language.dotnet, PackageManager.none, ("csproj/sln",))

    return DetectionResult(Language.unknown)
