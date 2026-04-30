"""Image tag strategy — deterministic, immutable per commit."""

from __future__ import annotations

import re
from typing import Final

_BRANCH_SANITIZER = re.compile(r"[^a-zA-Z0-9._-]+")
_MIN_SHORT_SHA_LENGTH: Final[int] = 4


def short_sha(sha: str, length: int = 7) -> str:
    if not sha:
        msg = "commit sha must not be empty"
        raise ValueError(msg)
    if length < _MIN_SHORT_SHA_LENGTH:
        msg = f"short sha length must be >= {_MIN_SHORT_SHA_LENGTH}"
        raise ValueError(msg)
    return sha[:length]


def sanitize_branch(branch: str) -> str:
    """Coerce a branch name into a Docker-tag-safe slug."""
    if not branch:
        msg = "branch must not be empty"
        raise ValueError(msg)
    cleaned = _BRANCH_SANITIZER.sub("-", branch).strip("-").lower()
    return cleaned[:64] or "branch"


def tag_for_commit(*, branch: str, sha: str) -> str:
    return f"{sanitize_branch(branch)}-{short_sha(sha)}"


def image_ref(*, registry_host: str, repository: str, tag: str) -> str:
    if not registry_host or not repository or not tag:
        msg = "registry_host, repository, tag must all be non-empty"
        raise ValueError(msg)
    return f"{registry_host}/{repository}:{tag}"
