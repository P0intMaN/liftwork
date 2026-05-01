#!/usr/bin/env bash
# Wipes any prior welcome-app + acme-api leftovers, registers welcome-app
# against the existing kind cluster row, and triggers a build. The
# dashboard auto-refreshes — open it and watch the cards/charts/feed light
# up over the next ~60 seconds.
set -euo pipefail

ADMIN_EMAIL="admin@example.com"
ADMIN_PW="change-me-now"
APP_NS="welcome-app"
KCTX="kind-kubedeploy-dev"

TOKEN=$(curl -s -X POST http://localhost:7878/auth/login \
  -H 'content-type: application/json' \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PW}\"}" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
echo "token len=${#TOKEN}"

echo "▶ ensuring kind ns exists"
kubectl --context "${KCTX}" create namespace "${APP_NS}" 2>/dev/null || true

echo "▶ wiping existing application rows (acme-api / welcome-app stubs)"
curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/applications \
  | python3 -c '
import sys, json
for x in json.load(sys.stdin):
    if x["slug"] in ("acme-api", "welcome-app"):
        print(x["id"])' | while read -r appid; do
  curl -s -X DELETE -H "Authorization: Bearer ${TOKEN}" \
    "http://localhost:7878/applications/${appid}" >/dev/null
done

echo "▶ resolving cluster id"
CLUSTER_ID=$(curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/clusters \
  | python3 -c '
import sys, json
for x in json.load(sys.stdin):
    if x["name"] == "kind-kubedeploy-dev":
        print(x["id"]); break')
if [[ -z "${CLUSTER_ID}" ]]; then
  echo "✗ no kind-kubedeploy-dev cluster registered. Open the dashboard → Clusters → Register cluster."
  exit 1
fi
echo "  cluster_id=${CLUSTER_ID}"

echo "▶ creating welcome-app"
APP_ID=$(curl -s -X POST http://localhost:7878/applications \
  -H "Authorization: Bearer ${TOKEN}" -H 'content-type: application/json' \
  -d "{
    \"slug\":\"welcome-app\",
    \"display_name\":\"Welcome to Docker\",
    \"repo_url\":\"https://github.com/docker/welcome-to-docker.git\",
    \"repo_owner\":\"docker\",
    \"repo_name\":\"welcome-to-docker\",
    \"default_branch\":\"main\",
    \"cluster_id\":\"${CLUSTER_ID}\",
    \"namespace\":\"${APP_NS}\",
    \"image_repository\":\"liftwork/welcome-app\",
    \"auto_deploy\":true,
    \"app_port\":3000,
    \"health_check_path\":\"/\",
    \"replicas\":1
  }" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')
echo "  app_id=${APP_ID}"

echo "▶ triggering build"
BUILD_ID=$(curl -s -X POST -H "Authorization: Bearer ${TOKEN}" \
  "http://localhost:7878/applications/${APP_ID}/builds" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["build_id"])')
echo "  build_id=${BUILD_ID}"

echo
echo "✓ open the dashboard now: http://localhost:5173"
echo "  Overview will show the build go queued → running → succeeded"
echo "  Click Applications → Welcome to Docker → the build to watch live logs"
