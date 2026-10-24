"""P13-C: independent conditional-regime checks and normative anti-drift gates.

This reference suite must not import the optimizer or any production package.
"""
from __future__ import annotations

from fractions import Fraction as F
from itertools import combinations, product
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/product/5-specifications/formulario_longo"
REGIMES = (
    "FULL_RATE_STANDBY",
    "DISCOUNTED_STANDBY",
    "EXPLICIT_OFF_HIRE",
    "OUTPUT_PROPORTIONAL",
    "OUTPUT_WITH_MEASURED_LOSS",
    "HOURLY_WITH_MEASURED_IDLE",
)


def _doc(name: str) -> str:
    text = (DOCS / name).read_text(encoding="utf-8")
    return text.replace(r"\_", "_")


@pytest.mark.parametrize(
    "name",
    ["FORMALISMO_LONGO.md", "FORMALISMO_RESUMIDO.md", "formulario_longo.tex"],
)
def test_regime_selector_parity_and_missing_evidence_fails_closed(name: str) -> None:
    doc = _doc(name)
    for regime in REGIMES:
        assert regime in doc, f"{name}: {regime} missing"
    assert "NOT_EVALUATED" in doc
    assert "P13B_TIPAGEM_REGIMES_CONSUMO.md" in doc


def test_in_place_long_form_no_unconditional_baseline_equalities() -> None:
    long = _doc("FORMALISMO_LONGO.md")
    ix = long.split("## Parte IX", 1)[1].split("## Parte X", 1)[0]
    x = long.split("## Parte X", 1)[1].split("## Parte XI", 1)[0]
    xiv = long.split("### XIV.4", 1)[1].split("### XIV.6", 1)[0]
    assert "c_g^{act}d_{gj}+c_g^{idle}s_{gj}" in ix
    assert "k_{uv}c_r^{idle}" in ix
    assert "FULL_RATE_STANDBY" in ix
    assert "NOT_EVALUATED" in ix
    assert "C^{cons}=\\sum_g p_g U_g" in x
    assert "OUTPUT_PROPORTIONAL" in x
    assert "OUTPUT_WITH_MEASURED_LOSS" in x
    assert "HOURLY_WITH_MEASURED_IDLE" in x
    assert "act_τ*c_τ^act + idle_τ*c_τ^idle" in xiv
    assert "gap*c_τ^idle" in xiv
    assert "C^{cons} ← Σ_g p_g*U_g" in xiv
    assert "C^{pool}     ← C^{pool}     + sem_τ · c_τ^sem" not in xiv
    assert "C^{cons} ← Σ_i γ_i^{V,cat} · Q_i / ρ_i" not in xiv


def test_tex_sections_reflect_conditional_tariffs_and_physical_consumption() -> None:
    tex = _doc("formulario_longo.tex")
    ix = tex.split(r"\subsubsection{IX.2", 1)[1].split(r"\subsection{Parte X", 1)[0] if (
        r"\subsection{Parte X" in tex
    ) else tex.split(r"\subsubsection{IX.2", 1)[1]
    assert "c_g^{act}d_{gj}+c_g^{idle}s_{gj}" in ix
    assert "k_{uv}c_r^{idle}" in ix
    assert "somente" in ix
    assert r"C^{cons}=\sum_gp_gU_g" in tex
    assert "OUTPUT_WITH_MEASURED_LOSS" in tex


def _cost(
    gaps: tuple[int, ...],
    *,
    active: F,
    idle: F,
    movement: F,
    max_idle_gap: int,
) -> tuple[F, int, tuple[bool, ...]]:
    """Independent exhaustive search over all keep/split binary decisions.

    One active week per demand block; if a gap is kept, its idle weeks
    are paid; each resulting chain incurs one pair of movements.
    Minimize exact cost, then number of chains (stable KEEP on a tie).
    """
    candidates: list[tuple[F, int, tuple[bool, ...]]] = []
    for flags in product((False, True), repeat=len(gaps)):
        if any(keep and gap > max_idle_gap
               for keep, gap in zip(flags, gaps, strict=True)):
            continue
        chains = 1 + sum(not keep for keep in flags)
        standby = sum(gap for keep, gap in zip(flags, gaps, strict=True) if keep)
        total = F(len(gaps) + 1) * active + F(standby) * idle + chains * movement
        candidates.append((total, chains, flags))
    if not candidates:
        raise ValueError("no contractual configuration")
    return min(candidates, key=lambda x: (x[0], x[1]))


@pytest.mark.parametrize(
    ("idle", "max_gap", "cost", "chains", "choices"),
    [
        (F(25), 2, F(330), 1, (True,)),
        (F(100), 2, F(360), 2, (False,)),
        (F(40), 2, F(360), 1, (True,)),
        (F(0), 0, F(360), 2, (False,)),
    ],
)
def test_independent_two_block_oracle_distinguishes_tariff_regime(
    idle: F, max_gap: int, cost: F, chains: int, choices: tuple[bool, ...],
) -> None:
    assert _cost((2,), active=F(100), idle=idle, movement=F(80),
                 max_idle_gap=max_gap) == (cost, chains, choices)


def test_three_blocks_enumerated_without_optimistic_zero_rate_fallback() -> None:
    # Two independent length-1 gaps; total active cost always 3*100.
    assert _cost((1, 1), active=F(100), idle=F(70),
                 movement=F(80), max_idle_gap=2) == (F(520), 1, (True, True))
    assert _cost((1, 1), active=F(100), idle=F(100),
                 movement=F(80), max_idle_gap=2) == (F(540), 3, (False, False))


def test_output_partition_invariance_is_conditional_and_losses_add_delta() -> None:
    quantity = F(100)
    kappa = F(2)
    unit_price = F(5)
    baseline = quantity * kappa * unit_price
    assert baseline == (F(40) + F(60)) * kappa * unit_price == F(1000)
    measured_loss = F(20)
    assert baseline + measured_loss * unit_price == F(1100)
    hourly_operated = F(10) * F(3)
    measured_idle = F(2)
    measured_waste = F(1)
    assert (hourly_operated + measured_idle + measured_waste) * unit_price == F(165)


def _fungible_assignment_minimum(
    demand: tuple[int, ...], *, instances: int,
    active: F, idle: F, movement: F, max_idle_gap: int,
) -> tuple[F, int]:
    """Exhaustively enumerate labeled physical-instance assignments.

    Unlike the fixed-level oracle, instance identities may exchange middle
    demand periods while reconstructing exactly the same weekly demand.
    """
    if any(d < 0 or d > instances for d in demand):
        raise ValueError("demand must fit declared physical instances")
    choices = [
        tuple(combinations(range(instances), count))
        for count in demand
    ]
    solutions: list[tuple[F, int]] = []
    for weekly in product(*choices):
        optimum = F(0)
        chains_total = 0
        for inst in range(instances):
            active_weeks = tuple(j for j, labels in enumerate(weekly) if inst in labels)
            if not active_weeks:
                continue
            gaps = tuple(
                nxt - prev - 1
                for prev, nxt in zip(active_weeks, active_weeks[1:], strict=False)
            )
            local = [
                (
                    F(len(active_weeks)) * active
                    + F(sum(gap for gap, keep in zip(gaps, flags, strict=True)
                            if keep)) * idle
                    + (1 + sum(not keep for keep in flags)) * movement,
                    1 + sum(not keep for keep in flags),
                )
                for flags in product((False, True), repeat=len(gaps))
                if all((not keep) or gap <= max_idle_gap
                       for gap, keep in zip(gaps, flags, strict=True))
            ]
            best = min(local)
            optimum += best[0]
            chains_total += best[1]
        solutions.append((optimum, chains_total))
    return min(solutions)


def test_fungible_reassignment_falsifies_fixed_layer_global_optimality() -> None:
    # P16's canonical height-level demand assignment costs 120:
    # level 1 active 4 weeks = 4*5+30 = 50;
    # level 2 active weeks 1 and 4, gap 2>1 => 2*5+2*30 = 70.
    fixed_layers = F(120)
    # A valid alternative: two labeled instances, active on weeks
    # (1,2,4) and (1,3,4), each idle once: 3*5+1+30 = 46.
    true_small_optimum = _fungible_assignment_minimum(
        (2, 1, 1, 2), instances=2,
        active=F(5), idle=F(1), movement=F(30), max_idle_gap=1,
    )
    assert true_small_optimum == (F(92), 2)
    assert fixed_layers > true_small_optimum[0]
