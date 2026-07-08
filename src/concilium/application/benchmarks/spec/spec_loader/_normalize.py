"""BenchmarkSpecLoader — normalização de schema e enriquecimento de EAP."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from concilium.infrastructure.catalog.catalog_loader import CatalogLoader

from .._spec_loader_helpers_a import (
    _ebr_apply_fallbacks,
    _ebr_from_por_item,
    _ebr_from_stats,
    _norm_ref_atividades_to_eap,
    _norm_ref_datas_block,
    _norm_ref_ensure_rcpsp_spec,
    _norm_ref_metas_confronto,
    _norm_ref_projeto_block,
)
from .._spec_loader_helpers_b import _ea_normalize_itens_eap, _eei_find_best_match
from ._v2_schema import _unpack_v2_schema

if TYPE_CHECKING:
    from ._host_protocol import BenchmarkSpecLoaderHost as _Base
else:
    _Base = object


class _NormalizeMixin(_Base):
    def _normalize_reference_schema(self, ref: dict[str, Any]) -> dict[str, Any]:
        """Normaliza schemas de referência para o formato legado esperado pelo loader.

        Compatibiliza o novo modo `benchmark_config` sem quebrar referências antigas.
        Suporta schema v2 (meta+spec+resultado) quando a chave 'spec' está presente.
        """
        if not isinstance(ref, dict):
            return ref
        # v2: presença de 'spec' indica schema reorganizado → normaliza para v1-compat
        if "spec" in ref:
            ref = _unpack_v2_schema(ref)
        mode = str(ref.get("mode") or "").strip().lower()
        if mode != "benchmark_config":
            return ref
        out = dict(ref)
        raw_projeto = out.get("projeto")
        raw_datas = out.get("datas")
        raw_regime = out.get("regime")
        projeto_block: dict[str, Any] = raw_projeto if isinstance(raw_projeto, dict) else {}
        datas_block: dict[str, Any] = raw_datas if isinstance(raw_datas, dict) else {}
        regime_block: dict[str, Any] = raw_regime if isinstance(raw_regime, dict) else {}
        _norm_ref_projeto_block(out, projeto_block)
        _norm_ref_datas_block(out, datas_block)
        if regime_block and not out.get("regime_trabalho"):
            out["regime_trabalho"] = {
                "horas_dia": regime_block.get("horas_dia", 8),
                "dias_semana": regime_block.get("dias_semana", 6),
            }
        _norm_ref_atividades_to_eap(out)
        _norm_ref_metas_confronto(out)
        _norm_ref_ensure_rcpsp_spec(out)
        return out


    @staticmethod
    def _extract_eap(ref: dict[str, Any]) -> list[dict[str, Any]]:
        """Extrai EAP em formatos de referência distintos.

        Suporta:
        - Formato canônico de benchmark: ref["eap"]
        - Formato de iteração extraída: ref["cpus"]["itens_eap"]
        """
        eap_direct = ref.get("eap")
        if isinstance(eap_direct, list) and eap_direct:
            return eap_direct
        itens_eap = (ref.get("cpus") or {}).get("itens_eap")
        if not (isinstance(itens_eap, list) and itens_eap):
            return []
        return _ea_normalize_itens_eap(itens_eap)


    @staticmethod
    def _extract_bdi_rates(ref: dict[str, Any]) -> dict[str, float]:
        """Extrai BDI final por categoria em referências no formato extraído.

        Fontes suportadas:
        - ref["bdi"]["estatisticas_componentes"][<categoria>]["media"]
        - ref["bdi"]["por_item"][*]["bdi"][<categoria>] (fallback)
        """
        bdi_ref = ref.get("bdi") or {}
        stats = bdi_ref.get("estatisticas_componentes") or {}
        mapped = _ebr_from_stats(stats)
        if not mapped:
            mapped = _ebr_from_por_item(bdi_ref)
        _ebr_apply_fallbacks(mapped)
        return mapped


    def _enrich_eap_with_cpu_ids(
        self, eap: list[dict[str, Any]], contexto_id: str = "mendeslobo"
    ) -> list[dict[str, Any]]:
        if not eap:
            return eap
        if all(item.get("cpu_id") for item in eap):
            return eap
        try:
            loader = CatalogLoader(
                config_root=self._config_root,
                project_root=self._project_root,
                offline=False,
                force_refresh=False,
            )
            snapshot, _ = loader.load(contexto_id)
        except Exception as exc:
            try:
                snapshot, _ = loader.load("mendeslobo")
            except Exception:
                print(f"  [WARN] Falha ao carregar catalogo para normalizar EAP ({contexto_id}): {exc}")
                return eap
        cpus = snapshot.cpus or []
        cpu_by_codigo = {cpu.get("codigo"): cpu for cpu in cpus if cpu.get("codigo")}
        for item in eap:
            _eei_find_best_match(item, cpus, cpu_by_codigo)
        return eap


