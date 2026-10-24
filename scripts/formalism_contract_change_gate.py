"""Fail-closed PR path gate for economic changes requiring reviewed witnesses.

Stdlib-only; designed to run without production dependencies or Azure credentials.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import PurePosixPath

SPEC = "docs/product/5-specifications/formulario_longo/"
VECTORS = "tests/reference_formalism/vectors/"
EVIDENCE = (
    SPEC,
    VECTORS,
    "tests/reference_formalism/test_p13c_regime_parity_oracle.py",
    "tests/reference_formalism/test_equation_inventory_p09c.py",
)

# Deliberately narrow: changes to numeric contract implementations, not all code.
ECONOMIC_PATHS = (
    "src/concilium/application/scheduling/contractual_cost_ledger.py",
    "src/concilium/application/scheduling/economic_regime_contracts.py",
    "src/concilium/application/scheduling/physical_consumption_rates.py",
    "src/concilium/application/scheduling/resource_level_contracts.py",
    "src/concilium/application/scheduling/resource_demand_levels.py",
    "src/concilium/domain/models/canonical/_pool_recursos.py",
    "src/concilium/domain/models/canonical/_estoque_consumiveis.py",
)
ECONOMIC_SEGMENTS = (
    "/results_financeiros/",
    "/pool_recursos/",
    "/estoque_consumiveis/",
    "/economics/",
    "/finance/",
)
EXCLUDED_DOCS = (SPEC + "EQUATION_INVENTORY_P09C.json",)


def is_economic(path: str) -> bool:
    normalized = str(PurePosixPath(path))
    return normalized in ECONOMIC_PATHS or (
        normalized.startswith("src/concilium/")
        and any(part in normalized for part in ECONOMIC_SEGMENTS)
    )


def is_evidence(path: str) -> bool:
    normalized = str(PurePosixPath(path))
    return any(normalized.startswith(prefix) for prefix in (SPEC, VECTORS)) or normalized in EVIDENCE


def assess_paths(changed: set[str]) -> tuple[bool, str]:
    if not changed:
        return False, "Cannot certify an empty/unknown diff."
    impacted = sorted(p for p in changed if is_economic(p))
    if not impacted:
        return True, "No production economic contract files changed."
    # Inventory-only updates cannot substitute for a reviewed normative source.
    specifications = sorted(p for p in changed
                            if p.startswith(SPEC) and p not in EXCLUDED_DOCS)
    vectors = sorted(p for p in changed if p.startswith(VECTORS)
                     and p.endswith(".json")
                     and any(token in p for token in ("economic", "reconciliation", "consumption", "pool")))
    if not specifications or not vectors:
        return False, (
            "Economic changes require BOTH a reviewed normative specification "
            "AND a versioned golden JSON vector in the same PR; "
            f"economic={impacted}; specifications={specifications}; vectors={vectors}"
        )
    return True, f"Economic files {impacted} have spec {specifications} and vector {vectors}."


def git_changed(base: str, head: str) -> set[str]:
    if not base or not head or base == "0" * 40 or head == "0" * 40:
        raise ValueError("A real base and head commit SHA are required")
    output = subprocess.check_output(
        ["git", "diff", "--name-only", "--diff-filter=ACMRTD", f"{base}...{head}"],
        text=True,
        stderr=subprocess.PIPE,
    )
    return {p.strip() for p in output.splitlines() if p.strip()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    try:
        paths = git_changed(args.base, args.head)
        valid, reason = assess_paths(paths)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"::error::Contract diff unavailable; refusing to pass: {exc}")
        return 1
    print(reason)
    if not valid:
        print("::error::Missing reviewed spec/golden evidence for economic change.")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
