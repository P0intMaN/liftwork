"""Standard labels, annotations, and the field manager string for SSA."""

from __future__ import annotations

from typing import Final

LIFTWORK_FIELD_MANAGER: Final[str] = "liftwork-controller"


def selector_labels(app_slug: str) -> dict[str, str]:
    """Labels stable across rollouts — Deployment.spec.selector.matchLabels."""
    return {
        "app.kubernetes.io/name": app_slug,
        "app.kubernetes.io/managed-by": "liftwork",
    }


def base_labels(
    *,
    app_slug: str,
    application_id: str,
    image_tag: str,
    component: str = "app",
) -> dict[str, str]:
    return {
        "app.kubernetes.io/name": app_slug,
        "app.kubernetes.io/instance": app_slug,
        "app.kubernetes.io/version": image_tag,
        "app.kubernetes.io/managed-by": "liftwork",
        "app.kubernetes.io/component": component,
        "liftwork.io/application-id": application_id,
    }


def base_annotations(
    *,
    revision: int,
    commit_sha: str,
    branch: str,
    image_digest: str | None = None,
) -> dict[str, str]:
    out = {
        "liftwork.io/revision": str(revision),
        "liftwork.io/commit": commit_sha,
        "liftwork.io/branch": branch,
    }
    if image_digest:
        out["liftwork.io/image-digest"] = image_digest
    return out
