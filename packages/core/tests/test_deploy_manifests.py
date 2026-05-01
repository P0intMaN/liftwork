from __future__ import annotations

from liftwork_core.build.config import (
    DeploySpec,
    HealthCheck,
    IngressSpec,
    ResourceQuantity,
    Resources,
)
from liftwork_core.deploy import (
    DeployRequest,
    DeployTarget,
    build_all_manifests,
    build_deployment_manifest,
    build_ingress_manifest,
    build_service_manifest,
    resource_name,
)


def _make_request(**overrides: object) -> DeployRequest:
    base: dict[str, object] = {
        "target": DeployTarget(cluster_name="kind-kubedeploy-dev", namespace="acme"),
        "application_slug": "acme-api",
        "application_id": "11111111-2222-3333-4444-555555555555",
        "image_ref": "ghcr.io/acme/api@sha256:" + "a" * 64,
        "image_digest": "sha256:" + "a" * 64,
        "image_tag": "main-abc1234",
        "deploy_spec": DeploySpec(
            port=8080,
            replicas=2,
            env={"LOG_LEVEL": "INFO"},
            resources=Resources(
                requests=ResourceQuantity(cpu="200m", memory="256Mi"),
                limits=ResourceQuantity(cpu="1", memory="512Mi"),
            ),
            health_check=HealthCheck(path="/healthz", initial_delay_seconds=3, period_seconds=5),
        ),
        "revision": 7,
        "commit_sha": "abc1234567890",
        "branch": "main",
        "image_pull_secret": "liftwork-registry-creds",
    }
    base.update(overrides)
    return DeployRequest(**base)  # type: ignore[arg-type]


def test_resource_name_is_dns_safe() -> None:
    assert resource_name("My App!") == "my-app"
    assert len(resource_name("x" * 100)) <= 63


def test_deployment_manifest_top_level_shape() -> None:
    req = _make_request()
    m = build_deployment_manifest(req)
    assert m["apiVersion"] == "apps/v1"
    assert m["kind"] == "Deployment"
    assert m["metadata"]["name"] == "acme-api"
    assert m["metadata"]["namespace"] == "acme"
    assert m["metadata"]["annotations"]["liftwork.io/revision"] == "7"
    assert m["metadata"]["annotations"]["liftwork.io/image-digest"].startswith("sha256:")


def test_deployment_strategy_is_zero_downtime() -> None:
    m = build_deployment_manifest(_make_request())
    strategy = m["spec"]["strategy"]
    assert strategy["type"] == "RollingUpdate"
    assert strategy["rollingUpdate"]["maxUnavailable"] == 0
    assert strategy["rollingUpdate"]["maxSurge"] == "25%"


def test_deployment_container_security_and_probes() -> None:
    m = build_deployment_manifest(_make_request())
    container = m["spec"]["template"]["spec"]["containers"][0]
    assert container["image"].endswith("@sha256:" + "a" * 64)
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
    }
    assert container["readinessProbe"]["httpGet"] == {"path": "/healthz", "port": "http"}
    assert container["readinessProbe"]["initialDelaySeconds"] == 3
    assert container["livenessProbe"]["initialDelaySeconds"] == 6  # 2x readiness
    assert container["resources"]["requests"] == {"cpu": "200m", "memory": "256Mi"}
    assert container["resources"]["limits"] == {"cpu": "1", "memory": "512Mi"}
    assert container["env"] == [{"name": "LOG_LEVEL", "value": "INFO"}]


def test_deployment_pod_security_and_pull_secret() -> None:
    m = build_deployment_manifest(_make_request())
    pod_spec = m["spec"]["template"]["spec"]
    assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["imagePullSecrets"] == [{"name": "liftwork-registry-creds"}]


def test_deployment_selector_matches_pod_labels() -> None:
    m = build_deployment_manifest(_make_request())
    selector = m["spec"]["selector"]["matchLabels"]
    pod_labels = m["spec"]["template"]["metadata"]["labels"]
    for k, v in selector.items():
        assert pod_labels.get(k) == v


def test_service_manifest_targets_named_port() -> None:
    m = build_service_manifest(_make_request())
    assert m["apiVersion"] == "v1"
    assert m["kind"] == "Service"
    assert m["spec"]["type"] == "ClusterIP"
    assert m["spec"]["ports"][0] == {
        "name": "http",
        "port": 80,
        "targetPort": "http",
        "protocol": "TCP",
    }


def test_ingress_disabled_returns_none() -> None:
    assert build_ingress_manifest(_make_request()) is None


def test_ingress_enabled_emits_full_spec() -> None:
    req = _make_request(
        deploy_spec=DeploySpec(
            port=8080,
            replicas=2,
            ingress=IngressSpec(
                enabled=True,
                host="api.example.com",
                class_name="nginx",
                annotations={"nginx.ingress.kubernetes.io/proxy-body-size": "8m"},
                tls_secret_name="api-tls",
            ),
        ),
    )
    m = build_ingress_manifest(req)
    assert m is not None
    assert m["apiVersion"] == "networking.k8s.io/v1"
    assert m["spec"]["ingressClassName"] == "nginx"
    rule = m["spec"]["rules"][0]
    assert rule["host"] == "api.example.com"
    assert rule["http"]["paths"][0]["backend"]["service"]["name"] == "acme-api"
    assert m["spec"]["tls"] == [{"hosts": ["api.example.com"], "secretName": "api-tls"}]
    assert "nginx.ingress.kubernetes.io/proxy-body-size" in m["metadata"]["annotations"]


def test_build_all_manifests_skips_disabled_ingress() -> None:
    manifests = build_all_manifests(_make_request())
    kinds = [m["kind"] for m in manifests]
    assert kinds == ["Deployment", "Service"]


def test_build_all_manifests_includes_enabled_ingress() -> None:
    req = _make_request(
        deploy_spec=DeploySpec(
            port=8080,
            replicas=1,
            ingress=IngressSpec(enabled=True, host="api.example.com"),
        ),
    )
    manifests = build_all_manifests(req)
    kinds = [m["kind"] for m in manifests]
    assert kinds == ["Deployment", "Service", "Ingress"]
