"""ProjectService — parte extraída de project_service.py (mixin _BenchmarkEapMixin)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .._project_service_helpers import (
    _enrich_payload_bdi,
    _enrich_payload_catalog,
    _enrich_payload_encargos,
)
from ._shared import (
    _canonical_eap_to_rows,
    _catalog_is_deficit,
    _debug_storage_info,
    _extract_historical_eap_rows,
    _is_valid_canonical_eap,
    _latest_version_with_eap,
)

if TYPE_CHECKING:
    from ._host_protocol import ProjectServiceHost

    _Base = ProjectServiceHost
else:
    _Base = object

logger = logging.getLogger(__name__)


class _BenchmarkEapMixin(_Base):
    """Métodos de benchmark_eap de ProjectService."""

    @staticmethod
    def _normalize_eap_item(item: dict[str, Any], ordem_padrao: int) -> dict[str, Any] | None:
        def _pick(*keys: str) -> Any:
            for key in keys:
                value = item.get(key)
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                return value
            return None

        item_id = _pick("item_id", "activity_id", "eap_item_id", "id", "codigo")
        cpu_id = _pick("cpu_id", "cpu", "cpu_codigo", "codigo_cpu")
        if not item_id or not cpu_id:
            return None

        ordem_raw = _pick("ordem", "order", "seq")
        try:
            ordem = int(ordem_raw) if ordem_raw is not None else ordem_padrao
        except (TypeError, ValueError):
            ordem = ordem_padrao

        quantitativo_raw = _pick("quantitativo", "quantidade", "qtd", "volume")
        try:
            quantitativo = float(quantitativo_raw) if quantitativo_raw is not None else 0.0
        except (TypeError, ValueError):
            quantitativo = 0.0

        normalized = dict(item)
        normalized.update(
            {
                "item_id": str(item_id),
                "ordem": ordem,
                "cpu_id": str(cpu_id),
                "descricao": str(_pick("descricao", "nome", "atividade_descricao") or item_id),
                "unidade": str(_pick("unidade", "un", "und") or "un"),
                "quantitativo": quantitativo,
            }
        )
        return normalized

    @staticmethod
    def _resolve_eap_source(payload: dict[str, Any]) -> str | None:
        cpus_block = payload.get("cpus")
        if isinstance(cpus_block, dict) and isinstance(cpus_block.get("itens_eap"), list):
            return "canonical.cpus.itens_eap"
        if isinstance(payload.get("eap"), list):
            return "historical.eap_root"
        skill_inputs = payload.get("skill_inputs")
        if isinstance(skill_inputs, dict):
            escopo = skill_inputs.get("01-escopo-e-eap")
            if isinstance(escopo, dict):
                if isinstance(escopo.get("eap"), list):
                    return "historical.skill_inputs.01-escopo-e-eap.eap"
                nested = escopo.get("inputs_escopo")
                if isinstance(nested, dict) and isinstance(nested.get("eap"), list):
                    return "historical.skill_inputs.01-escopo-e-eap.inputs_escopo.eap"
        return None

    def _validate_benchmark_reference_contract(self, payload: dict[str, Any]) -> None:
        """Enforce canonical benchmark reference contract for EAP.

        Sprint 3 (NEP-026): historical EAP paths are no longer accepted.
        """
        source = self._resolve_eap_source(payload)
        if source is None:
            raw_cpus_block = payload.get("cpus")
            cpus_block = raw_cpus_block if isinstance(raw_cpus_block, dict) else {}
            cpus_block.setdefault("itens_eap", [])
            payload["cpus"] = cpus_block
            return

        if source != "canonical.cpus.itens_eap":
            logger.error(
                "VAL-CONTRACT-EAP-HISTORICO-BLOQUEADO: source=%s action=reject_historical_payload",
                source,
            )
            raise ValueError(
                "VAL-CONTRACT-EAP-HISTORICO-BLOQUEADO: use somente 'cpus.itens_eap' no benchmark_reference."
            )

        raw_cpus_block = payload.get("cpus")
        cpus_block = raw_cpus_block if isinstance(raw_cpus_block, dict) else {}
        raw_items = [row for row in cpus_block.get("itens_eap", []) if isinstance(row, dict)]
        canonical_items: list[dict[str, Any]] = []
        seen_item_ids: set[str] = set()
        for idx, row in enumerate(raw_items, start=1):
            normalized = self._normalize_eap_item(row, ordem_padrao=idx)
            if normalized is None:
                continue
            item_id = normalized["item_id"]
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)
            canonical_items.append(normalized)
        cpus_block["itens_eap"] = canonical_items
        payload["cpus"] = cpus_block

    @staticmethod
    def _merge_into_cpus_block(payload: dict[str, Any], items: list[dict[str, Any]]) -> None:
        """Funde `items` em payload['cpus']['itens_eap'], preservando o restante do bloco cpus."""
        cpus_block_raw = payload.get("cpus")
        cpus_block: dict[str, Any] = cpus_block_raw if isinstance(cpus_block_raw, dict) else {}
        cpus_block["itens_eap"] = items
        payload["cpus"] = cpus_block

    def _normalize_and_merge_eap_rows(
        self, payload: dict[str, Any], raw_rows: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | None:
        """Normaliza raw_rows e, se não vazio, funde em payload['cpus']['itens_eap']."""
        canonical_items = self._normalize_eap_rows(raw_rows)
        if not canonical_items:
            return None
        self._merge_into_cpus_block(payload, canonical_items)
        return canonical_items

    def _hydrate_eap_from_eap_items(self, payload: dict[str, Any], project: Any) -> str | None:
        """Estágio 1: hidrata cpus.itens_eap a partir de project.eap_items quando o catálogo é inválido."""
        if _is_valid_canonical_eap(payload):
            return None
        eap_items = project.read_json(self._files.eap_items, [])
        eap_rows = [row for row in eap_items if isinstance(row, dict)] if isinstance(eap_items, list) else []
        if not eap_rows:
            return None
        canonical_items = self._normalize_and_merge_eap_rows(payload, eap_rows)
        if not canonical_items:
            return None
        return "eap_items->cpus.itens_eap"

    def _hydrate_eap_from_historical_payload(self, payload: dict[str, Any]) -> str | None:
        """Estágio 2: hidrata cpus.itens_eap a partir de fontes históricas embutidas no próprio payload.

        Roda incondicionalmente (sem checar validade do catálogo) — pode
        sobrescrever o resultado do estágio 1, replicando o comportamento
        original.
        """
        source = self._resolve_eap_source(payload)
        if not source or source == "canonical.cpus.itens_eap":
            return None
        historical_rows = _extract_historical_eap_rows(payload)
        canonical_items = self._normalize_and_merge_eap_rows(payload, historical_rows)
        if not canonical_items:
            return None
        return f"{source}->cpus.itens_eap"

    def _hydrate_eap_from_canonical_payload(self, payload: dict[str, Any], project: Any) -> str | None:
        """Estágio 3: hidrata cpus.itens_eap a partir do canonical.eap da versão atual."""
        if _is_valid_canonical_eap(payload):
            return None
        canonical = project.load_canonical()
        if canonical is None:
            return None
        eap_rows = _canonical_eap_to_rows(canonical)
        if not eap_rows:
            return None
        self._merge_into_cpus_block(payload, eap_rows)
        return "canonical.eap->cpus.itens_eap"

    def _hydrate_eap_from_historical_version(self, payload: dict[str, Any], project: Any) -> str | None:
        """Estágio 4: hidrata cpus.itens_eap a partir da versão histórica mais recente que a possui."""
        if _is_valid_canonical_eap(payload):
            return None
        historical_rows, historical_version = _latest_version_with_eap(project)
        if not historical_rows:
            return None
        self._merge_into_cpus_block(payload, historical_rows)
        return f"historical_canonical.eap:{historical_version or 'unknown'}->cpus.itens_eap"

    def get_benchmark_reference(self, project_id: str) -> dict[str, Any]:
        project = self._repository.get_project(project_id)
        ref_file = self._files.benchmark_reference
        payload = project.read_json(ref_file, {})
        benchmark_source = "benchmark_reference.json"
        if not isinstance(payload, dict):
            raise ValueError("Referencia de benchmark invalida.")

        # Backward compatibility: hydrate missing sections from project runtime state.
        if not isinstance(payload.get("skill_inputs"), dict):
            skill_inputs = project.read_json(self._files.skill_inputs, {})
            if isinstance(skill_inputs, dict):
                payload["skill_inputs"] = skill_inputs

        eap_hydration_stages = (
            lambda: self._hydrate_eap_from_eap_items(payload, project),
            lambda: self._hydrate_eap_from_historical_payload(payload),
            lambda: self._hydrate_eap_from_canonical_payload(payload, project),
            lambda: self._hydrate_eap_from_historical_version(payload, project),
        )
        for stage in eap_hydration_stages:
            new_source = stage()
            if new_source is not None:
                benchmark_source = new_source

        if _catalog_is_deficit(payload.get("catalog")):
            _enrich_payload_catalog(payload, project)
        _enrich_payload_encargos(payload, project)
        _enrich_payload_bdi(payload)
        self._validate_benchmark_reference_contract(payload)
        payload["_debug"] = {
            **_debug_storage_info(project),
            "eap_source": self._resolve_eap_source(payload) or "none",
            "benchmark_reference_source": benchmark_source,
        }
        return payload

