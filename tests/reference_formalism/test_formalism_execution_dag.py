"""Regression tests for the issue/PR execution DAG; no GitHub network needed."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.formalism_wave_dag import MANIFEST, report, validate_dag


@pytest.fixture
def spec() -> dict:
    return json.loads(Path(MANIFEST).read_text(encoding="utf-8"))


def states(*closed: int) -> dict[int, str]:
    return {i: ("closed" if i in closed else "open") for i in range(9, 27)}


def all_merged(spec: dict) -> set[int]:
    return {
        pr
        for node in spec["nodes"]
        for package in node["packages"]
        for pr in package["prs"]
    }


def test_exact_portfolio_and_valid_topological_order(spec: dict) -> None:
    order = validate_dag(spec)
    assert len(order) == 18
    assert set(order) == set(range(9, 27))
    assert sum(len(n["packages"]) for n in spec["nodes"]) == 44
    for n in spec["nodes"]:
        assert all(order.index(p) < order.index(n["issue"]) for p in n["blocked_by"])


def test_dag_rejects_backward_wave_dependency(spec: dict) -> None:
    changed = copy.deepcopy(spec)
    next(n for n in changed["nodes"] if n["issue"] == 9)["blocked_by"] = [23]
    with pytest.raises(ValueError, match="backwards wave"):
        validate_dag(changed)


def test_dag_rejects_cycle_within_wave(spec: dict) -> None:
    changed = copy.deepcopy(spec)
    next(n for n in changed["nodes"] if n["issue"] == 9)["blocked_by"] = [11]
    with pytest.raises(ValueError, match="cycle"):
        validate_dag(changed)


def test_dag_rejects_missing_node(spec: dict) -> None:
    changed = copy.deepcopy(spec)
    changed["nodes"] = [n for n in changed["nodes"] if n["issue"] != 13]
    with pytest.raises(ValueError, match="exactly once"):
        validate_dag(changed)


def test_only_issue_nine_ready_while_wave_zero_incomplete(spec: dict) -> None:
    result = report(spec, states(10, 12), all_merged(spec))
    assert result["active_wave"] == 0
    assert result["ready_to_execute"] == [9]
    assert result["waves_closed"][0] is False
    assert not any(x["closure_preflight"] for x in result["issues"] if x["wave"] > 0)
    assert any(x["historical_out_of_order"] for x in result["issues"] if x["issue"] == 10)


def test_merged_prs_do_not_override_open_prerequisites(spec: dict) -> None:
    r = report(spec, states(10, 12), all_merged(spec))
    issue_14 = next(x for x in r["issues"] if x["issue"] == 14)
    assert issue_14["pr_packages_merged"] == issue_14["pr_packages_total"]
    assert issue_14["blocked_by_prior_waves"] == [0, 1]
    assert issue_14["closure_preflight"] is False
    assert issue_14["acceptance_verified"] is None


def test_wave_unblocks_only_after_every_prior_issue_closed(spec: dict) -> None:
    w0 = states(9, 10, 11, 12, 13)
    result = report(spec, w0, all_merged(spec))
    assert result["waves_closed"][0] is True
    assert result["active_wave"] == 1
    assert result["ready_to_execute"] == [22]


def test_missing_package_blocks_closure_even_when_parents_done(spec: dict) -> None:
    result = report(spec, states(9, 10, 11, 12), all_merged(spec))
    thirteen = next(x for x in result["issues"] if x["issue"] == 13)
    assert thirteen["ready_to_execute"]
    assert thirteen["pending_packages"] == ["P13-A", "P13-B"]
    assert not thirteen["closure_preflight"]


def test_snapshot_cannot_mark_acceptance_verified(spec: dict) -> None:
    result = report(spec, states(9, 10, 11, 12, 13), all_merged(spec))
    assert all(x["acceptance_verified"] is None for x in result["issues"])


def test_incomplete_issue_snapshot_fails_closed(spec: dict) -> None:
    with pytest.raises(ValueError, match="incomplete"):
        report(spec, states(10, 12) | {9: "closed", 13: "open"} | {26: "unknown"}, set())
