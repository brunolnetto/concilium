"""#206: the per-resource rcpsp_spec is derived from the project's own data."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from concilium.application.scheduling.exact_rcpsp_derivation import derive_exact_rcpsp_spec
from tests.support.golden_pipeline import SCENARIO_FILES, catalog, scenario


def _canonical(spec: dict, pool: list[dict] | None = None) -> SimpleNamespace:
    dates = spec["dates"]
    rows = spec["skill_inputs"]["03-catalogo-de-recursos"]["pool_inicial"] if pool is None else pool
    return SimpleNamespace(
        projeto=SimpleNamespace(
            regime_trabalho=SimpleNamespace(dias_semana=dates["dias_semana"], horas_dia=dates["horas_dia"])
        ),
        eap=[
            SimpleNamespace(
                item_id=i["item_id"], cpu_id=i["cpu_id"], quantitativo=i["quantitativo"], descricao=i["descricao"]
            )
            for i in spec["eap"]
        ],
        recurso_pool=[
            SimpleNamespace(
                tipo_id=r["tipo_id"],
                quantidade_total=r["quantidade_total"],
                proveniencia=r.get("proveniencia", "CONFIGURADO"),
            )
            for r in rows
        ],
    )


@pytest.mark.parametrize("name", sorted(SCENARIO_FILES))
def test_derived_spec_equals_the_hand_written_golden_spec(name: str) -> None:
    """What the golden fixtures declare by hand is exactly what the project data implies."""
    spec = scenario(name)
    declared = spec["skill_inputs"]["04-cronograma"]["rcpsp_spec"]
    derived, reasons = derive_exact_rcpsp_spec(_canonical(spec), catalog(spec))
    assert reasons == [] and derived is not None
    assert {a["item_id"]: a["required_resources"] for a in derived["activities"]} == {
        a["item_id"]: a["required_resources"] for a in declared["activities"]
    }
    assert {a["item_id"]: a["duration_weeks"] for a in derived["activities"]} == {
        a["item_id"]: a["duration_weeks"] for a in declared["activities"]
    }
    assert derived["resource_pool"] == declared["resource_pool"]


def test_nothing_is_inferred_when_data_is_missing() -> None:
    spec = scenario("single_plant_sequence")
    cat = catalog(spec)

    derived, reasons = derive_exact_rcpsp_spec(_canonical(spec, pool=[]), cat)
    assert derived is None and any("configured physical pool" in r for r in reasons)

    synthetic = [
        {**r, "proveniencia": "DERIVADO_SKILL05"}
        for r in spec["skill_inputs"]["03-catalogo-de-recursos"]["pool_inicial"]
    ]
    derived, reasons = derive_exact_rcpsp_spec(_canonical(spec, pool=synthetic), cat)
    assert derived is None, "synthetic allocations are not a physical pool"

    short = [dict(r, quantidade_total=1) for r in spec["skill_inputs"]["03-catalogo-de-recursos"]["pool_inicial"]]
    derived, reasons = derive_exact_rcpsp_spec(_canonical(spec, pool=short), cat)
    assert derived is None and any("does not cover one front" in r for r in reasons)

    broken = dict(cat, producoes=[])
    derived, reasons = derive_exact_rcpsp_spec(_canonical(spec), broken)
    assert derived is None and all("no production record" in r for r in reasons)

    canonical = _canonical(spec)
    canonical.eap[0].cpu_id = "CPU-UNKNOWN"
    derived, reasons = derive_exact_rcpsp_spec(canonical, cat)
    assert derived is None and "absent from the catalog" in reasons[0]


VECTORS = json.loads(
    (Path(__file__).resolve().parents[3] / "reference_formalism/vectors/pool_spec_from_project_v1.json").read_text(
        encoding="utf-8"
    )
)["vectors"]


@pytest.mark.parametrize("case", VECTORS, ids=lambda c: c["case_id"])
def test_production_matches_the_pool_spec_oracle_vector(case: dict) -> None:
    data = case["case"]
    canonical = SimpleNamespace(
        projeto=SimpleNamespace(
            regime_trabalho=SimpleNamespace(dias_semana=data["dias_semana"], horas_dia=data["horas_dia"])
        ),
        eap=[
            SimpleNamespace(item_id=a["id"], cpu_id=f"CPU-{a['id']}", quantitativo=a["Q"], descricao=a["id"])
            for a in data["activities"]
        ],
        recurso_pool=[
            SimpleNamespace(tipo_id=g, quantidade_total=n, proveniencia="CONFIGURADO")
            for g, n in (data.get("configured_pool") or {}).items()
        ],
    )
    catalogo = {
        "cpus": [{"codigo": f"CPU-{a['id']}", "producao_id_ref": f"P-{a['id']}"} for a in data["activities"]],
        "producoes": [
            {
                "id": f"P-{a['id']}",
                "producao_horaria": a["rho"],
                "composicao_padrao_equipe": {
                    "equipamentos": [{"equip_id": g, "num_unidades": n} for g, n in a["team"].items()],
                    "funcoes": [],
                },
            }
            for a in data["activities"]
        ],
    }
    derived, reasons = derive_exact_rcpsp_spec(canonical, catalogo)
    if "expected_error" in case:
        assert derived is None and any(case["expected_error"].split()[-1] in r or "pool" in r for r in reasons)
        return
    assert reasons == [] and derived is not None
    observed = {
        "activities": {
            a["item_id"]: {"duration_weeks": a["duration_weeks"], "required_resources": a["required_resources"]}
            for a in derived["activities"]
        },
        "resource_pool": derived["resource_pool"],
    }
    assert observed == case["expected"]
