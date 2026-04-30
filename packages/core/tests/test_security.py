from __future__ import annotations

import time

import pytest
from pydantic import SecretStr

from liftwork_core.config import JwtSettings
from liftwork_core.security import decode_jwt, hash_password, issue_jwt, verify_password


def test_password_hash_and_verify() -> None:
    pw = "correct-horse-battery-staple"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("nope", hashed) is False


def test_password_verify_handles_garbage_hash() -> None:
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_jwt_round_trip() -> None:
    settings = JwtSettings(secret=SecretStr("a" * 32), algorithm="HS256", ttl_seconds=60)
    token = issue_jwt(subject="user-123", settings=settings, claims={"role": "admin"})
    decoded = decode_jwt(token, settings)
    assert decoded["sub"] == "user-123"
    assert decoded["role"] == "admin"
    assert decoded["iss"] == "liftwork"


def test_jwt_rejects_wrong_secret() -> None:
    settings = JwtSettings(secret=SecretStr("a" * 32), algorithm="HS256", ttl_seconds=60)
    token = issue_jwt(subject="user-123", settings=settings)
    bad = JwtSettings(secret=SecretStr("b" * 32), algorithm="HS256", ttl_seconds=60)
    with pytest.raises(Exception):  # noqa: B017,PT011 — InvalidSignatureError
        decode_jwt(token, bad)


def test_jwt_expired_is_rejected() -> None:
    settings = JwtSettings(secret=SecretStr("a" * 32), algorithm="HS256", ttl_seconds=1)
    token = issue_jwt(subject="user-123", settings=settings)
    time.sleep(2)
    with pytest.raises(Exception):  # noqa: B017,PT011 — ExpiredSignatureError
        decode_jwt(token, settings)
