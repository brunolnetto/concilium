"""Tests for histogramas.py visualization module — covers missing lines 16-37,46-47,49-63,67-70,74-77."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_init_mpl_patch():
    """Return a patch that makes init_mpl() return a mock plt and a fig_to_bytes stub."""
    mock_plt = MagicMock()
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)

    def _fig_to_bytes(fig) -> bytes:
        return b"PNG"

    return mock_plt, _fig_to_bytes


def _patch_init_mpl(mock_plt, fig_to_bytes_fn):
    return patch(
        "concilium.application.runtime.deliverables.visualizations.charts._common.init_mpl",
        return_value=(mock_plt, fig_to_bytes_fn),
    )


def _patch_weekly_labels():
    """Patch weekly_to_monthly_labels to return labels unchanged."""
    return patch(
        "concilium.application.runtime.deliverables.visualizations.chart_markdown_support.weekly_to_monthly_labels",
        side_effect=lambda labels: labels,
    )


# ---------------------------------------------------------------------------
# Tests for _build_hist — empty / missing labels returns None (lines 16-19)
# ---------------------------------------------------------------------------

class TestBuildHistEmptyInputs:
    def test_empty_labels_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        section = {"labels": [], "values": [1.0, 2.0]}
        result = _build_hist(section, "Title", "Y", "#000", "by_type")
        assert result is None

    def test_empty_values_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        section = {"labels": ["A", "B"], "values": []}
        result = _build_hist(section, "Title", "Y", "#000", "by_type")
        assert result is None

    def test_missing_labels_key_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        section = {"values": [1.0, 2.0]}
        result = _build_hist(section, "Title", "Y", "#000", "by_type")
        assert result is None

    def test_missing_values_key_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        section = {"labels": ["A", "B"]}
        result = _build_hist(section, "Title", "Y", "#000", "by_type")
        assert result is None


# ---------------------------------------------------------------------------
# Tests for _build_hist — ImportError from init_mpl returns None (lines 22-25)
# ---------------------------------------------------------------------------

class TestBuildHistImportError:
    def test_import_error_from_init_mpl_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        section = {"labels": ["W1", "W2"], "values": [10.0, 20.0]}
        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            side_effect=ImportError("no matplotlib"),
        ):
            result = _build_hist(section, "Title", "Y", "#000", "by_type")
        assert result is None


# ---------------------------------------------------------------------------
# Tests for _build_hist — exception inside render returns None (lines 61-63)
# ---------------------------------------------------------------------------

class TestBuildHistRenderException:
    def test_exception_in_render_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("subplots exploded")

        def _fig_to_bytes(fig):
            return b"PNG"

        section = {"labels": ["A", "B"], "values": [1.0, 2.0]}
        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, _fig_to_bytes),
        ):
            result = _build_hist(section, "Title", "Y", "#000", "by_type")
        assert result is None


# ---------------------------------------------------------------------------
# Tests for _build_hist — simple flat bar (no breakdown) (lines 49, 50-60)
# ---------------------------------------------------------------------------

class TestBuildHistFlatBar:
    def test_flat_bar_returns_bytes(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        section = {"labels": ["A", "B", "C"], "values": [10.0, 20.0, 30.0]}

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = _build_hist(section, "My Title", "Units", "#1a3a5c", "by_type")

        assert result == b"PNG"

    def test_flat_bar_none_values_coerced(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        section = {"labels": ["A", "B"], "values": [None, 5.0]}

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = _build_hist(section, "Title", "Y", "#000", "by_type")

        assert result == b"PNG"


# ---------------------------------------------------------------------------
# Tests for _build_hist — stacked bar with breakdown dict (lines 29-47)
# ---------------------------------------------------------------------------

class TestBuildHistStackedBar:
    def test_stacked_bar_returns_bytes(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        section = {
            "labels": ["A", "B", "C"],
            "values": [30.0, 50.0, 20.0],
            "by_type": {
                "Escavadeira": [10.0, 20.0, 5.0],
                "Caminhão": [20.0, 30.0, 15.0],
            },
        }

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = _build_hist(section, "Hist Equip", "Units", "#1a3a5c", "by_type")

        assert result == b"PNG"
        # ax.bar should have been called twice (one per series)
        mock_ax = mock_plt.subplots.return_value[1]
        assert mock_ax.bar.call_count == 2

    def test_stacked_bar_label_truncation_over_22_chars(self):
        """Labels longer than 22 chars should be truncated with ellipsis (line 36)."""
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        long_label = "A" * 30  # 30 chars > 22
        section = {
            "labels": ["A", "B"],
            "values": [5.0, 10.0],
            "by_type": {
                long_label: [3.0, 6.0],
            },
        }

        captured_labels = []

        def capturing_bar(*args, **kwargs):
            label = kwargs.get("label", "")
            captured_labels.append(label)
            return MagicMock()

        mock_ax = mock_plt.subplots.return_value[1]
        mock_ax.bar.side_effect = capturing_bar

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            _build_hist(section, "Title", "Y", "#000", "by_type")

        assert len(captured_labels) == 1
        label_used = captured_labels[0]
        # Should end with ellipsis and be length 22
        assert label_used.endswith("…")
        assert len(label_used) == 22

    def test_stacked_bar_none_values_in_breakdown(self):
        """None values in breakdown series should be coerced to 0.0 (line 33)."""
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        section = {
            "labels": ["A", "B"],
            "values": [5.0, 10.0],
            "by_type": {
                "Tipo X": [None, 6.0],
            },
        }

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = _build_hist(section, "Title", "Y", "#000", "by_type")

        assert result == b"PNG"

    def test_breakdown_shorter_than_labels_padded(self):
        """Breakdown series shorter than labels should be zero-padded (line 34)."""
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        section = {
            "labels": ["A", "B", "C", "D"],
            "values": [1.0, 2.0, 3.0, 4.0],
            "by_type": {
                "Short": [10.0],  # only 1 value for 4 labels
            },
        }

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = _build_hist(section, "Title", "Y", "#000", "by_type")

        assert result == b"PNG"

    def test_non_dict_breakdown_falls_back_to_flat(self):
        """If breakdown key is not a dict, fall back to flat bar (lines 48-49)."""
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import _build_hist

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        section = {
            "labels": ["A", "B"],
            "values": [5.0, 10.0],
            "by_type": "not_a_dict",  # non-dict breakdown
        }

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = _build_hist(section, "Title", "Y", "#000", "by_type")

        assert result == b"PNG"
        mock_ax = mock_plt.subplots.return_value[1]
        # flat bar: bar called once, legend NOT called
        assert mock_ax.bar.call_count == 1


# ---------------------------------------------------------------------------
# Tests for build_hist_equipamentos (lines 66-70)
# ---------------------------------------------------------------------------

class TestBuildHistEquipamentos:
    def test_delegates_with_correct_key(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_equipamentos

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        graficos = {
            "equipamentos": {
                "labels": ["A", "B"],
                "values": [5.0, 10.0],
            }
        }

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = build_hist_equipamentos(graficos)

        assert result == b"PNG"

    def test_missing_section_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_equipamentos

        result = build_hist_equipamentos({})
        assert result is None

    def test_non_dict_section_returns_none(self):
        """Non-dict section should return None (line 68-69)."""
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_equipamentos

        result = build_hist_equipamentos({"equipamentos": "not_a_dict"})
        assert result is None

    def test_none_section_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_equipamentos

        result = build_hist_equipamentos({"equipamentos": None})
        assert result is None


# ---------------------------------------------------------------------------
# Tests for build_hist_mao_obra (lines 73-77)
# ---------------------------------------------------------------------------

class TestBuildHistMaoObra:
    def test_delegates_with_correct_key(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_mao_obra

        mock_plt, fig_to_bytes_fn = _make_init_mpl_patch()
        graficos = {
            "mao_obra": {
                "labels": ["A", "B"],
                "values": [3.0, 7.0],
            }
        }

        with patch(
            "concilium.application.runtime.deliverables.visualizations.charts.histogramas.init_mpl",
            return_value=(mock_plt, fig_to_bytes_fn),
        ), _patch_weekly_labels():
            result = build_hist_mao_obra(graficos)

        assert result == b"PNG"

    def test_missing_section_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_mao_obra

        result = build_hist_mao_obra({})
        assert result is None

    def test_non_dict_section_returns_none(self):
        """Non-dict section should return None (lines 75-76)."""
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_mao_obra

        result = build_hist_mao_obra({"mao_obra": ["list", "not", "dict"]})
        assert result is None

    def test_none_section_returns_none(self):
        from concilium.application.runtime.deliverables.visualizations.charts.histogramas import build_hist_mao_obra

        result = build_hist_mao_obra({"mao_obra": None})
        assert result is None
