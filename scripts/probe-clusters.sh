#!/usr/bin/env bash
set -euo pipefail
TOKEN=$(curl -s -X POST http://localhost:7878/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"admin@example.com","password":"change-me-now"}' \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])')
curl -s -H "Authorization: Bearer ${TOKEN}" http://localhost:7878/clusters | python3 -m json.tool
