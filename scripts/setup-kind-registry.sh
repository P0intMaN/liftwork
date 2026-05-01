#!/usr/bin/env bash
# Configures the existing kind cluster `kubedeploy-dev` for liftwork's
# dev e2e:
#
#   1. Applies the liftwork namespace + RBAC + in-cluster registry
#   2. Patches containerd on every kind node so it mirrors
#      `registry.liftwork.svc.cluster.local:5000` through the registry's
#      NodePort at http://localhost:30500. Without this step, kubelet
#      (which uses the node's containerd) would try HTTPS against the
#      cluster-DNS hostname and fail.
#
# Re-running is safe — every step is idempotent.

set -euo pipefail

CLUSTER="${LIFTWORK_KIND_CLUSTER:-kubedeploy-dev}"
KCTX="kind-${CLUSTER}"
NS="liftwork"
REG_HOST="registry.${NS}.svc.cluster.local"
REG_PORT="5000"
NODE_PORT="30500"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"

echo "▶ context = ${KCTX}"
if ! kubectl --context "${KCTX}" cluster-info >/dev/null 2>&1; then
  echo "  ✗ context ${KCTX} not reachable" >&2
  exit 1
fi

echo "▶ applying ${NS} namespace + RBAC + registry"
kubectl --context "${KCTX}" apply -f "${REPO_ROOT}/deploy/k8s/00-namespace.yaml"
kubectl --context "${KCTX}" apply -f "${REPO_ROOT}/deploy/k8s/01-rbac.yaml"
kubectl --context "${KCTX}" apply -f "${REPO_ROOT}/deploy/k8s/02-registry.yaml"

echo "▶ waiting for registry to be ready"
kubectl --context "${KCTX}" -n "${NS}" rollout status deploy/registry --timeout=120s

echo "▶ patching containerd on every kind node"
HOSTS_DIR="/etc/containerd/certs.d/${REG_HOST}:${REG_PORT}"
HOSTS_TOML="
server = \"http://${REG_HOST}:${REG_PORT}\"
[host.\"http://localhost:${NODE_PORT}\"]
  capabilities = [\"pull\", \"resolve\"]
"

NODES=$(kind get nodes --name "${CLUSTER}")
for node in ${NODES}; do
  echo "  · ${node}"
  # 1. Per-host hosts.toml that maps the cluster-DNS hostname through the
  #    NodePort. Without this, containerd would try HTTPS against the
  #    in-cluster Service IP (which it can't even resolve).
  docker exec "${node}" mkdir -p "${HOSTS_DIR}"
  printf '%s' "${HOSTS_TOML}" | docker exec -i "${node}" tee "${HOSTS_DIR}/hosts.toml" >/dev/null

  # 2. Make sure containerd is *told* to look at /etc/containerd/certs.d.
  #    Some kind/node images don't ship the CRI registry section by
  #    default — without `config_path`, the hosts.toml above is invisible
  #    and pulls fall back to the default HTTPS-against-the-hostname path.
  if ! docker exec "${node}" grep -q 'config_path = "/etc/containerd/certs.d"' /etc/containerd/config.toml; then
    docker exec "${node}" sh -c 'printf "\n[plugins.\"io.containerd.grpc.v1.cri\".registry]\n  config_path = \"/etc/containerd/certs.d\"\n" >> /etc/containerd/config.toml'
    docker exec "${node}" systemctl restart containerd
    sleep 5
  fi
done

echo "▶ documenting registry to anyone using kind tooling"
cat <<EOF | kubectl --context "${KCTX}" apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: local-registry-hosting
  namespace: kube-public
data:
  localRegistryHosting.v1: |
    host: "${REG_HOST}:${REG_PORT}"
    hostFromContainerRuntime: "${REG_HOST}:${REG_PORT}"
    hostFromClusterNetwork: "${REG_HOST}:${REG_PORT}"
    help: "https://kind.sigs.k8s.io/docs/user/local-registry/"
EOF

echo
echo "✓ done."
echo "  BuildKit pushes to ${REG_HOST}:${REG_PORT}"
echo "  kubelet pulls    via http://localhost:${NODE_PORT} (containerd mirror)"
