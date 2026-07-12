"""ADR-080: Helpers de custo diferenciado de permanência por instância.

Funções expostas:
  ``calcular_custo_contrato_por_instancia`` — custo de uma instância de pool
    usando taxa ativa (c_unit) para semanas ativas e taxa ociosa (c_idle) para
    standby, incluindo mob/demob.

Semântica:
  custo = c_unit × active_weeks
        + rate_standby × standby_weeks     (rate = c_idle se c_idle>0, else c_unit)
        + c_mob + c_demob
"""

from __future__ import annotations


def calcular_custo_contrato_por_instancia(
    active_weeks: int,
    standby_weeks: int,
    custo_unit_semanal: float,
    custo_idle_semanal: float,
    custo_mob: float,
    custo_demob: float,
) -> float:
    """Custo total de uma instância de pool para seu ciclo de vida.

    ADR-080 §B — Taxa Ociosa Diferenciada:
    - Semanas ativas: cobradas a ``custo_unit_semanal`` (inclui MO + EQ + combustível)
    - Semanas standby: cobradas a ``custo_idle_semanal`` (apenas aluguel de equipamento)
      - Fallback: quando ``custo_idle_semanal == 0``, usa ``custo_unit_semanal`` (legado)

    ADR-080 §C — Desmobilização Antecipada Efetiva:
    - O chamador passa ``standby_weeks=0`` e ``custo_demob`` para refletir early demob
    - Quando trailing standby é eliminado, ``standby_weeks=0``, custo_demob é pago

    ADR-080 §A — Mobilização Tardia:
    - O chamador ajusta ``active_weeks`` e ``standby_weeks`` com base na janela real
      [semana_mobilizacao_i, semana_desmobilizacao_i] em vez do span global do contrato

    Compatibilidade retroativa (ADR-079):
    - ``custo_idle_semanal=0`` → standby cobrado a taxa plena (comportamento anterior)
    """
    rate_standby = custo_idle_semanal if custo_idle_semanal > 0 else custo_unit_semanal
    return custo_unit_semanal * active_weeks + rate_standby * standby_weeks + custo_mob + custo_demob


# ADR-136 F5: calcular_custo_instancia_composicional() foi consolidada em
# concilium.domain.services.financial.equipe_custo_engine.LifecycleEngine.calcular()
# — paridade numérica confirmada (inclusive com mob/demob efetivos) em
# tests/unit/test_adr106_f1_lifecycle_engine.py::TestParidadeComHelperExistente antes
# da remoção. _compute_instancia_lifecycle (_resource_instance_assignment.py) chama o
# engine diretamente; esta função não tem mais chamadores em produção.
