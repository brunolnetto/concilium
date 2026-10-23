"""P16-A: falsifiers for exact fungible resource-demand layer normalization."""
from __future__ import annotations

import pytest

from concilium.application.scheduling.resource_demand_levels import (
    normalize_weekly_resource_demand,
)

WEEKS = ("2026-W01", "2026-W02", "2026-W03", "2026-W04")


def test_staggered_multilevel_demands_reconstruct_exactly() -> None:
    d = normalize_weekly_resource_demand(
        WEEKS,
        {
            "A": {"GRUA": (1, 0, 2, 0)},
            "B": {"GRUA": (0, 1, 1, 0), "ESC": (0, 2, 0, 0)},
        },
    )
    assert d.reconstruct() == {
        "ESC": (0, 2, 0, 0),
        "GRUA": (1, 1, 3, 0),
    }
    assert [(l.level, l.blocks) for l in d.layers if l.resource_type == "GRUA"] == [
        (1, ((0, 3),)), (2, ((2, 3),)), (3, ((2, 3),)),
    ]
    assert [(l.level, l.blocks) for l in d.layers if l.resource_type == "ESC"] == [
        (1, ((1, 2),)), (2, ((1, 2),)),
    ]


def test_zero_demand_is_not_a_contractual_instance() -> None:
    zeros = normalize_weekly_resource_demand(WEEKS, {"A": {"GRUA": (0, 0, 0, 0)}})
    assert zeros.layers == ()
    assert zeros.reconstruct() == {"GRUA": (0, 0, 0, 0)}
    empty = normalize_weekly_resource_demand(WEEKS, {})
    assert empty.layers == ()
    assert empty.reconstruct() == {}


def test_adjacent_demand_has_zero_gap_and_missing_week_splits_blocks() -> None:
    d = normalize_weekly_resource_demand(
        WEEKS, {"A": {"GRUA": (1, 1, 0, 1)}}
    )
    assert d.layers[0].blocks == ((0, 2), (3, 4))
    assert 3 - 2 == 1  # one unoccupied week


def test_team_profile_is_counted_without_dividing_by_other_resource_types() -> None:
    # a_A,GRUA(m=2)=2; a_A,TRUCK(m=2)=6, both independently supplied.
    d = normalize_weekly_resource_demand(
        WEEKS, {"A": {"GRUA": (2, 0, 0, 0), "TRUCK": (6, 0, 0, 0)}}
    )
    assert d.reconstruct()["GRUA"][0] == 2
    assert d.reconstruct()["TRUCK"][0] == 6
    assert len(d.layers) == 8  # 2 + 6 exact instances; no cross-type ratio


@pytest.mark.parametrize(
    "bad",
    [
        {"A": {"GRUA": (-1, 0, 0, 0)}},
        {"A": {"GRUA": (True, 0, 0, 0)}},
        {"A": {"GRUA": (1.0, 0, 0, 0)}},
        {"A": {"GRUA": (1, 0, 0)}},
        {"A": {"GRUA": None}},
        {"A": {"": (1, 0, 0, 0)}},
        {"": {"GRUA": (1, 0, 0, 0)}},
        {"A": None},
    ],
)
def test_invalid_or_incomplete_physical_demand_fails_closed(bad: object) -> None:
    with pytest.raises(ValueError):
        normalize_weekly_resource_demand(WEEKS, bad)


def test_missing_evidence_is_not_zero_demand() -> None:
    with pytest.raises(ValueError, match="evidence"):
        normalize_weekly_resource_demand(WEEKS, None)


@pytest.mark.parametrize("weeks", [(), ("2026-W01", "2026-W01"), ("",)])
def test_bad_calendar_fails_closed(weeks: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        normalize_weekly_resource_demand(weeks, {})
