"""Tests for ADR-064 — No Raw JSON Editing in UI.

Covers:
  F1: catalogo_page.py has no st.text_area + json.loads
  F2: lint_report._scan_raw_json_ui detects the antipattern
  F3: form_contracts FieldSpec + render_typed_form contract
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

import pytest

# ─── F1: catalogo_page.py is clean ───────────────────────────────────────────


class TestCatalogoPageNoRawJson:
    CATALOGO_PAGE = Path(__file__).resolve().parents[2] / "src/concilium/presentation/ui/templates/catalogo_page.py"

    def test_no_text_area_with_json_dumps(self):
        """catalogo_page.py must not pass json.dumps output to st.text_area."""
        source = self.CATALOGO_PAGE.read_text(encoding="utf-8")
        # Check no function simultaneously has text_area and json.loads
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            func_src = ast.get_source_segment(source, node) or ""
            has_text_area = bool(re.search(r"\bst\.text_area\b", func_src))
            has_json_loads = bool(re.search(r"\bjson\.loads\b", func_src))
            assert not (has_text_area and has_json_loads), (
                f"Function '{node.name}' in catalogo_page.py still uses st.text_area + json.loads (ADR-064 violation)"
            )

    def test_payload_not_from_user_text(self):
        """Payload to API should not be built from json.loads(user_text)."""
        source = self.CATALOGO_PAGE.read_text(encoding="utf-8")
        # Pattern: json.loads(variable_from_text_area)
        assert "json.loads(cpu_json)" not in source, (
            "catalogo_page.py still uses json.loads(cpu_json) — ADR-064 violation"
        )

    def test_inspect_json_is_readonly(self):
        """Read-only JSON inspection must use st.json() not st.text_area."""
        source = self.CATALOGO_PAGE.read_text(encoding="utf-8")
        assert "st.json(cpu_data)" in source, "catalogo_page.py should have st.json(cpu_data) for read-only inspection"

    def test_uses_render_typed_form(self):
        """catalogo_page.py must use render_typed_form for CPU editing."""
        source = self.CATALOGO_PAGE.read_text(encoding="utf-8")
        assert "render_typed_form" in source, "catalogo_page.py must call render_typed_form() (ADR-064)"


# ─── F2: lint scanner detects antipattern ────────────────────────────────────


class TestLintRawJsonScanner:
    def test_detects_antipattern_in_synthetic_file(self, tmp_path):
        """Scanner finds st.text_area + json.loads in same function."""
        from scripts.lint_report import _scan_raw_json_ui

        bad_file = tmp_path / "bad_ui.py"
        bad_file.write_text(
            textwrap.dedent("""
            import json
            import streamlit as st

            def edit_object():
                raw = st.text_area("Edit JSON", value="{}")
                obj = json.loads(raw)
                return obj
        """),
            encoding="utf-8",
        )

        hits = _scan_raw_json_ui(tmp_path)
        assert len(hits) == 1
        assert hits[0]["code"] == "UI-JSON-RAW"
        assert hits[0]["function"] == "edit_object"
        assert hits[0]["category"] == "ui-json-raw"

    def test_no_false_positive_when_separate_functions(self, tmp_path):
        """text_area in one function, json.loads in another — NOT a violation."""
        from scripts.lint_report import _scan_raw_json_ui

        ok_file = tmp_path / "ok_ui.py"
        ok_file.write_text(
            textwrap.dedent("""
            import json
            import streamlit as st

            def render_form():
                motivo = st.text_area("Motivo")
                return motivo

            def load_data(text):
                return json.loads(text)
        """),
            encoding="utf-8",
        )

        hits = _scan_raw_json_ui(tmp_path)
        assert hits == []

    def test_no_false_positive_for_readonly_st_json(self, tmp_path):
        """st.json() display (no text_area) is NOT a violation."""
        from scripts.lint_report import _scan_raw_json_ui

        ok_file = tmp_path / "readonly_ui.py"
        ok_file.write_text(
            textwrap.dedent("""
            import json
            import streamlit as st

            def inspect_object(data):
                st.json(data)
                processed = json.loads(json.dumps(data))  # deep copy, not user input
                return processed
        """),
            encoding="utf-8",
        )

        hits = _scan_raw_json_ui(tmp_path)
        assert hits == []

    @pytest.mark.slow
    def test_ui_directory_is_clean(self):
        """The actual UI directory has zero UI-JSON-RAW violations."""
        from scripts.lint_report import _scan_raw_json_ui

        ui_root = Path(__file__).resolve().parents[2] / "src/concilium/presentation/ui"
        hits = _scan_raw_json_ui(ui_root)
        assert hits == [], "UI-JSON-RAW violations found (ADR-064):\n" + "\n".join(
            f"  {h['file']}:{h['line']} — {h['function']}" for h in hits
        )


# ─── F3: form_contracts contract ─────────────────────────────────────────────


class TestFormContracts:
    @pytest.mark.slow
    def test_field_spec_defaults(self):
        from concilium.presentation.ui.atoms.form_contracts import FieldSpec

        spec = FieldSpec(label="Descrição")
        assert spec.widget == "text_input"
        assert spec.options == []
        assert spec.min_value is None

    def test_cpu_editable_fields_has_required_keys(self):
        from concilium.presentation.ui.atoms.form_contracts import CPU_EDITABLE_FIELDS

        required = {"descricao", "unidade", "categoria", "composicao_itens"}
        assert required.issubset(CPU_EDITABLE_FIELDS.keys()), (
            f"CPU_EDITABLE_FIELDS missing: {required - CPU_EDITABLE_FIELDS.keys()}"
        )

    def test_cpu_readonly_fields_excludes_codigo(self):
        from concilium.presentation.ui.atoms.form_contracts import CPU_READONLY_FIELDS

        assert "codigo" in CPU_READONLY_FIELDS, "codigo must be read-only (user cannot change CPU code)"

    def test_cpu_internal_fields_excludes_historico(self):
        from concilium.presentation.ui.atoms.form_contracts import CPU_INTERNAL_FIELDS

        assert "historico_precos" in CPU_INTERNAL_FIELDS

    def test_selectbox_spec_has_options(self):
        from concilium.presentation.ui.atoms.form_contracts import CPU_EDITABLE_FIELDS

        unidade_spec = CPU_EDITABLE_FIELDS["unidade"]
        assert unidade_spec.widget == "selectbox"
        assert len(unidade_spec.options) > 0
        assert "m³" in unidade_spec.options

    def test_composicao_is_data_editor(self):
        from concilium.presentation.ui.atoms.form_contracts import CPU_EDITABLE_FIELDS

        comp_spec = CPU_EDITABLE_FIELDS["composicao_itens"]
        assert comp_spec.widget == "data_editor"
        assert "insumo_id" in comp_spec.columns
        assert "coeficiente" in comp_spec.columns
        assert "categoria_custo" in comp_spec.columns

    def test_editable_and_readonly_are_disjoint(self):
        """No field appears in both editable and readonly."""
        from concilium.presentation.ui.atoms.form_contracts import (
            CPU_EDITABLE_FIELDS,
            CPU_READONLY_FIELDS,
        )

        overlap = set(CPU_EDITABLE_FIELDS.keys()) & CPU_READONLY_FIELDS
        assert not overlap, f"Fields in both editable and readonly: {overlap}"

    def test_editable_and_internal_are_disjoint(self):
        from concilium.presentation.ui.atoms.form_contracts import (
            CPU_EDITABLE_FIELDS,
            CPU_INTERNAL_FIELDS,
        )

        overlap = set(CPU_EDITABLE_FIELDS.keys()) & CPU_INTERNAL_FIELDS
        assert not overlap, f"Fields in both editable and internal: {overlap}"
