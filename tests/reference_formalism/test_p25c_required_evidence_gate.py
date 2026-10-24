"""Pure stdlib negative fixtures for mandatory economic PR gate."""
from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/formalism_contract_change_gate.py"
spec = importlib.util.spec_from_file_location("formalism_contract_change_gate", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

PRODUCTION = "src/concilium/application/scheduling/economic_regime_contracts.py"
LONG = "docs/product/5-specifications/formulario_longo/FORMALISMO_LONGO.md"
GOLDEN = "tests/reference_formalism/vectors/economic_reconciliation_v1.json"
INVENTORY = "docs/product/5-specifications/formulario_longo/EQUATION_INVENTORY_P09C.json"


def test_negative_economic_mutation_cannot_pass_without_evidence() -> None:
    assert module.assess_paths({PRODUCTION})[0] is False
    assert module.assess_paths({PRODUCTION, LONG})[0] is False
    assert module.assess_paths({PRODUCTION, GOLDEN})[0] is False
    assert module.assess_paths({PRODUCTION, INVENTORY, GOLDEN})[0] is False


def test_economic_change_requires_both_normative_and_golden() -> None:
    valid, reason = module.assess_paths({PRODUCTION, LONG, GOLDEN})
    assert valid, reason


def test_non_economic_refactor_does_not_require_false_evidence() -> None:
    assert module.assess_paths({"src/concilium/api/router.py"})[0]


def test_empty_or_unresolved_diff_fails_closed() -> None:
    assert module.assess_paths(set())[0] is False


def test_known_physical_contracts_trigger_protection() -> None:
    for file in module.ECONOMIC_PATHS:
        assert module.is_economic(file), file
