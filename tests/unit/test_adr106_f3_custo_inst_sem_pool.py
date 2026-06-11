"""ADR-106 F3 — Preencher custo_inst_* para equipes sem pool contracts.

TDD: testes escritos antes da implementação.

F3 introduz _fill_custo_inst_sem_pool(equipes) em equipe_custo_engine.py:
  - Para cada equipe com custo_inst_mo is None, usa DirectTeamCostStrategy
  - Equipes com pool (custo_inst_mo already set) não são modificadas

Invariantes:
  - Após _fill_custo_inst_sem_pool: TODAS equipes têm custo_inst_mo is not None
  - IC-3: |soma(custo_inst_*) - custo_total| < 0.05 para toda equipe
  - Equipes com pool preservadas (não sobrescritas)
"""

from __future__ import annotations

import pytest


def _make_equipe(
    item_id: str = "i1",
    custo_total: float = 400_000.0,
    custo_mao_obra_mensal: float = 20_000.0,
    custo_encargos_mensal: float = 35_540.0,
    custo_equipamentos_mensal: float = 15_000.0,
    custo_combustivel_total_mensal: float = 5_000.0,
    permanencia_efetiva_meses: float = 6.0,
    custo_inst_mo=None,  # None = sem pool; valor = com pool
):
    from concilium.domain.models.canonical import EquipeDireta, FuncaoEquipeDireta

    return EquipeDireta(
        equipe_id=f"eq-{item_id}",
        item_id=item_id,
        cpu_id="CPU-1",
        nome=f"Equipe {item_id}",
        num_equipes_base=1,
        funcoes=[FuncaoEquipeDireta(funcao_id="F1", num_pessoas=2)],
        custo_mao_obra_mensal=custo_mao_obra_mensal,
        custo_encargos_mensal=custo_encargos_mensal,
        custo_equipamentos_mensal=custo_equipamentos_mensal,
        custo_combustivel_total_mensal=custo_combustivel_total_mensal,
        permanencia_meses=permanencia_efetiva_meses,
        permanencia_efetiva_meses=permanencia_efetiva_meses,
        custo_total=custo_total,
        custo_inst_mo=custo_inst_mo,
        custo_inst_eq=0.0 if custo_inst_mo is not None else None,
        custo_inst_comb=0.0 if custo_inst_mo is not None else None,
        custo_inst_mat=0.0 if custo_inst_mo is not None else None,
        custo_inst_mob_demob=0.0 if custo_inst_mo is not None else None,
    )


def _import():
    from concilium.domain.services.equipe_custo_engine import _fill_custo_inst_sem_pool

    return _fill_custo_inst_sem_pool


class TestFillCustoInstSemPool:
    def test_funcao_importavel(self):
        _import()

    def test_equipe_sem_pool_fica_preenchida(self):
        fill = _import()
        equipes = [_make_equipe("i1")]
        assert equipes[0].custo_inst_mo is None

        fill(equipes)

        assert equipes[0].custo_inst_mo is not None
        assert equipes[0].custo_inst_eq is not None
        assert equipes[0].custo_inst_comb is not None
        assert equipes[0].custo_inst_mat is not None
        assert equipes[0].custo_inst_mob_demob is not None

    def test_equipe_com_pool_nao_e_sobrescrita(self):
        """Equipes com pool (custo_inst_mo already set) devem ser preservadas."""
        fill = _import()
        valor_original = 50_000.0
        eq_com_pool = _make_equipe("i1", custo_inst_mo=valor_original)
        fill([eq_com_pool])
        assert eq_com_pool.custo_inst_mo == pytest.approx(valor_original)

    def test_mistura_pool_e_sem_pool(self):
        fill = _import()
        equipes = [
            _make_equipe("i1", custo_inst_mo=None),  # sem pool → deve preencher
            _make_equipe("i2", custo_inst_mo=99_999.0),  # com pool → preservar
        ]
        fill(equipes)
        assert equipes[0].custo_inst_mo is not None  # preenchido
        assert equipes[1].custo_inst_mo == pytest.approx(99_999.0)  # preservado

    def test_invariante_decomposicao_ic3(self):
        """IC-3: soma(custo_inst_*) ≈ custo_total (tolerância 0.10 para arredondamentos)."""
        fill = _import()
        custo_total = 456_240.0
        equipes = [_make_equipe("i1", custo_total=custo_total)]
        fill(equipes)

        eq = equipes[0]
        soma = (
            (eq.custo_inst_mo or 0)
            + (eq.custo_inst_eq or 0)
            + (eq.custo_inst_comb or 0)
            + (eq.custo_inst_mat or 0)
            + (eq.custo_inst_mob_demob or 0)
        )
        desvio = abs(soma - custo_total)
        assert desvio < 0.10, f"decomposição não fecha: soma={soma:.2f}, total={custo_total:.2f}"

    def test_lista_vazia_sem_erro(self):
        fill = _import()
        fill([])  # não deve levantar exceção

    def test_permanencia_zero_nao_divide_por_zero(self):
        fill = _import()
        eq = _make_equipe("i1", permanencia_efetiva_meses=0.0, custo_total=0.0)
        fill([eq])  # não deve levantar ZeroDivisionError
        assert eq.custo_inst_mo is not None
