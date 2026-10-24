"""Fail-closed economic specification delta gate, with synthetic PR file sets."""
from __future__ import annotations

from scripts.check_economic_spec_delta import is_economic_source, validate_paths


def test_unrelated_changes_do_not_require_repricing() -> None:
    assert validate_paths({"README.md", "tests/unit/test_cli.py"}) == []


def test_economic_changes_without_any_reference_are_rejected() -> None:
    paths = {"src/concilium/application/scheduling/economic_regime_contracts.py"}
    errors = validate_paths(paths)
    assert len(errors) == 3
    assert any("normative" in e for e in errors)
    assert any("JSON golden" in e for e in errors)


def test_economic_change_with_only_docs_still_rejected() -> None:
    paths = {
        "src/concilium/application/scheduling/contractual_cost_ledger.py",
        "docs/product/5-specifications/formulario_longo/FORMALISMO_LONGO.md",
    }
    assert len(validate_paths(paths)) == 2


def test_proper_normative_golden_and_independent_regression_pass() -> None:
    paths = {
        "src/concilium/application/scheduling/physical_consumption_rates.py",
        "docs/product/5-specifications/formulario_longo/FORMALISMO_LONGO.md",
        "tests/reference_formalism/vectors/economic_reconciliation_v1.json",
        "tests/reference_formalism/test_p22c_economic_oracle.py",
    }
    assert validate_paths(paths) == []


def test_runtime_change_without_production_economics_does_not_trigger() -> None:
    assert not is_economic_source(
        "src/concilium/application/scheduling/resource_demand_levels.py"
    )
    assert is_economic_source(
        "src/concilium/domain/models/canonical/_pool_recursos.py"
    )
    assert is_economic_source(
        "src/concilium/application/scheduling/economic_regime_contracts.py"
    )


def test_spoofing_tests_outside_reference_tree_does_not_satisfy_gate() -> None:
    paths = {
        "src/concilium/application/scheduling/economic_regime_contracts.py",
        "docs/product/5-specifications/formulario_longo/FORMALISMO_LONGO.md",
        "tests/reference_formalism/vectors/economic_reconciliation_v1.json",
        "tests/unit/test_false_reference.py",
    }
    assert any("oracle regression" in error for error in validate_paths(paths))
