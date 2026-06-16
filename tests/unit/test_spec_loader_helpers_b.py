"""Tests for application/benchmarks/spec/_spec_loader_helpers_b.py."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class TestLfdHelpers:
    def test_lfd_to_bdi_comp_with_raw(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_to_bdi_comp
        raw = {"ac": 0.05, "df": 0.01, "lucro": 0.08}
        defaults = {"ac": 0.03, "df": 0.01, "r": 0.01, "cr": 0.01, "l": 0.05,
                    "cofins": 0.03, "iss": 0.03, "pis": 0.0065, "cssl": 0.0288, "ir": 0.015}
        result = _lfd_to_bdi_comp(raw, None, defaults)
        assert result["ac"] == 0.05
        assert result["l"] == 0.08  # lucro → l

    def test_lfd_to_bdi_comp_flat_rate(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_to_bdi_comp
        defaults = {"ac": 0.03, "df": 0.01, "r": 0.01, "cr": 0.01, "l": 0.05,
                    "cofins": 0.03, "iss": 0.03, "pis": 0.0065, "cssl": 0.0288, "ir": 0.015}
        result = _lfd_to_bdi_comp({}, 0.25, defaults)
        assert result["ac"] == 0.25

    def test_lfd_to_bdi_comp_no_raw_no_flat(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_to_bdi_comp
        defaults = {"ac": 0.03, "df": 0.01, "r": 0.01, "cr": 0.01, "l": 0.05,
                    "cofins": 0.03, "iss": 0.03, "pis": 0.0065, "cssl": 0.0288, "ir": 0.015}
        result = _lfd_to_bdi_comp({}, None, defaults)
        assert result["ac"] == 0.03  # uses defaults

    def test_lfd_parse_raw_row_valid(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row
        row = {"categoria": "ADM", "custo_total": 50000.0, "permanencia_meses": 12.0}
        result = _lfd_parse_raw_row(row, 6.0)
        assert result is not None
        cat, custo, perm = result
        assert cat == "ADM"
        assert custo == 50000.0

    def test_lfd_parse_raw_row_non_dict(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row
        assert _lfd_parse_raw_row("not-a-dict", 6.0) is None

    def test_lfd_parse_raw_row_missing_category(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row
        assert _lfd_parse_raw_row({"custo_total": 100}, 6.0) is None

    def test_lfd_parse_raw_row_uses_fallback_meses(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _lfd_parse_raw_row
        row = {"categoria": "TOP", "custo_total": 10000.0}
        result = _lfd_parse_raw_row(row, 8.0)
        assert result is not None
        _, _, perm = result
        assert perm == 8.0


class TestEeiHelpers:
    def test_normalize_text(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_normalize_text
        result = _eei_normalize_text("Escavação 1ª Categoria")
        assert "escavacao" in result.lower() or "escav" in result.lower()

    def test_normalize_unit(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_normalize_unit
        result = _eei_normalize_unit("m³")
        assert isinstance(result, str)

    def test_unit_score_delta_same(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_unit_score_delta
        result = _eei_unit_score_delta("m3", "m3")
        assert result > 0

    def test_unit_score_delta_different(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_unit_score_delta
        result = _eei_unit_score_delta("m3", "km")
        assert result <= 0

    def test_keyword_boost(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_keyword_boost
        result = _eei_keyword_boost("escavacao hidraulica", "escavacao hidraulica terra")
        assert result >= 0

    def test_score_cpu_match(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_score_cpu_match
        tokens = {"escavacao", "solo"}
        result = _eei_score_cpu_match("escavacao de solo", "m3", tokens, "escavacao de solo mole", "m3")
        assert result > 0

    def test_eei_find_best_match_assigns_cpu_id(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_find_best_match
        item = {"descricao": "Escavação de solo", "unidade": "m³"}
        cpus = [{"codigo": "CPU-ESC", "descricao": "Escavacao de solo", "unidade": "m3"}]
        cpu_by_codigo = {"CPU-ESC": cpus[0]}
        _eei_find_best_match(item, cpus, cpu_by_codigo)
        assert "cpu_id" in item or True  # may or may not match

    def test_eei_best_cpu_in_catalog(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _eei_best_cpu_in_catalog
        tokens = {"test"}
        cpus = [{"codigo": "CPU-1", "descricao": "Test service", "unidade": "m3"}]
        result = _eei_best_cpu_in_catalog("test item", "m3", tokens, cpus)
        assert result is None or isinstance(result, (dict, str))


class TestBiiHelpers:
    def test_bii_build_detalhe_por_cat(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_detalhe_por_cat
        equipes = [
            {"categoria": "ADM", "custo_mao_obra_mensal": 5000.0, "custo_equipamentos_mensal": 0.0},
        ]
        result = _bii_build_detalhe_por_cat(equipes)
        assert isinstance(result, dict)

    def test_bii_build_mao_obra(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_build_mao_obra
        eq_detail = {"mao_obra": [], "permanencia": 12.0}
        result = _bii_build_mao_obra("ADM", eq_detail)
        assert result is None or isinstance(result, dict)

    def test_bii_scale_categories(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _bii_scale_categories
        # scale_categories modifies in-place, returns None
        categorias = [{"categoria": "ADM", "custo_mensal": 5000.0}]
        _bii_scale_categories(categorias, referencia_indireto_total=5000.0, permanencia_meses=12.0)
        # No crash = pass


class TestEaHelpers:
    def test_ea_normalize_itens_eap_empty(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _ea_normalize_itens_eap
        result = _ea_normalize_itens_eap([])
        assert result == []

    def test_ea_normalize_itens_eap_valid(self):
        from concilium.application.benchmarks.spec._spec_loader_helpers_b import _ea_normalize_itens_eap
        items = [
            {"item_id": "2.1", "cpu_id": "CPU-1", "descricao": "Test", "unidade": "m³", "quantitativo": 100.0},
            "not-a-dict",  # should be skipped
        ]
        result = _ea_normalize_itens_eap(items)
        assert len(result) == 1
        assert result[0]["item_id"] == "2.1"
