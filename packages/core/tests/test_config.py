from __future__ import annotations

import pytest

from liftwork_core.config import Settings, get_settings, reset_settings_cache


def test_settings_loads_from_env() -> None:
    reset_settings_cache()
    s = get_settings()
    assert s.api.port == 7878
    assert s.worker.health_port == 7879
    assert str(s.database.url).startswith("postgresql+asyncpg://")
    assert s.jwt.secret.get_secret_value()
    assert s.telemetry.otel_enabled is False  # disabled in test env


def test_settings_rejects_missing_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIFTWORK_DATABASE__URL", raising=False)
    monkeypatch.delenv("LIFTWORK_REDIS__URL", raising=False)
    monkeypatch.delenv("LIFTWORK_JWT__SECRET", raising=False)
    with pytest.raises(Exception):  # noqa: B017,PT011 — pydantic ValidationError
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_use_json_logs_defaults_per_env(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_settings_cache()
    monkeypatch.setenv("LIFTWORK_ENV", "prod")
    s = Settings()  # type: ignore[call-arg]
    assert s.use_json_logs is True
    monkeypatch.setenv("LIFTWORK_ENV", "dev")
    s = Settings()  # type: ignore[call-arg]
    assert s.use_json_logs is False
