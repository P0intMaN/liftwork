"""Request-scoped middleware: request id, structured access log, prometheus."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

from liftwork_core.telemetry import PROMETHEUS_REGISTRY

REQUEST_COUNT = Counter(
    "liftwork_http_requests_total",
    "HTTP requests handled by the liftwork API.",
    labelnames=("method", "route", "status"),
    registry=PROMETHEUS_REGISTRY,
)

REQUEST_LATENCY = Histogram(
    "liftwork_http_request_duration_seconds",
    "HTTP request latency.",
    labelnames=("method", "route"),
    registry=PROMETHEUS_REGISTRY,
)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return str(route.path)
    return request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        log = structlog.get_logger("liftwork.api")

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("request_failed")
            elapsed = time.perf_counter() - start
            route = _route_template(request)
            REQUEST_COUNT.labels(request.method, route, "500").inc()
            REQUEST_LATENCY.labels(request.method, route).observe(elapsed)
            raise

        elapsed = time.perf_counter() - start
        route = _route_template(request)
        REQUEST_COUNT.labels(request.method, route, str(response.status_code)).inc()
        REQUEST_LATENCY.labels(request.method, route).observe(elapsed)

        response.headers["x-request-id"] = request_id
        log.info(
            "request_completed",
            status_code=response.status_code,
            elapsed_ms=round(elapsed * 1000, 2),
        )
        return response
