"""FastAPI application entrypoint.

Phase 0 ships only a liveness/readiness surface and a service identity
endpoint. Domain routes, telemetry middleware, and database wiring land
in Phase 1.
"""

from __future__ import annotations

from fastapi import FastAPI

from liftwork_api import __version__


def create_app() -> FastAPI:
    app = FastAPI(
        title="Liftwork API",
        version=__version__,
        docs_url="/docs",
        redoc_url=None,
    )

    @app.get("/healthz", tags=["meta"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["meta"])
    async def readyz() -> dict[str, str]:
        return {"status": "ready"}

    @app.get("/", tags=["meta"])
    async def root() -> dict[str, str]:
        return {"service": "liftwork-api", "version": __version__}

    return app


app = create_app()
