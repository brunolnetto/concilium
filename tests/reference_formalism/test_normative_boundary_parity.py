"""P09-B: fail-closed, standalone normative boundary and cross-format guards.

These tests check explicit contractual markers and evaluate hand-derived
boundary cases. They do not claim to prove every displayed equation.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/product/5-specifications/formulario_longo"
FILES = {
    "LONGO": DOCS / "FORMALISMO_LONGO.md",
    "RESUMIDO": DOCS / "FORMALISMO_RESUMIDO.md",
    "TEX": DOCS / "formulario_longo.tex",
}
ANNEX = DOCS / "CONVENCOES_NORMATIVAS.md"
CAPACITY = DOCS / "CAPACIDADE_E_RECURSOS.md"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ramp(n: int, start: int, end: int, maximum: int, up: int, down: int) -> list[int]:
    """Independent evaluation of the documented integer ramp envelope."""
    if n < 1 or min(start, end, maximum) < 1 or min(up, down) < 0:
        raise ValueError("invalid ramp domain")
    if start > maximum or end > maximum:
        raise ValueError("endpoint exceeds maximum")
    return [min(start + up * t, maximum, end + down * (n - 1 - t)) for t in range(n)]


@pytest.mark.parametrize(
    ("parameters", "expected"),
    [
        ((4, 2, 2, 2, 0, 0), [2, 2, 2, 2]),
        ((4, 1, 1, 4, 0, 0), [1, 1, 1, 1]),
        ((5, 1, 1, 3, 1, 1), [1, 2, 3, 2, 1]),
        ((1, 1, 1, 4, 0, 0), [1]),
    ],
)
def test_ramp_manual_vectors(parameters: tuple[int, ...], expected: list[int]) -> None:
    assert ramp(*parameters) == expected


@pytest.mark.parametrize("parameters", [(0, 1, 1, 2, 0, 0), (3, 1, 1, 2, -1, 0),
                                        (3, 3, 1, 2, 0, 0)])
def test_invalid_ramp_domain_rejected(parameters: tuple[int, ...]) -> None:
    with pytest.raises(ValueError):
        ramp(*parameters)


@pytest.mark.parametrize(("left", "right", "gap"), [
    ((1, 2), (3, 5), 0),
    ((1, 2), (4, 5), 1),
    ((1, 2), (8, 9), 5),
])
def test_inclusive_week_gap_matches_half_open(left: tuple[int, int],
                                               right: tuple[int, int], gap: int) -> None:
    assert max(0, right[0] - left[1] - 1) == gap
    assert max(0, right[0] - (left[1] + 1)) == gap


def test_exact_standby_break_even_prefers_fewer_transitions() -> None:
    idle_cost, switch_cost, empty_weeks = Decimal("80"), Decimal("160"), 2
    assert empty_weeks * idle_cost == switch_cost
    # Deterministic tie-break from normative annex: keep the existing chain.
    choice = "keep" if empty_weeks * idle_cost <= switch_cost else "split"
    assert choice == "keep"


def test_partial_week_is_closure_not_efficiency_loss() -> None:
    capacity = Decimal("400")
    delivered = Decimal("100")
    phi = delivered / capacity
    assert phi == Decimal("0.25")
    assert Decimal("40") * Decimal("10") == Decimal("400")  # contractual full-week K
    assert Decimal("2") * delivered / Decimal("10") == Decimal("20")  # physical V


def test_required_documents_exist_with_normative_cross_references() -> None:
    assert ANNEX.is_file() and CAPACITY.is_file()
    for path in FILES.values():
        assert path.is_file() and len(_text(path)) > 1000
    for name in ("LONGO", "RESUMIDO"):
        body = _text(FILES[name])
        assert "CONVENCOES_NORMATIVAS.md" in body
        assert "CAPACIDADE_E_RECURSOS.md" in body
    tex = _text(FILES["TEX"])
    assert "CAPACIDADE_E_RECURSOS.md" in tex
    assert "FORMALISMO_RESUMIDO.md" in tex or "FORMALISMO\\_RESUMIDO.md" in tex


def test_all_representations_contain_actual_capacity_semantics() -> None:
    for name, path in FILES.items():
        body = _text(path)
        assert "F_i(m" in body, name
        assert "eta_s" in body or "eta_{s" in body or "η_s" in body, name
        assert "standby" in body.lower() or "ocioso" in body.lower(), name
    assert "alpha" in _text(ANNEX)


def test_specification_has_no_obsolete_executable_team_penalty() -> None:
    forbidden = (
        "q_ij ← ρ_i · ε_ij · h_i · d_i · m_ij",
        "q_{ij} ← ρ_i · ε_{ij} · h_i · d_i · m_{ij}",
        "η_{s,ij} ← max-fluxo",
        "η_{s,iτ} ←",
    )
    for name, path in FILES.items():
        body = _text(path)
        for statement in forbidden:
            assert statement not in body, f"{name}: obsolete executable equation {statement}"


def test_normative_fail_closed_and_interval_assumptions_stay_visible() -> None:
    annex = _text(ANNEX)
    for rule in ("semiaberto", "mu_i^+", "tol_Q", "tol_C", "UNKNOWN",
                 "NOT_EVALUATED", "gap", "desempate"):
        assert rule in annex, rule
    assert "F_i(m)" in _text(CAPACITY)
