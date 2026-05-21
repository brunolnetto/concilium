"""DiagnosticoPEBuilder — decomposição causal do gap de PE (ADR-060).

Fórmulas exatas (ADR-060 §3):
  C_real = c_fixo/S × N_total + c_diesel/S × Q̃   (diesel cancela no gap)
  gap_direto = c_fixo/S × N_total × (1 − η_real)
  η_real = Σ p(t)n(t) / Σ n(t)
  ε_cross = η_real − p̄ + Cov(n,p)/n̄
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.diagnostico_pe import (
    DiagnosticoPEItem,
    DiagnosticoPERelatorio,
    FatorPE,
)

_CROSS_TERM_THRESHOLD = 0.05


def _compute_item_metrics(active: list) -> dict[str, float]:
    """Calcula η_real, p_medio, cov_np, eps_cross, validade a partir das semanas ativas."""
    N_total = sum(d.num_equipes for d in active)
    prod_weighted = sum(d.eficiencia * d.num_equipes for d in active)
    eta_real = prod_weighted / N_total if N_total > 0 else 1.0
    T_weeks = len(active)
    p_medio = sum(d.eficiencia for d in active) / T_weeks
    n_medio = N_total / T_weeks
    cov_np = prod_weighted / T_weeks - p_medio * n_medio
    eps_cross = eta_real - p_medio + cov_np / n_medio if n_medio > 0 else 0.0
    validade = abs(cov_np / (n_medio * p_medio)) < _CROSS_TERM_THRESHOLD if n_medio * p_medio > 0 else True
    return {
        "N_total": N_total,
        "prod_weighted": prod_weighted,
        "eta_real": eta_real,
        "T_weeks": T_weeks,
        "p_medio": p_medio,
        "n_medio": n_medio,
        "cov_np": cov_np,
        "eps_cross": eps_cross,
        "validade": validade,
    }


def _build_gap_fatores(
    c_fixo_semanal: float,
    metrics: dict[str, float],
    ca: Any,
    canonical_in: Any,
    gap_total: float,
    resultado: Any,
) -> tuple[tuple[FatorPE, ...], float]:
    """Decompõe o gap em fatores causais e retorna (fatores, f1_rs)."""
    N_total = metrics["N_total"]
    eta_real = metrics["eta_real"]
    p_medio = metrics["p_medio"]

    gap_direto_estimado = c_fixo_semanal * N_total * (1.0 - eta_real)
    gap_ind_estimado = float((ca.custo_indireto_atribuido if ca else 0) * (1.0 - eta_real))
    gap_total_estimado = gap_direto_estimado + gap_ind_estimado
    escala = abs(gap_total) / max(abs(gap_total_estimado), 1.0) if gap_total_estimado else 1.0

    f_eta_clima_rs = c_fixo_semanal * N_total * max(0.0, 1.0 - p_medio) * escala
    f_cross_rs = c_fixo_semanal * N_total * max(0.0, p_medio - eta_real) * escala
    f_ind_clima_rs = gap_ind_estimado * p_medio / max(eta_real, 0.01) * escala if eta_real < p_medio else 0.0
    f_ind_ramp_rs = max(0.0, gap_ind_estimado * escala - f_ind_clima_rs)
    f_residual_rs = max(0.0, abs(gap_total) - f_eta_clima_rs - f_cross_rs - f_ind_clima_rs - f_ind_ramp_rs)

    f1_rs = 0.0
    if canonical_in.bridge_analysis and isinstance(canonical_in.bridge_analysis, dict):
        n1 = float(canonical_in.bridge_analysis.get("nivel_1_catalogo_base") or 0)
        n2 = float(canonical_in.bridge_analysis.get("nivel_2_catalogo_escalado") or 0)
        if n1 > 0 and n2 > n1:
            proj_total = float(getattr(getattr(resultado, "custo", None), "total", 1) or 1)
            f1_rs = abs(gap_total) * (n2 - n1) / max(proj_total, 1.0)

    fatores_raw = [
        ("F_ETA_CLIMA", f_eta_clima_rs),
        ("F_ETA_CROSS", f_cross_rs),
        ("F_IND_CLIMA", f_ind_clima_rs),
        ("F_IND_RAMP", f_ind_ramp_rs),
        ("F1_QUANTIZACAO", f1_rs),
        ("F_RESIDUAL", f_residual_rs),
    ]
    total_attr = sum(v for _, v in fatores_raw)
    fatores = tuple(
        FatorPE(codigo=cod, gap_rs=round(v, 2), pct_gap=round(v / max(total_attr, 1.0), 4))
        for cod, v in sorted(fatores_raw, key=lambda kv: kv[1], reverse=True)
        if v > 0.50
    )
    return fatores, f1_rs


def _resolve_pe_prices(pe: Any, plan: Any, ca: Any) -> tuple[float, float]:
    """Retorna (preco_venda, custo_real) priorizando dados de plano/ca sobre PE."""
    preco_venda = float(
        (plan.subtotal.com_bdi.total if plan and plan.subtotal and plan.subtotal.com_bdi else 0) or pe.custo_venda_cpu
    )
    custo_real = float((ca.custo_total_atividade if ca else 0) or pe.custo_operacional_real or pe.custo_fixo_equipe)
    return preco_venda, custo_real


def _compute_recalibracao_l(gap_total: float, plan: Any, T_efetivo: float) -> float:
    """Calcula delta_l necessário para fechar o gap de PE."""
    C_cat = float((plan.subtotal.sem_bdi.total if plan and plan.subtotal and plan.subtotal.sem_bdi else 0) or 1)
    return abs(gap_total) / max(C_cat / (1.0 - T_efetivo), 1.0) if C_cat > 0 else 0.0


def _process_pe_item(
    pe: Any,
    equipe_lookup: dict,
    sched_lookup: dict,
    plan_lookup: dict,
    ca_lookup: dict,
    eap_lookup: dict,
    L_aplicado: float,
    T_efetivo: float,
    canonical_in: Any,
    resultado: Any,
) -> tuple[DiagnosticoPEItem | None, bool]:
    """Processa um item PE e retorna (item_diagnóstico, cross_term_presente) ou (None, False)."""
    item_id = pe.item_id
    eap = eap_lookup.get(item_id)
    equipe = equipe_lookup.get(item_id)
    sa = sched_lookup.get(item_id)
    plan = plan_lookup.get(item_id)
    ca = ca_lookup.get(item_id)

    preco_venda, custo_real = _resolve_pe_prices(pe, plan, ca)
    gap_total = preco_venda - custo_real

    if not equipe or not sa or not sa.distribuicao_semanal:
        return None, False
    active = [d for d in sa.distribuicao_semanal.values() if d.num_equipes > 0]
    if not active:
        return None, False

    metrics = _compute_item_metrics(active)
    c_fixo_semanal = (equipe.custo_mao_obra_mensal + equipe.custo_equipamentos_mensal) / SEMANAS_POR_MES
    fatores, _ = _build_gap_fatores(c_fixo_semanal, metrics, ca, canonical_in, gap_total, resultado)

    delta_l = _compute_recalibracao_l(gap_total, plan, T_efetivo)
    descricao = str(eap.descricao if eap and hasattr(eap, "descricao") else item_id)
    cpu_id = str(eap.cpu_id if eap else "?")

    return DiagnosticoPEItem(
        atividade_id=item_id,
        cpu_id=cpu_id,
        descricao=descricao[:80],
        preco_venda=round(preco_venda, 2),
        custo_realizado=round(custo_real, 2),
        gap_rs=round(gap_total, 2),
        pct_gap_sobre_venda=round(gap_total / max(preco_venda, 1.0), 4),
        eta_real=round(metrics["eta_real"], 4),
        p_medio_uniforme=round(metrics["p_medio"], 4),
        cov_n_p=round(metrics["cov_np"], 6),
        eps_cross=round(metrics["eps_cross"], 6),
        validez_aproximacao=metrics["validade"],
        n_total=round(metrics["N_total"], 2),
        fatores=fatores,
        l_aplicado=round(L_aplicado, 4),
        l_requerido=round(L_aplicado + delta_l, 4),
        delta_l=round(delta_l, 4),
    ), not metrics["validade"]


def _build_relatorio_summary(
    projeto_id: str,
    itens_diag: list[DiagnosticoPEItem],
    cross_term_presente: bool,
    norm_tol_pct: float,
) -> DiagnosticoPERelatorio:
    gap_total_sum = sum(i.gap_rs for i in itens_diag)
    gap_evit = sum(i.gap_evitavel_rs for i in itens_diag)
    gap_estrt = sum(i.gap_estrutural_rs for i in itens_diag)

    todas_causas: dict[str, float] = defaultdict(float)
    for item in itens_diag:
        for f in item.fatores:
            todas_causas[f.label] += f.gap_rs
    fator_dom = max(todas_causas, key=lambda k: todas_causas[k]) if todas_causas else "—"

    l_medio = (
        sum(i.l_requerido * abs(i.gap_rs) for i in itens_diag) / max(sum(abs(i.gap_rs) for i in itens_diag), 1.0)
        if itens_diag
        else 0.0
    )

    validacoes: list[str] = []
    if cross_term_presente:
        validacoes.append("VAL-PE-CROSS-TERM")
    sum_fatores = sum(sum(f.gap_rs for f in i.fatores) for i in itens_diag)
    consistencia = (
        abs(gap_total_sum) < 1.0 or abs(sum_fatores - abs(gap_total_sum)) / max(abs(gap_total_sum), 1.0) < norm_tol_pct
    )
    if not consistencia:
        validacoes.append("VAL-PE-NORM-FAIL")

    return DiagnosticoPERelatorio(
        projeto_id=projeto_id,
        gerado_em=datetime.now(UTC).isoformat(),
        n_itens_deficit=len(itens_diag),
        gap_total_rs=round(gap_total_sum, 2),
        gap_evitavel_rs=round(gap_evit, 2),
        gap_estrutural_rs=round(gap_estrt, 2),
        fator_dominante_label=fator_dom,
        aviso_cross_term=cross_term_presente,
        l_medio_requerido=round(l_medio, 4),
        itens_deficit=tuple(sorted(itens_diag, key=lambda i: i.gap_rs)),
        consistencia_validada=consistencia,
        validacoes_emitidas=tuple(validacoes),
    )


class DiagnosticoPEBuilder:
    """Constrói DiagnosticoPERelatorio a partir do canonical pós-Skill 08."""

    # Tolerância de normalização: soma dos fatores ≈ gap_total
    NORM_TOL_PCT = 0.02  # 2%
    # Threshold para detectar cross-term significativo
    CROSS_TERM_THRESHOLD = 0.05

    def build(
        self,
        canonical_in: Any,
        bdi_rates: dict[str, float] | None = None,
    ) -> DiagnosticoPERelatorio:
        projeto_id = str(getattr(getattr(canonical_in, "projeto", None), "nome", "?"))
        pe_items = canonical_in.ponto_equilibrio or []
        deficit_items = [p for p in pe_items if p.delta < 0]

        if not deficit_items:
            return DiagnosticoPERelatorio(
                projeto_id=projeto_id,
                gerado_em=datetime.now(UTC).isoformat(),
                n_itens_deficit=0,
                gap_total_rs=0.0,
                gap_evitavel_rs=0.0,
                gap_estrutural_rs=0.0,
                fator_dominante_label="—",
                aviso_cross_term=False,
                l_medio_requerido=0.0,
                itens_deficit=(),
                consistencia_validada=True,
            )

        sched_lookup = {
            sa.activity_id: sa
            for sa in (canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else [])
        }
        equipe_lookup = {e.item_id: e for e in (canonical_in.equipes_diretas or [])}
        plan_lookup = {p.item_id: p for p in (canonical_in.planejamento or [])}
        ca_lookup = {ca.atividade_id: ca for ca in (canonical_in.custos_atividades or [])}
        eap_lookup = {e.item_id: e for e in (canonical_in.eap or [])}
        resultado = canonical_in.resultado
        L_aplicado = float(getattr(getattr(resultado, "venda", None), "bdi_lucro_impostos", 0.09) or 0.09)
        T_efetivo = 0.1338

        itens_diag: list[DiagnosticoPEItem] = []
        cross_term_presente = False

        for pe in deficit_items:
            item, cross = _process_pe_item(
                pe,
                equipe_lookup,
                sched_lookup,
                plan_lookup,
                ca_lookup,
                eap_lookup,
                L_aplicado,
                T_efetivo,
                canonical_in,
                resultado,
            )
            if item is not None:
                itens_diag.append(item)
            if cross:
                cross_term_presente = True

        return _build_relatorio_summary(projeto_id, itens_diag, cross_term_presente, self.NORM_TOL_PCT)
