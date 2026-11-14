"""Pinned, offline runs of the golden RFP projects through the real pipeline (#24).

Every external source a golden run reads is a versioned fixture: the project
spec, the fixture CPUs added to the resolved catalog, and the climate snapshot
served in place of the Open-Meteo network client. A run that asks the climate
client for anything other than the pinned snapshot fails instead of silently
reaching the network.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from typing import Any
from unittest.mock import patch

from concilium.application.runtime import Runtime
from concilium.application.services.concilium_service import ConciliumDependencies, ConciliumService
from concilium.application.services.pipeline_service import PipelineService
from concilium.application.services.project.audit_service import AuditService
from concilium.application.services.project.override_service import OverrideService
from concilium.application.services.project.project_input_builder import ProjectInputBuilder
from concilium.application.services.project.project_service import ProjectService
from concilium.infrastructure.clients.openmeteo import DadosClimaticosMensais, OpenMeteoClient
from concilium.infrastructure.storage.store_factory import build_project_repository
from concilium.presentation.api.schemas import CreateProjectRequest
from tests.reference_formalism.catalog_envelope_reference import evaluate_catalog_envelope

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config"
FIXTURES = ROOT / "tests/fixtures/formalism_golden_rfp"
SCENARIO_FILES = {
    "single_plant_sequence": "spec.json",
    "sharing_theta_standby_remob": "spec_sharing.json",
}


def scenario(name: str) -> dict[str, Any]:
    """A fresh copy of a versioned golden spec (safe to mutate)."""
    return json.loads((FIXTURES / SCENARIO_FILES[name]).read_text(encoding="utf-8"))


def climate_snapshot(spec: dict[str, Any]) -> dict[str, Any]:
    raw = json.loads((FIXTURES / spec["climate_snapshot"]).read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("$")}


@contextmanager
def pinned_climate(snapshot: dict[str, Any]) -> Iterator[list[tuple[float, float, int]]]:
    """Serve `snapshot` for its own (lat, lng, year); any other request fails."""
    data = DadosClimaticosMensais.model_validate(snapshot)
    calls: list[tuple[float, float, int]] = []

    def fetch(_self: OpenMeteoClient, latitude: float, longitude: float, ano: int) -> DadosClimaticosMensais:
        calls.append((latitude, longitude, ano))
        if (round(latitude, 4), round(longitude, 4), ano) != (
            round(data.latitude, 4),
            round(data.longitude, 4),
            data.ano_referencia,
        ):
            raise RuntimeError(f"golden run requested unpinned climate ({latitude}, {longitude}, {ano})")
        return data.model_copy(deep=True)

    with patch.object(OpenMeteoClient, "fetch_dados_anuais", fetch):
        yield calls


def catalog(spec: dict[str, Any]) -> dict[str, Any]:
    """Resolved context catalog plus the spec's fixture CPUs.

    `catalog_patches` (falsifiers only) edits insumo records: a value of None
    removes that field.
    """
    result = copy.deepcopy(Runtime(CONFIG).load_catalogo(spec["contexto_id"]))
    result["cpus"] = list(result["cpus"]) + spec["fixture_cpus"]
    patches = spec.get("catalog_patches", {}).get("insumos", {})
    if patches:
        insumos = []
        for record in result["insumos"]:
            change = patches.get(record.get("codigo"))
            if change is not None:
                record = dict(record)
                for field, value in change.items():
                    if value is None:
                        record.pop(field, None)
                    else:
                        record[field] = value
            insumos.append(record)
        missing = set(patches) - {r.get("codigo") for r in result["insumos"]}
        if missing:
            raise KeyError(f"catalog_patches name unknown insumos: {sorted(missing)}")
        result["insumos"] = insumos
    return result


def run(
    tmp_path: Path,
    spec: dict[str, Any],
    *,
    intent: str = "rfp",
    climate: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ConciliumService]:
    """Run skills 01-09 (or the RFI subset) on `spec` with every source pinned."""
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
    repository.get_project(project_id).write_json("benchmark_reference.json", {"catalog": catalog(spec)})
    with pinned_climate(climate if climate is not None else climate_snapshot(spec)) as calls:
        result = pipeline.run_project(
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
    if not calls:
        raise AssertionError("golden run never consulted the pinned climate snapshot")
    return result, service


def load_canonical(result: dict[str, Any], service: ConciliumService):
    project = service._dependencies.repository.get_project(result["project_id"])
    return project.load_canonical(result["version"])


def wetter_climate(snapshot: dict[str, Any], extra_days: int = 1) -> dict[str, Any]:
    """A pointwise more adverse copy of `snapshot`: every ISO week gets `extra_days`
    more days at or above each precipitation threshold (capped at 7), and every
    month 4x that (capped at 28) for the monthly fallback."""
    result = copy.deepcopy(snapshot)
    for counts in result["dias_precipitacao_semanal"].values():
        for threshold in counts:
            counts[threshold] = min(7, counts[threshold] + extra_days)
    for counts in result["dias_precipitacao_mensal"].values():
        for threshold in counts:
            counts[threshold] = min(28, counts[threshold] + 4 * extra_days)
    return result


def oracle_c_cat(spec: dict[str, Any]) -> str:
    """C^cat from the raw catalog records with the independent stdlib oracle."""
    records = catalog(spec)
    cpus = {c["codigo"]: c for c in records["cpus"]}
    productions = {p["id"]: p for p in records["producoes"]}
    insumos = {i["codigo"]: i for i in records["insumos"]}

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
