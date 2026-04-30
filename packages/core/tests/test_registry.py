from __future__ import annotations

import base64
import json

import pytest

from liftwork_core.registry import (
    build_docker_config_json,
    ghcr_repository,
    image_ref,
    sanitize_branch,
    short_sha,
    tag_for_commit,
)
from liftwork_core.registry.protocols import ImageRef


def test_short_sha_default_seven() -> None:
    assert short_sha("abc1234567890def") == "abc1234"


def test_short_sha_validates_inputs() -> None:
    with pytest.raises(ValueError, match="empty"):
        short_sha("")
    with pytest.raises(ValueError, match=">= 4"):
        short_sha("abc1234567890", length=2)


def test_sanitize_branch_strips_unsafe_chars() -> None:
    assert sanitize_branch("feature/foo bar!") == "feature-foo-bar"
    assert sanitize_branch("MAIN") == "main"


def test_sanitize_branch_caps_length() -> None:
    long = "x" * 200
    assert len(sanitize_branch(long)) == 64


def test_tag_for_commit_combines_branch_and_sha() -> None:
    assert (
        tag_for_commit(branch="feature/Auth-2", sha="0123456789abcdef0123456789abcdef01234567")
        == "feature-auth-2-0123456"
    )


def test_image_ref_assembles_full_reference() -> None:
    assert (
        image_ref(registry_host="ghcr.io", repository="acme/api", tag="main-deadbee")
        == "ghcr.io/acme/api:main-deadbee"
    )


def test_image_ref_validates_inputs() -> None:
    with pytest.raises(ValueError):
        image_ref(registry_host="", repository="x", tag="y")


def test_ghcr_repository_lowercases() -> None:
    assert ghcr_repository("AcmeCorp", "Cool-API") == "acmecorp/cool-api"


def test_ghcr_repository_validates() -> None:
    with pytest.raises(ValueError):
        ghcr_repository("", "x")


def test_image_ref_model_with_digest() -> None:
    ref = ImageRef(
        registry="ghcr.io",
        repository="acme/api",
        tag="main-abc1234",
        digest="sha256:" + "0" * 64,
    )
    assert ref.reference == f"ghcr.io/acme/api@sha256:{'0' * 64}"
    assert ref.with_tag_only == "ghcr.io/acme/api:main-abc1234"


def test_image_ref_model_without_digest_uses_tag() -> None:
    ref = ImageRef(registry="ghcr.io", repository="acme/api", tag="main-abc1234")
    assert ref.reference == "ghcr.io/acme/api:main-abc1234"


def test_docker_config_json_round_trip() -> None:
    blob = build_docker_config_json(
        server="ghcr.io",
        username="P0intMaN",
        token="ghp_secret_token_value",
    )
    parsed = json.loads(blob)
    auths = parsed["auths"]["ghcr.io"]
    assert auths["username"] == "P0intMaN"
    assert auths["password"] == "ghp_secret_token_value"
    decoded = base64.b64decode(auths["auth"]).decode("utf-8")
    assert decoded == "P0intMaN:ghp_secret_token_value"


def test_docker_config_json_validates() -> None:
    with pytest.raises(ValueError):
        build_docker_config_json(server="", username="u", token="t")
