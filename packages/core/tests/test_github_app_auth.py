from __future__ import annotations

from typing import Any

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from liftwork_core.github.app_auth import (
    GitHubAppError,
    app_jwt,
    installation_access_token,
)


def _make_keypair() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = (
        key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_pem, public_pem


def test_app_jwt_round_trip() -> None:
    import time

    private, public = _make_keypair()
    now = int(time.time())
    token = app_jwt(app_id="424242", private_key_pem=private, now=now)
    decoded = pyjwt.decode(token, public, algorithms=["RS256"])
    assert decoded["iss"] == "424242"
    assert decoded["iat"] == now - 60
    assert decoded["exp"] == now + 9 * 60


def test_app_jwt_rejects_missing_inputs() -> None:
    private, _ = _make_keypair()
    with pytest.raises(GitHubAppError, match="app_id"):
        app_jwt(app_id="", private_key_pem=private)
    with pytest.raises(GitHubAppError, match="private_key"):
        app_jwt(app_id="42", private_key_pem="")


def test_app_jwt_rejects_garbage_pem() -> None:
    with pytest.raises(GitHubAppError, match="failed to sign"):
        app_jwt(app_id="42", private_key_pem="not-a-real-pem")


async def test_installation_access_token_happy_path() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            201,
            json={"token": "ghs_install_token_xyz", "expires_at": "2026-04-30T00:00:00Z"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        token = await installation_access_token(
            installation_id=12345,
            jwt_token="fake-app-jwt",
            client=client,
        )
    assert token == "ghs_install_token_xyz"
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.url.path == "/app/installations/12345/access_tokens"
    assert req.headers["Authorization"] == "Bearer fake-app-jwt"
    assert req.headers["X-GitHub-Api-Version"] == "2022-11-28"


async def test_installation_access_token_rejects_non_201() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(401, json={"message": "Bad credentials"})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(GitHubAppError, match="HTTP 401"):
            await installation_access_token(
                installation_id=42,
                jwt_token="bad-jwt",
                client=client,
            )


async def test_installation_access_token_rejects_missing_token_field() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(201, json={"unrelated": "no token here"})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(GitHubAppError, match="missing 'token'"):
            await installation_access_token(
                installation_id=42,
                jwt_token="ok-jwt",
                client=client,
            )


async def test_installation_access_token_validates_inputs() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(201, json={"token": "x"}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(GitHubAppError, match="positive integer"):
            await installation_access_token(installation_id=0, jwt_token="x", client=client)


async def test_installation_access_token_handles_network_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns fail")

    transport = httpx.MockTransport(boom)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(GitHubAppError, match="installation token request failed"):
            await installation_access_token(installation_id=1, jwt_token="x", client=client)


def test_app_jwt_payload_structure_explicit() -> None:
    """Spot-check exact claims so a future refactor can't silently change them."""
    private, _ = _make_keypair()
    token = app_jwt(app_id="42", private_key_pem=private, now=10_000)
    headers = pyjwt.get_unverified_header(token)
    payload: dict[str, Any] = pyjwt.decode(
        token,
        options={"verify_signature": False, "verify_exp": False},
    )
    assert headers["alg"] == "RS256"
    assert payload == {"iss": "42", "iat": 10_000 - 60, "exp": 10_000 + 540}
