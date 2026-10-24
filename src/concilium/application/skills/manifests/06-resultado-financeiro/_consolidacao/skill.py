"""Skill 06 (_consolidacao) — Consolidação Financeira (Consolidada).

Consolida:
1. Consolidação de Resultado (antiga 06)
2. Reconciliação de Custos de Recurso (antiga 06A)
3. Análise de Compensação Estrutural — The Bridge (ADR-039)

Objetivo: Produzir o balanço final de venda, custo e margem, já considerando impactos de aquisição
e separando os desvios estruturais (escala + clima) do delta real de gestão.
"""

from __future__ import annotations

from typing import Any

from concilium.application.scheduling.skill06_realized_consumer import (
    build_skill06_realized_preview,
)
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    ResultadoReconciliado,
    ValidacaoItem,
)

from ._skill_helpers import _bdi_resolucao as _mod_b  # ty: ignore[unresolved-import]
from ._skill_helpers import (  # ty: ignore[unresolved-import]
    _build_abc_analytics,
    _build_bridge_from_pe,
    _build_diagnostico_pe,
    _build_memorial_bdi,
    _build_ponto_equilibrio,
    _build_resultado,
    enrich_pe_bdi_equivalente,
)

# Re-export abaixo é consumido apenas por testes de cobertura que acessam a
# função interna do helper via este módulo (não usada por run_consolidacao_financeira).
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

    # P11-C is strictly opt-in and fail-closed: no implicit ledger/cost
    # materialization. A partial witness may never produce a plausible GO.
    p11_keys = (
        "p11_financial_reconciliation",
        "p11_scopes_by_activity",
        "p11_bdi_by_category",
        "p11_independent_variable_unit_rate",
    )
    preview = None
    if any(key in inputs for key in p11_keys):
        required = p11_keys[:3]
        if not all(key in inputs for key in required):
            validacoes.append(ValidacaoItem(
                codigo="VAL-P11-PROVENANCE", status="ERRO",
                mensagem="P11 preview requires a complete P20 source, Q and BDI mapping.",
            ))
            return SkillResult(canonical_in, validacoes)
        try:
            preview = build_skill06_realized_preview(
                canonical_in,
                reconciliation=inputs["p11_financial_reconciliation"],
                scopes_by_activity=inputs["p11_scopes_by_activity"],
                bdi_by_category=inputs["p11_bdi_by_category"],
                independent_variable_unit_rate=inputs.get(
                    "p11_independent_variable_unit_rate"
                ),
            )
        except (ValueError, TypeError, KeyError) as exc:
            validacoes.append(ValidacaoItem(
                codigo="VAL-P11-PROVENANCE", status="ERRO",
                mensagem=f"P11 preview evidence failed: {exc}",
            ))
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
        custos_atividades,
    ) = _build_resultado(canonical_in, inputs, validacoes, perfil)

    if preview is not None:
        # Exact rational strings are explicit diagnostics; do not overwrite
        # the old sale/cost/margin fields with a potentially incomplete journal.
        res = res.model_copy(update={"metricas_realizadas_p11": preview})

    ponto_equilibrio_items = _build_ponto_equilibrio(canonical_in, validacoes, perfil)
    enrich_pe_bdi_equivalente(ponto_equilibrio_items, canonical_in.equipes_diretas, bdi_rates)
    recon = ResultadoReconciliado(
        itens_aquisicao=[],
        delta_custo_total=0.0,
        venda_total_com_bdi=venda_catalogo_plus,
        custo_total_reconciliado=custo_total,
        margem_reconciliada_pct=margem,
        status_margem_reconciliado=status_margem,
    )
    bridge_dict, limitacao_clima_n4 = _build_bridge_from_pe(
        ponto_equilibrio_items, venda_sem_bdi, custo_direto_equipe, inputs, validacoes
    )
    if limitacao_clima_n4 is not None:
        # Issue #124: anexa a limitação conhecida ao Resultado como campo de 1ª classe,
        # tipado e com mensagem explicativa (ver LimitacaoClimaN4) — não altera nenhum
        # valor de custo/venda já calculado em `res`.
        res = res.model_copy(update={"limitacao_clima_n4": limitacao_clima_n4})
    _diag_pe, _back_pe = _build_diagnostico_pe(
        canonical_in, custos_atividades, ponto_equilibrio_items, validacoes, _bdi_tabela
    )
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
