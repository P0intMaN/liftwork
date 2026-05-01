#!/usr/bin/env bash
# Pre-pull the BuildKit + alpine/git images onto every kind node so the
# first real build doesn't burn 5 minutes on image fetches. Idempotent.
set -euo pipefail

CLUSTER="${LIFTWORK_KIND_CLUSTER:-kubedeploy-dev}"
IMAGES=(
  "moby/buildkit:v0.16.0-rootless"
  "alpine/git:2.45.2"
)

echo "▶ pre-pulling on every node of kind/${CLUSTER}"
NODES=$(kind get nodes --name "${CLUSTER}")
for node in ${NODES}; do
  echo "  · ${node}"
  for image in "${IMAGES[@]}"; do
    echo "    pulling ${image}"
    docker exec "${node}" crictl pull "${image}" 2>&1 | tail -2
  done
done
echo "✓ done."
