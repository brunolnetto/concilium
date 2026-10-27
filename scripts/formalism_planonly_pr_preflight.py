#!/usr/bin/env python3
"""Fail-closed preflight for formalism PLAN_ONLY PRs and their release-wave gates.

Never interprets a plan-only PR as implemented, review-approved, or certified.
Supports offline snapshots and GitHub's REST API without side effects.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.formalism_wave_dag import MANIFEST, REPO, validate_dag

REGISTRY = MANIFEST.with_name("formalism_planonly_pr_registry.json")


def load_registry() -> tuple[dict[str, Any], dict[str, Any]]:
    dag = json.loads(MANIFEST.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    validate_dag(dag)
    if registry.get("schema") != "concilium.formalism.planonly_pr_registry.v1":
        raise ValueError("unknown planning registry schema")
    return dag, registry


def validate_registry(dag: dict[str, Any], registry: dict[str, Any]) -> None:
    """Require exact canonical package gaps and an acyclic PR planning order."""
    unregistered = {
        (node["issue"], node["wave"], package["id"])
        for node in dag["nodes"]
        for package in node["packages"]
        if not package["prs"]
    }
    rows = registry["packages"]
    registered = {(row["issue"], row["wave"], row["id"]) for row in rows}
    if registered != unregistered or len(rows) != len(registered):
        raise ValueError("planning registry and unimplemented DAG slots differ")
    recorded_prs = {
        pr for node in dag["nodes"] for package in node["packages"]
        for pr in package["prs"]
    }
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        raise ValueError("duplicate planning package ID")
    ids = [row["planning_pr"] for row in rows]
    if len(ids) != len(set(ids)) or recorded_prs.intersection(ids):
        raise ValueError("plan-only PR reused or registered as implementation")
    for index, row in enumerate(rows):
        if row["status"] != "PLAN_ONLY" or row["topological_index"] != index:
            raise ValueError(f"{row['id']}: planned state/order changed")
        if 25 not in row["blocks_on_issues"] or row["wave"] <= 1:
            raise ValueError(f"{row['id']}: wave-1 blocker missing")
        parent_branches = set()
        for parent_id in row["depends_on_plans"]:
            parent = by_id.get(parent_id)
            if parent is None or parent["topological_index"] >= index:
                raise ValueError(f"{row['id']}: invalid PR dependency {parent_id}")
            if parent["wave"] > row["wave"]:
                raise ValueError(f"{row['id']}: backwards PR-wave dependency")
            parent_branches.add(parent["head_branch"])
        if row["base_branch"] != "main" and row["base_branch"] not in parent_branches:
            raise ValueError(f"{row['id']}: base branch is not a declared predecessor")
        if row["head_branch"] == row["base_branch"]:
            raise ValueError(f"{row['id']}: no distinct PR branch")


def audit_snapshot(
    dag: dict[str, Any], registry: dict[str, Any], snapshot: dict[str, Any]
) -> dict[str, Any]:
    """Check actual pull metadata and independent issue release gates, not code."""
    validate_registry(dag, registry)
    issues = {
        obj["number"]: obj["state"] for obj in snapshot["issues"]
        if not obj.get("pull_request") and 9 <= obj["number"] <= 26
    }
    nodes = {node["issue"]: node for node in dag["nodes"]}
    if set(issues) != set(nodes):
        raise ValueError("incomplete GitHub issue snapshot")
    if any(value not in {"open", "closed"} for value in issues.values()):
        raise ValueError("invalid issue state in snapshot")
    pulls = {p["number"]: p for p in snapshot["pulls"]}
    results = []
    for row in registry["packages"]:
        pr = pulls.get(row["planning_pr"])
        if pr is None:
            raise ValueError(f"{row['id']}: missing GitHub PR")
        if pr["head"]["ref"] != row["head_branch"]:
            raise ValueError(f"{row['id']}: head branch drift")
        if pr["base"]["ref"] != row["base_branch"]:
            raise ValueError(f"{row['id']}: base branch drift")
        if pr["state"] != "open" or not pr.get("draft") or pr.get("merged_at"):
            raise ValueError(f"{row['id']}: PLAN_ONLY must remain an open draft")
        node = nodes[row["issue"]]
        blocked_issues = sorted({
            *row["blocks_on_issues"],
            *node["blocked_by"],
            *(
                earlier["issue"] for earlier in dag["nodes"]
                if earlier["wave"] < row["wave"]
            ),
        } - {row["issue"]})
        pending = [i for i in blocked_issues if issues[i] != "closed"]
        results.append({
            "id": row["id"], "pr": row["planning_pr"], "wave": row["wave"],
            "state": "PLAN_ONLY", "pending_issue_gates": pending,
            "ready_to_implement": not pending,
            "ready_to_merge": False,  # Plans never count as product.
        })
    return {
        "valid": True,
        "wave_1_blocked": issues[25] != "closed",
        "planning_prs_audited": len(results),
        "plans": results,
        "note": "PLAN_ONLY is never evidence of implementation, merge or project GO",
    }


def github_collection(collection: str, token: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for page in range(1, 31):
        req = Request(
            f"https://api.github.com/repos/{REPO}/{collection}"
            f"?state=all&per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "concilium-formalism-planonly-preflight",
                "Authorization": f"Bearer {token}",
            },
        )
        with urlopen(req, timeout=20) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("unexpected GitHub response")
        records.extend(batch)
        if len(batch) < 100:
            return records
    raise ValueError("GitHub pagination limit exceeded")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--live", action="store_true")
    choice.add_argument("--snapshot", type=Path)
    parser.add_argument(
        "--require-merge-ready", action="store_true",
        help="fail if any package is still PLAN_ONLY (always fail until promotion)",
    )
    args = parser.parse_args()
    try:
        dag, registry = load_registry()
        validate_registry(dag, registry)
        if not args.live and args.snapshot is None:
            print(json.dumps({
                "valid": True, "planning_prs": len(registry["packages"]),
                "all_status": "PLAN_ONLY", "merge_ready": False,
            }, indent=2))
            return 1 if args.require_merge_ready else 0
        if args.live:
            token = os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")
            if not token:
                raise ValueError("GH_TOKEN/GITHUB_TOKEN required for private repo")
            snapshot = {
                "issues": github_collection("issues", token),
                "pulls": github_collection("pulls", token),
            }
        else:
            snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        report = audit_snapshot(dag, registry, snapshot)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 1 if args.require_merge_ready else 0
    except (ValueError, KeyError, TypeError, HTTPError, URLError, OSError) as exc:
        print(f"FAIL CLOSED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
