"""Helm-template smoke tests.

We don't snapshot full YAML (too noisy on chart-version bumps); instead
we assert each release shape we care about so accidental
breakages — wrong namespace, missing component, schema regressions —
fail loudly. Skipped silently if `helm` isn't on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART_DIR = Path(__file__).resolve().parent.parent

_REQUIRED_BASE_VALUES = [
    "--set",
    "secrets.jwtSecret=test-secret-32-bytes-or-more-please-please-please",
    "--set",
    "externalDatabase.url=postgresql+asyncpg://x",
    "--set",
    "externalRedis.url=redis://x",
    "--set",
    "registry.host=registry.local",
]


def _have_helm() -> bool:
    return shutil.which("helm") is not None


def _render(*extra_values: str, namespace: str = "lw") -> list[dict]:
    args = [
        "helm", "template", "lw", str(CHART_DIR),
        "--namespace", namespace,
        *_REQUIRED_BASE_VALUES,
        *extra_values,
    ]
    out = subprocess.run(args, check=True, capture_output=True, text=True)  # noqa: S603
    return [d for d in yaml.safe_load_all(out.stdout) if d]


pytestmark = pytest.mark.skipif(not _have_helm(), reason="helm CLI not available")


def test_minimal_install_renders_all_three_workloads() -> None:
    docs = _render()
    deployments = {d["metadata"]["name"] for d in docs if d.get("kind") == "Deployment"}
    assert deployments == {"lw-api", "lw-worker", "lw-dashboard"}


def test_namespace_is_propagated_via_helm_namespace_flag() -> None:
    docs = _render(namespace="custom-tenant")
    namespaces = {d["metadata"].get("namespace") for d in docs if "metadata" in d}
    namespaces.discard(None)
    assert namespaces == {"custom-tenant"}


def test_namespace_value_overrides_release_namespace() -> None:
    docs = _render("--set", "namespace=app-alpha", namespace="install-target")
    namespaces = {d["metadata"].get("namespace") for d in docs if "metadata" in d}
    namespaces.discard(None)
    assert namespaces == {"app-alpha"}


def test_namespace_resource_emitted_when_namespaceCreate() -> None:
    docs = _render(
        "--set", "namespace=t1",
        "--set", "namespaceCreate=true",
    )
    kinds = [d["kind"] for d in docs]
    assert "Namespace" in kinds
    ns = next(d for d in docs if d["kind"] == "Namespace")
    assert ns["metadata"]["name"] == "t1"


def test_migrate_job_is_a_helm_hook() -> None:
    docs = _render()
    jobs = [d for d in docs if d.get("kind") == "Job"]
    assert len(jobs) == 1
    annotations = jobs[0]["metadata"].get("annotations", {})
    assert annotations.get("helm.sh/hook") == "pre-install,pre-upgrade"


def test_servicemonitor_only_when_enabled() -> None:
    off = _render()
    assert not [d for d in off if d.get("kind") == "ServiceMonitor"]
    on = _render("--set", "serviceMonitor.enabled=true")
    sms = [d for d in on if d.get("kind") == "ServiceMonitor"]
    assert {sm["metadata"]["name"] for sm in sms} == {"lw-api", "lw-worker"}


def test_ingress_only_when_enabled() -> None:
    off = _render()
    assert not [d for d in off if d.get("kind") == "Ingress"]
    on = _render("--set", "ingress.enabled=true", "--set", "ingress.host=lw.example.com")
    ingresses = [d for d in on if d.get("kind") == "Ingress"]
    assert len(ingresses) == 1
    rules = ingresses[0]["spec"]["rules"]
    paths = [p["path"] for p in rules[0]["http"]["paths"]]
    assert "/api(/|$)(.*)" in paths
    assert "/" in paths


def test_secret_required_unless_existingSecret() -> None:
    """Install fails fast when neither secrets.jwtSecret nor existingSecret is set."""
    args = [
        "helm", "template", "lw", str(CHART_DIR),
        "--set", "externalDatabase.url=postgresql+asyncpg://x",
        "--set", "externalRedis.url=redis://x",
        "--set", "registry.host=registry.local",
    ]
    result = subprocess.run(args, check=False, capture_output=True, text=True)  # noqa: S603
    assert result.returncode != 0
    assert "secrets.jwtSecret is required" in result.stderr


def test_existingSecret_skips_chart_managed_secret() -> None:
    docs = _render("--set", "secrets.existingSecret=my-external-secret")
    secret_names = [d["metadata"]["name"] for d in docs if d.get("kind") == "Secret"]
    assert "lw-secrets" not in secret_names
    # Confirm the Deployments reference the external one.
    api_deploy = next(
        d for d in docs
        if d.get("kind") == "Deployment" and d["metadata"]["name"] == "lw-api"
    )
    env_from = api_deploy["spec"]["template"]["spec"]["containers"][0]["envFrom"]
    secret_refs = [e["secretRef"]["name"] for e in env_from if "secretRef" in e]
    assert "my-external-secret" in secret_refs


def test_worker_uses_recreate_strategy() -> None:
    docs = _render()
    worker = next(
        d for d in docs
        if d.get("kind") == "Deployment" and d["metadata"]["name"] == "lw-worker"
    )
    assert worker["spec"]["strategy"]["type"] == "Recreate"


def test_values_schema_is_valid_json() -> None:
    schema_path = CHART_DIR / "values.schema.json"
    json.loads(schema_path.read_text(encoding="utf-8"))
