"""ADR-078: Pré-processamento Estrutural de Compartilhamento de Recursos.

Funções puras e pipeline de construção do RelatorioOportunidades.

Expõe:
  _gap_max_economico          — gap_r^max a partir de custos mob/demob/idle
  _eta_perpetuacao            — índice de eficiência η ∈ [0, 1]
  _sobreposicao_bundle        — ov_vector + Ω para um par de equipes
  _delta_c_pot                — ΔC potencial para um par (i, j, r)
  _build_pre_processamento_compartilhamento  — pipeline completo

Referência: docs/product/4-research/recursos.md
            docs/engineering/0-architecture/adrs/ADR-078-*.md
"""

from __future__ import annotations

import math
from typing import Any

from concilium.domain.models.canonical import (
    OportunidadeCompartilhamento,
    RelatorioOportunidades,
    ValidacaoItem,
)

# Tipos de faturamento sem custo de ociosidade (c_idle = 0)
_UNIDADE_SEM_IDLE: frozenset[str] = frozenset({"hora_prod"})

# Sentinel para gap_max "infinito"
_GAP_MAX_INFINITO: int = 9999


# ──────────────────────────────────────────────────────────────────────────────
# Funções puras
# ──────────────────────────────────────────────────────────────────────────────


def _gap_max_economico(
    custo_mob: float,
    custo_demob: float,
    custo_idle_semanal: float,
    unidade_faturamento: str,
) -> int:
    """Retorna o gap máximo (semanas) em que a perpetuação ainda é viável.

    Condição de viabilidade: (c_mob + c_demob) > g × c_idle
    → g_max = ceil(budget / c_idle) − 1   [strict inequality]

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

    # gap_max = ceil(budget / c_idle) − 1
    # Verificação: g_max × c_idle < budget  (strict)
    return max(0, math.ceil(budget / custo_idle_semanal) - 1)


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
    soma_ov_custo = sum(
        ov_vector.get(tipo, 0) * mob_demob_costs.get(tipo, 0.0)
        for tipo in ov_vector
    )
    return soma_ov_custo * max(0.0, eta)


# ──────────────────────────────────────────────────────────────────────────────
# Helper interno: converter semana "S001" ou "2026-W01" → índice inteiro
# ──────────────────────────────────────────────────────────────────────────────


def _week_to_idx(week_str: str) -> int:
    """Converte "S001" → 1, "S042" → 42, "2026-W48" → 48, etc."""
    s = week_str.strip()
    if s.upper().startswith("S"):
        try:
            return int(s[1:])
        except ValueError:
            pass
    if "W" in s:
        try:
            return int(s.split("W")[-1])
        except ValueError:
            pass
    return 0


# ──────────────────────────────────────────────────────────────────────────────
# Pipeline principal
# ──────────────────────────────────────────────────────────────────────────────


def _build_pre_processamento_compartilhamento(
    contratos_recurso: list[Any],
    rcpsp_spec: dict[str, Any],
    cron_lookup: dict[str, Any],
    validacoes: list[ValidacaoItem],
) -> RelatorioOportunidades | None:
    """Fase 0 do ADR-078: pré-processamento estrutural de compartilhamento.

    Calcula gap_r^max, η, Ω e ΔC_pot para todos os pares de atividades que
    compartilham um tipo de recurso com `resource_costs` configurado.

    Quando `rcpsp_spec` não contém `resource_costs`, emite
    VAL-PRE-PROCESSAMENTO-SKIP e retorna None.

    Args:
        contratos_recurso: lista de RecursoContrato (mutável — campos mob/demob
                           são atualizados in-place)
        rcpsp_spec: dicionário do spec RCPSP (com chave opcional "resource_costs")
        cron_lookup: {item_id: ScheduledActivityCanonical} com semana_inicio/fim
        validacoes: lista acumuladora de ValidacaoItem

    Returns:
        RelatorioOportunidades com oportunidades ordenadas por delta_c_pot desc,
        ou None se resource_costs ausente.
    """
    resource_costs: dict[str, dict] = rcpsp_spec.get("resource_costs") or {}

    if not resource_costs:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-PRE-PROCESSAMENTO-SKIP",
                status="AVISO",
                mensagem=(
                    "ADR-078: resource_costs ausente no rcpsp_spec — "
                    "pré-processamento de compartilhamento ignorado."
                ),
            )
        )
        return None

    # ── 1. Construir lookup de custos por tipo ────────────────────────────────
    gap_max_por_tipo: dict[str, int] = {}
    mob_demob_por_tipo: dict[str, float] = {}  # c_mob + c_demob per unit

    for tipo_id, costs in resource_costs.items():
        # Ignorar entradas que não são dicts (e.g., "_comment": "...")
        if not isinstance(costs, dict):
            continue
        c_mob = float(costs.get("custo_mob_unit", 0.0))
        c_demob = float(costs.get("custo_demob_unit", 0.0))
        c_idle = float(costs.get("custo_idle_semanal_unit", 0.0))
        unidade = str(costs.get("unidade_faturamento", "hora_prod"))

        gap_max_por_tipo[tipo_id] = _gap_max_economico(c_mob, c_demob, c_idle, unidade)
        mob_demob_por_tipo[tipo_id] = c_mob + c_demob

    # ── 2. Atualizar RecursoContrato in-place ────────────────────────────────
    for contrato in contratos_recurso:
        tipo_id = getattr(contrato, "tipo_id", None)
        if tipo_id and tipo_id in resource_costs:
            costs = resource_costs[tipo_id]
            contrato.custo_mob_unit = float(costs.get("custo_mob_unit", 0.0))
            contrato.custo_demob_unit = float(costs.get("custo_demob_unit", 0.0))
            contrato.custo_idle_semanal_unit = float(
                costs.get("custo_idle_semanal_unit", 0.0)
            )
            contrato.unidade_faturamento = str(
                costs.get("unidade_faturamento", "hora_prod")
            )
            contrato.gap_max_economico = gap_max_por_tipo[tipo_id]

    # ── 3. Construir lookup de requisitos por atividade ───────────────────────
    # {item_id: {tipo_id: quantidade}}
    activity_resources: dict[str, dict[str, int]] = {}
    for act in rcpsp_spec.get("activities", []):
        item_id = act.get("item_id", "")
        reqs = act.get("required_resources", {})
        if item_id and reqs:
            activity_resources[item_id] = {k: int(v) for k, v in reqs.items()}

    # ── 4. Para cada tipo com resource_costs, enumerar pares (i, j) ──────────
    oportunidades: list[OportunidadeCompartilhamento] = []
    tem_inviavel = False

    # Iterar apenas sobre tipos válidos (dict entries — ignora "_comment" e similares)
    for tipo_id in sorted(gap_max_por_tipo):
        costs_t = resource_costs[tipo_id]
        c_mob = float(costs_t.get("custo_mob_unit", 0.0))
        c_demob = float(costs_t.get("custo_demob_unit", 0.0))
        c_idle = float(costs_t.get("custo_idle_semanal_unit", 0.0))
        unidade = str(costs_t.get("unidade_faturamento", "hora_prod"))
        gap_max = gap_max_por_tipo[tipo_id]

        # Atividades que usam este tipo
        atividades_tipo = [
            (iid, reqs[tipo_id])
            for iid, reqs in activity_resources.items()
            if tipo_id in reqs
        ]

        if len(atividades_tipo) < 2:
            continue

        # Ordenar por semana_inicio para enumerar pares canonicamente
        def _start_idx(iid: str) -> int:
            sa = cron_lookup.get(iid)
            if sa is None:
                return 0
            return _week_to_idx(getattr(sa, "semana_inicio", "S000"))

        def _end_idx(iid: str) -> int:
            sa = cron_lookup.get(iid)
            if sa is None:
                return 0
            return _week_to_idx(getattr(sa, "semana_fim", "S000"))

        atividades_tipo.sort(key=lambda x: _start_idx(x[0]))

        # Enumerar todos os pares (a, b) — determinar ordem temporal depois
        for idx_a, (id_a, q_a) in enumerate(atividades_tipo):
            for id_b, q_b in atividades_tipo[idx_a + 1:]:
                end_a = _end_idx(id_a)
                start_b = _start_idx(id_b)
                end_b = _end_idx(id_b)
                start_a = _start_idx(id_a)

                # Determinar quem termina antes (i = anterior, j = posterior)
                if end_a <= start_b:
                    i_id, j_id, q_i, q_j = id_a, id_b, q_a, q_b
                    gap = start_b - end_a
                elif end_b <= start_a:
                    i_id, j_id, q_i, q_j = id_b, id_a, q_b, q_a
                    gap = start_a - end_b
                else:
                    # Sobreposição temporal — não gera oportunidade de perpetuação
                    continue

                eta = _eta_perpetuacao(gap, c_mob, c_demob, c_idle, unidade)
                ov = {tipo_id: min(q_i, q_j)}
                max_q = max(q_i, q_j)
                omega = min(q_i, q_j) / max_q if max_q > 0 else 0.0
                mob_costs = {tipo_id: c_mob + c_demob}
                delta = _delta_c_pot(q_i, q_j, ov, eta, mob_costs)
                lambda0 = delta * omega
                viavel = gap <= gap_max

                if not viavel:
                    tem_inviavel = True

                oportunidades.append(
                    OportunidadeCompartilhamento(
                        atividade_i=i_id,
                        atividade_j=j_id,
                        tipo_id=tipo_id,
                        gap_semanas=gap,
                        gap_max_semanas=gap_max,
                        eta=round(eta, 6),
                        omega_bundle=round(omega, 6),
                        delta_c_pot=round(delta, 2),
                        lambda0=round(lambda0, 2),
                        recursos_compartilhaveis=ov,
                        economicamente_viavel=viavel,
                    )
                )

    # ── 5. Ordenar por delta_c_pot decrescente ────────────────────────────────
    oportunidades.sort(key=lambda o: -o.delta_c_pot)

    # ── 6. Métricas agregadas ─────────────────────────────────────────────────
    total_economia = sum(o.delta_c_pot for o in oportunidades if o.economicamente_viavel)
    podadas = sum(1 for o in oportunidades if not o.economicamente_viavel)
    lambda0_total = sum(o.lambda0 for o in oportunidades if o.economicamente_viavel)

    relatorio = RelatorioOportunidades(
        total_oportunidades=len(oportunidades),
        total_economia_pot=round(total_economia, 2),
        oportunidades_podadas=podadas,
        lambda0_total=round(lambda0_total, 2),
        oportunidades=oportunidades,
        gap_max_por_tipo=gap_max_por_tipo,
    )

    # ── 7. Validadores ────────────────────────────────────────────────────────
    n_viaveis = len(oportunidades) - podadas
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-PRE-PROCESSAMENTO-OK",
            status="OK",
            mensagem=(
                f"ADR-078: {len(oportunidades)} oportunidade(s) avaliada(s) para "
                f"{len(gap_max_por_tipo)} tipo(s) — "
                f"{n_viaveis} viável(is), {podadas} podada(s). "
                f"Economia potencial: R$ {total_economia:,.2f}. "
                f"λ_0 total: R$ {lambda0_total:,.2f}."
            ),
        )
    )

    if tem_inviavel:
        inviáveis_desc = [
            f"{o.atividade_i}→{o.atividade_j} "
            f"({o.tipo_id}, gap={o.gap_semanas}w > max={o.gap_max_semanas}w)"
            for o in oportunidades
            if not o.economicamente_viavel
        ]
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-OPT-INVIAVEL",
                status="AVISO",
                mensagem=(
                    f"ADR-078: {podadas} aresta(s) inviável(is) "
                    f"(gap > gap_r^max) excluídas de G_r^viável: "
                    + "; ".join(inviáveis_desc[:5])
                    + ("..." if podadas > 5 else "")
                ),
            )
        )

    return relatorio
