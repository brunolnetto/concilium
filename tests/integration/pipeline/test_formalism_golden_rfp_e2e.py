"""#23/#24: golden RFPs reach a traceable GO through the real pipeline and match independent oracles.

The project is run end to end by PipelineService (skills 01–09, RFP) on the
fixtures in tests/fixtures/formalism_golden_rfp/ with every source pinned
(tests/support/golden_pipeline.py, including the climate snapshot). The GO test runs in
the default (fast) profile as the certification regression guard; the
falsifiers re-run the pipeline once each and are marked slow.
"""

from __future__ import annotations

import copy
from fractions import Fraction
from pathlib import Path

import pytest

from tests.support.golden_differential import PHASES, differential_report
from tests.support.golden_pipeline import SCENARIO_FILES, catalog, load_canonical, oracle_c_cat, scenario
from tests.support.golden_pipeline import run as _pipeline_run

SCENARIOS = {name: scenario(name) for name in SCENARIO_FILES}
SPEC = SCENARIOS["single_plant_sequence"]
GATES = (
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "FINANCIAL_COST_RECONCILIATION",
    "PRICE_PRESENT",
    "REGULATORY_BDI_BASIS",
    "PROFITABILITY",
    "PRODUCTIVITY_PROVENANCE",
)


def _catalog(spec: dict) -> dict:
    return catalog(spec)


def _run(tmp_path: Path, spec: dict, intent: str = "rfp"):
    return _pipeline_run(tmp_path, spec, intent=intent)


def _oracle_c_cat(spec: dict) -> str:
    return oracle_c_cat(spec)


@pytest.fixture(scope="module", params=sorted(SCENARIOS))
def golden(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory):
    spec = SCENARIOS[request.param]
    run, service = _run(tmp_path_factory.mktemp(request.param), spec)
    return run, service, spec


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_declared_bdi_basis_is_the_oracle_catalog_envelope(scenario: str) -> None:
    spec = SCENARIOS[scenario]
    evidence = spec["skill_inputs"]["06-resultado-financeiro"]["p21_pricing_evidence"]
    expected = _oracle_c_cat(spec)
    assert evidence["catalog"]["amount"] == expected
    assert evidence["regulatory_basis"]["amount"] == expected


def test_golden_rfp_is_a_clean_current_go(golden) -> None:
    run, _service, _spec = golden
    assert run["status"] == "OK", run.get("error")
    assert all(s["status"] == "OK" for s in run["skills_log"]), run["skills_log"]
    certificate = run["formalism_certificate"]
    assert (certificate["status"], certificate["effective_decision"], certificate["project_go"]) == (
        "CURRENT",
        "GO",
        True,
    )
    assert certificate["scope"] == "RFP"
    assert certificate["reasons"] == []
    assert [(g["gate_id"], g["status"]) for g in certificate["gates"]] == [(g, "PASS") for g in GATES]


def _first_cell(canonical):
    return next(iter(canonical.cronograma.scheduled_activities[0].distribuicao_semanal.values()))


def _differential(golden):
    run, service, spec = golden
    canonical = load_canonical(run, service)
    return canonical, differential_report(canonical, _catalog(spec), run["formalism_certificate"])


def test_golden_fronts_never_exceed_contracted_resources(golden) -> None:
    """No fictitious capacity (#24): m_ij * a_ig^front equals the P16 demand for every
    resource and week. Regression for fronts once being the SUM of heterogeneous units
    (7 and 10 'fronts' on one plant)."""
    _canonical, report = _differential(golden)
    demand = [c for c in report["checks"] if c.check.endswith("demand = m * a^front")]
    assert demand and all(c.status == "MATCH" for c in demand), [c for c in demand if c.status != "MATCH"][:3]


def test_golden_matches_independent_oracles_in_every_phase(golden) -> None:
    """#24 P24-A: every mandatory phase of the real run is recomputed by independent
    oracles; nothing diverges and nothing is left unverified."""
    _canonical, report = _differential(golden)
    assert report["first_divergence"] is None, report["first_divergence"]
    assert report["unverified"] == []
    assert report["summary"] == {phase: ["MATCH"] for phase in PHASES}


def _duplicate_pool_cost(canonical) -> None:
    """Cost duplication: a P16 contract books its pool total twice."""
    costs = canonical.contratos_recurso[0].p16_global_assignment["costs"]
    for key, value in list(costs.items()):
        costs[key] = str(2 * Fraction(str(value)))


def _duplicate_ledger_row(canonical) -> None:
    """Unexplained currency delta: one P20 weekly balance is posted twice."""
    rows = canonical.resultado.p20_financial_reconciliation["weekly_category_balances"]
    rows.append(dict(rows[0]))


@pytest.mark.parametrize(
    ("phase", "corrupt"),
    [
        ("PHYSICAL", lambda c: _first_cell(c).__setattr__("qtd_executada", 1.0)),
        ("POOL", _duplicate_pool_cost),
        ("CONSUMPTION", lambda c: c.p18_consumption_preview["evidence"][0].__setitem__("exact_cost", "1")),
        ("CATALOG", lambda c: c.resultado.pricing_diagnostics.__setitem__("catalog_benchmark", "1")),
        ("PRICE", lambda c: c.resultado.pricing_diagnostics.__setitem__("operational_price", "1")),
        ("PRICE", _duplicate_ledger_row),
    ],
    ids=["physical", "pool-duplicated-cost", "consumption", "catalog", "price", "price-currency-delta"],
)
def test_differential_reports_the_first_divergent_phase(golden, phase: str, corrupt) -> None:
    """A deliberately corrupted phase is reported as the FIRST divergence, with both values."""
    canonical, _report = _differential(golden)
    tampered = canonical.model_copy(deep=True)
    corrupt(tampered)
    report = differential_report(tampered, _catalog(golden[2]), golden[0]["formalism_certificate"])
    first = report["first_divergence"]
    assert first is not None and first.phase == phase, first
    assert first.pipeline != first.oracle


def test_golden_go_is_invalidated_by_a_post_issuance_source_mutation(golden) -> None:
    run, service, _spec = golden
    deps = service._dependencies
    project = deps.repository.get_project(run["project_id"])
    version = run["version"]
    canonical = project.load_canonical(version)
    mutated = canonical.model_copy(
        update={
            "eap": [
                item.model_copy(update={"quantitativo": item.quantitativo + 1}) if i == 0 else item
                for i, item in enumerate(canonical.eap)
            ]
        }
    )
    project.save_canonical(mutated, version)
    current = deps.pipeline_service.get_run(run["project_id"], run["run_id"])["formalism_certificate"]
    assert current["status"] == "INVALIDATED"
    assert (current["effective_decision"], current["project_go"]) == ("NOT_CERTIFIABLE", False)
    assert current["recorded_decision"] == "GO"


def _falsified(mutate, scenario_name: str = "single_plant_sequence") -> dict:
    spec = copy.deepcopy(SCENARIOS[scenario_name])
    mutate(spec)
    return spec


def _p21(spec: dict) -> dict:
    return spec["skill_inputs"]["06-resultado-financeiro"]["p21_pricing_evidence"]


_CATEGORIES = ("MO", "EQ", "MAT", "COMB", "IND")


def _layers(ac: str, profit: str, markup: str | None):
    """Redeclare the markup layers of every category (AC and profit L; R+S+G, DF and
    taxes stay 0). ``markup`` is the declared consequence ``bdi_by_category``, which
    must equal (1 + AC)(1 + L) - 1; ``None`` leaves the fixture's 3/10 untouched."""

    def mutate(spec: dict) -> None:
        evidence = _p21(spec)
        evidence["markup_layers"] = {
            category: {"ac": ac, "rsg": "0", "df": "0", "l": profit, "taxes": {}} for category in _CATEGORIES
        }
        if markup is not None:
            evidence["bdi_by_category"] = dict.fromkeys(_CATEGORIES, markup)

    return mutate


# Golden layers: AC 1/10, L 2/11 -> markup 3/10, profit layer 2/13 of the price.
#
# V2 falsifier: no overhead, L 1/10 -> markup 1/10. The price is P20 cost * 11/10,
# below the 1/5 floor over C^cat; the profit layer is (1/10)/(11/10) = 1/11 of the
# price >= 1/20, so PROFITABILITY still passes and the NOGO is V2's alone.
_MARKUP_ONE_TENTH = _layers("0", "1/10", "1/10")
# Negative layer: L = -1 would give P = 0 <= C_tot. bdi_by_category stays the
# valid 3/10, so the refusal is the negative layer rate itself.
_NEGATIVE_PROFIT_LAYER = _layers("0.10", "-1", None)
# PROFITABILITY falsifier: AC 1/4, L 1/25 -> (5/4)(26/25) = 13/10, the SAME markup
# 3/10 as the golden run. Price, P20 cost and BDI over C^cat are therefore the
# golden ones (V2 passes with the same margin over the 1/5 floor), and
# (P - C)/P = 3/13 ~ 23.1% would clear the 1/20 minimum. The profit layer is
# C * 5/4 * 1/25 = C/20 of a price 13C/10: share (1/20)/(13/10) = 1/26 ~ 3.85%
# < 1/20. All categories share the layers, so the share is 1/26 whatever the cost
# mix. Only the profit-layer criterion fails.
_THIN_PROFIT_LAYER_AT_THE_GOLDEN_MARKUP = _layers("0.25", "0.04", None)


# (label, scenario, mutation, gate that must not PASS, expected decision or None,
#  gates that must still PASS so the falsifier is attributed to its own gate)
FALSIFIERS = [
    (
        "V2: markup too low for the regulatory floor over C^cat",
        "single_plant_sequence",
        _MARKUP_ONE_TENTH,
        "V2",
        "NOGO",
        ("V1", "V3", "V4", "V5", "V6", "PRICE_PRESENT", "FINANCIAL_COST_RECONCILIATION", "PROFITABILITY"),
    ),
    (
        "V1: calendar too short to close the physical scope",
        "single_plant_sequence",
        lambda s: s["dates"].update(data_termino="2026-05-24"),
        "V1",
        "NOGO",
        (),
    ),
    # Without P16 there is no exact ledger, so P21 cannot build the RFP regulatory
    # basis either; a missing RFP basis is a FAIL by contract.
    (
        "V3: P16 exact tariffs withheld",
        "single_plant_sequence",
        lambda s: s["skill_inputs"]["05-equipes-e-alocacao"]["rcpsp_spec"].pop("p16_exact_tariffs"),
        "V3",
        "NOGO",
        (),
    ),
    (
        "V5: activity bound to an uncalibrated production",
        "single_plant_sequence",
        lambda s: s["fixture_cpus"][0].update(producao_id_ref="CPU-PAVIM-PAV-BASE-BGTC-PROD-001"),
        "V5",
        None,
        (),
    ),
    (
        "V2: declared basis differs from derived C^cat",
        "single_plant_sequence",
        lambda s: _p21(s)["regulatory_basis"].update(amount="1"),
        "V2",
        None,
        (),
    ),
    # P21 refuses negative layer rates, so P <= C_tot (and P <= 0) cannot be
    # priced at all: no operational price is published.
    (
        "V4/PRICE: negative profit layer (P <= C_tot) is refused, no price",
        "single_plant_sequence",
        _NEGATIVE_PROFIT_LAYER,
        "PRICE_PRESENT",
        "NOGO",
        (),
    ),
    # N9: layers are mandatory. A flat bdi_by_category (here the golden 3/10, which
    # priced a GO before layers were required) is not a price declaration: Skill06
    # builds no evidence, nothing is priced and the run is never GO.
    (
        "PRICE: flat markup without declared layers is not priced",
        "single_plant_sequence",
        lambda s: _p21(s).pop("markup_layers"),
        "PRICE_PRESENT",
        "NOGO",
        ("V1", "V3", "V5", "V6"),
    ),
    (
        "V6: RCPSP conflict, pool smaller than the team",
        "single_plant_sequence",
        lambda s: s["skill_inputs"]["04-cronograma"]["rcpsp_spec"]["resource_pool"].update(
            {"EQ-CARREG-PNEUS-340M3": 1}
        ),
        "V6",
        "NOGO",
        (),
    ),
    # N10: the site-indirects scope is never assumed. Without it Skill06 builds no
    # exact ledger, so nothing is priced and the financial gates cannot pass.
    (
        "FINANCIAL_COST_RECONCILIATION: site-indirects scope withheld",
        "single_plant_sequence",
        lambda s: _p21(s).pop("site_indirects_scope"),
        "FINANCIAL_COST_RECONCILIATION",
        None,
        ("V1", "V3", "V5", "V6"),
    ),
    (
        "FINANCIAL_COST_RECONCILIATION: DECLARED site-indirects scope without lines",
        "single_plant_sequence",
        lambda s: _p21(s)["site_indirects_scope"].update(status="DECLARED"),
        "FINANCIAL_COST_RECONCILIATION",
        None,
        ("V1", "V3", "V5", "V6"),
    ),
    (
        "PROFITABILITY: BDI above the floor but profit layer below the minimum",
        "sharing_theta_standby_remob",
        _THIN_PROFIT_LAYER_AT_THE_GOLDEN_MARKUP,
        "PROFITABILITY",
        "NOGO",
        ("V1", "V2", "V3", "V4", "V5", "V6", "REGULATORY_BDI_BASIS", "PRICE_PRESENT", "FINANCIAL_COST_RECONCILIATION"),
    ),
]


@pytest.mark.slow
@pytest.mark.parametrize(
    ("label", "scenario_name", "mutate", "gate", "decision", "still_pass"),
    FALSIFIERS,
    ids=[f[0].split(":")[0] + "-" + str(i) for i, f in enumerate(FALSIFIERS)],
)
def test_falsified_golden_is_never_go(
    tmp_path: Path, label: str, scenario_name: str, mutate, gate: str, decision: str | None, still_pass: tuple
) -> None:
    run, _service = _run(tmp_path, _falsified(mutate, scenario_name))
    certificate = run["formalism_certificate"]
    assert certificate["project_go"] is False, label
    assert certificate["effective_decision"] != "GO", label
    if decision is not None:
        assert certificate["effective_decision"] == decision, (label, certificate["reasons"])
    gates = {g["gate_id"]: g["status"] for g in certificate.get("gates", [])}
    assert gates.get(gate) != "PASS", (label, gates)
    assert any(r.startswith(f"{gate}:") for r in certificate["reasons"]), (label, certificate["reasons"])
    assert {g: gates.get(g) for g in still_pass} == dict.fromkeys(still_pass, "PASS"), (label, gates)


@pytest.mark.slow
def test_missing_catalog_cost_names_the_unpriced_input(tmp_path: Path) -> None:
    """#24: an unpriced input never falls through as GO, and the failure names it."""
    spec = _falsified(lambda s: s.update(catalog_patches={"insumos": {"MA-BRITA-1": {"preco_unitario": None}}}))
    run, _service = _run(tmp_path, spec)
    certificate = run["formalism_certificate"]
    assert (certificate["project_go"], certificate["effective_decision"]) == (False, "NOGO")
    gates = {g["gate_id"]: g["status"] for g in certificate["gates"]}
    assert gates["PRICE_PRESENT"] == "FAIL", gates
    errors = " ".join(
        str(skill.get("erros") or skill.get("erro")) for skill in run["skills_log"] if skill.get("status") != "OK"
    )
    assert "eap-01/MA-BRITA-1" in errors, errors


@pytest.mark.slow
def test_rfi_run_of_the_golden_project_is_never_an_rfp_certificate(tmp_path: Path) -> None:
    """#24: an RFI (skills 01-06) is never reported as a complete RFP 01-09 certification."""
    run, _service = _run(tmp_path, SPEC, intent="rfi")
    certificate = run["formalism_certificate"]
    assert certificate["project_go"] is False
    assert certificate["effective_decision"] != "GO"
    assert certificate.get("scope") in (None, "RFI", "PREVIEW")
