"""GitHub App authentication.

Two functions:
  * app_jwt — mint a 9-minute RS256 JWT signed with the App's private key
    (GitHub allows up to 10 minutes; we leave a safety margin).
  * installation_access_token — exchange the App JWT for an installation
    access token (`POST /app/installations/{id}/access_tokens`). These
    tokens are short-lived (~1h) and scoped to one installation.

Tokens returned by `installation_access_token` are what we use to clone
private repos and post commit statuses on behalf of the installation.
"""

from __future__ import annotations

import time
from typing import Final

import httpx
import jwt as pyjwt

GITHUB_API_BASE: Final[str] = "https://api.github.com"
_JWT_LIFETIME_SECONDS: Final[int] = 9 * 60  # 9 min — safety margin under GitHub's 10-min cap
_JWT_CLOCK_SKEW_SECONDS: Final[int] = 60  # account for clock drift


class GitHubAppError(RuntimeError):
    pass


def app_jwt(*, app_id: str, private_key_pem: str, now: int | None = None) -> str:
    """Mint an RS256 JWT that authenticates as the App itself."""
    if not app_id:
        msg = "app_id is required"
        raise GitHubAppError(msg)
    if not private_key_pem:
        msg = "private_key_pem is required"
        raise GitHubAppError(msg)

    issued = now if now is not None else int(time.time())
    payload = {
        "iat": issued - _JWT_CLOCK_SKEW_SECONDS,
        "exp": issued + _JWT_LIFETIME_SECONDS,
        "iss": app_id,
    }
    try:
        return pyjwt.encode(payload, private_key_pem, algorithm="RS256")
    except Exception as exc:  # pyjwt may raise multiple types
        msg = f"failed to sign App JWT: {exc.__class__.__name__}: {exc}"
        raise GitHubAppError(msg) from exc


async def installation_access_token(
    *,
    installation_id: int,
    jwt_token: str,
    client: httpx.AsyncClient | None = None,
    timeout_seconds: float = 10.0,
) -> str:
    """Exchange an App JWT for an installation access token."""
    if installation_id <= 0:
        msg = "installation_id must be a positive integer"
        raise GitHubAppError(msg)

    own_client = client is None
    cli = client or httpx.AsyncClient(timeout=timeout_seconds)
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {jwt_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        resp = await cli.post(url, headers=headers)
    except httpx.HTTPError as exc:
        msg = f"GitHub installation token request failed: {exc}"
        raise GitHubAppError(msg) from exc
    finally:
        if own_client:
            await cli.aclose()

    if resp.status_code != httpx.codes.CREATED:
        msg = f"GitHub installation token rejected: HTTP {resp.status_code} {resp.text[:200]}"
        raise GitHubAppError(msg)

    body = resp.json()
    token = body.get("token")
    if not isinstance(token, str) or not token:
        msg = "GitHub installation token response missing 'token' field"
        raise GitHubAppError(msg)
    return token
