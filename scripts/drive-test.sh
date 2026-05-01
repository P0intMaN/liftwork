#!/usr/bin/env bash
# Drives a build through an already-running API+worker. Used by
# e2e-demo.sh and runnable standalone for quick reruns.
set -euo pipefail

ADMIN_EMAIL="${LIFTWORK_BOOTSTRAP__ADMIN_EMAIL:-admin@example.com}"
ADMIN_PW="${LIFTWORK_BOOTSTRAP__ADMIN_PASSWORD:-change-me-now}"
APP_NS="${LIFTWORK_DEMO_NAMESPACE:-welcome-app}"
KCTX="${LIFTWORK_K8S__KUBE_CONTEXT:-kind-kubedeploy-dev}"

TOKEN=$(curl -s -X POST http://localhost:7878/auth/login \
  -H 'content-type: application/json' \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PW}\"}" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
echo "token len=${#TOKEN}"

# cluster (idempotent — 409 swallowed)
curl -s -X POST http://localhost:7878/clusters \
  -H "Authorization: Bearer ${TOKEN}" -H 'content-type: application/json' \
  -d '{"name":"kind-kubedeploy-dev","display_name":"Kind dev cluster","default_namespace":"default"}' >/dev/null

CLUSTER_ID=$(curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/clusters \
  | python3 -c '
import sys, json
for x in json.load(sys.stdin):
    if x["name"] == "kind-kubedeploy-dev":
        print(x["id"]); break')
echo "cluster_id=${CLUSTER_ID}"

# Wipe any prior welcome-app row + ensure ns
curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/applications \
  | python3 -c '
import sys, json
for x in json.load(sys.stdin):
    if x["slug"] == "welcome-app":
        print(x["id"])' | while read -r appid; do
  curl -s -X DELETE -H "Authorization: Bearer ${TOKEN}" "http://localhost:7878/applications/${appid}" >/dev/null
done
kubectl --context "${KCTX}" create namespace "${APP_NS}" 2>/dev/null || true

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
    \"auto_deploy\":true
  }" | python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')
echo "app_id=${APP_ID}"

BUILD_ID=$(curl -s -X POST -H "Authorization: Bearer ${TOKEN}" \
  "http://localhost:7878/applications/${APP_ID}/builds" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["build_id"])')
echo "build_id=${BUILD_ID}"

echo "▶ polling build (max 4 min)"
for i in $(seq 1 48); do
  sleep 5
  STATE=$(curl -s -H "Authorization: Bearer ${TOKEN}" "http://localhost:7878/builds/${BUILD_ID}" \
    | python3 -c 'import sys, json; print(json.load(sys.stdin)["status"])')
  printf "  [%03ds] status=%s\n" "$((i*5))" "${STATE}"
  case "${STATE}" in
    succeeded|failed|cancelled) break ;;
  esac
done

echo
echo "--- final build row ---"
curl -s -H "Authorization: Bearer ${TOKEN}" "http://localhost:7878/builds/${BUILD_ID}" | python3 -m json.tool
