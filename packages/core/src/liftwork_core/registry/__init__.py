"""Container registry abstraction (v1: GHCR)."""

from liftwork_core.registry.ghcr import build_docker_config_json, ghcr_repository
from liftwork_core.registry.protocols import ImageRef, RegistryClient
from liftwork_core.registry.tags import (
    image_ref,
    sanitize_branch,
    short_sha,
    tag_for_commit,
)

__all__ = [
    "ImageRef",
    "RegistryClient",
    "build_docker_config_json",
    "ghcr_repository",
    "image_ref",
    "sanitize_branch",
    "short_sha",
    "tag_for_commit",
]
