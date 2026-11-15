"""N9.1 (#206): the project's exact BDI declaration is saved in exact strings and injected into Skill06."""

from __future__ import annotations

import copy
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from concilium.application.runtime.mixins.inputs import InputsMixin
from concilium.application.scheduling.exact_pricing_declaration import (
    PROJECT_SCHEMA,
    PricingDeclarationError,
    project_declaration_fingerprint,
    validate_project_declaration,
)
from concilium.application.scheduling.pricing_report_adapter import apply_pricing_report_evidence
from concilium.application.scheduling.project_bdi_exact_store import (
    HEAD,
    LEGACY_HEAD,
    SAVED_SCHEMA,
    ProjectBdiExactError,
    diff_path,
    inject_exact_project_bdi,
    load_exact_project_bdi,
    save_exact_project_bdi,
    version_path,
)
from concilium.application.skills import _load
from concilium.application.skills.base import SkillResult

ROOT = Path(__file__).resolve().parents[4]
PROFILE = json.loads((ROOT / "config/perfis/mendeslobo.json").read_text(encoding="utf-8"))
PROFILE_ROWS = PROFILE["precificacao_exata"]["tabela_bdi"]["linhas"]


class FakeProject:
    """Project files as JSON text in memory, with the handle's read/write/exists contract."""

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


def _declaration(lines: dict | None = None, fonte: str = "ISS 2% — lei municipal") -> dict:
    return {
        "schema": PROJECT_SCHEMA,
        "fonte": fonte,
        "linhas": lines or {"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "0.02"}}}},
    }


def _save(project: FakeProject, declaration: object, motivo: str | None = None, **kwargs: Any) -> dict:
    return save_exact_project_bdi(
        project, "proj-1", declaration, confirmado_por="Eng. A", motivo_revisao=motivo, **kwargs
    )


# ── save: validation ──────────────────────────────────────────────────────


def test_first_save_writes_head_and_immutable_snapshot() -> None:
    project = FakeProject()
    saved = _save(project, _declaration())
    assert (saved["schema"], saved["versao"], saved["projeto_id"]) == (SAVED_SCHEMA, 1, "proj-1")
    assert saved["content_hash"] == project_declaration_fingerprint(_declaration())
    assert "diff" not in saved
    assert (
        set(project.files)
        == {HEAD, version_path(1)}
        == {
            "bdi/perfil_bdi_exato.json",
            "bdi/perfil_bdi_exato_v001.json",
        }
    )
    assert project.read_json(HEAD, None) == project.read_json(version_path(1), None)
    # Stored exactly as declared: strings stay strings.
    stored = project.read_json(HEAD, None)["declaracao"]
    assert stored == _declaration() and stored["linhas"]["mao_obra"]["tributos"]["iss"]["aliquota"] == "0.02"


@pytest.mark.parametrize(
    ("declaration", "match"),
    [
        (None, "required"),
        ({"tributario": {}, "lucro": {"mao_obra": 0.08}}, "exactly schema, fonte and linhas"),
        (_declaration({"mao_obra": {"l": 0.08}}), "exact decimal or rational string"),
        (_declaration({"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": 0.02}}}}), "exact decimal"),
        (_declaration({"equipamento": {"l": "0.05"}}), "unknown row"),
        (_declaration({"mao_obra": {"tributos": {"icms": {"aplicavel": False}}}}), "no such tax"),
        (_declaration({"mao_obra": {"ac": "0.03"}}), "overrides only l and tributos"),
        (_declaration({"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "1"}}}}), "below 100%"),
        (_declaration(fonte=" "), "fonte"),
    ],
)
def test_invalid_declaration_is_rejected_and_nothing_is_written(declaration: object, match: str) -> None:
    project = FakeProject()
    with pytest.raises(ProjectBdiExactError, match=match):
        _save(project, declaration)
    assert project.files == {}


def test_save_validates_against_the_profile_rows_when_given() -> None:
    # ISS 95.27% alone is below 100%; with the profile's CSSL + IR (4.73%) on the same row it reaches 100%.
    declaration = _declaration({"mao_obra": {"tributos": {"iss": {"aplicavel": True, "aliquota": "0.9527"}}}})
    validate_project_declaration(declaration)  # structurally valid on its own
    project = FakeProject()
    with pytest.raises(ProjectBdiExactError, match="below 100%"):
        _save(project, declaration, profile_rows=PROFILE_ROWS)
    assert project.files == {}
    assert _save(project, _declaration(), profile_rows=PROFILE_ROWS)["versao"] == 1


def test_confirmado_por_is_required() -> None:
    with pytest.raises(ProjectBdiExactError, match="confirmado_por"):
        save_exact_project_bdi(FakeProject(), "proj-1", _declaration(), confirmado_por=" ", motivo_revisao=None)


# ── save: versions ────────────────────────────────────────────────────────


def test_update_needs_a_reason_and_keeps_history_with_a_diff() -> None:
    project = FakeProject()
    first = _save(project, _declaration())
    with pytest.raises(ProjectBdiExactError, match="motivo_revisao is required"):
        _save(project, _declaration({"mao_obra": {"l": "0.08"}}))
    assert project.read_json(HEAD, None)["versao"] == 1

    revised = _declaration(
        {"mao_obra": {"l": "0.08", "tributos": {"iss": {"aplicavel": True, "aliquota": "0.03"}}}},
    )
    second = _save(project, revised, motivo="ISS renegociado para 3%; lucro 8%")
    assert second["versao"] == 2
    assert second["diff"]["campos_alterados"] == ["linhas.mao_obra.l", "linhas.mao_obra.tributos.iss.aliquota"]
    assert (second["diff"]["versao_anterior"], second["diff"]["versao_nova"]) == (1, 2)
    assert second["diff"]["content_hash_anterior"] == first["content_hash"] != second["content_hash"]
    assert project.read_json(diff_path(2), None) == second["diff"]
    # v1 snapshot untouched; head is v2.
    assert project.read_json(version_path(1), None)["declaracao"] == _declaration()
    assert project.read_json(HEAD, None)["declaracao"] == revised
    assert project.read_json(version_path(2), None)["motivo_revisao"] == "ISS renegociado para 3%; lucro 8%"


def test_damaged_head_is_not_overwritten() -> None:
    project = FakeProject()
    _save(project, _declaration())
    record = project.read_json(HEAD, None)
    record["declaracao"]["linhas"]["mao_obra"]["tributos"]["iss"]["aliquota"] = "0.05"  # edited by hand
    project.write_json(HEAD, record)
    before = dict(project.files)
    with pytest.raises(ProjectBdiExactError, match="content_hash does not match"):
        _save(project, _declaration(), motivo="tentativa")
    assert project.files == before


def test_existing_snapshot_is_never_replaced() -> None:
    project = FakeProject()
    _save(project, _declaration())
    project.write_json(version_path(2), {"anything": True})
    with pytest.raises(ProjectBdiExactError, match="snapshots are immutable"):
        _save(project, _declaration({"mao_obra": {"l": "0.08"}}), motivo="x")
    assert project.read_json(HEAD, None)["versao"] == 1


# ── load and injection ────────────────────────────────────────────────────


def test_load_states() -> None:
    project = FakeProject()
    assert load_exact_project_bdi(project) == (None, None)

    project.write_json(LEGACY_HEAD, {"versao": 3, "lucro": {"mao_obra": 0.08}})
    declaration, reason = load_exact_project_bdi(project)
    assert declaration is None
    assert "floating-point" in reason and "never converted" in reason and "re-save" in reason

    _save(project, _declaration())
    assert load_exact_project_bdi(project) == (_declaration(), None)

    project.files[HEAD] = "{not json"
    declaration, reason = load_exact_project_bdi(project)
    assert declaration is None and "not a valid saved exact declaration" in reason and "re-save" in reason

    project.write_json(HEAD, {**json.loads(project.files[version_path(1)]), "declaracao": _declaration({"x": {}})})
    declaration, reason = load_exact_project_bdi(project)
    assert declaration is None and "unknown row" in reason


def test_injection_precedence() -> None:
    project = FakeProject()
    _save(project, _declaration())

    inputs: dict = {}
    inject_exact_project_bdi(project, inputs)
    assert inputs == {"bdi_projeto_exato": _declaration()}

    explicit = _declaration({"material": {"l": "0.05"}}, fonte="override do run")
    inputs = {"bdi_projeto_exato": copy.deepcopy(explicit)}
    inject_exact_project_bdi(project, inputs)
    assert inputs == {"bdi_projeto_exato": explicit}

    inputs = {"p21_pricing_evidence": {"schema": "hand-written"}}
    inject_exact_project_bdi(project, inputs)
    assert "bdi_projeto_exato" not in inputs and "bdi_projeto_exato_indisponivel" not in inputs

    legacy_only = FakeProject()
    legacy_only.write_json(LEGACY_HEAD, {"versao": 1})
    inputs = {}
    inject_exact_project_bdi(legacy_only, inputs)
    assert set(inputs) == {"bdi_projeto_exato_indisponivel"}
    # An explicit exact declaration in the run still wins over a float-only project.
    inputs = {"bdi_projeto_exato": copy.deepcopy(explicit)}
    inject_exact_project_bdi(legacy_only, inputs)
    assert inputs == {"bdi_projeto_exato": explicit}

    inputs = {}
    inject_exact_project_bdi(FakeProject(), inputs)
    assert inputs == {}


class _Runtime(InputsMixin):
    def load_jurisdicao_com_fallback(self, _jurisdicao_id: str) -> tuple[dict, list]:
        return {}, []


class _Contexto:
    id = "ctx"
    jurisdicao_id = "BR-CE"


def test_runtime_injects_only_into_skill06() -> None:
    project = FakeProject()
    _save(project, _declaration())
    runtime = _Runtime()
    assert (
        runtime._apply_runtime_defaults("06-resultado-financeiro", project, _Contexto(), {})["bdi_projeto_exato"]
        == _declaration()
    )
    assert "bdi_projeto_exato" not in runtime._apply_runtime_defaults("07-qualquer", project, _Contexto(), {})
    explicit = _declaration({"diesel": {"l": "0.05"}})
    normalized = runtime._apply_runtime_defaults(
        "06-resultado-financeiro", project, _Contexto(), {"bdi_projeto_exato": explicit}
    )
    assert normalized["bdi_projeto_exato"] == explicit


# ── through Skill 06 ──────────────────────────────────────────────────────


def _run_skill06(monkeypatch, project: FakeProject) -> tuple[Any, Any]:
    from tests.unit.application.scheduling.test_p21_runtime_pricing_integration import (
        _json_runtime_fixture,
        _result,
    )

    _load("06-resultado-financeiro", "run_resultado_financeiro")
    skill = sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]
    canonical, catalogo, _hand_written = _json_runtime_fixture()
    seen: dict = {}

    def stage(current, *_args):
        return SkillResult(current, [])

    def consolidation(current, inputs, *_args):
        seen["result"] = _result()
        validations: list = []
        apply_pricing_report_evidence(seen["result"], inputs, validations)
        return SkillResult(current, validations)

    monkeypatch.setattr(skill, "_run_precificacao", stage)
    monkeypatch.setattr(skill, "_run_indiretos", stage)
    monkeypatch.setattr(skill, "_run_consolidacao", consolidation)
    monkeypatch.setattr(skill, "build_skill06_p17_reconciliation", lambda _canonical: {"status": "RECONCILED"})
    inputs = _Runtime()._apply_runtime_defaults(
        "06-resultado-financeiro",
        project,
        _Contexto(),
        {
            "p18_consumption_preview_enabled": True,
            # N10: the project states its site-indirects scope; this fixture models none.
            "site_indirects_scope": {
                "status": "NO_SITE_INDIRECTS",
                "source": "unit fixture: fuel ledger only, no site administration modelled",
                "reference_id": "unit-no-site-indirects",
                "fingerprint": "unit-site-indirects-v1",
            },
        },
    )
    outcome = skill.run_resultado_financeiro(canonical, inputs, catalogo, PROFILE)
    return outcome, seen["result"]


def test_saved_project_declaration_changes_the_layered_result(monkeypatch) -> None:
    """The fixture's exact ledger is 42.804 of fuel (COMB <- `diesel` row: L 4%, no taxes in the profile)."""
    _outcome, plain = _run_skill06(monkeypatch, FakeProject())
    assert plain.markup_layers["total"]["cost"] == "10701/250"
    assert Fraction(plain.markup_layers["total"]["price"]) == Fraction("42.804") * Fraction("1.04")
    assert plain.markup_layers["provenance"]["project"] is None

    project = FakeProject()
    saved = _save(
        project,
        _declaration(
            {"diesel": {"l": "0.06", "tributos": {"cofins": {"aplicavel": True, "aliquota": "0.03"}}}},
            fonte="perfil do projeto v1",
        ),
        profile_rows=PROFILE_ROWS,
    )
    _outcome, merged = _run_skill06(monkeypatch, project)
    layers = merged.markup_layers
    # Hand check: profit 6% of 42.804 = 2.56824; net 45.37224; price = 45.37224 / 0.97; COFINS = 3% of the price.
    price = Fraction("45.37224") / Fraction("0.97")
    assert Fraction(layers["total"]["cost"]) == Fraction("42.804")
    assert Fraction(layers["total"]["profit"]) == Fraction("2.56824")
    assert Fraction(layers["total"]["price"]) == price
    assert Fraction(layers["total"]["taxes"]["cofins"]) == Fraction("0.03") * price
    assert layers["rates"]["COMB"]["l"] == "3/50" and layers["rates"]["MAT"]["l"] == "1/25"
    assert Fraction(merged.pricing_diagnostics["operational_price"]) == price
    provenance = layers["provenance"]
    assert provenance["project"] == {
        "schema": PROJECT_SCHEMA,
        "source": "perfil do projeto v1",
        "fingerprint": saved["content_hash"],
    }
    assert provenance["fields"]["COMB"]["l"] == provenance["fields"]["COMB"]["taxes"]["cofins"] == "project"
    assert provenance["fields"]["MAT"]["l"] == provenance["fields"]["COMB"]["taxes"]["iss"] == "profile"


def test_float_only_project_profile_leaves_the_exact_price_not_evaluated(monkeypatch) -> None:
    project = FakeProject()
    project.write_json(LEGACY_HEAD, {"versao": 2, "lucro": {"diesel": 0.06}})
    outcome, result = _run_skill06(monkeypatch, project)
    reasons = [v.mensagem for v in outcome.validacoes if v.codigo == "VAL-P21-NAO-AVALIADO"]
    assert len(reasons) == 1
    assert "legacy floating-point BDI profile" in reasons[0] and "re-save" in reasons[0]
    # Not priced at the company default: there is no layered result at all.
    assert result.markup_layers is None
    # The cause is persisted with the result, not only in this run's warnings (W3):
    # any later reader can say why the price was not evaluated and how to fix it.
    assert result.pricing_diagnostics["status"] == "UNKNOWN"
    assert "re-save" in result.pricing_diagnostics["reason"]
    from concilium.application.scheduling.exact_financial_view import build_exact_financial_view

    view = build_exact_financial_view({"resultado": result.model_dump(mode="json"), "contratos_recurso": []})
    codes = {reason["code"] for reason in view["reasons"]}
    assert view["status"] == "NAO_AVALIADO" and "BDI_PROJETO_NAO_EXATO" in codes, view["reasons"]


def test_damaged_saved_declaration_leaves_the_exact_price_not_evaluated(monkeypatch) -> None:
    project = FakeProject()
    _save(project, _declaration())
    project.files[HEAD] = "{not json"
    outcome, result = _run_skill06(monkeypatch, project)
    reasons = [v.mensagem for v in outcome.validacoes if v.codigo == "VAL-P21-NAO-AVALIADO"]
    assert len(reasons) == 1 and "not a valid saved exact declaration" in reasons[0]
    assert result.markup_layers is None


def test_validate_requires_a_declaration() -> None:
    with pytest.raises(PricingDeclarationError, match="required"):
        validate_project_declaration(None)
