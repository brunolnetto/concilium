"""Production C^cat derivation matches the independent oracle vector exactly."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, date, datetime
from fractions import Fraction
from pathlib import Path

import pytest

from concilium.application.scheduling.catalog_cost_envelope import derive_catalog_cost_envelope
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
)

VECTOR = Path(__file__).resolve().parents[3] / "reference_formalism" / "vectors" / "catalog_envelope_v1.json"
_TYPE = {"EQ": "EQUIPAMENTO", "MO": "MAO_OBRA"}


def _case() -> dict:
    return json.loads(VECTOR.read_text(encoding="utf-8"))["vectors"][0]


def _to_catalog_and_canonical(case: dict) -> tuple[dict, CanonicalModel]:
    """Translate the oracle's abstract inputs into catalog/canonical records."""
    inputs = case["inputs"]
    cpus, productions, insumos, eap = [], [], {}, []
    for activity in inputs["activities"]:
        aid = activity["id"]
        equipamentos, funcoes = [], []
        for r in activity["contractual"]:
            insumos[r["id"]] = {
                "codigo": r["id"],
                "tipo": _TYPE[r["cat"]],
                "unidade": r["price_unit"],
                "preco_unitario": float(Fraction(r["price"])),
            }
            target = equipamentos if r["cat"] == "EQ" else funcoes
            key, count = ("equip_id", "num_unidades") if r["cat"] == "EQ" else ("funcao_id", "num_pessoas")
            target.append({key: r["id"], count: r["n"]})
        for g in activity["consumables"]:
            insumos[g["id"]] = {
                "codigo": g["id"],
                "tipo": "MATERIAL",
                "unidade": g["unit"],
                "preco_unitario": float(Fraction(g["price"])),
            }
        productions.append(
            {
                "id": f"PROD-{aid}",
                "unidade": activity["unit"],
                "producao_horaria": float(Fraction(activity["rho"])),
                "composicao_padrao_equipe": {"equipamentos": equipamentos, "funcoes": funcoes},
            }
        )
        cpus.append(
            {
                "codigo": f"CPU-{aid}",
                "unidade": activity["unit"],
                "producao_id_ref": f"PROD-{aid}",
                "composicao_itens": [
                    {"insumo_id": g["id"], "coeficiente": float(Fraction(g["coef"])), "categoria_custo": "MATERIAL"}
                    for g in activity["consumables"]
                ],
            }
        )
        eap.append(
            EapItem(
                item_id=aid, cpu_id=f"CPU-{aid}", unidade=activity["unit"], quantitativo=float(Fraction(activity["Q"]))
            )
        )
    canonical = CanonicalModel(
        meta=Meta(gerado_em=datetime(2026, 1, 1, tzinfo=UTC), contexto_id="catalog-envelope"),
        projeto=Projeto(
            id="catalog-envelope",
            nome="catalog envelope",
            tipo_obra="terraplenagem",
            localizacao="test",
            coordenadas=Coordenadas(lat=0, lng=0),
            regime_trabalho=RegimeTrabalho(dias_semana=inputs["regime"]["d"], horas_dia=inputs["regime"]["h"]),
            data_inicio=date(2026, 1, 5),
            data_termino=date(2026, 3, 1),
            snapshot_catalogo_id="catalog-v1",
            snapshot_perfil_id="profile-v1",
        ),
        eap=eap,
    )
    return {"cpus": cpus, "producoes": productions, "insumos": list(insumos.values())}, canonical


def test_production_envelope_matches_oracle_vector_exactly() -> None:
    case = _case()
    catalog, canonical = _to_catalog_and_canonical(case)
    envelope = derive_catalog_cost_envelope(canonical, catalog)
    observed = {
        a.activity_id: {"K": str(a.contractual), "V": str(a.consumable), "total": str(a.total)}
        for a in envelope.activities
    }
    assert observed == case["expected"]["activities"]
    assert str(envelope.total) == case["expected"]["total"]
    assert len(envelope.fingerprint()) == 64


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda c: c["insumos"][0].update(unidade="dia"), "'mes' or 'h'"),
        (
            lambda c: c["cpus"][0]["composicao_itens"].append(
                {"insumo_id": "E1", "coeficiente": 1.0, "categoria_custo": "EQUIPAMENTO"}
            ),
            "production team",
        ),
        (lambda c: c["producoes"][0].update(unidade="t"), "production unit differs"),
        (lambda c: c["producoes"][0].pop("composicao_padrao_equipe"), "production team"),
        (lambda c: c["cpus"][0].update(producao_id_ref="MISSING"), "production record"),
        (lambda c: c["insumos"][0].update(preco_unitario=float("nan")), "finite exact"),
    ],
)
def test_ambiguous_or_incomplete_catalog_fails_closed(mutate, message: str) -> None:
    catalog, canonical = _to_catalog_and_canonical(_case())
    catalog = deepcopy(catalog)
    mutate(catalog)
    with pytest.raises(ValueError, match=message):
        derive_catalog_cost_envelope(canonical, catalog)


def test_missing_production_unit_is_a_named_data_gap() -> None:
    catalog, canonical = _to_catalog_and_canonical(_case())
    catalog["producoes"][0].pop("unidade")
    with pytest.raises(ValueError, match="production record has no unidade"):
        derive_catalog_cost_envelope(canonical, catalog)
