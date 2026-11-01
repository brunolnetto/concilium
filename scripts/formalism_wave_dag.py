#!/usr/bin/env python3
"""Validate wave DAG and report live GitHub issue/PR closure prerequisites.

This is a governance *preflight*, not an automatic issue closer and not
a numerical/financial GO certificate. No production-code imports.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/engineering/formalism_execution_dag.json"
REPO = "brunolnetto/concilium"
EXPECTED = {0: 5, 1: 2, 2: 8, 3: 3}


def validate_dag(spec: dict[str, Any]) -> list[int]:
    """Fail on missing work, duplicate IDs, backwards edges, or cycles."""
    if spec.get("schema") != "concilium.formalism.execution_dag.v1":
        raise ValueError("unknown DAG schema")
    nodes = spec["nodes"]
    ids = [n["issue"] for n in nodes]
    if len(ids) != len(set(ids)) or set(ids) != set(range(9, 27)):
        raise ValueError("DAG must contain each issue #9–#26 exactly once")
    by_id = {n["issue"]: n for n in nodes}
    if {w: sum(n["wave"] == w for n in nodes) for w in EXPECTED} != EXPECTED:
        raise ValueError("wave membership changed without governance review")
    for n in nodes:
        if n["wave"] not in EXPECTED:
            raise ValueError(f"invalid wave on #{n['issue']}")
        prereqs = n["blocked_by"]
        if len(prereqs) != len(set(prereqs)):
            raise ValueError(f"duplicate prerequisite on #{n['issue']}")
        for parent in prereqs:
            if parent not in by_id:
                raise ValueError(f"unknown prerequisite #{parent}")
            if by_id[parent]["wave"] > n["wave"]:
                raise ValueError(f"backwards wave edge #{parent} → #{n['issue']}")
        packages = n["packages"]
        if not packages or len({p["id"] for p in packages}) != len(packages):
            raise ValueError(f"missing/duplicate packages on #{n['issue']}")
        for p in packages:
            if any(not isinstance(pr, int) or pr <= 0 for pr in p["prs"]):
                raise ValueError(f"bad PR on #{n['issue']}/{p['id']}")
    visiting: set[int] = set()
    visited: set[int] = set()
    order: list[int] = []

    def visit(issue: int) -> None:
        if issue in visiting:
            raise ValueError(f"cycle found at #{issue}")
        if issue in visited:
            return
        visiting.add(issue)
        for parent in by_id[issue]["blocked_by"]:
            visit(parent)
        visiting.remove(issue)
        visited.add(issue)
        order.append(issue)

    for issue in ids:
        visit(issue)
    return order


def report(
    spec: dict[str, Any],
    issue_state: dict[int, str],
    merged_prs: set[int],
) -> dict[str, Any]:
    """Report implementation packages and advisory sequencing context.

    Predecessor and prior-wave state are deliberately non-blocking. Issue
    closure still requires merged mandatory packages plus independent human
    acceptance evidence; this preflight never supplies that evidence.
    """
    validate_dag(spec)
    ids = {n["issue"] for n in spec["nodes"]}
    if set(issue_state) != ids:
        raise ValueError(f"issue snapshot incomplete; missing={sorted(ids-set(issue_state))}")
    if any(s not in ("open", "closed") for s in issue_state.values()):
        raise ValueError("invalid issue state")
    waves = {
        w: sorted(n["issue"] for n in spec["nodes"] if n["wave"] == w)
        for w in EXPECTED
    }
    waves_closed = {
        w: all(issue_state[i] == "closed" for i in issues)
        for w, issues in waves.items()
    }
    active_wave = next((w for w, passed in waves_closed.items() if not passed), None)
    entries = []
    for n in spec["nodes"]:
        issue, wave = n["issue"], n["wave"]
        parents_open = [i for i in n["blocked_by"] if issue_state[i] != "closed"]
        prior_waves_open = [w for w in range(wave) if not waves_closed[w]]
        missing_packages = [
            p["id"] for p in n["packages"]
            if not p["prs"] or not all(pr in merged_prs for pr in p["prs"])
        ]
        # A historic completed issue is NOT retroactively re-opened by this report.
        # A future closure must respect the graph and independent human acceptance.
        entries.append({
            "issue": issue,
            "wave": wave,
            "state": issue_state[issue],
            "pr_packages_merged": len(n["packages"]) - len(missing_packages),
            "pr_packages_total": len(n["packages"]),
            "pending_packages": missing_packages,
            "open_predecessor_context": parents_open,
            "open_prior_waves_context": prior_waves_open,
            "sequencing_advisory": bool(parents_open or prior_waves_open),
            "ready_to_execute": issue_state[issue] == "open",
            "closure_preflight": issue_state[issue] == "open" and not missing_packages,
            "acceptance_verified": None,  # MUST be independently reviewed
            "closed_with_open_sequence_context": (
                issue_state[issue] == "closed" and bool(parents_open or prior_waves_open)
            ),
        })
    return {
        "active_wave": active_wave,
        "waves_closed": waves_closed,
        "ready_to_execute": [x["issue"] for x in entries if x["ready_to_execute"]],
        "note": "predecessor and wave state are advisory only; merged packages plus independently reviewed local acceptance are required; PR merge alone never satisfies acceptance or project GO",
        "issues": sorted(entries, key=lambda x: (x["wave"], x["issue"])),
    }


def github_list(path: str, token: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for page in range(1, 51):
        url = f"https://api.github.com/repos/{REPO}/{path}"
        separator = "&" if "?" in url else "?"
        req = Request(
            f"{url}{separator}per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "concilium-wave-dag-preflight",
                "Authorization": f"Bearer {token}",
            },
        )
        with urlopen(req, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("GitHub returned a non-list response")
        values.extend(batch)
        if len(batch) < 100:
            return values
    raise ValueError("GitHub pagination limit exceeded (fail closed)")


def snapshot_from_github() -> dict[str, Any]:
    token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        raise ValueError("private repository requires GH_TOKEN/GITHUB_TOKEN; no silent offline PASS")
    return {
        "issues": github_list("issues?state=all", token),
        "pulls": github_list("pulls?state=all", token),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--live", action="store_true", help="read private GitHub with GH_TOKEN")
    group.add_argument("--snapshot", type=Path, help="offline issues/pulls GitHub JSON snapshot")
    parser.add_argument("--require-close", type=int, help="check prerequisites for a specific issue")
    args = parser.parse_args()
    try:
        spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
        order = validate_dag(spec)
        if not args.live and not args.snapshot:
            if args.require_close is not None:
                raise ValueError("--require-close requires --live or --snapshot")
            print(json.dumps({"dag_valid": True, "topological_order": order}, indent=2))
            return 0
        snapshot = snapshot_from_github() if args.live else json.loads(
            args.snapshot.read_text(encoding="utf-8")
        )
        # GitHub Issues API includes pull requests; they must not be confused
        # with canonical issue nodes.
        states = {
            i["number"]: i["state"] for i in snapshot["issues"]
            if "pull_request" not in i and 9 <= i["number"] <= 26
        }
        merged = {pr["number"] for pr in snapshot["pulls"] if pr.get("merged_at")}
        result = report(spec, states, merged)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.require_close is not None:
            item = next((x for x in result["issues"] if x["issue"] == args.require_close), None)
            if item is None or not item["closure_preflight"]:
                return 1
        return 0
    except (ValueError, KeyError, HTTPError, URLError, TimeoutError, OSError) as exc:
        print(f"FAIL CLOSED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
