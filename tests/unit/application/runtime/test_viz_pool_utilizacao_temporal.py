"""Unit tests for pool_utilizacao_temporal.py (CC=19D, coverage 11.9%).

Cobertura das linhas: 19-20, 22-24, 26-28, 30-32, 34-37, 39-44, 46,
48-49, 51-53, 55-58, 60-62, 65-66, 69-71, 73-77.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

MODULE = "concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal"
RESOLVE = "concilium.application.services.analytics.cubo_pool_projection.resolve_cubo_pool_projection"


def _rows_factory(n=3):
    return [{"periodo": f"2024-W{i + 1:02d}", "prod": 5, "idle": 2, "off": 1} for i in range(n)]


def _make_mock_plt():
    """Retorna (mock_plt, mock_fig, mock_ax, fig_to_bytes_stub)."""
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)

    def _stub(fig):
        return b"PNG"

    return mock_plt, mock_fig, mock_ax, _stub


# ---------------------------------------------------------------------------
# Tier 1 — Retornos None precoces
# ---------------------------------------------------------------------------


class TestEarlyReturnsNone:
    def test_resolve_exception_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        with patch(RESOLVE, side_effect=RuntimeError("fail")):
            result = build(canonical)

        assert result is None

    def test_empty_rows_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {"rows": [], "totais": {"semanas_por_estado": {"prod": 0}}}
        with patch(RESOLVE, return_value=proj):
            result = build(canonical)

        assert result is None

    def test_null_rows_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {"rows": None, "totais": {"semanas_por_estado": {"prod": 0}}}
        with patch(RESOLVE, return_value=proj):
            result = build(canonical)

        assert result is None

    def test_missing_rows_key_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {"totais": {"semanas_por_estado": {"prod": 0}}}
        with patch(RESOLVE, return_value=proj):
            result = build(canonical)

        assert result is None

    def test_zero_prod_slots_returns_none(self):
        """totais.semanas_por_estado.prod == 0 → retorna None."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {
            "rows": _rows_factory(3),
            "totais": {"semanas_por_estado": {"prod": 0}},
        }
        with patch(RESOLVE, return_value=proj):
            result = build(canonical)

        assert result is None

    def test_missing_totais_returns_none(self):
        """Sem totais, prod default 0 → retorna None."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {"rows": _rows_factory(3)}
        with patch(RESOLVE, return_value=proj):
            result = build(canonical)

        assert result is None

    def test_import_error_returns_none(self):
        """init_mpl lança ImportError → retorna None."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {
            "rows": _rows_factory(3),
            "totais": {"semanas_por_estado": {"prod": 5}},
        }
        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", side_effect=ImportError("matplotlib not found")),
        ):
            result = build(canonical)

        assert result is None


# ---------------------------------------------------------------------------
# Tier 2 — Caminho feliz (happy path)
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_returns_bytes_with_weekly_labels(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {
            "rows": _rows_factory(3),
            "totais": {"semanas_por_estado": {"prod": 15}},
        }
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical)

        assert result == b"PNG"

    def test_returns_bytes_with_non_weekly_labels(self):
        """Quando não é semanal, seta xticks explicitamente."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {
            "rows": _rows_factory(4),
            "totais": {"semanas_por_estado": {"prod": 20}},
        }
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=False),
        ):
            result = build(canonical)

        assert result == b"PNG"
        mock_ax.set_xticks.assert_called_once()
        mock_ax.set_xticklabels.assert_called_once()

    def test_narrativa_added_when_present(self):
        """Narrativa do proj é adicionada ao figure."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {
            "rows": _rows_factory(2),
            "totais": {"semanas_por_estado": {"prod": 10}},
            "narrativa": ["Recurso X está ocioso por 3 semanas"],
        }
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical)

        assert result == b"PNG"
        mock_fig.text.assert_called_once()

    def test_narrativa_empty_not_added(self):
        """Narrativa vazia: fig.text não chamado."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {
            "rows": _rows_factory(2),
            "totais": {"semanas_por_estado": {"prod": 10}},
            "narrativa": [],
        }
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical)

        assert result == b"PNG"
        mock_fig.text.assert_not_called()

    def test_cubo_argument_passed_through(self):
        """Argumento cubo é aceito sem erros."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()
        cubo = MagicMock()

        proj = {
            "rows": _rows_factory(2),
            "totais": {"semanas_por_estado": {"prod": 8}},
        }
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical, cubo=cubo)

        assert result == b"PNG"

    def test_plots_mob_and_demob_when_present(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        rows = [
            {"periodo": "2024-W01", "prod": 5, "idle": 0, "off": 0, "mob": 1, "demob": 0},
            {"periodo": "2024-W02", "prod": 5, "idle": 1, "off": 0, "mob": 0, "demob": 1},
        ]
        proj = {
            "rows": rows,
            "totais": {"semanas_por_estado": {"prod": 10}},
        }
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical)

        assert result == b"PNG"
        assert mock_ax.plot.call_count == 2

    def test_skips_event_lines_when_absent(self):
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        rows = [
            {"periodo": "2024-W01", "prod": 5, "idle": 0, "off": 0, "mob": 0, "demob": 0},
            {"periodo": "2024-W02", "prod": 5, "idle": 1, "off": 0, "mob": 0, "demob": 0},
        ]
        proj = {
            "rows": rows,
            "totais": {"semanas_por_estado": {"prod": 10}},
        }
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical)

        assert result == b"PNG"
        mock_ax.plot.assert_not_called()


# ---------------------------------------------------------------------------
# Tier 3 — None/zero em campos de row
# ---------------------------------------------------------------------------


class TestRowFieldDefaults:
    def test_none_fields_default_to_zero(self):
        """Campos prod/idle/off = None são tratados como 0."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        rows = [
            {"periodo": "2024-W01", "prod": None, "idle": None, "off": None},
            {"periodo": "2024-W02", "prod": 5, "idle": 1, "off": 0},
        ]
        proj = {"rows": rows, "totais": {"semanas_por_estado": {"prod": 5}}}
        mock_plt, mock_fig, mock_ax, stub = _make_mock_plt()

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.apply_monthly_ticks"),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical)

        assert result == b"PNG"

    def test_missing_fields_default_to_zero(self):
        """Campos ausentes em rows são tratados como 0."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        rows = [{"periodo": "2024-W01"}, {"periodo": "2024-W02"}]
        proj = {"rows": rows, "totais": {"semanas_por_estado": {"prod": 0}}}

        with patch(RESOLVE, return_value=proj):
            result = build(canonical)

        # prod=0 → retorna None
        assert result is None


# ---------------------------------------------------------------------------
# Tier 4 — Exceção durante renderização
# ---------------------------------------------------------------------------


class TestExceptionHandling:
    def test_exception_in_subplots_returns_none(self):
        """Exceção em plt.subplots → retorna None, fecha todos plots."""
        from concilium.application.runtime.deliverables.visualizations.cube.pool_utilizacao_temporal import build

        canonical = MagicMock()

        proj = {
            "rows": _rows_factory(3),
            "totais": {"semanas_por_estado": {"prod": 10}},
        }
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("plotting failed")

        def stub(fig):
            return b"PNG"

        with (
            patch(RESOLVE, return_value=proj),
            patch(f"{MODULE}.init_mpl", return_value=(mock_plt, stub)),
            patch(f"{MODULE}.is_weekly_labels", return_value=True),
        ):
            result = build(canonical)

        assert result is None
        mock_plt.close.assert_called()
