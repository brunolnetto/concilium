"""Tests for build_relatorio_fallback in _relatorio_fallback.py.

Covers all missing lines including:
- early-return paths (non-dict, ImportError)
- chart 1: resumo_utilizacao_contratos -> bar_tempo_natureza.png
- chart 2: instancias_recurso -> linha_recursos_tempo.png
- chart 3: PLANEJAMENTO -> bar_categoria_componente.png
- chart 4: ponto_equilibrio -> bar_atividade_componente.png
- exception-swallowing paths inside each chart block
- empty / falsy data paths (no chart produced)
- all charts produced together
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.cube._relatorio_fallback"
_INIT_MLP_PATCH = f"{_MOD}.init_mpl"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_fn():
    import importlib
    mod = importlib.import_module(_MOD)
    return mod.build_relatorio_fallback


def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _make_ax_mock():
    ax = MagicMock()
    # axes[r][c] subscript support for instancias path
    ax.__getitem__ = MagicMock(return_value=MagicMock())
    return ax


def _make_plt_mock():
    """Return (mock_plt, mock_fig, mock_ax)."""
    mock_fig = MagicMock()
    mock_ax = _make_ax_mock()
    # For the instancias_recurso path, plt.subplots returns (fig, axes) where axes is 2-D
    # We make a 2-D axes mock that supports [r][c] indexing
    axes_2d = MagicMock()
    inner_ax = _make_ax_mock()
    axes_2d.__getitem__ = MagicMock(return_value=[inner_ax, inner_ax, inner_ax, inner_ax])
    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)
    return mock_plt, mock_fig, mock_ax


def _patched_init_mpl(mock_plt):
    return patch(_INIT_MLP_PATCH, return_value=(mock_plt, _fig_to_bytes_stub))


# ---------------------------------------------------------------------------
# Fixtures — minimal data for each section
# ---------------------------------------------------------------------------

def _resumo_row(**kwargs):
    base = {"tipo_id": "EQ-01", "machine_weeks_usados": 5, "machine_weeks_standby": 2}
    base.update(kwargs)
    return base


def _instancia_row(**kwargs):
    base = {
        "tipo_id": "EQ-01",
        "numero": 1,
        "instancia_id": "EQ-01-001",
        "semanas_ativas": 3,
        "semanas_standby": 1,
    }
    base.update(kwargs)
    return base


def _plano_row(**kwargs):
    base = {
        "item_id": "ITEM-001",
        "subtotal_sem_bdi_mo": 1_000_000,
        "subtotal_sem_bdi_eq": 500_000,
        "subtotal_sem_bdi_diesel": 200_000,
        "subtotal_sem_bdi_mat": 300_000,
    }
    base.update(kwargs)
    return base


def _pe_row(**kwargs):
    base = {
        "item_id": "ITEM-001",
        "custo_venda_cpu": 2_000_000,
        "custo_operacional_real": 1_500_000,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# 1. Early-return paths
# ---------------------------------------------------------------------------

class TestEarlyReturns:
    def test_not_a_dict_returns_empty(self):
        """relatorio is not a dict -> return {}."""
        build = _import_fn()
        assert build(None) == {}

    def test_list_returns_empty(self):
        """relatorio is a list -> return {}."""
        build = _import_fn()
        assert build([{"a": 1}]) == {}

    def test_string_returns_empty(self):
        """relatorio is a string -> return {}."""
        build = _import_fn()
        assert build("hello") == {}

    def test_import_error_returns_empty(self):
        """ImportError from init_mpl -> return {}."""
        build = _import_fn()
        with patch(_INIT_MLP_PATCH, side_effect=ImportError("no matplotlib")):
            assert build({}) == {}

    def test_empty_dict_returns_empty(self):
        """Empty dict -> return {} (no sections present)."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({})
        assert result == {}


# ---------------------------------------------------------------------------
# 2. Chart 1 — resumo_utilizacao_contratos -> bar_tempo_natureza.png
# ---------------------------------------------------------------------------

class TestChart1ResumoUtilizacaoContratos:
    def test_produces_bar_tempo_natureza(self):
        """Valid resumo rows -> bar_tempo_natureza.png in output."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {"resumo_utilizacao_contratos": [_resumo_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_tempo_natureza.png" in result
        assert result["bar_tempo_natureza.png"] == b"PNG"

    def test_none_values_coerced_to_zero(self):
        """None machine_weeks values default to 0."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {
            "resumo_utilizacao_contratos": [
                {"tipo_id": "T1", "machine_weeks_usados": None, "machine_weeks_standby": None}
            ]
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_tempo_natureza.png" in result

    def test_missing_tipo_id_defaults_to_question_mark(self):
        """Missing tipo_id defaults to '?'."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {"resumo_utilizacao_contratos": [{"machine_weeks_usados": 3}]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_tempo_natureza.png" in result

    def test_multiple_resumo_rows(self):
        """Multiple rows -> chart still produced."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {
            "resumo_utilizacao_contratos": [
                _resumo_row(tipo_id="A"),
                _resumo_row(tipo_id="B"),
                _resumo_row(tipo_id="C"),
            ]
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_tempo_natureza.png" in result

    def test_empty_resumo_list_skips_chart(self):
        """Empty list -> bar_tempo_natureza.png not in output."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"resumo_utilizacao_contratos": []}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_tempo_natureza.png" not in result

    def test_none_resumo_skips_chart(self):
        """None value -> bar_tempo_natureza.png not in output."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"resumo_utilizacao_contratos": None}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_tempo_natureza.png" not in result

    def test_non_dict_rows_filtered_out(self):
        """Non-dict rows are filtered; if none left, no chart."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"resumo_utilizacao_contratos": ["not a dict", 42, None]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_tempo_natureza.png" not in result

    def test_exception_in_chart1_swallowed(self):
        """Exception in chart1 block is swallowed; other charts still run."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_ax.barh.side_effect = RuntimeError("render fail")
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {"resumo_utilizacao_contratos": [_resumo_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        # chart1 failed but no exception propagated
        assert isinstance(result, dict)
        assert "bar_tempo_natureza.png" not in result


# ---------------------------------------------------------------------------
# 3. Chart 2 — instancias_recurso -> linha_recursos_tempo.png
# ---------------------------------------------------------------------------

class TestChart2InstanciasRecurso:
    def _make_instancias_plt(self):
        """plt mock whose subplots returns (fig, 2D axes array)."""
        mock_fig = MagicMock()
        mock_plt = MagicMock()
        # axes[r][c] -> returns a MagicMock ax
        inner_ax = MagicMock()
        axes_2d = MagicMock()
        axes_2d.__getitem__ = MagicMock(return_value=[inner_ax] * 4)
        mock_plt.subplots.return_value = (mock_fig, axes_2d)
        return mock_plt, mock_fig, axes_2d, inner_ax

    def test_produces_linha_recursos_tempo(self):
        """Valid instancias rows -> linha_recursos_tempo.png in output."""
        build = _import_fn()
        mock_plt, mock_fig, axes_2d, inner_ax = self._make_instancias_plt()
        relatorio = {"instancias_recurso": [_instancia_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" in result
        assert result["linha_recursos_tempo.png"] == b"PNG"

    def test_multiple_tipos_multiple_cols(self):
        """Multiple tipo_id groups -> multiple subplots."""
        build = _import_fn()
        mock_plt, mock_fig, axes_2d, inner_ax = self._make_instancias_plt()
        rows = [
            _instancia_row(tipo_id="A", instancia_id="A-001"),
            _instancia_row(tipo_id="B", instancia_id="B-001"),
            _instancia_row(tipo_id="C", instancia_id="C-001"),
        ]
        relatorio = {"instancias_recurso": rows}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" in result

    def test_more_than_4_tipos_wraps_rows(self):
        """5 tipos -> n_rows=2, n_cols=4 layout."""
        build = _import_fn()
        mock_plt, mock_fig, axes_2d, inner_ax = self._make_instancias_plt()
        rows = [_instancia_row(tipo_id=f"T{i}") for i in range(5)]
        relatorio = {"instancias_recurso": rows}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" in result

    def test_none_semanas_coerced_to_zero(self):
        """None semanas values default to 0."""
        build = _import_fn()
        mock_plt, mock_fig, axes_2d, inner_ax = self._make_instancias_plt()
        row = {"tipo_id": "T1", "numero": None, "instancia_id": "T1-001",
               "semanas_ativas": None, "semanas_standby": None}
        relatorio = {"instancias_recurso": [row]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" in result

    def test_missing_tipo_id_defaults_to_question_mark(self):
        """Missing tipo_id defaults to '?'."""
        build = _import_fn()
        mock_plt, mock_fig, axes_2d, inner_ax = self._make_instancias_plt()
        row = {"numero": 1, "instancia_id": "X-001", "semanas_ativas": 2, "semanas_standby": 0}
        relatorio = {"instancias_recurso": [row]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" in result

    def test_empty_instancias_skips_chart(self):
        """Empty instancias list -> linha_recursos_tempo.png not in output."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"instancias_recurso": []}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" not in result

    def test_none_instancias_skips_chart(self):
        """None instancias -> chart skipped."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"instancias_recurso": None}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" not in result

    def test_non_dict_rows_filtered(self):
        """Non-dict items filtered out; if none remain, no chart."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"instancias_recurso": ["str", 99, None]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "linha_recursos_tempo.png" not in result

    def test_exception_in_chart2_swallowed(self):
        """Exception in chart2 block swallowed; function still returns dict."""
        build = _import_fn()
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("boom")
        relatorio = {"instancias_recurso": [_instancia_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert isinstance(result, dict)
        assert "linha_recursos_tempo.png" not in result


# ---------------------------------------------------------------------------
# 4. Chart 3 — PLANEJAMENTO -> bar_categoria_componente.png
# ---------------------------------------------------------------------------

class TestChart3Planejamento:
    def test_produces_bar_categoria_componente(self):
        """Valid PLANEJAMENTO rows -> bar_categoria_componente.png in output."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {"PLANEJAMENTO": [_plano_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_categoria_componente.png" in result
        assert result["bar_categoria_componente.png"] == b"PNG"

    def test_none_cost_fields_coerced_to_zero(self):
        """None cost fields default to 0."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        row = {
            "item_id": "X",
            "subtotal_sem_bdi_mo": None,
            "subtotal_sem_bdi_eq": None,
            "subtotal_sem_bdi_diesel": None,
            "subtotal_sem_bdi_mat": None,
        }
        relatorio = {"PLANEJAMENTO": [row]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_categoria_componente.png" in result

    def test_missing_item_id_defaults_to_question_mark(self):
        """Missing item_id defaults to '?'."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        row = {"subtotal_sem_bdi_mo": 1_000_000}
        relatorio = {"PLANEJAMENTO": [row]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_categoria_componente.png" in result

    def test_multiple_plano_rows(self):
        """Multiple rows -> chart still produced."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {
            "PLANEJAMENTO": [
                _plano_row(item_id="A"),
                _plano_row(item_id="B"),
                _plano_row(item_id="C"),
            ]
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_categoria_componente.png" in result

    def test_empty_planejamento_skips_chart(self):
        """Empty PLANEJAMENTO -> bar_categoria_componente.png not in output."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"PLANEJAMENTO": []}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_categoria_componente.png" not in result

    def test_none_planejamento_skips_chart(self):
        """None PLANEJAMENTO -> chart skipped."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"PLANEJAMENTO": None}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_categoria_componente.png" not in result

    def test_non_dict_rows_filtered(self):
        """Non-dict PLANEJAMENTO items filtered; if none remain, no chart."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"PLANEJAMENTO": ["str", None, 42]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_categoria_componente.png" not in result

    def test_exception_in_chart3_swallowed(self):
        """Exception in chart3 block swallowed."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_ax.barh.side_effect = ValueError("bad data")
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {"PLANEJAMENTO": [_plano_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert isinstance(result, dict)
        assert "bar_categoria_componente.png" not in result


# ---------------------------------------------------------------------------
# 5. Chart 4 — ponto_equilibrio -> bar_atividade_componente.png
# ---------------------------------------------------------------------------

class TestChart4PontoEquilibrio:
    def test_produces_bar_atividade_componente(self):
        """Valid pe_rows -> bar_atividade_componente.png in output."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {"ponto_equilibrio": [_pe_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" in result
        assert result["bar_atividade_componente.png"] == b"PNG"

    def test_zero_custo_venda_filtered_out(self):
        """Rows with custo_venda_cpu <= 0 are filtered; if none remain, no chart."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {
            "ponto_equilibrio": [
                {"item_id": "X", "custo_venda_cpu": 0, "custo_operacional_real": 1_000_000},
                {"item_id": "Y", "custo_venda_cpu": None, "custo_operacional_real": 1_000_000},
            ]
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" not in result

    def test_none_custo_venda_filtered_out(self):
        """None custo_venda_cpu treated as 0.0 -> filtered out."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {
            "ponto_equilibrio": [
                {"item_id": "Z", "custo_venda_cpu": None, "custo_operacional_real": 500_000}
            ]
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" not in result

    def test_positive_custo_venda_included(self):
        """Positive custo_venda_cpu -> row included -> chart produced."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {
            "ponto_equilibrio": [
                _pe_row(custo_venda_cpu=5_000_000, custo_operacional_real=3_000_000)
            ]
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" in result

    def test_none_custo_operacional_coerced_to_zero(self):
        """None custo_operacional_real defaults to 0."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        row = {"item_id": "A", "custo_venda_cpu": 2_000_000, "custo_operacional_real": None}
        relatorio = {"ponto_equilibrio": [row]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" in result

    def test_missing_item_id_defaults_to_question_mark(self):
        """Missing item_id defaults to '?'."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        row = {"custo_venda_cpu": 1_000_000, "custo_operacional_real": 800_000}
        relatorio = {"ponto_equilibrio": [row]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" in result

    def test_empty_ponto_equilibrio_skips_chart(self):
        """Empty ponto_equilibrio -> chart not in output."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"ponto_equilibrio": []}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" not in result

    def test_none_ponto_equilibrio_skips_chart(self):
        """None ponto_equilibrio -> chart skipped."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"ponto_equilibrio": None}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" not in result

    def test_non_dict_rows_filtered(self):
        """Non-dict rows filtered out."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        relatorio = {"ponto_equilibrio": ["not dict", 1, None]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" not in result

    def test_exception_in_chart4_swallowed(self):
        """Exception in chart4 block swallowed."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_ax.barh.side_effect = ValueError("fail")
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {"ponto_equilibrio": [_pe_row()]}
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert isinstance(result, dict)
        assert "bar_atividade_componente.png" not in result

    def test_multiple_pe_rows(self):
        """Multiple ponto_equilibrio rows -> chart produced."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {
            "ponto_equilibrio": [
                _pe_row(item_id="A"),
                _pe_row(item_id="B"),
            ]
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        assert "bar_atividade_componente.png" in result


# ---------------------------------------------------------------------------
# 6. All charts together
# ---------------------------------------------------------------------------

class TestAllChartsTogther:
    def test_all_four_charts_produced(self):
        """All four data sections present -> all four chart keys in output."""
        build = _import_fn()
        # We need subplots to be called multiple times and always return valid mocks
        mock_fig = MagicMock()
        inner_ax = MagicMock()
        axes_2d = MagicMock()
        axes_2d.__getitem__ = MagicMock(return_value=[inner_ax] * 4)
        mock_plt = MagicMock()
        # Return 2D axes for chart2, simple ax for others
        call_count = [0]
        def _subplots_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                # instancias_recurso (chart 2) uses 2D axes
                return (mock_fig, axes_2d)
            return (mock_fig, inner_ax)
        mock_plt.subplots.side_effect = _subplots_side_effect

        relatorio = {
            "resumo_utilizacao_contratos": [_resumo_row()],
            "instancias_recurso": [_instancia_row()],
            "PLANEJAMENTO": [_plano_row()],
            "ponto_equilibrio": [_pe_row()],
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)

        assert "bar_tempo_natureza.png" in result
        assert "linha_recursos_tempo.png" in result
        assert "bar_categoria_componente.png" in result
        assert "bar_atividade_componente.png" in result

    def test_returns_dict_type(self):
        """Return value is always a dict."""
        build = _import_fn()
        mock_plt, *_ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({})
        assert isinstance(result, dict)

    def test_output_values_are_bytes(self):
        """All chart values in output dict are bytes."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_plt.subplots.return_value = (mock_fig, mock_ax)
        relatorio = {
            "resumo_utilizacao_contratos": [_resumo_row()],
            "PLANEJAMENTO": [_plano_row()],
            "ponto_equilibrio": [_pe_row()],
        }
        with _patched_init_mpl(mock_plt):
            result = build(relatorio)
        for key, val in result.items():
            assert isinstance(val, bytes), f"Expected bytes for {key}"
