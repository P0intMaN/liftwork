"""Pattern-match tests for `classify_build_error`."""

from __future__ import annotations

import pytest

from liftwork_core.build.diagnostics import (
    BuildDiagnosisCategory,
    classify_build_error,
)

# ---------------------------------------------------------------------------
# Registry auth
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "BuildKitExecutorError: failed to push: denied: requested access to the resource is denied",
        "push failed with: 401 Unauthorized when accessing https://registry.example.com/v2/",
        "unauthorized: HTTP 401 from registry",
        "registry returned: authentication required",
        "buildctl: failed: basic auth credentials not provided",
    ],
)
def test_registry_auth_classifies(text: str) -> None:
    diag = classify_build_error(error_text=text)
    assert diag is not None
    assert diag.category is BuildDiagnosisCategory.registry_auth
    assert "authentication" in diag.message.lower() or "credentials" in diag.message.lower()


# ---------------------------------------------------------------------------
# Dockerfile syntax
# ---------------------------------------------------------------------------


def test_dockerfile_parse_error_with_line() -> None:
    diag = classify_build_error(
        error_text="buildkit: dockerfile parse error on line 14: unknown instruction"
    )
    assert diag is not None
    assert diag.category is BuildDiagnosisCategory.dockerfile_syntax
    assert "line 14" in diag.message or "line  14" in diag.message


def test_unknown_instruction_classifies() -> None:
    diag = classify_build_error(error_text="buildkit: unknown instruction: COPYY")
    assert diag is not None
    assert diag.category is BuildDiagnosisCategory.dockerfile_syntax


def test_failed_to_parse_stage_name() -> None:
    diag = classify_build_error(error_text="failed to parse stage name 'as builder'")
    assert diag is not None
    assert diag.category is BuildDiagnosisCategory.dockerfile_syntax


# ---------------------------------------------------------------------------
# Network / DNS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "buildctl: dial tcp 10.96.5.5:5000: connect: no route to host",
        "dial tcp 1.2.3.4:443: connect: connection refused",
        "Get https://registry.example.com/: lookup registry.example.com: no such host",
        "i/o timeout dial tcp registry-1.docker.io:443",
        "temporary failure in name resolution",
    ],
)
def test_network_classifies(text: str) -> None:
    diag = classify_build_error(error_text=text)
    assert diag is not None
    assert diag.category is BuildDiagnosisCategory.network


# ---------------------------------------------------------------------------
# Precedence + log-tail fallback
# ---------------------------------------------------------------------------


def test_pattern_in_log_excerpt_when_exception_is_generic() -> None:
    diag = classify_build_error(
        error_text="BuildKitExecutorError: build pod exited non-zero",
        log_excerpt=(
            "Step 4/12 : RUN pip install -r requirements.txt\n"
            "...\n"
            "denied: requested access to the resource is denied\n"
        ),
    )
    assert diag is not None
    assert diag.category is BuildDiagnosisCategory.registry_auth


def test_registry_auth_takes_precedence_over_network() -> None:
    # If both signals appear, registry-auth (more specific) wins.
    text = (
        "denied: requested access to the resource is denied\n"
        "earlier: dial tcp 10.0.0.1:443: connect: connection refused"
    )
    diag = classify_build_error(error_text=text)
    assert diag is not None
    assert diag.category is BuildDiagnosisCategory.registry_auth


# ---------------------------------------------------------------------------
# No match
# ---------------------------------------------------------------------------


def test_unrecognised_error_returns_none() -> None:
    assert classify_build_error(error_text="npm ERR! code ELIFECYCLE\nnpm ERR! foo@1 build") is None


def test_empty_error_returns_none() -> None:
    assert classify_build_error(error_text="") is None
