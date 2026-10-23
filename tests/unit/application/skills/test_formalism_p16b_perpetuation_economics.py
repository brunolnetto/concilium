"""P16-B: local exact contractual keep-vs-restart witnesses.

This is a boundary contract for homogeneous fungible instances, not yet an
oracle for global joint (workforce, calendar, pool) optimization.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[4]
HELPERS = (
    ROOT / "src/concilium/application/skills/manifests"
    / "05-equipes-e-alocacao/_skill_helpers/__init__.py"
)


def _helpers() -> ModuleType:
    name = "_formalism_p16b_test_helpers"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, HELPERS, submodule_search_locations=[str(HELPERS.parent)]
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _items(required: int) -> list[dict]:
    return [
        {
            "item_id": item, "required": required,
            "start_idx": j, "end_idx": j + 1,
            "semana_inicio": f"2026-W{j:02d}",
            "semana_fim": f"2026-W{j:02d}",
            "active_weeks": [f"2026-W{j:02d}"],
            "machine_weeks": required,
        }
        for item, j in (("A", 1), ("B", 3))
    ]


def _chains(
    required: int,
    idle: float,
    *,
    gap_max: int = 2,
    mob: float = 80,
    demob: float = 80,
):
    return _helpers()._build_perpetuation_chains(
        tipo_id="GUINDASTE",
        items=_items(required),
        custo_mob_unit=mob,
        custo_demob_unit=demob,
        custo_standby_unit=idle,
        gap_max=gap_max,
        week_demand={"2026-W01": required, "2026-W03": required},
    )


def test_compare_idle_and_restart_for_the_same_two_instances() -> None:
    # Gap=1: keep 2*100=200; restart 2*(80+80)=320. Keep.
    chains = _chains(2, 100)
    assert len(chains) == 1
    assert chains[0].semanas_ociosas == 1
    assert chains[0].custo_standby == pytest.approx(200)


def test_exact_economic_tie_prefers_fewer_mobilizations() -> None:
    # Gap=1: keep 2*160=320 == restart 2*(80+80)=320.
    assert len(_chains(2, 160)) == 1
    assert len(_chains(1, 160)) == 1


def test_more_expensive_standby_splits_into_distinct_chains() -> None:
    assert len(_chains(2, 161)) == 2


def test_physical_gap_cap_overrides_cheaper_standby() -> None:
    assert len(_chains(2, 1, gap_max=0)) == 2


@pytest.mark.parametrize(
    ("mob", "demob", "idle", "expected"),
    [
        (100, 100, 100, 2),  # exact tie at k=2 is allowed
        (100, 100, 101, 1),
        (0, 0, 100, 0),
        (0.1, 0.2, 0.1, 3),  # decimal 0.1+0.2 has exact ratio 3
    ],
)
def test_inclusive_economic_gap_cap(
    mob: float, demob: float, idle: float, expected: int
) -> None:
    result_idle, gap = _helpers()._resolve_gap_max_e_idle_efetivo(
        mob, demob, idle, False, 0.0, 0.0
    )
    assert result_idle == idle
    assert gap == expected


@pytest.mark.parametrize("unit", ["dia_cal", "mes"])
def test_downstream_sharing_preprocessor_uses_same_inclusive_boundary(unit: str) -> None:
    from types import SimpleNamespace

    mod = _helpers()
    costs = {
        "GUINDASTE": {
            "custo_mob_unit": 100.0,
            "custo_demob_unit": 100.0,
            "custo_idle_semanal_unit": 100.0,
            "unidade_faturamento": unit,
        }
    }
    assert mod._gap_max_economico(100, 100, 100, unit) == 2
    gap_by_type = mod._bppc_build_gap_max_lookup(costs)
    assert gap_by_type["GUINDASTE"] == 2
    contract = SimpleNamespace(tipo_id="GUINDASTE", gap_max_economico=1)
    mod._bppc_atualizar_contratos([contract], costs, gap_by_type)
    assert contract.gap_max_economico == 2


def test_downstream_decimal_gap_matches_upstream_contract() -> None:
    mod = _helpers()
    assert mod._gap_max_economico(0.1, 0.2, 0.1, "dia_cal") == 3
    _, upstream = mod._resolve_gap_max_e_idle_efetivo(0.1, 0.2, 0.1, False, 0, 0)
    assert upstream == 3


@pytest.mark.parametrize(
    ("mob", "demob", "idle", "expected"),
    [
        (80_000.0, 40_000.0, 12_000.0, 10),
        (100.0, 100.0, 100.0, 2),
        (0.1, 0.2, 0.1, 3),
        (-100.0, 0.0, 20.0, 0),
        (100.0, 0.0, 0.0, 9999),
    ],
)
def test_contract_bound_equals_sharing_preprocessor_bound(
    mob: float, demob: float, idle: float, expected: int
) -> None:
    """The contractual and pre-processing paths must not disagree."""
    mod = _helpers()
    _, contract_bound = mod._resolve_gap_max_e_idle_efetivo(
        mob, demob, idle, False, 0.0, 0.0
    )
    assert contract_bound == expected
    assert mod._gap_max_economico(mob, demob, idle, "dia_cal") == expected
