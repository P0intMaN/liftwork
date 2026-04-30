"""Async wrappers around the official kubernetes python client.

The k8s client is sync-only, so we run blocking calls on a worker thread
via `anyio.to_thread.run_sync` — this keeps the event loop responsive
under concurrent build/deploy workloads.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config

from liftwork_core.config import K8sSettings


class K8sClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class K8sClients:
    core_v1: k8s_client.CoreV1Api
    batch_v1: k8s_client.BatchV1Api
    apps_v1: k8s_client.AppsV1Api
    networking_v1: k8s_client.NetworkingV1Api
    api_client: k8s_client.ApiClient


def load_kube_clients(settings: K8sSettings) -> K8sClients:
    """Load kubeconfig + return typed Api clients.

    Resolves in this order:
      1. `in_cluster=True` -> in-cluster service account
      2. `kube_context` set -> ~/.kube/config with named context
      3. fallback -> default ~/.kube/config
    """
    if settings.in_cluster:
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException as exc:
            msg = "in_cluster=True but no in-cluster service account found"
            raise K8sClientError(msg) from exc
    else:
        try:
            k8s_config.load_kube_config(context=settings.kube_context)
        except k8s_config.ConfigException as exc:
            msg = f"could not load kubeconfig (context={settings.kube_context!r}): {exc}"
            raise K8sClientError(msg) from exc

    api_client = k8s_client.ApiClient()
    return K8sClients(
        core_v1=k8s_client.CoreV1Api(api_client),
        batch_v1=k8s_client.BatchV1Api(api_client),
        apps_v1=k8s_client.AppsV1Api(api_client),
        networking_v1=k8s_client.NetworkingV1Api(api_client),
        api_client=api_client,
    )


def sanitize_for_serialization(api_client: k8s_client.ApiClient, obj: Any) -> Any:
    """Convert typed V1* objects into plain dicts (for snapshot tests / apply)."""
    return api_client.sanitize_for_serialization(obj)
