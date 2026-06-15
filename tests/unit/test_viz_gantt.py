"""Tests for build_gantt in gantt.py.

Covers all missing lines including:
- early-return paths (empty/non-dict input, missing 'tasks', no tasks with 'start')
- ImportError path (returns None)
- happy path with one task (returns bytes)
- happy path with multiple tasks and various fields
- task name fallback logic (item_id, default "Atividade N")
- long name truncation (> 38 chars)
- level cycling through _GANTT_LEVEL_COLORS
- error path (rendering exception → returns None)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Module-level import helper
# ---------------------------------------------------------------------------

_MOD = "concilium.application.runtime.deliverables.visualizations.charts.gantt"


def _import_fn():
    import importlib
    mod = importlib.import_module(_MOD)
    return mod.build_gantt


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _fig_to_bytes_stub(fig) -> bytes:
    return b"PNG"


def _make_ax_mock():
    mock_ax = MagicMock()
    mock_ax.xaxis = MagicMock()
    return mock_ax


def _make_plt_mock():
    """Return (mock_plt, mock_fig, mock_ax) with sensible stubs."""
    mock_ax = _make_ax_mock()
    mock_fig = MagicMock()
    mock_plt = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)
    return mock_plt, mock_fig, mock_ax


def _patched_init_mpl(mock_plt):
    """Return a context manager patching init_mpl to return (mock_plt, stub)."""
    return patch(
        f"{_MOD}.init_mpl",
        return_value=(mock_plt, _fig_to_bytes_stub),
    )


def _one_task(
    start: str = "2024-01-15",
    name: str | None = "Task One",
    item_id: str | None = None,
    duration_days: int = 14,
    level: int = 0,
) -> dict:
    t: dict = {"start": start, "duration_days": duration_days, "level": level}
    if name is not None:
        t["name"] = name
    if item_id is not None:
        t["item_id"] = item_id
    return t


# ---------------------------------------------------------------------------
# 1. Early-return guard clauses (no matplotlib needed)
# ---------------------------------------------------------------------------

class TestEarlyReturns:
    def test_non_dict_input_returns_none(self):
        """Non-dict input → tasks=[], return None."""
        build = _import_fn()
        assert build(None) is None

    def test_list_input_returns_none(self):
        """list input (non-dict) → return None."""
        build = _import_fn()
        assert build([{"start": "2024-01-01"}]) is None

    def test_empty_dict_returns_none(self):
        """Empty dict (no 'tasks' key) → return None."""
        build = _import_fn()
        assert build({}) is None

    def test_tasks_key_absent_returns_none(self):
        """Dict without 'tasks' key → return None."""
        build = _import_fn()
        assert build({"other_key": "value"}) is None

    def test_empty_tasks_list_returns_none(self):
        """Explicit empty tasks list → return None."""
        build = _import_fn()
        assert build({"tasks": []}) is None

    def test_tasks_none_raises_typeerror(self):
        """tasks=None → list(None) raises TypeError from the source."""
        build = _import_fn()
        with pytest.raises(TypeError):
            build({"tasks": None})

    def test_all_tasks_missing_start_returns_none(self):
        """All tasks lack 'start' key → sorted_tasks empty → return None."""
        build = _import_fn()
        assert build({"tasks": [{"name": "No start task"}]}) is None

    def test_tasks_with_empty_start_returns_none(self):
        """Task with start='' (falsy) is filtered out → return None."""
        build = _import_fn()
        assert build({"tasks": [{"name": "T", "start": ""}]}) is None


# ---------------------------------------------------------------------------
# 2. ImportError path
# ---------------------------------------------------------------------------

class TestImportErrorPath:
    def test_import_error_returns_none(self):
        """ImportError during init_mpl → return None."""
        build = _import_fn()
        with patch(
            f"{_MOD}.init_mpl",
            side_effect=ImportError("no matplotlib"),
        ):
            assert build({"tasks": [_one_task()]}) is None


# ---------------------------------------------------------------------------
# 3. Happy path — one task
# ---------------------------------------------------------------------------

class TestHappyPathOneTask:
    def test_returns_bytes_one_task(self):
        """Single task with valid start date → returns bytes."""
        build = _import_fn()
        mock_plt, _, _ = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            result = build({"tasks": [_one_task()]})
        assert result == b"PNG"

    def test_subplots_called(self):
        """plt.subplots should be called once."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task()]})
        mock_plt.subplots.assert_called_once()

    def test_ax_broken_barh_called(self):
        """ax.broken_barh should be called once per task."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task()]})
        assert mock_ax.broken_barh.call_count == 1

    def test_ax_text_called(self):
        """ax.text should be called once per task (bar label)."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task()]})
        assert mock_ax.text.call_count == 1

    def test_axes_decoration_called(self):
        """set_yticks, set_yticklabels, xaxis_date, set_title, etc. are called."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task()]})
        mock_ax.set_yticks.assert_called_once()
        mock_ax.set_yticklabels.assert_called_once()
        mock_ax.xaxis_date.assert_called_once()
        mock_ax.set_title.assert_called_once()
        mock_ax.set_xlabel.assert_called_once()
        mock_ax.grid.assert_called_once()
        mock_fig.tight_layout.assert_called_once()
        mock_fig.autofmt_xdate.assert_called_once()


# ---------------------------------------------------------------------------
# 4. Multiple tasks (loop coverage, sorting, ytick range)
# ---------------------------------------------------------------------------

class TestMultipleTasks:
    def test_two_tasks_rendered(self):
        """Two tasks both get broken_barh calls."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        tasks = [
            _one_task(start="2024-02-01", name="Task A"),
            _one_task(start="2024-01-15", name="Task B"),
        ]
        with _patched_init_mpl(mock_plt):
            result = build({"tasks": tasks})
        assert result == b"PNG"
        assert mock_ax.broken_barh.call_count == 2
        assert mock_ax.text.call_count == 2

    def test_tasks_sorted_by_start(self):
        """Tasks are sorted chronologically — earlier start gets idx=0."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        tasks = [
            _one_task(start="2024-03-01", name="Later"),
            _one_task(start="2024-01-01", name="Earlier"),
        ]
        with _patched_init_mpl(mock_plt):
            result = build({"tasks": tasks})
        assert result == b"PNG"
        # ytick labels should be in sorted order: Earlier, Later
        call_args = mock_ax.set_yticklabels.call_args[0][0]
        assert call_args[0] == "Earlier"
        assert call_args[1] == "Later"

    def test_mixed_tasks_some_missing_start(self):
        """Tasks without 'start' are filtered; only tasks with 'start' render."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        tasks = [
            {"name": "No start"},
            _one_task(start="2024-01-01", name="Has start"),
        ]
        with _patched_init_mpl(mock_plt):
            result = build({"tasks": tasks})
        assert result == b"PNG"
        assert mock_ax.broken_barh.call_count == 1


# ---------------------------------------------------------------------------
# 5. Task name fallback logic
# ---------------------------------------------------------------------------

class TestTaskNameFallback:
    def test_name_key_used_when_present(self):
        """Task with 'name' key → name used as label."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task(name="My Task")]})
        call_args = mock_ax.text.call_args
        label_text = call_args[0][2]  # third positional arg is the label text
        assert "My Task" in label_text

    def test_item_id_fallback_when_name_absent(self):
        """Task without 'name' but with 'item_id' → item_id used as label."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        task = _one_task(name=None, item_id="CPU-001")
        with _patched_init_mpl(mock_plt):
            build({"tasks": [task]})
        call_args = mock_ax.text.call_args
        label_text = call_args[0][2]
        assert "CPU-001" in label_text

    def test_default_name_when_both_absent(self):
        """Task without 'name' or 'item_id' → 'Atividade 1' used."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        task = {"start": "2024-01-01", "duration_days": 7}
        with _patched_init_mpl(mock_plt):
            build({"tasks": [task]})
        call_args = mock_ax.text.call_args
        label_text = call_args[0][2]
        assert "Atividade 1" in label_text

    def test_name_none_falls_back_to_item_id(self):
        """Task with name=None explicitly → falls back to item_id."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        task = {"start": "2024-01-01", "name": None, "item_id": "ITEM-42"}
        with _patched_init_mpl(mock_plt):
            build({"tasks": [task]})
        call_args = mock_ax.text.call_args
        label_text = call_args[0][2]
        assert "ITEM-42" in label_text


# ---------------------------------------------------------------------------
# 6. Long name truncation (> 38 chars → "name[:38]...")
# ---------------------------------------------------------------------------

class TestLongNameTruncation:
    def test_long_name_truncated(self):
        """Name longer than 38 chars is truncated with '...' suffix."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        long_name = "A" * 39  # 39 chars → triggers truncation
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task(name=long_name)]})
        call_args = mock_ax.text.call_args
        label_text = call_args[0][2]
        assert label_text.endswith("...")
        assert len(label_text) == 38 + 3  # 38 chars + "..."

    def test_name_exactly_38_not_truncated(self):
        """Name exactly 38 chars is NOT truncated."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        exact_name = "B" * 38
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task(name=exact_name)]})
        call_args = mock_ax.text.call_args
        label_text = call_args[0][2]
        assert not label_text.endswith("...")
        assert label_text == exact_name

    def test_short_name_not_truncated(self):
        """Name shorter than 38 chars is returned as-is."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task(name="Short")]})
        call_args = mock_ax.text.call_args
        label_text = call_args[0][2]
        assert label_text == "Short"


# ---------------------------------------------------------------------------
# 7. Level color cycling through _GANTT_LEVEL_COLORS
# ---------------------------------------------------------------------------

class TestLevelColors:
    def test_level_0_uses_first_color(self):
        """level=0 → first color from _GANTT_LEVEL_COLORS."""
        from concilium.application.runtime.deliverables.visualizations.charts.gantt import (
            _GANTT_LEVEL_COLORS,
        )
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task(level=0)]})
        call_kwargs = mock_ax.broken_barh.call_args[1]
        assert call_kwargs["facecolors"] == _GANTT_LEVEL_COLORS[0]

    def test_level_cycles_beyond_palette_length(self):
        """level >= len(colors) wraps around via modulo."""
        from concilium.application.runtime.deliverables.visualizations.charts.gantt import (
            _GANTT_LEVEL_COLORS,
        )
        n = len(_GANTT_LEVEL_COLORS)
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task(level=n)]})  # wraps to index 0
        call_kwargs = mock_ax.broken_barh.call_args[1]
        assert call_kwargs["facecolors"] == _GANTT_LEVEL_COLORS[0]

    def test_multiple_levels_all_valid_colors(self):
        """Five tasks with different levels all produce valid colors."""
        from concilium.application.runtime.deliverables.visualizations.charts.gantt import (
            _GANTT_LEVEL_COLORS,
        )
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        tasks = [
            _one_task(start=f"2024-0{i+1}-01", name=f"Task {i}", level=i)
            for i in range(1, 6)
        ]
        with _patched_init_mpl(mock_plt):
            result = build({"tasks": tasks})
        assert result == b"PNG"
        assert mock_ax.broken_barh.call_count == 5
        for call in mock_ax.broken_barh.call_args_list:
            color = call[1]["facecolors"]
            assert color in _GANTT_LEVEL_COLORS


# ---------------------------------------------------------------------------
# 8. Duration defaults (missing duration_days → 7)
# ---------------------------------------------------------------------------

class TestDurationDefaults:
    def test_missing_duration_defaults_to_7(self):
        """Task without duration_days defaults to 7."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        task = {"start": "2024-01-01", "name": "No duration"}
        with _patched_init_mpl(mock_plt):
            build({"tasks": [task]})
        call_args = mock_ax.broken_barh.call_args
        bars = call_args[0][0]  # first positional arg: list of (start, duration) tuples
        _, duration = bars[0]
        assert duration == 7

    def test_explicit_duration_used(self):
        """Explicit duration_days is used as bar width."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task(duration_days=30)]})
        call_args = mock_ax.broken_barh.call_args
        bars = call_args[0][0]
        _, duration = bars[0]
        assert duration == 30


# ---------------------------------------------------------------------------
# 9. Error path (rendering exception → returns None)
# ---------------------------------------------------------------------------

class TestErrorPath:
    def test_subplots_raises_returns_none(self):
        """When plt.subplots raises, the except block catches it and returns None."""
        build = _import_fn()
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("no display")
        with _patched_init_mpl(mock_plt):
            result = build({"tasks": [_one_task()]})
        assert result is None

    def test_subplots_raises_calls_plt_close(self):
        """When plt.subplots raises, plt.close('all') is called."""
        build = _import_fn()
        mock_plt = MagicMock()
        mock_plt.subplots.side_effect = RuntimeError("no display")
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task()]})
        mock_plt.close.assert_called_once_with("all")

    def test_fig_to_bytes_raises_returns_none(self):
        """When fig_to_bytes raises, the except block catches it and returns None."""
        def _bad_fig_to_bytes(fig):
            raise OSError("disk full")

        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with patch(
            f"{_MOD}.init_mpl",
            return_value=(mock_plt, _bad_fig_to_bytes),
        ):
            result = build({"tasks": [_one_task()]})
        assert result is None

    def test_broken_barh_raises_returns_none(self):
        """When ax.broken_barh raises, error is caught and None returned."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        mock_ax.broken_barh.side_effect = ValueError("bad date")
        with _patched_init_mpl(mock_plt):
            result = build({"tasks": [_one_task()]})
        assert result is None


# ---------------------------------------------------------------------------
# 10. figsize scales with number of tasks
# ---------------------------------------------------------------------------

class TestFigsize:
    def test_figsize_height_scales_with_tasks(self):
        """figsize height = max(4, n_tasks * 0.7 + 2)."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        tasks = [_one_task(start=f"2024-0{i+1}-01", name=f"T{i}") for i in range(1, 4)]
        with _patched_init_mpl(mock_plt):
            build({"tasks": tasks})
        call_args = mock_plt.subplots.call_args
        figsize = call_args[1]["figsize"]
        expected_height = max(4, 3 * 0.7 + 2)
        assert figsize == (14, expected_height)

    def test_single_task_uses_min_height(self):
        """Single task: max(4, 1*0.7+2) = max(4, 2.7) = 4."""
        build = _import_fn()
        mock_plt, mock_fig, mock_ax = _make_plt_mock()
        with _patched_init_mpl(mock_plt):
            build({"tasks": [_one_task()]})
        call_args = mock_plt.subplots.call_args
        figsize = call_args[1]["figsize"]
        assert figsize[1] == 4  # max(4, 0.7+2) = 4
