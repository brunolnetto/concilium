"""Coverage tests for concilium.application.benchmarks.charts._chart_shared.

The module had zero test coverage. It hosts plotting helpers used by
_chart_plan_space (matplotlib Axes-based) plus a tiny JSON loader. We drive
the plotting helpers with a MagicMock standing in for the Axes object (we
only care that the branch logic executes correctly, not that matplotlib
actually renders anything), and exercise both branches of `_load_json`.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from concilium.application.benchmarks.charts._chart_shared import (
    _load_json,
    _ps_draw_deadline_makespan,
    _ps_draw_delta_cd,
    _ps_draw_insight,
    _ps_draw_pool_bars,
    _ps_draw_viabilidade,
)


class TestLoadJson:
    def test_load_json_missing_path_returns_empty_dict(self, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        assert _load_json(missing) == {}

    def test_load_json_existing_path_returns_parsed_dict(self, tmp_path):
        p = tmp_path / "data.json"
        p.write_text('{"a": 1}', encoding="utf-8")
        assert _load_json(p) == {"a": 1}


class TestPsDrawPoolBars:
    def test_covers_below_equal_and_above_base(self):
        ax = MagicMock()
        cenarios = [{"k": 3}, {"k": 5}, {"k": 8}]
        _ps_draw_pool_bars(ax, [0, 1, 2], cenarios, "k", base=5, title="ESC3", labels=["a", "b", "c"])
        ax.bar.assert_called_once()
        ax.axhline.assert_called_once()
        assert ax.text.call_count == 3


class TestPsDrawDeadlineMakespan:
    def test_covers_manual_and_folga_branches(self):
        ax = MagicMock()
        cenarios = [
            {"deadline": 56, "makespan": 50, "manual": True},  # folga=6 >= 4 -> verde
            {"deadline": 56, "makespan": 54, "manual": False},  # folga=2 < 4 -> vermelho
        ]
        _ps_draw_deadline_makespan(ax, [0, 1], cenarios, ["m0", "a0"])
        assert ax.bar.call_count == 2
        assert ax.text.call_count == 2


class TestPsDrawDeltaCd:
    def test_covers_all_three_color_bands_and_text_offsets(self):
        ax = MagicMock()
        cenarios = [
            {"delta_cd": -2.5},  # < -1 -> vermelho, negative offset
            {"delta_cd": -0.5},  # < 0 -> amarelo, negative offset
            {"delta_cd": 1.2},  # >= 0 -> verde, positive offset
        ]
        _ps_draw_delta_cd(ax, [0, 1, 2], cenarios, ["m0", "a0", "a1"])
        ax.bar.assert_called_once()
        ax.axhline.assert_called_once()
        assert ax.text.call_count == 3


class TestPsDrawViabilidade:
    def test_covers_feasible_and_infeasible(self):
        ax = MagicMock()
        cenarios = [{"feasible": True}, {"feasible": False}]
        _ps_draw_viabilidade(ax, [0, 1], cenarios, ["m0", "a0"])
        ax.bar.assert_called_once()
        assert ax.text.call_count == 2


class TestPsDrawInsight:
    def test_draws_insight_box(self):
        ax = MagicMock()
        _ps_draw_insight(ax)
        ax.set_facecolor.assert_called_once()
        ax.axis.assert_called_once_with("off")
        ax.text.assert_called_once()
