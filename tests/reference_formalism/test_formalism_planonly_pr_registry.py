"""Guard plan-only PR skeletons against false formalism-package completion.

This checks governance metadata only, not product behavior or certification.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.formalism_wave_dag import MANIFEST, validate_dag

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/engineering/formalism_planonly_pr_registry.json"


@pytest.fixture
def sources() -> tuple[dict, dict]:
    dag = json.loads(MANIFEST.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    validate_dag(dag)
    return dag, registry


def test_plan_registry_covers_unimplemented_packages_and_preserves_history(sources) -> None:
    dag, registry = sources
    assert registry["schema"] == "concilium.formalism.planonly_pr_registry.v1"
    assert registry["policy"]["must_never_count_as_merged_package"] is True
    assert registry["policy"]["never_auto_close_issue"] is True
    assert registry["policy"]["planning_pr_lifecycle"] == "OPEN_DRAFT_OR_SUPERSEDED_CLOSED_UNMERGED"
    assert registry["policy"]["retirement_governance_pr"] == 120
    assert registry["policy"]["retirement_marker"].startswith(
        "Superseded by the durable plan-only registry in PR #120;"
    )
    package_slots = {
        (node["issue"], node["wave"], package["id"])
        for node in dag["nodes"] for package in node["packages"]
    }
    unimplemented = {
        (node["issue"], node["wave"], package["id"])
        for node in dag["nodes"] for package in node["packages"]
        if not package["prs"]
    }
    registered = {
        (plan["issue"], plan["wave"], plan["id"])
        for plan in registry["packages"]
    }
    # Every still-empty DAG slot needs a plan, but historical PLAN_ONLY PR
    # records remain auditable after a canonical implementation PR is assigned.
    assert registered.issubset(package_slots)
    assert unimplemented.issubset(registered)
    assert len(registered) == len(registry["packages"])


def test_planonly_prs_must_not_satisfy_canonical_dag_slots(sources) -> None:
    dag, registry = sources
    canonical = {pr for node in dag["nodes"] for p in node["packages"] for pr in p["prs"]}
    plans = {p["planning_pr"] for p in registry["packages"]}
    assert canonical.isdisjoint(plans)
    assert len(plans) == len(registry["packages"])
    assert all(p["status"] == "PLAN_ONLY" for p in registry["packages"])
    assert all(25 in p["blocks_on_issues"] for p in registry["packages"])
    assert all("Closes #" not in p.get("status", "") for p in registry["packages"])


def test_planning_dependencies_are_acyclic_and_in_topological_order(sources) -> None:
    _, registry = sources
    plans = registry["packages"]
    ids = {p["id"] for p in plans}
    positions = {p["id"]: i for i, p in enumerate(plans)}
    assert len(ids) == len(plans)
    assert [p["topological_index"] for p in plans] == list(range(len(plans)))
    by_id = {p["id"]: p for p in plans}
    for plan in plans:
        assert plan["head_branch"].startswith("plan/formalism-")
        assert plan["planning_url"].endswith("/" + str(plan["planning_pr"]))
        for parent in plan["depends_on_plans"]:
            assert parent in ids
            assert positions[parent] < positions[plan["id"]]
            assert by_id[parent]["wave"] <= plan["wave"]
        if plan["base_branch"] != "main":
            assert plan["base_branch"] in {
                by_id[parent]["head_branch"] for parent in plan["depends_on_plans"]
            }


def test_cross_issue_join_requires_all_predecessor_plans(sources) -> None:
    _, registry = sources
    by_id = {p["id"]: p for p in registry["packages"]}
    assert set(by_id["P20-B"]["depends_on_plans"]) == {"P17-C", "P19-C"}
    assert set(by_id["P20-B"]["blocks_on_issues"]) >= {17, 19, 25}
    assert by_id["P23-B"]["wave"] == 3
    assert "P21-B" in by_id["P23-B"]["depends_on_plans"]
    assert set(by_id["P26-B"]["depends_on_plans"]) == {"P26-A"}


def test_legacy_code_drafts_are_classified_as_out_of_manifest_or_superseded(sources) -> None:
    dag, registry = sources
    slots = {
        (node["issue"], package["id"])
        for node in dag["nodes"] for package in node["packages"]
    }
    for item in registry["existing_out_of_manifest"]:
        assert (item["issue"], item["provisional_package"]) not in slots
        assert item["status"] == "CODE_DRAFT_BLOCKED_WAVE1"

    by_id = {
        package["id"]: package
        for node in dag["nodes"] for package in node["packages"]
    }
    canonical_prs = {
        pr for node in dag["nodes"] for package in node["packages"]
        for pr in package["prs"]
    }
    superseded = {
        item["pr"]: item
        for item in registry["superseded_implementation_prs"]
    }
    assert set(superseded) == {102, 103}
    assert all(pr not in canonical_prs for pr in superseded)
    assert all(
        item["superseded_by_pr"] in canonical_prs
        for item in superseded.values()
    )
    assert superseded[103]["superseded_by_pr"] == 142
    assert set(superseded[103]["superseded_package_ids"]) == {"P18-C1", "P18-C2"}
    assert all(
        142 in by_id[package_id]["prs"]
        for package_id in superseded[103]["superseded_package_ids"]
    )

    cross = {item["pr"]: item for item in registry["cross_cutting_not_package_slots"]}
    assert cross[106]["depends_on_prs"] == [105]
