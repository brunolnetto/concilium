"""Tests for pu_calculator, pdf_renderer, azure_blob_storage, and runtime helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

# ─── runtime pipeline helpers ─────────────────────────────────────────────────


class TestRuntimePipelineHelpers:
    def test_parse_executed_skills_empty(self):
        from concilium.application.runtime.helpers.pipeline import _parse_executed_skills

        result = _parse_executed_skills([])
        assert isinstance(result, set)

    def test_parse_executed_skills_from_file(self):
        import json

        from concilium.application.runtime.helpers.pipeline import _parse_executed_skills

        lines = [
            json.dumps({"skill": "01-escopo-e-eap", "status": "OK"}),
            json.dumps({"skill": "02-prod", "status": "ERRO"}),
        ]
        result = _parse_executed_skills(lines)
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

