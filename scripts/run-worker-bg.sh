#!/usr/bin/env bash
# Detaches a worker process and prints its pid. Survives caller exit.
set -euo pipefail

cd /home/pratheek/dev-workspace/python/liftwork
export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

set -a
. ./.env.example
set +a
export LIFTWORK_WORKER__EXECUTOR=kind
export LIFTWORK_K8S__KUBE_CONTEXT=kind-kubedeploy-dev
export LIFTWORK_REGISTRY__HOST=registry.liftwork.svc.cluster.local:5000
export LIFTWORK_REGISTRY__INSECURE=true

: > /tmp/liftwork-worker.log
setsid nohup uv run --package liftwork-worker python -m liftwork_worker.main \
  >/tmp/liftwork-worker.log 2>&1 < /dev/null &
WPID=$!
disown
sleep 6
if kill -0 "${WPID}" 2>/dev/null; then
  echo "worker_pid=${WPID}"
else
  echo "WORKER_DIED"
  tail -20 /tmp/liftwork-worker.log
  exit 1
fi
