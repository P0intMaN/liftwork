"""GitHub Container Registry helpers.

Two responsibilities for v1:
  1. Build a `~/.docker/config.json` blob the BuildKit Job mounts as a
     Secret to authenticate the push.
  2. Compute the canonical GHCR repository slug for an owner/repo pair.

Manifest inspection lives in a future iteration; for v1 we trust the
push and read the digest BuildKit prints.
"""

from __future__ import annotations

import base64
import json
from typing import Final

GHCR_HOST: Final[str] = "ghcr.io"


def ghcr_repository(owner: str, name: str) -> str:
    """`owner/name` (lowercased) — GHCR is case-insensitive but stores lowercase."""
    if not owner or not name:
        msg = "owner and name are required"
        raise ValueError(msg)
    return f"{owner.lower()}/{name.lower()}"


def build_docker_config_json(*, server: str, username: str, token: str) -> bytes:
    """Return a JSON blob shaped like `~/.docker/config.json`.

    The token field is base64-encoded under `auths.<server>.auth` per the
    docker config schema. K8s `kubernetes.io/dockerconfigjson` Secrets
    consume this format directly.
    """
    if not server or not username or not token:
        msg = "server, username, token are all required"
        raise ValueError(msg)
    raw = f"{username}:{token}".encode()
    auth_b64 = base64.b64encode(raw).decode("ascii")
    payload = {"auths": {server: {"username": username, "password": token, "auth": auth_b64}}}
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")
