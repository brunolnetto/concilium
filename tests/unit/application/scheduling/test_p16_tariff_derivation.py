"""N8 (#206): exact P16 tariffs from the catalog rate and declared contract terms."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_EVEN, Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from concilium.application.runtime import Runtime
from concilium.application.scheduling.p16_tariff_derivation import (
    UnknownContractError,
    derive_p16_tariff,
    derive_p16_tariffs,
    resolve_contract_terms,
)
from concilium.application.scheduling.resource_level_contracts import exact_money

ROOT = Path(__file__).resolve().parents[4]
VECTORS = json.loads(
    (ROOT / "tests/reference_formalism/vectors/pool_contract_tariff_v1.json").read_text(encoding="utf-8")
)["vectors"]
DEFAULT = {"regime": "FULL_RATE_STANDBY", "mobilize": "0", "demobilize": "0", "max_idle_gap": 2, "source": "test"}


def _derive(case: dict) -> dict:
    insumo = {
        "codigo": "R",
        "tipo": "EQUIPAMENTO" if case["price_unit"] == "mes" else "MAO_OBRA",
        "unidade": case["price_unit"],
        "preco_unitario": case["price"],
    }
    declarations = {"default": case.get("default", {}), "overrides": {"R": case.get("override", {})}}
    if "default" not in case:
        declarations = None
    return derive_p16_tariff(
        "R",
        insumo,
        dias_semana=case["dias_semana"],
        horas_dia=Fraction(case["horas_dia"]),
        declarations=declarations,
        currency="BRL",
        catalog_reference="catalog-x",
    )


@pytest.mark.parametrize("case", VECTORS, ids=lambda c: c["case_id"])
def test_production_matches_the_oracle_vector(case: dict) -> None:
    if "expected_error" in case:
        with pytest.raises(UnknownContractError):
            _derive(case["case"])
        return
    tariff = _derive(case["case"])
    observed = {k: str(tariff[k]) for k in ("active_week", "idle_week", "mobilize", "demobilize", "max_idle_gap")}
    assert observed == case["expected"]


@pytest.mark.parametrize("spec_name", ["spec.json", "spec_sharing.json"])
def test_golden_fixture_tariffs_are_the_cent_rounding_of_the_derived_rate(spec_name: str) -> None:
    """The hand-declared golden tariffs came from the same catalog rule; the derived
    exact rate must round (half-even, cents) to every one of them."""
    spec = json.loads((ROOT / "tests/fixtures/formalism_golden_rfp" / spec_name).read_text(encoding="utf-8"))
    declared = spec["skill_inputs"]["05-equipes-e-alocacao"]["rcpsp_spec"]["p16_exact_tariffs"]
    catalog = Runtime(ROOT / "config").load_catalogo(spec["contexto_id"])
    tariffs, unknown = derive_p16_tariffs(
        declared,
        catalog,
        dias_semana=spec["dates"]["dias_semana"],
        horas_dia=spec["dates"]["horas_dia"],
        declarations={"default": DEFAULT},
        currency="BRL",
        catalog_reference="mendeslobo",
    )
    assert unknown == {}
    for tipo_id, fixture in declared.items():
        derived = Fraction(tariffs[tipo_id]["active_week"])
        cents = Decimal(derived.numerator) / Decimal(derived.denominator)
        assert str(cents.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)) == fixture["active_week"], tipo_id
        assert tariffs[tipo_id]["category"] == fixture["category"], tipo_id
        assert tariffs[tipo_id]["idle_week"] == tariffs[tipo_id]["active_week"]


def test_override_merges_over_the_default_and_unknown_fields_are_rejected() -> None:
    terms = resolve_contract_terms({"default": DEFAULT, "overrides": {"R": {"mobilize": "7"}}}, "R")
    assert (terms["mobilize"], terms["demobilize"], terms["max_idle_gap"]) == ("7", "0", 2)
    with pytest.raises(UnknownContractError, match="unknown contract-term fields"):
        resolve_contract_terms({"default": {**DEFAULT, "discount": "1"}}, "R")


@pytest.mark.parametrize(
    ("declarations", "match"),
    [
        (None, "no contract terms"),
        ({"default": {k: v for k, v in DEFAULT.items() if k != "regime"}}, "not declared: regime"),
        ({"default": {**DEFAULT, "regime": "EXPLICIT_OFF_HIRE"}}, "unsupported or undeclared"),
        ({"default": {**DEFAULT, "mobilize": 0.0}}, "exact rational string"),
        ({"default": {**DEFAULT, "max_idle_gap": 1.5}}, "nonnegative integer"),
        ({"default": {**DEFAULT, "source": " "}}, "source is required"),
    ],
)
def test_incomplete_or_inexact_terms_are_unknown_contracts(declarations, match: str) -> None:
    insumo = {"codigo": "R", "tipo": "EQUIPAMENTO", "unidade": "mes", "preco_unitario": "100"}
    with pytest.raises(UnknownContractError, match=match):
        derive_p16_tariff(
            "R", insumo, dias_semana=6, horas_dia=8, declarations=declarations, currency="BRL", catalog_reference="c"
        )


def test_resources_missing_from_the_catalog_or_non_contractual_are_reported_not_priced() -> None:
    catalog = {
        "insumos": [
            {"codigo": "EQ", "tipo": "EQUIPAMENTO", "unidade": "mes", "preco_unitario": "100"},
            {"codigo": "MAT", "tipo": "MATERIAL", "unidade": "kg", "preco_unitario": "5"},
            {"codigo": "DAY", "tipo": "EQUIPAMENTO", "unidade": "dia", "preco_unitario": "5"},
        ]
    }
    tariffs, unknown = derive_p16_tariffs(
        ["EQ", "MAT", "DAY", "GHOST"],
        catalog,
        dias_semana=6,
        horas_dia=8,
        declarations={"default": DEFAULT},
        currency="BRL",
        catalog_reference="c",
    )
    assert set(tariffs) == {"EQ"}
    assert set(unknown) == {"MAT", "DAY", "GHOST"}
    assert "absent from the catalog" in unknown["GHOST"]


def test_declared_active_tariff_overrides_the_catalog_rate_with_its_source() -> None:
    insumo = {"codigo": "R", "tipo": "EQUIPAMENTO", "unidade": "mes", "preco_unitario": "100"}
    tariff = derive_p16_tariff(
        "R",
        insumo,
        dias_semana=6,
        horas_dia=8,
        currency="BRL",
        catalog_reference="c",
        declarations={
            "default": DEFAULT,
            "overrides": {"R": {"active_week": "17985.76", "source": "contract 12/2026"}},
        },
    )
    assert tariff["active_week"] == "449644/25"
    assert "declared active tariff" in tariff["source_id"] and "contract 12/2026" in tariff["source_id"]


def test_p16_parser_accepts_exact_rationals_and_still_rejects_floats() -> None:
    assert exact_money("218976576/12175") == Fraction(218976576, 12175)
    assert exact_money("17985.76") == Fraction("17985.76")
    for bad in ("1/0", "-1/2", "1.5/2", "a/b", "1e400/1"):
        with pytest.raises(ValueError):
            exact_money(bad)
    with pytest.raises(ValueError):
        exact_money(1.5)  # type: ignore[arg-type]
