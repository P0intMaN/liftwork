#!/usr/bin/env bash
set -euo pipefail
BUILD_ID="${1:-}"
[[ -z "${BUILD_ID}" ]] && { echo "usage: poll-build.sh <build-uuid>"; exit 1; }

TOKEN=$(curl -s -X POST http://localhost:7878/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"change-me-now"}' \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')

for i in $(seq 1 24); do
  sleep 5
  STATE=$(curl -s -H "Authorization: Bearer ${TOKEN}" "http://localhost:7878/builds/${BUILD_ID}" \
    | python3 -c 'import sys, json; print(json.load(sys.stdin)["status"])')
  printf "  [%03ds] status=%s\n" "$((i*5))" "${STATE}"
  case "${STATE}" in succeeded|failed|cancelled) break ;; esac
done

echo
echo "▶ final build row:"
curl -s -H "Authorization: Bearer ${TOKEN}" "http://localhost:7878/builds/${BUILD_ID}" | python3 -m json.tool
