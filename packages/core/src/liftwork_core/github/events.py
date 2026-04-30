"""Webhook signature verification + push event parsing."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from pydantic import BaseModel, ValidationError


class WebhookVerificationError(Exception):
    pass


def verify_signature(
    *,
    secret: str,
    payload: bytes,
    signature_header: str | None,
) -> None:
    """Verify GitHub's `X-Hub-Signature-256` HMAC header.

    Raises `WebhookVerificationError` on any failure. Returns silently
    when the signature matches.
    """
    if not secret:
        msg = "webhook secret is empty — webhook handler refuses to accept anything"
        raise WebhookVerificationError(msg)
    if not signature_header:
        msg = "missing X-Hub-Signature-256 header"
        raise WebhookVerificationError(msg)
    if not signature_header.startswith("sha256="):
        msg = "X-Hub-Signature-256 header must start with 'sha256='"
        raise WebhookVerificationError(msg)

    expected_digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    expected = f"sha256={expected_digest}"

    if not hmac.compare_digest(expected, signature_header):
        msg = "X-Hub-Signature-256 mismatch"
        raise WebhookVerificationError(msg)


class PushEvent(BaseModel):
    """Subset of GitHub's push event payload that liftwork needs."""

    ref: str
    after: str
    repository: dict[str, Any]
    head_commit: dict[str, Any] | None = None
    installation: dict[str, Any] | None = None
    sender: dict[str, Any] | None = None

    @property
    def is_branch_push(self) -> bool:
        return self.ref.startswith("refs/heads/")

    @property
    def branch(self) -> str:
        return self.ref.removeprefix("refs/heads/")

    @property
    def repo_owner(self) -> str:
        owner = self.repository.get("owner") or {}
        return str(owner.get("login") or "")

    @property
    def repo_name(self) -> str:
        return str(self.repository.get("name") or "")

    @property
    def repo_full_name(self) -> str:
        return str(self.repository.get("full_name") or f"{self.repo_owner}/{self.repo_name}")

    @property
    def repo_clone_url(self) -> str:
        return str(self.repository.get("clone_url") or "")

    @property
    def commit_sha(self) -> str:
        return self.after

    @property
    def commit_message(self) -> str | None:
        if self.head_commit is None:
            return None
        msg = self.head_commit.get("message")
        return str(msg) if msg is not None else None

    @property
    def installation_id(self) -> int | None:
        if self.installation is None:
            return None
        raw = self.installation.get("id")
        return int(raw) if raw is not None else None

    @property
    def is_zero_after(self) -> bool:
        """A branch deletion has after=0...0 — we never build for these."""
        return self.after in ("0" * 40, "")


def parse_push_event(payload: bytes) -> PushEvent:
    """Parse a JSON push payload into a PushEvent model."""
    try:
        return PushEvent.model_validate_json(payload)
    except ValidationError as exc:
        msg = f"invalid push event payload: {exc}"
        raise WebhookVerificationError(msg) from exc
