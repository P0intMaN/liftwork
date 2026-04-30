"""High-level deploy orchestration."""

from __future__ import annotations

import time

from liftwork_core.build.protocols import LogSink
from liftwork_core.deploy import (
    DeployExecutor,
    DeployRequest,
    DeployResult,
    RolloutOutcome,
    build_all_manifests,
    resource_name,
)


class DeployOrchestrationError(RuntimeError):
    pass


async def orchestrate_deploy(
    request: DeployRequest,
    *,
    executor: DeployExecutor,
    log_sink: LogSink,
) -> DeployResult:
    """Apply manifests, watch rollout, return a DeployResult."""
    started = time.perf_counter()
    deployment_name = resource_name(request.application_slug)
    service_name = deployment_name
    ingress_name: str | None = deployment_name if request.deploy_spec.ingress.enabled else None

    manifests = build_all_manifests(request)
    await log_sink.write(
        f"deploy: revision={request.revision} "
        f"namespace={request.target.namespace} "
        f"image_ref={request.image_ref} "
        f"manifests={','.join(m['kind'] for m in manifests)}"
    )

    error: str | None = None
    try:
        await executor.apply_manifests(
            manifests,
            namespace=request.target.namespace,
            log_sink=log_sink,
        )
        outcome = await executor.wait_for_rollout(
            namespace=request.target.namespace,
            deployment_name=deployment_name,
            target_replicas=request.deploy_spec.replicas,
            log_sink=log_sink,
        )
    except Exception as exc:  # noqa: BLE001 — surface any failure as DeployResult
        error = f"{exc.__class__.__name__}: {exc}"
        outcome = RolloutOutcome.failed
        await log_sink.write(f"deploy: error — {error}")

    return DeployResult(
        revision=request.revision,
        deployment_name=deployment_name,
        service_name=service_name,
        ingress_name=ingress_name,
        outcome=outcome,
        duration_seconds=round(time.perf_counter() - started, 3),
        error=error,
    )
