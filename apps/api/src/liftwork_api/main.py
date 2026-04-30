"""FastAPI application factory.

Phase 1 wires telemetry, DB, Redis, request-scoped middleware, and a real
readiness probe. Domain routers (apps, builds, webhooks, auth) land in
later phases.
"""

from __future__ import annotations

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from liftwork_api import __version__
from liftwork_api.lifespan import lifespan
from liftwork_api.middleware import RequestContextMiddleware
from liftwork_api.routers import health, metrics


def create_app() -> FastAPI:
    app = FastAPI(
        title="Liftwork API",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(metrics.router)

    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
