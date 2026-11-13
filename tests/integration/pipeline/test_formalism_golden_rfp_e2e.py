"""#23 criterion 1: a golden RFP reaches a traceable GO through the real pipeline.

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

ROOT = Path(__file__).resolve().parents[3]
CONFIG = ROOT / "config"
SPEC = json.loads((ROOT / "tests/fixtures/formalism_golden_rfp/spec.json").read_text(encoding="utf-8"))
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


def _run(tmp_path: Path, spec: dict) -> tuple[dict, ConciliumService]:
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
        procurement_intent="rfp",
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


@pytest.fixture(scope="module")
def golden(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, ConciliumService]:
    return _run(tmp_path_factory.mktemp("golden"), SPEC)


def test_declared_bdi_basis_is_the_oracle_catalog_envelope() -> None:
    evidence = SPEC["skill_inputs"]["06-resultado-financeiro"]["p21_pricing_evidence"]
    expected = _oracle_c_cat(SPEC)
    assert evidence["catalog"]["amount"] == expected
    assert evidence["regulatory_basis"]["amount"] == expected


def test_golden_rfp_is_a_clean_current_go(golden) -> None:
    run, _service = golden
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


def test_golden_fronts_never_exceed_contracted_resources(golden) -> None:
    """No fictitious capacity (#24): for every activity, resource and week the
    scheduled fronts times the team's units per front equal the P16 demand
    (a_ig(m) = m a_ig^front; d_gj = sum_i a_ig(m_ij)). Regression for fronts once
    being the SUM of heterogeneous units (7 and 10 'fronts' on one plant)."""
    run, service = golden
    project = service._dependencies.repository.get_project(run["project_id"])
    canonical = project.load_canonical(run["version"])
    catalog = _catalog(SPEC)
    cpus = {c["codigo"]: c for c in catalog["cpus"]}
    productions = {p["id"]: p for p in catalog["producoes"]}
    eap = {item.item_id: item for item in canonical.eap}
    expected: dict[tuple[str, str], int] = {}
    for activity in canonical.cronograma.scheduled_activities:
        production = productions[cpus[eap[activity.activity_id].cpu_id]["producao_id_ref"]]
        team = production["composicao_padrao_equipe"]
        per_front = {r["equip_id"]: r["num_unidades"] for r in team["equipamentos"]}
        per_front |= {r["funcao_id"]: r["num_pessoas"] for r in team["funcoes"]}
        for week, cell in activity.distribuicao_semanal.items():
            assert cell.num_equipes >= 1 and cell.qtd_executada >= 0
            for resource, units in per_front.items():
                expected[(resource, week)] = expected.get((resource, week), 0) + cell.num_equipes * units
    observed: dict[tuple[str, str], int] = {}
    for contract in canonical.contratos_recurso:
        witness = contract.p16_global_assignment
        for week, demand in zip(witness["calendar_weeks"], witness["demand"], strict=True):
            observed[(contract.tipo_id, week)] = observed.get((contract.tipo_id, week), 0) + demand
    assert {k: v for k, v in expected.items() if v} == {k: v for k, v in observed.items() if v}


def test_golden_go_is_invalidated_by_a_post_issuance_source_mutation(golden) -> None:
    run, service = golden
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
