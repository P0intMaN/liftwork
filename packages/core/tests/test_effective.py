"""Tests for `effective_deploy_spec` — the file-wins merge."""

from __future__ import annotations

import textwrap
from dataclasses import dataclass

import pytest

from liftwork_core.build.config import EnvSecretRef, LiftworkConfigError
from liftwork_core.build.defaults import DeployDefaults
from liftwork_core.build.effective import effective_deploy_spec


@dataclass
class _AppStub:
    app_port: int = 3000
    health_check_path: str = "/"
    replicas: int = 2


_NODE_DEFAULTS = DeployDefaults(port=3000, health_check_path="/", source="node convention")
_PYTHON_DEFAULTS = DeployDefaults(port=8000, health_check_path="/", source="python convention")


def _spec(
    *,
    yaml_text: str | None = None,
    inferred: DeployDefaults | None = _NODE_DEFAULTS,
    app: _AppStub | None = None,
) -> object:
    return effective_deploy_spec(
        application=app or _AppStub(),
        inferred_defaults=inferred,
        liftwork_yaml=yaml_text,
    )


def test_no_yaml_uses_inferred_defaults() -> None:
    spec = _spec(inferred=_PYTHON_DEFAULTS)
    assert spec.port == 8000
    assert spec.health_check.path == "/"
    # Replicas comes from Application (no inferred field for it)
    assert spec.replicas == 2


def test_legacy_no_inferred_falls_back_to_application_columns() -> None:
    spec = _spec(inferred=None, app=_AppStub(app_port=4321, health_check_path="/probe"))
    assert spec.port == 4321
    assert spec.health_check.path == "/probe"


def test_blank_yaml_uses_inferred_defaults() -> None:
    spec = _spec(yaml_text="   \n  \n", inferred=_PYTHON_DEFAULTS)
    assert spec.port == 8000


def test_partial_yaml_overrides_only_named_fields() -> None:
    yaml_text = textwrap.dedent(
        """
        deploy:
          replicas: 5
          health_check:
            path: /healthz
        """
    ).strip()
    spec = _spec(yaml_text=yaml_text, inferred=_PYTHON_DEFAULTS)
    assert spec.replicas == 5
    assert spec.health_check.path == "/healthz"
    # Inferred port survives where the file is silent
    assert spec.port == 8000
    # Defaults survive on nested fields the file didn't mention
    assert spec.health_check.initial_delay_seconds == 5


def test_full_yaml_replaces_inferred_values() -> None:
    yaml_text = textwrap.dedent(
        """
        deploy:
          port: 9000
          replicas: 1
          env:
            LOG_LEVEL: DEBUG
            DB:
              from_secret: db
              key: url
          health_check:
            path: /readyz
            period_seconds: 30
        """
    ).strip()
    spec = _spec(yaml_text=yaml_text)
    assert spec.port == 9000
    assert spec.replicas == 1
    assert spec.health_check.path == "/readyz"
    assert spec.health_check.period_seconds == 30
    assert spec.env["LOG_LEVEL"] == "DEBUG"
    db = spec.env["DB"]
    assert isinstance(db, EnvSecretRef)
    assert db.from_secret == "db"


def test_invalid_yaml_raises() -> None:
    with pytest.raises(LiftworkConfigError, match="not valid YAML"):
        _spec(yaml_text="key: value:\n bad: [")


def test_root_must_be_mapping() -> None:
    with pytest.raises(LiftworkConfigError, match="mapping at the root"):
        _spec(yaml_text="- not\n- a\n- mapping")


def test_deploy_must_be_mapping() -> None:
    with pytest.raises(LiftworkConfigError, match="`deploy` must be a mapping"):
        _spec(yaml_text="deploy: oops")


def test_deploy_absent_falls_back_to_inferred() -> None:
    yaml_text = 'version: "1"\nlanguage: python\n'
    spec = _spec(yaml_text=yaml_text, inferred=_PYTHON_DEFAULTS)
    assert spec.port == 8000
    assert spec.health_check.path == "/"
