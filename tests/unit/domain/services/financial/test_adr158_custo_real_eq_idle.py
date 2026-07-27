"""ADR-158 D1 — custo_real_eq_idle_semanal: TDD.

Espelha o fallback calibrado (custo_idle_semanal_unit = cus_mo + cus_locacao,
_pool_contrato_demanda.py::_resolve_gap_max_e_idle_efetivo): equipamento ocioso
continua sob contrato de locação (custo fixo), mas não incorre manutenção ativa.

Escrito antes da implementação (red phase).
"""

from __future__ import annotations

from datetime import date

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import AtivoEquipamentoReal
from concilium.domain.services.financial.roster_custo_equipamento import (
    custo_real_eq_idle_semanal,
)


def _ativo(**overrides) -> AtivoEquipamentoReal:
    defaults = dict(
        ativo_id="ESC-001",
        equip_id="EQ-E0019",
        custo_locacao_mensal_real=20000.0,
        custo_manutencao_mensal_real=2000.0,
        data_contrato_inicio=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return AtivoEquipamentoReal(**defaults)


class TestCustoRealEqIdleSemanal:
    def test_custo_ocioso_exclui_manutencao(self):
        ativo = _ativo()
        custo = custo_real_eq_idle_semanal([ativo], "EQ-E0019", "2026-W02", "2026-W02")
        esperado = round(20000.0 / SEMANAS_POR_MES, 2)  # só locação, sem manutenção
        assert custo["2026-W02"] == esperado

    def test_custo_ocioso_menor_que_custo_ativo(self):
        from concilium.domain.services.financial.roster_custo_equipamento import custo_real_eq_semanal

        ativo = _ativo()
        idle = custo_real_eq_idle_semanal([ativo], "EQ-E0019", "2026-W02", "2026-W02")
        ativo_cost = custo_real_eq_semanal([ativo], "EQ-E0019", "2026-W02", "2026-W02")
        assert idle["2026-W02"] < ativo_cost["2026-W02"]

    def test_ativo_de_outro_equip_id_e_ignorado(self):
        ativo = _ativo(equip_id="EQ-E0007")
        custo = custo_real_eq_idle_semanal([ativo], "EQ-E0019", "2026-W02", "2026-W02")
        assert custo.get("2026-W02", 0.0) == 0.0

    def test_ativo_sem_contrato_ativo_na_semana_conta_zero(self):
        ativo = _ativo(data_contrato_inicio=date(2026, 2, 1))
        custo = custo_real_eq_idle_semanal([ativo], "EQ-E0019", "2026-W02", "2026-W02")
        assert custo["2026-W02"] == 0.0
