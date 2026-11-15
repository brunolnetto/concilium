"""N9.1 (#206): the UI editor of the project's exact BDI declaration — logic without a browser."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from concilium.application.scheduling.exact_pricing_declaration import (
    PROJECT_SCHEMA,
    PricingDeclarationError,
    validate_project_declaration,
)
from concilium.application.scheduling.project_bdi_exact_status import exact_project_bdi_status
from concilium.application.scheduling.project_bdi_exact_store import LEGACY_HEAD, save_exact_project_bdi
from concilium.presentation.ui.helpers.bdi_exato import (
    APPLICABLE,
    FROM_PROFILE,
    NOT_APPLICABLE,
    ROWS,
    TAXES,
    build_save_request,
    current_version,
    declaration_from_form,
    empty_form,
    form_from_declaration,
    layers_rows,
    profile_value,
    status_banner,
)

ROOT = Path(__file__).resolve().parents[4]
UI = ROOT / "src/concilium/presentation/ui"
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
DECLARATION = {
    "schema": PROJECT_SCHEMA,
    "fonte": "ISS 2% — lei municipal",
    "linhas": {
        "mao_obra": {
            "l": "0.08",
            "tributos": {"iss": {"aplicavel": True, "aliquota": "1/50"}, "cofins": {"aplicavel": False}},
        },
        "material": {"l": "0.035"},
    },
}


class FakeProject:
    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    def exists(self, relative_path: str) -> bool:
        return relative_path in self.files

    def read_json(self, relative_path: str, default: Any) -> Any:
        try:
            return json.loads(self.files[relative_path])
        except (KeyError, json.JSONDecodeError):
            return default

    def write_json(self, relative_path: str, payload: Any) -> None:
        self.files[relative_path] = json.dumps(payload, ensure_ascii=False)


def _status(saved: bool = True) -> dict[str, Any]:
    project = FakeProject()
    if saved:
        save_exact_project_bdi(project, "p", DECLARATION, confirmado_por="Eng", motivo_revisao=None)
    return exact_project_bdi_status(project, PROFILE, perfil_id="mendeslobo")


def test_form_round_trips_the_saved_declaration_text_for_text() -> None:
    form = form_from_declaration(DECLARATION)
    assert form["linhas"]["mao_obra"]["l"] == "0.08"
    assert form["linhas"]["mao_obra"]["tributos"]["iss"] == {"modo": APPLICABLE, "aliquota": "1/50"}
    assert form["linhas"]["mao_obra"]["tributos"]["cofins"] == {"modo": NOT_APPLICABLE, "aliquota": ""}
    assert form["linhas"]["mao_obra"]["tributos"]["pis"] == {"modo": FROM_PROFILE, "aliquota": ""}
    assert declaration_from_form(form) == DECLARATION  # "1/50" stays "1/50": nothing is reformatted


def test_empty_form_declares_nothing_and_is_refused_with_the_reason() -> None:
    assert form_from_declaration(None) == empty_form()
    assert set(empty_form()["linhas"]) == set(ROWS)
    declaration = declaration_from_form({**empty_form(), "fonte": "x"})
    assert declaration == {"schema": PROJECT_SCHEMA, "fonte": "x", "linhas": {}}
    payload, refusal = build_save_request(empty_form(), confirmado_por="Eng", motivo_revisao="", versao_atual=None)
    assert payload is None and "Declaração exata inválida" in refusal


def test_only_text_enters_the_declaration() -> None:
    form = form_from_declaration(DECLARATION)
    form["linhas"]["mao_obra"]["l"] = 0.08  # a float from a numeric widget would be a silent conversion
    with pytest.raises(TypeError, match="must be text"):
        declaration_from_form(form)
    payload, refusal = build_save_request(form, confirmado_por="Eng", motivo_revisao="", versao_atual=None)
    assert payload is None and "must be text" in refusal


@pytest.mark.parametrize(
    ("row", "tax", "entry", "needle"),
    [
        ("mao_obra", "iss", {"modo": APPLICABLE, "aliquota": "2%"}, "exact decimal or rational string"),
        ("mao_obra", "iss", {"modo": APPLICABLE, "aliquota": ""}, "must declare aliquota"),
        ("mao_obra", "iss", {"modo": APPLICABLE, "aliquota": "-0.02"}, "nonnegative"),
        ("mao_obra", "iss", {"modo": APPLICABLE, "aliquota": "1.0"}, "below 100%"),
        ("mao_obra", "pis", {"modo": NOT_APPLICABLE, "aliquota": "0.01"}, "must not declare aliquota"),
        ("mao_obra", "pis", {"modo": FROM_PROFILE, "aliquota": "0.01"}, "do perfil"),
    ],
)
def test_invalid_input_is_rejected_with_the_reason(row: str, tax: str, entry: dict, needle: str) -> None:
    form = form_from_declaration(DECLARATION)
    form["linhas"][row]["tributos"][tax] = entry
    payload, refusal = build_save_request(form, confirmado_por="Eng", motivo_revisao="", versao_atual=None)
    assert payload is None and needle in refusal


def test_inexact_profit_and_missing_source_are_rejected() -> None:
    form = form_from_declaration(DECLARATION)
    form["linhas"]["material"]["l"] = "3,5%"
    assert "linhas.material.l" in build_save_request(form, confirmado_por="E", motivo_revisao="", versao_atual=None)[1]
    form = form_from_declaration({**DECLARATION, "fonte": "  "})
    assert "fonte" in build_save_request(form, confirmado_por="E", motivo_revisao="", versao_atual=None)[1]


def test_confirmado_por_always_and_motivo_from_version_2() -> None:
    form = form_from_declaration(DECLARATION)
    assert build_save_request(form, confirmado_por=" ", motivo_revisao="", versao_atual=None) == (
        None,
        "confirmado_por é obrigatório.",
    )
    payload, refusal = build_save_request(form, confirmado_por=" Eng ", motivo_revisao="", versao_atual=None)
    assert refusal is None and payload == {"declaracao": DECLARATION, "confirmado_por": "Eng", "motivo_revisao": None}
    validate_project_declaration(payload["declaracao"])
    payload, refusal = build_save_request(form, confirmado_por="Eng", motivo_revisao=" ", versao_atual=1)
    assert payload is None and "motivo_revisao é obrigatório" in refusal and "versão atual: 1" in refusal
    payload, refusal = build_save_request(form, confirmado_por="Eng", motivo_revisao="ISS novo", versao_atual=1)
    assert refusal is None and payload["motivo_revisao"] == "ISS novo"


def test_request_built_by_the_ui_is_accepted_by_the_store_and_versions() -> None:
    project = FakeProject()
    form = form_from_declaration(DECLARATION)
    first, _ = build_save_request(form, confirmado_por="Eng", motivo_revisao="", versao_atual=None)
    save_exact_project_bdi(
        project, "p", first["declaracao"], confirmado_por=first["confirmado_por"], motivo_revisao=None
    )
    status = exact_project_bdi_status(project, PROFILE)
    assert current_version(status) == 1
    form = form_from_declaration(status["declaracao"])
    form["linhas"]["mao_obra"]["l"] = "0.07"
    second, _ = build_save_request(form, confirmado_por="Eng", motivo_revisao="lucro", versao_atual=1)
    saved = save_exact_project_bdi(
        project, "p", second["declaracao"], confirmado_por="Eng", motivo_revisao=second["motivo_revisao"]
    )
    assert saved["versao"] == 2 and saved["diff"]["campos_alterados"] == ["linhas.mao_obra.l"]


def test_banner_matches_each_state() -> None:
    level, text = status_banner(_status())
    assert level == "success" and text.startswith("EXATO — ")
    level, text = status_banner(_status(saved=False))
    assert level == "info" and text.startswith("NENHUM — ") and current_version(_status(saved=False)) is None

    legacy = FakeProject()
    legacy.write_json(LEGACY_HEAD, {"versao": 1})
    level, text = status_banner(exact_project_bdi_status(legacy, PROFILE))
    assert level == "error" and "PREÇO EXATO NÃO AVALIADO" in text and "never converted" in text

    damaged = FakeProject()
    damaged.files["bdi/perfil_bdi_exato.json"] = "{}"
    level, text = status_banner(exact_project_bdi_status(damaged, PROFILE))
    assert level == "error" and text.startswith("DANIFICADO — ") and "Motivo:" in text


def test_layers_table_carries_exact_values_origin_and_marked_approximation() -> None:
    rows = layers_rows(_status())
    assert [row["Categoria"] for row in rows] == ["MO", "EQ", "MAT", "COMB", "IND"]
    mo = rows[0]
    assert mo["L"] == "0.08 (projeto)" and mo["ISS"] == "0.02 (projeto)" and mo["COFINS"] == "0 (projeto)"
    assert mo["AC"] == "0.05 (perfil)" and mo["Markup ≈ (aproximado)"].endswith("%")
    assert rows[2]["L"] == "0.035 (projeto)" and rows[1]["L"] == "0.09 (perfil)"
    assert {tax.upper() for tax in TAXES} <= set(mo)
    assert layers_rows({"camadas": None}) == []
    assert profile_value(_status(), "mao_obra", "l") == "0.08 (projeto)"
    assert profile_value(_status(), "servicos", "iss") == "0.05 (perfil)"
    assert profile_value({"camadas": None}, "mao_obra", "l") is None


def test_declaration_from_form_rejects_unknown_mode() -> None:
    form = empty_form()
    form["linhas"]["diesel"]["tributos"]["ir"] = {"modo": "talvez", "aliquota": ""}
    with pytest.raises(PricingDeclarationError, match="modo desconhecido"):
        declaration_from_form(form)


def test_exact_editor_has_no_numeric_widget_and_no_float_conversion() -> None:
    """The exact editor must never be able to produce a float: text widgets only."""
    for name in ("organisms/layout/_bdi_exato_editor.py", "helpers/bdi_exato.py"):
        source = (UI / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = {
            node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert not calls & {"number_input", "slider", "float", "round", "data_editor", "text_area"}, name
        assert not any(isinstance(node, ast.Constant) and isinstance(node.value, float) for node in ast.walk(tree))


def test_bdi_tab_renders_exact_first_and_labels_the_float_editor_as_legacy() -> None:
    source = (UI / "organisms/layout/_bdi_tab_indiretos.py").read_text(encoding="utf-8")
    tab = source[source.index("def render_bdi_tab(") : source.index("_INDIR_REGIMES")]
    assert tab.index("render_bdi_exato(") < tab.index("render_bdi_editor(")
    assert "Legado (ponto flutuante) — não usado pelo preço exato" in tab
    legacy = (UI / "organisms/layout/_bdi_editor.py").read_text(encoding="utf-8")
    # The float editor cannot write the exact file.
    assert "bdi-exato" not in legacy and "perfil_bdi_exato" not in legacy
