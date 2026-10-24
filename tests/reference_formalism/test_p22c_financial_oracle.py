"""P22-C independent finance goldens, falsifiers, and no-production checks."""
from __future__ import annotations

import ast
import json
from copy import deepcopy
from pathlib import Path

import pytest

from tests.reference_formalism.financial_reference import (
    evaluate_financial,
    verify_financial,
)
from tests.reference_formalism.protocol import ReferenceContractError

ROOT = Path(__file__).resolve().parent
VECTORS = ROOT / "vectors" / "financial_cost_v1.json"


def cases() -> list[dict]:
    doc = json.loads(VECTORS.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-financial/1"
    assert "NOT_PROJECT_GO" in doc["formalism"]["scope"]
    assert doc["formalism"]["rounding"].startswith("exact Fraction")
    return doc["vectors"]


@pytest.mark.parametrize("case", cases(), ids=lambda row: row["case_id"])
def test_exact_financial_goldens(case: dict) -> None:
    assert verify_financial(case) == case["expected"]
    assert evaluate_financial(case) == evaluate_financial(deepcopy(case))


def test_fungible_reassignment_falsifies_fixed_levels() -> None:
    # P16 fixed-level construction costs 120; optimum over labeled instances=92.
    actual = evaluate_financial(cases()[1])
    assert int(actual["cost_total"]) == 92
    assert int(actual["cost_total"]) < 120


def test_mutated_cost_or_expected_output_is_caught() -> None:
    bad = deepcopy(cases()[0])
    bad["expected"]["cost_total"] = "2111"
    with pytest.raises(ReferenceContractError, match="golden mismatch"):
        verify_financial(bad)
    bad = deepcopy(cases()[0])
    bad["inputs"]["contract"]["idle"] = "26"
    with pytest.raises(ReferenceContractError, match="golden mismatch"):
        verify_financial(bad)


def test_duplicate_event_source_fails_closed() -> None:
    bad = deepcopy(cases()[0])
    bad["inputs"]["goods"].append(deepcopy(bad["inputs"]["goods"][0]))
    with pytest.raises(ReferenceContractError, match="duplicate"):
        evaluate_financial(bad)


def test_negative_stock_and_missing_purchase_fail_closed() -> None:
    bad = deepcopy(cases()[0])
    bad["inputs"]["stock"][0]["receipts"] = ["0", "0", "0", "0"]
    with pytest.raises(ReferenceContractError, match="negative inventory"):
        evaluate_financial(bad)
    bad = deepcopy(cases()[0])
    bad["inputs"]["goods"] = []
    with pytest.raises(ReferenceContractError, match="acquisition source"):
        evaluate_financial(bad)


@pytest.mark.parametrize("field", ["unit", "rate_source", "price_source"])
def test_missing_physical_provenance_is_not_zero(field: str) -> None:
    bad = deepcopy(cases()[0])
    bad["inputs"]["goods"][0][field] = ""
    with pytest.raises(ReferenceContractError, match="provenance"):
        evaluate_financial(bad)


def test_binary_float_and_unknown_economic_fields_fail_closed() -> None:
    bad = deepcopy(cases()[0])
    bad["inputs"]["contract"]["active"] = 100.0
    with pytest.raises(ReferenceContractError, match="decimal string"):
        evaluate_financial(bad)
    bad = deepcopy(cases()[0])
    bad["inputs"]["contract"]["rho_idle_eq"] = "0"
    with pytest.raises(ReferenceContractError, match="unknown fields"):
        evaluate_financial(bad)


def test_full_rate_is_not_universally_reduced_to_keep() -> None:
    assert evaluate_financial(cases()[2])["cost_total"] == "360"
    assert evaluate_financial(cases()[0])["contractual_k"] == "250"


def test_independent_oracle_forbids_production_imports() -> None:
    path = ROOT / "financial_reference.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    assert not any(
        mod == "concilium" or mod.startswith("concilium.")
        for mod in imports
    )
