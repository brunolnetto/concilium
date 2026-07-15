"""Tests for skill 13 — run_replanejamento_e_cenarios (consolidated pipeline).

Strategy: mock ``run_explorador_cenarios`` and ``run_assessor_replanejamento``
directly in the function's globals dict (the module namespace loaded via the
real production loader, ``_load_skill_module``/synthetic package).  This
avoids any import-path gymnastics and exercises the thin orchestration layer
in ``skill.py`` without invoking the real stages.

Covers:
- explorador is called first with the original canonical_in
- assessor is called second with the canonical returned by the explorador result
- validacoes are merged (explorador first, then assessor)
- final SkillResult.canonical comes from the assessor
- final SkillResult.validacoes is the merged list
- has_errors reflects the merged validacoes (ERRO in either stage bubbles up)
- perfil and inputs are forwarded to both stages unchanged
- explorador validacoes only (assessor returns empty list)
- assessor validacoes only (explorador returns empty list)
- both return empty validacoes lists
- multiple validacoes from each stage are all preserved in order
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime
from unittest.mock import MagicMock

from concilium.application.skills import run_replanejamento_e_cenarios as _trigger
from concilium.application.skills.base import SkillResult
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
    ValidacaoItem,
)

# ---------------------------------------------------------------------------
# Load the function under test
# ---------------------------------------------------------------------------

# Importing `run_replanejamento_e_cenarios` from the package triggers the real
# production loader (`_load_skill_module`), which registers a synthetic
# package so skill.py's relative imports (`from ._skill_helpers._assessor import ...`) work.
assert _trigger
_skill_mod = sys.modules["_concilium_skillpkg_08_replanejamento_e_cenarios.skill"]
run_replanejamento_e_cenarios = _skill_mod.run_replanejamento_e_cenarios

# The module namespace where we can inject mocks
_SKILL_GLOBALS = run_replanejamento_e_cenarios.__globals__


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _meta() -> Meta:
    return Meta(versao_schema="1.0.0", gerado_em=datetime.now(UTC), contexto_id="test-skill13-replan")


def _projeto() -> Projeto:
    return Projeto(
        id="p-skill13",
        nome="Projeto Replan",
        tipo_obra="terraplenagem",
        localizacao="CE",
        coordenadas=Coordenadas(lat=-3.7, lng=-38.5),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 1, 1),
        data_termino=date(2026, 12, 31),
        snapshot_catalogo_id="cat-1",
        snapshot_perfil_id="perf-1",
    )


def _canonical() -> CanonicalModel:
    return CanonicalModel(meta=_meta(), projeto=_projeto())


def _val(codigo: str, status: str = "OK") -> ValidacaoItem:
    return ValidacaoItem(codigo=codigo, status=status)


# ---------------------------------------------------------------------------
# Context manager / pytest fixture for injecting mocks
# ---------------------------------------------------------------------------


class _PatchSkill:
    """Temporarily replace run_explorador_cenarios and run_assessor_replanejamento
    in the skill module's global namespace."""

    def __init__(
        self,
        mock_exp: MagicMock,
        mock_ass: MagicMock,
    ) -> None:
        self._mock_exp = mock_exp
        self._mock_ass = mock_ass
        self._orig_exp = None
        self._orig_ass = None

    def __enter__(self) -> _PatchSkill:
        self._orig_exp = _SKILL_GLOBALS["run_explorador_cenarios"]
        self._orig_ass = _SKILL_GLOBALS["run_assessor_replanejamento"]
        _SKILL_GLOBALS["run_explorador_cenarios"] = self._mock_exp
        _SKILL_GLOBALS["run_assessor_replanejamento"] = self._mock_ass
        return self

    def __exit__(self, *_):
        _SKILL_GLOBALS["run_explorador_cenarios"] = self._orig_exp
        _SKILL_GLOBALS["run_assessor_replanejamento"] = self._orig_ass


# ---------------------------------------------------------------------------
# Helper to build a patched run with controlled SkillResults
# ---------------------------------------------------------------------------


def _make_mocks(
    can_after_exp: CanonicalModel | None = None,
    can_after_ass: CanonicalModel | None = None,
    vals_exp: list[ValidacaoItem] | None = None,
    vals_ass: list[ValidacaoItem] | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Return (mock_exp, mock_ass) pre-configured with SkillResult return values."""
    can_after_exp = can_after_exp or _canonical()
    can_after_ass = can_after_ass or _canonical()
    vals_exp = vals_exp if vals_exp is not None else []
    vals_ass = vals_ass if vals_ass is not None else []
    mock_exp = MagicMock(return_value=SkillResult(can_after_exp, vals_exp))
    mock_ass = MagicMock(return_value=SkillResult(can_after_ass, vals_ass))
    return mock_exp, mock_ass


# ---------------------------------------------------------------------------
# 1. Call order — explorador is called before assessor
# ---------------------------------------------------------------------------


class TestCallOrder:
    def test_explorador_called_before_assessor(self):
        """explorador must be invoked before assessor."""
        call_log: list[str] = []
        can_in = _canonical()
        can_mid = _canonical()
        can_out = _canonical()

        def _exp(c, inputs, perfil):
            call_log.append("exp")
            return SkillResult(can_mid, [])

        def _ass(c, inputs, perfil):
            call_log.append("ass")
            return SkillResult(can_out, [])

        mock_exp = MagicMock(side_effect=_exp)
        mock_ass = MagicMock(side_effect=_ass)

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, None)

        assert call_log == ["exp", "ass"]

    def test_explorador_called_exactly_once(self):
        """explorador must be called exactly once per invocation."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, None)

        mock_exp.assert_called_once()

    def test_assessor_called_exactly_once(self):
        """assessor must be called exactly once per invocation."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, None)

        mock_ass.assert_called_once()


# ---------------------------------------------------------------------------
# 2. Input forwarding — explorador gets original canonical_in
# ---------------------------------------------------------------------------


class TestInputForwarding:
    def test_explorador_receives_original_canonical_in(self):
        """explorador must be called with the original canonical_in (not a copy)."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, None)

        first_arg = mock_exp.call_args[0][0]
        assert first_arg is can_in

    def test_assessor_receives_canonical_from_explorador(self):
        """assessor must be called with the canonical produced by the explorador."""
        can_in = _canonical()
        can_mid = _canonical()  # distinct object returned by explorador
        mock_exp, mock_ass = _make_mocks(can_after_exp=can_mid)

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, None)

        ass_first_arg = mock_ass.call_args[0][0]
        assert ass_first_arg is can_mid

    def test_assessor_does_not_receive_original_canonical_in(self):
        """assessor must NOT receive the original canonical_in when explorador returns a different one."""
        can_in = _canonical()
        can_mid = _canonical()
        mock_exp, mock_ass = _make_mocks(can_after_exp=can_mid)

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, None)

        ass_first_arg = mock_ass.call_args[0][0]
        assert ass_first_arg is not can_in

    def test_inputs_forwarded_to_explorador(self):
        """inputs dict is forwarded unchanged to explorador."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()
        inputs = {"some_key": "some_value"}

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, inputs, None)

        assert mock_exp.call_args[0][1] is inputs

    def test_inputs_forwarded_to_assessor(self):
        """inputs dict is forwarded unchanged to assessor."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()
        inputs = {"another_key": 42}

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, inputs, None)

        assert mock_ass.call_args[0][1] is inputs

    def test_perfil_forwarded_to_explorador(self):
        """perfil dict is forwarded unchanged to explorador."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()
        perfil = {"faixa_margem_alvo": {"min": 0.08, "max": 0.10}}

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, perfil)

        assert mock_exp.call_args[0][2] is perfil

    def test_perfil_forwarded_to_assessor(self):
        """perfil dict is forwarded unchanged to assessor."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()
        perfil = {"faixa_margem_alvo": {"min": 0.08, "max": 0.10}}

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, perfil)

        assert mock_ass.call_args[0][2] is perfil

    def test_none_perfil_forwarded_to_both(self):
        """perfil=None is forwarded as-is to both stages."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            run_replanejamento_e_cenarios(can_in, {}, None)

        assert mock_exp.call_args[0][2] is None
        assert mock_ass.call_args[0][2] is None


# ---------------------------------------------------------------------------
# 3. Final canonical — comes from assessor result
# ---------------------------------------------------------------------------


class TestFinalCanonical:
    def test_result_canonical_is_from_assessor(self):
        """SkillResult.canonical must be the canonical returned by the assessor."""
        can_in = _canonical()
        can_mid = _canonical()
        can_out = _canonical()
        mock_exp, mock_ass = _make_mocks(can_after_exp=can_mid, can_after_ass=can_out)

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.canonical is can_out

    def test_result_canonical_is_not_from_explorador(self):
        """SkillResult.canonical must NOT be the explorador canonical when assessor returns another."""
        can_in = _canonical()
        can_mid = _canonical()
        can_out = _canonical()
        mock_exp, mock_ass = _make_mocks(can_after_exp=can_mid, can_after_ass=can_out)

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.canonical is not can_mid

    def test_result_canonical_is_not_original_canonical_in(self):
        """SkillResult.canonical must not be the original canonical_in."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.canonical is not can_in


# ---------------------------------------------------------------------------
# 4. Validacoes merging
# ---------------------------------------------------------------------------


class TestValidacoesMerging:
    def test_explorador_validacoes_come_first(self):
        """explorador validacoes precede assessor validacoes in the merged list."""
        can_in = _canonical()
        v1 = _val("EXP-01")
        v2 = _val("ASS-01")
        mock_exp, mock_ass = _make_mocks(vals_exp=[v1], vals_ass=[v2])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.validacoes[0].codigo == "EXP-01"
        assert result.validacoes[1].codigo == "ASS-01"

    def test_merged_validacoes_total_count(self):
        """Total validacoes count equals len(exp_vals) + len(ass_vals)."""
        can_in = _canonical()
        vals_exp = [_val(f"E-{i}") for i in range(3)]
        vals_ass = [_val(f"A-{i}") for i in range(2)]
        mock_exp, mock_ass = _make_mocks(vals_exp=vals_exp, vals_ass=vals_ass)

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert len(result.validacoes) == 5

    def test_empty_explorador_validacoes(self):
        """When explorador returns no validacoes, only assessor validacoes appear."""
        can_in = _canonical()
        v_ass = _val("ASS-ONLY")
        mock_exp, mock_ass = _make_mocks(vals_exp=[], vals_ass=[v_ass])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert len(result.validacoes) == 1
        assert result.validacoes[0].codigo == "ASS-ONLY"

    def test_empty_assessor_validacoes(self):
        """When assessor returns no validacoes, only explorador validacoes appear."""
        can_in = _canonical()
        v_exp = _val("EXP-ONLY")
        mock_exp, mock_ass = _make_mocks(vals_exp=[v_exp], vals_ass=[])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert len(result.validacoes) == 1
        assert result.validacoes[0].codigo == "EXP-ONLY"

    def test_both_empty_validacoes(self):
        """When both stages return empty validacoes, result has no validacoes."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks(vals_exp=[], vals_ass=[])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.validacoes == []

    def test_multiple_validacoes_from_each_stage_preserved(self):
        """All validacoes from both stages are present and in correct order."""
        can_in = _canonical()
        vals_exp = [_val("E1"), _val("E2"), _val("E3")]
        vals_ass = [_val("A1"), _val("A2")]
        mock_exp, mock_ass = _make_mocks(vals_exp=vals_exp, vals_ass=vals_ass)

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        codigos = [v.codigo for v in result.validacoes]
        assert codigos == ["E1", "E2", "E3", "A1", "A2"]

    def test_validacoes_objects_are_same_instances(self):
        """ValidacaoItem objects in result are the same instances (not copies)."""
        can_in = _canonical()
        v1 = _val("EXP-REF")
        v2 = _val("ASS-REF")
        mock_exp, mock_ass = _make_mocks(vals_exp=[v1], vals_ass=[v2])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.validacoes[0] is v1
        assert result.validacoes[1] is v2


# ---------------------------------------------------------------------------
# 5. has_errors propagation
# ---------------------------------------------------------------------------


class TestHasErrors:
    def test_no_errors_when_all_ok(self):
        """has_errors is False when all validacoes are OK/AVISO/INFO."""
        can_in = _canonical()
        vals = [_val("V1", "OK"), _val("V2", "AVISO"), _val("V3", "INFO")]
        mock_exp, mock_ass = _make_mocks(vals_exp=vals[:2], vals_ass=vals[2:])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert not result.has_errors

    def test_has_errors_when_explorador_produces_erro(self):
        """has_errors is True when explorador returns an ERRO validacao."""
        can_in = _canonical()
        vals_exp = [_val("EXP-ERR", "ERRO")]
        mock_exp, mock_ass = _make_mocks(vals_exp=vals_exp, vals_ass=[])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.has_errors

    def test_has_errors_when_assessor_produces_erro(self):
        """has_errors is True when assessor returns an ERRO validacao."""
        can_in = _canonical()
        vals_ass = [_val("ASS-ERR", "ERRO")]
        mock_exp, mock_ass = _make_mocks(vals_exp=[], vals_ass=vals_ass)

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.has_errors

    def test_has_errors_when_both_produce_erros(self):
        """has_errors is True when both stages return ERRO validacoes."""
        can_in = _canonical()
        vals_exp = [_val("E-ERR", "ERRO")]
        vals_ass = [_val("A-ERR", "ERRO")]
        mock_exp, mock_ass = _make_mocks(vals_exp=vals_exp, vals_ass=vals_ass)

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert result.has_errors

    def test_no_errors_when_both_empty_validacoes(self):
        """has_errors is False when both stages return empty validacoes."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks(vals_exp=[], vals_ass=[])

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert not result.has_errors


# ---------------------------------------------------------------------------
# 6. Return type
# ---------------------------------------------------------------------------


class TestReturnType:
    def test_returns_skill_result_instance(self):
        """run_replanejamento_e_cenarios must return a SkillResult."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert isinstance(result, SkillResult)

    def test_result_has_canonical_attribute(self):
        """SkillResult must have .canonical attribute."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert hasattr(result, "canonical")
        assert isinstance(result.canonical, CanonicalModel)

    def test_result_has_validacoes_attribute(self):
        """SkillResult must have .validacoes attribute as a list."""
        can_in = _canonical()
        mock_exp, mock_ass = _make_mocks()

        with _PatchSkill(mock_exp, mock_ass):
            result = run_replanejamento_e_cenarios(can_in, {}, None)

        assert hasattr(result, "validacoes")
        assert isinstance(result.validacoes, list)


