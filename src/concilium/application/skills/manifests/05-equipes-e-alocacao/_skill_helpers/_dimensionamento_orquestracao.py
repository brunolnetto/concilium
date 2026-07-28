"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _dimensionamento_equipe.py)."""

from __future__ import annotations

from typing import Any

from concilium.domain.constants import (
    ENCARGOS_CLT,
    ENCARGOS_MENSALISTA,
    SEMANAS_POR_MES,
)
from concilium.domain.models.canonical import (
    CanonicalModel,
    EquipeDireta,
    ValidacaoItem,
)

from ._dimensionamento_custos import _RepoCtx, _resolve_preco  # ty: ignore[unresolved-import]
from ._dimensionamento_itens import (  # ty: ignore[unresolved-import]
    _build_comp_para_item,
    _calc_custo_cron,
    _calc_custo_mob_desmob_split,
    _processar_equipamentos_item,
    _processar_funcoes_item,
    _validar_materiais_item,
)


def _resolve_preco_diesel(inputs: dict, catalogo: dict, ctx: _RepoCtx) -> float:
    """Returns resolved diesel price from catalog or inputs fallback."""
    preco_diesel = inputs.get("preco_diesel", 6.20)
    for i in catalogo.get("insumos", []):
        if i["codigo"] == "DIESEL-S10":
            return _resolve_preco(ctx, "DIESEL-S10", float(i.get("preco_unitario", preco_diesel) or preco_diesel))
    return preco_diesel


def _resolve_prod_lookup(catalogo: dict) -> dict:
    """Returns {id: producao_dict} from catalog produtividades or producoes."""
    fonte = catalogo.get("produtividades", []) or catalogo.get("producoes", [])
    return {p.get("id"): p for p in fonte if p.get("id")}


def _setup_dimensionamento_context(
    canonical_in: CanonicalModel,
    inputs: dict,
    catalogo: dict,
    ctx: _RepoCtx,
) -> tuple:
    """Resolve parâmetros, preço de diesel e tabelas de lookup para dimensionamento."""
    perc_horista = inputs.get("percentual_encargos", ENCARGOS_CLT)
    perc_mensalista = inputs.get("percentual_encargos_mensalista", ENCARGOS_MENSALISTA)
    preco_diesel = _resolve_preco_diesel(inputs, catalogo, ctx)
    horas_dia = canonical_in.projeto.regime_trabalho.horas_dia
    dias_uteis = 30.0 * (canonical_in.projeto.regime_trabalho.dias_semana / 7)
    cpu_lookup = {c["codigo"]: c for c in catalogo.get("cpus", [])}
    prod_lookup = _resolve_prod_lookup(catalogo)
    sched_acts = canonical_in.cronograma.scheduled_activities if canonical_in.cronograma else []
    cron_lookup = {sa.activity_id: sa for sa in sched_acts}
    return perc_horista, perc_mensalista, preco_diesel, horas_dia, dias_uteis, cpu_lookup, prod_lookup, cron_lookup


def _resolve_num_equipes_paralelas(cron: Any) -> int:
    """ADR-091: infere o número de equipes paralelas alocadas para evitar duplicação de custos.

    assigned_resources é propagado por skill-04 em modo AUTO; em MANUAL_ALLOCATION fica vazio,
    caso em que deduzimos do max(num_equipes) na distribuição semanal do cronograma.
    """
    assigned_resources = getattr(cron, "assigned_resources", None) or {}
    num_equipes_paralelas = sum(assigned_resources.values()) if assigned_resources else 1

    if not num_equipes_paralelas or num_equipes_paralelas == 1:
        dist_semanal = getattr(cron, "distribuicao_semanal", {}) or {}
        if dist_semanal and isinstance(dist_semanal, dict):
            values_list = list(dist_semanal.values())
            max_num_eq = max((getattr(d, "num_equipes", 0) for d in values_list), default=1)
            if max_num_eq > 1:
                num_equipes_paralelas = max_num_eq

    return num_equipes_paralelas


def _resolve_permanencia_e_custo_total_ajustados(
    ativos: int,
    custo_1frente: float,
    custo_mat: float,
    custo_ocioso: float,
    custo_mob_desmob: float,
) -> tuple[float, float]:
    """ADR-162 D4: permanência e custo total na base de UMA frente de referência,
    semana a semana (`_sum_1frente_cost`) — substitui a versão anterior (ADR-091), que
    dividia o agregado multi-frente (`team_weeks`/`custo_total`) por um único
    `num_equipes_paralelas` constante.

    Essa divisão por constante só reconstruía exatamente 1 frente quando o número de
    frentes era constante em todas as semanas ativas; com rampa (mobilização/desmobilização
    parcial, lesão climática reduzindo frentes efetivas em algumas semanas), subestimava a
    permanência/custo de referência — verificado numericamente: rampa 1→3→1 ao longo de
    7 semanas ativas subestimava a permanência em ~40% (0,9966 vs 1,6099 meses corretos).

    `ativos` (contagem de semanas com `num_equipes > 0`) e `custo_1frente` (taxa semanal de
    1 frente somada só nas semanas ativas, sem multiplicar por `num_equipes`) são robustos a
    qualquer forma de rampa — a mesma fonte semanal-por-item já usada por `machine_weeks_brutas`
    no diagnóstico `causa_dominante` (D1) do ADR-162.
    """
    permanencia_efetiva = round(ativos / SEMANAS_POR_MES, 4)
    custo_total_final = round(custo_1frente + custo_mat * permanencia_efetiva + custo_ocioso + custo_mob_desmob, 2)
    return permanencia_efetiva, custo_total_final


def _dimensionar_item_equipe(
    item: Any,
    cpu: dict,
    cron: Any,
    comp: dict,
    item_custom: dict,
    ctx: _RepoCtx,
    perc_horista: float,
    perc_mensalista: float,
    horas_dia: float,
    dias_uteis: float,
    preco_diesel: float,
    validacoes: list,
) -> EquipeDireta:
    """Dimensiona a equipe direta de um item de EAP, agregando MO/encargos/equipamentos/custos."""
    funcoes_mod, custo_mo_base, custo_encargos = _processar_funcoes_item(
        comp, item.item_id, item_custom, ctx, perc_horista, perc_mensalista, validacoes
    )
    # NEP-037: custo_mo para cron = base + encargos (custo_total inalterado)
    custo_mo = custo_mo_base + custo_encargos
    equips_mod, custo_eq, custo_comb, modo_est = _processar_equipamentos_item(
        comp, item.item_id, item_custom, cpu, horas_dia, dias_uteis, preco_diesel, ctx, validacoes
    )
    _validar_materiais_item(comp, cpu, validacoes)
    # custo_material_mensal é responsabilidade de etapas posteriores (skill-06+).
    # Skill-05 apenas valida cobertura via VAL-EQUIP-MAT-01/02.
    custo_mat = 0.0

    # Sem calibração por custo_hora_total_referencia (removida): _processar_equipamentos_item
    # já prioriza preco_h_unitario embutido na composição sobre o catálogo geral (ADR-132),
    # o que por si só reproduz o custo de referência calibrado contra obra real (verificado
    # para PROD-REJEITO-COMP-EQ1-4, delta < 0,003%) — o atalho por C_ref era redundante.

    # NEP-031 L3 / ADR-106 F2-bis: custo de mob/desmob por evento de transição de
    # recursos, separado em mob/demob — antes só o agregado era calculado, e os
    # campos custo_mobilizacao_mensal/custo_desmobilizacao_mensal ficavam mortos
    # (nunca atribuídos), apesar do invariante documentado no modelo.
    custo_mob_mensal, custo_demob_mensal = _calc_custo_mob_desmob_split(comp, cron)
    custo_mob_desmob = round(custo_mob_mensal + custo_demob_mensal, 2)
    _custo_total, ativos, custo_comb_efetivo, _fixo_mensal, _team_weeks, custo_ocioso, custo_1frente = (
        _calc_custo_cron(cron, custo_mo, custo_eq, custo_comb)
    )
    num_equipes_paralelas = _resolve_num_equipes_paralelas(cron)

    permanencia_efetiva, custo_total_final = _resolve_permanencia_e_custo_total_ajustados(
        ativos, custo_1frente, custo_mat, custo_ocioso, custo_mob_desmob
    )
    # NEP-037: custo_fixo_mensal usa custo_mo_base (sem encargos) — encargos ficam em custo_encargos_mensal.
    fixo_mensal_total = round(custo_mo_base + custo_eq + custo_comb_efetivo + custo_mat, 2)

    return EquipeDireta(
        equipe_id=f"eq-{item.item_id}",
        item_id=item.item_id,
        cpu_id=item.cpu_id,
        nome=f"Equipe {cpu['descricao'][:30]}",
        num_equipes_base=num_equipes_paralelas,
        funcoes=funcoes_mod,
        equipamentos=equips_mod,
        custo_mao_obra_mensal=round(custo_mo_base, 2),
        custo_encargos_mensal=round(custo_encargos, 2),
        custo_equipamentos_mensal=round(custo_eq, 2),
        custo_combustivel_total_mensal=round(custo_comb_efetivo, 2),
        custo_material_mensal=round(custo_mat, 2),
        custo_fixo_mensal=fixo_mensal_total,
        permanencia_meses=round(ativos / SEMANAS_POR_MES, 2),
        permanencia_efetiva_meses=permanencia_efetiva,
        custo_total=custo_total_final,
        modo_estimativa=modo_est,
        custo_ocioso_equipamentos=custo_ocioso,
        custo_mob_desmob=custo_mob_desmob,
        custo_mobilizacao_mensal=custo_mob_mensal,
        custo_desmobilizacao_mensal=custo_demob_mensal,
        # ADR-088: sub-campos de equipamento agregados da equipe
        custo_locacao_mensal=round(sum(e.custo_locacao_mensal * e.num_unidades for e in equips_mod), 2),
        custo_manutencao_mensal=round(sum(e.custo_manutencao_mensal * e.num_unidades for e in equips_mod), 2),
    )


def _build_dimensionamento(
    canonical_in: CanonicalModel,
    inputs: dict,
    catalogo: dict,
    ctx: _RepoCtx,
    validacoes: list,
) -> list[EquipeDireta]:
    """Seção 1: Dimensionamento de equipes (Antiga Skill 03)."""
    perc_horista, perc_mensalista, preco_diesel, horas_dia, dias_uteis, cpu_lookup, prod_lookup, cron_lookup = (
        _setup_dimensionamento_context(canonical_in, inputs, catalogo, ctx)
    )
    composicao_customizada = inputs.get("composicao_customizada", {})

    equipes: list[EquipeDireta] = []
    for item in canonical_in.eap:
        cpu = cpu_lookup.get(item.cpu_id)
        cron = cron_lookup.get(item.item_id)
        if not cpu or not cron:
            continue
        comp = _build_comp_para_item(cpu, prod_lookup, validacoes)
        item_custom = composicao_customizada.get(item.item_id, {})
        equipes.append(
            _dimensionar_item_equipe(
                item,
                cpu,
                cron,
                comp,
                item_custom,
                ctx,
                perc_horista,
                perc_mensalista,
                horas_dia,
                dias_uteis,
                preco_diesel,
                validacoes,
            )
        )
    if not equipes:
        validacoes.append(
            ValidacaoItem(
                codigo="VAL-EQUIP-MODO-INICIAL",
                status="INFO",
                mensagem="Nenhuma equipe dimensionada — pipeline sem atividades elegíveis.",
            )
        )
    return equipes


