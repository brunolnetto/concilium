"""Routes for system health."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from concilium.presentation.api.container import ServiceContainer

router = APIRouter(tags=["system"])


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/swagger")


@router.get("/health", summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/catalog/reload", summary="Invalidate in-memory catalog cache and force reload from disk")
def reload_catalog() -> dict[str, object]:
    """Limpa o _config_cache de catálogos em memória e deleta o bundle em disco.

    Use quando novos arquivos de catálogo forem adicionados via volume sem reiniciar
    o container. O próximo run irá reconstruir o bundle a partir dos arquivos atuais.
    """
    try:
        container = ServiceContainer.instance()
        runtime = container.concilium_service.deps.pipeline_service._runtime_factory()
        # Limpa apenas as entradas de catálogo do cache (preserva outros dados)
        catalogo_keys = [k for k in runtime._config_cache if k.startswith("catalogo:")]
        for k in catalogo_keys:
            del runtime._config_cache[k]

        # Deleta o bundle em disco para forçar reconstrução completa na próxima carga
        from concilium.presentation.cli.shared import config_root

        cfg = config_root()
        deleted_bundles = []
        for bundle in cfg.rglob(".catalog_bundle.json"):
            bundle.unlink(missing_ok=True)
            deleted_bundles.append(str(bundle.relative_to(cfg)))

        return {
            "status": "ok",
            "catalog_cache_keys_cleared": len(catalogo_keys),
            "bundles_deleted": deleted_bundles,
            "message": "Cache em memória e bundles em disco invalidados. Próximo run recarrega do filesystem.",
        }
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
