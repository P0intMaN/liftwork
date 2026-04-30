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
    # Executor selection. "mock" for unit tests + first-run dev; "kind"
    # wires the real BuildKit-in-pod + K8s server-side-apply executors
    # against the cluster identified by `k8s.kube_context` /
    # `k8s.in_cluster`.
    executor: Literal["mock", "kind"] = "mock"
    builder_namespace: str = "liftwork"
    builder_service_account: str = "liftwork-builder"
    deploy_field_manager: str = "liftwork-controller"


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
    insecure: bool = False  # set true for the dev in-cluster `registry:2`


class GitHubAppSettings(BaseModel):
    app_id: str | None = None
    private_key: SecretStr | None = None  # full PEM contents
    webhook_secret: SecretStr | None = None
    installation_id: int | None = None  # optional default

    @property
    def is_configured(self) -> bool:
        return all((self.app_id, self.private_key, self.webhook_secret))


class K8sSettings(BaseModel):
    kube_context: str | None = None
    in_cluster: bool = False


class BootstrapSettings(BaseModel):
    """Optional first-run admin seeding. Both fields required to take effect."""

    admin_email: str | None = None
    admin_password: SecretStr | None = None


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
    github: GitHubAppSettings = Field(default_factory=GitHubAppSettings)
    k8s: K8sSettings = Field(default_factory=K8sSettings)
    bootstrap: BootstrapSettings = Field(default_factory=BootstrapSettings)

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
