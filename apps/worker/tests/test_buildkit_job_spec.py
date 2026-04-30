from __future__ import annotations

from liftwork_worker.executors.buildkit_pod import (
    DEFAULT_BUILDKIT_IMAGE,
    DIGEST_MARKER,
    JobSpecInputs,
    build_buildkit_job_spec,
    parse_digest,
)


def test_parse_digest_picks_marker_line() -> None:
    line = f"some preamble {DIGEST_MARKER}sha256:" + "a" * 64 + " trailing"
    assert parse_digest(line) == "sha256:" + "a" * 64


def test_parse_digest_returns_none_for_unrelated() -> None:
    assert parse_digest("nothing to see here") is None
    assert parse_digest("sha256:abc") is None  # too short, no marker


def test_job_spec_top_level_shape() -> None:
    inputs = JobSpecInputs(
        build_id="20260430-abc1234",
        repo_url="https://github.com/acme/api.git",
        branch="main",
        dockerfile_configmap="liftwork-build-20260430-abc1234-dockerfile",
        image_ref="ghcr.io/acme/api:main-abc1234",
        cache_ref="ghcr.io/acme/api:buildcache",
    )
    spec = build_buildkit_job_spec(inputs)

    assert spec["apiVersion"] == "batch/v1"
    assert spec["kind"] == "Job"
    assert spec["metadata"]["name"].startswith("liftwork-build-20260430-abc1234")
    assert spec["metadata"]["labels"]["liftwork.io/build-id"] == "20260430-abc1234"

    pod_spec = spec["spec"]["template"]["spec"]
    assert pod_spec["restartPolicy"] == "Never"
    assert pod_spec["serviceAccountName"] == "liftwork-builder"
    assert pod_spec["automountServiceAccountToken"] is False


def test_job_spec_emits_init_container_for_git_clone() -> None:
    inputs = JobSpecInputs(
        build_id="b1",
        repo_url="https://github.com/acme/api.git",
        branch="release/v2",
        dockerfile_configmap="cm-b1",
        image_ref="ghcr.io/acme/api:v2-deadbee",
    )
    spec = build_buildkit_job_spec(inputs)
    init = spec["spec"]["template"]["spec"]["initContainers"][0]
    assert init["name"] == "git-clone"
    assert init["image"].startswith("alpine/git:")
    assert "release/v2" in init["args"][0]
    assert init["securityContext"]["runAsNonRoot"] is True


def test_job_spec_main_container_runs_buildctl_and_emits_digest() -> None:
    inputs = JobSpecInputs(
        build_id="b1",
        repo_url="https://github.com/acme/api.git",
        branch="main",
        dockerfile_configmap="cm-b1",
        image_ref="ghcr.io/acme/api:main-abc",
        cache_ref="ghcr.io/acme/api:buildcache",
    )
    spec = build_buildkit_job_spec(inputs)
    main = spec["spec"]["template"]["spec"]["containers"][0]
    assert main["name"] == "buildkit"
    assert main["image"] == DEFAULT_BUILDKIT_IMAGE

    cmd = main["command"]
    assert cmd[0] == "sh"
    full_script = cmd[-1]
    assert "buildctl-daemonless.sh" in full_script
    assert "--frontend=dockerfile.v0" in full_script
    assert "--output=type=image,name=ghcr.io/acme/api:main-abc,push=true" in full_script
    assert "--export-cache=type=registry,ref=ghcr.io/acme/api:buildcache,mode=max" in full_script
    assert DIGEST_MARKER in full_script

    sec_ctx = main["securityContext"]
    assert sec_ctx["runAsNonRoot"] is True
    assert sec_ctx["runAsUser"] == 1000
    assert sec_ctx["allowPrivilegeEscalation"] is False


def test_job_spec_mounts_dockerfile_and_registry_creds() -> None:
    inputs = JobSpecInputs(
        build_id="b1",
        repo_url="https://github.com/acme/api.git",
        branch="main",
        dockerfile_configmap="my-cm",
        image_ref="ghcr.io/acme/api:main-abc",
        registry_secret_name="my-creds",
    )
    spec = build_buildkit_job_spec(inputs)
    volumes = {v["name"]: v for v in spec["spec"]["template"]["spec"]["volumes"]}
    assert volumes["dockerfile"]["configMap"]["name"] == "my-cm"
    assert volumes["docker-config"]["secret"]["secretName"] == "my-creds"
    assert "workspace" in volumes
    assert "buildkit-cache" in volumes


def test_job_spec_insecure_skips_secret_and_adds_flag() -> None:
    """Dev-mode in-cluster registry: no docker-config Secret, push over HTTP."""
    spec = build_buildkit_job_spec(
        JobSpecInputs(
            build_id="b1",
            repo_url="https://github.com/acme/api.git",
            branch="main",
            dockerfile_configmap="cm-b1",
            image_ref="registry.liftwork.svc.cluster.local:5000/acme/api:main-abc",
            registry_insecure=True,
        )
    )
    pod_spec = spec["spec"]["template"]["spec"]
    volume_names = {v["name"] for v in pod_spec["volumes"]}
    assert "docker-config" not in volume_names
    assert "dockerfile" in volume_names
    assert "buildkit-cache" in volume_names

    main = pod_spec["containers"][0]
    mount_names = {m["name"] for m in main["volumeMounts"]}
    assert "docker-config" not in mount_names

    full_script = main["command"][-1]
    assert (
        "--output=type=image,"
        "name=registry.liftwork.svc.cluster.local:5000/acme/api:main-abc,"
        "push=true,registry.insecure=true"
    ) in full_script

    env_names = {e["name"] for e in main["env"]}
    assert "DOCKER_CONFIG" not in env_names


def test_job_spec_name_is_truncated_and_dns_safe() -> None:
    very_long_id = "x" * 200
    spec = build_buildkit_job_spec(
        JobSpecInputs(
            build_id=very_long_id,
            repo_url="https://github.com/acme/api.git",
            branch="main",
            dockerfile_configmap="cm",
            image_ref="ghcr.io/acme/api:main-abc",
        )
    )
    name = spec["metadata"]["name"]
    assert len(name) <= 63
    assert all(c.isalnum() or c == "-" for c in name)
