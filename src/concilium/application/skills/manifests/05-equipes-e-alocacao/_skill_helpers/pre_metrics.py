"""ADR-078/ADR-133 — pré-processamento e detecção de oportunidades de compartilhamento.

Métricas econômicas puras (gap máximo, eta de perpetuação, sobreposição, delta de custo).
"""

from __future__ import annotations

from fractions import Fraction

from .week_index import iso_week_index  # ty: ignore[unresolved-import]

_UNIDADE_SEM_IDLE: frozenset[str] = frozenset({"hora_prod"})


_GAP_MAX_INFINITO: int = 9999


def _gap_max_economico(
    custo_mob: float,
    custo_demob: float,
    custo_idle_semanal: float,
    unidade_faturamento: str,
) -> int:
    """Retorna o gap máximo (semanas) em que a perpetuação ainda é viável.

    Condição de viabilidade: g × c_idle <= (c_mob + c_demob)
    → g_max = floor((c_mob+c_demob) / c_idle), inclusive on exact ties.

    Tie-breaking keeps the same physical instances contracted and avoids
    unnecessary movements. This must match the Skill 05 chain builder.

    Para `hora_prod` ou c_idle == 0, retorna _GAP_MAX_INFINITO (9999).

    Args:
        custo_mob: custo de mobilização por unidade de recurso (R$)
        custo_demob: custo de desmobilização por unidade (R$)
        custo_idle_semanal: custo semanal por unidade em standby (R$)
        unidade_faturamento: "hora_prod" | "dia_cal" | "mes"

    Returns:
        Número inteiro de semanas (gap_r^max).
    """
    if unidade_faturamento in _UNIDADE_SEM_IDLE or custo_idle_semanal <= 0.0:
        return _GAP_MAX_INFINITO

    budget = custo_mob + custo_demob
    if budget <= 0.0:
        return 0

    # Same exact inclusive tariff boundary as _resolve_gap_max_e_idle_efetivo.
    # Avoid float rounding at an integral gap (notably decimal 0.1+0.2).
    exact_budget = Fraction(str(custo_mob)) + Fraction(str(custo_demob))
    return max(0, int(exact_budget // Fraction(str(custo_idle_semanal))))


def _eta_perpetuacao(
    gap_semanas: int,
    custo_mob: float,
    custo_demob: float,
    custo_idle_semanal: float,
    unidade_faturamento: str,
) -> float:
    """Retorna o índice de eficiência η ∈ [0.0, 1.0] para uma perpetuação com gap g.

    η = 1 − (g × c_idle) / (c_mob + c_demob)

    η = 1.0 quando:
      - gap == 0 (atividades adjacentes — nenhuma semana idle)
      - unidade_faturamento == "hora_prod" (sem custo idle)
      - custo_idle_semanal == 0

    η ≤ 0.0 quando gap ≥ gap_r^max; clampado a 0.0.

    Args:
        gap_semanas: número de semanas entre fim(i) e início(j)
        custo_mob: R$/unidade — mobilização
        custo_demob: R$/unidade — desmobilização
        custo_idle_semanal: R$/unidade/semana — standby contínuo
        unidade_faturamento: "hora_prod" | "dia_cal" | "mes"

    Returns:
        float em [0.0, 1.0]
    """
    if gap_semanas <= 0:
        return 1.0
    if unidade_faturamento in _UNIDADE_SEM_IDLE or custo_idle_semanal <= 0.0:
        return 1.0

    total_mob_demob = custo_mob + custo_demob
    if total_mob_demob <= 0.0:
        return 0.0

    eta = 1.0 - (gap_semanas * custo_idle_semanal) / total_mob_demob
    return max(0.0, min(1.0, eta))


def _sobreposicao_bundle(
    equipe_i: dict[str, int],
    equipe_j: dict[str, int],
    mob_demob_costs: dict[str, float],
) -> tuple[dict[str, int], float]:
    """Calcula o vetor de sobreposição ov_{ij} e o índice econômico Ω_{ij}.

    ov_{ij,r} = min(e_i_r, e_j_r)

    Ω = Σ_r [ov_r × cost_r] / Σ_r [max(e_i_r, e_j_r) × cost_r]

    Recursos ausentes em um dos lados têm ov = 0.

    Args:
        equipe_i: {tipo_id: quantidade} para a atividade i
        equipe_j: {tipo_id: quantidade} para a atividade j
        mob_demob_costs: {tipo_id: c_mob + c_demob} por unidade

    Returns:
        (ov_vector, omega) onde ov_vector = {tipo: min(qi, qj)} e omega ∈ [0,1]
    """
    todos_tipos = set(equipe_i) | set(equipe_j)
    ov: dict[str, int] = {}
    numerador = 0.0
    denominador = 0.0

    for tipo in sorted(todos_tipos):
        q_i = equipe_i.get(tipo, 0)
        q_j = equipe_j.get(tipo, 0)
        ov[tipo] = min(q_i, q_j)
        custo = mob_demob_costs.get(tipo, 0.0)
        numerador += ov[tipo] * custo
        denominador += max(q_i, q_j) * custo

    omega = numerador / denominador if denominador > 0.0 else 0.0
    return ov, omega


def _delta_c_pot(
    q_i: int,
    q_j: int,
    ov_vector: dict[str, int],
    eta: float,
    mob_demob_costs: dict[str, float],
) -> float:
    """ΔC_ij^pot — economia potencial máxima do par (i, j) para um tipo de recurso.

    ΔC = Σ_r [ov_r × (c_mob_r + c_demob_r)] × η

    O fator `min(q_i, q_j)` já está embutido no ov_vector (= min por tipo).
    Recursos fora de mob_demob_costs têm custo zero e não contribuem.

    Args:
        q_i: quantidade total do recurso na atividade i (para fins de contexto)
        q_j: quantidade total do recurso na atividade j
        ov_vector: {tipo: min(q_i, q_j)} — da _sobreposicao_bundle
        eta: índice de eficiência η
        mob_demob_costs: {tipo: c_mob + c_demob} por unidade

    Returns:
        float R$ — economia potencial descontada por η
    """
    soma_ov_custo = sum(ov_vector.get(tipo, 0) * mob_demob_costs.get(tipo, 0.0) for tipo in ov_vector)
    return soma_ov_custo * max(0.0, eta)


def _week_to_idx(week_str: str) -> int:
    """Convert legacy S-index or ISO week to a comparable absolute index."""
    s = week_str.strip()
    if s.upper().startswith("S"):
        if s[1:].isdigit():
            return int(s[1:])
        raise ValueError(f"invalid legacy week index: {week_str!r}")
    if "-W" in s:
        return iso_week_index(s)
    if s.isdigit():
        return int(s)
    raise ValueError(f"unsupported week index: {week_str!r}")


