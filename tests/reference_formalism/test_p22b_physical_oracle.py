"""Independent P22-B physical oracle goldens and negative mutations.

Expected values in JSON are reviewed physical hand calculations, never
generated from production scheduling or finance modules.
"""
from __future__ import annotations

import json
from copy import deepcopy
from fractions import Fraction as F
from itertools import combinations
from pathlib import Path

import pytest

from tests.reference_formalism.physical_reference import (
    _max_flow,
    _ramp,
    evaluate_physical,
    verify_physical,
)
from tests.reference_formalism.protocol import ReferenceContractError

PATH = Path(__file__).parent / "vectors" / "physical_calendar_v1.json"


def goldens() -> list[dict]:
    doc = json.loads(PATH.read_text(encoding="utf-8"))
    assert doc["protocol"] == "formalism-physical/1"
    assert doc["formalism"]["baseline_blob"] == "f83d37c03b3dbcebc0cbb446cc6d4333fa05cdd5"
    assert doc["formalism"]["rounding"].startswith("exact Fraction")
    return doc["vectors"]


@pytest.mark.parametrize("case", goldens(), ids=lambda c: c["case_id"])
def test_hand_verified_physical_vectors(case: dict) -> None:
    assert verify_physical(deepcopy(case)) == case["expected"]
    # Repeated reference computations must not mutate the input contract.
    assert verify_physical(case) == verify_physical(case)


def test_early_q_fs_start_mutation_is_detected() -> None:
    bad = deepcopy(goldens()[3])
    # 75% of predecessor scope is attained only at end of week 2.
    bad["expected"]["activities"]["B"]["start_week"] = 2
    with pytest.raises(ReferenceContractError, match="physical golden mismatch"):
        verify_physical(bad)


def test_extra_capacity_from_double_front_count_is_detected() -> None:
    bad = deepcopy(goldens()[0])
    # Wrongly multiplicative model F(2)*m would double throughput;
    # declaring the edge capacity higher must invalidate the reviewed golden.
    bad["inputs"]["graphs"]["linear"]["edges"][0]["capacity"] = "20"
    with pytest.raises(ReferenceContractError, match="physical golden mismatch"):
        verify_physical(bad)


def test_ramp_rate_mutation_changes_golden() -> None:
    bad = deepcopy(goldens()[2])
    bad["inputs"]["activities"][0]["ramp"]["up"] = 0
    with pytest.raises(ReferenceContractError):
        verify_physical(bad)


def test_scarce_resource_not_freed_in_zero_weather_week() -> None:
    case = deepcopy(goldens()[3])
    for activity in case["inputs"]["activities"]:
        activity["resource_units"] = {"CREW": 1}
    case["inputs"]["resource_caps"] = {"CREW": 1}
    # Predecessor A holds the scarce crew through week 2 even though
    # the middle week has zero productive output.
    result = evaluate_physical(case)
    assert result["activities"]["B"]["start_week"] == 3


def test_missing_calendar_or_horizon_fails_closed() -> None:
    bad = deepcopy(goldens()[3])
    bad["inputs"]["horizon_weeks"] = 2
    bad["inputs"]["weather"] = bad["inputs"]["weather"][:2]
    bad["inputs"]["performance"] = bad["inputs"]["performance"][:2]
    with pytest.raises(ReferenceContractError, match="INFEASIBLE"):
        evaluate_physical(bad)


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("weather", ["1", "2", "1"]),
        ("performance", ["NaN", "1", "1"]),
        ("weather", [1.0, "1", "1"]),
    ],
)
def test_invalid_weather_performance_fail_closed(field: str, bad: list) -> None:
    case = deepcopy(goldens()[1])
    case["inputs"][field] = bad
    with pytest.raises(ReferenceContractError):
        evaluate_physical(case)


def test_cyclic_q_fs_rejected_before_scheduling() -> None:
    case = deepcopy(goldens()[4])
    case["inputs"]["activities"][0]["predecessors"] = [
        {"id": "B", "threshold": "0.5", "lag_weeks": 0},
    ]
    with pytest.raises(ReferenceContractError, match="precedence cycle"):
        evaluate_physical(case)


def test_unknown_fields_and_unknown_resource_rejected() -> None:
    case = deepcopy(goldens()[0])
    case["inputs"]["a_runtime_fallback"] = True
    with pytest.raises(ReferenceContractError, match="missing or unknown"):
        evaluate_physical(case)
    case = deepcopy(goldens()[0])
    case["inputs"]["activities"][0]["resource_units"]["GHOST"] = 1
    with pytest.raises(ReferenceContractError, match="unknown physical resource"):
        evaluate_physical(case)


def test_ramp_null_rates_do_not_mobilize_maximum_for_free() -> None:
    profile = _ramp({"initial": 1, "final": 1, "maximum": 4, "up": 0, "down": 0}, 3)
    assert profile == (1, 1, 1)


def test_max_flow_equals_independent_min_cut_for_tiny_directed_graph() -> None:
    graph = {
        "nodes": ["s", "a", "b", "t"], "source": "s", "sink": "t",
        "edges": [
            {"from": "s", "to": "a", "capacity": "5", "scaling": "per_front"},
            {"from": "s", "to": "b", "capacity": "3", "scaling": "fixed"},
            {"from": "a", "to": "b", "capacity": "2", "scaling": "fixed"},
            {"from": "a", "to": "t", "capacity": "4", "scaling": "per_front"},
            {"from": "b", "to": "t", "capacity": "6", "scaling": "fixed"},
        ],
    }
    for fronts in range(1, 5):
        cuts = []
        for count in range(3):
            for interior in combinations(("a", "b"), count):
                source_side = set(interior) | {"s"}
                cut = sum(
                    F(e["capacity"]) * (fronts if e["scaling"] == "per_front" else 1)
                    for e in graph["edges"]
                    if e["from"] in source_side and e["to"] not in source_side
                )
                cuts.append(cut)
        assert _max_flow(graph, fronts) == min(cuts)


def test_calendar_search_deterministic_over_stable_goldens() -> None:
    for case in goldens():
        observations = [evaluate_physical(deepcopy(case)) for _ in range(3)]
        assert observations[0] == observations[1] == observations[2]
