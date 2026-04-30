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
from liftwork_api.routers import (
    applications,
    auth,
    builds,
    clusters,
    health,
    metrics,
    webhooks,
)


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
    app.include_router(auth.router)
    app.include_router(clusters.router)
    app.include_router(applications.router)
    app.include_router(builds.router)
    app.include_router(builds.detail_router)
    app.include_router(webhooks.router)

    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
