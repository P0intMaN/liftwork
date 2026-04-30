from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from liftwork_core.build.config import (
    LiftworkConfig,
    LiftworkConfigError,
    load_liftwork_config,
)
from liftwork_core.build.language import Language


def test_load_returns_none_when_missing(tmp_path: Path) -> None:
    assert load_liftwork_config(tmp_path / "liftwork.yaml") is None


def test_load_full_config(tmp_path: Path) -> None:
    p = tmp_path / "liftwork.yaml"
    p.write_text(
        textwrap.dedent(
            """
            version: "1"
            language: python
            build:
              dockerfile: ./Dockerfile.dev
              args: { PY_VERSION: "3.12" }
            deploy:
              port: 9000
              replicas: 3
              command: ["uvicorn", "main:app"]
              env: { LOG_LEVEL: DEBUG }
              resources:
                requests: { cpu: "200m", memory: "256Mi" }
              ingress:
                enabled: true
                host: api.example.com
                class_name: nginx
                tls_secret_name: api-tls
            """
        ).strip(),
        encoding="utf-8",
    )
    cfg = load_liftwork_config(p)
    assert cfg is not None
    assert cfg.language is Language.python
    assert cfg.build.dockerfile == "./Dockerfile.dev"
    assert cfg.build.args == {"PY_VERSION": "3.12"}
    assert cfg.deploy.port == 9000
    assert cfg.deploy.command == ["uvicorn", "main:app"]
    assert cfg.deploy.resources.requests.cpu == "200m"
    assert cfg.deploy.ingress.enabled is True
    assert cfg.deploy.ingress.host == "api.example.com"
    assert cfg.deploy.ingress.class_name == "nginx"
    assert cfg.deploy.ingress.tls_secret_name == "api-tls"


def test_load_empty_file_returns_defaults(tmp_path: Path) -> None:
    p = tmp_path / "liftwork.yaml"
    p.write_text("", encoding="utf-8")
    cfg = load_liftwork_config(p)
    assert cfg == LiftworkConfig()


def test_invalid_root_type_raises(tmp_path: Path) -> None:
    p = tmp_path / "liftwork.yaml"
    p.write_text("- not-a-mapping", encoding="utf-8")
    with pytest.raises(LiftworkConfigError, match="mapping at the root"):
        load_liftwork_config(p)


def test_unparseable_yaml_raises(tmp_path: Path) -> None:
    p = tmp_path / "liftwork.yaml"
    p.write_text("key: value:\n  nested but bad indent\n  - list", encoding="utf-8")
    with pytest.raises(LiftworkConfigError):
        load_liftwork_config(p)


def test_unknown_language_raises(tmp_path: Path) -> None:
    p = tmp_path / "liftwork.yaml"
    p.write_text("language: cobol", encoding="utf-8")
    with pytest.raises(LiftworkConfigError, match="failed validation"):
        load_liftwork_config(p)


def test_ingress_default_disabled() -> None:
    cfg = LiftworkConfig()
    assert cfg.deploy.ingress.enabled is False
    assert cfg.deploy.ingress.host is None
