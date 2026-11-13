"""#23/#24: golden RFPs reach a traceable GO through the real pipeline and match independent oracles.

The project is run end to end by PipelineService (skills 01–09, RFP) on the
fixture in tests/fixtures/formalism_golden_rfp/spec.json. The GO test runs in
the default (fast) profile as the certification regression guard; the
falsifiers re-run the pipeline once each and are marked slow.
"""

from __future__ import annotations

import copy
import json
from fractions import Fraction
from pathlib import Path

import pytest

from concilium.application.runtime import Runtime
from concilium.application.services.concilium_service import ConciliumDependencies, ConciliumService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project.audit_service import AuditService
from concilium.application.services.project.override_service import OverrideService
from concilium.application.services.project.project_input_builder import ProjectInputBuilder
from concilium.application.services.project.project_service import ProjectService
from concilium.infrastructure.storage.store_factory import build_project_repository
from concilium.presentation.api.schemas import CreateProjectRequest
from tests.reference_formalism.catalog_envelope_reference import evaluate_catalog_envelope
from tests.support.golden_differential import PHASES, differential_report

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config"
FIXTURES = ROOT / "tests/fixtures/formalism_golden_rfp"
SCENARIOS = {
    "single_plant_sequence": json.loads((FIXTURES / "spec.json").read_text(encoding="utf-8")),
    "sharing_theta_standby_remob": json.loads((FIXTURES / "spec_sharing.json").read_text(encoding="utf-8")),
}
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
    catalog = copy.deepcopy(Runtime(CONFIG).load_catalogo(spec["contexto_id"]))
    catalog["cpus"] = list(catalog["cpus"]) + spec["fixture_cpus"]
    return catalog


def _run(tmp_path: Path, spec: dict, intent: str = "rfp") -> tuple[dict, ConciliumService]:
    repository = build_project_repository(tmp_path / "projetos")
    audit = AuditService()
    pipeline = PipelineService(repository, audit, runtime_factory=lambda: Runtime(CONFIG))
    service = ConciliumService(
        ConciliumDependencies(
            input_builder=ProjectInputBuilder(CONFIG, ROOT / "benchmarks" / "data"),
            repository=repository,
            project_service=ProjectService(repository, audit),
            override_service=OverrideService(repository, audit),
            pipeline_service=pipeline,
            audit_service=audit,
            benchmarks_root=ROOT / "benchmarks" / "data",
        )
    )
    request = CreateProjectRequest(
        nome=spec["nome"],
        contexto_id=spec["contexto_id"],
        eap=[{k: v for k, v in item.items() if k != "predecessores"} for item in spec["eap"]],
        **spec["dates"],
    )
    project_id = service.create_project(request, actor="golden-e2e")["project_id"]
    service.upsert_eap(project_id, spec["eap"], actor="golden-e2e")
    repository.get_project(project_id).write_json("benchmark_reference.json", {"catalog": _catalog(spec)})
    run = pipeline.run_project(
        project_id,
        base_version=None,
        fork_version=False,
        procurement_intent=intent,
        skill_inputs_override=spec["skill_inputs"],
        use_saved_overrides=True,
        use_mobilizacao_policy=True,
        use_strict_catalog_baseline=True,
        actor="golden-e2e",
    )
    return run, service


def _oracle_c_cat(spec: dict) -> str:
    """C^cat from the raw catalog records with the independent stdlib oracle."""
    catalog = _catalog(spec)
    cpus = {c["codigo"]: c for c in catalog["cpus"]}
    productions = {p["id"]: p for p in catalog["producoes"]}
    insumos = {i["codigo"]: i for i in catalog["insumos"]}

    def q(value: object) -> str:
        return str(Fraction(str(value)))

    activities = []
    for item in spec["eap"]:
        cpu = cpus[item["cpu_id"]]
        production = productions[cpu["producao_id_ref"]]
        team = production["composicao_padrao_equipe"]
        contractual = [
            {
                "id": r["equip_id"],
                "cat": "EQ",
                "price": q(insumos[r["equip_id"]]["preco_unitario"]),
                "price_unit": insumos[r["equip_id"]]["unidade"],
                "n": r["num_unidades"],
            }
            for r in team["equipamentos"]
        ] + [
            {
                "id": r["funcao_id"],
                "cat": "MO",
                "price": q(insumos[r["funcao_id"]]["preco_unitario"]),
                "price_unit": insumos[r["funcao_id"]]["unidade"],
                "n": r["num_pessoas"],
            }
            for r in team["funcoes"]
        ]
        consumables = [
            {
                "id": r["insumo_id"],
                "coef": q(r["coeficiente"]),
                "price": q(insumos[r["insumo_id"]]["preco_unitario"]),
                "unit": r.get("unidade", ""),
            }
            for r in cpu["composicao_itens"]
        ]
        activities.append(
            {
                "id": item["item_id"],
                "Q": q(item["quantitativo"]),
                "rho": q(production["producao_horaria"]),
                "unit": cpu["unidade"],
                "contractual": contractual,
                "consumables": consumables,
            }
        )
    dates = spec["dates"]
    case = {
        "inputs": {
            "regime": {"d": dates["dias_semana"], "h": dates["horas_dia"]},
            "s_mes": "1461/336",
            "activities": activities,
        }
    }
    return evaluate_catalog_envelope(case)["total"]


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
    project = service._dependencies.repository.get_project(run["project_id"])
    canonical = project.load_canonical(run["version"])
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


@pytest.mark.parametrize(
    ("phase", "corrupt"),
    [
        ("PHYSICAL", lambda c: _first_cell(c).__setattr__("qtd_executada", 1.0)),
        ("CONSUMPTION", lambda c: c.p18_consumption_preview["evidence"][0].__setitem__("exact_cost", "1")),
        ("PRICE", lambda c: c.resultado.pricing_diagnostics.__setitem__("operational_price", "1")),
    ],
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


def _falsified(mutate) -> dict:
    spec = copy.deepcopy(SPEC)
    mutate(spec)
    return spec


@pytest.mark.slow
@pytest.mark.parametrize(
    ("label", "mutate", "gate", "decision"),
    [
        (
            "V2: markup too low for the regulatory floor over C^cat",
            lambda s: s["skill_inputs"]["06-resultado-financeiro"]["p21_pricing_evidence"].update(
                bdi_by_category={k: "1/10" for k in ("MO", "EQ", "MAT", "COMB", "IND")}
            ),
            "V2",
            "NOGO",
        ),
        (
            "V1: calendar too short to close the physical scope",
            lambda s: s["dates"].update(data_termino="2026-05-24"),
            "V1", "NOGO",
        ),
        (
            "V3: P16 exact tariffs withheld",
            lambda s: s["skill_inputs"]["05-equipes-e-alocacao"]["rcpsp_spec"].pop("p16_exact_tariffs"),
            # Without P16 there is no exact ledger, so P21 cannot build the RFP
            # regulatory basis either; a missing RFP basis is a FAIL by contract.
            "V3",
            "NOGO",
        ),
        (
            "V5: activity bound to an uncalibrated production",
            lambda s: s["fixture_cpus"][0].update(producao_id_ref="CPU-PAVIM-PAV-BASE-BGTC-PROD-001"),
            "V5",
            None,
        ),
        (
            "V2: declared basis differs from derived C^cat",
            lambda s: s["skill_inputs"]["06-resultado-financeiro"]["p21_pricing_evidence"]["regulatory_basis"].update(
                amount="1"
            ),
            "V2",
            None,
        ),
    ],
    ids=lambda v: v if isinstance(v, str) and ":" in v else None,
)
def test_falsified_golden_is_never_go(tmp_path: Path, label: str, mutate, gate: str, decision: str | None) -> None:
    run, _service = _run(tmp_path, _falsified(mutate))
    certificate = run["formalism_certificate"]
    assert certificate["project_go"] is False, label
    assert certificate["effective_decision"] != "GO", label
    if decision is not None:
        assert certificate["effective_decision"] == decision, (label, certificate["reasons"])
    gates = {g["gate_id"]: g["status"] for g in certificate.get("gates", [])}
    assert gates.get(gate) != "PASS", (label, gates)


@pytest.mark.slow
def test_rfi_run_of_the_golden_project_is_never_an_rfp_certificate(tmp_path: Path) -> None:
    """#24: an RFI (skills 01-06) is never reported as a complete RFP 01-09 certification."""
    run, _service = _run(tmp_path, SPEC, intent="rfi")
    certificate = run["formalism_certificate"]
    assert certificate["project_go"] is False
    assert certificate["effective_decision"] != "GO"
    assert certificate.get("scope") in (None, "RFI", "PREVIEW")
