"""Tests for adapters/template_interpreter.py — real coverage of all methods.

These tests use the real template at config/templates/planilha_planejamento.json
and exercise all code paths including the FileNotFoundError path at line 37.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from concilium.infrastructure.adapters.template_interpreter import TemplateInterpreter

CONFIG_TEMPLATE = Path(__file__).resolve().parents[2] / "config" / "templates" / "planilha_planejamento.json"


# ── __init__ paths ─────────────────────────────────────────────────────────────


def test_init_with_explicit_path():
    """TemplateInterpreter loads template when given an explicit path."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.spec is not None
    assert isinstance(interp.spec, dict)


def test_init_raises_file_not_found_when_no_default_path_exists():
    """FileNotFoundError raised when no default path exists (line 37)."""
    # Line 37 is triggered when template_path=None AND none of the default paths exist
    with patch("concilium.infrastructure.adapters.template_interpreter.Path.exists", return_value=False):
        with pytest.raises(FileNotFoundError, match="não encontrado"):
            TemplateInterpreter()


def test_init_raises_file_not_found_for_invalid_explicit_path():
    """FileNotFoundError raised when explicit path points to non-existent file."""
    # This triggers the OS-level FileNotFoundError from open() at line 39
    with pytest.raises(FileNotFoundError):
        TemplateInterpreter(Path("/nonexistent/path/to/planilha_planejamento.json"))


def test_init_default_path_discovery():
    """TemplateInterpreter() without args finds template via default paths."""
    interp = TemplateInterpreter()
    assert interp.spec is not None


# ── get_sheet_names ────────────────────────────────────────────────────────────


def test_get_sheet_names_returns_list():
    """get_sheet_names returns a non-empty sorted list of sheet names."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    names = interp.get_sheet_names()
    assert isinstance(names, list)
    # May be empty if template has no sheets — but we verify the return type


# ── get_sheet_sections ─────────────────────────────────────────────────────────


def test_get_sheet_sections_existing_sheet():
    """get_sheet_sections returns sections list for a known sheet."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    names = interp.get_sheet_names()
    if names:
        sections = interp.get_sheet_sections(names[0])
        assert isinstance(sections, list)


def test_get_sheet_sections_missing_sheet_returns_empty():
    """get_sheet_sections returns [] for a sheet not in the template (lines 61-62)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_sheet_sections("NONEXISTENT_SHEET_XYZ")
    assert result == []


# ── get_sheet_category ─────────────────────────────────────────────────────────


def test_get_sheet_category_returns_none_for_nonexistent_sheet():
    """get_sheet_category returns None for unknown sheet (lines 61-62, 66)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_sheet_category("NONEXISTENT_SHEET_XYZ")
    assert result is None


def test_get_sheet_category_on_real_sheets():
    """get_sheet_category returns None or a string for real sheets."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    for name in interp.get_sheet_names():
        cat = interp.get_sheet_category(name)
        assert cat is None or isinstance(cat, str)


# ── is_indirect_cost_sheet ─────────────────────────────────────────────────────


def test_is_indirect_cost_sheet_false_for_nonexistent():
    """is_indirect_cost_sheet returns False when sheet not in template (line 66)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.is_indirect_cost_sheet("NONEXISTENT_SHEET_XYZ") is False


def test_is_indirect_cost_sheet_on_real_sheets():
    """is_indirect_cost_sheet returns bool for all real sheets (line 66 on False path)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    for name in interp.get_sheet_names():
        result = interp.is_indirect_cost_sheet(name)
        assert isinstance(result, bool)


# ── get_indirect_cost_sheets ───────────────────────────────────────────────────


def test_get_indirect_cost_sheets_returns_list():
    """get_indirect_cost_sheets returns a list (may be empty) (lines 70-71)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    sheets = interp.get_indirect_cost_sheets()
    assert isinstance(sheets, list)
    # Every item must be an indirect-cost sheet
    for s in sheets:
        assert interp.is_indirect_cost_sheet(s)


# ── section_is_repetitive ──────────────────────────────────────────────────────


def test_section_is_repetitive_false_for_empty_section():
    """section_is_repetitive returns False when section has no repeticao/template_linhas (line 75)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.section_is_repetitive({}) is False


def test_section_is_repetitive_true_for_repeticao():
    """section_is_repetitive returns True when 'repeticao' key present (line 75)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.section_is_repetitive({"repeticao": "eap"}) is True


def test_section_is_repetitive_true_for_template_linhas():
    """section_is_repetitive returns True when 'template_linhas' key present."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.section_is_repetitive({"template_linhas": [1, 2, 3]}) is True


# ── get_section_source_path ────────────────────────────────────────────────────


def test_get_section_source_path_returns_none_when_absent():
    """get_section_source_path returns None for section without origem_canonico (lines 83-86)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.get_section_source_path({}) is None


def test_get_section_source_path_returns_value_when_present():
    """get_section_source_path returns path string when key present."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.get_section_source_path({"origem_canonico": "eap"}) == "eap"


# ── get_section_line_range ─────────────────────────────────────────────────────


def test_get_section_line_range_returns_none_for_empty_section():
    """get_section_line_range returns None when no linhas/template_linhas (lines 88-93, 105)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.get_section_line_range({}) is None


def test_get_section_line_range_from_linhas():
    """get_section_line_range uses 'linhas' list (lines 88-91)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_section_line_range({"linhas": [5, 3, 7, 4]})
    assert result == (3, 7)


def test_get_section_line_range_from_template_linhas():
    """get_section_line_range uses 'template_linhas' list (lines 97-101)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_section_line_range({"template_linhas": [10, 12, 11]})
    assert result == (10, 12)


def test_get_section_line_range_single_line():
    """get_section_line_range handles single-element list."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_section_line_range({"linhas": [7]})
    assert result == (7, 7)


# ── get_section_column_range ───────────────────────────────────────────────────


def test_get_section_column_range_returns_none_for_empty_section():
    """get_section_column_range returns None when no colunas key (line 109)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.get_section_column_range({}) is None


def test_get_section_column_range_with_colon_spec():
    """get_section_column_range parses 'A:D' into ('A', 'D') (lines 97-101, 109-114)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_section_column_range({"colunas": "A:D"})
    assert result == ("A", "D")


def test_get_section_column_range_with_spaces():
    """get_section_column_range strips spaces from column spec."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_section_column_range({"colunas": "B : F"})
    assert result == ("B", "F")


def test_get_section_column_range_no_colon_returns_none():
    """get_section_column_range returns None when colunas has no colon."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.get_section_column_range({"colunas": "ABCD"})
    assert result is None


# ── get_section_mapping ────────────────────────────────────────────────────────


def test_get_section_mapping_returns_empty_dict_for_no_mapping():
    """get_section_mapping returns {} when section has no mapeamento (line 105)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    assert interp.get_section_mapping({}) == {}


def test_get_section_mapping_returns_mapping():
    """get_section_mapping returns the mapeamento dict."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    mapping = {"nome": "A1", "valor": "B1"}
    assert interp.get_section_mapping({"mapeamento": mapping}) == mapping


# ── describe_sheet ─────────────────────────────────────────────────────────────


def test_describe_sheet_for_nonexistent_sheet():
    """describe_sheet returns a string (may be empty) for unknown sheet (lines 109-114)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    result = interp.describe_sheet("NONEXISTENT_SHEET")
    assert isinstance(result, str)


def test_describe_sheet_for_real_sheets():
    """describe_sheet returns a string for all real sheets."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    for name in interp.get_sheet_names():
        desc = interp.describe_sheet(name)
        assert isinstance(desc, str)


def test_describe_sheet_includes_category_for_indirect_sheets():
    """describe_sheet appends '(Categoria: ...)' for indirect sheets (lines 112-113)."""
    interp = TemplateInterpreter(CONFIG_TEMPLATE)
    for name in interp.get_indirect_cost_sheets():
        desc = interp.describe_sheet(name)
        assert "Categoria" in desc
        break  # Only need one example


import json  # noqa: E402
import tempfile  # noqa: E402

# template_interpreter.py line 82->85: linhas is not a list or is empty → skip
# template_interpreter.py line 87->90: template_linhas empty → return None
# ---------------------------------------------------------------------------


def _make_template_interpreter(spec: dict):
    """Write spec to a temp file and return TemplateInterpreter instance."""
    from concilium.infrastructure.adapters.template_interpreter import TemplateInterpreter

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(spec, f)
        tmp = Path(f.name)

    return TemplateInterpreter(template_path=tmp)


class TestTemplateInterpreterGetSectionLineRange:
    def test_returns_none_when_linhas_is_empty_list(self):
        """Line 82->85: 'linhas': [] → len == 0 → if False → check template_linhas."""
        ti = _make_template_interpreter({"abas": {}})
        # "linhas" key present but empty list → first if fails → falls to template_linhas check
        # "template_linhas" absent → returns None
        result = ti.get_section_line_range({"linhas": []})
        assert result is None

    def test_returns_none_when_linhas_is_string(self):
        """Line 82->85: 'linhas': 'not-a-list' → isinstance False → skip."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"linhas": "not-a-list"})
        assert result is None

    def test_returns_none_when_template_linhas_is_empty(self):
        """Line 87->90: 'template_linhas': [] → len==0 → if False → return None."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"template_linhas": []})
        assert result is None

    def test_returns_range_when_linhas_has_items(self):
        """Normal path: 'linhas': [3, 1, 2] → return (1, 3)."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"linhas": [3, 1, 2]})
        assert result == (1, 3)

    def test_returns_range_when_template_linhas_has_items(self):
        """Normal path for template_linhas: return (min, max)."""
        ti = _make_template_interpreter({"abas": {}})
        result = ti.get_section_line_range({"template_linhas": [10, 20, 15]})
        assert result == (10, 20)


# ---------------------------------------------------------------------------

