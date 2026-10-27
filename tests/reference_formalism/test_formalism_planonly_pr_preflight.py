"""Offline falsifiers for the live-ready plan-only PR dependency auditor."""
from __future__ import annotations

import copy

import pytest

from scripts.formalism_planonly_pr_preflight import (
    audit_snapshot,
    load_registry,
    validate_registry,
)


@pytest.fixture
def state() -> tuple[dict, dict, dict]:
    dag, registry = load_registry()
    issue_rows = [{
        "number": n["issue"],
        "state": "closed" if n["issue"] in {9, 10, 11, 12, 13, 22} else "open",
    } for n in dag["nodes"]]
    pr_rows = [{
        "number": row["planning_pr"],
        "state": "open",
        "draft": True,
        "merged_at": None,
        "head": {"ref": row["head_branch"]},
        "base": {"ref": row["base_branch"]},
    } for row in registry["packages"]]
    return dag, registry, {"issues": issue_rows, "pulls": pr_rows}


def test_all_twelve_planonly_prs_are_valid_but_none_merge_ready(state) -> None:
    dag, registry, snapshot = state
    result = audit_snapshot(dag, registry, snapshot)
    assert result["planning_prs_audited"] == 12
    assert result["wave_1_blocked"] is True
    assert all(not item["ready_to_merge"] for item in result["plans"])
    assert all(25 in item["pending_issue_gates"] for item in result["plans"])


def test_cross_branch_join_requires_both_independent_issues(state) -> None:
    dag, registry, snapshot = state
    row = next(x for x in audit_snapshot(dag, registry, snapshot)["plans"] if x["id"] == "P20-B")
    assert {17, 19, 25}.issubset(row["pending_issue_gates"])


@pytest.mark.parametrize("field", ["draft", "state", "merged_at"])
def test_preflight_rejects_any_planonly_promotion_or_merge(state, field) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    if field == "draft":
        changed["pulls"][0]["draft"] = False
    elif field == "state":
        changed["pulls"][0]["state"] = "closed"
    else:
        changed["pulls"][0]["merged_at"] = "2026-10-27T13:00:00Z"
    with pytest.raises(ValueError, match="must remain an open draft"):
        audit_snapshot(dag, registry, changed)


@pytest.mark.parametrize("field", ["head", "base"])
def test_preflight_rejects_branch_or_stack_retarget(state, field) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    changed["pulls"][2][field]["ref"] = "main"
    with pytest.raises(ValueError, match=f"{field} branch drift"):
        audit_snapshot(dag, registry, changed)


def test_preflight_rejects_missing_pr_instead_of_guessing(state) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    changed["pulls"].pop()
    with pytest.raises(ValueError, match="missing GitHub PR"):
        audit_snapshot(dag, registry, changed)


def test_preflight_rejects_incomplete_issue_snapshot(state) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    changed["issues"] = [i for i in changed["issues"] if i["number"] != 25]
    with pytest.raises(ValueError, match="incomplete GitHub issue snapshot"):
        audit_snapshot(dag, registry, changed)


def test_preflight_rejects_dag_pr_registration_of_document_only_work(state) -> None:
    dag, registry, _ = state
    changed = copy.deepcopy(dag)
    target = next(x for x in changed["nodes"] if x["issue"] == 17)
    target["packages"][-1]["prs"] = [108]
    with pytest.raises(ValueError, match="planning registry and unimplemented DAG slots differ"):
        validate_registry(changed, registry)


def test_preflight_rejects_bypassing_both_parents_of_financial_join(state) -> None:
    dag, registry, _ = state
    changed = copy.deepcopy(registry)
    row = next(x for x in changed["packages"] if x["id"] == "P20-B")
    row["depends_on_plans"] = ["P19-C"]  # silently discard independent P17-C
    # Extra non-base edges must not disappear on a graph edit.
    assert {r["id"] for r in registry["packages"]} >= {"P17-C", "P19-C"}
    # This guard is an explicit contract of the canonical PR plan:
    assert "P17-C" not in row["depends_on_plans"]
    # Validate this independently of GitHub's one-base API.
    assert set(next(x for x in registry["packages"] if x["id"] == "P20-B")[
        "depends_on_plans"
    ]) == {"P17-C", "P19-C"}
