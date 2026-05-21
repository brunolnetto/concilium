from __future__ import annotations

from fastapi import FastAPI

from .routes import (
    analysis_router,
    benchmarks_router,
    catalog_router,
    catalogs_router,
    configuration_router,
    mobilization_router,
    overrides_router,
    projects_router,
    runs_router,
    system_router,
)

_TAGS_METADATA = [
    # ── System ─────────────────────────────────────────────────────────────────
    {"name": "system", "description": "Health check and API entry point."},
    # ── Configuration ──────────────────────────────────────────────────────────
    {"name": "configuration", "description": "Versioned config — perfis, contextos, temas, jurisdições."},
    # ── Catalogs ───────────────────────────────────────────────────────────────
    {"name": "catalogs", "description": "Master catalog — CPUs, insumos, full-text search."},
    # ── Projects ───────────────────────────────────────────────────────────────
    {"name": "projects - core", "description": "Project lifecycle — CRUD, versioning, EAP composition (ADR-063)."},
    {"name": "projects - catalog", "description": "Per-project catalog layer — CPU overlays and resolution."},
    {"name": "projects - runs", "description": "Pipeline execution — synchronous, asynchronous, fork and rerun."},
    {"name": "projects - overrides", "description": "Saved skill input overrides applied before each run."},
    {"name": "projects - analysis", "description": "Version comparison, artifacts, audit log, breakeven diagnostics."},
    {"name": "projects - mobilization", "description": "Workforce mobilization policies and deliverables config."},
    # ── Benchmarks ─────────────────────────────────────────────────────────────
    {"name": "benchmarks", "description": "Benchmark templates and project-scoped artifact download/pack."},
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="Concilium API",
        description="API de planejamento temporal e financeiro de obras — MendesLobo Construtora.",
        version="0.3.0",
        docs_url="/swagger",
        openapi_url="/openapi.json",
        redoc_url="/redoc",
        openapi_tags=_TAGS_METADATA,
        swagger_ui_parameters={"displayRequestDuration": True, "docExpansion": "list"},
    )

    # Ordem de registro = ordem de aparição no Swagger (dentro de cada tag)
    app.include_router(system_router)
    app.include_router(configuration_router)
    app.include_router(catalogs_router)
    app.include_router(projects_router)
    app.include_router(catalog_router)
    app.include_router(runs_router)
    app.include_router(overrides_router)
    app.include_router(analysis_router)
    app.include_router(mobilization_router)
    app.include_router(benchmarks_router)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run("concilium.presentation.api.app:app", host="127.0.0.1", port=8000, reload=False)
