from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
    _accumulate_predecessors,
    _add_predecessors_to_adj,
    _assign_positions,
    _barycenter_order,
    _bfs_relax_neighbors,
    _break_long_label,
    _build_networkx,
    _draw_edges,
    _edge_rad,
    _get_edge_info,
    _pred_id_from,
    build_dependencia_eap,
)

# ---------------------------------------------------------------------------
# build_dependencia_eap
# ---------------------------------------------------------------------------


def test_build_dependencia_eap_empty_tasks_returns_none():
    assert build_dependencia_eap({"tasks": []}) is None


def test_build_dependencia_eap_no_tasks_key_returns_none():
    assert build_dependencia_eap({}) is None


def test_build_dependencia_eap_non_dict_returns_none():
    assert build_dependencia_eap("not a dict") is None


# ---------------------------------------------------------------------------
# _pred_id_from
# ---------------------------------------------------------------------------


def test_pred_id_from_dict_with_item_id():
    assert _pred_id_from({"item_id": "42", "tipo": "FS"}) == "42"


def test_pred_id_from_non_dict_str():
    assert _pred_id_from("99") == "99"


def test_pred_id_from_non_dict_int():
    assert _pred_id_from(7) == "7"


# ---------------------------------------------------------------------------
# _add_predecessors_to_adj
# ---------------------------------------------------------------------------


def test_add_predecessors_to_adj_pred_in_adj_adds_successor():
    adj = {"A": set(), "B": set()}
    task = {"item_id": "B", "predecessores": [{"item_id": "A"}]}
    _add_predecessors_to_adj(adj, task)
    assert "B" in adj["A"]


def test_add_predecessors_to_adj_pred_not_in_adj_skips():
    adj = {"B": set()}
    task = {"item_id": "B", "predecessores": [{"item_id": "X"}]}
    _add_predecessors_to_adj(adj, task)
    assert adj == {"B": set()}


# ---------------------------------------------------------------------------
# _accumulate_predecessors
# ---------------------------------------------------------------------------


def test_accumulate_predecessors_pred_in_pred_count_adds():
    pred_count = {"A": set(), "B": set()}
    task = {"item_id": "B", "predecessores": [{"item_id": "A"}]}
    _accumulate_predecessors(pred_count, "B", task)
    assert "A" in pred_count["B"]


def test_accumulate_predecessors_pred_not_in_pred_count_skips():
    pred_count = {"B": set()}
    task = {"item_id": "B", "predecessores": [{"item_id": "X"}]}
    _accumulate_predecessors(pred_count, "B", task)
    assert pred_count["B"] == set()


# ---------------------------------------------------------------------------
# _bfs_relax_neighbors
# ---------------------------------------------------------------------------


def test_bfs_relax_neighbors_in_deg_drops_to_zero_queued():
    from collections import deque

    level = {"A": 0, "B": 0}
    in_deg = {"A": 0, "B": 1}
    adj = {"A": {"B"}}
    queue = deque()
    _bfs_relax_neighbors(level, in_deg, queue, adj, "A")
    assert in_deg["B"] == 0
    assert "B" in queue
    assert level["B"] == 1


def test_bfs_relax_neighbors_in_deg_not_zero_not_queued():
    from collections import deque

    level = {"A": 0, "B": 0, "C": 0}
    in_deg = {"A": 0, "B": 2, "C": 1}
    adj = {"A": {"B"}}
    queue = deque()
    _bfs_relax_neighbors(level, in_deg, queue, adj, "A")
    assert in_deg["B"] == 1
    assert "B" not in queue


# ---------------------------------------------------------------------------
# _barycenter_order
# ---------------------------------------------------------------------------


def test_barycenter_order_with_preds_in_prev_pos():
    layer = ["B", "C"]
    prev_pos = {"A": 1.0}
    pred_adj = {"B": {"A"}, "C": set()}
    result = _barycenter_order(layer, prev_pos, pred_adj)
    # B has a predecessor with a position, C has none (inf) → B comes first
    assert result[0] == "B"
    assert result[1] == "C"


def test_barycenter_order_without_preds_in_prev_pos():
    layer = ["X", "Y"]
    prev_pos = {}
    pred_adj = {"X": set(), "Y": set()}
    result = _barycenter_order(layer, prev_pos, pred_adj)
    # All inf, sorted by name
    assert result == sorted(layer)


# ---------------------------------------------------------------------------
# _assign_positions
# ---------------------------------------------------------------------------


def test_assign_positions_chain_levels():
    tasks = [
        {"item_id": "A", "predecessores": []},
        {"item_id": "B", "predecessores": [{"item_id": "A"}]},
        {"item_id": "C", "predecessores": [{"item_id": "B"}]},
    ]
    pos, adj = _assign_positions(tasks)
    # A should be at level 0 (x=0), B at level 1 (x=4), C at level 2 (x=8)
    assert pos["A"][0] == pytest.approx(0.0)
    assert pos["B"][0] == pytest.approx(4.0)
    assert pos["C"][0] == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# _edge_rad
# ---------------------------------------------------------------------------


def test_edge_rad_same_y_returns_zero():
    assert _edge_rad(1.0, 1.0) == pytest.approx(0.0)


def test_edge_rad_y1_less_than_y0_returns_positive():
    assert _edge_rad(2.0, 1.0) == pytest.approx(0.25)


def test_edge_rad_y1_greater_than_y0_returns_negative():
    assert _edge_rad(1.0, 2.0) == pytest.approx(-0.25)


def test_edge_rad_very_close_y_returns_zero():
    assert _edge_rad(1.0, 1.005) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# _get_edge_info
# ---------------------------------------------------------------------------


def test_get_edge_info_dict_with_tipo_lag_zero():
    pred = {"item_id": "A", "tipo": "SS", "lag": 0}
    pred_id, tipo, lag, edge_label = _get_edge_info(pred)
    assert pred_id == "A"
    assert tipo == "SS"
    assert lag == 0
    assert edge_label == "SS"


def test_get_edge_info_dict_with_lag_greater_than_zero():
    pred = {"item_id": "A", "tipo": "FS", "lag": 3}
    pred_id, tipo, lag, edge_label = _get_edge_info(pred)
    assert lag == 3
    assert edge_label == "FS+3sem"


def test_get_edge_info_non_dict():
    pred_id, tipo, lag, edge_label = _get_edge_info("42")
    assert pred_id == "42"
    assert tipo == "FS"
    assert lag == 0
    assert edge_label == "FS"


# ---------------------------------------------------------------------------
# _draw_edges
# ---------------------------------------------------------------------------


def test_draw_edges_pred_not_in_pos_skips():
    ax = MagicMock()
    pe = MagicMock()
    tasks = [{"item_id": "B", "predecessores": [{"item_id": "X"}]}]
    pos = {"B": (4.0, 0.0)}
    # X is not in pos → should skip without error
    _draw_edges(ax, tasks, pos, pe)
    ax.annotate.assert_not_called()


# ---------------------------------------------------------------------------
# _break_long_label
# ---------------------------------------------------------------------------


def test_break_long_label_short_unchanged():
    label = "Short label"
    assert _break_long_label(label) == label


def test_break_long_label_long_with_space_splits():
    label = "A very long label that exceeds the limit here"
    result = _break_long_label(label)
    assert "\n" in result


def test_break_long_label_long_no_spaces_unchanged():
    label = "A" * 40
    result = _break_long_label(label)
    assert "\n" not in result
    assert result == label


# ---------------------------------------------------------------------------
# _build_networkx
# ---------------------------------------------------------------------------


def test_build_networkx_import_error_returns_none():
    with patch(
        "concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap.init_mpl",
        side_effect=ImportError("no matplotlib"),
    ):
        tasks = [{"item_id": "A", "predecessores": []}]
        result = _build_networkx(tasks)
    assert result is None


def test_build_networkx_exception_during_draw_returns_none():
    mock_plt = MagicMock()
    mock_fig_to_bytes = MagicMock(side_effect=RuntimeError("draw failed"))

    with patch(
        "concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap.init_mpl",
        return_value=(mock_plt, mock_fig_to_bytes),
    ):
        tasks = [{"item_id": "A", "predecessores": []}]
        result = _build_networkx(tasks)
    assert result is None


def test_build_networkx_success_returns_bytes():
    fake_bytes = b"PNG_DATA"
    mock_plt = MagicMock()
    mock_fig_to_bytes = MagicMock(return_value=fake_bytes)
    mock_fig = MagicMock()
    mock_ax = MagicMock()
    mock_plt.subplots.return_value = (mock_fig, mock_ax)

    with patch(
        "concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap.init_mpl",
        return_value=(mock_plt, mock_fig_to_bytes),
    ):
        tasks = [{"item_id": "A", "predecessores": []}]
        result = _build_networkx(tasks)
    assert result == fake_bytes


# ─── dependencia_eap.py lines 197-202, 214-215, 242, 303 ────────────────────


class TestDrawSingleEdge:
    """Lines 197-202, 214-215: _draw_single_edge draws arrow + label."""

    def test_calls_annotate_and_text(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_single_edge,
        )

        ax = MagicMock()
        pe = MagicMock()
        pos = {"A": (0.0, 0.0), "B": (4.0, 1.0)}

        _draw_single_edge(ax, pos, "A", "B", "FS", pe)

        ax.annotate.assert_called_once()
        ax.text.assert_called_once()

    def test_same_y_uses_zero_rad(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_single_edge,
        )

        ax = MagicMock()
        pe = MagicMock()
        pos = {"X": (0.0, 0.0), "Y": (4.0, 0.0)}

        _draw_single_edge(ax, pos, "X", "Y", "FS+2sem", pe)

        ax.annotate.assert_called_once()


class TestDrawEdgesCallsSingle:
    """Line 242: _draw_single_edge called when pred is in pos."""

    def test_pred_in_pos_triggers_draw_single_edge(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_edges,
        )

        ax = MagicMock()
        pe = MagicMock()
        tasks = [{"item_id": "B", "predecessores": [{"item_id": "A"}]}]
        pos = {"A": (0.0, 0.0), "B": (4.0, 0.0)}

        _draw_edges(ax, tasks, pos, pe)

        ax.annotate.assert_called_once()

    def test_multiple_predecessors_draws_each(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _draw_edges,
        )

        ax = MagicMock()
        pe = MagicMock()
        tasks = [
            {"item_id": "C", "predecessores": [{"item_id": "A"}, {"item_id": "B"}]}
        ]
        pos = {"A": (0.0, 0.0), "B": (0.0, 1.0), "C": (4.0, 0.5)}

        _draw_edges(ax, tasks, pos, pe)

        assert ax.annotate.call_count == 2


class TestBuildNetworkxPosEmpty:
    """Line 303: return None when _assign_positions yields empty pos."""

    def test_returns_none_when_pos_empty(self):
        from concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap import (
            _build_networkx,
        )

        mock_plt = MagicMock()
        mock_fig_to_bytes = MagicMock()

        with (
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap.init_mpl",
                return_value=(mock_plt, mock_fig_to_bytes),
            ),
            patch(
                "concilium.application.runtime.deliverables.visualizations.charts.dependencia_eap._assign_positions",
                return_value=({}, {}),
            ),
        ):
            result = _build_networkx([{"item_id": "A", "predecessores": []}])

        assert result is None

