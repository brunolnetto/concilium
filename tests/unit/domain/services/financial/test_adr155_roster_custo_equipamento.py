"""ADR-155 F1 — Roster Real de Equipamento: Custo Individualizado: TDD.

Cobre:
  - `AtivoEquipamentoReal`: ativo real com contrato de locação real (locação +
    manutenção mensal) e datas reais de início/fim de contrato.
  - `custo_real_eq_semanal`: soma, por semana ISO, o custo real (locação +
    manutenção) de cada ativo ativo naquele tipo e naquele intervalo.
  - `custo_real_eq_total`: soma agregada de `custo_real_eq_semanal`.

Escrito antes da implementação (red phase). Sem nenhuma ligação com
InstanciaRecurso/segmentos/scheduling — o pool RCPSP continua fungível; isto é
puramente uma camada de custo bottom-up a partir de ativos reais. Estrutura
irmã de ADR-154 (roster de mão-de-obra).
"""

from __future__ import annotations

from datetime import date

from concilium.domain.constants import SEMANAS_POR_MES
from concilium.domain.models.canonical import AtivoEquipamentoReal
from concilium.domain.services.financial.roster_custo_equipamento import (
    custo_real_eq_semanal,
    custo_real_eq_total,
)


def _ativo(**overrides) -> AtivoEquipamentoReal:
    defaults = dict(
        ativo_id="ESC-001",
        tipo_id="ESC-3CAT",
        custo_locacao_mensal_real=20000.0,
        custo_manutencao_mensal_real=2000.0,
        data_contrato_inicio=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return AtivoEquipamentoReal(**defaults)


class TestCustoRealEqSemanal:
    def test_ativo_com_contrato_ativo_toda_a_semana_conta_custo_cheio(self):
        ativo = _ativo()
        custo = custo_real_eq_semanal([ativo], "ESC-3CAT", "2026-W02", "2026-W02")
        esperado = round((20000.0 + 2000.0) / SEMANAS_POR_MES, 2)
        assert custo["2026-W02"] == esperado

    def test_ativo_com_contrato_iniciado_no_meio_do_span_so_conta_a_partir_da_semana(self):
        # 2026-W03 = 12 a 18 de janeiro de 2026
        ativo = _ativo(data_contrato_inicio=date(2026, 1, 15))
        custo = custo_real_eq_semanal([ativo], "ESC-3CAT", "2026-W02", "2026-W04")
        assert custo.get("2026-W02", 0.0) == 0.0
        assert custo["2026-W03"] > 0.0
        assert custo["2026-W04"] > 0.0

    def test_ativo_com_contrato_encerrado_no_meio_do_span_so_conta_ate_a_semana(self):
        ativo = _ativo(data_contrato_fim=date(2026, 1, 15))  # cai em 2026-W03
        custo = custo_real_eq_semanal([ativo], "ESC-3CAT", "2026-W02", "2026-W04")
        assert custo["2026-W02"] > 0.0
        assert custo["2026-W03"] > 0.0
        assert custo.get("2026-W04", 0.0) == 0.0

    def test_ativo_sem_data_fim_conta_em_todas_as_semanas_do_span(self):
        ativo = _ativo(data_contrato_fim=None)
        custo = custo_real_eq_semanal([ativo], "ESC-3CAT", "2026-W02", "2026-W10")
        assert all(custo[w] > 0.0 for w in custo)
        assert len(custo) == 9  # W02..W10 inclusive

    def test_ativo_de_outro_tipo_e_ignorado(self):
        ativo = _ativo(tipo_id="CAM-BASC")
        custo = custo_real_eq_semanal([ativo], "ESC-3CAT", "2026-W02", "2026-W02")
        assert custo.get("2026-W02", 0.0) == 0.0

    def test_custo_soma_locacao_e_manutencao(self):
        ativo = _ativo(custo_locacao_mensal_real=10000.0, custo_manutencao_mensal_real=500.0)
        custo = custo_real_eq_semanal([ativo], "ESC-3CAT", "2026-W02", "2026-W02")
        esperado = round(10500.0 / SEMANAS_POR_MES, 2)
        assert custo["2026-W02"] == esperado

    def test_multiplos_ativos_do_mesmo_tipo_somam_por_semana(self):
        a1 = _ativo(ativo_id="ESC-001", custo_locacao_mensal_real=20000.0, custo_manutencao_mensal_real=0.0)
        a2 = _ativo(ativo_id="ESC-002", custo_locacao_mensal_real=18000.0, custo_manutencao_mensal_real=0.0)
        custo = custo_real_eq_semanal([a1, a2], "ESC-3CAT", "2026-W02", "2026-W02")
        esperado = round(20000.0 / SEMANAS_POR_MES, 2) + round(18000.0 / SEMANAS_POR_MES, 2)
        assert custo["2026-W02"] == round(esperado, 2)


class TestCustoRealEqTotal:
    def test_total_e_soma_do_semanal(self):
        ativo = _ativo()
        semanal = custo_real_eq_semanal([ativo], "ESC-3CAT", "2026-W02", "2026-W04")
        total = custo_real_eq_total([ativo], "ESC-3CAT", "2026-W02", "2026-W04")
        assert total == round(sum(semanal.values()), 2)
