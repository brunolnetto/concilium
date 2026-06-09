"""Skill 09 — Diagnóstico de Criticidade (Consolidado).

Consolida:
1. Criticidade de Prazo (antiga 08)
2. Criticidade de Custo e Recursos (antiga 09)

Objetivo: Fornecer um diagnóstico de saúde 360° (Prazo, Custo, Recurso, Sensibilidade).
"""

from __future__ import annotations

import math
from typing import Any

from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    CostCriticalityResult,
    CriticidadeProfile,
    DimensaoCriticidade,
    ValidacaoItem,
)


def _periodo_to_ordinal(p):
    if "W" in p:
        y, w = p.split("-W")
        return int(y) * 53 + int(w)
    y, m = p.split("-")
    return int(y) * 12 + int(m)


def _percentil_rank(values):
    n = len(values)
    if n == 0:
        return []
    sorted_vals = sorted(values)
    return [sorted_vals.index(v) / max(n - 1, 1) for v in values]


def _rank_descending(values):
    indexed = sorted(enumerate(values), key=lambda x: -x[1])
    ranks = [0] * len(values)
    for pos, (orig_idx, _) in enumerate(indexed):
        ranks[orig_idx] = pos + 1
    return ranks


def _classify(rank: int, n: int, on_frontier: bool) -> str:
    """Classifica atividade por rank lexicográfico em A+/A/B/C."""
    top_20 = math.ceil(n * 0.2)
    top_40 = math.ceil(n * 0.4)
    top_70 = math.ceil(n * 0.7)
    if on_frontier and rank <= top_20:
        return "A+"
    if rank <= top_40:
        return "A"
    if rank <= top_70:
        return "B"
    return "C"


def _build_timings(scheduled_activities: list) -> dict:
    timings: dict = {}
    for sa in scheduled_activities:
        meses = sorted([p for p, d in sa.distribuicao_semanal.items() if d.qtd_executada > 0])
        if meses:
            start_m = _periodo_to_ordinal(meses[0])
            end_m = _periodo_to_ordinal(meses[-1])
            timings[sa.activity_id] = {
                "start": meses[0],
                "end": meses[-1],
                "start_m": start_m,
                "end_m": end_m,
                "duration": end_m - start_m + 1,
            }
    return timings


def _analyze_schedule_timings(scheduled_activities: list) -> tuple:
    timings = _build_timings(scheduled_activities)
    proj_end_m = max((t["end_m"] for t in timings.values()), default=0)
    proj_start_m = min((t["start_m"] for t in timings.values()), default=0)
    proj_dur = proj_end_m - proj_start_m + 1 if timings else 1
    critical_set = {aid for aid, t in timings.items() if t["end_m"] == proj_end_m}
    return timings, proj_end_m, proj_start_m, proj_dur, critical_set


def _build_atvs_crit_recurso(alocacoes: list) -> set:
    return {a.atividade_id for a in alocacoes if a.criticidade_recurso == "CONSTRANGIDO"}


def _build_raw_item(eq: object, timings: dict, proj_dur: int, custo_total_obra: float, atvs_crit_recurso: set) -> dict:
    aid = eq.item_id  # type: ignore[attr-defined]
    t = timings.get(aid, {"duration": 0, "start_m": 0, "end_m": 0})
    dur_share = t["duration"] / proj_dur if proj_dur > 0 else 0
    cost_share = eq.custo_total / custo_total_obra if custo_total_obra > 0 else 0  # type: ignore[attr-defined]
    return {
        "atividade_id": aid,
        "cost_share": cost_share,
        "duration_share": dur_share,
        "is_time_critical": aid in atvs_crit_recurso,
        "recurso_critico": aid in atvs_crit_recurso,
        "recurso_float": 1.0 if aid in atvs_crit_recurso else 0.0,
        "margin_sensitivity": eq.custo_mao_obra_mensal * eq.permanencia_meses / (eq.custo_total or 1),  # type: ignore[attr-defined]
    }


def _build_raw_list(
    equipes: list,
    timings: dict,
    proj_dur: int,
    custo_total_obra: float,
    atvs_crit_recurso: set,
) -> list:
    return [_build_raw_item(eq, timings, proj_dur, custo_total_obra, atvs_crit_recurso) for eq in equipes]


def _compute_rankings(raw: list) -> tuple:
    pcts_custo = _percentil_rank([r["cost_share"] for r in raw])
    pcts_dur = _percentil_rank([r["duration_share"] for r in raw])
    pcts_rec = _percentil_rank([r["recurso_float"] for r in raw])
    pcts_sens = _percentil_rank([r["margin_sensitivity"] for r in raw])
    ranks_custo = _rank_descending([r["cost_share"] for r in raw])
    ranks_dur = _rank_descending([r["duration_share"] for r in raw])
    ranks_rec = _rank_descending([r["recurso_float"] for r in raw])
    ranks_sens = _rank_descending([r["margin_sensitivity"] for r in raw])
    return pcts_custo, pcts_dur, pcts_rec, pcts_sens, ranks_custo, ranks_dur, ranks_rec, ranks_sens


def _compute_severity_scores(raw: list) -> list[float]:
    """Combina dimensões de criticidade em um score único determinístico.

    Priorizamos custo e duração (impacto financeiro/cronograma), sem perder sinal de
    recurso e sensibilidade. Pesos estáveis evitam classificação por ordem de entrada.
    """
    scores: list[float] = []
    for r in raw:
        score = (
            float(r["cost_share"]) * 0.50
            + float(r["duration_share"]) * 0.25
            + float(r["recurso_float"]) * 0.15
            + float(r["margin_sensitivity"]) * 0.10
        )
        scores.append(score)
    return scores


def _build_lexicographic_ranks(raw: list, severity_scores: list[float]) -> list[int]:
    order = sorted(range(len(raw)), key=lambda idx: (-severity_scores[idx], str(raw[idx]["atividade_id"])))
    ranks = [0] * len(raw)
    for pos, idx in enumerate(order, 1):
        ranks[idx] = pos
    return ranks


def _build_profiles(
    raw: list,
    pcts_custo: list,
    pcts_dur: list,
    pcts_rec: list,
    pcts_sens: list,
    ranks_custo: list,
    ranks_dur: list,
    ranks_rec: list,
    ranks_sens: list,
) -> list:
    severity_scores = _compute_severity_scores(raw)
    lex_ranks = _build_lexicographic_ranks(raw, severity_scores)
    top_20 = math.ceil(len(raw) * 0.2)
    profiles: list[CriticidadeProfile] = []
    for i, r in enumerate(raw):
        rank_lex = lex_ranks[i]
        on_frontier = rank_lex <= top_20
        profiles.append(
            CriticidadeProfile(
                atividade_id=r["atividade_id"],
                custo=DimensaoCriticidade(
                    valor_raw=r["cost_share"], rank=ranks_custo[i], percentil=round(pcts_custo[i], 4)
                ),
                duracao=DimensaoCriticidade(
                    valor_raw=r["duration_share"], rank=ranks_dur[i], percentil=round(pcts_dur[i], 4)
                ),
                recurso=DimensaoCriticidade(
                    valor_raw=r["recurso_float"], rank=ranks_rec[i], percentil=round(pcts_rec[i], 4)
                ),
                sensibilidade=DimensaoCriticidade(
                    valor_raw=round(r["margin_sensitivity"], 4), rank=ranks_sens[i], percentil=round(pcts_sens[i], 4)
                ),
                pareto_frontier=on_frontier,
                rank_lexicografico=rank_lex,
                classe=_classify(rank_lex, len(raw), on_frontier),
                interpretacao="Análise consolidada",
            )
        )
    return profiles


def run_diagnostico_criticidade(
    canonical_in: CanonicalModel,
    inputs: dict[str, Any],
) -> SkillResult:
    validacoes: list[ValidacaoItem] = []

    # ADR-XXX: Graceful degradation for minimalista benchmarks
    # If equipes_diretas is empty or has zero cost, it means pool-based costing
    # (from rcpsp_spec) was not used. Costs may come from skill-06/08 via PUxQ.
    # Proceed with cronograma analysis only, returning AVISO instead of ERRO.
    custo_total_obra = sum(eq.custo_total for eq in (canonical_in.equipes_diretas or []))
    equipes_disponivel = canonical_in.equipes_diretas and len(canonical_in.equipes_diretas) > 0

    if equipes_disponivel and custo_total_obra == 0:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-CC-01",
                status="AVISO",
                mensagem="Equipes diretas sem custo. Diagnóstico limitado ao cronograma. (Custos calculados por skill-06/08 via PUxQ)",
            )
        )
        equipes_disponivel = False  # Degrade gracefully

    if not canonical_in.cronograma:
        validacoes.append(ValidacaoItem(codigo="VAL-DIAG-PRE", status="ERRO", mensagem="Cronograma necessário."))
        return SkillResult(canonical_in, validacoes)

    timings, proj_end_m, proj_start_m, proj_dur, critical_set = _analyze_schedule_timings(
        canonical_in.cronograma.scheduled_activities
    )

    if not timings:
        validacoes.append(ValidacaoItem(codigo="VAL-DIAG-01", status="AVISO", mensagem="Sem execução no cronograma"))

    # ADR-XXX: Build cost criticality only if equipes data is available
    # Otherwise skip detailed resource analysis (cost comes from skill-06/08 via PUxQ)
    report = None
    if equipes_disponivel:
        custo_total_obra = sum(eq.custo_total for eq in (canonical_in.equipes_diretas or []))
        atvs_crit_recurso = _build_atvs_crit_recurso(canonical_in.alocacoes)
        raw = _build_raw_list(canonical_in.equipes_diretas, timings, proj_dur, custo_total_obra, atvs_crit_recurso)
        rankings = _compute_rankings(raw)
        profiles = _build_profiles(raw, *rankings)
        report = CostCriticalityResult(
            atividades=profiles, n_pareto_frontier=len(profiles), n_atividades=len(profiles), criterio_primario="custo"
        )
    else:
        # Graceful degradation: empty criticality report when equipes unavailable
        report = CostCriticalityResult(atividades=[], n_pareto_frontier=0, n_atividades=0, criterio_primario="custo")

    novo = canonical_in.model_copy(
        update={
            "cost_criticality_report": report,
            "criticality_report": {"project_duration_meses": proj_dur, "critical_path": list(critical_set)},
        }
    )
    validacoes.append(
        ValidacaoItem(codigo="VAL-DIAG-OK", status="OK", mensagem="Diagnóstico de criticidade concluído.")
    )
    return SkillResult(novo, validacoes)
