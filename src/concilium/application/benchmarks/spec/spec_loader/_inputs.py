"""BenchmarkSpecLoader — construção de inputs de escopo e indiretos."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .._spec_loader_helpers_b import _bii_build_detalhe_por_cat, _bii_build_entry, _bii_scale_categories

if TYPE_CHECKING:
    from ._host_protocol import BenchmarkSpecLoaderHost as _Base
else:
    _Base = object


class _InputsMixin(_Base):
    @staticmethod
    def _lfd_build_inputs_escopo(
        projeto_nome: str,
        localizacao: Any,
        regime_trabalho: dict,
        data_ini: str,
        data_fim: str,
        eap: list[dict[str, Any]],
        ref: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "nome": projeto_nome,
            "tipo_obra": "terraplenagem",
            # localizacao: string legada OU {lat, lng} normalizado. coordenadas é
            # alias retrocompat — se localizacao já é {lat,lng}, reusa o mesmo dict.
            "localizacao": localizacao or "Brasil",
            "coordenadas": (
                localizacao if isinstance(localizacao, dict) else ref.get("coordenadas", {"lat": 0.0, "lng": 0.0})
            ),
            "regime_trabalho": regime_trabalho,
            "data_inicio": data_ini,
            "data_termino": data_fim,
            "eap": [item for item in eap if item.get("cpu_id")],
        }


    @staticmethod
    def _lfd_static_extra_inputs() -> dict[str, Any]:
        """Blocos de inputs fixos (baseline automática) para skills 08 e 09."""
        return {
            "08-avaliacao-intervencoes": {
                "intervencoes_propostas": [
                    {
                        "nome": "Baseline Automatica",
                        "custo_estimado": 0,
                        "impacto_prazo_semanas": 0,
                        "justificativa": "Ponto de partida para benchmark de engenharia.",
                    }
                ]
            },
            "09-registro-decisoes": {
                "objective": "Aprovacao de Baseline para Auditoria Financeira",
                "considered_interventions": [
                    {
                        "nome": "Baseline Automatica",
                        "variavel": "baseline",
                        "custo_estimado": 0,
                        "impacto_prazo_semanas": 0,
                        "justificativa": "Ponto de partida para benchmark de engenharia.",
                    }
                ],
                "selected_intervention": "baseline",
                "justification": {
                    "main_reason": "Alinhamento com dados de referencia historicos.",
                    "rejected_reasons": {},
                },
                "decided_by": {
                    "type": "system",
                    "id": "benchmark_runner",
                },
            },
        }


    @staticmethod
    def _build_inputs_indiretos(
        ind_ref: dict[str, Any],
        weeks: list[str],
        referencia_indireto_total: float | None,
        equipes_indiretas: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not ind_ref:
            return {}
        detalhe_por_cat = _bii_build_detalhe_por_cat(equipes_indiretas or [])
        permanencia_meses = len(weeks) / 4.34
        categorias_config = [_bii_build_entry(cat, data, detalhe_por_cat) for cat, data in ind_ref.items() if data]
        if not categorias_config:
            return {}
        _bii_scale_categories(categorias_config, referencia_indireto_total, permanencia_meses)
        return {"categorias_config": categorias_config}


