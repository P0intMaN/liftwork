"""Prometheus exposition endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Response

from liftwork_core.telemetry import render_prometheus

router = APIRouter(tags=["meta"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    body, content_type = render_prometheus()
    return Response(content=body, media_type=content_type)
