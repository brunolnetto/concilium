"""Tests for CLI commands_skills and BenchmarkFacade."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from concilium.presentation.cli.commands_skills import app as skills_app


class TestSkillsExportCommand:
    # Single-command Typer app: "export" is the default — invoke without it.
    def _run(self, *args):
        return CliRunner().invoke(skills_app, list(args))

    def test_export_mermaid_stdout(self):
        with patch(
            "concilium.application.skills.graph_exporter.SkillGraphExporter.to_mermaid",
            return_value="graph LR\n  A --> B",
        ):
            result = self._run()
        assert result.exit_code == 0
        assert "graph LR" in result.output

    def test_export_json_stdout(self):
        with patch(
            "concilium.application.skills.graph_exporter.SkillGraphExporter.to_json",
            return_value={"nodes": [], "edges": []},
        ):
            result = self._run("--format", "json")
        assert result.exit_code == 0
        assert "nodes" in result.output

    def test_export_dot_stdout(self):
        with patch(
            "concilium.application.skills.graph_exporter.SkillGraphExporter.to_dot",
            return_value="digraph G {}",
        ):
            result = self._run("--format", "dot")
        assert result.exit_code == 0

    def test_export_to_file(self, tmp_path):
        out_file = tmp_path / "out.md"
        with patch(
            "concilium.application.skills.graph_exporter.SkillGraphExporter.to_mermaid",
            return_value="graph LR",
        ):
            result = self._run("--output", str(out_file))
        assert result.exit_code == 0
        assert out_file.exists()
        assert "graph LR" in out_file.read_text()

    def test_export_group_by_phase(self):
        with patch(
            "concilium.application.skills.graph_exporter.SkillGraphExporter.to_mermaid",
            return_value="graph LR",
        ) as m:
            result = self._run("--group-by-phase")
        assert result.exit_code == 0
        m.assert_called_once_with(group_by_phase=True, show_validations=False)

    def test_export_show_validations(self):
        with patch(
            "concilium.application.skills.graph_exporter.SkillGraphExporter.to_mermaid",
            return_value="graph LR",
        ) as m:
            result = self._run("--show-validations")
        assert result.exit_code == 0
        m.assert_called_once_with(group_by_phase=False, show_validations=True)


class TestBenchmarkFacade:
    def test_from_root(self, tmp_path):
        from concilium.application.benchmarks.execution.facade import BenchmarkFacade
        facade = BenchmarkFacade.from_root(tmp_path)
        assert facade.config_root == tmp_path / "config"
        assert facade.benchmarks_root == tmp_path / "benchmarks" / "data"
        assert facade.projects_root == tmp_path / "benchmarks" / "projetos"

    def test_from_env(self, tmp_path):
        from concilium.application.benchmarks.execution.facade import BenchmarkFacade
        from unittest.mock import patch, MagicMock
        storage_mock = MagicMock()
        storage_mock.root = tmp_path
        storage_mock.config_root = tmp_path / "config"
        storage_mock.benchmark_projects_root = None
        with patch("concilium.application.benchmarks.execution.facade.get_storage", return_value=storage_mock):
            facade = BenchmarkFacade.from_env()
        assert facade.config_root == tmp_path / "config"
        assert facade.benchmarks_root == tmp_path / "benchmarks" / "data"

    def test_run_single_file_not_found(self, tmp_path):
        from concilium.application.benchmarks.execution.facade import BenchmarkFacade
        facade = BenchmarkFacade.from_root(tmp_path)
        with pytest.raises(FileNotFoundError, match="referencia.json"):
            facade.run_single("NONEXISTENT")

    def test_run_single_calls_runner(self, tmp_path):
        from concilium.application.benchmarks.execution.facade import BenchmarkFacade
        facade = BenchmarkFacade.from_root(tmp_path)
        slug = "BENCH-1"
        bench_dir = tmp_path / "benchmarks" / "data" / slug
        bench_dir.mkdir(parents=True)
        ref = {"nome": "Test", "slug": slug.lower(), "contexto_id": "ctx"}
        (bench_dir / "referencia.json").write_text(json.dumps(ref))

        runner_mock = MagicMock()
        runner_mock.run.return_value = {"status_final": "VIAVEL"}

        with patch.object(facade, "_make_runner", return_value=runner_mock):
            result = facade.run_single(slug, reset=False)

        assert result == {"status_final": "VIAVEL"}

    def test_run_all_delegates_to_batch(self, tmp_path):
        from concilium.application.benchmarks.execution.facade import BenchmarkFacade
        from concilium.application.benchmarks.execution.batch import BenchmarkBatchRunner
        facade = BenchmarkFacade.from_root(tmp_path)

        with patch.object(BenchmarkBatchRunner, "run_all", return_value=[{"slug": "bench-1"}]) as mock_run:
            result = facade.run_all(reset=False)

        assert result == [{"slug": "bench-1"}]

    def test_build_summary_delegates_to_batch(self, tmp_path):
        from concilium.application.benchmarks.execution.facade import BenchmarkFacade
        from concilium.application.benchmarks.execution.batch import BenchmarkBatchRunner
        facade = BenchmarkFacade.from_root(tmp_path)
        reports = [{"status_final": "VIAVEL"}]

        with patch.object(BenchmarkBatchRunner, "build_summary", return_value=[{"slug": "s"}]) as m:
            result = facade.build_summary(reports)

        assert result == [{"slug": "s"}]

    def test_make_runner_returns_benchmark_runner(self, tmp_path):
        from concilium.application.benchmarks.execution.facade import BenchmarkFacade
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner
        facade = BenchmarkFacade.from_root(tmp_path)
        runner = facade._make_runner()
        assert isinstance(runner, BenchmarkRunner)
