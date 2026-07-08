"""Skill 05 — Equipes e Alocação (helpers A, parte extraída de _skill_helpers_a.py)."""

from __future__ import annotations

from concilium.domain.models.canonical import (
    CustoParticionadoItem,
    EquipeDireta,
    RecursoContrato,
    ValidacaoItem,
)


def _reset_custo_inst_para_items(eq_by_id: dict, items_em_contratos: set) -> None:
    """TD-1: reset custo_inst_* para items em contratos antes de acumular."""
    for item_id in items_em_contratos:
        eq = eq_by_id.get(item_id)
        if eq is not None:
            eq.custo_inst_mo = 0.0
            eq.custo_inst_eq = 0.0
            eq.custo_inst_comb = 0.0
            eq.custo_inst_mat = 0.0
            eq.custo_inst_mob_demob = 0.0


def _accumulate_custo_inst_para_part(eq: EquipeDireta, part: CustoParticionadoItem) -> None:
    """TD-1: acumula custo_inst_* sobre todos os contratos (não sobrescreve)."""
    eq.custo_inst_mo = round((eq.custo_inst_mo or 0.0) + (part.custo_inst_mo or 0.0), 2)
    eq.custo_inst_eq = round((eq.custo_inst_eq or 0.0) + (part.custo_inst_eq or 0.0), 2)
    eq.custo_inst_comb = round((eq.custo_inst_comb or 0.0) + (part.custo_inst_comb or 0.0), 2)
    eq.custo_inst_mat = round((eq.custo_inst_mat or 0.0) + (part.custo_inst_mat or 0.0), 2)
    eq.custo_inst_mob_demob = round(
        (eq.custo_inst_mob_demob or 0.0) + part.custo_mob_imputado + part.custo_demob_imputado,
        2,
    )


def _append_reescala_validacao(
    validacoes: list[ValidacaoItem], part: CustoParticionadoItem, desvio: float, fator_reescala: float
) -> None:
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-DECOMP-REESCALA",
            status="AVISO",
            mensagem=(
                f"Item {part.item_id}: breakdown reescalado proporcionalmente "
                f"(desvio R$ {desvio:.2f}). Fator: {fator_reescala:.4f}"
            ),
        )
    )


def _append_invariante_falha_validacao(
    validacoes: list[ValidacaoItem], part: CustoParticionadoItem, eq: EquipeDireta, soma: float, desvio: float
) -> None:
    validacoes.append(
        ValidacaoItem(
            codigo="VAL-DECOMP-INVARIANTE",
            status="AVISO",
            mensagem=(
                f"Item {part.item_id}: soma decomposição (R$ {soma:,.2f}) "
                f"≠ custo_total (R$ {eq.custo_total:,.2f}). "
                f"Desvio: R$ {desvio:.2f} — Não foi possível reescalar (soma = 0)"
            ),
        )
    )


def _reescalar_custo_inst_se_necessario(
    eq: EquipeDireta, part: CustoParticionadoItem, validacoes: list[ValidacaoItem]
) -> None:
    """ADR-106: se há desvio significativo do invariante custo_total == soma(custo_inst_*), reescala.

    ADR-085: custo_total_particionado = custo_inst_mo + eq + comb + mat
    (mob_demob já está incluído em custo_inst_mo como resíduo).
    """
    # _accumulate_custo_inst_para_part (chamado antes desta função) sempre
    # atribui um float (round(...)) a estes 4 campos — nunca None aqui.
    assert eq.custo_inst_mo is not None
    assert eq.custo_inst_eq is not None
    assert eq.custo_inst_comb is not None
    assert eq.custo_inst_mat is not None
    assert eq.custo_inst_mob_demob is not None
    soma = eq.custo_inst_mo + eq.custo_inst_eq + eq.custo_inst_comb + eq.custo_inst_mat
    desvio = abs(soma - eq.custo_total)
    if desvio <= 1.0:
        return

    if soma <= 0:
        _append_invariante_falha_validacao(validacoes, part, eq, soma, desvio)
        return

    fator_reescala = eq.custo_total / soma
    eq.custo_inst_mo = round(eq.custo_inst_mo * fator_reescala, 2)
    eq.custo_inst_eq = round(eq.custo_inst_eq * fator_reescala, 2)
    eq.custo_inst_comb = round(eq.custo_inst_comb * fator_reescala, 2)
    eq.custo_inst_mat = round(eq.custo_inst_mat * fator_reescala, 2)
    eq.custo_inst_mob_demob = round(eq.custo_inst_mob_demob * fator_reescala, 2)
    _append_reescala_validacao(validacoes, part, desvio, fator_reescala)


def _enrich_equipes_com_decomposicao_instancial(
    equipes: list[EquipeDireta],
    contratos: list[RecursoContrato],
    validacoes: list[ValidacaoItem],
) -> None:
    """Enriquece equipes com decomposição de custos instanciais após ADR-085.

    Copia custo_inst_* de contratos[].particao_por_item[] para equipes[].
    Valida invariante: custo_total == soma(custo_inst_*) com tolerância R$ 0.05.

    Mutação in-place de `equipes`. Apenas items em contratos receberão decomposição.
    """
    eq_by_id = {eq.item_id: eq for eq in equipes}
    items_em_contratos = {part.item_id for c in contratos for part in c.particao_por_item}
    _reset_custo_inst_para_items(eq_by_id, items_em_contratos)

    for contrato in contratos:
        for part in contrato.particao_por_item:
            eq = eq_by_id.get(part.item_id)
            if eq is None:
                continue

            _accumulate_custo_inst_para_part(eq, part)
            # Validar invariante (detecção precoce de bugs)
            _reescalar_custo_inst_se_necessario(eq, part, validacoes)


