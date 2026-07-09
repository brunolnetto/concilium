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
    _calc_custo_mob_desmob,
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


def _resolve_calibration_fractions(cpu: dict, prod_lookup: dict) -> tuple[float, float, float, float] | None:
    """Resolve (C_ref, frac_mo, frac_eq, frac_diesel) a partir do PU_sbdi; None se não calibrável."""
    prod_id = cpu.get("producao_id_ref") or ""
    prod = prod_lookup.get(prod_id) or {}
    C_ref = float(prod.get("custo_hora_total_referencia") or 0.0)
    if C_ref <= 0.0:
        return None

    sbdi = cpu.get("precos_unitarios_sbdi") or {}
    pu_mo = float(sbdi.get("mo", 0.0) or 0.0)
    pu_eq = float(sbdi.get("equipamentos", 0.0) or 0.0)
    pu_diesel = float(sbdi.get("diesel", 0.0) or 0.0)
    pu_total = pu_mo + pu_eq + pu_diesel
    if pu_total <= 0.0:
        return None

    # Decompor pelas frações do PU_sbdi
    return C_ref, pu_mo / pu_total, pu_eq / pu_total, pu_diesel / pu_total


def _calibrar_custos_por_cref(
    cpu: dict,
    prod_lookup: dict,
    horas_dia: float,
    custo_mo: float,
    custo_encargos: float,
    custo_mo_base: float,
    custo_eq: float,
    custo_comb: float,
) -> tuple[float, float, float, float, float]:
    """NEP-029/S1: recalibra custos mensais usando custo_hora_total_referencia do catálogo.

    Os preços individuais de insumos do catálogo divergem do custo calibrado pela planilha
    (custo_hora_total_referencia), gerando custo autônomo inconsistente com o pool.
    Usando precos_unitarios_sbdi como frações e C_ref como base, a equipe autônoma
    fica alinhada com o pool (mesmo custo_unit_semanal).

    Retorna (custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb) calibrados.
    Sem alteração quando C_ref ausente ou insumos zerados (fallback silencioso).
    """
    fracs = _resolve_calibration_fractions(cpu, prod_lookup)
    if fracs is None:
        return custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb
    C_ref, frac_mo, frac_eq, frac_diesel = fracs

    # Custo total por mês calibrado = C_ref × horas_semana × SEMANAS_POR_MES
    horas_semana = horas_dia * 6  # dias_semana fixo via regime
    custo_mes_ref = C_ref * horas_semana * SEMANAS_POR_MES

    # O PU_sbdi de MO já inclui encargos (B_base × (1+enc)) — manter enc proporcional
    custo_mo_cal = custo_mes_ref * frac_mo  # inclui encargos
    custo_eq_cal = custo_mes_ref * frac_eq
    custo_comb_cal = custo_mes_ref * frac_diesel

    # Derivar custo_mo_base e custo_encargos mantendo a proporção original
    mo_total_orig = custo_mo if custo_mo > 0 else custo_mo_cal
    frac_enc = custo_encargos / mo_total_orig if mo_total_orig > 0 else 0.0
    custo_mo_base_cal = round(custo_mo_cal * (1.0 - frac_enc), 2)
    custo_encargos_cal = round(custo_mo_cal * frac_enc, 2)

    return (
        round(custo_mo_cal, 2),
        custo_encargos_cal,
        custo_mo_base_cal,
        round(custo_eq_cal, 2),
        round(custo_comb_cal, 2),
    )


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
    team_weeks: float,
    num_equipes_paralelas: int,
    custo_total: float,
    custo_mat: float,
    custo_ocioso: float,
    custo_mob_desmob: float,
) -> tuple[float, float]:
    """ADR-091: divide permanência e custo total pelo número de equipes paralelas (n_frentes).

    CRÍTICO: team_weeks já vem do cronograma SOMANDO o num_equipes para cada semana
    (ex: 3 equipes × 32 semanas vem como 96 weeks) — dividir por num_equipes obtém a
    permanência de UMA equipe.
    """
    team_weeks_ajustado = team_weeks / max(num_equipes_paralelas, 1)
    permanencia_efetiva = round(team_weeks_ajustado / SEMANAS_POR_MES, 4)
    # custo_total_ajustado = custo total / n_frentes = custo de 1 frente (ADR-091)
    custo_total_ajustado = custo_total / max(num_equipes_paralelas, 1) if num_equipes_paralelas > 1 else custo_total
    custo_total_final = round(
        custo_total_ajustado + custo_mat * permanencia_efetiva + custo_ocioso + custo_mob_desmob, 2
    )
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
    prod_lookup: dict,
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

    # NEP-029/S1: calibrar custos mensais pelo custo_hora_total_referencia do catálogo.
    # precos_unitarios_sbdi fornece as frações mo/eq/diesel já calculadas pela planilha.
    # Sem esta calibração, os insumos individuais divergem do C_ref e o custo autônomo
    # fica ~2.5× menor que o pool, gerando "economia negativa" espúria no painel.
    custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb = _calibrar_custos_por_cref(
        cpu, prod_lookup, horas_dia, custo_mo, custo_encargos, custo_mo_base, custo_eq, custo_comb
    )

    # NEP-031 L3: custo de mob/desmob por evento de transição de recursos
    custo_mob_desmob = _calc_custo_mob_desmob(comp, cron)
    custo_total, ativos, custo_comb_efetivo, _fixo_mensal, team_weeks, custo_ocioso = _calc_custo_cron(
        cron, custo_mo, custo_eq, custo_comb
    )
    num_equipes_paralelas = _resolve_num_equipes_paralelas(cron)

    permanencia_efetiva, custo_total_final = _resolve_permanencia_e_custo_total_ajustados(
        team_weeks, num_equipes_paralelas, custo_total, custo_mat, custo_ocioso, custo_mob_desmob
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
                prod_lookup,
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


