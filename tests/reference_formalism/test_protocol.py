"""P22-A: independent protocol examples and intentional negative mutations."""
from __future__ import annotations

import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.reference_formalism.protocol import (
    ReferenceContractError,
    evaluate_vector,
    verify_golden,
)

HERE = Path(__file__).resolve().parent
VECTORS = HERE / "vectors" / "scalar_baseline_v1.json"


def cases() -> list[dict]:
    data = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert data["protocol"] == "formalism-reference/1"
    assert data["formalism"]["baseline_blob"] == "8e67c89df4e43147394210ea8acc4094ffbf5384"
    return data["vectors"]


@pytest.mark.parametrize("vector", cases(), ids=lambda vector: vector["case_id"])
def test_hand_checked_vectors(vector: dict) -> None:
    assert verify_golden(vector)["scope_residual"] == "0"


def test_changed_expected_value_is_rejected() -> None:
    vector = deepcopy(cases()[0])
    vector["expected"]["variable_total_cost"] = "19.99"
    with pytest.raises(ReferenceContractError, match="variable_total_cost"):
        verify_golden(vector)


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("scope_total", "0"),
        ("scope_total", "NaN"),
        ("scope_total", "Infinity"),
        ("scope_total", 100.0),
        ("team_count", "1.5"),
        ("nominal_final_week_capacity", "-1"),
        ("productivity_per_team_hour", "0"),
        ("variable_rate_per_team_hour", "-1"),
    ],
)
def test_invalid_values_fail_closed(key: str, bad: object) -> None:
    vector = deepcopy(cases()[0])
    vector["inputs"][key] = bad
    with pytest.raises(ReferenceContractError):
        evaluate_vector(vector)


def test_unknown_fields_are_rejected() -> None:
    vector = deepcopy(cases()[0])
    vector["inputs"]["untrusted_production_fallback"] = "1000"
    with pytest.raises(ReferenceContractError, match="unknown"):
        evaluate_vector(vector)


def test_calendar_capacity_shortfall_rejected() -> None:
    vector = deepcopy(cases()[0])
    vector["inputs"]["nominal_final_week_capacity"] = "99"
    with pytest.raises(ReferenceContractError, match="cannot close"):
        evaluate_vector(vector)


def test_reference_code_does_not_import_runtime() -> None:
    for file in HERE.rglob("*.py"):
        node = ast.parse(file.read_text(encoding="utf-8"))
        for part in ast.walk(node):
            if isinstance(part, ast.Import):
                assert not any(alias.name.startswith("concilium") for alias in part.names), file
            if isinstance(part, ast.ImportFrom):
                assert not (part.module or "").startswith("concilium"), file

def test_oracle_rejects_rounded_high_precision_expected_value() -> None:
    # Regression for Codex P2: context precision 28 incorrectly made
    # rate 2.0000000000000000000000000001 indistinguishable from 2.
    vector = deepcopy(cases()[0])
    vector["inputs"]["variable_rate_per_team_hour"] = "2.0000000000000000000000000001"
    with pytest.raises(ReferenceContractError, match="variable_total_cost|variable_final_week_cost"):
        verify_golden(vector)
    result = evaluate_vector(vector)
    assert result["variable_total_cost"] == "20.000000000000000000000000001"


def test_oracle_is_immune_to_global_decimal_context() -> None:
    from decimal import localcontext

    vector = deepcopy(cases()[0])
    vector["inputs"]["variable_rate_per_team_hour"] = "2.0000000000000000000000000001"
    with localcontext() as ctx:
        ctx.prec = 3
        assert evaluate_vector(vector)["variable_total_cost"] == "20.000000000000000000000000001"


def test_nonterminating_fraction_fails_closed() -> None:
    vector = deepcopy(cases()[0])
    vector["inputs"]["productivity_per_team_hour"] = "3"
    with pytest.raises(ReferenceContractError, match="nonterminating decimal"):
        evaluate_vector(vector)


def test_exact_finite_fraction_is_serialized_without_rounding() -> None:
    vector = deepcopy(cases()[0])
    vector["inputs"]["productivity_per_team_hour"] = "8"
    assert evaluate_vector(vector)["variable_total_cost"] == "25"
