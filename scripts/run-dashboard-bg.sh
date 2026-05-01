#!/usr/bin/env bash
# Detach a Vite dev server. Survives caller exit.
set -euo pipefail

cd /home/pratheek/dev-workspace/python/liftwork/apps/dashboard
export PATH="${HOME}/.npm-global/bin:${HOME}/.local/bin:${PATH}"

# Vite proxies /api → API target.
export LIFTWORK_API_URL="${LIFTWORK_API_URL:-http://localhost:7878}"

: > /tmp/liftwork-dashboard.log
setsid nohup pnpm dev --host >/tmp/liftwork-dashboard.log 2>&1 < /dev/null &
DPID=$!
disown
sleep 6
if curl -sf http://localhost:5173/ >/dev/null 2>&1; then
  echo "dashboard_pid=${DPID} (healthy at http://localhost:5173)"
else
  echo "DASHBOARD_DOWN"
  tail -25 /tmp/liftwork-dashboard.log
  exit 1
fi
