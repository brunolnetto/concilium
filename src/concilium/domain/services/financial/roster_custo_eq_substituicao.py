"""ADR-157 F1 — Composição de equipamentos por tipo de pool + substituição segura de EQ.

Espelho de `roster_custo_mo_substituicao.py` (ADR-156) para o lado de equipamento.
`RecursoContrato.tipo_id` não representa um tipo de equipamento isolado — é um hash
da composição inteira de uma equipe (`_tipo_recurso_fungivel`, ADR-046), que pode
combinar múltiplos equipamentos e funções de MO sob o mesmo tipo_id. Substituir
`custo_unit_semanal_eq` por um roster de um único `equip_id` corromperia o
resultado de um tipo misto.

`extrair_composicao_equipamentos_eq` expõe a mesma informação usada para gerar o
hash, sem tocar o pipeline real. `aplicar_roster_custo_real_eq` só substitui
quando o roster cobre, com headcount suficiente, TODOS os equipamentos da
composição — nunca substituição parcial.

Sem wiring ao orquestrador real de skill-05 nem a `Escopo` — ver ADR futura de wiring.
"""

from __future__ import annotations

from concilium.domain.models.canonical import AtivoEquipamentoReal, RecursoContrato
from concilium.domain.models.catalog.catalogo import ComposicaoPadraoEquipe
from concilium.domain.services.financial.roster_custo_equipamento import custo_real_eq_total


def extrair_composicao_equipamentos_eq(composicao: ComposicaoPadraoEquipe) -> dict[str, int]:
    """Extrai {equip_id: num_unidades} de uma ComposicaoPadraoEquipe do catálogo.

    Mesma informação usada por `_tipo_recurso_fungivel` (`_pool_contrato_construcao.py`)
    para gerar o hash do tipo_id — exposta aqui como função standalone, sem tocar o
    pipeline real. Equipamentos sem `equip_id` são ignorados.
    """
    return {e.equip_id: e.num_unidades for e in composicao.equipamentos if e.equip_id}


def _cobertura_suficiente(roster: list[AtivoEquipamentoReal], equip_id: str, necessario: int) -> bool:
    distintos = {a.ativo_id for a in roster if a.equip_id == equip_id}
    return len(distintos) >= necessario


def roster_cobre_composicao_eq(contrato: RecursoContrato, roster: list[AtivoEquipamentoReal]) -> bool:
    return all(
        _cobertura_suficiente(roster, equip_id, num_unidades * contrato.quantidade_contratada)
        for equip_id, num_unidades in contrato.composicao_equipamentos_eq.items()
    )


def aplicar_roster_custo_real_eq(
    contrato: RecursoContrato,
    roster: list[AtivoEquipamentoReal],
) -> RecursoContrato:
    """Substitui `custo_unit_semanal_eq` (e `custo_unit_semanal`/`custo_total_contrato`
    dependentes) pelo custo real do roster — só quando o roster cobre, com headcount
    suficiente, TODOS os equipamentos em `contrato.composicao_equipamentos_eq`.

    Espelho de `aplicar_roster_custo_real_mo` (ADR-156 D3) — mesma verificação de
    cobertura e mesmo fallback seguro (contrato inalterado se incompleto).
    """
    if not contrato.composicao_equipamentos_eq:
        return contrato
    if not roster_cobre_composicao_eq(contrato, roster):
        return contrato

    custo_real_total = sum(
        custo_real_eq_total(roster, equip_id, contrato.semana_inicio, contrato.semana_fim)
        for equip_id in contrato.composicao_equipamentos_eq
    )
    denom = contrato.quantidade_contratada * contrato.semanas_contrato
    cus_eq_novo = round(custo_real_total / denom, 4) if denom > 0 else 0.0
    cus_outros = contrato.custo_unit_semanal_mo + contrato.custo_unit_semanal_comb + contrato.custo_unit_semanal_mat
    cus_semanal_novo = round(cus_eq_novo + cus_outros, 4)
    custo_total_novo = round(contrato.quantidade_contratada * cus_semanal_novo * contrato.semanas_contrato, 2)
    return contrato.model_copy(
        update={
            "custo_unit_semanal_eq": cus_eq_novo,
            "custo_unit_semanal": cus_semanal_novo,
            "custo_total_contrato": custo_total_novo,
        }
    )
