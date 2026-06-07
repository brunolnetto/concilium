"""Skill 06 — Consolidação Financeira (Consolidada).

Consolida:
1. Consolidação de Resultado (antiga 06)
2. Reconciliação de Custos de Recurso (antiga 06A)
3. Análise de Compensação Estrutural — The Bridge (ADR-039)

Objetivo: Produzir o balanço final de venda, custo e margem, já considerando impactos de aquisição
e separando os desvios estruturais (escala + clima) do delta real de gestão.
"""

from __future__ import annotations

from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    ResultadoReconciliado,
    ValidacaoItem,
)

try:
    from ._skill_helpers_a import (
        _build_bridge,
        _build_custos_atividades,
        _build_diagnostico_pe,
        _build_ponto_equilibrio,
        _build_resultado,
    )
    from ._skill_helpers_b import (
        _build_abc_analytics,
        _build_memorial_bdi,
        _classificar_margem,
    )
except ImportError:
    import importlib.util
    from pathlib import Path

    _here = Path(__file__).resolve().parent
    _spec_a = importlib.util.spec_from_file_location("skill08_helpers_a", _here / "_skill_helpers_a.py")
    _mod_a = importlib.util.module_from_spec(_spec_a)  # type: ignore[arg-type]
    _spec_a.loader.exec_module(_mod_a)  # type: ignore[union-attr]

    _spec_b = importlib.util.spec_from_file_location("skill08_helpers_b", _here / "_skill_helpers_b.py")
    _mod_b = importlib.util.module_from_spec(_spec_b)  # type: ignore[arg-type]
    _spec_b.loader.exec_module(_mod_b)  # type: ignore[union-attr]

    _build_bridge = _mod_a._build_bridge
    _build_custos_atividades = _mod_a._build_custos_atividades
    _build_diagnostico_pe = _mod_a._build_diagnostico_pe
    _build_ponto_equilibrio = _mod_a._build_ponto_equilibrio
    _build_resultado = _mod_a._build_resultado
    _build_abc_analytics = _mod_b._build_abc_analytics
    _build_memorial_bdi = _mod_b._build_memorial_bdi
    _classificar_margem = _mod_b._classificar_margem


def run_consolidacao_financeira(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
    perfil: dict[str, Any],
) -> SkillResult:
    validacoes: list[ValidacaoItem] = []

    if not canonical_in.equipes_diretas or not canonical_in.planejamento:
        validacoes.append(
            ValidacaoItem(codigo="VAL-CONSOL-PRE", status="ERRO", mensagem="Equipes e Planejamento necessários.")
        )
        return SkillResult(canonical_in, validacoes)

    (
        res,
        bdi_rates,
        _bdi_tabela,
        _bdi_fonte,
        _bdi_regime,
        _bdi_override,
        venda_sem_bdi,
        venda_catalogo_plus,
        margem,
        custo_direto_equipe,
        status_margem,
        venda_plus,
        custo_total,
        custo_total_catalogo,
    ) = _build_resultado(canonical_in, inputs, validacoes, perfil)

    ponto_equilibrio_items = _build_ponto_equilibrio(canonical_in, validacoes)
    recon = ResultadoReconciliado(
        itens_aquisicao=[],
        delta_custo_total=0.0,
        venda_total_com_bdi=venda_catalogo_plus,
        custo_total_reconciliado=custo_total,
        margem_reconciliada_pct=margem,
        status_margem_reconciliado=status_margem,
    )
    bridge_dict = _build_bridge(inputs, venda_sem_bdi, custo_direto_equipe, validacoes)
    custos_atividades = _build_custos_atividades(canonical_in)
    _diag_pe, _back_pe = _build_diagnostico_pe(canonical_in, custos_atividades, validacoes)
    curva_abc, s_curve, cubo_analitico = _build_abc_analytics(
        canonical_in, inputs, _bdi_tabela, _bdi_regime, validacoes
    )
    # O memorial usa resultado financeiro consolidado; ele precisa enxergar o canônico já enriquecido.
    canonical_for_memorial = canonical_in.model_copy(update={"resultado": res})
    memorial = _build_memorial_bdi(canonical_for_memorial, _bdi_fonte, _bdi_regime, _bdi_tabela, _bdi_override)

    novo = canonical_in.model_copy(
        update={
            "resultado": res,
            "resultado_reconciliado": recon,
            "bridge_analysis": bridge_dict,
            "ponto_equilibrio": ponto_equilibrio_items,
            "custos_atividades": custos_atividades,
            "memorial_calculo_bdi": memorial,
            "curva_abc_insumo": curva_abc,
            "s_curve": s_curve,
            "cubo_analitico": cubo_analitico,
            "diagnostico_pe": _diag_pe,
            "backtracking_pe": _back_pe,
            # Persiste a tabela BDI efetiva para garantir formulação consistente
            # em lazy-builds do serviço e no _build_from_pool do ADR-086.
            "tabela_bdi_efetiva": _bdi_tabela,
        }
    )
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-CONSOL-OK", status="OK", mensagem=f"Consolidação concluída. Margem: {margem * 100:.2f}%"
        )
    )
    return SkillResult(novo, validacoes)
