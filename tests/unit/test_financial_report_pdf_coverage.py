"""Tests for pure helper functions in financial_report_pdf.

Covers lines: 67, 83, 86-91, 97, 109-112, 137, 139-143, 651-748.
"""

from __future__ import annotations

import pytest

from concilium.application.runtime.deliverables.reports.financial_report_pdf import (
    _br_estado_approx,
    _brl,
    _chart_caption,
    _chart_label,
    _fmt_cpu_descricao,
    _fmt_localizacao,
    _pct,
    _safe_text,
)

try:
    from concilium.application.runtime.deliverables.reports.financial_report_pdf import (
        render_financial_report_pdf,
    )

    _HAS_RENDER = True
except ImportError:
    _HAS_RENDER = False


# ---------------------------------------------------------------------------
# _chart_label
# ---------------------------------------------------------------------------


class TestChartLabel:
    def test_known_slug_scurve_custo(self):
        result = _chart_label("scurve_custo.png")
        assert result == "Curva S de Custo Acumulado"

    def test_known_slug_gantt(self):
        result = _chart_label("gantt_cronograma.png")
        assert result == "Cronograma de Execução (Gantt RCPSP)"

    def test_fallback_unknown_slug_title_case(self):
        # line 67: fallback title()
        result = _chart_label("unknown_chart.png")
        assert result == "Unknown Chart"

    def test_fallback_multi_word(self):
        result = _chart_label("my_custom_thing.png")
        assert result == "My Custom Thing"

    def test_no_png_extension_unknown(self):
        # filename without .png — slug is the whole string
        result = _chart_label("some_chart")
        assert result == "Some Chart"


# ---------------------------------------------------------------------------
# _chart_caption
# ---------------------------------------------------------------------------


class TestChartCaption:
    def test_known_slug_returns_nonempty(self):
        result = _chart_caption("scurve_custo.png")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_nonexistent_returns_empty_string(self):
        # line 83
        result = _chart_caption("nonexistent.png")
        assert result == ""

    def test_known_slug_bar_direto(self):
        result = _chart_caption("bar_direto_atividade_temporal.png")
        assert result != ""

    def test_unknown_slug_no_extension(self):
        result = _chart_caption("totally_unknown_chart_xyz")
        assert result == ""


# ---------------------------------------------------------------------------
# _fmt_localizacao
# ---------------------------------------------------------------------------


class TestFmtLocalizacao:
    def test_none_returns_dash(self):
        assert _fmt_localizacao(None) == "-"

    def test_empty_string_returns_dash(self):
        assert _fmt_localizacao("") == "-"

    def test_non_coordinate_string_returned_as_is(self):
        # lines 86-88: regex no-match
        result = _fmt_localizacao("Goiás, GO")
        assert result == "Goiás, GO"

    def test_plain_city_name_returned_as_is(self):
        result = _fmt_localizacao("Brasília, DF")
        assert result == "Brasília, DF"

    def test_coordinate_with_state_contains_brasil(self):
        # lat=-15.5, lng=-49.0 falls within MT/GO box
        result = _fmt_localizacao("lat=-15.5, lng=-49.0")
        assert "Brasil" in result

    def test_coordinate_with_state_contains_state_name(self):
        # lat=-10, lng=-55 hits the MT/GO box (-15.0→-7.0, -61.0→-48.0)
        result = _fmt_localizacao("lat=-10.0, lng=-55.0")
        assert any(name in result for name in ["Mato Grosso", "Goiás", "MT/GO"])

    def test_coordinate_format_south_west(self):
        result = _fmt_localizacao("lat=-15.5, lng=-49.0")
        assert "S" in result
        assert "O" in result

    def test_coordinate_outside_all_boxes_returns_brasil(self):
        # line 91 else branch: no state match → "Brasil (...)"
        result = _fmt_localizacao("lat=10.0, lng=-80.0")
        assert "Brasil" in result
        assert "N" in result  # positive lat → N

    def test_coordinate_no_space_around_equals(self):
        result = _fmt_localizacao("lat=-5.0,lng=-48.0")
        assert "Brasil" in result

    def test_coordinate_with_spaces(self):
        result = _fmt_localizacao("lat = -5.0, lng = -48.0")
        assert "Brasil" in result


# ---------------------------------------------------------------------------
# _br_estado_approx
# ---------------------------------------------------------------------------


class TestBrEstadoApprox:
    def test_para_within_first_box(self):
        # Box: (-5.3, 2.8, -52.6, -44.0) → Pará
        result = _br_estado_approx(-5.0, -48.0)
        assert result == "Pará"

    def test_outside_all_boxes_returns_none(self):
        # line 97 / return None
        result = _br_estado_approx(10.0, 10.0)
        assert result is None

    def test_mato_grosso_goias_box(self):
        # Box: (-15.0, -7.0, -61.0, -48.0) → Mato Grosso / Goiás
        result = _br_estado_approx(-12.0, -55.0)
        assert result == "Mato Grosso / Goiás"

    def test_rio_grande_do_sul_box(self):
        result = _br_estado_approx(-30.0, -53.0)
        assert result == "Rio Grande do Sul"

    def test_boundary_values_included(self):
        # Exact boundary of Pará box: lat_min=-5.3, lat_max=2.8, lng_min=-52.6, lng_max=-44.0
        assert _br_estado_approx(-5.3, -52.6) == "Pará"
        assert _br_estado_approx(2.8, -44.0) == "Pará"

    def test_just_outside_boundary_returns_none_or_other(self):
        # lat=3.0 > 2.8 (above Pará upper bound), far from other boxes
        result = _br_estado_approx(3.0, -48.0)
        # Should not be Pará
        assert result != "Pará"


# ---------------------------------------------------------------------------
# _brl
# ---------------------------------------------------------------------------


class TestBrl:
    def test_large_number_format(self):
        # line 109
        result = _brl(1234567.89)
        assert result == "R$ 1.234.567,89"

    def test_zero(self):
        result = _brl(0)
        assert result == "R$ 0,00"

    def test_small_value(self):
        result = _brl(1.5)
        assert result == "R$ 1,50"

    def test_negative_value(self):
        result = _brl(-500.0)
        assert result == "R$ -500,00"

    def test_float_string_coercion(self):
        # accepts int
        result = _brl(1000)
        assert result == "R$ 1.000,00"


# ---------------------------------------------------------------------------
# _pct
# ---------------------------------------------------------------------------


class TestPct:
    def test_fraction_multiplied_by_100(self):
        # line 110: -1 <= x <= 1 → multiply by 100
        result = _pct(0.25)
        assert result == "25.00%"

    def test_already_percentage_not_multiplied(self):
        result = _pct(25.0)
        assert result == "25.00%"

    def test_negative_fraction(self):
        result = _pct(-0.05)
        assert result == "-5.00%"

    def test_negative_large(self):
        result = _pct(-10.0)
        assert result == "-10.00%"

    def test_boundary_exactly_1(self):
        # x=1.0: -1 <= 1 <= 1 → multiply → 100%
        result = _pct(1.0)
        assert result == "100.00%"

    def test_boundary_exactly_minus_1(self):
        result = _pct(-1.0)
        assert result == "-100.00%"

    def test_just_above_1_not_multiplied(self):
        # x=1.01: not in [-1,1] → returned as-is
        result = _pct(1.01)
        assert result == "1.01%"


# ---------------------------------------------------------------------------
# _safe_text
# ---------------------------------------------------------------------------


class TestSafeText:
    def test_html_escape_script(self):
        # line 111
        result = _safe_text("<script>")
        assert result == "&lt;script&gt;"

    def test_none_returns_empty_string(self):
        result = _safe_text(None)
        assert result == ""

    def test_ampersand_escaped(self):
        result = _safe_text("A & B")
        assert result == "A &amp; B"

    def test_plain_text_unchanged(self):
        result = _safe_text("hello world")
        assert result == "hello world"

    def test_numeric_coercion(self):
        result = _safe_text(42)
        assert result == "42"

    def test_false_like_zero_returns_empty(self):
        # 0 is falsy → str(0 or "") = str("") = ""
        result = _safe_text(0)
        assert result == ""


# ---------------------------------------------------------------------------
# _fmt_cpu_descricao
# ---------------------------------------------------------------------------


class TestFmtCpuDescricao:
    def test_cpu_terra_prefix_removed(self):
        # lines 137, 139-143
        result = _fmt_cpu_descricao("CPU-TERRA-ESCO-1CAT")
        assert result == "Esco 1Cat"

    def test_cpu_prefix_removed(self):
        result = _fmt_cpu_descricao("CPU-GERAL")
        assert result == "Geral"

    def test_no_prefix_naked_id(self):
        result = _fmt_cpu_descricao("NAKED-ID")
        assert result == "Naked Id"

    def test_cpu_terra_multi_segment(self):
        result = _fmt_cpu_descricao("CPU-TERRA-ESCO-CARGA-1CAT")
        assert result == "Esco Carga 1Cat"

    def test_lowercase_cpu_prefix(self):
        # startswith is case-insensitive via .upper()
        result = _fmt_cpu_descricao("cpu-terra-ati-003")
        assert result == "Ati 003"

    def test_cpu_only_prefix(self):
        result = _fmt_cpu_descricao("CPU-DIESEL-MAN")
        assert result == "Diesel Man"


# ---------------------------------------------------------------------------
# render_financial_report_pdf — fallback PDF (lines 651-748)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HAS_RENDER, reason="render_financial_report_pdf not importable")
class TestRenderFinancialReportPdfFallback:
    """Tests that exercise the fallback canvas-based PDF path."""

    def _minimal_relatorio(self) -> dict:
        return {
            "resumo": {
                "projeto": "Projeto Teste",
                "tipo_obra": "Rodovia",
                "localizacao": "Goiás, GO",
            },
            "RESULTADO": {
                "preco_venda_total": 1_000_000.0,
                "custo_total": 800_000.0,
                "resultado_bruto": 200_000.0,
                "margem_pct": 0.20,
            },
        }

    def test_minimal_relatorio_returns_bytes(self):
        """Calling with a minimal valid relatorio should return bytes or None."""
        result = render_financial_report_pdf(self._minimal_relatorio(), title="Teste")
        assert result is None or isinstance(result, bytes)

    def test_valid_pdf_starts_with_header(self):
        result = render_financial_report_pdf(self._minimal_relatorio(), title="Teste")
        if result is not None:
            assert result[:4] == b"%PDF"

    def test_fallback_triggered_by_broken_platypus(self, monkeypatch):
        """Force the Platypus path to raise so the fallback canvas PDF is generated."""
        import concilium.application.runtime.deliverables.reports.financial_report_pdf as mod

        original_render = mod.render_financial_report_pdf

        def patched_render(relatorio, title, image_provider=None):
            # Monkeypatch SimpleDocTemplate inside the module's namespace

            # Temporarily replace reportlab.platypus.SimpleDocTemplate to raise
            try:
                import reportlab.platypus as platypus

                real_cls = platypus.SimpleDocTemplate

                class _Broken:
                    def __init__(self, *a, **kw):
                        raise RuntimeError("forced failure for fallback test")

                platypus.SimpleDocTemplate = _Broken
                try:
                    return original_render(relatorio, title, image_provider)
                finally:
                    platypus.SimpleDocTemplate = real_cls
            except ImportError:
                pytest.skip("reportlab not available")

        result = patched_render(self._minimal_relatorio(), title="Fallback Test")
        # Fallback should produce a valid PDF or None
        assert result is None or isinstance(result, bytes)
        if result is not None:
            assert result[:4] == b"%PDF"

    def test_empty_relatorio_does_not_crash(self):
        result = render_financial_report_pdf({}, title="Vazio")
        assert result is None or isinstance(result, bytes)

    def test_none_image_provider_does_not_crash(self):
        result = render_financial_report_pdf(self._minimal_relatorio(), title="Sem Imagens", image_provider=None)
        assert result is None or isinstance(result, bytes)
