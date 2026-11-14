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


def test_profile_prices_the_exact_ledger_with_nothing_hand_written(tmp_path: Path) -> None:
    """No rcpsp_spec, no P18 flag, no P21 evidence: contract terms + the profile's
    declared pricing terms (N9) carry the project to an exact, attributable decision.

    With the Mendes Lobo layers (materials/diesel: 4% profit only) this materials-heavy
    scope prices below its composition-weighted floor and its profit layer is below the
    minimum: NOGO by V2 and PROFITABILITY only — an exact, layer-by-layer consequence of
    the declared terms, never a legacy estimate."""
    spec, _declared = _without_hand_written_spec(
        lambda t: {k: t[k] for k in ("mobilize", "demobilize", "max_idle_gap")}
    )
    spec["skill_inputs"]["06-resultado-financeiro"] = {}
    result, service = run(tmp_path, spec)
    certificate = result["formalism_certificate"]
    assert result["status"] == "OK"
    assert (certificate["effective_decision"], certificate["project_go"]) == ("NOGO", False)
    gates = {g["gate_id"]: g["status"] for g in certificate["gates"]}
    failing = {gate for gate, status in gates.items() if status != "PASS"}
    assert failing == {"V2", "REGULATORY_BDI_BASIS", "PROFITABILITY"}, gates

    canonical = load_canonical(result, service)
    diagnostics, pricing_gates = canonical.resultado.pricing_diagnostics, canonical.resultado.pricing_gates
    # Markups are the TCU formula over the profile's declared rows (EQ = services rate).
    assert {c: Fraction(diagnostics[f"bdi_rate_{c.lower()}"]) for c in ("MO", "EQ", "MAT", "COMB", "IND")} == {
        "MO": Fraction(270031, 902700),
        "EQ": Fraction(270031, 902700),
        "MAT": Fraction(1, 25),
        "COMB": Fraction(1, 25),
        "IND": Fraction(15133, 60180),
    }
    # Layers: the price is exactly cost + overhead + profit + taxes, per category and in total.
    layers = canonical.resultado.markup_layers
    total = layers["total"]
    price = Fraction(total["price"])
    assert price == Fraction(diagnostics["operational_price"])
    assert Fraction(total["cost"]) == Fraction(diagnostics["total_cost"])
    assert sum(Fraction(total[k]) for k in ("cost", "overhead", "profit", "tax_total")) == price
    for amounts in layers["by_category"].values():
        assert sum(Fraction(amounts[k]) for k in ("cost", "overhead", "profit", "tax_total")) == Fraction(
            amounts["price"]
        )
    # The minimum is a criterion on the profit layer's share of the price, not on (P - C)/P.
    share = Fraction(total["profit"]) / price
    assert Fraction(pricing_gates["profit_layer_share"]) == share < Fraction(3, 50)
    assert share < Fraction(pricing_gates["realized_margin"])  # (P - C)/P also holds overhead and taxes
    # Floors per category by nature (TCU 1st quartile: services 19.60%, mere supply 11.10%);
    # the V2 floor is their average weighted by the catalog composition.
    assert layers["bdi_floor_by_category"] == {
        "COMB": "111/1000",
        "EQ": "49/250",
        "IND": "49/250",
        "MAT": "111/1000",
        "MO": "49/250",
    }
    assert layers["bdi_below_category_floor"] == ["COMB", "MAT"]
    floor = Fraction(pricing_gates["regulatory_bdi_floor"])
    assert Fraction("0.1110") < floor < Fraction("0.1960")
    assert Fraction(pricing_gates["regulatory_bdi_rate"]) < floor
    # The independent oracles recompute cost, price and BDI from the same ledgers.
    report = differential_report(canonical, catalog(spec), certificate)
    assert report["first_divergence"] is None
