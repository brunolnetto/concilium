"""ConciliumService — parte extraída de concilium_service.py (mixin _CatalogMixin)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from concilium.application.runtime import Runtime

from .._concilium_service_helpers import (
    _cs_get_enriched_cpus,
    _cs_upsert_catalog_cpu,
    _enrich_cpus_with_producao,
)
from ..catalog.catalog_reasonability import build_catalog_reasonability_artifact

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object

logger = logging.getLogger(__name__)


class _CatalogMixin(_Base):
    """Métodos de catalog de ConciliumService."""

    def upsert_catalog_cpu(
        self,
        catalog_id: str,
        cpu_id: str,
        cpu_data: dict[str, Any],
        actor: str = "system",
        motivo: str = "",
    ) -> dict[str, Any]:
        """Create or replace a CPU in the master catalog (ADR-067)."""
        return _cs_upsert_catalog_cpu(self, catalog_id, cpu_id, cpu_data, actor, motivo)

    def list_catalogs(self) -> list[dict[str, Any]]:
        cats_dir = self.config_root / "catalogos"
        if not cats_dir.exists():
            return []
        return sorted(
            [{"id": d.name} for d in cats_dir.iterdir() if d.is_dir() and not d.name.startswith(".")],
            key=lambda x: x["id"],
        )

    def get_catalog(self, catalog_id: str) -> dict[str, Any]:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        return {
            "id": catalog_id,
            "n_cpus": len(cat.get("cpus", [])),
            "n_insumos": len(cat.get("insumos", [])),
            "n_producoes": len(cat.get("producoes", [])),
        }

    def _get_enriched_cpus(self, catalog_id: str) -> list[dict[str, Any]]:
        return _cs_get_enriched_cpus(self, catalog_id)

    @staticmethod
    def _enrich_cpus_with_producao(cat: dict) -> list[dict[str, Any]]:
        return _enrich_cpus_with_producao(cat)

    def list_catalog_cpus(self, catalog_id: str, q: str | None = None, limit: int = 50) -> dict[str, Any]:
        cpus = self._get_enriched_cpus(catalog_id)
        if q:
            q_lower = q.lower()
            cpus = [
                c
                for c in cpus
                if q_lower in (c.get("codigo") or "").lower() or q_lower in (c.get("descricao") or "").lower()
            ]
        return {"catalog_id": catalog_id, "items": cpus[:limit], "total": len(cpus)}

    def get_catalog_cpu(self, catalog_id: str, cpu_id: str) -> dict[str, Any] | None:
        for cpu in self._get_enriched_cpus(catalog_id):
            if cpu.get("codigo") == cpu_id:
                return cpu
        return None

    def list_catalog_insumos(self, catalog_id: str, q: str | None = None, limit: int = 50) -> dict[str, Any]:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        insumos = cat.get("insumos", [])
        if q:
            q_lower = q.lower()
            insumos = [
                i
                for i in insumos
                if q_lower in (i.get("codigo") or "").lower() or q_lower in (i.get("descricao") or "").lower()
            ]
        return {"catalog_id": catalog_id, "items": insumos[:limit], "total": len(insumos)}

    def search_catalog(self, q: str, catalog_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        results: list[dict] = []
        cats = [catalog_id] if catalog_id else [d["id"] for d in self.list_catalogs()]
        q_lower = q.lower()
        for cid in cats:
            try:
                self._search_catalog_in(cid, q_lower, results, limit)
            except Exception as e:
                logger.warning("Falha ao buscar no catálogo %s: %s", cid, e, exc_info=True)
                continue
            if len(results) >= limit:
                break
        return {"q": q, "items": results[:limit], "total": len(results)}

    def audit_catalog_reasonability(self, catalog_id: str) -> dict[str, Any]:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        raw_cpus = cat.get("cpus")
        cpus = raw_cpus if isinstance(raw_cpus, list) else []
        raw_produtividades = cat.get("produtividades")
        raw_producoes = cat.get("producoes")
        produtividades = raw_produtividades if isinstance(raw_produtividades, list) else []
        producoes_legado = raw_producoes if isinstance(raw_producoes, list) else []
        producoes = produtividades + producoes_legado
        return build_catalog_reasonability_artifact(catalog_id, cpus, producoes)

    def _search_catalog_in(self, cid: str, q_lower: str, results: list, limit: int) -> None:
        for cpu in self._get_enriched_cpus(cid):
            codigo = (cpu.get("codigo") or "").lower()
            descricao = (cpu.get("descricao") or "").lower()
            if q_lower in codigo or q_lower in descricao:
                results.append({**cpu, "_catalog_id": cid})
            if len(results) >= limit:
                break

