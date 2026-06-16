"""Tests for pdf_renderer, financial_report_pdf, and query_engine CatalogSession."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ─── application/runtime/deliverables/reports/pdf_renderer.py ─────────────────

class TestPdfRenderer:
    def test_strip_inline_bold(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline
        result = _strip_inline("**bold text**")
        assert "bold text" in result
        assert "**" not in result

    def test_strip_inline_code(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline
        result = _strip_inline("`code`")
        assert "code" in result
        assert "`" not in result

    def test_is_table_sep_true(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep
        assert _is_table_sep("|---|---|") is True
        assert _is_table_sep("| :--- | ---: |") is True

    def test_is_table_sep_false(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep
        assert _is_table_sep("| data | row |") is False

    def test_render_table_row_no_crash(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row
        pdf = MagicMock()
        _render_table_row(pdf, "| col1 | col2 | col3 |", col_w=60.0)
        assert pdf.cell.call_count >= 1

    def test_render_markdown_pdf_empty_returns_bytes_or_none(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf
        result = render_markdown_pdf("")
        assert result is None or isinstance(result, bytes)

    def test_render_markdown_pdf_basic(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf
        md = "# Title\n\nThis is a paragraph.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
        result = render_markdown_pdf(md, title="Test Report")
        assert result is None or isinstance(result, bytes)

    def test_render_markdown_pdf_with_code_block(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf
        md = "Normal text\n\n```\ncode block\n```\n\nAfter code."
        result = render_markdown_pdf(md)
        assert result is None or isinstance(result, bytes)


# ─── application/runtime/deliverables/reports/financial_report_pdf.py ─────────

class TestFinancialReportPdf:
    def test_brl_formatting(self):
        from concilium.application.runtime.deliverables.reports.financial_report_pdf import _brl
        result = _brl(1234567.89)
        assert "." in result or "," in result

    def test_pct_formatting(self):
        from concilium.application.runtime.deliverables.reports.financial_report_pdf import _pct
        result = _pct(0.1523)
        assert "%" in result or "15" in result

    def test_safe_text_str(self):
        from concilium.application.runtime.deliverables.reports.financial_report_pdf import _safe_text
        result = _safe_text("Test String")
        assert result == "Test String"

    def test_safe_text_none(self):
        from concilium.application.runtime.deliverables.reports.financial_report_pdf import _safe_text
        result = _safe_text(None)
        assert isinstance(result, str)

    def test_render_financial_report_pdf_basic(self):
        from concilium.application.runtime.deliverables.reports.financial_report_pdf import render_financial_report_pdf
        relatorio = {
            "resumo": {"projeto": "Test Project", "tipo_obra": "Terra", "localizacao": "SP"},
            "RESULTADO": {"preco_venda_total": 1500000.0, "custo_total": 1200000.0,
                          "resultado_bruto": 300000.0, "margem_pct": 0.20},
        }
        result = render_financial_report_pdf(relatorio, title="Test Report")
        assert result is None or isinstance(result, bytes)

    def test_render_financial_report_pdf_empty(self):
        from concilium.application.runtime.deliverables.reports.financial_report_pdf import render_financial_report_pdf
        result = render_financial_report_pdf({}, title="")
        assert result is None or isinstance(result, bytes)

    def test_render_financial_report_pdf_with_image_provider(self):
        from concilium.application.runtime.deliverables.reports.financial_report_pdf import render_financial_report_pdf
        result = render_financial_report_pdf(
            {"resumo": {"projeto": "Test"}},
            title="Test",
            image_provider=lambda name: None,
        )
        assert result is None or isinstance(result, bytes)


# ─── infrastructure/catalog/query_engine.py — CatalogSession deeper paths ─────

class TestCatalogSessionDeeper:
    def _make_session(self):
        from concilium.infrastructure.catalog.query_engine import CatalogSession
        catalog = {
            "cpus": [
                {"codigo": "CPU-ESC", "descricao": "Escavacao hidraulica", "unidade": "m3",
                 "categoria": "TERRA", "producao_id_ref": "PROD-ESC",
                 "composicao_itens": [{"insumo_id": "DIESEL", "coeficiente": 2.0}]},
            ],
            "insumos": [
                {"codigo": "DIESEL", "descricao": "Diesel S10", "tipo": "COMBUSTIVEL",
                 "preco_unitario": 6.5, "unidade": "litro"},
            ],
            "producoes": [
                {"id": "PROD-ESC", "valor_horario": 50.0,
                 "composicao_padrao_equipe": {
                     "funcoes": [{"funcao_id": "OP", "num_pessoas": 1, "salario_mensal": 3000.0}],
                     "equipamentos": [{"equip_id": "ESC-HIDRA", "num_unidades": 1}],
                 }},
            ],
            "funcoes": [
                {"funcao_id": "OP", "descricao": "Operador", "salario_base": 3000.0},
            ],
        }
        return CatalogSession.from_resolved(catalog)

    def test_get_composicao_com_precos(self):
        session = self._make_session()
        result = session.get_composicao_com_precos("CPU-ESC")
        assert isinstance(result, list)

    def test_get_equipe_com_precos(self):
        session = self._make_session()
        result = session.get_equipe_com_precos("PROD-ESC")
        assert isinstance(result, dict)

    def test_find_cpus_by_categoria(self):
        session = self._make_session()
        result = session.find_cpus_by_categoria("TERRA")
        assert len(result) >= 1
        assert result[0]["codigo"] == "CPU-ESC"

    def test_find_cpus_by_categoria_no_match(self):
        session = self._make_session()
        result = session.find_cpus_by_categoria("PAVE")
        assert result == []

    def test_find_cpus_using_insumo(self):
        session = self._make_session()
        result = session.find_cpus_using_insumo("DIESEL")
        assert isinstance(result, list)

    def test_catalog_session_query(self):
        session = self._make_session()
        # query method - check it doesn't raise
        result = session.query("SELECT codigo FROM cpus LIMIT 1")
        assert isinstance(result, list)

    def test_catalog_session_get_price_stats(self):
        session = self._make_session()
        result = session.get_price_stats()
        assert isinstance(result, (dict, list))
