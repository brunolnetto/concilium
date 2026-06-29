from __future__ import annotations

from fastapi import FastAPI

from concilium.infrastructure.middleware.auth_context import AuthContextMiddleware
from concilium.infrastructure.observability.logging_config import configure_logging
from concilium.infrastructure.settings import get_telemetry
from concilium.infrastructure.telemetry import setup_telemetry

from .config import resolve_api_bind
from .middleware import JWTAuthMiddleware
from .rate_limit import limiter, rate_limit_exceeded_handler
from .routes import (
    analysis_router,
    auth_router,
    benchmarks_router,
    campaign_router,
    catalog_router,
    catalogs_router,
    configuration_router,
    formulario_router,
    mobilization_router,
    observability_router,
    overrides_router,
    projects_router,
    runs_router,
    system_router,
)

_TAGS_METADATA = [
    # ── Auth ───────────────────────────────────────────────────────────────────
    {"name": "auth", "description": "Autenticação JWT RS256 — emissão de tokens (ADR-094)."},
    # ── Observability ──────────────────────────────────────────────────────────
    {
        "name": "observability",
        "description": "Pipeline de observabilidade (ADR-112): Bronze/Silver/Gold paginados — SLIs, fallback rates, alertas, records raw.",
    },
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
    # ── Campaign ───────────────────────────────────────────────────────────────
    {
        "name": "projects - campaign",
        "description": "ADR-070: parametric GO-space sweep — campaign runs, bundles, reports.",
    },
]


def create_app() -> FastAPI:
    setup_telemetry()
    configure_logging(json_format=True)

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

    # Evita custo de instrumentação quando SDK está desativado (comum em testes/CI).
    if not get_telemetry().otel_sdk_disabled:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except ImportError:
            pass

    # ADR-099: PermissionError → 403 Forbidden
    from fastapi import Request as _Request
    from fastapi.responses import JSONResponse as _JSONResponse

    @app.exception_handler(PermissionError)
    async def _permission_error_handler(_req: _Request, exc: PermissionError) -> _JSONResponse:
        return _JSONResponse(status_code=403, content={"detail": str(exc)})

    # ADR-098: Rate limiting — ordem de middleware: SlowAPI (outer) → JWT (inner)
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)  # type: ignore[arg-type]
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(AuthContextMiddleware)  # antes do JWT — request_id sempre presente
    app.add_middleware(SlowAPIMiddleware)

    # Ordem de registro = ordem de aparição no Swagger (dentro de cada tag)
    app.include_router(auth_router)
    app.include_router(system_router)
    app.include_router(configuration_router)
    app.include_router(catalogs_router)
    app.include_router(projects_router)
    app.include_router(catalog_router)
    app.include_router(runs_router)
    app.include_router(formulario_router)
    app.include_router(overrides_router)
    app.include_router(analysis_router)
    app.include_router(mobilization_router)
    app.include_router(benchmarks_router)
    app.include_router(campaign_router)
    app.include_router(observability_router)

    return app


app = create_app()


def main() -> None:
    import uvicorn

    from concilium.infrastructure.settings import get_api, startup_check
    from concilium.infrastructure.storage.store_factory import ensure_storage_root

    startup_check()
    ensure_storage_root()

    host, port = resolve_api_bind()
    reload = get_api().reload
    uvicorn.run("concilium.presentation.api.app:app", host=host, port=port, reload=reload)
