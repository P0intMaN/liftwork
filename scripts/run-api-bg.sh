#!/usr/bin/env bash
# Detach a liftwork-api uvicorn. Survives caller exit.
set -euo pipefail

cd /home/pratheek/dev-workspace/python/liftwork
export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

set -a
. ./.env.example
set +a
# overrides for kind mode
export LIFTWORK_WORKER__EXECUTOR=kind
export LIFTWORK_K8S__KUBE_CONTEXT=kind-kubedeploy-dev
export LIFTWORK_REGISTRY__HOST=registry.liftwork.svc.cluster.local:5000
export LIFTWORK_REGISTRY__INSECURE=true

: > /tmp/liftwork-api.log
setsid nohup uv run --package liftwork-api uvicorn \
  liftwork_api.main:app --host 0.0.0.0 --port 7878 \
  >/tmp/liftwork-api.log 2>&1 < /dev/null &
APID=$!
disown
sleep 6
if curl -sf http://localhost:7878/healthz >/dev/null; then
  echo "api_pid=${APID} (healthy)"
else
  echo "API_DOWN"
  tail -25 /tmp/liftwork-api.log
  exit 1
fi
