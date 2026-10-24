"""P13-A independent exact standby regime and economic counterfactual oracle."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction as F
from pathlib import Path

import pytest

DOC = (
    Path(__file__).resolve().parents[2]
    / "docs/product/5-specifications/formulario_longo/P13A_REGIMES_STANDBY.md"
)


class Regime(StrEnum):
    FULL_RATE_STANDBY = "FULL_RATE_STANDBY"
    DISCOUNTED_STANDBY = "DISCOUNTED_STANDBY"
    EXPLICIT_OFF_HIRE = "EXPLICIT_OFF_HIRE"


@dataclass(frozen=True)
class Tariff:
    regime: Regime
    active: F
    idle: F
    mobilize: F
    demobilize: F
    max_idle_gap: int

    def __post_init__(self) -> None:
        if not isinstance(self.regime, Regime):
            raise ValueError("explicit economic regime required")
        if any(
            type(value) is not F or value < 0
            for value in (self.active, self.idle, self.mobilize, self.demobilize)
        ):
            raise ValueError("four exact, nonnegative contractual rates required")
        if type(self.max_idle_gap) is not int or self.max_idle_gap < 0:
            raise ValueError("exact nonnegative maximal idle gap required")
        if self.regime is Regime.FULL_RATE_STANDBY and self.idle != self.active:
            raise ValueError("full-rate standby requires idle=active")
        if self.regime is Regime.DISCOUNTED_STANDBY and not (
            self.idle < self.active
        ):
            raise ValueError("discounted standby requires idle<active")


def costs(
    physical_demand: tuple[int, ...],
    contracted_presence: tuple[int, ...],
    tariff: Tariff,
    chains: int,
) -> tuple[F, F, F]:
    assert len(physical_demand) == len(contracted_presence)
    assert type(chains) is int and chains >= 0
    assert all(
        type(demand) is int and type(presence) is int
        and 0 <= demand <= presence
        for demand, presence in zip(physical_demand, contracted_presence, strict=True)
    )
    active = F(sum(physical_demand)) * tariff.active
    idle = F(sum(
        present - demand
        for demand, present in zip(physical_demand, contracted_presence, strict=True)
    )) * tariff.idle
    mobility = F(chains) * (tariff.mobilize + tariff.demobilize)
    return active, idle, mobility


def counterfactual(gap: int, tariff: Tariff) -> tuple[F, F, str]:
    if type(gap) is not int or gap < 0:
        raise ValueError("gap must be exact nonnegative integer")
    if gap > tariff.max_idle_gap:
        return F(gap) * tariff.idle, tariff.mobilize + tariff.demobilize, "KEEP_INFEASIBLE"
    keep = F(gap) * tariff.idle
    split = tariff.mobilize + tariff.demobilize
    if keep < split:
        verdict = "KEEP"
    elif keep > split:
        verdict = "SPLIT"
    else:
        verdict = "KEEP"  # normative deterministic tie-break: fewer transitions
    return keep, split, verdict


def test_baseline_full_rate_presence_identity() -> None:
    rate = Tariff(Regime.FULL_RATE_STANDBY, F(100), F(100), F(40), F(40), 3)
    act, idle, move = costs((1, 0, 0, 1), (1, 1, 1, 1), rate, 1)
    assert (act, idle, move) == (F(200), F(200), F(80))
    assert act + idle == F(100) * 4
    assert counterfactual(2, rate) == (F(200), F(80), "SPLIT")


def test_discounted_rate_falsifies_baseline_and_prefers_keep() -> None:
    rate = Tariff(Regime.DISCOUNTED_STANDBY, F(100), F(25), F(40), F(40), 3)
    act, idle, move = costs((1, 0, 0, 1), (1, 1, 1, 1), rate, 1)
    assert (act, idle, move) == (F(200), F(50), F(80))
    assert act + idle == F(250)
    assert act + idle != F(400)
    assert counterfactual(2, rate) == (F(50), F(80), "KEEP")


def test_tie_keeps_when_feasible_and_maximum_gap_rejects_keep() -> None:
    tie = Tariff(Regime.DISCOUNTED_STANDBY, F(100), F(40), F(40), F(40), 2)
    assert counterfactual(2, tie) == (F(80), F(80), "KEEP")
    assert counterfactual(3, tie)[-1] == "KEEP_INFEASIBLE"


def test_missing_rate_mismatch_and_unknown_regime_fail_closed() -> None:
    with pytest.raises(ValueError, match="explicit economic regime"):
        Tariff("UNKNOWN_CONTRACT", F(100), F(25), F(40), F(40), 3)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="full-rate"):
        Tariff(Regime.FULL_RATE_STANDBY, F(100), F(25), F(40), F(40), 3)
    with pytest.raises(ValueError, match="discounted"):
        Tariff(Regime.DISCOUNTED_STANDBY, F(100), F(100), F(40), F(40), 3)


def test_physical_demand_cannot_exceed_contract_presence() -> None:
    tariff = Tariff(Regime.FULL_RATE_STANDBY, F(100), F(100), F(0), F(0), 2)
    with pytest.raises(AssertionError):
        costs((2,), (1,), tariff, 1)


def test_posting_categories_are_exclusive_and_do_not_duplicate_movement() -> None:
    # K is a presence charge; mobility lives in IND; MAT/COMB purchases
    # must not be deduced from the contractual standby rate.
    tariff = Tariff(Regime.DISCOUNTED_STANDBY, F(100), F(25), F(40), F(40), 2)
    active, idle, movement = costs((1, 0, 0, 1), (1, 1, 1, 1), tariff, 1)
    k = active + idle
    ind = movement
    material = F(2) * F(100)  # measured 2 goods/output and 100 output, 1 BRL/good
    assert k == F(250)
    assert ind == F(80)
    assert material == F(200)
    assert k + ind + material == F(530)


def test_normative_file_requires_regime_names_and_limits() -> None:
    s = DOC.read_text(encoding="utf-8")
    assert all(t.value in s for t in Regime)
    for token in ("NOT_EVALUATED", "MOBILIZATION_EVENT", "DISCOUNTED_STANDBY"):
        assert token in s
