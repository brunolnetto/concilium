"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import (
    EquipeDireta,
    InstanciaRecurso,
    RecursoContrato,
    ValidacaoItem,
)


def _scale_part_entry(
    part,
    escala: float,
    novo_total: float,
    tot_mo: float,
    tot_eq: float,
    tot_comb: float,
    tot_mat: float,
    eq_by_item: dict,
) -> None:
    """Scales one CustoParticionadoItem in place for _reescalar_particao."""
    part.custo_produtivo = round(part.custo_produtivo * escala, 2)
    part.custo_mob_imputado = round(part.custo_mob_imputado * escala, 2)
    part.custo_ocioso_imputado = round(part.custo_ocioso_imputado * escala, 2)
    part.overhead_ocioso = round(part.overhead_ocioso * escala, 2)
    part.custo_produtivo_exclusivo = round(part.custo_produtivo_exclusivo * escala, 2)
    part.custo_produtivo_compartilhado = round(part.custo_produtivo_compartilhado * escala, 2)
    part.custo_demob_imputado = round(part.custo_demob_imputado * escala, 2)
    part.custo_total_particionado = round(part.custo_total_particionado * escala, 2)
    part.economia_vs_autonomo = round(part.custo_total_autonomo - part.custo_total_particionado, 2)
    frac_item = (part.custo_total_particionado / novo_total) if novo_total > 0 else 0.0
    part.custo_inst_eq = round(tot_eq * frac_item, 2)
    part.custo_inst_comb = round(tot_comb * frac_item, 2)
    part.custo_inst_mat = round(tot_mat * frac_item, 2)
    part.custo_inst_mo = round(
        part.custo_total_particionado - part.custo_inst_eq - part.custo_inst_comb - part.custo_inst_mat, 2
    )
    eq = eq_by_item.get(part.item_id)
    if eq is not None:
        eq.custo_total = part.custo_total_particionado


def _sum_inst_categories(insts_contrato: list) -> tuple:
    """Returns (tot_mo, tot_eq, tot_comb, tot_mat) sums from instancias list.

    ADR-136 F3: custo_mob_instancia entra na mesma categoria (EQ) que
    custo_demob_instancia já ocupava — mob/demob são custo indireto de campo
    tipicamente associado a transporte/logística de equipamento (ADR-125 D1),
    não a mão-de-obra, combustível ou material. Mantém o invariante
    tot_mo + tot_eq + tot_comb + tot_mat == Σ custo_instancia_total
    (VAL-INST-CAT-SOMA / test_invariante_categorial_soma).
    """
    tot_mo = sum(i.custo_ativo_mo + i.custo_idle_mo for i in insts_contrato)
    tot_eq = sum(
        i.custo_ativo_eq + i.custo_idle_eq + i.custo_mob_instancia + i.custo_demob_instancia for i in insts_contrato
    )
    tot_comb = sum(i.custo_ativo_comb for i in insts_contrato)
    tot_mat = sum(i.custo_ativo_mat for i in insts_contrato)
    return tot_mo, tot_eq, tot_comb, tot_mat


def _reescalar_particao(contrato, novo_total: float, insts_contrato: list, eq_by_item: dict, validacoes: list) -> None:
    """Reescala particao_por_item proporcionalmente ao novo custo instancial total."""
    antigo_total = float(contrato.custo_total_contrato or 0.0)
    escala = novo_total / antigo_total if antigo_total > 0 else 1.0
    contrato.custo_total_contrato = novo_total
    tot_mo, tot_eq, tot_comb, tot_mat = _sum_inst_categories(insts_contrato)
    for part in contrato.particao_por_item:
        _scale_part_entry(part, escala, novo_total, tot_mo, tot_eq, tot_comb, tot_mat, eq_by_item)


def _apply_instancial_to_contrato(contrato, instancias: list, eq_by_item: dict, validacoes: list) -> None:
    """Applies ADR-085 instancial cost to one contrato if applicable."""
    insts_contrato = [i for i in instancias if i.contrato_id == contrato.contrato_id]
    novo_total = round(sum(inst.custo_instancia_total for inst in insts_contrato), 2)
    antigo_total = float(contrato.custo_total_contrato or 0.0)
    if novo_total <= 0:
        return
    if antigo_total <= 0:
        return
    _reescalar_particao(contrato, novo_total, insts_contrato, eq_by_item, validacoes)
    reducao_pct = round((1.0 - novo_total / antigo_total) * 100, 1)
    n_mob_tardia = len(contrato.mobilizacao_por_instancia)
    n_desmob = sum(1 for inst in insts_contrato if inst.desmob_antecipada_aplicada)
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-MOB-TARDIA-OK",
            status="OK",
            mensagem=(
                f"ADR-085: Contrato {contrato.tipo_id} — custo instancial composicional "
                f"R$ {novo_total:,.2f} (era R$ {antigo_total:,.2f}, −{reducao_pct:.1f}%). "
                f"{n_mob_tardia} instância(s) com mobilização tardia; "
                f"{n_desmob} com desmobilização antecipada efetiva."
            ),
        )
    )


def _aplicar_custo_instancial(
    contratos: list[RecursoContrato],
    instancias: list[InstanciaRecurso],
    equipes: list[EquipeDireta],
    validacoes: list,
) -> None:
    """Substitui custo_total_contrato pela soma dos custos instanciais — ADR-085 D3.

    Para cada contrato com custo instancial composicional ativo (c_idle > 0), o custo
    do contrato passa a ser Σ custo_instancia_total (mobilização tardia + taxa ociosa
    por componente + desmobilização antecipada efetiva), substituindo a fórmula
    monolítica `quantidade × custo_unit × semanas` do ADR-071.

    A atribuição por item (machine-weeks) é preservada (ADR-071 §3.1): apenas o custo
    total é reescalado, mantendo as frações. `eq.custo_total` e
    `CustoParticionadoItem.custo_total_particionado` são atualizados proporcionalmente.

    Mutação in-place de `contratos` e `equipes`. Retrocompatível: contratos sem custo
    instancial (Σ = 0) permanecem com a fórmula monolítica.
    """
    eq_by_item = {eq.item_id: eq for eq in equipes if eq.item_id}
    for contrato in contratos:
        _apply_instancial_to_contrato(contrato, instancias, eq_by_item, validacoes)

    # TD-1: recomputa eq.custo_total como Σ_r custo_total_particionado_ir após ADR-085.
    # Necessário porque _reescalar_particao sobrescreve em vez de acumular (por design —
    # ADR-085 reescala cada contrato independentemente). O acumulado correto é a soma de
    # todas as partições, já reescaladas ou monolíticas.
    pool_total_por_item: dict[str, float] = {}
    for c in contratos:
        for part in c.particao_por_item:
            pool_total_por_item[part.item_id] = pool_total_por_item.get(part.item_id, 0.0) + float(
                getattr(part, "custo_total_particionado", 0.0) or 0.0
            )
    for item_id, total in pool_total_por_item.items():
        eq = eq_by_item.get(item_id)
        if eq is not None and total > 0:
            eq.custo_total = round(total, 2)


