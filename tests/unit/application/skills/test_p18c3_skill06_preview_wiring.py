"""P18-C3 opt-in Skill06 sidecar wiring; no legacy-finance override."""
from __future__ import annotations

import sys

import pytest

from concilium.application.skills import _load
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import CanonicalModel


_SKILL_ID = "06-resultado-financeiro"


@pytest.fixture
def skill_module():
    _load(_SKILL_ID, "run_resultado_financeiro")
    return sys.modules["_concilium_skillpkg_06_resultado_financeiro.skill"]


def _canonical() -> CanonicalModel:
    return CanonicalModel.model_construct(p18_consumption_preview={"stale": True})


def _stub_stages(monkeypatch, skill_module, *, final=None):
    seen = {"final_input": None, "stage3_calls": 0}

    def pre(canonical, *_args):
        return SkillResult(canonical, [])

    def indirect(canonical, *_args):
        return SkillResult(canonical, [])

    def consolidate(canonical, *_args):
        seen["stage3_calls"] += 1
        seen["final_input"] = canonical.p18_consumption_preview
        return SkillResult(canonical, [])

    monkeypatch.setattr(skill_module, "_run_precificacao", pre)
    monkeypatch.setattr(skill_module, "_run_indiretos", indirect)
    monkeypatch.setattr(skill_module, "_run_consolidacao", consolidate)
    return seen


def test_preview_is_disabled_by_default_and_stale_sidecar_is_cleared(monkeypatch, skill_module):
    seen = _stub_stages(monkeypatch, skill_module)
    monkeypatch.setattr(
        skill_module, "build_p18_skill06_preview",
        lambda *_args: pytest.fail("opt-in preview builder must not be called"),
    )
    result = skill_module.run_resultado_financeiro(_canonical(), {}, {}, {})
    assert result.canonical.p18_consumption_preview is None
    assert seen["stage3_calls"] == 1
    assert seen["final_input"] is None


def test_opt_in_publishes_sidecar_and_only_warns(monkeypatch, skill_module):
    seen = _stub_stages(monkeypatch, skill_module)
    expected = {
        "schema": "concilium.p18.skill06-preview.v1",
        "authority": "P18_SKILL06_READ_ONLY_PREVIEW_NOT_PROJECT_GO",
        "project_go_authorized": False,
        "currency": "BRL",
        "currency_source": "EXPLICIT_RUNTIME_DECLARATION_CATALOG_SCHEMA_HAS_NO_CURRENCY_FIELD",
        "totals": {"contractual_k": "10", "consumable_v": "3", "indirect": "2", "direct": "13", "total": "15"},
    }
    monkeypatch.setattr(skill_module, "build_p18_skill06_preview", lambda *_args: expected)
    result = skill_module.run_resultado_financeiro(
        _canonical(),
        {
            "p18_consumption_preview_enabled": True,
            "p18_catalog_price_currency": "BRL",
        },
        {"cpus": [], "insumos": []},
        {},
    )
    assert result.canonical.p18_consumption_preview == expected
    assert seen["final_input"] == expected
    assert seen["stage3_calls"] == 1
    assert any(
        item.codigo == "VAL-P18-CONSUMPTION-PREVIEW" and item.status == "AVISO"
        for item in result.validacoes
    )


def test_invalid_opt_in_type_returns_error_before_legacy_stages(monkeypatch, skill_module):
    seen = _stub_stages(monkeypatch, skill_module)
    result = skill_module.run_resultado_financeiro(
        _canonical(), {"p18_consumption_preview_enabled": "true"}, {}, {},
    )
    assert result.canonical.p18_consumption_preview is None
    assert seen["stage3_calls"] == 0
    assert any(
        item.codigo == "VAL-P18-CONSUMPTION-PREVIEW" and item.status == "ERRO"
        for item in result.validacoes
    )


def test_invalid_evidence_aborts_stage3_without_falling_back(monkeypatch, skill_module):
    seen = _stub_stages(monkeypatch, skill_module)

    def fail_closed(*_args):
        raise ValueError("no exact Skill05 witness")

    monkeypatch.setattr(skill_module, "build_p18_skill06_preview", fail_closed)
    result = skill_module.run_resultado_financeiro(
        _canonical(), {"p18_consumption_preview_enabled": True}, {}, {},
    )
    assert result.canonical.p18_consumption_preview is None
    assert seen["stage3_calls"] == 0
    assert any(
        item.codigo == "VAL-P18-CONSUMPTION-PREVIEW" and item.status == "ERRO"
        for item in result.validacoes
    )
