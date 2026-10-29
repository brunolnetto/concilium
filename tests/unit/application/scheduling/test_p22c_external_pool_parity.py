"""P22-C external-runtime mutation gate; oracle never imports production helpers.

Production P16 is independently adapted to a small factual snapshot and
compared against the hand-checked physical/economic golden reference.
"""
from __future__ import annotations

import json
from copy import deepcopy
from fractions import Fraction as F
from pathlib import Path

import pytest

from concilium.application.scheduling.resource_demand_levels import (
    normalize_weekly_resource_demand,
)
from concilium.application.scheduling.resource_level_contracts import (
    ResourceTariff,
    optimize_homogeneous_pool,
)
from tests.reference_formalism.economic_reference import compare_external_pool
from tests.reference_formalism.protocol import ReferenceContractError

VECTORS = (
    Path(__file__).resolve().parents[3]
    / "reference_formalism/vectors/economic_reconciliation_v1.json"
)


def reference_case(case_id: str) -> dict:
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    return next(case for case in data["vectors"] if case["case_id"] == case_id)


def _actual_pool(case: dict) -> dict:
    contract = case["inputs"]["contract"]
    demand = case["inputs"]["demand"]
    weeks = tuple(f"S{i + 1:03d}" for i in range(len(demand)))
    physical = normalize_weekly_resource_demand(
        weeks, {"A": {"EXC": demand}},
    )
    tariff = ResourceTariff(
        F(contract["active"]), F(contract["idle"]),
        F(contract["movement"]) / 2, F(contract["movement"]) / 2,
        contract["max_idle_gap"],
    )
    ledger = optimize_homogeneous_pool(physical, {"EXC": tariff}).ledgers[0]
    return {
        "demand": list(ledger.demand),
        "presence": list(ledger.presence),
        "standby": list(ledger.standby),
        "chains": len(ledger.chains),
        "active_cost": str(ledger.active_cost),
        "idle_cost": str(ledger.standby_cost),
        "movement_cost": str(ledger.mobility_cost),
    }


def test_real_p16_discounted_ledger_matches_independent_reference() -> None:
    case = reference_case("discounted_pool_measured_loss_and_exclusive_k_v_ind")
    observed = _actual_pool(case)
    compare_external_pool(case, observed)
    assert (observed["active_cost"], observed["idle_cost"],
            observed["movement_cost"]) == ("200", "50", "80")


def test_intentional_mutation_in_real_production_output_is_rejected() -> None:
    case = reference_case("discounted_pool_measured_loss_and_exclusive_k_v_ind")
    observed = _actual_pool(case)
    damaged = deepcopy(observed)
    damaged["idle_cost"] = "0"  # malicious/accidental omission of paid standby
    with pytest.raises(ReferenceContractError, match="idle_cost"):
        compare_external_pool(case, damaged)


def test_actual_p16_global_instance_assignment_matches_fungible_oracle() -> None:
    case = reference_case("fungible_reassignment_92_not_fixed_layers_120")
    production = _actual_pool(case)
    compare_external_pool(case, production)
    assert (production["active_cost"], production["idle_cost"],
            production["movement_cost"]) == ("30", "2", "60")
    assert production["chains"] == 2
    assert production["presence"] == [2, 2, 2, 2]
    assert production["standby"] == [0, 1, 1, 0]
