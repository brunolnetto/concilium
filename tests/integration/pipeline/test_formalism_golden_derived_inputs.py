"""#206: a project reaches the exact ledgers from its own data plus declared contract terms.

The golden RFPs hand-write `rcpsp_spec` (team per front, pool, durations) and
`p16_exact_tariffs`. Here the same projects run with **neither**: Skill04 and
Skill05 derive the per-resource spec from the EAP, the catalog production
teams and the configured pool, and the P16 tariffs come from the catalog rate
plus the project's `contract_terms` declaration (N8). Without declared terms
nothing is estimated. All runs are `slow` (one pipeline run each).
"""

from __future__ import annotations

from fractions import Fraction
from pathlib import Path

import pytest

from tests.support.golden_differential import differential_report
from tests.support.golden_pipeline import catalog, load_canonical, run, scenario

pytestmark = pytest.mark.slow

SCENARIO = "sharing_theta_standby_remob"
DEFAULT = {
    "regime": "FULL_RATE_STANDBY",
    "mobilize": "0",
    "demobilize": "0",
    "max_idle_gap": 0,
    "source": "golden fixture",
}


def _without_hand_written_spec(overrides) -> tuple[dict, dict]:
    spec = scenario(SCENARIO)
    declared = spec["skill_inputs"]["05-equipes-e-alocacao"].pop("rcpsp_spec")["p16_exact_tariffs"]
    spec["skill_inputs"]["04-cronograma"].pop("rcpsp_spec")
    if overrides is not None:
        spec["skill_inputs"]["05-equipes-e-alocacao"]["contract_terms"] = {
            "default": DEFAULT,
            "overrides": {tipo: overrides(tariff) for tipo, tariff in declared.items()},
        }
    return spec, declared


def _witnesses(canonical) -> dict[str, dict]:
    return {c.tipo_id: c.p16_global_assignment for c in canonical.contratos_recurso if c.p16_global_assignment}


def test_declared_terms_reproduce_the_golden_without_a_hand_written_spec(tmp_path: Path) -> None:
    """Declaring the fixture's tariffs as contract terms yields the same certified run:
    clean GO, every phase matching the independent oracles, nothing unverified."""
    spec, declared = _without_hand_written_spec(
        lambda t: {k: t[k] for k in ("active_week", "mobilize", "demobilize", "max_idle_gap", "gap_max_viavel")}
    )
    result, service = run(tmp_path, spec)
    certificate = result["formalism_certificate"]
    assert (certificate["effective_decision"], certificate["project_go"]) == ("GO", True), certificate["reasons"]
    canonical = load_canonical(result, service)
    report = differential_report(canonical, catalog(spec), certificate)
    assert report["first_divergence"] is None and report["unverified"] == []
    witnesses = _witnesses(canonical)
    assert set(witnesses) == set(declared)
    for tipo, tariff in declared.items():
        assert Fraction(witnesses[tipo]["tariff"]["active_week"]) == Fraction(tariff["active_week"]), tipo


def test_catalog_derived_tariffs_certify_with_exact_rationals(tmp_path: Path) -> None:
    """Only movement costs and idle gaps are declared; the active rate is the exact
    catalog rate (monthly / s_mes), carried unrounded through P16-P23."""
    spec, declared = _without_hand_written_spec(lambda t: {k: t[k] for k in ("mobilize", "demobilize", "max_idle_gap")})
    result, service = run(tmp_path, spec)
    certificate = result["formalism_certificate"]
    assert (certificate["effective_decision"], certificate["project_go"]) == ("GO", True), certificate["reasons"]
    canonical = load_canonical(result, service)
    report = differential_report(canonical, catalog(spec), certificate)
    assert report["first_divergence"] is None
    # The exhaustive reference oracle takes terminating decimals only (follow-up).
    assert {u.provenance for u in report["unverified"]} <= {
        "tariff is not a terminating decimal for the reference protocol"
    }
    plant = _witnesses(canonical)["EQ-USINA-SOLOS-300TH"]["tariff"]["active_week"]
    assert Fraction(plant) == Fraction("78205.92") / Fraction(1461, 336)
    assert Fraction(plant) != Fraction(declared["EQ-USINA-SOLOS-300TH"]["active_week"])  # not the cent rounding


def test_without_declared_contract_terms_nothing_is_estimated(tmp_path: Path) -> None:
    """No contract terms: the pool has no exact witness, the run is never GO and the
    unknown contracts are reported — no fallback cost appears in the certificate."""
    spec, declared = _without_hand_written_spec(None)
    result, service = run(tmp_path, spec)
    certificate = result["formalism_certificate"]
    assert certificate["project_go"] is False and certificate["effective_decision"] != "GO"
    gates = {g["gate_id"]: g["status"] for g in certificate["gates"]}
    assert gates["V3"] != "PASS" and gates["PRICE_PRESENT"] != "PASS"
    canonical = load_canonical(result, service)
    assert _witnesses(canonical) == {}
    assert {c.tipo_id for c in canonical.contratos_recurso} == set(declared)  # per-resource contracts, unpriced
    warnings = " ".join(str(a) for skill in result["skills_log"] for a in (skill.get("avisos") or []))
    assert "UNKNOWN_CONTRACT" in warnings
