"""ADR-078/ADR-110 — pré-processamento e detecção de oportunidades de compartilhamento.

Detecção de oportunidades de compartilhamento paralelo (ADR-110).
"""

from __future__ import annotations

from typing import Any

from concilium.domain.models.canonical import (
    OportunidadeCompartilhamentoParalelo,
)

from ._cpm import _cpm_early_start, _cpm_late_finish, _gap_coberto_por_recurso  # ty: ignore[unresolved-import]


def _dop_ordem_temporal(id_x: str, id_y: str, sa_map: dict[str, Any]) -> tuple[str, str] | None:
    """Determina (i_id, j_id) tal que i termina antes de j começar; None se sobrepõem."""
    sa_x, sa_y = sa_map[id_x], sa_map[id_y]
    if sa_x.end_week <= sa_y.start_week:
        return id_x, id_y
    if sa_y.end_week <= sa_x.start_week:
        return id_y, id_x
    return None


def _dop_delay_viola_float(
    act_id: str, delay: int, dag: Any, act_map: dict[str, Any], cpm_es: dict[str, int], cpm_lf: dict[str, int]
) -> bool:
    """True se o delay de `act_id` viola o float de algum sucessor direto no DAG (critério 5)."""
    if delay <= 0:
        return False
    for succ in dag.successors(act_id):
        # act_map sempre contém `succ`: dag.topological_order() (chamado acima em
        # _cpm_early_start/_cpm_late_finish) já teria levantado ValueError/KeyError se
        # dag.precedence referenciasse uma atividade fora de dag.activities — logo `succ`
        # é garantidamente uma chave válida de act_map neste ponto.
        act_succ = act_map[succ]
        tf_succ = cpm_lf[succ] - cpm_es.get(succ, 0) - act_succ.duration_weeks
        if tf_succ < delay:
            return True
    return False


def _dop_avaliar_par(
    id_x: str,
    id_y: str,
    tipo_id: str,
    sched: Any,
    dag: Any,
    sa_map: dict[str, Any],
    act_map: dict[str, Any],
    precedencias: set[frozenset],
    e_gargalo: bool,
    cpm_es: dict[str, int],
    cpm_lf: dict[str, int],
    custo_semana: float,
    custo_indireto_semana: float,
) -> OportunidadeCompartilhamentoParalelo | None:
    """Avalia um par (id_x, id_y) contra os critérios 3-5 do ADR-110 §D1 e retorna a oportunidade, se viável."""
    if frozenset([id_x, id_y]) in precedencias:
        return None

    ordem = _dop_ordem_temporal(id_x, id_y, sa_map)
    if ordem is None:
        return None
    i_id, j_id = ordem

    sa_i, sa_j = sa_map[i_id], sa_map[j_id]
    act_i = act_map.get(i_id)
    act_j = act_map.get(j_id)
    if act_i is None or act_j is None:
        return None

    # Critério 4: gap entre i e j coberto por outras atividades do tipo
    if not _gap_coberto_por_recurso(sched, tipo_id, sa_i.end_week, sa_j.start_week):
        return None

    d_i = act_i.duration_weeks
    d_j = act_j.duration_weeks
    t0 = sa_i.start_week  # ambas iniciam em t0 no cenário paralelo

    # Delays individuais no cenário paralelo-com-alternância
    new_ef_i = t0 + 2 * d_i
    new_ef_j = t0 + 2 * d_j
    delay_i = max(0, new_ef_i - sa_i.end_week)
    delay_j = max(0, new_ef_j - sa_j.end_week)

    # Critério 5 (gargalo): delay não pode violar float de sucessores diretos
    if e_gargalo:
        for act_id, delay in ((i_id, delay_i), (j_id, delay_j)):
            if _dop_delay_viola_float(act_id, delay, dag, act_map, cpm_es, cpm_lf):
                return None

    delta_makespan = max(0, max(new_ef_i, new_ef_j) - sa_j.end_week) if e_gargalo else 0

    semanas_frota = max(d_i, d_j)
    delta_custo_frota = round(custo_semana * semanas_frota, 2)
    delta_indiretos = round(custo_indireto_semana * delta_makespan, 2)
    delta_liquido = round(delta_custo_frota - delta_indiretos, 2)

    return OportunidadeCompartilhamentoParalelo(
        atividade_i=i_id,
        atividade_j=j_id,
        tipo_recurso_id=tipo_id,
        recurso_e_gargalo=e_gargalo,
        delta_makespan_semanas=delta_makespan,
        delta_custo_frota=delta_custo_frota,
        delta_indiretos=delta_indiretos,
        delta_liquido=delta_liquido,
        economicamente_viavel=delta_liquido > 0,
    )


def _dop_oportunidades_para_tipo(
    usuarios: list[str],
    tipo_id: str,
    sched: Any,
    dag: Any,
    sa_map: dict[str, Any],
    act_map: dict[str, Any],
    precedencias: set[frozenset],
    e_gargalo: bool,
    cpm_es: dict[str, int],
    cpm_lf: dict[str, int],
    custo_semana: float,
    custo_indireto_semana: float,
) -> list[OportunidadeCompartilhamentoParalelo]:
    """Enumera todos os pares de `usuarios` de um mesmo tipo de recurso e avalia cada oportunidade."""
    oportunidades: list[OportunidadeCompartilhamentoParalelo] = []
    for idx_x in range(len(usuarios)):
        for idx_y in range(idx_x + 1, len(usuarios)):
            oport = _dop_avaliar_par(
                usuarios[idx_x],
                usuarios[idx_y],
                tipo_id,
                sched,
                dag,
                sa_map,
                act_map,
                precedencias,
                e_gargalo,
                cpm_es,
                cpm_lf,
                custo_semana,
                custo_indireto_semana,
            )
            if oport is not None:
                oportunidades.append(oport)
    return oportunidades


def _dop_contexto_tipo(
    tipo_id: str, costs: Any, pool: Any, sched: Any, lpp: dict[str, str]
) -> tuple[list[str], float, bool] | None:
    """Valida os critérios 1-2 e monta o contexto (usuarios, custo_semana, e_gargalo) do tipo.

    Retorna None quando o tipo não é elegível (não é dict, não é disputado, sem custo
    de frota configurado, ou com menos de 2 usuários no cronograma).
    """
    if not isinstance(costs, dict):
        return None
    if pool.resources.get(tipo_id, 0) != 1:
        return None

    custo_semana = float(costs.get("custo_contrato_semana_unit", 0.0))
    if custo_semana <= 0.0:
        return None

    usuarios: list[str] = [
        sa.activity_id for sa in sched.scheduled_activities if sa.assigned_resources.get(tipo_id, 0) > 0
    ]
    if len(usuarios) < 2:
        return None

    e_gargalo = lpp.get(tipo_id, "equipamento") == "equipamento"
    return usuarios, custo_semana, e_gargalo


def _detectar_oportunidades_paralelo(
    sched: Any,
    dag: Any,
    pool: Any,
    resource_costs: dict[str, dict],
    custo_indireto_semana: float,
    limite_producao_por_tipo: dict[str, str] | None = None,
) -> list[OportunidadeCompartilhamentoParalelo]:
    """Detecta candidatos a compartilhamento paralelo pós-RCPSP (ADR-110 §D1).

    Critérios:
      1. Tipo r presente em resource_costs (custo de frota conhecido)
      2. pool[r] == 1 (recurso disputado — contenção)
      3. Sem aresta de precedência lógica direta entre i e j
      4. Gap entre elas coberto por outras atividades do mesmo tipo
         (mesma cadeia de contenção); gap zero = diretamente adjacentes
      5. Para gargalo: delay causado não viola o float dos sucessores diretos no DAG
    """
    if not sched.scheduled_activities:
        return []

    lpp = limite_producao_por_tipo or {}
    sa_map: dict[str, Any] = {sa.activity_id: sa for sa in sched.scheduled_activities}
    act_map: dict[str, Any] = {a.activity_id: a for a in dag.activities}

    cpm_es = _cpm_early_start(dag)
    cpm_lf = _cpm_late_finish(dag, sched.makespan)

    precedencias: set[frozenset] = {frozenset([pred, succ]) for pred, succ in dag.precedence}

    resultado: list[OportunidadeCompartilhamentoParalelo] = []

    for tipo_id, costs in resource_costs.items():
        contexto = _dop_contexto_tipo(tipo_id, costs, pool, sched, lpp)
        if contexto is None:
            continue
        usuarios, custo_semana, e_gargalo = contexto

        resultado.extend(
            _dop_oportunidades_para_tipo(
                usuarios,
                tipo_id,
                sched,
                dag,
                sa_map,
                act_map,
                precedencias,
                e_gargalo,
                cpm_es,
                cpm_lf,
                custo_semana,
                custo_indireto_semana,
            )
        )

    resultado.sort(key=lambda o: -o.delta_liquido)
    return resultado


