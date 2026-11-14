"""N9 (#206): exact pricing declaration from the profile's declared terms."""

from __future__ import annotations

import copy
import json
from fractions import Fraction
from pathlib import Path

import pytest

from concilium.application.scheduling.exact_pricing_declaration import (
    PricingDeclarationError,
    build_p21_declaration,
    profile_pricing_terms,
    tcu_bdi_rate,
)

ROOT = Path(__file__).resolve().parents[4]
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
VECTORS = json.loads((ROOT / "tests/reference_formalism/vectors/economic_bdi_tcu_v1.json").read_text(encoding="utf-8"))[
    "vectors"
]


def _row(case: dict) -> dict:
    return {
        "ac": case["AC"],
        "r": case["RSG"],
        "cr": "0",
        "df": case["DF"],
        "l": case["L"],
        "cofins": "0",
        "iss": case["T"],
        "pis": "0",
        "cssl": "0",
        "ir": "0",
    }


@pytest.mark.parametrize("case", VECTORS, ids=lambda c: c["case_id"])
def test_production_bdi_matches_the_tcu_oracle_vector(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(PricingDeclarationError, match=case["expected_error"]):
            tcu_bdi_rate(_row(case["case"]))
    else:
        assert str(tcu_bdi_rate(_row(case["case"]))) == case["expected"]


def test_mendeslobo_profile_declares_complete_exact_pricing_terms() -> None:
    terms = profile_pricing_terms(PROFILE, "terraplenagem")
    assert {k: str(v) for k, v in terms["bdi_by_category"].items()} == {
        "MO": "270031/902700",
        "EQ": "270031/902700",  # equipment takes the services rate, no rental/maintenance blend
        "MAT": "1/25",
        "COMB": "1/25",
        "IND": "15133/60180",
    }
    assert terms["minimum_profit_margin"] == Fraction(3, 50)
    assert terms["regulatory_floor"] == Fraction("0.1960")
    assert "2622/2013" in terms["regulatory_source"] and terms["inventory_status"] == "NO_INVENTORY"
    assert profile_pricing_terms(PROFILE, "saneamento")["regulatory_floor"] == Fraction("0.2076")


def _without(path: list[str]) -> dict:
    profile = copy.deepcopy(PROFILE)
    node = profile
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return profile


@pytest.mark.parametrize(
    ("profile", "tipo_obra", "match"),
    [
        (_without(["precificacao_exata"]), "terraplenagem", "no precificacao_exata"),
        (_without(["precificacao_exata", "tabela_bdi", "linhas", "servicos"]), "terraplenagem", "tabela_bdi.servicos"),
        (_without(["precificacao_exata", "tabela_bdi", "fonte"]), "terraplenagem", "fonte"),
        (_without(["precificacao_exata", "piso_bdi_regulatorio"]), "terraplenagem", "piso_bdi_regulatorio"),
        (_without(["precificacao_exata", "escopo_estoque"]), "terraplenagem", "escopo_estoque"),
        (_without(["faixa_margem_aceitavel"]), "terraplenagem", "faixa_margem_aceitavel"),
        (PROFILE, "edificacao", "no regulatory BDI floor declared for work type"),
    ],
)
def test_incomplete_profile_terms_are_not_defaulted(profile: dict, tipo_obra: str, match: str) -> None:
    with pytest.raises(PricingDeclarationError, match=match):
        profile_pricing_terms(profile, tipo_obra)


def test_float_components_are_rejected() -> None:
    profile = copy.deepcopy(PROFILE)
    profile["precificacao_exata"]["tabela_bdi"]["linhas"]["mao_obra"]["ac"] = 0.05
    with pytest.raises(PricingDeclarationError, match="exact decimal or rational string"):
        profile_pricing_terms(profile, "terraplenagem")


def test_declaration_reports_why_it_cannot_be_built() -> None:
    from types import SimpleNamespace

    canonical = SimpleNamespace(projeto=SimpleNamespace(tipo_obra="terraplenagem"), eap=[])
    declaration, reasons = build_p21_declaration(_without(["precificacao_exata"]), canonical, {"currency": "BRL"})
    assert declaration is None and "precificacao_exata" in reasons[0]
    declaration, reasons = build_p21_declaration(PROFILE, canonical, {})
    assert declaration is None and "currency" in reasons[0]
    declaration, reasons = build_p21_declaration(PROFILE, SimpleNamespace(projeto=None), {"currency": "BRL"})
    assert declaration is None and "tipo_obra" in reasons[0]
