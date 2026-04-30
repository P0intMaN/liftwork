"""`liftwork.yaml` schema — committed at the root of a target repo.

Every field is optional. liftwork resolves defaults from language
detection. Users that need control commit a `liftwork.yaml`; users that
need full control commit their own `Dockerfile`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from liftwork_core.build.language import Language


class BuildSpec(BaseModel):
    dockerfile: str | None = None  # path inside repo to a hand-authored Dockerfile
    context: str = "."
    args: dict[str, str] = Field(default_factory=dict)
    target: str | None = None
    cache_from: list[str] = Field(default_factory=list)
    extra_files: list[str] = Field(default_factory=list)


class ResourceQuantity(BaseModel):
    cpu: str = "100m"
    memory: str = "128Mi"


class Resources(BaseModel):
    requests: ResourceQuantity = Field(default_factory=ResourceQuantity)
    limits: ResourceQuantity | None = None


class HealthCheck(BaseModel):
    path: str = "/healthz"
    initial_delay_seconds: int = 5
    period_seconds: int = 10


class IngressSpec(BaseModel):
    enabled: bool = False
    host: str | None = None
    class_name: str | None = None
    annotations: dict[str, str] = Field(default_factory=dict)
    tls_secret_name: str | None = None


class DeploySpec(BaseModel):
    port: int = 8080
    replicas: int = 1
    command: list[str] | None = None
    env: dict[str, str] = Field(default_factory=dict)
    resources: Resources = Field(default_factory=Resources)
    health_check: HealthCheck = Field(default_factory=HealthCheck)
    ingress: IngressSpec = Field(default_factory=IngressSpec)


class LiftworkConfig(BaseModel):
    version: Literal["1"] = "1"
    language: Language | None = None
    build: BuildSpec = Field(default_factory=BuildSpec)
    deploy: DeploySpec = Field(default_factory=DeploySpec)


class LiftworkConfigError(Exception):
    """Raised when `liftwork.yaml` exists but cannot be parsed."""


def load_liftwork_config(path: Path | str) -> LiftworkConfig | None:
    """Load `liftwork.yaml` from disk; return None if it doesn't exist.

    Raises `LiftworkConfigError` for unparseable / invalid YAML.
    """
    p = Path(path)
    if not p.exists():
        return None
    try:
        raw: Any = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"liftwork.yaml is not valid YAML: {exc}"
        raise LiftworkConfigError(msg) from exc

    if raw is None:
        return LiftworkConfig()
    if not isinstance(raw, dict):
        msg = f"liftwork.yaml must be a mapping at the root, got {type(raw).__name__}"
        raise LiftworkConfigError(msg)

    try:
        return LiftworkConfig.model_validate(raw)
    except ValidationError as exc:
        msg = f"liftwork.yaml failed validation: {exc}"
        raise LiftworkConfigError(msg) from exc
