"""Pydantic settings for the entire liftwork stack.

All env vars use the prefix `LIFTWORK_`. Nested fields use a double
underscore as the delimiter (e.g. `LIFTWORK_DATABASE__URL`).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field, PostgresDsn, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class APISettings(BaseModel):
    host: str = "0.0.0.0"  # noqa: S104  (intentional bind for container use)
    port: int = 7878


class WorkerSettings(BaseModel):
    concurrency: int = 4
    health_port: int = 7879


class DatabaseSettings(BaseModel):
    url: PostgresDsn
    pool_size: int = 10
    max_overflow: int = 5
    pool_pre_ping: bool = True
    echo: bool = False


class RedisQueueSettings(BaseModel):
    url: RedisDsn


class TelemetrySettings(BaseModel):
    otel_enabled: bool = True
    otel_exporter_otlp_endpoint: str | None = None
    otel_service_name: str = "liftwork"
    otel_service_namespace: str = "liftwork"
    prometheus_path: str = "/metrics"


class JwtSettings(BaseModel):
    secret: SecretStr
    algorithm: str = "HS256"
    ttl_seconds: int = 3600


class RegistrySettings(BaseModel):
    host: str = "ghcr.io"
    username: str | None = None
    token: SecretStr | None = None


class GitHubSettings(BaseModel):
    webhook_secret: SecretStr | None = None


class K8sSettings(BaseModel):
    kube_context: str | None = None
    in_cluster: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LIFTWORK_",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["dev", "staging", "prod"] = "dev"
    log_level: str = "INFO"
    json_logs: bool | None = None  # None => True in non-dev, False in dev

    api: APISettings = Field(default_factory=APISettings)
    worker: WorkerSettings = Field(default_factory=WorkerSettings)
    database: DatabaseSettings
    redis: RedisQueueSettings
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    jwt: JwtSettings
    registry: RegistrySettings = Field(default_factory=RegistrySettings)
    github: GitHubSettings = Field(default_factory=GitHubSettings)
    k8s: K8sSettings = Field(default_factory=K8sSettings)

    @property
    def use_json_logs(self) -> bool:
        if self.json_logs is not None:
            return self.json_logs
        return self.env != "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test-only helper to drop the cached Settings instance."""
    get_settings.cache_clear()
