"""ConciliumService — parte extraída de concilium_service.py (mixin _CpuResolutionMixin)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from concilium.application.runtime import Runtime

if TYPE_CHECKING:
    from ._host_protocol import ConciliumServiceHost

    _Base = ConciliumServiceHost
else:
    _Base = object

logger = logging.getLogger(__name__)


class _CpuResolutionMixin(_Base):
    """Métodos de cpu_resolution de ConciliumService."""

    def extend_cpu(self, project_id: str, cpu_id: str, cpu_data: dict, actor: str = "system", motivo: str = "") -> None:
        self._dependencies.override_service.extend_cpu(project_id, cpu_id, cpu_data, actor=actor, motivo=motivo)

    def get_project_catalog_overrides(self, project_id: str) -> dict:
        """Return the current CPU overlay dict for a project (ADR-066)."""
        project = self._dependencies.repository.get_project(project_id)
        overlay = project.read_json("overrides/cpus_overlay.json", {})
        return overlay if isinstance(overlay, dict) else {}

    def set_cpu_contexto(self, project_id: str, cpu_id: str, contexto: str, actor: str = "system") -> None:
        """ADR-148: contexto de projeto complementar à descrição de CPU (texto livre, sem aprovação)."""
        self._dependencies.override_service.set_cpu_contexto(project_id, cpu_id, contexto, actor=actor)

    def get_cpu_contexto(self, project_id: str, cpu_id: str) -> str | None:
        """ADR-148: contexto de projeto complementar à descrição de CPU (texto livre, sem aprovação)."""
        return self._dependencies.override_service.get_cpu_contexto(project_id, cpu_id)

    def list_cpu_contextos(self, project_id: str) -> dict[str, str]:
        """ADR-148: dict[cpu_id, contexto] completo do projeto — para hidratação em lote na UI."""
        return self._dependencies.override_service.list_cpu_contextos(project_id)

    def resolve_cpu(self, project_id: str, cpu_id: str) -> dict | None:
        candidate = self._dependencies.override_service.resolve_cpu(project_id, cpu_id)

        project = self._dependencies.repository.get_project(project_id)
        master_cpu = None
        for catalog_id in self._candidate_catalog_ids(project):
            try:
                master_cpu = self.get_catalog_cpu(catalog_id, cpu_id)
            except Exception as e:
                logger.error("Falha ao resolver CPU %s no catálogo %s: %s", cpu_id, catalog_id, e, exc_info=True)
                master_cpu = None
            if master_cpu:
                break

        if candidate and master_cpu:
            # Preserve project-level fields while inheriting richer master composition.
            result = {**master_cpu, **candidate}
        elif candidate:
            result = self._enrich_cpu_from_producao(project, dict(candidate))
        elif master_cpu:
            result = master_cpu
        else:
            result = candidate

        # ADR-148: contexto de projeto é sempre complementar — anexado independentemente
        # da fonte que resolveu a CPU (override/catálogo base/snapshot), nunca a substitui.
        if result is not None:
            contexto = self.get_cpu_contexto(project_id, cpu_id)
            if contexto:
                result = {**result, "contexto_projeto": contexto}
        return result

    def _candidate_catalog_ids(self, project: Any) -> list[str]:
        """Resolve possible catalog IDs for project CPU enrichment."""
        meta = project.meta if isinstance(project.meta, dict) else {}
        ids: list[str] = []

        base_catalog = str(meta.get("catalogo_base") or "").strip()
        if base_catalog:
            ids.append(base_catalog)

        contexto_catalog = self._resolve_project_catalog_id(project)
        if contexto_catalog:
            ids.append(contexto_catalog)

        contexto_id = str(meta.get("contexto_id") or "").strip()
        if contexto_id:
            ids.append(contexto_id)

        dedup: list[str] = []
        seen: set[str] = set()
        for cid in ids:
            if cid and cid not in seen:
                seen.add(cid)
                dedup.append(cid)
        return dedup

    def _apply_producao_fields(self, cpu: dict[str, Any], prod: dict[str, Any]) -> None:
        """Applies producao_horaria/equipe fields from a producao catalog entry into cpu (in-place)."""
        if cpu.get("producao_horaria") is None and prod.get("valor_horario") is not None:
            cpu["producao_horaria"] = prod.get("valor_horario")
        if not cpu.get("equipe"):
            equipe = prod.get("equipe")
            if not isinstance(equipe, dict):
                equipe = prod.get("composicao_padrao_equipe")
            if isinstance(equipe, dict):
                cpu["equipe"] = equipe

    def _enrich_cpu_from_producao(self, project: Any, cpu: dict[str, Any]) -> dict[str, Any]:
        """Inject producao_horaria/equipe from catalog produtividade when CPU is sparse."""
        if cpu.get("equipe") and cpu.get("producao_horaria") is not None:
            return cpu

        prod_id = str(cpu.get("producao_id_ref") or cpu.get("producao_id") or "").strip()
        if not prod_id:
            return cpu

        for catalog_id in self._candidate_catalog_ids(project):
            prod = self._get_catalog_producao(catalog_id, prod_id)
            if not prod:
                continue
            self._apply_producao_fields(cpu, prod)
            if cpu.get("equipe") and cpu.get("producao_horaria") is not None:
                break

        return cpu

    def _get_catalog_producao(self, catalog_id: str, prod_id: str) -> dict[str, Any] | None:

        rt = Runtime(self.config_root)
        cat = rt.load_catalogo(catalog_id)
        for key in ("produtividades", "producoes"):
            rows = cat.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if isinstance(row, dict) and str(row.get("id") or "") == prod_id:
                    return row
        return None

    def _fetch_contexto_versions(self, contexto_id: str) -> list[Any]:
        """Lista as versões do contexto, retornando [] em caso de falha (com log de erro)."""
        try:
            return self._dependencies.project_service.list_contexto_versions(contexto_id)
        except Exception as e:
            logger.error("Falha ao listar versões do contexto %s: %s", contexto_id, e, exc_info=True)
            return []

    def _select_contexto_version(self, versions: list[Any], contexto_version: str) -> Any:
        """Seleciona a versão de contexto solicitada, ou a mais recente como fallback."""
        selected = None
        if contexto_version:
            selected = next((v for v in versions if str(v.get("version") or "") == contexto_version), None)
        if selected is None:
            selected = versions[-1]
        return selected

    def _resolve_project_catalog_id(self, project: Any) -> str | None:
        """Resolve current catalog id for a project via contexto version metadata."""
        meta = project.meta if isinstance(project.meta, dict) else {}
        contexto_id = str(meta.get("contexto_id") or "").strip()
        if not contexto_id:
            return None

        versions = self._fetch_contexto_versions(contexto_id)
        if not versions:
            return contexto_id

        contexto_version = str(meta.get("contexto_version") or "").strip()
        selected = self._select_contexto_version(versions, contexto_version)

        catalog_id = str((selected or {}).get("catalogo_id") or "").strip()
        return catalog_id or contexto_id

