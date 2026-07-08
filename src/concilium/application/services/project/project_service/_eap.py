"""ProjectService — parte extraída de project_service.py (mixin _EapMixin)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .._project_service_helpers import _ps_upsert_eap
from ._shared import (
    _canonical_eap_to_rows,
    _debug_storage_info,
    _extract_canonical_eap_rows,
    _extract_historical_eap_rows,
    _latest_version_with_eap,
    _resolve_project_type,
)

if TYPE_CHECKING:
    from ._host_protocol import ProjectServiceHost

    _Base = ProjectServiceHost
else:
    _Base = object


class _EapMixin(_Base):
    """Métodos de eap de ProjectService."""

    def _normalize_eap_rows(self, raw_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normaliza linhas cruas de EAP, atribuindo ordem padrão e descartando duplicados."""
        normalized_rows: list[dict[str, Any]] = []
        seen_item_ids: set[str] = set()
        for idx, row in enumerate(raw_rows, start=1):
            normalized = self._normalize_eap_item(row, ordem_padrao=idx)
            if normalized is None:
                continue
            item_id = normalized["item_id"]
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)
            normalized_rows.append(normalized)
        return normalized_rows

    def _try_eap_from_benchmark_reference(self, project: Any) -> tuple[list[dict[str, Any]], str] | None:
        """Tenta resolver a EAP a partir do benchmark_reference.json do projeto."""
        ref_payload = project.read_json(self._files.benchmark_reference, {})
        if not isinstance(ref_payload, dict):
            return None
        source = self._resolve_eap_source(ref_payload)
        if source == "canonical.cpus.itens_eap":
            raw_rows = _extract_canonical_eap_rows(ref_payload)
        else:
            raw_rows = _extract_historical_eap_rows(ref_payload)
        normalized_rows = self._normalize_eap_rows(raw_rows)
        if not normalized_rows:
            return None
        return normalized_rows, f"benchmark_reference:{source or 'historical'}"

    @staticmethod
    def _try_eap_from_canonical(project: Any) -> tuple[list[dict[str, Any]], str] | None:
        """Tenta resolver a EAP a partir do canonical.eap da versão atual."""
        canonical = project.load_canonical()
        if canonical is None:
            return None
        eap = _canonical_eap_to_rows(canonical)
        if not eap:
            return None
        return eap, "canonical.eap"

    @staticmethod
    def _try_eap_from_historical(project: Any) -> tuple[list[dict[str, Any]], str] | None:
        """Tenta resolver a EAP a partir da versão histórica mais recente que a possui."""
        historical_rows, historical_version = _latest_version_with_eap(project)
        if not historical_rows:
            return None
        return historical_rows, f"historical_canonical.eap:{historical_version or 'unknown'}"

    def get_eap(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        eap = project.read_json(self._files.eap_items, [])
        eap_source = "project.eap_items"
        if not isinstance(eap, list):
            eap = []

        if not eap:
            result = self._try_eap_from_benchmark_reference(project)
            if result is not None:
                eap, eap_source = result

        if not eap:
            result = self._try_eap_from_canonical(project)
            if result is not None:
                eap, eap_source = result

        if not eap:
            result = self._try_eap_from_historical(project)
            if result is not None:
                eap, eap_source = result

        tipo = _resolve_project_type(project.meta)
        default_status = "ATIVO" if tipo == "hot_project" else "RASCUNHO"
        return {
            "project_id": project_id,
            "status_eap": project.meta.get("status_eap", default_status),
            "items": eap,
            "count": len(eap),
            "_debug": {
                **_debug_storage_info(project),
                "eap_source": eap_source,
            },
        }

    def upsert_eap(self, project_id: str, eap_items: list[dict[str, Any]], actor: str = "system") -> dict[str, Any]:
        return _ps_upsert_eap(self, project_id, eap_items, actor)

