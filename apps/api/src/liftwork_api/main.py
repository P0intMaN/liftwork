"""FastAPI application factory.

Phase 1 wires telemetry, DB, Redis, request-scoped middleware, and a real
readiness probe. Domain routers (apps, builds, webhooks, auth) land in
later phases.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from liftwork_api import __version__
from liftwork_api.lifespan import lifespan
from liftwork_api.middleware import RequestContextMiddleware
from liftwork_api.routers import (
    applications,
    auth,
    builds,
    clusters,
    dashboard,
    deployments,
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

    # Allow the dashboard's Vite dev server to call the API directly.
    # In production both run behind the same nginx ingress so CORS is moot.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:4173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(metrics.router)
    app.include_router(auth.router)
    app.include_router(clusters.router)
    app.include_router(applications.router)
    app.include_router(builds.router)
    app.include_router(builds.detail_router)
    app.include_router(deployments.router)
    app.include_router(deployments.detail_router)
    app.include_router(dashboard.router)
    app.include_router(webhooks.router)

    FastAPIInstrumentor.instrument_app(app)
    return app


app = create_app()
