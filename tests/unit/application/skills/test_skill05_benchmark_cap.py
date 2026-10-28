"""Regression tests for preserving financial decomposition after benchmark caps."""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

# Register the dynamic Skill05 package before importing its private helper.
from concilium.application.skills import run_equipes_e_alocacao

_ = run_equipes_e_alocacao
_instancias = importlib.import_module(
    "_concilium_skillpkg_05_equipes_e_alocacao._skill_helpers.instancias"
)


def _equipe(*, total: float = 200.0, components=(100.0, 50.0, 30.0, 20.0)):
    return SimpleNamespace(
        item_id="eap-A",
        custo_total=total,
        custo_inst_mo=components[0],
        custo_inst_eq=components[1],
        custo_inst_mat=components[2],
        custo_inst_comb=components[3],
        custo_inst_mob_demob=10.0,
    )


def _apply_cap(
    equipe, cap: float, benchmark_mode: bool = True, validacoes: list | None = None
) -> None:
    _instancias._limitar_custo_por_planejamento_benchmark(
        [equipe], benchmark_mode, {}, {"eap-A": cap}, validacoes
    )


def test_pool_breakdown_is_reconciled_when_benchmark_caps_expense():
    eq = _equipe()
    _apply_cap(eq, 100.0)
    assert eq.custo_total == 100.0
    assert (eq.custo_inst_mo, eq.custo_inst_eq,
            eq.custo_inst_mat, eq.custo_inst_comb) == (50.0, 25.0, 15.0, 10.0)
    assert eq.custo_inst_mob_demob == 5.0
    assert sum((eq.custo_inst_mo, eq.custo_inst_eq,
                eq.custo_inst_mat, eq.custo_inst_comb)) == pytest.approx(eq.custo_total)


def test_cent_level_caps_never_invent_negative_component():
    eq = _equipe(total=0.04, components=(0.01, 0.01, 0.01, 0.01))
    _apply_cap(eq, 0.01)
    values = (eq.custo_inst_mo, eq.custo_inst_eq,
              eq.custo_inst_mat, eq.custo_inst_comb)
    assert sum(values) == pytest.approx(0.01)
    assert all(value >= 0 for value in values)
    assert values == (0.01, 0.0, 0.0, 0.0)


@pytest.mark.parametrize("invalid_component", [float("nan"), float("inf"), -1.0])
def test_invalid_complete_breakdown_blocks_benchmark_cap(invalid_component):
    eq = _equipe(components=(invalid_component, 50.0, 30.0, 20.0))
    validacoes = []

    _apply_cap(eq, 100.0, validacoes=validacoes)

    # Leave the original cost and decomposition untouched rather than applying
    # a cap against component data that cannot be reconciled safely.
    assert eq.custo_total == 200.0
    assert eq.custo_inst_eq == 50.0
    assert any(v.codigo == "VAL-BENCHMARK-CAP-DECOMPOSICAO" and v.status == "ERRO" for v in validacoes)


def test_zero_complete_breakdown_blocks_benchmark_cap():
    eq = _equipe(components=(0.0, 0.0, 0.0, 0.0))
    validacoes = []

    _apply_cap(eq, 100.0, validacoes=validacoes)

    assert eq.custo_total == 200.0
    assert any(v.codigo == "VAL-BENCHMARK-CAP-DECOMPOSICAO" and v.status == "ERRO" for v in validacoes)


def test_non_benchmark_does_not_redistribute_or_cap_costs():
    eq = _equipe()
    _apply_cap(eq, 100.0, benchmark_mode=False)
    assert eq.custo_total == 200.0
    assert eq.custo_inst_mo == 100.0
    assert eq.custo_inst_mob_demob == 10.0


def test_higher_reference_does_not_change_measured_costs():
    eq = _equipe()
    _apply_cap(eq, 300.0)
    assert eq.custo_total == 200.0
    assert eq.custo_inst_mo == 100.0


def test_absent_instancial_breakdown_is_not_fabricated_by_benchmark_cap():
    eq = _equipe()
    eq.custo_inst_mo = None
    _apply_cap(eq, 100.0)
    assert eq.custo_total == 100.0
    assert eq.custo_inst_mo is None
