"""Fail-closed PR guard for economic implementation changes without reference evidence.

Stdlib-only, hermetic and independent of Azure/production imports. CI invokes
with a PR base SHA, computing changes from the merge base to HEAD.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Mapping

# Conservative protected boundary: physical scheduling changes can affect K, V,
# booked asset counts and monetary outputs even without a "cost" filename.
ECONOMIC_PREFIXES = (
    "src/concilium/application/scheduling/",
    "src/concilium/application/finance",
    "src/concilium/application/financial",
    "src/concilium/domain/services/financial/",
    "src/concilium/domain/models/canonical/_pool_recursos",
    "src/concilium/domain/models/canonical/_estoque_consumiveis",
)
NORMATIVE_PREFIX = "docs/product/5-specifications/formulario_longo/"
GOLDEN_PREFIX = "tests/reference_formalism/vectors/"
REFERENCE_PREFIX = "tests/reference_formalism/test_"


def is_economic_source(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in ECONOMIC_PREFIXES)


def validate_paths(changes: Mapping[str, str] | set[str]) -> list[str]:
    """Treat a deletion as a changed source but NEVER as new evidence."""
    statuses = {name: "M" for name in changes} if isinstance(changes, set) else dict(changes)
    touched = sorted(path for path in statuses if is_economic_source(path))
    if not touched:
        return []
    evidence = {p for p, status in statuses.items() if status in {"A", "M", "T"}}
    missing: list[str] = []
    if not any(p.startswith(NORMATIVE_PREFIX) for p in evidence):
        missing.append(f"normative formalism update under {NORMATIVE_PREFIX}")
    if not any(p.startswith(GOLDEN_PREFIX) and p.endswith(".json") for p in evidence):
        missing.append(f"independent reviewed JSON golden under {GOLDEN_PREFIX}")
    if not any(p.startswith(REFERENCE_PREFIX) and p.endswith(".py") for p in evidence):
        missing.append(f"independent oracle regression under {REFERENCE_PREFIX}")
    return missing


def changed_files(base: str) -> dict[str, str]:
    """Read Git status+path pairs with rename detection explicitly disabled.

    Renames must expose both deleted source and added destination, and a
    deleted golden/test may not count as a replacement proof.
    """
    subprocess.run(["git", "cat-file", "-e", f"{base}^{{commit}}"], check=True)
    merge = subprocess.check_output(["git", "merge-base", base, "HEAD"], text=True).strip()
    data = subprocess.check_output(
        ["git", "diff", "--no-renames", "--name-status", "-z", merge, "HEAD"],
    )
    parts = data.split(b"\0")
    if parts[-1] != b"":
        raise ReferenceDiffError("unterminated status diff")
    fields = parts[:-1]
    if len(fields) % 2:
        raise ReferenceDiffError("invalid status/path pair count")
    result: dict[str, str] = {}
    for i in range(0, len(fields), 2):
        status, path = fields[i].decode("utf-8"), fields[i + 1].decode("utf-8")
        if status not in {"A", "M", "D", "T"} or not path or path in result:
            raise ReferenceDiffError(f"unsupported/duplicate git diff entry: {status}")
        result[path] = status
    return result


class ReferenceDiffError(ValueError):
    """Source comparison is ambiguous and must fail closed."""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, help="PR base commit SHA")
    args = parser.parse_args()
    try:
        paths = changed_files(args.base)
    except (subprocess.CalledProcessError, UnicodeDecodeError, ReferenceDiffError) as exc:
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
