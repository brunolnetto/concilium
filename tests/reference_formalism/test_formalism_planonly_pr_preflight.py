"""Offline falsifiers for the live-ready plan-only PR dependency auditor."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

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
        "body": "",
        "head": {"ref": row["head_branch"]},
        "base": {"ref": row["base_branch"]},
    } for row in registry["packages"]]
    # Canonical package PRs are completed implementations, not planning drafts.
    implemented_prs = {
        pr for node in dag["nodes"] for package in node["packages"]
        for pr in package["prs"]
    }
    pr_rows.extend({
        "number": number, "state": "closed", "draft": False,
        "merged_at": "2026-01-01T00:00:00Z",
    } for number in sorted(implemented_prs))
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


def test_same_issue_predecessor_plan_blocks_implementation_readiness(state) -> None:
    dag, registry, snapshot = state
    completed = {"P17-C": 201, "P19-C": 202, "P20-B": 203, "P20-C": 204}
    for node in dag["nodes"]:
        for package in node["packages"]:
            if package["id"] in completed:
                package["prs"] = [completed[package["id"]]]
    registry["packages"] = [
        row for row in registry["packages"] if row["id"] not in completed
    ]
    for index, row in enumerate(registry["packages"]):
        row["topological_index"] = index
    p21a = next(row for row in registry["packages"] if row["id"] == "P21-A")
    p21a["base_branch"] = "main"

    # Simulate completed predecessors and closed issue gates, while P21-A/B
    # remain unimplemented packages in the same open issue #21.
    for issue in snapshot["issues"]:
        issue["state"] = "open" if issue["number"] in {21, 23, 24, 26} else "closed"
    snapshot["pulls"] = [
        pull for pull in snapshot["pulls"]
        if pull["number"] not in {108, 109, 110, 111}
    ]
    snapshot["pulls"].extend({
        "number": number, "state": "closed", "draft": False,
        "merged_at": "2026-10-27T00:00:00Z",
    } for number in completed.values())
    next(pull for pull in snapshot["pulls"] if pull["number"] == 112)["base"]["ref"] = "main"

    report = audit_snapshot(dag, registry, snapshot)
    p21b = next(item for item in report["plans"] if item["id"] == "P21-B")
    assert p21b["pending_issue_gates"] == []
    assert p21b["pending_predecessor_plans"] == ["P21-A"]
    assert p21b["ready_to_implement"] is False


@pytest.mark.parametrize("promoted_state", ["open_draft", "merged"])
def test_planonly_pr_cannot_be_promoted_as_canonical_implementation(
    state, promoted_state,
) -> None:
    dag, registry, snapshot = state
    # Adversarial mutation: copy P17-C's planning PR into the canonical slot
    # and remove its PLAN_ONLY row. It remains forbidden even if merged.
    package = next(
        package for node in dag["nodes"] for package in node["packages"]
        if package["id"] == "P17-C"
    )
    package["prs"] = [108]
    registry["packages"] = [
        row for row in registry["packages"] if row["id"] != "P17-C"
    ]
    for index, row in enumerate(registry["packages"]):
        row["topological_index"] = index
    if promoted_state == "merged":
        planning_pr = next(pull for pull in snapshot["pulls"] if pull["number"] == 108)
        planning_pr.update(
            state="closed", draft=False, merged_at="2026-10-27T00:00:00Z"
        )

    with pytest.raises(ValueError, match="plan-only PR reused or registered as implementation"):
        audit_snapshot(dag, registry, snapshot)




def test_preflight_accepts_closed_unmerged_superseded_pr_without_promoting_package(state) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    row = next(item for item in registry["packages"] if item["planning_pr"] == 108)
    pull = next(item for item in changed["pulls"] if item["number"] == 108)
    marker = registry["policy"]["retirement_marker"]
    pull.update(state="closed", draft=True, merged_at=None, body=f"Original plan body\\n\\n{marker}")

    report = audit_snapshot(dag, registry, changed)
    result = next(item for item in report["plans"] if item["id"] == row["id"])
    assert result["state"] == "PLAN_ONLY"
    assert result["pr_lifecycle"] == "RETIRED_SUPERSEDED"
    assert result["ready_to_merge"] is False
    assert result["ready_to_implement"] is False
    assert 108 in registry["reserved_planning_prs"]
    assert 108 not in {
        pr for node in dag["nodes"] for package in node["packages"] for pr in package["prs"]
    }


def test_preflight_rejects_closed_plan_pr_without_registry_marker(state) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    pull = next(item for item in changed["pulls"] if item["number"] == 108)
    pull.update(state="closed", draft=True, merged_at=None, body="Closed without migration marker")
    with pytest.raises(ValueError, match="closed planning PR lacks registry supersession marker"):
        audit_snapshot(dag, registry, changed)


def test_preflight_rejects_merged_plan_pr_even_with_registry_marker(state) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    pull = next(item for item in changed["pulls"] if item["number"] == 108)
    pull.update(
        state="closed",
        merged_at="2026-10-28T12:00:00Z",
        body=registry["policy"]["retirement_marker"],
    )
    with pytest.raises(ValueError, match="planning PR must not be merged"):
        audit_snapshot(dag, registry, changed)

def test_closed_issue_cannot_retain_planonly_package(state) -> None:
    dag, registry, snapshot = state
    next(issue for issue in snapshot["issues"] if issue["number"] == 17)["state"] = "closed"
    with pytest.raises(ValueError, match="closed while package P17-C remains PLAN_ONLY"):
        audit_snapshot(dag, registry, snapshot)


def test_reopened_transitive_issue_gate_blocks_downstream_package(state) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    planned_issues = {row["issue"] for row in registry["packages"]}
    for issue in changed["issues"]:
        issue["state"] = "open" if issue["number"] in planned_issues else "closed"
    next(issue for issue in changed["issues"] if issue["number"] == 17)["state"] = "open"

    plans = audit_snapshot(dag, registry, changed)["plans"]
    p21a = next(item for item in plans if item["id"] == "P21-A")
    assert 17 in p21a["pending_issue_gates"]
    assert p21a["ready_to_implement"] is False


def test_open_issue_23_blocks_p26a_even_if_issue_24_is_closed(state) -> None:
    dag, registry, snapshot = state
    changed = copy.deepcopy(snapshot)
    planned_issues = {row["issue"] for row in registry["packages"]}
    for issue in changed["issues"]:
        issue["state"] = "open" if issue["number"] in planned_issues else "closed"
    next(issue for issue in changed["issues"] if issue["number"] == 23)["state"] = "open"

    plans = audit_snapshot(dag, registry, changed)["plans"]
    p26a = next(item for item in plans if item["id"] == "P26-A")
    assert 23 in p26a["pending_issue_gates"]
    assert p26a["ready_to_implement"] is False


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
    expected = {
        "draft": "must remain an open draft or be closed unmerged with registry marker",
        "state": "closed planning PR lacks registry supersession marker",
        "merged_at": "planning PR must not be merged",
    }[field]
    with pytest.raises(ValueError, match=expected):
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
    missing_planning_pr = registry["packages"][0]["planning_pr"]
    changed["pulls"] = [
        pull for pull in changed["pulls"]
        if pull["number"] != missing_planning_pr
    ]
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
    with pytest.raises(ValueError, match="missing mandatory predecessor plan paths"):
        validate_registry(dag, changed)


def test_direct_cli_verifies_registry_without_github_access() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/formalism_planonly_pr_preflight.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    data = json.loads(proc.stdout)
    assert data == {
        "valid": True, "planning_prs": 12,
        "all_status": "PLAN_ONLY", "merge_ready": False,
    }


def test_direct_cli_denies_merge_readiness_for_documents() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/formalism_planonly_pr_preflight.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--require-merge-ready"],
        cwd=root, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 1
    assert json.loads(proc.stdout)["merge_ready"] is False


def test_require_merge_ready_succeeds_when_all_packages_are_promoted(
    state, monkeypatch, tmp_path, capsys,
) -> None:
    import scripts.formalism_planonly_pr_preflight as preflight

    dag, registry, snapshot = state
    registry["packages"] = []
    next_pr = 2000
    for node in dag["nodes"]:
        for package in node["packages"]:
            if not package["prs"]:
                package["prs"] = [next_pr]
                snapshot["pulls"].append({
                    "number": next_pr,
                    "state": "closed",
                    "draft": False,
                    "merged_at": "2026-10-27T00:00:00Z",
                })
                next_pr += 1
    for issue in snapshot["issues"]:
        issue["state"] = "closed"

    snapshot_path = tmp_path / "promoted-snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot), encoding="utf-8")
    monkeypatch.setattr(preflight, "load_registry", lambda: (dag, registry))
    monkeypatch.setattr(
        preflight.sys,
        "argv",
        ["formalism_planonly_pr_preflight.py", "--snapshot", str(snapshot_path),
         "--require-merge-ready"],
    )

    assert preflight.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["planning_prs_audited"] == 0
    assert report["plans"] == []
