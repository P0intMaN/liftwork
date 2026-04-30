"""Password hashing and JWT helpers (v1 single-tenant auth)."""

from __future__ import annotations

import time
from typing import Any

import bcrypt
import jwt

from liftwork_core.config import JwtSettings

_BCRYPT_ROUNDS = 12


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(rounds=_BCRYPT_ROUNDS),
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def issue_jwt(*, subject: str, settings: JwtSettings, claims: dict[str, Any] | None = None) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": now + settings.ttl_seconds,
        "iss": "liftwork",
    }
    if claims:
        payload.update(claims)
    return jwt.encode(payload, settings.secret.get_secret_value(), algorithm=settings.algorithm)


def decode_jwt(token: str, settings: JwtSettings) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.secret.get_secret_value(),
        algorithms=[settings.algorithm],
        issuer="liftwork",
    )
