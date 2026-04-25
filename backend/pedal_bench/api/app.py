"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pedal_bench import config
from pedal_bench.api.routes import (
    ai_status,
    bom,
    debug,
    diagnose,
    drill_extract,
    enclosures,
    holes,
    inventory,
    layout_presets,
    mouser,
    pdf,
    photos,
    projects,
    refdes_map,
    stl,
    tayda,
    verify_component,
)


def create_app() -> FastAPI:
    app = FastAPI(
        title="pedal-bench",
        version="0.2.0",
        description=(
            "Bench copilot for DIY guitar pedal builds. "
            "See /docs for the interactive API reference."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.DEV_CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(enclosures.router, prefix="/api/v1")
    app.include_router(projects.router, prefix="/api/v1")
    app.include_router(holes.router, prefix="/api/v1")
    app.include_router(bom.router, prefix="/api/v1")
    app.include_router(stl.router, prefix="/api/v1")
    app.include_router(tayda.router, prefix="/api/v1")
    app.include_router(pdf.router, prefix="/api/v1")
    app.include_router(pdf.projects_router, prefix="/api/v1")
    app.include_router(drill_extract.router, prefix="/api/v1")
    app.include_router(debug.router, prefix="/api/v1")
    app.include_router(layout_presets.router, prefix="/api/v1")
    app.include_router(refdes_map.router, prefix="/api/v1")
    app.include_router(photos.router, prefix="/api/v1")
    app.include_router(verify_component.router, prefix="/api/v1")
    app.include_router(diagnose.router, prefix="/api/v1")
    app.include_router(ai_status.router, prefix="/api/v1")
    app.include_router(inventory.router, prefix="/api/v1")
    app.include_router(mouser.router, prefix="/api/v1")

    @app.get("/api/v1/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "pedal-bench"}

    return app


app = create_app()
