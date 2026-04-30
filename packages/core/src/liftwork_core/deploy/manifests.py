"""Pure functions that build Kubernetes manifests for a deploy request.

All manifests are returned as plain dicts so the executor can hand them
straight to a server-side-apply patch and tests can snapshot them
without spinning up a cluster.
"""

from __future__ import annotations

import re
from typing import Any

from liftwork_core.deploy.labels import (
    base_annotations,
    base_labels,
    selector_labels,
)
from liftwork_core.deploy.protocols import DeployRequest

_DNS_LABEL_RE = re.compile(r"[^a-z0-9-]+")


def resource_name(app_slug: str, *, suffix: str = "") -> str:
    """Coerce `app_slug[-suffix]` into a DNS-1123-safe k8s name."""
    base = _DNS_LABEL_RE.sub("-", app_slug.lower()).strip("-")
    full = f"{base}-{suffix}" if suffix else base
    return full[:63].rstrip("-")


def build_deployment_manifest(req: DeployRequest) -> dict[str, Any]:
    name = resource_name(req.application_slug)
    spec = req.deploy_spec
    labels = base_labels(
        app_slug=req.application_slug,
        application_id=req.application_id,
        image_tag=req.image_tag,
    )
    annotations = base_annotations(
        revision=req.revision,
        commit_sha=req.commit_sha,
        branch=req.branch,
        image_digest=req.image_digest,
    )

    container: dict[str, Any] = {
        "name": "app",
        "image": req.image_ref,
        "imagePullPolicy": "IfNotPresent",
        "ports": [
            {
                "name": "http",
                "containerPort": spec.port,
                "protocol": "TCP",
            }
        ],
        "env": [{"name": k, "value": v} for k, v in spec.env.items()],
        "resources": {
            "requests": {
                "cpu": spec.resources.requests.cpu,
                "memory": spec.resources.requests.memory,
            },
        },
        "readinessProbe": {
            "httpGet": {"path": spec.health_check.path, "port": "http"},
            "initialDelaySeconds": spec.health_check.initial_delay_seconds,
            "periodSeconds": spec.health_check.period_seconds,
        },
        "livenessProbe": {
            "httpGet": {"path": spec.health_check.path, "port": "http"},
            "initialDelaySeconds": spec.health_check.initial_delay_seconds * 2,
            "periodSeconds": spec.health_check.period_seconds * 2,
        },
        "securityContext": {
            "runAsNonRoot": True,
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        },
    }

    if spec.resources.limits is not None:
        container["resources"]["limits"] = {
            "cpu": spec.resources.limits.cpu,
            "memory": spec.resources.limits.memory,
        }

    if spec.command:
        container["command"] = list(spec.command)

    pod_spec: dict[str, Any] = {
        "containers": [container],
        "securityContext": {
            "runAsNonRoot": True,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "automountServiceAccountToken": False,
    }
    if req.image_pull_secret:
        pod_spec["imagePullSecrets"] = [{"name": req.image_pull_secret}]

    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": req.target.namespace,
            "labels": labels,
            "annotations": annotations,
        },
        "spec": {
            "replicas": spec.replicas,
            "revisionHistoryLimit": 5,
            "selector": {"matchLabels": selector_labels(req.application_slug)},
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": "25%", "maxUnavailable": 0},
            },
            "template": {
                "metadata": {
                    "labels": labels | selector_labels(req.application_slug),
                    "annotations": annotations,
                },
                "spec": pod_spec,
            },
        },
    }


def build_service_manifest(req: DeployRequest) -> dict[str, Any]:
    name = resource_name(req.application_slug)
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": name,
            "namespace": req.target.namespace,
            "labels": base_labels(
                app_slug=req.application_slug,
                application_id=req.application_id,
                image_tag=req.image_tag,
            ),
        },
        "spec": {
            "type": "ClusterIP",
            "selector": selector_labels(req.application_slug),
            "ports": [
                {
                    "name": "http",
                    "port": 80,
                    "targetPort": "http",
                    "protocol": "TCP",
                }
            ],
        },
    }


def build_ingress_manifest(req: DeployRequest) -> dict[str, Any] | None:
    ingress = req.deploy_spec.ingress
    if not ingress.enabled or not ingress.host:
        return None

    name = resource_name(req.application_slug)
    service_name = name
    rule: dict[str, Any] = {
        "host": ingress.host,
        "http": {
            "paths": [
                {
                    "path": "/",
                    "pathType": "Prefix",
                    "backend": {
                        "service": {"name": service_name, "port": {"number": 80}},
                    },
                }
            ]
        },
    }

    spec: dict[str, Any] = {"rules": [rule]}
    if ingress.class_name:
        spec["ingressClassName"] = ingress.class_name
    if ingress.tls_secret_name:
        spec["tls"] = [{"hosts": [ingress.host], "secretName": ingress.tls_secret_name}]

    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "Ingress",
        "metadata": {
            "name": name,
            "namespace": req.target.namespace,
            "labels": base_labels(
                app_slug=req.application_slug,
                application_id=req.application_id,
                image_tag=req.image_tag,
            ),
            "annotations": ingress.annotations or {},
        },
        "spec": spec,
    }


def build_all_manifests(req: DeployRequest) -> list[dict[str, Any]]:
    """Return every manifest required for one deploy, in apply order."""
    out: list[dict[str, Any]] = [
        build_deployment_manifest(req),
        build_service_manifest(req),
    ]
    ingress = build_ingress_manifest(req)
    if ingress is not None:
        out.append(ingress)
    return out
