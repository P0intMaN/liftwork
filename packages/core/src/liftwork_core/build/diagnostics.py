"""Classify common BuildKit failure modes into actionable diagnoses.

Build failures are mostly debuggable from the live log stream — the
user can read whatever `npm install` or `pip install` printed. The two
classes that *aren't* easy to debug from the log alone live at the
boundary between liftwork's wiring and BuildKit:

  1. **Registry push auth failures** — happens after a successful build,
     when BuildKit tries to push to a registry it can't authenticate to.
  2. **Dockerfile syntax errors** — BuildKit emits a structured "parse
     error at line N" but it's easy to miss in a long build log.
  3. **Network/DNS failures** — pod cannot resolve the registry or
     base image source. Common in restricted clusters.

These three categories cover ~80% of "build failed and the user has no
idea why" support tickets in similar systems.
"""

from __future__ import annotations

import enum
import re
from dataclasses import dataclass


class BuildDiagnosisCategory(enum.StrEnum):
    registry_auth = "registry_auth"
    dockerfile_syntax = "dockerfile_syntax"
    network = "network"


@dataclass(frozen=True)
class BuildDiagnosis:
    category: BuildDiagnosisCategory
    message: str  # actionable, fix-this-specific-thing message


# Patterns are matched against the concatenation of the exception text
# and the captured log tail (case-insensitive). Order matters — most
# specific first; the first match wins.

_REGISTRY_AUTH_PATTERNS = (
    re.compile(r"denied:\s*requested access to the resource is denied", re.IGNORECASE),
    re.compile(r"401\s+unauthorized", re.IGNORECASE),
    re.compile(r"unauthorized:\s*HTTP\s+401", re.IGNORECASE),
    re.compile(r"authentication required", re.IGNORECASE),
    re.compile(r"basic auth credentials", re.IGNORECASE),
)

_DOCKERFILE_SYNTAX_PATTERNS = (
    re.compile(r"dockerfile parse error.*line\s*(\d+)", re.IGNORECASE),
    re.compile(r"unknown instruction:\s*(\S+)", re.IGNORECASE),
    re.compile(r"failed to parse stage name", re.IGNORECASE),
    re.compile(r"parse error on line\s*(\d+)", re.IGNORECASE),
)

_NETWORK_PATTERNS = (
    re.compile(r"dial tcp.*: connect: (?:no route to host|connection refused)", re.IGNORECASE),
    re.compile(r"network is unreachable", re.IGNORECASE),
    re.compile(r"lookup\s+\S+:\s*no such host", re.IGNORECASE),
    re.compile(r"i/o timeout.*dial tcp", re.IGNORECASE),
    re.compile(r"temporary failure in name resolution", re.IGNORECASE),
)


def classify_build_error(
    *,
    error_text: str,
    log_excerpt: str | None = None,
) -> BuildDiagnosis | None:
    """Pattern-match exception + log tail; return the most-actionable diagnosis."""
    haystack = error_text
    if log_excerpt:
        haystack = f"{error_text}\n{log_excerpt}"

    for pattern in _REGISTRY_AUTH_PATTERNS:
        if pattern.search(haystack):
            return BuildDiagnosis(
                BuildDiagnosisCategory.registry_auth,
                (
                    "registry rejected the image push: authentication failed. "
                    "Check that the worker has push credentials for the configured "
                    "registry — usually via an imagePullSecret on the buildkit "
                    "ServiceAccount, or by configuring `LIFTWORK_REGISTRY__USERNAME` "
                    "and `LIFTWORK_REGISTRY__PASSWORD`."
                ),
            )

    for pattern in _DOCKERFILE_SYNTAX_PATTERNS:
        match = pattern.search(haystack)
        if match:
            detail = match.group(0).strip()
            return BuildDiagnosis(
                BuildDiagnosisCategory.dockerfile_syntax,
                (
                    f"Dockerfile parse error: {detail}. "
                    "Fix the Dockerfile (or the file pointed to by "
                    "`build.dockerfile` in liftwork.yaml) and push again."
                ),
            )

    for pattern in _NETWORK_PATTERNS:
        if pattern.search(haystack):
            return BuildDiagnosis(
                BuildDiagnosisCategory.network,
                (
                    "build failed with a network/DNS error. The buildkit pod "
                    "couldn't reach a host it needed (registry, base-image source, "
                    "or a dependency mirror). Check cluster egress / DNS, or "
                    "if you're behind a corporate proxy, set HTTP_PROXY/HTTPS_PROXY "
                    "on the worker."
                ),
            )

    return None
