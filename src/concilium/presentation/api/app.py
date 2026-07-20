from __future__ import annotations

from fastapi import FastAPI

from concilium.infrastructure.middleware.auth_context import AuthContextMiddleware
from concilium.infrastructure.observability.logging_config import configure_logging
from concilium.infrastructure.observability.pipeline import bronze_storage_for_bootstrap
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
        "description": "Pipeline de observabilidade (ADR-112): Bronze/Silver/Gold paginados — "
        "SLIs, fallback rates, alertas, records raw.",
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
    bronze_storage = bronze_storage_for_bootstrap()
    setup_telemetry(bronze_storage=bronze_storage)
    configure_logging(json_format=True, bronze_storage=bronze_storage)

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

    # ADR-047 §D7: falha persistente do backend de storage → 503 em vez de 500
    # genérico. Padroniza o tratamento para todas as rotas de leitura sem exigir
    # try/except individual em cada uma. Não setamos Retry-After aqui: o
    # SlowAPIMiddleware (ADR-098, headers_enabled=True) já injeta esse header
    # quando aplicável, mas sua presença depende do estado do rate limiter —
    # não é garantida por resposta (ver discussão em #29).
    from concilium.domain.repositories.blob_storage_port import StorageUnavailableError

    @app.exception_handler(StorageUnavailableError)
    async def _storage_unavailable_handler(_req: _Request, exc: StorageUnavailableError) -> _JSONResponse:
        return _JSONResponse(status_code=503, content={"detail": str(exc)})

    # ADR-098: Rate limiting — ordem de middleware: SlowAPI (outer) → JWT (inner)
    from fastapi import Response as _Response
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware

    async def _rate_limit_handler(request: _Request, exc: Exception) -> _Response:
        # Adapta a assinatura genérica `(Request, Exception) -> Response` exigida por
        # `Starlette.add_exception_handler` à assinatura específica de
        # `rate_limit_exceeded_handler(Request, RateLimitExceeded)` — o Starlette só
        # invoca este handler para `RateLimitExceeded` (é a chave de registro abaixo),
        # então o isinstance nunca falha em runtime.
        if not isinstance(exc, RateLimitExceeded):
            raise exc
        return rate_limit_exceeded_handler(request, exc)

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)
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

    from concilium.infrastructure.settings import get_api, get_catalog_digest, get_visibility_digest, startup_check
    from concilium.infrastructure.storage.store_factory import ensure_storage_root

    startup_check()
    ensure_storage_root()

    # ADR-141 D6: só inicia aqui (processo real do servidor), nunca em
    # create_app() — que é importado por testes (TestClient) e não deve
    # nascer um thread real a cada import.
    if get_catalog_digest().enabled:
        from concilium.application.services.catalog.draft_digest_scheduler import get_draft_digest_scheduler

        get_draft_digest_scheduler().start()

    # ADR-143 D8: mesma convenção — desligado por padrão, só liga em processo real.
    if get_visibility_digest().enabled:
        from concilium.application.services.visibility_digest_scheduler import get_visibility_digest_scheduler

        get_visibility_digest_scheduler().start()

    host, port = resolve_api_bind()
    reload = get_api().reload
    uvicorn.run("concilium.presentation.api.app:app", host=host, port=port, reload=reload)
