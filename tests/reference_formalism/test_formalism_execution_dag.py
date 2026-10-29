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
    # P18-C1/C2/C3 are merged; package registration remains independent of issue acceptance.
    assert sum(len(n["packages"]) for n in spec["nodes"]) == 66
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
    # P13-A #92 and P13-C #94 are assumed merged; P13-B #93 is not.
    result = report(spec, states(9, 10, 11, 12), all_merged(spec) - {93})
    thirteen = next(x for x in result["issues"] if x["issue"] == 13)
    assert thirteen["ready_to_execute"]
    assert thirteen["pending_packages"] == ["P13-B"]
    assert thirteen["pr_packages_merged"] == 2
    assert not thirteen["closure_preflight"]


def test_p13a_registered_but_not_merged_cannot_close_issue_thirteen(spec: dict) -> None:
    # A registered PR does not count as a merged mandatory package.
    result = report(spec, states(9, 10, 11, 12), all_merged(spec) - {92, 93, 94})
    thirteen = next(x for x in result["issues"] if x["issue"] == 13)
    assert thirteen["ready_to_execute"]
    assert thirteen["pending_packages"] == ["P13-A", "P13-B", "P13-C"]
    assert thirteen["pr_packages_merged"] == 0
    assert not thirteen["closure_preflight"]


def test_p13b_registration_does_not_prove_issue_acceptance(spec: dict) -> None:
    result = report(spec, states(9, 10, 11, 12), all_merged(spec))
    thirteen = next(x for x in result["issues"] if x["issue"] == 13)
    assert thirteen["pr_packages_merged"] == 3
    assert thirteen["closure_preflight"]
    assert thirteen["acceptance_verified"] is None


def test_p13c_is_mandatory_after_p13a_and_p13b_have_merged(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 13)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P13-A", [92]),
        ("P13-B", [93]),
        ("P13-C", [94]),
    ]
    result = report(spec, states(9, 10, 11, 12), all_merged(spec) - {94})
    thirteen = next(x for x in result["issues"] if x["issue"] == 13)
    assert thirteen["pending_packages"] == ["P13-C"]
    assert thirteen["pr_packages_total"] == 3
    assert thirteen["pr_packages_merged"] == 2
    assert not thirteen["closure_preflight"]
    assert thirteen["acceptance_verified"] is None


def test_p22c_registered_but_not_merged_cannot_close_w1(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 22)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P22-A", [29]), ("P22-B", [95]), ("P22-C", [96]),
    ]
    # Even a hypothetical merged P22-B does not certify P22-C.
    result = report(spec, states(9, 10, 11, 12, 13), all_merged(spec) - {96})
    row = next(x for x in result["issues"] if x["issue"] == 22)
    assert row["ready_to_execute"]
    assert row["pending_packages"] == ["P22-C"]
    assert row["pr_packages_merged"] == 2
    assert row["pr_packages_total"] == 3
    assert not row["closure_preflight"]
    assert row["acceptance_verified"] is None


def test_p25c_evidence_gate_remains_mandatory_after_p22_is_accepted(spec: dict) -> None:
    packages = next(x for x in spec["nodes"] if x["issue"] == 25)["packages"]
    assert next(x for x in packages if x["id"] == "P25-C")["prs"] == [99, 100]
    result = report(spec, states(9, 10, 11, 12, 13, 22), all_merged(spec) - {100})
    row = next(x for x in result["issues"] if x["issue"] == 25)
    assert row["ready_to_execute"]
    assert row["pending_packages"] == ["P25-C"]
    assert not row["closure_preflight"]


def test_p22b_pr_open_is_not_merged_and_does_not_unblock_p25(spec: dict) -> None:
    result = report(spec, states(9, 10, 11, 12, 13), all_merged(spec) - {95, 96})
    row = next(x for x in result["issues"] if x["issue"] == 22)
    next_issue = next(x for x in result["issues"] if x["issue"] == 25)
    assert row["pending_packages"] == ["P22-B", "P22-C"]
    assert not row["closure_preflight"]
    assert not next_issue["ready_to_execute"]


def test_all_three_p22_prs_merged_still_require_independent_acceptance(spec: dict) -> None:
    result = report(spec, states(9, 10, 11, 12, 13), all_merged(spec))
    oracle = next(x for x in result["issues"] if x["issue"] == 22)
    successor = next(x for x in result["issues"] if x["issue"] == 25)
    assert oracle["pr_packages_merged"] == 3
    assert oracle["closure_preflight"]
    assert oracle["acceptance_verified"] is None
    assert not successor["ready_to_execute"]


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


def test_p17c_is_registered_as_mandatory_skill06_reconciliation_package(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 17)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P17-A", [74]),
        ("P17-B", [77]),
        ("P17-C", [144]),
    ]
    result = report(spec, states(9, 10, 11, 12, 13, 22, 25), all_merged(spec) - {144})
    row = next(x for x in result["issues"] if x["issue"] == 17)
    assert row["pending_packages"] == ["P17-C"]
    assert row["pr_packages_total"] == 3
    assert row["pr_packages_merged"] == 2
    assert not row["closure_preflight"]
    assert row["acceptance_verified"] is None


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

def test_p18c1_c2_c3_unmerged_package_simulation_cannot_close_issue_eighteen(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 18)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P18-A", [76]),
        ("P18-B", [79]),
        ("P18-C1", [142]),
        ("P18-C2", [142]),
        ("P18-C3", [143]),
        ("P18-D", [158]),
        ("P18-E", [159]),
    ]
    # Simulate a state where the three merged package IDs are absent from the integrated set.
    result = report(
        spec, states(9, 10, 11, 12, 13, 22, 25), all_merged(spec) - {142, 143}
    )
    issue = next(x for x in result["issues"] if x["issue"] == 18)
    assert issue["ready_to_execute"]
    assert issue["pr_packages_total"] == 7
    assert issue["pr_packages_merged"] == 4
    assert issue["pending_packages"] == ["P18-C1", "P18-C2", "P18-C3"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None

def test_p14d_and_p14e_packages_must_be_merged_before_issue_fourteen_closes(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 14)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P14-A", [50]),
        ("P14-B", [52]),
        ("P14-C", [129]),
        ("P14-D", [145]),
        ("P14-E", [155]),
        ("P14-F", [160]),
    ]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 22, 25),
        all_merged(spec) - {145, 155, 160},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 14)
    assert issue["ready_to_execute"]
    assert issue["pr_packages_total"] == 6
    assert issue["pr_packages_merged"] == 3
    assert issue["pending_packages"] == ["P14-D", "P14-E", "P14-F"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None

    # Merging P14-D alone still leaves the exact-residual package mandatory.
    result = report(
        spec, states(9, 10, 11, 12, 13, 22, 25), all_merged(spec) - {155}
    )
    issue = next(x for x in result["issues"] if x["issue"] == 14)
    assert issue["pr_packages_total"] == 6
    assert issue["pr_packages_merged"] == 5
    assert issue["pending_packages"] == ["P14-E"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p15e_exact_residual_bridge_remains_mandatory(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 15)["packages"]
    assert ("P15-E", [156]) in [(p["id"], p["prs"]) for p in packages]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 14, 22, 25),
        all_merged(spec) - {156},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 15)
    assert issue["ready_to_execute"]
    assert issue["pr_packages_total"] == len(packages)
    assert issue["pending_packages"] == ["P15-E"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p15f_runtime_residual_preservation_is_mandatory(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 15)["packages"]
    assert ("P15-F", [157]) in [(p["id"], p["prs"]) for p in packages]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 14, 22, 25),
        all_merged(spec) - {157},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 15)
    assert issue["ready_to_execute"]
    assert issue["pr_packages_total"] == len(packages)
    assert issue["pending_packages"] == ["P15-F"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p14f_zero_capacity_residual_package_is_mandatory(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 14)["packages"]
    assert ("P14-F", [160]) in [(p["id"], p["prs"]) for p in packages]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 22, 25),
        all_merged(spec) - {155, 160},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 14)
    assert issue["pending_packages"] == ["P14-E", "P14-F"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p16f_iso_week_consistency_is_mandatory_before_issue_closure(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 16)["packages"]
    assert ("P16-F", [161]) in [(p["id"], p["prs"]) for p in packages]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 22, 25),
        all_merged(spec) - {138, 161},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 16)
    assert "P16-F" in issue["pending_packages"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p18d_no_waste_identity_package_is_mandatory(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 18)["packages"]
    assert ("P18-D", [158]) in [(p["id"], p["prs"]) for p in packages]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 22, 25),
        all_merged(spec) - {158},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 18)
    assert issue["pending_packages"] == ["P18-D"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p18e_unsupported_units_are_fail_closed_before_issue_closure(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 18)["packages"]
    assert ("P18-E", [159]) in [(p["id"], p["prs"]) for p in packages]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 22, 25),
        all_merged(spec) - {158, 159},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 18)
    assert issue["pending_packages"] == ["P18-D", "P18-E"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p19c_external_stock_provisioning_is_registered_as_mandatory_package(
    spec: dict,
) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 19)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P19-A", [80]),
        ("P19-B", [81]),
        ("P19-C", [150]),
    ]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 22, 25),
        all_merged(spec) - {150},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 19)
    assert issue["ready_to_execute"]
    assert issue["pr_packages_total"] == 3
    assert issue["pr_packages_merged"] == 2
    assert issue["pending_packages"] == ["P19-C"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p20b_event_attribution_is_mandatory_before_issue_twenty_closes(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 20)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P20-A", [84]),
        ("P20-B", [151]),
        ("P20-C", [152]),
    ]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 17, 18, 19, 22, 25),
        all_merged(spec) - {151, 152},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 20)
    assert issue["ready_to_execute"]
    assert issue["pr_packages_total"] == 3
    assert issue["pr_packages_merged"] == 1
    assert issue["pending_packages"] == ["P20-B", "P20-C"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p20c_category_bdi_is_mandatory_before_issue_twenty_closes(spec: dict) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 20)["packages"]
    assert ("P20-C", [152]) in [(p["id"], p["prs"]) for p in packages]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 17, 18, 19, 22, 25),
        all_merged(spec) - {151, 152},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 20)
    assert issue["pending_packages"] == ["P20-B", "P20-C"]
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None


def test_p21a_operational_pricing_diagnostics_are_mandatory_before_issue_twenty_one_closes(
    spec: dict,
) -> None:
    packages = next(n for n in spec["nodes"] if n["issue"] == 21)["packages"]
    assert [(p["id"], p["prs"]) for p in packages] == [
        ("P21-A", [153]),
        ("P21-B", []),
    ]
    result = report(
        spec,
        states(9, 10, 11, 12, 13, 17, 18, 19, 20, 22, 25),
        all_merged(spec) - {153},
    )
    issue = next(x for x in result["issues"] if x["issue"] == 21)
    assert issue["ready_to_execute"]
    assert issue["pending_packages"] == ["P21-A", "P21-B"]
    assert issue["pr_packages_total"] == 2
    assert issue["pr_packages_merged"] == 0
    assert not issue["closure_preflight"]
    assert issue["acceptance_verified"] is None
