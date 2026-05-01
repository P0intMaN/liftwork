#!/usr/bin/env bash
set -euo pipefail
TOKEN=$(curl -s -X POST http://localhost:7878/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"change-me-now"}' \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
echo "token_len=${#TOKEN}"
echo
echo "--- /dashboard/summary ---"
curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/dashboard/summary | python3 -m json.tool
echo
echo "--- /dashboard/activity (top 5) ---"
curl -s -H "Authorization: Bearer ${TOKEN}" 'http://localhost:7878/dashboard/activity?limit=5' | python3 -m json.tool
echo
echo "--- /dashboard/builds/timeseries (last 3) ---"
curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/dashboard/builds/timeseries | python3 -c '
import sys, json
data = json.load(sys.stdin)
for d in data[-3:]: print(f"  {d}")
'
