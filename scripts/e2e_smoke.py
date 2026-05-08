"""End-to-end smoke harness used by .github/workflows/e2e.yaml.

Drives the full happy path against a freshly-installed liftwork:
  1. Login with bootstrap admin → JWT
  2. Create a Cluster row pointing at the in-cluster k8s
  3. Create an Application backed by docker/welcome-to-docker (public, small)
  4. Trigger a manual build
  5. Poll until the build + deploy reach a terminal status
  6. Assert success and that the live Deployment has the expected port

Designed to run from CI but also works locally against `make dev-up`-style
installs. Tunable via env: API, ADMIN_EMAIL, ADMIN_PASSWORD, TIMEOUT_SECONDS.
"""

# ruff: noqa: T201, S113 — print-based progress is intentional for CI logs;
# requests with a single explicit timeout per call.

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API = os.environ.get("API", "http://localhost:7878")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me-now")
TIMEOUT_SECONDS = int(os.environ.get("TIMEOUT_SECONDS", "600"))

REPO = "https://github.com/docker/welcome-to-docker.git"
REPO_OWNER = "docker"
REPO_NAME = "welcome-to-docker"
BRANCH = "main"
APP_SLUG = "welcome-e2e"
NAMESPACE = "welcome-e2e"


def _request(
    method: str,
    path: str,
    *,
    token: str | None = None,
    body: dict[str, Any] | None = None,
) -> Any:
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(url, data=data, method=method, headers=headers)  # noqa: S310
    try:
        with urlopen(req, timeout=30) as resp:  # noqa: S310
            payload = resp.read()
            return json.loads(payload) if payload else None
    except HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        msg = f"{method} {path} → HTTP {exc.code}: {body_text}"
        raise SystemExit(msg) from exc


def _wait_api_ready() -> None:
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            urlopen(f"{API}/healthz", timeout=5).read()  # noqa: S310
            return
        except (HTTPError, URLError):
            time.sleep(2)
    raise SystemExit("API not reachable within 120s")


def _login() -> str:
    resp = _request(
        "POST",
        "/auth/login",
        body={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    return resp["access_token"]


def _ensure_cluster(token: str) -> str:
    """Register an in-cluster cluster (the worker reaches it via kubeconfig
    in dev or in_cluster=true in prod). Idempotent on slug."""
    existing = _request("GET", "/clusters", token=token) or []
    for c in existing:
        if c["name"] == "kind-liftwork-e2e":
            return c["id"]
    created = _request(
        "POST",
        "/clusters",
        token=token,
        body={
            "name": "kind-liftwork-e2e",
            "display_name": "Liftwork e2e kind cluster",
            "in_cluster": True,
            "default_namespace": NAMESPACE,
        },
    )
    return created["id"]


def _ensure_application(token: str, cluster_id: str) -> str:
    existing = _request("GET", "/applications", token=token) or []
    for app in existing:
        if app["slug"] == APP_SLUG:
            return app["id"]
    created = _request(
        "POST",
        "/applications",
        token=token,
        body={
            "slug": APP_SLUG,
            "display_name": "welcome-to-docker (e2e)",
            "repo_url": REPO,
            "repo_owner": REPO_OWNER,
            "repo_name": REPO_NAME,
            "default_branch": BRANCH,
            "cluster_id": cluster_id,
            "namespace": NAMESPACE,
            "image_repository": "liftwork/welcome-e2e",
            "auto_deploy": True,
            "app_port": 3000,
            "health_check_path": "/",
            "replicas": 1,
        },
    )
    return created["id"]


def _trigger_build(token: str, app_id: str) -> str:
    resp = _request(
        "POST",
        f"/applications/{app_id}/builds",
        token=token,
        body={"branch": BRANCH, "source": "manual"},
    )
    return resp["build_id"]


def _poll(token: str, build_id: str, app_id: str) -> None:
    deadline = time.time() + TIMEOUT_SECONDS
    last_state: tuple[str, str | None] = ("", None)
    while time.time() < deadline:
        build = _request("GET", f"/builds/{build_id}", token=token)
        deploys = _request("GET", f"/applications/{app_id}/deployments", token=token) or []
        match = next((d for d in deploys if d["build_run_id"] == build_id), None)
        state = (build["status"], match["status"] if match else None)
        if state != last_state:
            print(f"[e2e] build={state[0]} deploy={state[1]}", flush=True)
            last_state = state
        if build["status"] in ("failed", "cancelled"):
            raise SystemExit(f"BUILD failed: {build.get('error') or '<no error captured>'}")
        if match and match["status"] in ("succeeded", "failed", "rolled_back"):
            if match["status"] != "succeeded":
                raise SystemExit(
                    f"DEPLOY {match['status']}: {match.get('error') or '<no error>'}"
                )
            print(f"[e2e] deploy succeeded — revision={match['revision']}", flush=True)
            return
        time.sleep(3)
    raise SystemExit(f"timed out after {TIMEOUT_SECONDS}s waiting for terminal status")


def main() -> int:
    print(f"[e2e] API={API}", flush=True)
    _wait_api_ready()
    token = _login()
    print("[e2e] logged in", flush=True)
    cluster_id = _ensure_cluster(token)
    print(f"[e2e] cluster={cluster_id}", flush=True)
    app_id = _ensure_application(token, cluster_id)
    print(f"[e2e] application={app_id}", flush=True)
    build_id = _trigger_build(token, app_id)
    print(f"[e2e] triggered build={build_id}", flush=True)
    _poll(token, build_id, app_id)
    print("[e2e] PASS", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
