#!/usr/bin/env bash
# Drive a real liftwork build → deploy through the existing kind cluster.
# Assumes:
#   * docker compose has postgres + redis up (make dev-up)
#   * make kind-prereqs has been run
#   * scripts/prepull-images.sh has been run (otherwise first run is slow)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

# Defaults from .env.example, then override for kind mode.
set -a
. ./.env.example
set +a
export LIFTWORK_WORKER__EXECUTOR=kind
export LIFTWORK_K8S__KUBE_CONTEXT=kind-kubedeploy-dev
export LIFTWORK_REGISTRY__HOST=registry.liftwork.svc.cluster.local:5000
export LIFTWORK_REGISTRY__INSECURE=true

ADMIN_EMAIL="${LIFTWORK_BOOTSTRAP__ADMIN_EMAIL:-admin@example.com}"
ADMIN_PW="${LIFTWORK_BOOTSTRAP__ADMIN_PASSWORD:-change-me-now}"
APP_NS="welcome-app"

echo "▶ resetting prior state"
pkill -9 -f 'uvicorn liftwork_api' 2>/dev/null || true
pkill -9 -f 'liftwork_worker' 2>/dev/null || true
pkill -9 -f 'liftwork_worker.main' 2>/dev/null || true
sleep 1
docker exec liftwork-redis redis-cli DEL arq:queue >/dev/null
kubectl --context "${LIFTWORK_K8S__KUBE_CONTEXT}" delete ns "${APP_NS}" --ignore-not-found
kubectl --context "${LIFTWORK_K8S__KUBE_CONTEXT}" -n liftwork delete jobs,configmaps -l app.kubernetes.io/component=builder --ignore-not-found

echo "▶ starting API"
: > /tmp/liftwork-api.log
nohup uv run --package liftwork-api uvicorn liftwork_api.main:app \
  --host 0.0.0.0 --port 7878 \
  >/tmp/liftwork-api.log 2>&1 < /dev/null &
disown

echo -n "   waiting"
for _ in $(seq 1 30); do
  if curl -sf http://localhost:7878/healthz >/dev/null 2>&1; then
    echo " up"
    break
  fi
  sleep 1
  echo -n .
done
curl -sf http://localhost:7878/healthz >/dev/null 2>&1 || {
  echo " ✗ API never came up"
  tail -25 /tmp/liftwork-api.log
  exit 1
}

echo "▶ starting worker (kind mode)"
: > /tmp/liftwork-worker.log
nohup uv run --package liftwork-worker python -m liftwork_worker.main \
  >/tmp/liftwork-worker.log 2>&1 < /dev/null &
disown
sleep 4

if ! pgrep -af 'liftwork_worker.main' >/dev/null; then
  echo "✗ worker did not start"
  tail -30 /tmp/liftwork-worker.log
  exit 1
fi

echo "▶ login"
TOKEN=$(curl -s -X POST http://localhost:7878/auth/login \
  -H 'content-type: application/json' \
  -d "{\"email\":\"${ADMIN_EMAIL}\",\"password\":\"${ADMIN_PW}\"}" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')

if [[ -z "${TOKEN}" ]]; then
  echo "✗ login failed"
  tail -25 /tmp/liftwork-api.log
  exit 1
fi

echo "▶ ensuring cluster row + target namespace"
curl -s -X POST http://localhost:7878/clusters \
  -H "Authorization: Bearer ${TOKEN}" -H 'content-type: application/json' \
  -d '{"name":"kind-kubedeploy-dev","display_name":"Kind dev cluster","default_namespace":"default"}' >/dev/null
CLUSTER_ID=$(curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/clusters \
  | python3 -c 'import sys,json
for x in json.load(sys.stdin):
    if x["name"]=="kind-kubedeploy-dev":
        print(x["id"]); break')
echo "   cluster_id=${CLUSTER_ID}"

kubectl --context "${LIFTWORK_K8S__KUBE_CONTEXT}" create namespace "${APP_NS}" 2>/dev/null || true

echo "▶ creating welcome-app application"
# Wipe any prior row for this slug
curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/applications \
  | python3 -c '
import sys, json
for x in json.load(sys.stdin):
    if x["slug"] == "welcome-app":
        print(x["id"])' | while read -r appid; do
  curl -s -X DELETE -H "Authorization: Bearer ${TOKEN}" "http://localhost:7878/applications/${appid}" >/dev/null
done

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
  }" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["id"])')
echo "   app_id=${APP_ID}"

echo "▶ triggering build"
BUILD_ID=$(curl -s -X POST -H "Authorization: Bearer ${TOKEN}" \
  "http://localhost:7878/applications/${APP_ID}/builds" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["build_id"])')
echo "   build_id=${BUILD_ID}"

echo "▶ following build (max 6 min)"
for i in $(seq 1 72); do
  sleep 5
  STATE=$(curl -s -H "Authorization: Bearer ${TOKEN}" \
    "http://localhost:7878/builds/${BUILD_ID}" \
    | python3 -c 'import sys, json; b=json.load(sys.stdin); print(b["status"])')
  echo "   t=${i}*5s status=${STATE}"
  case "${STATE}" in
    succeeded|failed|cancelled) break ;;
  esac
done

echo
echo "▶ final build row"
curl -s -H "Authorization: Bearer ${TOKEN}" "http://localhost:7878/builds/${BUILD_ID}" | python3 -m json.tool

echo
echo "▶ liftwork ns (jobs + pods)"
kubectl --context "${LIFTWORK_K8S__KUBE_CONTEXT}" -n liftwork get jobs,pods --sort-by=.metadata.creationTimestamp

echo
echo "▶ registry catalog"
kubectl --context "${LIFTWORK_K8S__KUBE_CONTEXT}" -n liftwork exec deploy/registry -- wget -qO- http://localhost:5000/v2/_catalog || true

echo
echo "▶ ${APP_NS} ns (the deployed app)"
kubectl --context "${LIFTWORK_K8S__KUBE_CONTEXT}" -n "${APP_NS}" get all 2>&1 | head -20

echo
echo "▶ worker.log tail"
tail -40 /tmp/liftwork-worker.log

echo
echo "✓ done."
