"""Deploy engine: manifest generation + executor protocols."""

from liftwork_core.deploy.labels import (
    LIFTWORK_FIELD_MANAGER,
    base_annotations,
    base_labels,
    selector_labels,
)
from liftwork_core.deploy.manifests import (
    build_all_manifests,
    build_deployment_manifest,
    build_ingress_manifest,
    build_service_manifest,
    resource_name,
)
from liftwork_core.deploy.protocols import (
    DeployExecutor,
    DeployRequest,
    DeployResult,
    DeployTarget,
    RolloutOutcome,
)

__all__ = [
    "LIFTWORK_FIELD_MANAGER",
    "DeployExecutor",
    "DeployRequest",
    "DeployResult",
    "DeployTarget",
    "RolloutOutcome",
    "base_annotations",
    "base_labels",
    "build_all_manifests",
    "build_deployment_manifest",
    "build_ingress_manifest",
    "build_service_manifest",
    "resource_name",
    "selector_labels",
]
