"""Fail-closed PR guard for economic implementation changes without reference evidence.

Stdlib-only, hermetic and independent of Azure/production imports. CI invokes
with a PR base SHA, computing changes from the merge base to HEAD.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ECONOMIC_PREFIXES = (
    "src/concilium/application/scheduling/",
    "src/concilium/domain/models/canonical/_pool_recursos",
    "src/concilium/domain/models/canonical/_estoque_consumiveis",
    "src/concilium/application/finance",
)
ECONOMIC_FILE_HINTS = (
    "cost", "finance", "tariff", "consum", "stock", "inventory",
    "revenue", "pricing", "ledger", "bdi", "contract",
)
NORMATIVE_PREFIX = "docs/product/5-specifications/formulario_longo/"
GOLDEN_PREFIX = "tests/reference_formalism/vectors/"
REFERENCE_PREFIX = "tests/reference_formalism/test_"


def is_economic_source(path: str) -> bool:
    if path.startswith("src/concilium/application/scheduling/"):
        return any(term in Path(path).name.lower() for term in ECONOMIC_FILE_HINTS)
    return any(path.startswith(prefix) for prefix in ECONOMIC_PREFIXES[1:])


def validate_paths(paths: set[str]) -> list[str]:
    touched = sorted(path for path in paths if is_economic_source(path))
    if not touched:
        return []
    missing: list[str] = []
    if not any(p.startswith(NORMATIVE_PREFIX) for p in paths):
        missing.append(f"normative formalism update under {NORMATIVE_PREFIX}")
    if not any(p.startswith(GOLDEN_PREFIX) and p.endswith(".json") for p in paths):
        missing.append(f"independent reviewed JSON golden under {GOLDEN_PREFIX}")
    if not any(p.startswith(REFERENCE_PREFIX) and p.endswith(".py") for p in paths):
        missing.append(f"independent oracle regression under {REFERENCE_PREFIX}")
    return missing


def changed_files(base: str) -> set[str]:
    # No shell interpolation; fail rather than silently skip missing/unfetchable SHA.
    subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], check=True)
    merge = subprocess.check_output(["git", "merge-base", base, "HEAD"], text=True).strip()
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", "-z", merge, "HEAD"],
    )
    return {p.decode("utf-8") for p in diff.split(b"\0") if p}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="PR base commit SHA")
    args = parser.parse_args()
    try:
        paths = changed_files(args.base)
    except (subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        print(f"FAIL CLOSED: cannot determine economic delta: {exc}", file=sys.stderr)
        return 2
    omissions = validate_paths(paths)
    if omissions:
        print("Economic source change requires independent normative and oracle evidence.",
              file=sys.stderr)
        for omission in omissions:
            print(f" - Missing: {omission}", file=sys.stderr)
        print("NO PROJECT_GO; update normative text, JSON golden and reference regression.",
              file=sys.stderr)
        return 1
    print(f"Economic evidence delta gate PASS ({len(paths)} changed paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
