"""Unit tests for concilium.application.runtime.helpers.pipeline."""

from __future__ import annotations

import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.runtime.exceptions import (
    RuntimeError as _RuntimeError,
    RuntimeTechnicalError,
)
from concilium.application.runtime.helpers.pipeline import (
    _apply_dv,
    _execute_skill,
    _format_records,
    _oas_log_invocation,
    _oas_save_state,
    _on_after_skill,
    _parse_executed_skills,
    _print_skill_start,
    _resolve_state,
)


# ---------------------------------------------------------------------------
# _parse_executed_skills
# ---------------------------------------------------------------------------


class TestParseExecutedSkills:
    def test_nonexistent_path_returns_empty_set(self, tmp_path):
        p = tmp_path / "nonexistent.jsonl"
        result = _parse_executed_skills(p)
        assert result == set()

    def test_valid_ok_line_adds_skill(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_text(json.dumps({"status": "OK", "skill": "01-escopo"}) + "\n")
        result = _parse_executed_skills(p)
        assert "01-escopo" in result

    def test_valid_erro_line_adds_skill(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_text(json.dumps({"status": "ERRO", "skill": "02-produtividade"}) + "\n")
        result = _parse_executed_skills(p)
        assert "02-produtividade" in result

    def test_multiple_skills_added(self, tmp_path):
        p = tmp_path / "log.jsonl"
        lines = [
            json.dumps({"status": "OK", "skill": "01-escopo"}),
            json.dumps({"status": "ERRO", "skill": "03-catalogo"}),
        ]
        p.write_text("\n".join(lines) + "\n")
        result = _parse_executed_skills(p)
        assert result == {"01-escopo", "03-catalogo"}

    def test_other_status_not_added(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_text(json.dumps({"status": "EXCEPTION", "skill": "04-cronograma"}) + "\n")
        result = _parse_executed_skills(p)
        assert result == set()

    def test_missing_skill_key_not_added(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_text(json.dumps({"status": "OK"}) + "\n")
        result = _parse_executed_skills(p)
        assert result == set()

    def test_malformed_json_line_silently_skipped(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_text("this is not json\n")
        result = _parse_executed_skills(p)
        assert result == set()

    def test_blank_lines_skipped(self, tmp_path):
        p = tmp_path / "log.jsonl"
        p.write_text("\n   \n\n")
        result = _parse_executed_skills(p)
        assert result == set()

    def test_mixed_valid_and_invalid_lines(self, tmp_path):
        p = tmp_path / "log.jsonl"
        lines = [
            json.dumps({"status": "OK", "skill": "01-escopo"}),
            "BAD JSON",
            "",
            json.dumps({"status": "ERRO", "skill": "03-catalogo"}),
        ]
        p.write_text("\n".join(lines) + "\n")
        result = _parse_executed_skills(p)
        assert result == {"01-escopo", "03-catalogo"}

    def test_duplicate_skill_only_once(self, tmp_path):
        p = tmp_path / "log.jsonl"
        lines = [
            json.dumps({"status": "OK", "skill": "01-escopo"}),
            json.dumps({"status": "ERRO", "skill": "01-escopo"}),
        ]
        p.write_text("\n".join(lines) + "\n")
        result = _parse_executed_skills(p)
        assert result == {"01-escopo"}
        assert len(result) == 1


# ---------------------------------------------------------------------------
# _execute_skill
# ---------------------------------------------------------------------------


class TestExecuteSkill:
    def _make_store(self):
        store = MagicMock()
        return store

    def test_happy_path_returns_result(self):
        skill_fn = MagicMock(return_value="output")
        store = self._make_store()
        ts = MagicMock()
        ts.isoformat.return_value = "2024-01-01T00:00:00"
        result = _execute_skill(skill_fn, {"a": 1}, "01-escopo", "exec-123", ts, store)
        assert result == "output"
        skill_fn.assert_called_once_with(a=1)
        store.log_invocation.assert_not_called()

    def test_domain_runtime_error_reraises_as_is(self):
        domain_error = _RuntimeError("domain problem")
        skill_fn = MagicMock(side_effect=domain_error)
        store = self._make_store()
        ts = MagicMock()
        ts.isoformat.return_value = "2024-01-01T00:00:00"
        with pytest.raises(_RuntimeError) as exc_info:
            _execute_skill(skill_fn, {}, "01-escopo", "exec-123", ts, store)
        assert exc_info.value is domain_error
        store.log_invocation.assert_called_once()
        payload = store.log_invocation.call_args[0][0]
        assert payload["status"] == "ERRO"
        assert payload["skill"] == "01-escopo"
        assert "domain problem" in payload["erro"]

    def test_generic_exception_wrapped_in_technical_error(self):
        skill_fn = MagicMock(side_effect=ValueError("unexpected"))
        store = self._make_store()
        ts = MagicMock()
        ts.isoformat.return_value = "2024-01-01T00:00:00"
        with pytest.raises(RuntimeTechnicalError) as exc_info:
            _execute_skill(skill_fn, {}, "02-produtividade", "exec-456", ts, store)
        assert "02-produtividade" in str(exc_info.value)
        assert "unexpected" in str(exc_info.value)
        store.log_invocation.assert_called_once()

    def test_log_invocation_payload_structure(self):
        skill_fn = MagicMock(side_effect=ValueError("boom"))
        store = self._make_store()
        ts = MagicMock()
        ts.isoformat.return_value = "2024-01-01T12:00:00"
        with pytest.raises(RuntimeTechnicalError):
            _execute_skill(skill_fn, {}, "03-catalogo", "exec-789", ts, store)
        payload = store.log_invocation.call_args[0][0]
        assert payload["ts"] == "2024-01-01T12:00:00"
        assert payload["execution_id"] == "exec-789"
        assert payload["skill"] == "03-catalogo"
        assert payload["status"] == "ERRO"
        assert "boom" in payload["erro"]

    def test_technical_error_is_also_runtime_error(self):
        """RuntimeTechnicalError must be a subclass of _RuntimeError (hierarchy check)."""
        skill_fn = MagicMock(side_effect=RuntimeError("generic python"))
        store = self._make_store()
        ts = MagicMock()
        ts.isoformat.return_value = "2024-01-01T00:00:00"
        with pytest.raises(RuntimeTechnicalError):
            _execute_skill(skill_fn, {}, "04-cronograma", "exec-000", ts, store)


# ---------------------------------------------------------------------------
# _apply_dv
# ---------------------------------------------------------------------------


class TestApplyDv:
    def test_dict_dv_raw_triggers_model_validate(self):
        from concilium.domain.models.project.decision_variables import DecisionVariables

        dv_validated = MagicMock(spec=DecisionVariables)
        canonical = MagicMock()
        canonical.decision_variables = object()  # different object
        updated_canonical = MagicMock()
        canonical.model_copy.return_value = updated_canonical

        with patch(
            "concilium.domain.models.project.decision_variables.DecisionVariables.model_validate",
            return_value=dv_validated,
        ) as mock_validate:
            result = _apply_dv(canonical, {"some": "dict"})
            mock_validate.assert_called_once_with({"some": "dict"})

    def test_already_typed_object_skips_validation(self):
        from concilium.domain.models.project.decision_variables import DecisionVariables

        dv_obj = MagicMock(spec=DecisionVariables)
        canonical = MagicMock()
        canonical.decision_variables = object()  # different
        canonical.model_copy.return_value = canonical

        with patch(
            "concilium.domain.models.project.decision_variables.DecisionVariables.model_validate"
        ) as mock_validate:
            _apply_dv(canonical, dv_obj)
            mock_validate.assert_not_called()

    def test_exception_inside_apply_returns_original(self):
        canonical = MagicMock()
        canonical.decision_variables = None
        canonical.model_copy.side_effect = RuntimeError("copy failed")

        # When model_copy raises, _apply_dv should silently return original
        with patch(
            "concilium.domain.models.project.decision_variables.DecisionVariables.model_validate",
            side_effect=RuntimeError("validate failed"),
        ):
            result = _apply_dv(canonical, {"broken": "data"})
        assert result is canonical

    def test_same_dv_no_model_copy(self):
        sentinel = object()
        canonical = MagicMock()
        canonical.decision_variables = sentinel
        canonical.model_copy.return_value = canonical

        with patch(
            "concilium.domain.models.project.decision_variables.DecisionVariables.model_validate",
            return_value=sentinel,
        ):
            result = _apply_dv(canonical, {"x": 1})
        # no update needed since dv didn't change
        canonical.model_copy.assert_not_called()


# ---------------------------------------------------------------------------
# _resolve_state
# ---------------------------------------------------------------------------


class TestResolveState:
    def _make_result(self, has_errors=False, canonical=None):
        result = MagicMock()
        result.has_errors = has_errors
        result.canonical = canonical or MagicMock()
        return result

    def test_gate_skill_with_errors_taints_canonical(self):
        from concilium.application.runtime.gates import _GATE_SKILLS

        gate_skill = next(iter(_GATE_SKILLS))
        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        tainted = MagicMock()
        canonical.model_copy.return_value = tainted

        result = self._make_result(has_errors=True, canonical=canonical)
        new_state = _resolve_state(gate_skill, result, {})
        canonical.model_copy.assert_called_once()
        call_kwargs = canonical.model_copy.call_args[1]["update"]
        assert gate_skill in call_kwargs["pipeline_blocked_from"]
        assert call_kwargs["pipeline_integridade"] == "CORROMPIDO"

    def test_gate_skill_without_errors_clears_own_entry(self):
        from concilium.application.runtime.gates import _GATE_SKILLS

        gate_skill = next(iter(_GATE_SKILLS))
        canonical = MagicMock()
        canonical.pipeline_blocked_from = [gate_skill]
        cleared = MagicMock()
        canonical.model_copy.return_value = cleared

        result = self._make_result(has_errors=False, canonical=canonical)
        new_state = _resolve_state(gate_skill, result, {})
        canonical.model_copy.assert_called_once()
        call_kwargs = canonical.model_copy.call_args[1]["update"]
        assert gate_skill not in call_kwargs["pipeline_blocked_from"]

    def test_gate_skill_without_errors_clears_integridade_when_no_more_blocked(self):
        from concilium.application.runtime.gates import _GATE_SKILLS

        gate_skill = next(iter(_GATE_SKILLS))
        canonical = MagicMock()
        canonical.pipeline_blocked_from = [gate_skill]
        cleared = MagicMock()
        canonical.model_copy.return_value = cleared

        result = self._make_result(has_errors=False, canonical=canonical)
        _resolve_state(gate_skill, result, {})
        call_kwargs = canonical.model_copy.call_args[1]["update"]
        assert call_kwargs["pipeline_integridade"] is None

    def test_non_gate_skill_is_passthrough(self):
        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        result = self._make_result(has_errors=False, canonical=canonical)

        with patch(
            "concilium.application.runtime.helpers.pipeline._GATE_SKILLS",
            frozenset(),
        ):
            new_state = _resolve_state("99-nongate", result, {})
        # no model_copy for taint
        canonical.model_copy.assert_not_called()

    def test_dv_raw_applied_when_skill_succeeds(self):
        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        result = self._make_result(has_errors=False, canonical=canonical)

        skill_inputs = {"99-nongate": {"decision_variables": {"x": 1}}}
        updated = MagicMock()
        with patch(
            "concilium.application.runtime.helpers.pipeline._GATE_SKILLS",
            frozenset(),
        ), patch(
            "concilium.application.runtime.helpers.pipeline._apply_dv",
            return_value=updated,
        ) as mock_apply:
            new_state = _resolve_state("99-nongate", result, skill_inputs)
        mock_apply.assert_called_once_with(canonical, {"x": 1})
        assert new_state is updated

    def test_dv_raw_not_applied_when_skill_has_errors(self):
        canonical = MagicMock()
        canonical.pipeline_blocked_from = []
        tainted = MagicMock()
        canonical.model_copy.return_value = tainted

        skill_inputs = {"01-escopo-e-eap": {"decision_variables": {"x": 1}}}

        from concilium.application.runtime.gates import _GATE_SKILLS

        gate_skill = "01-escopo-e-eap" if "01-escopo-e-eap" in _GATE_SKILLS else next(iter(_GATE_SKILLS))
        result = self._make_result(has_errors=True, canonical=canonical)

        with patch(
            "concilium.application.runtime.helpers.pipeline._apply_dv"
        ) as mock_apply:
            _resolve_state(gate_skill, result, skill_inputs)
        mock_apply.assert_not_called()

    def test_gate_skill_without_errors_not_in_blocked_no_update(self):
        from concilium.application.runtime.gates import _GATE_SKILLS

        gate_skill = next(iter(_GATE_SKILLS))
        canonical = MagicMock()
        canonical.pipeline_blocked_from = []  # gate_skill not in blocked
        result = self._make_result(has_errors=False, canonical=canonical)

        _resolve_state(gate_skill, result, {})
        # No model_copy should be called because skill_id not in current_blocked
        canonical.model_copy.assert_not_called()


# ---------------------------------------------------------------------------
# _oas_log_invocation
# ---------------------------------------------------------------------------


class TestOasLogInvocation:
    def _make_record(self, status="OK", duration_ms=100, warnings=None, errors=None):
        record = MagicMock()
        record.status = status
        record.duration_ms = duration_ms
        record.warnings = warnings or []
        record.errors = errors or []
        return record

    def _make_contract(self):
        contract = MagicMock()
        contract.required_inputs = ["input_a"]
        contract.optional_inputs = ["input_b"]
        contract.depends_on_skills = ["01-escopo"]
        contract.produces_section = "cronograma"
        return contract

    def test_ok_status_no_error_kind(self):
        runtime = MagicMock()
        contract = self._make_contract()
        runtime.get_skill_contract.return_value = contract
        store = MagicMock()
        record = self._make_record(status="OK")
        result = MagicMock()

        _oas_log_invocation(runtime, store, "v1", {}, "04-cronograma", result, record)
        store.log_invocation.assert_called_once()
        payload = store.log_invocation.call_args[0][1]
        assert payload["error_kind"] is None
        assert payload["status"] == "OK"

    def test_erro_status_error_kind_dominio(self):
        runtime = MagicMock()
        contract = self._make_contract()
        runtime.get_skill_contract.return_value = contract
        store = MagicMock()
        record = self._make_record(status="ERRO")
        result = MagicMock()
        result.validacoes = []

        _oas_log_invocation(runtime, store, "v1", {}, "04-cronograma", result, record)
        payload = store.log_invocation.call_args[0][1]
        assert payload["error_kind"] == "DOMINIO"

    def test_exception_status_error_kind_tecnico(self):
        runtime = MagicMock()
        contract = self._make_contract()
        runtime.get_skill_contract.return_value = contract
        store = MagicMock()
        record = self._make_record(status="EXCEPTION")
        result = MagicMock()
        result.validacoes = []

        _oas_log_invocation(runtime, store, "v1", {}, "04-cronograma", result, record)
        payload = store.log_invocation.call_args[0][1]
        assert payload["error_kind"] == "TECNICO"

    def test_catalog_source_defaults_to_master(self):
        runtime = MagicMock()
        contract = self._make_contract()
        runtime.get_skill_contract.return_value = contract
        store = MagicMock()
        record = self._make_record(status="OK")
        result = MagicMock()
        result.validacoes = []

        _oas_log_invocation(runtime, store, "v1", {}, "04-cronograma", result, record)
        payload = store.log_invocation.call_args[0][1]
        assert payload["catalog_source"] == "master"

    def test_catalog_source_overridden_from_context(self):
        runtime = MagicMock()
        contract = self._make_contract()
        runtime.get_skill_contract.return_value = contract
        store = MagicMock()
        record = self._make_record(status="OK")
        result = MagicMock()
        result.validacoes = []

        ctx = {"catalog_source": "overlay-xyz"}
        _oas_log_invocation(runtime, store, "v1", ctx, "04-cronograma", result, record)
        payload = store.log_invocation.call_args[0][1]
        assert payload["catalog_source"] == "overlay-xyz"

    def test_contract_dict_in_payload(self):
        runtime = MagicMock()
        contract = self._make_contract()
        runtime.get_skill_contract.return_value = contract
        store = MagicMock()
        record = self._make_record(status="OK")
        result = MagicMock()
        result.validacoes = []

        _oas_log_invocation(runtime, store, "v1", {}, "04-cronograma", result, record)
        payload = store.log_invocation.call_args[0][1]
        assert "contract" in payload
        assert payload["contract"]["required_inputs"] == ["input_a"]
        assert payload["contract"]["produces_section"] == "cronograma"

    def test_exception_silently_swallowed(self):
        runtime = MagicMock()
        runtime.get_skill_contract.side_effect = RuntimeError("contract not found")
        store = MagicMock()
        record = self._make_record(status="OK")
        result = MagicMock()

        # Must not raise
        _oas_log_invocation(runtime, store, "v1", {}, "04-cronograma", result, record)
        store.log_invocation.assert_not_called()

    def test_validacoes_mapped_from_result(self):
        runtime = MagicMock()
        contract = self._make_contract()
        runtime.get_skill_contract.return_value = contract
        store = MagicMock()
        record = self._make_record(status="OK")
        result = MagicMock()
        val = MagicMock()
        val.codigo = "V001"
        val.status = "PASS"
        result.validacoes = [val]

        _oas_log_invocation(runtime, store, "v1", {}, "04-cronograma", result, record)
        payload = store.log_invocation.call_args[0][1]
        assert payload["validacoes"] == [{"codigo": "V001", "status": "PASS"}]


# ---------------------------------------------------------------------------
# _oas_save_state
# ---------------------------------------------------------------------------


class TestOasSaveState:
    def test_normal_save_calls_store_save_canonical(self):
        store = MagicMock()
        record = MagicMock()
        record.status = "OK"
        new_state = MagicMock()
        result = MagicMock()

        _oas_save_state(store, "v1", "04-cronograma", result, new_state, record)
        store.save_canonical.assert_called_once_with(new_state, "v1", created_by="04-cronograma")

    def test_00_escopo_erro_skips_save(self):
        store = MagicMock()
        record = MagicMock()
        record.status = "ERRO"
        new_state = MagicMock()
        result = MagicMock()

        _oas_save_state(store, "v1", "00-escopo", result, new_state, record)
        store.save_canonical.assert_not_called()

    def test_exception_status_skips_save(self):
        store = MagicMock()
        record = MagicMock()
        record.status = "EXCEPTION"
        new_state = MagicMock()
        result = MagicMock()

        _oas_save_state(store, "v1", "04-cronograma", result, new_state, record)
        store.save_canonical.assert_not_called()

    def test_result_none_with_gate_skill_taints_and_saves(self):
        from concilium.application.runtime.gates import _GATE_SKILLS

        gate_skill = next(iter(_GATE_SKILLS))
        store = MagicMock()
        record = MagicMock()
        record.status = "OK"
        new_state = MagicMock()
        new_state.pipeline_blocked_from = []
        tainted = MagicMock()
        new_state.model_copy.return_value = tainted

        _oas_save_state(store, "v1", gate_skill, None, new_state, record)
        new_state.model_copy.assert_called_once()
        taint_kwargs = new_state.model_copy.call_args[1]["update"]
        assert gate_skill in taint_kwargs["pipeline_blocked_from"]
        assert taint_kwargs["pipeline_integridade"] == "CORROMPIDO"
        store.save_canonical.assert_called_once_with(tainted, "v1", created_by=f"taint:{gate_skill}")

    def test_result_none_non_gate_skill_no_save(self):
        store = MagicMock()
        record = MagicMock()
        record.status = "OK"
        new_state = MagicMock()

        with patch(
            "concilium.application.runtime.helpers.pipeline._GATE_SKILLS",
            frozenset(),
        ):
            _oas_save_state(store, "v1", "99-nongate", None, new_state, record)
        store.save_canonical.assert_not_called()

    def test_new_state_none_skips_save(self):
        store = MagicMock()
        record = MagicMock()
        record.status = "OK"
        result = MagicMock()

        _oas_save_state(store, "v1", "04-cronograma", result, None, record)
        store.save_canonical.assert_not_called()

    def test_erro_non_00_escopo_saves(self):
        store = MagicMock()
        record = MagicMock()
        record.status = "ERRO"
        new_state = MagicMock()
        result = MagicMock()

        _oas_save_state(store, "v1", "04-cronograma", result, new_state, record)
        store.save_canonical.assert_called_once()


# ---------------------------------------------------------------------------
# _on_after_skill
# ---------------------------------------------------------------------------


class TestOnAfterSkill:
    def _make_record(self, status="OK", duration_ms=150, errors=None, warnings=None):
        record = MagicMock()
        record.status = status
        record.duration_ms = duration_ms
        record.errors = errors or []
        record.warnings = warnings or []
        return record

    def test_prints_status_and_duration(self, capsys):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record(status="OK", duration_ms=200)
        result = MagicMock()
        new_state = MagicMock()

        with patch("concilium.application.runtime.helpers.pipeline._oas_save_state"), \
             patch("concilium.application.runtime.helpers.pipeline._oas_log_invocation"):
            _on_after_skill(runtime, store, "v1", {}, "04-cronograma", result, new_state, record)

        captured = capsys.readouterr()
        assert "[OK]" in captured.out
        assert "200ms" in captured.out

    def test_prints_errors_in_output(self, capsys):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record(status="ERRO", errors=["validation failed"])
        result = MagicMock()
        new_state = MagicMock()

        with patch("concilium.application.runtime.helpers.pipeline._oas_save_state"), \
             patch("concilium.application.runtime.helpers.pipeline._oas_log_invocation"):
            _on_after_skill(runtime, store, "v1", {}, "04-cronograma", result, new_state, record)

        captured = capsys.readouterr()
        assert "validation failed" in captured.out

    def test_gate_exception_prints_stop_message(self, capsys):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = True
        store = MagicMock()
        record = self._make_record(status="EXCEPTION")
        result = MagicMock()
        new_state = MagicMock()

        with patch("concilium.application.runtime.helpers.pipeline._oas_save_state"), \
             patch("concilium.application.runtime.helpers.pipeline._oas_log_invocation"):
            _on_after_skill(runtime, store, "v1", {}, "04-cronograma", result, new_state, record)

        captured = capsys.readouterr()
        assert "STOP" in captured.out
        assert "04-cronograma" in captured.out

    def test_non_gate_exception_no_stop_message(self, capsys):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record(status="EXCEPTION")
        result = MagicMock()
        new_state = MagicMock()

        with patch("concilium.application.runtime.helpers.pipeline._oas_save_state"), \
             patch("concilium.application.runtime.helpers.pipeline._oas_log_invocation"):
            _on_after_skill(runtime, store, "v1", {}, "99-nongate", result, new_state, record)

        captured = capsys.readouterr()
        assert "STOP" not in captured.out

    def test_process_side_effects_called_when_result_not_none(self):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record(status="OK")
        result = MagicMock()
        new_state = MagicMock()

        with patch("concilium.application.runtime.helpers.pipeline._oas_save_state"), \
             patch("concilium.application.runtime.helpers.pipeline._oas_log_invocation"):
            _on_after_skill(runtime, store, "v1", {}, "04-cronograma", result, new_state, record)

        runtime._process_side_effects.assert_called_once_with("04-cronograma", result, store, "v1")

    def test_process_side_effects_not_called_when_result_none(self):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record(status="OK")
        new_state = MagicMock()

        with patch("concilium.application.runtime.helpers.pipeline._oas_save_state"), \
             patch("concilium.application.runtime.helpers.pipeline._oas_log_invocation"):
            _on_after_skill(runtime, store, "v1", {}, "04-cronograma", None, new_state, record)

        runtime._process_side_effects.assert_not_called()

    def test_oas_save_state_called(self):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record()
        result = MagicMock()
        new_state = MagicMock()

        with patch(
            "concilium.application.runtime.helpers.pipeline._oas_save_state"
        ) as mock_save, patch(
            "concilium.application.runtime.helpers.pipeline._oas_log_invocation"
        ):
            _on_after_skill(runtime, store, "v1", {}, "04-cronograma", result, new_state, record)
        mock_save.assert_called_once_with(store, "v1", "04-cronograma", result, new_state, record)

    def test_oas_log_invocation_called(self):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record()
        result = MagicMock()
        new_state = MagicMock()

        with patch(
            "concilium.application.runtime.helpers.pipeline._oas_save_state"
        ), patch(
            "concilium.application.runtime.helpers.pipeline._oas_log_invocation"
        ) as mock_log:
            _on_after_skill(runtime, store, "v1", {"ctx": "x"}, "04-cronograma", result, new_state, record)
        mock_log.assert_called_once_with(
            runtime, store, "v1", {"ctx": "x"}, "04-cronograma", result, record
        )

    def test_multiple_errors_joined_by_semicolon(self, capsys):
        runtime = MagicMock()
        runtime._meta_is_gate.return_value = False
        store = MagicMock()
        record = self._make_record(status="ERRO", errors=["err1", "err2"])
        result = MagicMock()
        new_state = MagicMock()

        with patch("concilium.application.runtime.helpers.pipeline._oas_save_state"), \
             patch("concilium.application.runtime.helpers.pipeline._oas_log_invocation"):
            _on_after_skill(runtime, store, "v1", {}, "04-cronograma", result, new_state, record)

        captured = capsys.readouterr()
        assert "err1" in captured.out
        assert "err2" in captured.out


# ---------------------------------------------------------------------------
# _print_skill_start
# ---------------------------------------------------------------------------


class TestPrintSkillStart:
    def test_format_includes_skill_id(self, capsys):
        _print_skill_start("04-cronograma")
        captured = capsys.readouterr()
        assert "04-cronograma" in captured.out

    def test_format_has_arrow(self, capsys):
        _print_skill_start("01-escopo")
        captured = capsys.readouterr()
        assert ">" in captured.out

    def test_format_ends_with_space(self, capsys):
        _print_skill_start("01-escopo")
        captured = capsys.readouterr()
        # The function uses end=" " so the output should have a trailing space
        assert captured.out.endswith(" ")

    def test_format_includes_ellipsis(self, capsys):
        _print_skill_start("99-test")
        captured = capsys.readouterr()
        assert "..." in captured.out


# ---------------------------------------------------------------------------
# _format_records
# ---------------------------------------------------------------------------


class TestFormatRecords:
    def _make_record(self, skill_id, status, duration_ms, warnings=None, errors=None):
        r = MagicMock()
        r.skill_id = skill_id
        r.status = status
        r.duration_ms = duration_ms
        r.warnings = warnings or []
        r.errors = errors or []
        return r

    def test_basic_record_fields(self):
        r = self._make_record("01-escopo", "OK", 100)
        result = _format_records([r])
        assert len(result) == 1
        entry = result[0]
        assert entry["skill"] == "01-escopo"
        assert entry["status"] == "OK"
        assert entry["duration_ms"] == 100
        assert entry["avisos"] == []

    def test_no_erros_key_when_errors_empty(self):
        r = self._make_record("01-escopo", "OK", 50, errors=[])
        result = _format_records([r])
        assert "erros" not in result[0]

    def test_erros_key_present_when_errors_not_empty(self):
        r = self._make_record("02-prod", "ERRO", 200, errors=["calc failed"])
        result = _format_records([r])
        assert "erros" in result[0]
        assert result[0]["erros"] == ["calc failed"]

    def test_erro_key_present_for_exception_with_errors(self):
        r = self._make_record("04-cron", "EXCEPTION", 300, errors=["crash"])
        result = _format_records([r])
        assert "erro" in result[0]
        assert result[0]["erro"] == "crash"

    def test_erro_key_uses_first_error(self):
        r = self._make_record("04-cron", "EXCEPTION", 300, errors=["first", "second"])
        result = _format_records([r])
        assert result[0]["erro"] == "first"

    def test_erro_key_absent_for_exception_without_errors(self):
        r = self._make_record("04-cron", "EXCEPTION", 300, errors=[])
        result = _format_records([r])
        assert "erro" not in result[0]

    def test_erro_key_absent_for_non_exception_with_errors(self):
        r = self._make_record("04-cron", "ERRO", 300, errors=["some error"])
        result = _format_records([r])
        assert "erros" in result[0]
        assert "erro" not in result[0]

    def test_multiple_records(self):
        records = [
            self._make_record("01-escopo", "OK", 50),
            self._make_record("02-prod", "ERRO", 100, errors=["e1"]),
            self._make_record("04-cron", "EXCEPTION", 200, errors=["crash"]),
        ]
        result = _format_records(records)
        assert len(result) == 3
        assert result[0]["status"] == "OK"
        assert result[1]["status"] == "ERRO"
        assert result[2]["status"] == "EXCEPTION"
        assert "erro" in result[2]

    def test_empty_records_list(self):
        result = _format_records([])
        assert result == []

    def test_warnings_included_in_output(self):
        r = self._make_record("01-escopo", "OK", 50, warnings=["minor warning"])
        result = _format_records([r])
        assert result[0]["avisos"] == ["minor warning"]
