"""Periodic cluster reachability probe.

Runs every minute via arq cron. For each registered Cluster row we
load its kubeconfig context and call `core_v1.list_namespace` with a
short timeout — if it returns we mark the row `healthy` + bump
`last_seen_at`; on any failure we mark `unreachable`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from typing import Any

import anyio
import structlog

from liftwork_core.config import K8sSettings
from liftwork_core.db.models import Cluster, ClusterStatus
from liftwork_core.repositories import ClusterRepository
from liftwork_worker.k8s import K8sClientError, load_kube_clients
from liftwork_worker.state import get_state

log = structlog.get_logger("liftwork.worker.cluster_health")


async def check_clusters_health(ctx: dict[str, Any]) -> dict[str, int]:
    state = get_state(ctx)
    healthy = 0
    unreachable = 0

    async with state.session_factory() as session:
        clusters = await ClusterRepository(session).list_all()

    for c in clusters:
        ok = await _probe(c)
        async with state.session_factory() as session:
            row = await session.get(Cluster, c.id)
            if row is None:
                continue
            row.status = ClusterStatus.healthy if ok else ClusterStatus.unreachable
            if ok:
                row.last_seen_at = datetime.now(UTC)
                healthy += 1
            else:
                unreachable += 1
            await session.commit()
        log.info("cluster.probe", cluster=c.name, healthy=ok)

    return {"healthy": healthy, "unreachable": unreachable}


async def _probe(cluster: Cluster) -> bool:
    """One-shot reachability check. Returns True if list_namespace returns."""
    try:
        clients = await anyio.to_thread.run_sync(
            partial(
                load_kube_clients,
                K8sSettings(kube_context=cluster.name, in_cluster=cluster.in_cluster),
            )
        )
        await anyio.to_thread.run_sync(
            partial(clients.core_v1.list_namespace, _request_timeout=5)
        )
    except (K8sClientError, Exception):  # noqa: BLE001 — any failure ⇒ unreachable
        return False
    return True
