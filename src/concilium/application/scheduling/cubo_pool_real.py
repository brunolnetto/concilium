"""ADR-160 D3 — Cubo de pool real: composição transiente, sem registro persistente.

Compõe ADR-152 (`project_ocupacao_semanal`) + ADR-154/155 (roster real, sempre
passado como parâmetro simples — nunca lido de catálogo/Escopo/banco) +
ADR-156/157 (`aplicar_roster_custo_real_mo`/`_eq`, reaproveitadas aqui só como
cálculo de taxa "sombra": o `RecursoContrato` original nunca é mutado nem salvo
de volta) + ADR-158 (`custo_real_instancia_semanal`).

Retorna `None` quando o roster não cobre integralmente a composição declarada
— nunca mistura número real parcial com calibrado no mesmo timeline. Nenhuma
entidade de roster, cubo ou timeline é persistida por este módulo.
"""

from __future__ import annotations

from concilium.application.scheduling.custo_real_instancia import custo_real_instancia_semanal
from concilium.domain.models.canonical import (
    AtivoEquipamentoReal,
    InstanciaRecurso,
    MembroEquipeReal,
    RecursoContrato,
)
from concilium.domain.services.financial.roster_custo_eq_substituicao import (
    aplicar_roster_custo_real_eq,
    roster_cobre_composicao_eq,
)
from concilium.domain.services.financial.roster_custo_equipamento import taxa_media_eq_idle_real
from concilium.domain.services.financial.roster_custo_mo_substituicao import (
    aplicar_roster_custo_real_mo,
    roster_cobre_composicao_mo,
)


def gerar_timeline_real_instancias(
    contrato: RecursoContrato,
    instancias: list[InstanciaRecurso],
    roster_mo: list[MembroEquipeReal],
    roster_eq: list[AtivoEquipamentoReal],
) -> dict[str, dict[str, float]] | None:
    """Gera a timeline de custo real (ADR-158) de cada instância de um contrato,
    a partir de um roster passado transientemente nesta chamada.

    Retorna `None` se o roster não cobrir integralmente a composição de MO OU de
    equipamento do contrato (quando declaradas) — nunca mistura número real
    parcial com calibrado.

    Não persiste nada: `aplicar_roster_custo_real_mo`/`_eq` são usadas aqui só
    para calcular a taxa "sombra" (`contrato_real`, cópia local via
    `model_copy`) — o `RecursoContrato` recebido como argumento nunca é
    modificado nem salvo.
    """
    if contrato.composicao_funcoes_mo and not roster_cobre_composicao_mo(contrato, roster_mo):
        return None
    if contrato.composicao_equipamentos_eq and not roster_cobre_composicao_eq(contrato, roster_eq):
        return None

    contrato_real = aplicar_roster_custo_real_mo(contrato, roster_mo)
    contrato_real = aplicar_roster_custo_real_eq(contrato_real, roster_eq)
    cus_eq_idle_real = (
        taxa_media_eq_idle_real(contrato, roster_eq)
        if contrato.composicao_equipamentos_eq
        else contrato_real.custo_unit_semanal_eq
    )

    instancias_do_contrato = [i for i in instancias if i.contrato_id == contrato.contrato_id]
    return {
        i.instancia_id: custo_real_instancia_semanal(
            i,
            cus_mo_real=contrato_real.custo_unit_semanal_mo,
            cus_eq_real=contrato_real.custo_unit_semanal_eq,
            cus_eq_idle_real=cus_eq_idle_real,
        )
        for i in instancias_do_contrato
    }
