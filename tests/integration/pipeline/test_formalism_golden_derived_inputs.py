"""#206: a project reaches the exact ledgers from its own data plus declared contract terms.

The golden RFPs hand-write `rcpsp_spec` (team per front, pool, durations) and
`p16_exact_tariffs`. Here the same projects run with **neither**: Skill04 and
Skill05 derive the per-resource spec from the EAP, the catalog production
teams and the configured pool, and the P16 tariffs come from the catalog rate
plus the project's `contract_terms` declaration (N8). Without declared terms
nothing is estimated. All runs are `slow` (one pipeline run each).
"""

from __future__ import annotations

from datetime import date
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


NO_SITE_INDIRECTS = {
    "status": "NO_SITE_INDIRECTS",
    "source": "golden fixture: scope limited to plant operation; no site administration modelled",
    "reference_id": "golden-rfp-no-site-indirects",
    "fingerprint": "golden-rfp-site-indirects-v1",
}


def _iso_week(day: str) -> str:
    year, week, _ = date.fromisoformat(day).isocalendar()
    return f"{year}-W{week:02d}"


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
    assert report["unverified"] == [], report["unverified"]
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
    # The profile declares the pricing terms; the site-indirects scope is the project's own (N10).
    spec["skill_inputs"]["06-resultado-financeiro"] = {"site_indirects_scope": NO_SITE_INDIRECTS}
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


def test_profile_run_without_a_site_indirects_scope_is_not_priced(tmp_path: Path) -> None:
    """N10: the profile never supplies the site-indirects scope. Without the project's
    declaration there is no exact ledger and no price — never a total that omits them."""
    spec, _declared = _without_hand_written_spec(
        lambda t: {k: t[k] for k in ("mobilize", "demobilize", "max_idle_gap")}
    )
    spec["skill_inputs"]["06-resultado-financeiro"] = {}
    result, service = run(tmp_path, spec)
    certificate = result["formalism_certificate"]
    assert certificate["project_go"] is False and certificate["effective_decision"] != "GO"
    gates = {g["gate_id"]: g["status"] for g in certificate["gates"]}
    assert gates["FINANCIAL_COST_RECONCILIATION"] != "PASS" and gates["PRICE_PRESENT"] != "PASS", gates
    resultado = load_canonical(result, service).resultado
    assert resultado.pricing_gates["status"] == "UNKNOWN"
    assert "site_indirects_scope is required" in resultado.pricing_gates["reason"]
    assert "total_cost" not in resultado.pricing_diagnostics
    assert resultado.p20_financial_reconciliation is None


def test_declared_site_indirects_enter_the_exact_ledger_and_the_price(tmp_path: Path) -> None:
    """N10 positive: a declared site-administration line is posted week by week, priced by the
    layers of its own categories, replayed by P23 and recomputed by the independent oracle."""
    spec, _declared = _without_hand_written_spec(
        lambda t: {k: t[k] for k in ("mobilize", "demobilize", "max_idle_gap")}
    )
    window = {"first": _iso_week(spec["dates"]["data_inicio"]), "last": _iso_week(spec["dates"]["data_termino"])}
    site_indirects = {
        "schema": "concilium.n10.site-indirects.v1",
        "currency": "BRL",
        "source": "golden fixture: illustrative site administration, not calibrated data",
        "reference_id": "golden-rfp-site-indirects-declared",
        "mobilised_weeks": window,
        "lines": [
            {
                "line_id": "ADM",
                "driver": "perm",
                "source": "golden fixture line",
                # 14610/1461 = 10 -> 3360 per week of MO; VM 1461 -> 336 per week (IND).
                "monthly": {"MO": "14610", "EQ": "0", "COMB": "0", "VM": "1461"},
            },
            {
                "line_id": "MOB_SITE",
                "driver": "onetime",
                "source": "golden fixture line",
                "mobilize": "5000",
                "demobilize": "2500",
            },
        ],
    }
    spec["skill_inputs"]["06-resultado-financeiro"] = {
        "site_indirects_scope": {**NO_SITE_INDIRECTS, "status": "DECLARED", "reference_id": "golden-rfp-site-declared"},
        "site_indirects": site_indirects,
    }
    result, service = run(tmp_path, spec)
    assert result["status"] == "OK"
    certificate = result["formalism_certificate"]
    gates = {g["gate_id"]: g["status"] for g in certificate["gates"]}
    assert gates["FINANCIAL_COST_RECONCILIATION"] == "PASS" and gates["PRICE_PRESENT"] == "PASS", gates

    canonical = load_canonical(result, service)
    resultado = canonical.resultado
    ledger = resultado.p20_financial_reconciliation
    weeks = ledger["site_indirects"]["mobilised_weeks"]
    assert (weeks[0], weeks[-1]) == (window["first"], window["last"])
    site_cost = len(weeks) * Fraction(3360 + 336) + 7500
    assert Fraction(resultado.pricing_diagnostics["site_indirects_cost"]) == site_cost
    site_rows = [row for row in ledger["postings"] if row["event_id"][0] == "SITE_INDIRECT"]
    assert sum(Fraction(row["amount"]) for row in site_rows) == site_cost
    other = sum(Fraction(row["amount"]) for row in ledger["postings"] if row["event_id"][0] != "SITE_INDIRECT")
    total_cost = Fraction(resultado.pricing_diagnostics["total_cost"])
    assert Fraction(ledger["totals"]["total"]) == other + site_cost == total_cost
    assert Fraction(ledger["totals"]["direct"]) == sum(
        Fraction(row["amount"])
        for row in ledger["postings"]
        if row["nature"] in ("CONTRACTUAL_ACTIVE", "CONTRACTUAL_IDLE", "CONSUMABLE_ACQUISITION")
    )
    # Markup layers rebuild cost and price, with site labour in the MO layers.
    layers = resultado.markup_layers
    total = layers["total"]
    assert Fraction(total["cost"]) == Fraction(resultado.pricing_diagnostics["total_cost"])
    assert Fraction(total["price"]) == Fraction(resultado.pricing_diagnostics["operational_price"])
    assert sum(Fraction(total[k]) for k in ("cost", "overhead", "profit", "tax_total")) == Fraction(total["price"])
    site_mo = len(weeks) * Fraction(3360)
    pool_mo = sum(
        Fraction(row["amount"]) for row in ledger["postings"]
        if row["category"] == "MO" and row["event_id"][0] != "SITE_INDIRECT"
    )
    assert Fraction(layers["by_category"]["MO"]["cost"]) == pool_mo + site_mo

    report = differential_report(canonical, catalog(spec), certificate, site_indirects)
    assert report["first_divergence"] is None, report["first_divergence"]
    assert report["unverified"] == [], report["unverified"]
    site_checks = [c for c in report["checks"] if c.check.startswith("site indirect")]
    assert len(site_checks) == 3 and all(c.status == "MATCH" for c in site_checks), site_checks
    # Without the declaration the differential cannot vouch for a DECLARED run.
    blind = differential_report(canonical, catalog(spec), certificate)
    assert any(c.check == "site indirects" and c.status == "UNVERIFIED" for c in blind["unverified"])
