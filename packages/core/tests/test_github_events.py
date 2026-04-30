from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from liftwork_core.github import (
    PushEvent,
    WebhookVerificationError,
    parse_push_event,
    verify_signature,
)


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_correct() -> None:
    body = b'{"ref":"refs/heads/main"}'
    sig = _sign(body, "shh")
    verify_signature(secret="shh", payload=body, signature_header=sig)


def test_verify_signature_rejects_wrong_secret() -> None:
    body = b"{}"
    with pytest.raises(WebhookVerificationError, match="mismatch"):
        verify_signature(secret="other", payload=body, signature_header=_sign(body, "shh"))


def test_verify_signature_rejects_missing_header() -> None:
    with pytest.raises(WebhookVerificationError, match="missing"):
        verify_signature(secret="x", payload=b"{}", signature_header=None)


def test_verify_signature_rejects_bad_prefix() -> None:
    with pytest.raises(WebhookVerificationError, match="must start"):
        verify_signature(secret="x", payload=b"{}", signature_header="md5=abc")


def test_verify_signature_rejects_empty_secret() -> None:
    with pytest.raises(WebhookVerificationError, match="secret is empty"):
        verify_signature(secret="", payload=b"{}", signature_header="sha256=00")


def _push_payload(**overrides: object) -> dict[str, object]:
    base = {
        "ref": "refs/heads/main",
        "after": "0123456789abcdef" * 2 + "01234567",
        "repository": {
            "name": "api",
            "full_name": "acme/api",
            "owner": {"login": "acme"},
            "clone_url": "https://github.com/acme/api.git",
        },
        "head_commit": {"id": "abc123", "message": "fix: auth bug"},
        "installation": {"id": 999_888},
        "sender": {"login": "developer"},
    }
    base.update(overrides)  # type: ignore[arg-type]
    return base


def test_parse_push_event_extracts_metadata() -> None:
    payload = json.dumps(_push_payload()).encode()
    push: PushEvent = parse_push_event(payload)
    assert push.is_branch_push is True
    assert push.is_zero_after is False
    assert push.branch == "main"
    assert push.repo_owner == "acme"
    assert push.repo_name == "api"
    assert push.repo_full_name == "acme/api"
    assert push.repo_clone_url == "https://github.com/acme/api.git"
    assert push.commit_message == "fix: auth bug"
    assert push.installation_id == 999_888


def test_parse_push_event_rejects_garbage() -> None:
    with pytest.raises(WebhookVerificationError, match="invalid push event"):
        parse_push_event(b"not json at all")


def test_branch_deletion_marks_zero_after() -> None:
    payload = json.dumps(_push_payload(after="0" * 40)).encode()
    push = parse_push_event(payload)
    assert push.is_zero_after is True


def test_tag_push_is_not_branch_push() -> None:
    payload = json.dumps(_push_payload(ref="refs/tags/v1.0.0")).encode()
    push = parse_push_event(payload)
    assert push.is_branch_push is False
