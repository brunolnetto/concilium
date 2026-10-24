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
    assert sum(len(n["packages"]) for n in spec["nodes"]) == 48
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
    # P13-A now has a tracked PR (#92), so the hypothetical all-merged
    # snapshot still lacks only P13-B, which has no registered PR.
    assert thirteen["pending_packages"] == ["P13-B"]
    assert not thirteen["closure_preflight"]


def test_p13a_registered_but_not_merged_cannot_close_issue_thirteen(spec: dict) -> None:
    # Registering #92 in the DAG is not equivalent to merging it.
    result = report(spec, states(9, 10, 11, 12), all_merged(spec) - {92})
    thirteen = next(x for x in result["issues"] if x["issue"] == 13)
    assert thirteen["ready_to_execute"]
    assert thirteen["pending_packages"] == ["P13-A", "P13-B"]
    assert thirteen["pr_packages_merged"] == 0
    assert not thirteen["closure_preflight"]


def test_snapshot_cannot_mark_acceptance_verified(spec: dict) -> None:
    result = report(spec, states(9, 10, 11, 12, 13), all_merged(spec))
    assert all(x["acceptance_verified"] is None for x in result["issues"])


def test_incomplete_issue_snapshot_fails_closed(spec: dict) -> None:
    with pytest.raises(ValueError, match="incomplete"):
        report(spec, {i: s for i, s in states(10, 12).items() if i != 26}, set())


def test_p09c_is_integrated_but_p09d_blocks_issue_nine_closure(spec: dict) -> None:
    # Catch prior false-positive: original 2/2 slots were integrated, yet
    # P09-C (already merged #86) and P09-D proofs remain material obligations.
    packages = next(n for n in spec["nodes"] if n["issue"] == 9)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P09-A", [28]),
        ("P09-B", [43]),
        ("P09-C", [86]),
        ("P09-D", [87]),
        ("P09-E", [88]),
    ]
    result = report(spec, states(10, 12), all_merged(spec) - {87, 88})
    row = next(x for x in result["issues"] if x["issue"] == 9)
    assert row["pr_packages_merged"] == 3
    assert row["pr_packages_total"] == 5
    assert row["pending_packages"] == ["P09-D", "P09-E"]
    assert row["ready_to_execute"]
    assert not row["closure_preflight"]


def test_p09c_missing_merge_blocks_closure_even_with_d_proved(spec: dict) -> None:
    changed = copy.deepcopy(spec)
    node9 = next(n for n in changed["nodes"] if n["issue"] == 9)
    next(p for p in node9["packages"] if p["id"] == "P09-D")["prs"] = [87]
    merged = all_merged(changed)
    merged.discard(86)
    row = next(
        x for x in report(changed, states(10, 12), merged)["issues"]
        if x["issue"] == 9
    )
    assert "P09-C" in row["pending_packages"]
    assert not row["closure_preflight"]


def test_p09e_gate_remains_closed_even_after_p09d_is_merged(spec: dict) -> None:
    # P09-A/B/C/D may be merged on main, but the newly necessary alias
    # coverage cannot be bypassed while PR #88 is merely open.
    row = next(
        x for x in report(spec, states(10, 12), all_merged(spec) - {88})["issues"]
        if x["issue"] == 9
    )
    assert row["ready_to_execute"]
    assert row["pending_packages"] == ["P09-E"]
    assert row["pr_packages_merged"] == 4
    assert row["pr_packages_total"] == 5
    assert not row["closure_preflight"]


def test_wave_zero_issue_eleven_is_next_but_cannot_close_early(spec: dict) -> None:
    # #9/#10/#12 are accepted; #11 may execute P11-A, but cannot close
    # until P11-B (#90) and P11-C (#91) are fully integrated.
    packages = next(n for n in spec["nodes"] if n["issue"] == 11)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P11-A", [89]),
        ("P11-B", [90]),
        ("P11-C", [91]),
    ]
    result = report(spec, states(9, 10, 12), all_merged(spec) - {90})
    assert result["active_wave"] == 0
    assert result["ready_to_execute"] == [11]
    row = next(r for r in result["issues"] if r["issue"] == 11)
    assert row["pending_packages"] == ["P11-B"]
    assert not row["closure_preflight"]


def test_p11c_normative_consumer_prevents_premature_wave_zero_closure(spec: dict) -> None:
    # P11-A/B were merged, but full Skill06/representation acceptance still
    # requires P11-C #91. The previous PR count is not an acceptance proof.
    result = report(spec, states(9, 10, 12), all_merged(spec) - {91})
    row = next(x for x in result["issues"] if x["issue"] == 11)
    assert row["ready_to_execute"]
    assert row["pending_packages"] == ["P11-C"]
    assert row["pr_packages_merged"] == 2
    assert row["pr_packages_total"] == 3
    assert not row["closure_preflight"]
