"""N9.1 (#206): the status every interface shows for a project's BDI declaration."""

from __future__ import annotations

import copy
import json
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from concilium.application.scheduling.exact_pricing_declaration import (
    PROJECT_SCHEMA,
    PricingDeclarationError,
    profile_effective_layers,
    profile_pricing_terms,
)
from concilium.application.scheduling.project_bdi_exact_status import (
    DAMAGED,
    EXACT,
    LEGACY_ONLY,
    NONE,
    STATUS_SCHEMA,
    approx_percent,
    exact_project_bdi_status,
    exact_text,
    load_project_profile,
    profile_rows_for_validation,
)
from concilium.application.scheduling.project_bdi_exact_store import HEAD, LEGACY_HEAD, save_exact_project_bdi

ROOT = Path(__file__).resolve().parents[4]
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
ROWS = PROFILE["precificacao_exata"]["tabela_bdi"]["linhas"]
DECLARATION = {
    "schema": PROJECT_SCHEMA,
    "fonte": "ISS 2% — lei municipal",
    "linhas": {
        "mao_obra": {
            "l": "0.08",
            "tributos": {"iss": {"aplicavel": True, "aliquota": "0.02"}, "cssl": {"aplicavel": False}},
        }
    },
}


class FakeProject:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}
        self.meta = {"id": "proj-1"}

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.files

    def read_json(self, relative_path: str, default: Any) -> Any:
        try:
            return json.loads(self.files[relative_path])
        except (KeyError, json.JSONDecodeError):
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        self.files[relative_path] = json.dumps(payload, ensure_ascii=False)


def _saved() -> FakeProject:
    project = FakeProject()
    save_exact_project_bdi(project, "proj-1", DECLARATION, confirmado_por="Eng. A", motivo_revisao=None)
    return project


def _expected_mo_beta() -> Fraction:
    """TCU formula by hand over the merged mao_obra row (profile overhead, project L and taxes)."""
    row = ROWS["mao_obra"]
    overhead = 1 + Fraction(row["ac"]) + Fraction(row["r"]) + Fraction(row["cr"])
    taxes = Fraction(row["cofins"]) + Fraction("0.02") + Fraction(row["pis"]) + 0 + Fraction(row["ir"])
    return overhead * (1 + Fraction(row["df"])) * (1 + Fraction("0.08")) / (1 - taxes) - 1


def test_exact_declaration_shows_record_fields_and_merged_layers_with_origin() -> None:
    status = exact_project_bdi_status(_saved(), PROFILE, perfil_id="mendeslobo")
    assert status["schema"] == STATUS_SCHEMA and status["estado"] == EXACT
    assert status["preco_exato_bloqueado"] is False and status["motivo"] is None
    assert status["registro"]["versao"] == 1 and status["registro"]["confirmado_por"] == "Eng. A"
    assert len(status["registro"]["content_hash"]) == 64 and status["registro"]["confirmado_em"]
    assert status["declaracao"] == DECLARATION
    assert status["campos_declarados"] == [
        {"linha": "mao_obra", "campo": "l", "valor": "0.08"},
        {"linha": "mao_obra", "campo": "iss", "valor": "0.02"},
        {"linha": "mao_obra", "campo": "cssl", "valor": "não aplicável"},
    ]
    mo = status["camadas"]["categorias"]["MO"]
    assert mo["linha"] == "mao_obra" and mo["natureza"] == ROWS["mao_obra"]["natureza"]
    assert mo["l"] == {"valor": "0.08", "origem": "project"}
    assert mo["ac"] == {"valor": ROWS["mao_obra"]["ac"], "origem": "profile"}
    assert mo["tributos"]["iss"] == {"valor": "0.02", "origem": "project"}
    assert mo["tributos"]["cssl"] == {"valor": "0", "origem": "project"}
    assert mo["tributos"]["ir"] == {"valor": ROWS["mao_obra"]["ir"], "origem": "profile"}
    assert Fraction(mo["markup"]) == _expected_mo_beta()
    assert mo["markup_aprox"] == approx_percent(_expected_mo_beta())
    # Rows are independent: EQ comes from `servicos`, which the project did not declare.
    eq = status["camadas"]["categorias"]["EQ"]
    assert eq["l"]["origem"] == "profile" and set(t["origem"] for t in eq["tributos"].values()) == {"profile"}
    assert status["camadas"]["referencia_projeto"]["fingerprint"] == status["registro"]["content_hash"]


def test_shown_layers_are_the_ones_the_price_derives() -> None:
    status = exact_project_bdi_status(_saved(), PROFILE)
    tipo_obra = next(iter(PROFILE["precificacao_exata"]["piso_bdi_regulatorio"]["servico"]["por_tipo_obra"]))
    terms = profile_pricing_terms(PROFILE, tipo_obra, DECLARATION)
    for category, beta in terms["bdi_by_category"].items():
        assert Fraction(status["camadas"]["categorias"][category]["markup"]) == beta
    assert terms["layer_origins"] == profile_effective_layers(PROFILE, DECLARATION)["layer_origins"]


def test_float_only_profile_blocks_the_exact_price_and_is_never_converted() -> None:
    project = FakeProject()
    project.write_json(LEGACY_HEAD, {"versao": 3, "confirmado_por": "Eng. B", "lucro": {"mao_obra": 0.08}})
    status = exact_project_bdi_status(project, PROFILE)
    assert status["estado"] == LEGACY_ONLY and status["preco_exato_bloqueado"] is True
    assert "never converted" in status["motivo"]
    assert status["declaracao"] is None and status["registro"] is None and status["campos_declarados"] == []
    assert status["camadas"] is None and status["camadas_motivo"]
    assert status["perfil_legado"] == {"existe": True, "versao": 3, "confirmado_por": "Eng. B", "content_hash": None}
    assert "0.08" not in json.dumps(status)  # no float of the legacy profile leaks into the status


def test_damaged_head_is_reported_and_blocks() -> None:
    project = _saved()
    record = project.read_json(HEAD, None)
    record["declaracao"]["linhas"]["mao_obra"]["l"] = "0.09"  # content no longer matches the hash
    project.write_json(HEAD, record)
    status = exact_project_bdi_status(project, PROFILE)
    assert status["estado"] == DAMAGED and status["preco_exato_bloqueado"] is True
    assert "content_hash does not match" in status["motivo"]
    assert status["declaracao"] is None and status["camadas"] is None

    project.files[HEAD] = "{not json"
    assert exact_project_bdi_status(project, PROFILE)["estado"] == DAMAGED


def test_nothing_saved_shows_the_profile_layers() -> None:
    status = exact_project_bdi_status(FakeProject(), PROFILE)
    assert status["estado"] == NONE and status["preco_exato_bloqueado"] is False
    assert status["perfil_legado"] == {"existe": False}
    origins = {c["l"]["origem"] for c in status["camadas"]["categorias"].values()}
    assert origins == {"profile"} and status["camadas"]["referencia_projeto"] is None


def test_layers_need_the_profile_and_say_why_when_missing_or_incomplete() -> None:
    missing = exact_project_bdi_status(_saved(), None, perfil_motivo="no context")
    assert missing["estado"] == EXACT and missing["camadas"] is None and missing["camadas_motivo"] == "no context"
    assert missing["preco_exato_bloqueado"] is False  # unknown profile: nothing is claimed about the merge

    incomplete = copy.deepcopy(PROFILE)
    del incomplete["precificacao_exata"]["tabela_bdi"]["linhas"]["mao_obra"]["iss"]
    status = exact_project_bdi_status(_saved(), incomplete)
    assert status["camadas"] is None and status["preco_exato_bloqueado"] is True
    assert "tabela_bdi.mao_obra" in status["motivo"]


def test_declaration_that_does_not_merge_over_the_profile_blocks() -> None:
    project = FakeProject()
    excessive = {**DECLARATION, "linhas": {"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "0.99"}}}}}
    save_exact_project_bdi(project, "proj-1", excessive, confirmado_por="Eng", motivo_revisao=None)
    status = exact_project_bdi_status(project, PROFILE)
    assert status["estado"] == EXACT and status["preco_exato_bloqueado"] is True
    assert "below 100%" in status["motivo"]


@pytest.mark.parametrize(
    ("value", "text"),
    [("0", "0"), ("1/20", "0.05"), ("0.0199", "0.0199"), ("3", "3"), ("1/3", "1/3"), ("-1/8", "-0.125"), ("10", "10")],
)
def test_exact_text_is_exact(value: str, text: str) -> None:
    assert exact_text(Fraction(value)) == text
    assert Fraction(exact_text(Fraction(value))) == Fraction(value)


def test_approx_percent_rounds_for_display_only() -> None:
    assert approx_percent(Fraction(1, 3)) == "33.3333%"
    assert approx_percent(Fraction("0.25")) == "25.0000%"
    assert approx_percent(Fraction(-1, 8), 2) == "-12.50%"


def test_profile_rows_for_validation_only_from_a_complete_profile() -> None:
    assert profile_rows_for_validation(PROFILE) == ROWS
    assert profile_rows_for_validation(None) is None
    assert profile_rows_for_validation({"precificacao_exata": {}}) is None


def test_effective_layers_refuse_a_profile_without_the_block() -> None:
    with pytest.raises(PricingDeclarationError, match="no precificacao_exata block"):
        profile_effective_layers({}, None)


def test_load_project_profile_resolves_through_the_context_or_gives_a_reason() -> None:
    runtime = SimpleNamespace(
        load_contexto=lambda contexto_id: SimpleNamespace(perfil_id="p1"),
        load_perfil=lambda perfil_id: {"id": perfil_id},
    )
    assert load_project_profile(runtime, {"contexto_id": "ctx"}) == ("p1", {"id": "p1"}, None)
    perfil_id, perfil, reason = load_project_profile(runtime, {})
    assert perfil_id is None and perfil is None and "contexto_id" in reason

    def broken(_contexto_id: str) -> Any:
        raise RuntimeError("config gone")

    runtime.load_contexto = broken
    assert "config gone" in load_project_profile(runtime, {"contexto_id": "ctx"})[2]
