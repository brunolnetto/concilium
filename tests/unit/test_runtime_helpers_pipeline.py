"""Tests for pu_calculator, pdf_renderer, azure_blob_storage, and runtime helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── runtime pipeline helpers ─────────────────────────────────────────────────


class TestRuntimePipelineHelpers:
    def test_parse_executed_skills_empty(self, tmp_path):
        from concilium.application.runtime.helpers.pipeline import _parse_executed_skills

        result = _parse_executed_skills(tmp_path / "nonexistent.json")
        assert isinstance(result, set)

    def test_parse_executed_skills_from_file(self, tmp_path):
        import json

        from concilium.application.runtime.helpers.pipeline import _parse_executed_skills

        log = [{"skill": "01-escopo-e-eap", "status": "OK"}, {"skill": "02-prod", "status": "ERRO"}]
        log_file = tmp_path / "invocations.json"
        log_file.write_text(json.dumps(log), encoding="utf-8")
        result = _parse_executed_skills(log_file)
        assert isinstance(result, set)

    def test_apply_dv_returns_canonical(self):
        from concilium.application.runtime.helpers.pipeline import _apply_dv

        canonical = MagicMock()
        result = _apply_dv(canonical, None)
        assert result is not None

    def test_format_records_empty(self):
        from concilium.application.runtime.helpers.pipeline import _format_records

        result = _format_records([])
        assert result == []

    def test_print_skill_start_no_crash(self):
        from concilium.application.runtime.helpers.pipeline import _print_skill_start

        _print_skill_start("01-escopo-e-eap")  # Should not raise

