"""Skill04 pool inference reproduces the independent N7 pool-demand oracle (#206)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from concilium.application.scheduling.pool_inference import derivar_required_resources
from tests.reference_formalism.pool_demand_reference import evaluate_pool_demand

PATH = Path(__file__).resolve().parents[3] / "reference_formalism/vectors/pool_demand_from_fronts_v1.json"


def goldens() -> list[dict]:
    return json.loads(PATH.read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize("case", [c for c in goldens() if "expected" in c], ids=lambda c: c["case_id"])
def test_production_peak_equipment_demand_matches_the_oracle(case: dict) -> None:
    """Skill04 pool inference: e_ir = fronts x per-front units of each equipment type."""
    equipes = []
    for activity in case["case"]["activities"]:
        equipment = [
            SimpleNamespace(equip_id=resource, num_unidades=units)
            for resource, units in activity["composition"].items()
            if not resource.startswith("MO-") and resource != "WORKER"
        ]
        equipes.append(
            SimpleNamespace(item_id=activity["id"], num_equipes_base=max(activity["fronts"]), equipamentos=equipment)
        )
    identity = {e.equip_id: e.equip_id for eq in equipes for e in eq.equipamentos}
    required, _warnings = derivar_required_resources(equipes, identity)
    for activity in case["case"]["activities"]:
        peak = max(activity["fronts"])
        for resource, units in activity["composition"].items():
            if resource.startswith("MO-") or resource == "WORKER":
                continue
            single = evaluate_pool_demand(
                {
                    "horizon_weeks": 1,
                    "activities": [{"id": activity["id"], "fronts": [peak], "composition": {resource: units}}],
                }
            )
            assert required[activity["id"]][resource] == single[resource][0], (activity["id"], resource)
