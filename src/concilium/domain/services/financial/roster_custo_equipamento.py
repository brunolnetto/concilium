"""ADR-155 F1 — Roster real de equipamento: custo individualizado por semana.

Soma, semana a semana, o custo real de cada `AtivoEquipamentoReal` ativo num tipo —
locação + manutenção mensal do contrato real, convertidas a taxa semanal.

Sem nenhuma ligação com `InstanciaRecurso`/`segmentos_atividade`/`identidade_fisica_id`
(ADR-153) — o pool RCPSP permanece fungível; isto é puramente uma camada de custo
bottom-up a partir de ativos reais, independente de scheduling. Estrutura irmã de
`roster_custo_mo.py` (ADR-154).

Granularidade semanal (mesma do resto do motor RCPSP): início/fim de contrato no
meio de uma semana ISO não gera rateio por dia — a semana inteira em que a data cai
é contabilizada por completo.
"""

from __future__ import annotations

from datetime import date, timedelta

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import AtivoEquipamentoReal, RecursoContrato
from concilium.domain.services.planning.week_sequence import enumerar_semanas


def _intervalo_semana(semana: str) -> tuple[date, date]:
    """Segunda a domingo de uma semana ISO (ex: "2026-W03")."""
    year_str, week_str = semana.split("-W")
    segunda = date.fromisocalendar(int(year_str), int(week_str), 1)
    return segunda, segunda + timedelta(days=6)


def _ativo_ativo_na_semana(ativo: AtivoEquipamentoReal, semana: str) -> bool:
    segunda, domingo = _intervalo_semana(semana)
    if ativo.data_contrato_inicio > domingo:
        return False
    return ativo.data_contrato_fim is None or ativo.data_contrato_fim >= segunda


def _custo_semanal_ativo(ativo: AtivoEquipamentoReal) -> float:
    return (ativo.custo_locacao_mensal_real + ativo.custo_manutencao_mensal_real) / SEMANAS_POR_MES


def _custo_semanal_ativo_idle(ativo: AtivoEquipamentoReal) -> float:
    """ADR-158: custo ocioso real — só locação, sem manutenção (equipamento parado
    não gera desgaste ativo, mas o contrato de locação continua sendo cobrado)."""
    return ativo.custo_locacao_mensal_real / SEMANAS_POR_MES


def custo_real_eq_semanal(
    roster: list[AtivoEquipamentoReal],
    equip_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> dict[str, float]:
    """Custo real de equipamento por semana — soma, por semana, o custo de cada
    ativo do roster ativo naquele equip_id e naquele intervalo.

        custo_semana(t) = Σ_{ativo ativo em t} (custo_locacao_mensal_real
                           + custo_manutencao_mensal_real) / SEMANAS_POR_MES

    Ativos de outro equip_id são ignorados. `equip_id` casa com
    `EquipamentoEquipe.equip_id` do catálogo (ADR-157) — não com `RecursoContrato.
    tipo_id`, que é um hash de composição de equipe inteira (ADR-046/156).
    """
    ativos_tipo = [a for a in roster if a.equip_id == equip_id]
    custo: dict[str, float] = {}
    for semana in enumerar_semanas(semana_inicio, semana_fim):
        total_semana = sum(_custo_semanal_ativo(a) for a in ativos_tipo if _ativo_ativo_na_semana(a, semana))
        custo[semana] = round(total_semana, 2)
    return custo


def custo_real_eq_idle_semanal(
    roster: list[AtivoEquipamentoReal],
    equip_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> dict[str, float]:
    """ADR-158: custo real de equipamento OCIOSO por semana — só locação, sem
    manutenção. Espelha o fallback calibrado (`custo_idle_semanal_unit = cus_mo +
    cus_locacao`, `_pool_contrato_demanda.py::_resolve_gap_max_e_idle_efetivo`):
    equipamento ocioso continua sob contrato de locação (custo fixo), mas não
    incorre manutenção ativa. Mesma estrutura de `custo_real_eq_semanal`.
    """
    ativos_tipo = [a for a in roster if a.equip_id == equip_id]
    custo: dict[str, float] = {}
    for semana in enumerar_semanas(semana_inicio, semana_fim):
        total_semana = sum(_custo_semanal_ativo_idle(a) for a in ativos_tipo if _ativo_ativo_na_semana(a, semana))
        custo[semana] = round(total_semana, 2)
    return custo


def taxa_media_eq_idle_real(contrato: RecursoContrato, roster: list[AtivoEquipamentoReal]) -> float:
    """ADR-160: taxa média real de EQ ocioso para um contrato inteiro — mesma
    lógica de agregação de `aplicar_roster_custo_real_eq` (ADR-157), trocando o
    numerador para `custo_real_eq_idle_semanal`. Não verifica cobertura — isso é
    responsabilidade do chamador (ver ADR-160 D3). Retorna 0.0 quando a
    composição de equipamentos do contrato está vazia.
    """
    if not contrato.composicao_equipamentos_eq:
        return 0.0
    custo_real_total = sum(
        sum(custo_real_eq_idle_semanal(roster, equip_id, contrato.semana_inicio, contrato.semana_fim).values())
        for equip_id in contrato.composicao_equipamentos_eq
    )
    denom = contrato.quantidade_contratada * contrato.semanas_contrato
    return round(custo_real_total / denom, 4) if denom > 0 else 0.0


def custo_real_eq_total(
    roster: list[AtivoEquipamentoReal],
    equip_id: str,
    semana_inicio: str,
    semana_fim: str,
) -> float:
    """Custo real total de equipamento no span — soma de `custo_real_eq_semanal`."""
    return round(sum(custo_real_eq_semanal(roster, equip_id, semana_inicio, semana_fim).values()), 2)


def custo_semanal_individual_eq(
    ativo: AtivoEquipamentoReal,
    semana_inicio: str,
    semana_fim: str,
) -> list[dict]:
    """ADR-173 D13 — custo semanal detalhado de UMA instância de equipamento:
    só direto (locação+manutenção) — equipamento não tem análogo de custo
    indireto (EPI/treinamento/exame/benefício são conceitos exclusivamente
    humanos, ADR-165). Restrito às semanas em que o ativo está sob contrato
    dentro do span informado.

    A soma de `custo_total` da lista retornada é, por construção, o custo total
    de permanência real da instância no span — equivalente a
    `custo_real_eq_total([ativo], ...)`, com detalhamento semana a semana.
    """
    itens: list[dict] = []
    for semana in enumerar_semanas(semana_inicio, semana_fim):
        if not _ativo_ativo_na_semana(ativo, semana):
            continue
        custo_direto = round(_custo_semanal_ativo(ativo), 2)
        itens.append({"semana": semana, "custo_direto": custo_direto, "custo_total": custo_direto})
    return itens
