"""GitHub webhook receiver.

This endpoint is intentionally tiny and synchronous from the caller's
point of view: validate the HMAC signature, parse the event, look up
the matching application, and (if found + auto_deploy) create a queued
BuildRun row. Phase 4b adds the arq enqueue step.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.dependencies import get_db, get_settings_dep
from liftwork_api.schemas import WebhookAck
from liftwork_core.config import Settings
from liftwork_core.db.models import BuildSource
from liftwork_core.github import (
    WebhookVerificationError,
    parse_push_event,
    verify_signature,
)
from liftwork_core.repositories import (
    ApplicationRepository,
    BuildRunRepository,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

log = structlog.get_logger("liftwork.api.webhooks")


@router.post("/github", response_model=WebhookAck)
async def github_webhook(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings_dep)],
    session: Annotated[AsyncSession, Depends(get_db)],
    x_hub_signature_256: Annotated[str | None, Header(alias="X-Hub-Signature-256")] = None,
    x_github_event: Annotated[str | None, Header(alias="X-GitHub-Event")] = None,
    x_github_delivery: Annotated[str | None, Header(alias="X-GitHub-Delivery")] = None,
) -> WebhookAck:
    secret_obj = settings.github.webhook_secret
    if secret_obj is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub webhook secret is not configured",
        )

    payload = await request.body()
    try:
        verify_signature(
            secret=secret_obj.get_secret_value(),
            payload=payload,
            signature_header=x_hub_signature_256,
        )
    except WebhookVerificationError as exc:
        log.warning("webhook.signature_invalid", reason=str(exc), delivery=x_github_delivery)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    event = (x_github_event or "").lower()
    if event == "ping":
        return WebhookAck(received=True, event="ping", delivery_id=x_github_delivery, action="pong")

    if event != "push":
        return WebhookAck(
            received=True,
            event=event,
            delivery_id=x_github_delivery,
            detail="event type not handled",
        )

    try:
        push = parse_push_event(payload)
    except WebhookVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if not push.is_branch_push or push.is_zero_after:
        return WebhookAck(
            received=True,
            event="push",
            delivery_id=x_github_delivery,
            detail="non-branch or branch-deletion push — ignored",
        )

    app_repo = ApplicationRepository(session)
    application = await app_repo.find_for_push(
        owner=push.repo_owner,
        name=push.repo_name,
        branch=push.branch,
    )
    if application is None:
        return WebhookAck(
            received=True,
            event="push",
            delivery_id=x_github_delivery,
            detail=(f"no application matches {push.repo_owner}/{push.repo_name}@{push.branch}"),
        )

    if not application.auto_deploy:
        return WebhookAck(
            received=True,
            event="push",
            delivery_id=x_github_delivery,
            detail="application has auto_deploy disabled",
        )

    runs = BuildRunRepository(session)
    existing = await runs.find_existing(
        application_id=application.id,
        commit_sha=push.commit_sha,
        branch=push.branch,
    )
    if existing is not None:
        return WebhookAck(
            received=True,
            event="push",
            delivery_id=x_github_delivery,
            action="deduplicated",
            build_id=existing.id,
        )

    run = await runs.create(
        application_id=application.id,
        commit_sha=push.commit_sha,
        branch=push.branch,
        source=BuildSource.webhook,
        commit_message=push.commit_message,
    )
    await session.commit()
    log.info(
        "webhook.build_enqueued",
        build_id=str(run.id),
        application=application.slug,
        commit=push.commit_sha,
        branch=push.branch,
        delivery=x_github_delivery,
    )

    return WebhookAck(
        received=True,
        event="push",
        delivery_id=x_github_delivery,
        action="build_enqueued",
        build_id=run.id,
    )
