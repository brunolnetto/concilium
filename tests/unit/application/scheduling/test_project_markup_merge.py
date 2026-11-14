"""N9.1 (#206): the project's exact tax/profit declaration merged over the profile's layers."""

from __future__ import annotations

import copy
import json
import sys
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

from concilium.application.scheduling import exact_pricing_declaration as module
from concilium.application.scheduling.exact_pricing_declaration import (
    CATEGORY_ROWS,
    PROJECT_SCHEMA,
    PricingDeclarationError,
    build_p21_declaration,
    profile_pricing_terms,
)
from concilium.application.scheduling.markup_layers import (
    PROVENANCE_SCHEMA,
    decompose_by_category,
    parse_layer_provenance,
    parse_markup_layers,
)
from concilium.application.scheduling.pricing_report_adapter import build_pricing_report_evidence_context
from concilium.application.skills import _load
from concilium.application.skills.base import SkillResult

ROOT = Path(__file__).resolve().parents[4]
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
VECTORS = json.loads(
    (ROOT / "tests/reference_formalism/vectors/economic_project_markup_merge_v1.json").read_text(encoding="utf-8")
)["vectors"]
_ZERO_ROW = {
    **dict.fromkeys(("ac", "r", "cr", "df", "l", "cofins", "iss", "pis", "cssl", "ir"), "0"),
    "natureza": "servico",
}


def _profile_from(base: dict) -> dict:
    """The Mendes Lobo profile with the vector's category rates as its BDI rows."""
    profile = copy.deepcopy(PROFILE)
    rows = profile["precificacao_exata"]["tabela_bdi"]["linhas"]
    for category, row_name in CATEGORY_ROWS.items():
        rates = base.get(category)
        rows[row_name] = (
            dict(_ZERO_ROW)
            if rates is None
            else {
                "ac": rates["ac"],
                "r": rates["rsg"],
                "cr": "0",
                "df": rates["df"],
                "l": rates["l"],
                **rates["taxes"],
                "natureza": rows[row_name]["natureza"],
            }
        )
    return profile


def _declaration_from(project: dict | None) -> dict | None:
    """The vector's category-level project declaration in the production row shape."""
    if project is None:
        return None
    lines: dict = {}
    for category, declared in project.items():
        line = {key: value for key, value in declared.items() if key != "taxes"}
        if "taxes" in declared:
            line["tributos"] = {
                name: {{"applicable": "aplicavel", "rate": "aliquota"}.get(k, k): v for k, v in entry.items()}
                for name, entry in declared["taxes"].items()
            }
        lines[CATEGORY_ROWS.get(category, category)] = line
    return {"schema": PROJECT_SCHEMA, "fonte": "vetor N9.1", "linhas": lines}


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["case_id"])
def test_production_merge_matches_the_independent_oracle(vector: dict) -> None:
    case = vector["case"]
    profile, declaration = _profile_from(case["base"]), _declaration_from(case.get("project"))
    if "expected_error" in vector:
        with pytest.raises(PricingDeclarationError):
            profile_pricing_terms(profile, "terraplenagem", declaration)
        return
    expected = vector["expected"]
    terms = profile_pricing_terms(profile, "terraplenagem", declaration)
    for category in case["base"]:
        layers = terms["layers"][category]
        want = expected["rates"][category]
        assert (str(layers.ac), str(layers.rsg), str(layers.df), str(layers.profit)) == (
            want["ac"],
            want["rsg"],
            want["df"],
            want["l"],
        )
        assert {name: str(rate) for name, rate in layers.taxes} == want["taxes"]
        assert str(terms["bdi_by_category"][category]) == expected["beta"][category]
        assert terms["layer_origins"][category] == expected["origin"][category]
    by_category, total = decompose_by_category(
        ((category, Fraction(cost)) for category, cost in case["costs"].items()), terms["layers"]
    )
    for category, want in expected["by_category"].items():
        got = by_category[category]
        assert (str(got.cost), str(got.overhead), str(got.profit), str(got.tax_total), str(got.price)) == (
            want["cost"],
            want["overhead"],
            want["profit"],
            want["taxes"],
            want["price"],
        )
    assert (str(total.cost), str(total.overhead), str(total.profit), str(total.tax_total), str(total.price)) == tuple(
        expected["total"][key] for key in ("cost", "overhead", "profit", "taxes", "price")
    )


def _project(lines: dict) -> dict:
    return {"schema": PROJECT_SCHEMA, "fonte": "perfil BDI do projeto v2 — ISS 2% (lei municipal)", "linhas": lines}


ISS_2 = {"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "0.02"}}}}


def test_project_override_changes_only_the_declared_field_of_the_declared_row() -> None:
    base = profile_pricing_terms(PROFILE, "terraplenagem")
    merged = profile_pricing_terms(PROFILE, "terraplenagem", _project(ISS_2))
    assert base["project_reference"] is None
    assert merged["bdi_by_category"]["MO"] == Fraction(240031, 932700) < base["bdi_by_category"]["MO"]
    assert dict(merged["layers"]["MO"].taxes)["iss"] == Fraction("0.02")
    # EQ takes the `servicos` row: declaring `mao_obra` does not touch it, nor any other category.
    for category in ("EQ", "MAT", "COMB", "IND"):
        assert merged["layers"][category] == base["layers"][category]
        assert merged["layer_origins"][category] == base["layer_origins"][category]
    assert merged["layer_origins"]["MO"]["taxes"]["iss"] == "project"
    assert merged["layer_origins"]["MO"]["l"] == "profile"
    # Floors follow the row's natureza, which a project cannot change.
    assert merged["bdi_floor_by_category"] == base["bdi_floor_by_category"]
    assert merged["project_reference"]["source"].startswith("perfil BDI do projeto v2")
    assert len(merged["project_reference"]["fingerprint"]) == 64


@pytest.mark.parametrize(
    ("declaration", "match"),
    [
        ({"schema": PROJECT_SCHEMA, "linhas": ISS_2}, "exactly schema, fonte and linhas"),
        ({"schema": "outro", "fonte": "x", "linhas": ISS_2}, "must declare schema"),
        ({"schema": PROJECT_SCHEMA, "fonte": " ", "linhas": ISS_2}, "fonte"),
        (_project({}), "at least one row"),
        (_project({"equipamento": {"l": "0.05"}}), "unknown row"),
        (_project({"MO": {"l": "0.05"}}), "unknown row"),
        (_project({"mao_obra": {}}), "at least one field"),
        (_project({"mao_obra": {"ac": "0.03"}}), "overrides only l and tributos"),
        (_project({"mao_obra": {"natureza": "fornecimento"}}), "overrides only l and tributos"),
        (_project({"mao_obra": {"l": 0.08}}), "exact decimal or rational string"),
        (_project({"mao_obra": {"l": "-0.01"}}), "nonnegative"),
        (_project({"mao_obra": {"tributos": {}}}), "at least one tax"),
        (_project({"mao_obra": {"tributos": {"icms": {"aplicavel": True, "aliquota": "0.18"}}}}), "no such tax"),
        (_project({"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": 0.02}}}}), "exact decimal"),
        (_project({"mao_obra": {"tributos": {"iss": {"aplicavel": True}}}}), "must declare aliquota"),
        (_project({"mao_obra": {"tributos": {"iss": {"aplicavel": False, "aliquota": "0.05"}}}}), "must not declare"),
        (_project({"mao_obra": {"tributos": {"iss": {"aplicavel": 1, "aliquota": "0.05"}}}}), "explicit boolean"),
        (_project({"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "0.02", "x": "1"}}}}), "unknown"),
        (_project({"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "0.9527"}}}}), "below 100%"),
        (_project({"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "1"}}}}), "below 100%"),
        ([], "exactly schema, fonte and linhas"),
    ],
)
def test_invalid_project_declaration_yields_no_terms(declaration: object, match: str) -> None:
    with pytest.raises(PricingDeclarationError, match=match):
        profile_pricing_terms(PROFILE, "terraplenagem", declaration)


def test_project_does_not_fill_gaps_of_an_incomplete_profile() -> None:
    profile = copy.deepcopy(PROFILE)
    del profile["precificacao_exata"]["tabela_bdi"]["linhas"]["mao_obra"]["l"]
    with pytest.raises(PricingDeclarationError, match="missing"):
        profile_pricing_terms(profile, "terraplenagem", _project({"mao_obra": {"l": "0.08"}}))


def _fake_envelope(monkeypatch) -> None:
    envelope = SimpleNamespace(
        activities=[SimpleNamespace(contractual=Fraction(600), consumable=Fraction(400))],
        total=Fraction(1000),
        fingerprint=lambda: "f" * 64,
    )
    monkeypatch.setattr(module, "derive_catalog_cost_envelope", lambda *_args: envelope)


_CANONICAL = SimpleNamespace(projeto=SimpleNamespace(tipo_obra="terraplenagem"), eap=[])


def test_declaration_carries_merged_layers_consistent_markup_and_provenance(monkeypatch) -> None:
    _fake_envelope(monkeypatch)
    plain, reasons = build_p21_declaration(PROFILE, _CANONICAL, {"currency": "BRL"})
    assert reasons == [] and plain is not None
    merged, reasons = build_p21_declaration(PROFILE, _CANONICAL, {"currency": "BRL"}, _project(ISS_2))
    assert reasons == [] and merged is not None

    layers = parse_markup_layers(merged["markup_layers"])
    assert merged["markup_layers"]["MO"]["taxes"]["iss"] == "1/50"
    # The category markup is the merged layers' own consequence.
    assert {c: str(layers[c].beta) for c in layers} == merged["bdi_by_category"]
    assert merged["bdi_by_category"]["MO"] == "240031/932700"
    assert merged["bdi_by_category"]["EQ"] == plain["bdi_by_category"]["EQ"] == "270031/902700"
    assert merged["bdi_floor_by_category"] == plain["bdi_floor_by_category"]
    assert merged["regulatory_basis"] == plain["regulatory_basis"]

    provenance = merged["markup_layers_provenance"]
    assert provenance["schema"] == PROVENANCE_SCHEMA
    assert provenance["profile"]["reference_id"] == "perfil:mendeslobo:tabela_bdi"
    assert provenance["project"]["schema"] == PROJECT_SCHEMA
    assert provenance["fields"]["MO"]["taxes"]["iss"] == "project"
    projected = [
        (category, field)
        for category, entry in provenance["fields"].items()
        for field, origin in {**entry, **entry["taxes"]}.items()
        if origin == "project"
    ]
    assert projected == [("MO", "iss")]
    assert parse_layer_provenance(provenance, layers) == provenance

    assert plain["markup_layers_provenance"]["project"] is None
    assert all(
        origin == "profile"
        for entry in plain["markup_layers_provenance"]["fields"].values()
        for origin in [*(entry[k] for k in ("ac", "rsg", "df", "l")), *entry["taxes"].values()]
    )


def test_invalid_project_declaration_yields_no_declaration_and_its_reason(monkeypatch) -> None:
    _fake_envelope(monkeypatch)
    declaration, reasons = build_p21_declaration(
        PROFILE, _CANONICAL, {"currency": "BRL"}, _project({"mao_obra": {"l": 0.08}})
    )
    assert declaration is None
    assert "project BDI declaration.linhas.mao_obra.l" in reasons[0] and "exact" in reasons[0]


def _provenance(monkeypatch) -> tuple[dict, dict]:
    _fake_envelope(monkeypatch)
    declaration, _ = build_p21_declaration(PROFILE, _CANONICAL, {"currency": "BRL"}, _project(ISS_2))
    assert declaration is not None
    return declaration["markup_layers_provenance"], parse_markup_layers(declaration["markup_layers"])


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda p: p.update(schema="x"), "schema must be"),
        (lambda p: p.pop("project"), "exactly schema, profile, project and fields"),
        (lambda p: p["fields"].pop("IND"), "exactly the declared categories"),
        (lambda p: p["fields"]["MO"].pop("df"), "must cover ac, rsg, df, l and taxes"),
        (lambda p: p["fields"]["MO"]["taxes"].pop("pis"), "exactly the declared taxes"),
        (lambda p: p["fields"]["MO"].update(l="caller"), "origins must be one of"),
        (lambda p: p.update(project=None), "must come together"),
        (lambda p: p["fields"]["MO"]["taxes"].update(iss="profile"), "must come together"),
        (lambda p: p["profile"].update(source=""), "as text"),
    ],
)
def test_inconsistent_provenance_is_rejected(monkeypatch, mutate, match: str) -> None:
    provenance, layers = _provenance(monkeypatch)
    provenance = copy.deepcopy(provenance)
    mutate(provenance)
    with pytest.raises(ValueError, match=match):
        parse_layer_provenance(provenance, layers)


def test_adapter_refuses_provenance_without_layers() -> None:
    from tests.unit.application.scheduling.test_p21_runtime_pricing_integration import _json_runtime_fixture

    canonical, catalogo, declaration = _json_runtime_fixture()
    assert "markup_layers" not in declaration
    declaration = {**declaration, "markup_layers_provenance": {"schema": PROVENANCE_SCHEMA}}
    with pytest.raises(ValueError, match="requires declared markup_layers"):
        build_pricing_report_evidence_context(canonical, catalogo, declaration)


# ── Skill 06 transport: inputs["bdi_projeto_exato"] ───────────────────────


def _skill06(monkeypatch, seen: dict):
    from tests.unit.application.scheduling.test_p21_runtime_pricing_integration import _json_runtime_fixture

    _load("06-resultado-financeiro", "run_resultado_financeiro")
    skill = sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]

    def stage(current, *_args):
        return SkillResult(current, [])

    def consolidation(current, inputs, *_args):
        seen["context"] = inputs.get("p21_pricing_evidence")
        return SkillResult(current, [])

    def build(perfil, canonical, catalogo, project_bdi=None):
        seen["project_bdi"] = project_bdi
        return None, ["stub"]

    monkeypatch.setattr(skill, "_run_precificacao", stage)
    monkeypatch.setattr(skill, "_run_indiretos", stage)
    monkeypatch.setattr(skill, "_run_consolidacao", consolidation)
    monkeypatch.setattr(skill, "build_skill06_p17_reconciliation", lambda _canonical: {"status": "RECONCILED"})
    monkeypatch.setattr(skill, "build_p21_declaration", build)
    return skill, _json_runtime_fixture()


def _not_evaluated(outcome) -> list[str]:
    return [v.mensagem for v in outcome.validacoes if v.codigo == "VAL-P21-NAO-AVALIADO"]


def test_skill06_passes_the_project_declaration_to_the_builder(monkeypatch) -> None:
    seen: dict = {}
    skill, (canonical, catalogo, _declaration) = _skill06(monkeypatch, seen)
    project = _project(ISS_2)
    outcome = skill.run_resultado_financeiro(
        canonical, {"p18_consumption_preview_enabled": True, "bdi_projeto_exato": project}, catalogo, PROFILE
    )
    assert seen["project_bdi"] == project
    assert _not_evaluated(outcome) == ["Preço exato não avaliado (sem estimativa): stub"]
    assert seen["context"] is None


def test_skill06_does_not_mix_project_declaration_with_hand_written_evidence(monkeypatch) -> None:
    seen: dict = {}
    skill, (canonical, catalogo, declaration) = _skill06(monkeypatch, seen)
    outcome = skill.run_resultado_financeiro(
        canonical,
        {
            "p18_consumption_preview_enabled": True,
            "p21_pricing_evidence": declaration,
            "bdi_projeto_exato": _project(ISS_2),
        },
        catalogo,
        PROFILE,
    )
    assert "project_bdi" not in seen
    assert "mutually exclusive" in _not_evaluated(outcome)[0]
    assert "mutually exclusive" in seen["context"]["source_build_error"]


def test_skill06_never_converts_the_legacy_float_project_profile(monkeypatch) -> None:
    seen: dict = {}
    skill, (canonical, catalogo, _declaration) = _skill06(monkeypatch, seen)
    outcome = skill.run_resultado_financeiro(
        canonical,
        {"p18_consumption_preview_enabled": True, "bdi_perfil": {"versao": 2, "lucro": {"mao_obra": 0.08}}},
        catalogo,
        PROFILE,
    )
    assert "project_bdi" not in seen and seen["context"] is None
    assert "floating point" in _not_evaluated(outcome)[0] and "bdi_projeto_exato" in _not_evaluated(outcome)[0]


def test_skill06_reports_a_project_declaration_it_cannot_use(monkeypatch) -> None:
    seen: dict = {}
    skill, (canonical, catalogo, _declaration) = _skill06(monkeypatch, seen)
    outcome = skill.run_resultado_financeiro(
        canonical, {"p18_consumption_preview_enabled": False, "bdi_projeto_exato": _project(ISS_2)}, catalogo, PROFILE
    )
    assert "project_bdi" not in seen and seen["context"] is None
    assert "requires the exact ledgers" in _not_evaluated(outcome)[0]
