"""Tests for chart_generator.py entry point (gerar_graficos_benchmark).

Strategy: mock all six chart helper functions and _setup_matplotlib + numpy
so that the entry-point orchestration is tested without real matplotlib calls.
Also test the module-level constants and data are accessible.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_module():
    import concilium.application.benchmarks.charts.chart_generator as m

    return m


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestModuleConstants:
    def test_cenario_slugs_nonempty(self):
        m = _import_module()
        assert len(m._CENARIO_SLUGS) > 0

    def test_cenario_pool_def_has_all_slugs(self):
        m = _import_module()
        for slug in m._CENARIO_SLUGS:
            assert slug in m._CENARIO_POOL_DEF

    def test_atividades_gantt_nonempty(self):
        m = _import_module()
        assert len(m._ATIVIDADES_GANTT) > 0

    def test_eap_data_nonempty(self):
        m = _import_module()
        assert len(m._EAP_DATA) > 0

    def test_indir_data_keys(self):
        m = _import_module()
        for cat in ("ADM", "TOP", "LAB", "QSMS", "MOB"):
            assert cat in m._INDIR_DATA

    def test_times_data_nonempty(self):
        m = _import_module()
        assert len(m._TIMES_DATA) > 0


# ---------------------------------------------------------------------------
# gerar_graficos_benchmark — mocked end-to-end
# ---------------------------------------------------------------------------


class TestGerarGraficosBenchmark:
    def _make_path_mocks(self, out_dir: Path) -> list[Path]:
        return [
            out_dir / "01_gantt_cronograma.png",
            out_dir / "02_plan_space.png",
            out_dir / "03_waterfall_financeiro.png",
            out_dir / "04_eap_criticidade.png",
            out_dir / "05_indiretos_composicao.png",
            out_dir / "06_times_indiretos.png",
        ]

    def test_returns_six_paths(self, tmp_path: Path):
        m = _import_module()
        out_dir = tmp_path / "outputs"
        expected_paths = self._make_path_mocks(out_dir)

        plt_mock = MagicMock()
        np_mock = MagicMock()
        cenarios_mock = [{"slug": "A0_BASE_AUTO"}]

        with (
            patch.object(m, "_setup_matplotlib", return_value=plt_mock),
            patch("concilium.application.benchmarks.charts.chart_generator.np", np_mock, create=True),
            patch.object(m, "_load_cenarios", return_value=cenarios_mock),
            patch.object(m, "_chart_gantt", return_value=expected_paths[0]),
            patch.object(m, "_chart_plan_space", return_value=expected_paths[1]),
            patch.object(m, "_chart_waterfall", return_value=expected_paths[2]),
            patch.object(m, "_chart_eap_crit", return_value=expected_paths[3]),
            patch.object(m, "_chart_indiretos", return_value=expected_paths[4]),
            patch.object(m, "_chart_times", return_value=expected_paths[5]),
        ):
            result = m.gerar_graficos_benchmark(tmp_path, "AGIS")
            assert len(result) == 6

    def test_out_dir_created(self, tmp_path: Path):
        m = _import_module()
        out_dir = tmp_path / "outputs"
        expected_paths = self._make_path_mocks(out_dir)

        plt_mock = MagicMock()
        np_mock = MagicMock()

        with (
            patch.object(m, "_setup_matplotlib", return_value=plt_mock),
            patch("concilium.application.benchmarks.charts.chart_generator.np", np_mock, create=True),
            patch.object(m, "_load_cenarios", return_value=[]),
            patch.object(m, "_chart_gantt", return_value=expected_paths[0]),
            patch.object(m, "_chart_plan_space", return_value=expected_paths[1]),
            patch.object(m, "_chart_waterfall", return_value=expected_paths[2]),
            patch.object(m, "_chart_eap_crit", return_value=expected_paths[3]),
            patch.object(m, "_chart_indiretos", return_value=expected_paths[4]),
            patch.object(m, "_chart_times", return_value=expected_paths[5]),
        ):
            m.gerar_graficos_benchmark(tmp_path, "AGIS")
            assert out_dir.exists()

    def test_setup_matplotlib_called(self, tmp_path: Path):
        m = _import_module()
        out_dir = tmp_path / "outputs"
        expected_paths = self._make_path_mocks(out_dir)

        plt_mock = MagicMock()
        np_mock = MagicMock()

        with (
            patch.object(m, "_setup_matplotlib", return_value=plt_mock) as mock_setup,
            patch("concilium.application.benchmarks.charts.chart_generator.np", np_mock, create=True),
            patch.object(m, "_load_cenarios", return_value=[]),
            patch.object(m, "_chart_gantt", return_value=expected_paths[0]),
            patch.object(m, "_chart_plan_space", return_value=expected_paths[1]),
            patch.object(m, "_chart_waterfall", return_value=expected_paths[2]),
            patch.object(m, "_chart_eap_crit", return_value=expected_paths[3]),
            patch.object(m, "_chart_indiretos", return_value=expected_paths[4]),
            patch.object(m, "_chart_times", return_value=expected_paths[5]),
        ):
            m.gerar_graficos_benchmark(tmp_path, "AGIS")
            mock_setup.assert_called_once()

    def test_chart_gantt_called_with_slug(self, tmp_path: Path):
        m = _import_module()
        out_dir = tmp_path / "outputs"
        expected_paths = self._make_path_mocks(out_dir)

        plt_mock = MagicMock()
        np_mock = MagicMock()

        with (
            patch.object(m, "_setup_matplotlib", return_value=plt_mock),
            patch("concilium.application.benchmarks.charts.chart_generator.np", np_mock, create=True),
            patch.object(m, "_load_cenarios", return_value=[]),
            patch.object(m, "_chart_gantt", return_value=expected_paths[0]) as mock_gantt,
            patch.object(m, "_chart_plan_space", return_value=expected_paths[1]),
            patch.object(m, "_chart_waterfall", return_value=expected_paths[2]),
            patch.object(m, "_chart_eap_crit", return_value=expected_paths[3]),
            patch.object(m, "_chart_indiretos", return_value=expected_paths[4]),
            patch.object(m, "_chart_times", return_value=expected_paths[5]),
        ):
            m.gerar_graficos_benchmark(tmp_path, "MYSLUG")
            # gantt called with (plt, out_dir, slug, np)
            call_args = mock_gantt.call_args[0]
            assert call_args[2] == "MYSLUG"

    def test_load_cenarios_called_with_inter_dir(self, tmp_path: Path):
        m = _import_module()
        out_dir = tmp_path / "outputs"
        expected_paths = self._make_path_mocks(out_dir)

        plt_mock = MagicMock()
        np_mock = MagicMock()
        expected_inter_dir = tmp_path / "artifacts" / "intermediate"

        with (
            patch.object(m, "_setup_matplotlib", return_value=plt_mock),
            patch("concilium.application.benchmarks.charts.chart_generator.np", np_mock, create=True),
            patch.object(m, "_load_cenarios", return_value=[]) as mock_load,
            patch.object(m, "_chart_gantt", return_value=expected_paths[0]),
            patch.object(m, "_chart_plan_space", return_value=expected_paths[1]),
            patch.object(m, "_chart_waterfall", return_value=expected_paths[2]),
            patch.object(m, "_chart_eap_crit", return_value=expected_paths[3]),
            patch.object(m, "_chart_indiretos", return_value=expected_paths[4]),
            patch.object(m, "_chart_times", return_value=expected_paths[5]),
        ):
            m.gerar_graficos_benchmark(tmp_path, "AGIS")
            mock_load.assert_called_once_with(expected_inter_dir)

    def test_all_six_chart_helpers_called(self, tmp_path: Path):
        m = _import_module()
        out_dir = tmp_path / "outputs"
        expected_paths = self._make_path_mocks(out_dir)

        plt_mock = MagicMock()
        np_mock = MagicMock()
        cenarios = [{"slug": "A0_BASE_AUTO"}]

        with (
            patch.object(m, "_setup_matplotlib", return_value=plt_mock),
            patch("concilium.application.benchmarks.charts.chart_generator.np", np_mock, create=True),
            patch.object(m, "_load_cenarios", return_value=cenarios),
            patch.object(m, "_chart_gantt", return_value=expected_paths[0]) as g,
            patch.object(m, "_chart_plan_space", return_value=expected_paths[1]) as ps,
            patch.object(m, "_chart_waterfall", return_value=expected_paths[2]) as wf,
            patch.object(m, "_chart_eap_crit", return_value=expected_paths[3]) as ec,
            patch.object(m, "_chart_indiretos", return_value=expected_paths[4]) as ind,
            patch.object(m, "_chart_times", return_value=expected_paths[5]) as tm,
        ):
            m.gerar_graficos_benchmark(tmp_path, "AGIS")
            g.assert_called_once()
            ps.assert_called_once()
            wf.assert_called_once()
            ec.assert_called_once()
            ind.assert_called_once()
            tm.assert_called_once()

    def test_returns_list_of_paths(self, tmp_path: Path):
        m = _import_module()
        out_dir = tmp_path / "outputs"
        expected_paths = self._make_path_mocks(out_dir)

        plt_mock = MagicMock()
        np_mock = MagicMock()

        with (
            patch.object(m, "_setup_matplotlib", return_value=plt_mock),
            patch("concilium.application.benchmarks.charts.chart_generator.np", np_mock, create=True),
            patch.object(m, "_load_cenarios", return_value=[]),
            patch.object(m, "_chart_gantt", return_value=expected_paths[0]),
            patch.object(m, "_chart_plan_space", return_value=expected_paths[1]),
            patch.object(m, "_chart_waterfall", return_value=expected_paths[2]),
            patch.object(m, "_chart_eap_crit", return_value=expected_paths[3]),
            patch.object(m, "_chart_indiretos", return_value=expected_paths[4]),
            patch.object(m, "_chart_times", return_value=expected_paths[5]),
        ):
            result = m.gerar_graficos_benchmark(tmp_path, "AGIS")
            assert isinstance(result, list)
            assert all(isinstance(p, Path) for p in result)
