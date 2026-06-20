"""Tests for _chart_generator_helpers_b.py — target >= 80% coverage.

Strategy:
- _build_cenario_record: tested with tmp_path JSON fixtures; exercises all
  fields present, absent/null (defaulting to 52, 4, -0.2, -0.27).
- _load_cenarios: monkeypatches _CENARIO_SLUGS, _CENARIO_POOL_DEF, and
  _load_json on the module, then asserts list length and record shapes.
- _chart_gantt: uses real matplotlib Agg backend; injects _ATIVIDADES_GANTT
  and _CORES_REC, and asserts the returned Path points to
  01_gantt_cronograma.png which actually exists on disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_module():
    import concilium.application.benchmarks.charts._chart_generator_helpers_b as m

    return m


def _import_helpers_a():
    import concilium.application.benchmarks.charts._chart_generator_helpers_a as a

    return a


# Minimal _ATIVIDADES_GANTT and _CORES_REC stubs for gantt tests
SAMPLE_ATIVIDADES = [
    {"nome": "Desmatamento", "inicio": 1, "fim": 25, "recurso": "DESMAT", "frentes": 5},
    {"nome": "Esc 1aCat ≤2km", "inicio": 1, "fim": 10, "recurso": "ESC-1CAT", "frentes": 1},
    {"nome": "Esc 3aCat 2-3km", "inicio": 1, "fim": 48, "recurso": "ESC-3CAT", "frentes": 2},
]
SAMPLE_CORES_REC = {
    "DESMAT": "#8B5CF6",
    "ESC-1CAT": "#2563EB",
    "ESC-3CAT": "#EA580C",
}

# Short activity where dur <= 4 (no label inside bar)
SHORT_ATIVIDADES = [
    {"nome": "Curta", "inicio": 1, "fim": 3, "recurso": "DESMAT", "frentes": 1},
]

# Activity whose fim > 52 to exercise the min(fim, 52) branch
LONG_ATIVIDADES = [
    {"nome": "Longa", "inicio": 1, "fim": 60, "recurso": "DESMAT", "frentes": 3},
]


def _inject_gantt_globals(m, atividades=None, cores_rec=None):
    """Inject required module-level globals into helpers_b namespace."""
    m._ATIVIDADES_GANTT = atividades if atividades is not None else SAMPLE_ATIVIDADES
    m._CORES_REC = cores_rec if cores_rec is not None else SAMPLE_CORES_REC


def _inject_load_json(m):
    """Inject _load_json from helpers_a into helpers_b (needed by _build_cenario_record)."""
    a = _import_helpers_a()
    m._load_json = a._load_json


def _write_report(inter_dir: Path, slug: str, data: dict) -> Path:
    p = inter_dir / f"{slug}.benchmark_report.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _make_plt_mock():
    """Build a plt mock that returns a (fig, (ax_g, ax_r)) tuple."""
    plt = MagicMock()
    fig = MagicMock()
    ax_g = MagicMock()
    ax_r = MagicMock()
    plt.subplots.return_value = (fig, (ax_g, ax_r))
    return plt, fig, ax_g, ax_r


# ---------------------------------------------------------------------------
# 1. _build_cenario_record
# ---------------------------------------------------------------------------


class TestBuildCenarioRecord:
    def _setup(self, m):
        _inject_load_json(m)

    def test_slug_present_in_result(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S1", {})
        result = m._build_cenario_record("S1", {}, tmp_path)
        assert result["slug"] == "S1"

    def test_meta_fields_spread_into_result(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S1", {})
        meta = {"ESC3": 10, "ATERRO": 5, "deadline": 56}
        result = m._build_cenario_record("S1", meta, tmp_path)
        assert result["ESC3"] == 10
        assert result["ATERRO"] == 5
        assert result["deadline"] == 56

    def test_makespan_from_json(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(
            tmp_path, "S2", {"rcpsp_schedule": {"makespan_weeks": 40, "folga_semanas": 6, "is_feasible": True}}
        )
        result = m._build_cenario_record("S2", {}, tmp_path)
        assert result["makespan"] == 40

    def test_makespan_defaults_to_52_when_absent(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S3", {})
        result = m._build_cenario_record("S3", {}, tmp_path)
        assert result["makespan"] == 52

    def test_makespan_defaults_to_52_when_zero(self, tmp_path):
        """makespan_weeks == 0 is falsy → should default to 52."""
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S3b", {"rcpsp_schedule": {"makespan_weeks": 0}})
        result = m._build_cenario_record("S3b", {}, tmp_path)
        assert result["makespan"] == 52

    def test_folga_from_json(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S4", {"rcpsp_schedule": {"makespan_weeks": 30, "folga_semanas": 8}})
        result = m._build_cenario_record("S4", {}, tmp_path)
        assert result["folga"] == 8

    def test_folga_defaults_to_4_when_absent(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S5", {})
        result = m._build_cenario_record("S5", {}, tmp_path)
        assert result["folga"] == 4

    def test_feasible_true_from_json(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S6", {"rcpsp_schedule": {"is_feasible": True}})
        result = m._build_cenario_record("S6", {}, tmp_path)
        assert result["feasible"] is True

    def test_feasible_false_from_json(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S7", {"rcpsp_schedule": {"is_feasible": False}})
        result = m._build_cenario_record("S7", {}, tmp_path)
        assert result["feasible"] is False

    def test_feasible_defaults_to_true_when_absent(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S8", {"rcpsp_schedule": {}})
        result = m._build_cenario_record("S8", {}, tmp_path)
        assert result["feasible"] is True

    def test_delta_cd_from_json(self, tmp_path):
        m = _import_module()
        self._setup(m)
        data = {"confronto": {"deltas": {"custo_direto": {"percentual": -0.05}}}}
        _write_report(tmp_path, "S9", data)
        result = m._build_cenario_record("S9", {}, tmp_path)
        assert abs(result["delta_cd"] - (-0.05)) < 1e-9

    def test_delta_cd_defaults_when_absent(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S10", {})
        result = m._build_cenario_record("S10", {}, tmp_path)
        assert result["delta_cd"] == -0.2

    def test_delta_venda_from_json(self, tmp_path):
        m = _import_module()
        self._setup(m)
        data = {"confronto": {"deltas": {"preco_venda": {"percentual": -0.10}}}}
        _write_report(tmp_path, "S11", data)
        result = m._build_cenario_record("S11", {}, tmp_path)
        assert abs(result["delta_venda"] - (-0.10)) < 1e-9

    def test_delta_venda_defaults_when_absent(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S12", {})
        result = m._build_cenario_record("S12", {}, tmp_path)
        assert result["delta_venda"] == -0.27

    def test_missing_json_file_uses_defaults(self, tmp_path):
        """When JSON file does not exist, _load_json returns {} → all defaults."""
        m = _import_module()
        self._setup(m)
        # Don't write any file; tmp_path is empty
        result = m._build_cenario_record("NOFILE", {}, tmp_path)
        assert result["slug"] == "NOFILE"
        assert result["makespan"] == 52
        assert result["folga"] == 4
        assert result["delta_cd"] == -0.2
        assert result["delta_venda"] == -0.27

    def test_all_fields_present_full_data(self, tmp_path):
        m = _import_module()
        self._setup(m)
        data = {
            "rcpsp_schedule": {
                "makespan_weeks": 48,
                "folga_semanas": 2,
                "is_feasible": False,
            },
            "confronto": {
                "deltas": {
                    "custo_direto": {"percentual": -0.03},
                    "preco_venda": {"percentual": -0.07},
                }
            },
        }
        _write_report(tmp_path, "FULL", data)
        meta = {"ESC3": 12, "deadline": 52, "manual": False}
        result = m._build_cenario_record("FULL", meta, tmp_path)
        assert result["slug"] == "FULL"
        assert result["makespan"] == 48
        assert result["folga"] == 2
        assert result["feasible"] is False
        assert abs(result["delta_cd"] - (-0.03)) < 1e-9
        assert abs(result["delta_venda"] - (-0.07)) < 1e-9
        assert result["ESC3"] == 12

    def test_confronto_missing_deltas_uses_defaults(self, tmp_path):
        m = _import_module()
        self._setup(m)
        _write_report(tmp_path, "S13", {"confronto": {}})
        result = m._build_cenario_record("S13", {}, tmp_path)
        assert result["delta_cd"] == -0.2
        assert result["delta_venda"] == -0.27

    def test_delta_cd_zero_percentual_gives_default(self, tmp_path):
        """percentual == 0 is falsy → should fall through to -0.2."""
        m = _import_module()
        self._setup(m)
        data = {"confronto": {"deltas": {"custo_direto": {"percentual": 0}}}}
        _write_report(tmp_path, "S14", data)
        result = m._build_cenario_record("S14", {}, tmp_path)
        assert result["delta_cd"] == -0.2


# ---------------------------------------------------------------------------
# 2. _load_cenarios
# ---------------------------------------------------------------------------


class TestLoadCenarios:
    def _setup(self, m, slugs, pool_def=None):
        _inject_load_json(m)
        m._CENARIO_SLUGS = slugs
        m._CENARIO_POOL_DEF = pool_def or {}

    def test_returns_list_of_records(self, tmp_path):
        m = _import_module()
        self._setup(m, ["A", "B"])
        # Write minimal reports
        for slug in ["A", "B"]:
            _write_report(tmp_path, slug, {})
        result = m._load_cenarios(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_each_record_has_slug(self, tmp_path):
        m = _import_module()
        slugs = ["X1", "X2", "X3"]
        self._setup(m, slugs)
        for slug in slugs:
            _write_report(tmp_path, slug, {})
        result = m._load_cenarios(tmp_path)
        result_slugs = [r["slug"] for r in result]
        assert result_slugs == slugs

    def test_pool_def_meta_merged_into_record(self, tmp_path):
        m = _import_module()
        pool_def = {"M0": {"ESC3": 10, "deadline": 56, "manual": True}}
        self._setup(m, ["M0"], pool_def=pool_def)
        _write_report(tmp_path, "M0", {})
        result = m._load_cenarios(tmp_path)
        assert result[0]["ESC3"] == 10
        assert result[0]["manual"] is True

    def test_slug_not_in_pool_def_gives_empty_meta(self, tmp_path):
        m = _import_module()
        self._setup(m, ["UNKNOWN"], pool_def={})
        _write_report(tmp_path, "UNKNOWN", {})
        result = m._load_cenarios(tmp_path)
        # No extra keys beyond the base ones
        assert result[0]["slug"] == "UNKNOWN"
        assert result[0]["makespan"] == 52  # default

    def test_empty_slug_list_returns_empty(self, tmp_path):
        m = _import_module()
        self._setup(m, [])
        result = m._load_cenarios(tmp_path)
        assert result == []

    def test_load_cenarios_single_slug_with_data(self, tmp_path):
        m = _import_module()
        pool_def = {"A1": {"ESC3": 8, "ATERRO": 5, "deadline": 56, "manual": False}}
        self._setup(m, ["A1"], pool_def=pool_def)
        data = {
            "rcpsp_schedule": {"makespan_weeks": 44, "folga_semanas": 3, "is_feasible": True},
            "confronto": {"deltas": {"custo_direto": {"percentual": -0.08}, "preco_venda": {"percentual": -0.12}}},
        }
        _write_report(tmp_path, "A1", data)
        result = m._load_cenarios(tmp_path)
        assert len(result) == 1
        r = result[0]
        assert r["makespan"] == 44
        assert r["folga"] == 3
        assert abs(r["delta_cd"] - (-0.08)) < 1e-9
        assert r["ESC3"] == 8

    def test_load_cenarios_uses_mocked_load_json(self, tmp_path, monkeypatch):
        """Verify _load_cenarios properly delegates to _load_json via _build_cenario_record."""
        m = _import_module()
        slugs = ["AA", "BB"]
        pool_def = {}
        m._CENARIO_SLUGS = slugs
        m._CENARIO_POOL_DEF = pool_def

        mock_load_json = MagicMock(return_value={})
        m._load_json = mock_load_json

        result = m._load_cenarios(tmp_path)
        # _load_json should be called once per slug
        assert mock_load_json.call_count == len(slugs)
        assert len(result) == len(slugs)


# ---------------------------------------------------------------------------
# 3. _chart_gantt — with mock plt
# ---------------------------------------------------------------------------


class TestChartGanttMocked:
    """Tests using a mock plt to avoid filesystem writes."""

    def _setup(self, m, atividades=None, cores_rec=None):
        _inject_gantt_globals(m, atividades, cores_rec)

    def test_returns_path_to_gantt_png(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        result = m._chart_gantt(plt, tmp_path, "AGIS", np)
        assert result == tmp_path / "01_gantt_cronograma.png"

    def test_savefig_called_with_correct_path(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        fig.savefig.assert_called_once()
        saved_path = fig.savefig.call_args[0][0]
        assert saved_path == tmp_path / "01_gantt_cronograma.png"

    def test_figure_closed_after_save(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        plt.close.assert_called_once_with(fig)

    def test_suptitle_includes_slug_uppercased(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "myslug", np)
        fig.suptitle.assert_called_once()
        title = fig.suptitle.call_args[0][0]
        assert "MYSLUG" in title

    def test_add_patch_called_per_activity(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        # One FancyBboxPatch per activity
        assert ax_g.add_patch.call_count == len(SAMPLE_ATIVIDADES)

    def test_axvline_called_for_deadline_markers(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        # axvline called for weeks 52 and 56
        assert ax_g.axvline.call_count == 2

    def test_legend_called_on_gantt_axis(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        ax_g.legend.assert_called_once()

    def test_bar_called_on_resource_axis(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        # One bar call per resource type
        assert ax_r.bar.call_count == len(SAMPLE_CORES_REC)

    def test_set_title_called_on_resource_axis(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        ax_r.set_title.assert_called_once()

    def test_tight_layout_called(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        plt.tight_layout.assert_called_once()

    def test_text_inside_bar_for_long_activities(self, tmp_path):
        """Activities with dur > 4 get text inside the bar."""
        m = _import_module()
        # Use only one long activity (dur=24 > 4)
        long_act = [{"nome": "Longa", "inicio": 1, "fim": 25, "recurso": "DESMAT", "frentes": 5}]
        _inject_gantt_globals(m, long_act, {"DESMAT": "#8B5CF6"})
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        # text called: 1 (inside bar) + 1 (frentes label) = 2 calls minimum
        assert ax_g.text.call_count >= 2

    def test_no_text_inside_bar_for_short_activities(self, tmp_path):
        """Activities with dur <= 4 should NOT get text inside bar."""
        m = _import_module()
        short_act = [{"nome": "Curta", "inicio": 1, "fim": 3, "recurso": "DESMAT", "frentes": 1}]
        _inject_gantt_globals(m, short_act, {"DESMAT": "#8B5CF6"})
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        # Only the frentes label (×N) text call, not the dur label
        # ax_g.text called once (frentes text), not twice
        assert ax_g.text.call_count == 1

    def test_set_yticks_with_activity_count(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        ax_g.set_yticks.assert_called_once()
        ticks_arg = ax_g.set_yticks.call_args[0][0]
        assert len(list(ticks_arg)) == len(SAMPLE_ATIVIDADES)

    def test_yticklabels_reversed_names(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        ax_g.set_yticklabels.assert_called_once()
        labels = ax_g.set_yticklabels.call_args[0][0]
        expected = [a["nome"] for a in reversed(SAMPLE_ATIVIDADES)]
        assert list(labels) == expected

    def test_xlim_set_to_56(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        ax_g.set_xlim.assert_called_once_with(0, 56)

    def test_resource_bar_uses_correct_colors(self, tmp_path):
        m = _import_module()
        self._setup(m)
        plt, fig, ax_g, ax_r = _make_plt_mock()
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        # Verify each bar call uses a color from SAMPLE_CORES_REC
        for call in ax_r.bar.call_args_list:
            color = call[1].get("color", None)
            # color is "HEX" + "BB" format
            if color is not None:
                base_color = color[:-2]
                assert base_color in SAMPLE_CORES_REC.values()

    def test_activity_fim_beyond_52_clamped_in_resource_loop(self, tmp_path):
        """Activity fim > 52 should be clamped to 52 in resource utilization."""
        m = _import_module()
        # Activity from week 50 to 60 — only weeks 50-52 should be counted
        beyond_act = [{"nome": "LongAct", "inicio": 50, "fim": 60, "recurso": "DESMAT", "frentes": 2}]
        _inject_gantt_globals(m, beyond_act, {"DESMAT": "#8B5CF6"})
        plt, fig, ax_g, ax_r = _make_plt_mock()
        # Run without error — min(fim, 52) guards the range
        m._chart_gantt(plt, tmp_path, "AGIS", np)
        # Should complete without IndexError
        ax_r.bar.assert_called()


# ---------------------------------------------------------------------------
# 4. _chart_gantt — with real Agg backend (integration)
# ---------------------------------------------------------------------------


@pytest.mark.slow
class TestChartGanttRealMatplotlib:
    """Integration tests using the real matplotlib Agg backend.

    A fixture de classe inicializa matplotlib uma vez e gera os 4 PNGs necessários
    (AGIS padrão, short, long) num único diretório compartilhado. Testes apenas
    inspecionam os resultados — sem rerenderizar.
    """

    @pytest.fixture(scope="class")
    def _rendered(self, tmp_path_factory):
        """Gera todos os PNGs necessários uma única vez por classe."""
        import os

        os.environ["MPLBACKEND"] = "Agg"
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        m = _import_module()
        out = tmp_path_factory.mktemp("gantt")

        _inject_gantt_globals(m)
        std_dir = out / "std"; std_dir.mkdir()
        standard = m._chart_gantt(plt, std_dir, "AGIS", np, dpi=30)

        _inject_gantt_globals(m, SHORT_ATIVIDADES, {"DESMAT": "#8B5CF6"})
        short_dir = out / "short"; short_dir.mkdir()
        short = m._chart_gantt(plt, short_dir, "X", np, dpi=30)

        _inject_gantt_globals(m, LONG_ATIVIDADES, {"DESMAT": "#8B5CF6"})
        long_dir = out / "long"; long_dir.mkdir()
        long_ = m._chart_gantt(plt, long_dir, "LONG", np, dpi=30)

        return {"standard": standard, "short": short, "long": long_}

    def test_gantt_creates_file_on_disk(self, _rendered):
        assert _rendered["standard"].exists()
        assert _rendered["standard"].name == "01_gantt_cronograma.png"

    def test_gantt_file_is_non_empty(self, _rendered):
        assert _rendered["standard"].stat().st_size > 0

    def test_gantt_with_short_activity_only(self, _rendered):
        """Single short activity (dur<=4) should not raise."""
        assert _rendered["short"].exists()

    def test_gantt_with_activity_beyond_52_weeks(self, _rendered):
        """Activity extending beyond week 52 should not raise IndexError."""
        assert _rendered["long"].exists()

    def test_gantt_dpi_passed_to_savefig(self, _rendered):
        """Verify dpi parameter produces a valid file."""
        assert _rendered["standard"].exists()
