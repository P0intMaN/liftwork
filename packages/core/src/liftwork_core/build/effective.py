"""Compute the *effective* DeploySpec for a build.

Resolution order, lowest priority first:
  1. Build-time inferred defaults (`infer_deploy_defaults` — language /
     EXPOSE based)
  2. Application columns (`app_port`, `health_check_path`, `replicas`) —
     legacy fallback for builds that predate inferred defaults
  3. `liftwork.yaml` `deploy:` block — file wins

The merge happens at the *raw dict* level (yaml → deep_merge → validate)
rather than at the Pydantic-model level, because Pydantic's `model_copy`
replaces nested fields wholesale; users almost always want field-level
overrides (e.g. `health_check.path` only) instead of having to restate
the whole `health_check` block.
"""

from __future__ import annotations

from typing import Any, Protocol

import yaml

from liftwork_core.build.config import (
    DeploySpec,
    HealthCheck,
    LiftworkConfig,
    LiftworkConfigError,
)
from liftwork_core.build.defaults import DeployDefaults


class _ApplicationLike(Protocol):
    """Subset of `liftwork_core.db.models.Application` that we read."""

    app_port: int
    health_check_path: str
    replicas: int


def effective_deploy_spec(
    *,
    application: _ApplicationLike,
    inferred_defaults: DeployDefaults | None,
    liftwork_yaml: str | None,
) -> DeploySpec:
    """Return the DeploySpec the deploy job should actually use.

    `inferred_defaults` come from `infer_deploy_defaults(workspace)` at
    build time. When None (legacy builds), fall back to the Application
    row's columns to preserve backwards-compat.
    """
    if inferred_defaults is not None:
        base: dict[str, Any] = {
            "port": inferred_defaults.port,
            "replicas": application.replicas,
            "health_check": {"path": inferred_defaults.health_check_path},
        }
    else:
        base = {
            "port": application.app_port,
            "replicas": application.replicas,
            "health_check": {"path": application.health_check_path},
        }

    if not liftwork_yaml or not liftwork_yaml.strip():
        return DeploySpec.model_validate(base)

    try:
        raw = yaml.safe_load(liftwork_yaml) or {}
    except yaml.YAMLError as exc:
        msg = f"liftwork.yaml is not valid YAML: {exc}"
        raise LiftworkConfigError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"liftwork.yaml must be a mapping at the root, got {type(raw).__name__}"
        raise LiftworkConfigError(msg)

    deploy_overrides = raw.get("deploy") or {}
    if not isinstance(deploy_overrides, dict):
        msg = "liftwork.yaml: `deploy` must be a mapping"
        raise LiftworkConfigError(msg)

    merged = _deep_merge(base, deploy_overrides)
    return DeploySpec.model_validate(merged)


def parse_liftwork_yaml(text: str | None) -> LiftworkConfig | None:
    """Validate the raw text into a LiftworkConfig (used at build time)."""
    if not text or not text.strip():
        return None
    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        msg = f"liftwork.yaml is not valid YAML: {exc}"
        raise LiftworkConfigError(msg) from exc
    if not isinstance(raw, dict):
        msg = f"liftwork.yaml must be a mapping at the root, got {type(raw).__name__}"
        raise LiftworkConfigError(msg)
    try:
        return LiftworkConfig.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError + descendants
        msg = f"liftwork.yaml failed validation: {exc}"
        raise LiftworkConfigError(msg) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `override` onto `base`, mutating nothing.

    Lists and scalars in `override` replace whatever was in `base`. Only
    dicts are walked into. This matches the user mental model of "patch
    the field I named, leave the rest alone."
    """
    result: dict[str, Any] = dict(base)
    for k, v in override.items():
        existing = result.get(k)
        if isinstance(existing, dict) and isinstance(v, dict):
            result[k] = _deep_merge(existing, v)
        else:
            result[k] = v
    return result


# Re-export so the worker can build a fallback HealthCheck without an
# extra import.
__all__ = ["HealthCheck", "effective_deploy_spec", "parse_liftwork_yaml"]
