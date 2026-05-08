"""Infer sensible deploy defaults from a checked-out repository.

Used by the build job to stamp a *base* DeploySpec onto each BuildRun
*before* `liftwork.yaml` overrides are applied. Lets `liftwork` be
zero-config for the happy path: most apps Just Work without committing
a `liftwork.yaml` and without filling out the dashboard form.

Priority for `port`:
  1. EXPOSE directive in the repo's `Dockerfile` (if present)
  2. Per-language convention (node→3000, python→8000, etc.)
  3. Last-resort 8080
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from liftwork_core.build.language import DetectionResult, Language, detect_language

_DEFAULT_PORT = 8080
_DEFAULT_HEALTH_PATH = "/"

# Per-language port conventions. `static` covers "repo ships its own
# Dockerfile" — the EXPOSE parser picks up the real value if present;
# otherwise nginx-unprivileged's 8080 is a safe last resort.
_PORT_BY_LANGUAGE: dict[Language, int] = {
    Language.node: 3000,
    Language.python: 8000,
    Language.ruby: 3000,
    Language.dotnet: 5000,
    Language.go: 8080,
    Language.rust: 8080,
    Language.java: 8080,
    Language.php: 8080,
    Language.static: 8080,
    Language.unknown: 8080,
}

# `EXPOSE 8080`, `EXPOSE 8080/tcp`, `EXPOSE 8080 9090` — first port wins.
_EXPOSE_RE = re.compile(r"^\s*EXPOSE\s+(\d+)", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class DeployDefaults:
    """Best-guess defaults inferred from the repo. Always overridable."""

    port: int
    health_check_path: str
    # Human-readable provenance for the dashboard ("from EXPOSE in Dockerfile").
    source: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "port": self.port,
            "health_check_path": self.health_check_path,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | int]) -> DeployDefaults:
        return cls(
            port=int(data["port"]),
            health_check_path=str(data["health_check_path"]),
            source=str(data["source"]),
        )


def infer_deploy_defaults(workspace: Path) -> DeployDefaults:
    """Inspect a cloned repo and pick reasonable port + health defaults."""
    detection = detect_language(workspace)
    port, source = _infer_port(workspace, detection)
    return DeployDefaults(
        port=port,
        health_check_path=_DEFAULT_HEALTH_PATH,
        source=source,
    )


def _infer_port(workspace: Path, detection: DetectionResult) -> tuple[int, str]:
    expose = _read_expose(workspace / "Dockerfile") or _read_expose(
        workspace / "Containerfile"
    )
    if expose is not None:
        return expose, "Dockerfile EXPOSE"
    by_lang = _PORT_BY_LANGUAGE.get(detection.language, _DEFAULT_PORT)
    if detection.is_known:
        return by_lang, f"{detection.language.value} convention"
    return _DEFAULT_PORT, "fallback"


def _read_expose(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _EXPOSE_RE.search(text)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None
