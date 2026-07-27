"""ADR-154 F1 — Roster Real de Mão-de-Obra: Custo Individualizado: TDD.

Cobre:
  - `MembroEquipeReal`: pessoa real com salário, categoria sindical, data de
    admissão/desligamento.
  - `custo_real_mo_semanal`: soma, por semana ISO, o custo real (salário/encargos)
    de cada membro ativo naquela função e naquele intervalo.
  - `custo_real_mo_total`: soma agregada de `custo_real_mo_semanal`.

Escrito antes da implementação (red phase). Sem nenhuma ligação com
InstanciaRecurso/segmentos/scheduling — o pool RCPSP continua fungível; isto é
puramente uma camada de custo bottom-up a partir de pessoas reais.
"""

from __future__ import annotations

from datetime import date

from concilium.domain.constants import ENCARGOS_CLT, ENCARGOS_MENSALISTA, SEMANAS_POR_MES
from concilium.domain.models.canonical import MembroEquipeReal
from concilium.domain.services.financial.roster_custo_mo import (
    custo_real_mo_semanal,
    custo_real_mo_total,
)


def _membro(**overrides) -> MembroEquipeReal:
    defaults = dict(
        individuo_id="joao-001",
        funcao_id="PEDREIRO",
        salario_base_mensal=3000.0,
        categoria_sindical="horista",
        data_admissao=date(2026, 1, 1),
    )
    defaults.update(overrides)
    return MembroEquipeReal(**defaults)


class TestCustoRealMoSemanal:
    def test_membro_ativo_toda_a_semana_conta_custo_cheio(self):
        membro = _membro()
        custo = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W02")
        esperado = round((3000.0 / SEMANAS_POR_MES) * (1 + ENCARGOS_CLT), 2)
        assert custo["2026-W02"] == esperado

    def test_membro_admitido_no_meio_do_span_so_conta_a_partir_da_semana_de_admissao(self):
        # 2026-W03 = 12 a 18 de janeiro de 2026
        membro = _membro(data_admissao=date(2026, 1, 15))
        custo = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W04")
        assert "2026-W02" not in custo or custo["2026-W02"] == 0.0
        assert custo["2026-W03"] > 0.0
        assert custo["2026-W04"] > 0.0

    def test_membro_desligado_no_meio_do_span_so_conta_ate_a_semana_de_desligamento(self):
        membro = _membro(data_desligamento=date(2026, 1, 15))  # cai em 2026-W03
        custo = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W04")
        assert custo["2026-W02"] > 0.0
        assert custo["2026-W03"] > 0.0
        assert custo.get("2026-W04", 0.0) == 0.0

    def test_membro_sem_desligamento_conta_em_todas_as_semanas_do_span(self):
        membro = _membro(data_desligamento=None)
        custo = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W10")
        assert all(custo[w] > 0.0 for w in custo)
        assert len(custo) == 9  # W02..W10 inclusive

    def test_membro_de_outra_funcao_e_ignorado(self):
        membro = _membro(funcao_id="ELETRICISTA")
        custo = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W02")
        assert custo.get("2026-W02", 0.0) == 0.0

    def test_encargo_resolvido_via_categoria_sindical_mensalista(self):
        membro = _membro(categoria_sindical="mensalista")
        custo = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W02")
        esperado = round((3000.0 / SEMANAS_POR_MES) * (1 + ENCARGOS_MENSALISTA), 2)
        assert custo["2026-W02"] == esperado

    def test_encargo_override_local_tem_precedencia_sobre_categoria(self):
        membro = _membro(categoria_sindical="horista", percentual_encargos_local=0.5)
        custo = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W02")
        esperado = round((3000.0 / SEMANAS_POR_MES) * 1.5, 2)
        assert custo["2026-W02"] == esperado

    def test_multiplos_membros_somam_por_semana(self):
        m1 = _membro(individuo_id="joao-001", salario_base_mensal=3000.0)
        m2 = _membro(individuo_id="maria-002", salario_base_mensal=4000.0)
        custo = custo_real_mo_semanal([m1, m2], "PEDREIRO", "2026-W02", "2026-W02")
        esperado = round((3000.0 / SEMANAS_POR_MES) * (1 + ENCARGOS_CLT), 2) + round(
            (4000.0 / SEMANAS_POR_MES) * (1 + ENCARGOS_CLT), 2
        )
        assert custo["2026-W02"] == round(esperado, 2)


class TestCustoRealMoTotal:
    def test_total_e_soma_do_semanal(self):
        membro = _membro()
        semanal = custo_real_mo_semanal([membro], "PEDREIRO", "2026-W02", "2026-W04")
        total = custo_real_mo_total([membro], "PEDREIRO", "2026-W02", "2026-W04")
        assert total == round(sum(semanal.values()), 2)
