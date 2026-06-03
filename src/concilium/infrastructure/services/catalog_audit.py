from typing import Any

from concilium.application.orchestrators.catalog_governance import (
    CatalogGovernanceError,
    assert_catalog_healthy,
)
from concilium.application.runtime import Runtime


def perform_catalog_audit(runtime: Runtime, catalogo_id: str, catalogo: dict[str, Any]):
    try:
        assert_catalog_healthy(catalogo_id, catalogo)
    except CatalogGovernanceError as exc:
        raise RuntimeError(f"Erro de governança no catálogo {catalogo_id}: {exc}") from exc


def load_and_audit_catalog(runtime: Runtime, contexto_id: str):
    contexto = runtime.load_contexto(contexto_id)
    catalogo = runtime.load_catalogo(contexto.catalogo_id)
    perform_catalog_audit(runtime, contexto.catalogo_id, catalogo)
