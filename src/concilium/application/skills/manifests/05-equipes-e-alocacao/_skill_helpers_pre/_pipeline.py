"""ADR-078/ADR-110 — pré-processamento e detecção de oportunidades de compartilhamento.

Pipeline de construção do RelatorioOportunidades (ADR-078).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    OportunidadeCompartilhamento,
    RelatorioOportunidades,
    ValidacaoItem,
)

from ._metrics import _delta_c_pot, _eta_perpetuacao, _gap_max_economico, _week_to_idx  # ty: ignore[unresolved-import]


def _bppc_build_gap_max_lookup(resource_costs: dict[str, dict]) -> dict[str, int]:
    """Constrói gap_r^max por tipo de recurso a partir de resource_costs (ignora entradas não-dict)."""
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

    return gap_max_por_tipo


def _bppc_atualizar_contratos(
    contratos_recurso: list[Any], resource_costs: dict[str, dict], gap_max_por_tipo: dict[str, int]
) -> None:
    """Atualiza RecursoContrato in-place com os custos e gap_max_economico do tipo correspondente."""
    for contrato in contratos_recurso:
        tipo_id = getattr(contrato, "tipo_id", None)
        if tipo_id and tipo_id in resource_costs:
            costs = resource_costs[tipo_id]
            contrato.custo_mob_unit = float(costs.get("custo_mob_unit", 0.0))
            contrato.custo_demob_unit = float(costs.get("custo_demob_unit", 0.0))
            contrato.custo_idle_semanal_unit = float(costs.get("custo_idle_semanal_unit", 0.0))
            contrato.unidade_faturamento = str(costs.get("unidade_faturamento", "hora_prod"))
            contrato.gap_max_economico = gap_max_por_tipo[tipo_id]


def _bppc_build_activity_resources(rcpsp_spec: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Constrói {item_id: {tipo_id: quantidade}} a partir das activities do rcpsp_spec."""
    activity_resources: dict[str, dict[str, int]] = {}
    for act in rcpsp_spec.get("activities", []):
        item_id = act.get("item_id", "")
        reqs = act.get("required_resources", {})
        if item_id and reqs:
            activity_resources[item_id] = {k: int(v) for k, v in reqs.items()}
    return activity_resources


def _bppc_par_oportunidade(
    id_a: str,
    q_a: int,
    id_b: str,
    q_b: int,
    tipo_id: str,
    gap_max: int,
    c_mob: float,
    c_demob: float,
    c_idle: float,
    unidade: str,
    start_idx: Any,
    end_idx: Any,
) -> OportunidadeCompartilhamento | None:
    """Avalia o par (id_a, id_b) e retorna a oportunidade de compartilhamento, se houver ordem temporal."""
    end_a = end_idx(id_a)
    start_b = start_idx(id_b)
    end_b = end_idx(id_b)
    start_a = start_idx(id_a)

    # Determinar quem termina antes (i = anterior, j = posterior)
    if end_a <= start_b:
        i_id, j_id, q_i, q_j = id_a, id_b, q_a, q_b
        gap = start_b - end_a
    elif end_b <= start_a:
        i_id, j_id, q_i, q_j = id_b, id_a, q_b, q_a
        gap = start_a - end_b
    else:
        # Sobreposição temporal — não gera oportunidade de perpetuação
        return None

    eta = _eta_perpetuacao(gap, c_mob, c_demob, c_idle, unidade)
    ov = {tipo_id: min(q_i, q_j)}
    max_q = max(q_i, q_j)
    omega = min(q_i, q_j) / max_q if max_q > 0 else 0.0
    mob_costs = {tipo_id: c_mob + c_demob}
    delta = _delta_c_pot(q_i, q_j, ov, eta, mob_costs)
    lambda0 = delta * omega
    viavel = gap <= gap_max

    return OportunidadeCompartilhamento(
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


def _bppc_oportunidades_por_tipo(
    tipo_id: str,
    resource_costs: dict[str, dict],
    gap_max_por_tipo: dict[str, int],
    activity_resources: dict[str, dict[str, int]],
    cron_lookup: dict[str, Any],
) -> list[OportunidadeCompartilhamento]:
    """Enumera todos os pares (i, j) de atividades que compartilham `tipo_id` e avalia cada oportunidade."""
    costs_t = resource_costs[tipo_id]
    c_mob = float(costs_t.get("custo_mob_unit", 0.0))
    c_demob = float(costs_t.get("custo_demob_unit", 0.0))
    c_idle = float(costs_t.get("custo_idle_semanal_unit", 0.0))
    unidade = str(costs_t.get("unidade_faturamento", "hora_prod"))
    gap_max = gap_max_por_tipo[tipo_id]

    # Atividades que usam este tipo
    atividades_tipo = [(iid, reqs[tipo_id]) for iid, reqs in activity_resources.items() if tipo_id in reqs]

    if len(atividades_tipo) < 2:
        return []

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
    oportunidades: list[OportunidadeCompartilhamento] = []
    for idx_a, (id_a, q_a) in enumerate(atividades_tipo):
        for id_b, q_b in atividades_tipo[idx_a + 1 :]:
            oport = _bppc_par_oportunidade(
                id_a, q_a, id_b, q_b, tipo_id, gap_max, c_mob, c_demob, c_idle, unidade, _start_idx, _end_idx
            )
            if oport is not None:
                oportunidades.append(oport)
    return oportunidades


def _bppc_append_validacoes(
    validacoes: list[ValidacaoItem],
    oportunidades: list[OportunidadeCompartilhamento],
    podadas: int,
    total_economia: float,
    lambda0_total: float,
    gap_max_por_tipo: dict[str, int],
) -> None:
    """Adiciona (in-place) os ValidacaoItem de resultado e, se houver, de arestas inviáveis."""
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

    if podadas:
        inviáveis_desc = [
            f"{o.atividade_i}→{o.atividade_j} ({o.tipo_id}, gap={o.gap_semanas}w > max={o.gap_max_semanas}w)"
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
                    "ADR-078: resource_costs ausente no rcpsp_spec — pré-processamento de compartilhamento ignorado."
                ),
            )
        )
        return None

    # ── 1. Construir lookup de custos por tipo ────────────────────────────────
    gap_max_por_tipo = _bppc_build_gap_max_lookup(resource_costs)

    # ── 2. Atualizar RecursoContrato in-place ────────────────────────────────
    _bppc_atualizar_contratos(contratos_recurso, resource_costs, gap_max_por_tipo)

    # ── 3. Construir lookup de requisitos por atividade ───────────────────────
    activity_resources = _bppc_build_activity_resources(rcpsp_spec)

    # ── 4. Para cada tipo com resource_costs, enumerar pares (i, j) ──────────
    oportunidades: list[OportunidadeCompartilhamento] = []
    # Iterar apenas sobre tipos válidos (dict entries — ignora "_comment" e similares)
    for tipo_id in sorted(gap_max_por_tipo):
        oportunidades.extend(
            _bppc_oportunidades_por_tipo(tipo_id, resource_costs, gap_max_por_tipo, activity_resources, cron_lookup)
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
    _bppc_append_validacoes(validacoes, oportunidades, podadas, total_economia, lambda0_total, gap_max_por_tipo)

    return relatorio


