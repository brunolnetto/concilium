"""Fail-closed PR path gate for economic changes requiring reviewed witnesses.

Stdlib-only; designed to run without production dependencies or Azure credentials.
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
import tokenize
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
    "src/concilium/application/scheduling/realized_financial_metrics.py",
    "src/concilium/application/scheduling/financial_cost_reconciliation.py",
    "src/concilium/application/scheduling/skill06_realized_consumer.py",
    "src/concilium/domain/models/canonical/_pool_recursos.py",
    "src/concilium/domain/models/canonical/_estoque_consumiveis.py",
)
ECONOMIC_SEGMENTS = (
    "/results_financeiros/",
    "/pool_recursos/",
    "/estoque_consumiveis/",
    "/economics/",
    "/finance/",
    "/06-resultado-financeiro/",
    "/05-equipes-e-alocacao/",
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


def code_tokens(source: bytes) -> tuple[tuple[int, str], ...]:
    """Python token stream without comments and comment-only line breaks.

    Docstrings, indentation and the source encoding stay significant.
    Raises tokenize.TokenError / SyntaxError on unparseable input.
    """
    ignored = {tokenize.COMMENT, tokenize.NL}
    return tuple(
        (tok.type, tok.string)
        for tok in tokenize.tokenize(io.BytesIO(source).readline)
        if tok.type not in ignored
    )


def is_comment_only_change(before: bytes, after: bytes) -> bool:
    """True only when two Python sources differ in comments alone; else fail closed."""
    try:
        return code_tokens(before) == code_tokens(after)
    except (tokenize.TokenError, SyntaxError, UnicodeDecodeError):
        return False


def assess_paths(changed: set[str], comment_only: set[str] = frozenset()) -> tuple[bool, str]:
    """`comment_only`: economic paths proven to change only comments (see
    comment_only_changes); they need no spec/vector evidence."""
    if not changed:
        return False, "Cannot certify an empty/unknown diff."
    exempt = sorted(p for p in changed if is_economic(p) and p in comment_only)
    impacted = sorted(p for p in changed if is_economic(p) and p not in comment_only)
    if not impacted:
        if exempt:
            return True, f"Economic files changed only in comments (code tokens identical): {exempt}."
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


def git_changed(base: str, head: str, *, mode: str = "pr") -> set[str]:
    """PR: merge-base diff; push: endpoints diff (including divergent history).

    Using a merge-base for a force-push could hide reverted economic changes.
    An orphaned prior push tip that was not fetched raises and fails closed.
    """
    if not base or not head or base == "0" * 40 or head == "0" * 40:
        raise ValueError("A real base and head commit SHA are required")
    if mode not in ("pr", "push"):
        raise ValueError("Explicit PR or push comparison mode required")
    commits = [f"{base}...{head}"] if mode == "pr" else [base, head]
    output = subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-only", "--diff-filter=ACMRTD", *commits],
        text=True,
        stderr=subprocess.PIPE,
    )
    return {p.strip() for p in output.splitlines() if p.strip()}


def _blob(rev: str, path: str) -> bytes | None:
    result = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True)
    return result.stdout if result.returncode == 0 else None


def comment_only_changes(base: str, head: str, paths: set[str], *, mode: str = "pr") -> set[str]:
    """Economic .py paths whose code token stream is identical on both sides.

    Uses the same comparison points as git_changed (merge-base for PRs, the
    endpoints for pushes). Added, deleted, non-Python or unparseable files are
    never exempt.
    """
    if mode == "pr":
        before = subprocess.check_output(["git", "merge-base", base, head], text=True).strip()
    else:
        before = base
    exempt: set[str] = set()
    for path in paths:
        if not (is_economic(path) and path.endswith(".py")):
            continue
        old, new = _blob(before, path), _blob(head, path)
        if old is not None and new is not None and is_comment_only_change(old, new):
            exempt.add(path)
    return exempt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--mode", choices=("pr", "push"), required=True)
    args = parser.parse_args(argv)
    try:
        paths = git_changed(args.base, args.head, mode=args.mode)
        exempt = comment_only_changes(args.base, args.head, paths, mode=args.mode)
        valid, reason = assess_paths(paths, exempt)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(f"::error::Contract diff unavailable; refusing to pass: {exc}")
        return 1
    print(reason)
    if not valid:
        print("::error::Missing reviewed spec/golden evidence for economic change.")
    return 0 if valid else 1


if __name__ == "__main__":
    sys.exit(main())
