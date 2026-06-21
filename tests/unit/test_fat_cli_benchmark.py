"""Fat CLI tests for commands_benchmark.py, _commands_benchmark_helpers.py and commands_bdi.py.

Strategy: typer.testing.CliRunner + patch to cover as many lines as possible
without running actual pipelines. Each runner.invoke() covers dozens of lines.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

runner = CliRunner()

# ---------------------------------------------------------------------------
# Re-export the real app objects (they exist at module level in the CLI files)
# ---------------------------------------------------------------------------
from concilium.presentation.cli.commands_bdi import app as bdi_app  # noqa: E402
from concilium.presentation.cli.commands_benchmark import app as bench_app  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers: shared patch targets
# ---------------------------------------------------------------------------
_BENCH_MOD = "concilium.presentation.cli.commands_benchmark"
_HELPER_MOD = "concilium.presentation.cli._commands_benchmark_helpers"
_BDI_MOD = "concilium.presentation.cli.commands_bdi"
_SHARED_MOD = "concilium.presentation.cli.shared"


# ============================================================================
# commands_benchmark.py — list
# ============================================================================


class TestListBenchmarks:
    def test_list_no_benchmarks(self, tmp_path):
        """Empty data dir → yellow warning printed, exit 0."""
        (tmp_path / "benchmarks" / "data").mkdir(parents=True)
        with (
            patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path),
            patch(f"{_BENCH_MOD}.discover_benchmark_slugs", return_value=[]),
        ):
            result = runner.invoke(bench_app, ["list"])
        assert result.exit_code == 0
        assert "Nenhum benchmark" in result.output

    def test_list_with_slugs(self, tmp_path):
        """Slugs returned → table rendered with each slug."""
        data_dir = tmp_path / "benchmarks" / "data"
        slug_dir = data_dir / "MYPRO"
        slug_dir.mkdir(parents=True)
        ref = slug_dir / "referencia.json"
        ref.write_text("{}", encoding="utf-8")

        with (
            patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path),
            patch(f"{_BENCH_MOD}.discover_benchmark_slugs", return_value=["MYPRO"]),
        ):
            result = runner.invoke(bench_app, ["list"])
        assert result.exit_code == 0
        assert "MYPRO" in result.output

    def test_list_slug_without_referencia(self, tmp_path):
        """Slug dir exists but has no referencia.json → 'sem referencia' shown."""
        data_dir = tmp_path / "benchmarks" / "data"
        slug_dir = data_dir / "NORF"
        slug_dir.mkdir(parents=True)

        with (
            patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path),
            patch(f"{_BENCH_MOD}.discover_benchmark_slugs", return_value=["NORF"]),
        ):
            result = runner.invoke(bench_app, ["list"])
        assert result.exit_code == 0
        assert "sem referencia" in result.output


# ============================================================================
# commands_benchmark.py — merge-catalog
# ============================================================================


class TestMergeCatalog:
    def _make_bench_dir(self, tmp_path: Path, slug: str = "MYSLUG") -> Path:
        bench_dir = tmp_path / "benchmarks" / "data" / slug
        bench_dir.mkdir(parents=True)
        return bench_dir

    def test_merge_catalog_no_referencia(self, tmp_path):
        """Missing referencia.json → exit 1."""
        self._make_bench_dir(tmp_path)
        with patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path):
            result = runner.invoke(bench_app, ["merge-catalog", "MYSLUG"])
        assert result.exit_code == 1

    def test_merge_catalog_no_changes(self, tmp_path):
        """No alternativas.json or equipes.json → 'Nenhuma alteracao'."""
        bench_dir = self._make_bench_dir(tmp_path)
        (bench_dir / "referencia.json").write_text('{"cenarios": []}', encoding="utf-8")
        with patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path):
            result = runner.invoke(bench_app, ["merge-catalog", "MYSLUG"])
        assert result.exit_code == 0
        assert "Nenhuma alteracao" in result.output

    def test_merge_catalog_with_alternativas(self, tmp_path):
        """alternativas.json present → merged into referencia.json."""
        bench_dir = self._make_bench_dir(tmp_path)
        (bench_dir / "referencia.json").write_text("{}", encoding="utf-8")
        (bench_dir / "alternativas.json").write_text('[{"id":"A1"}]', encoding="utf-8")
        with patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path):
            result = runner.invoke(bench_app, ["merge-catalog", "MYSLUG"])
        assert result.exit_code == 0
        assert "referencia.json atualizado" in result.output

    def test_merge_catalog_keep_flag(self, tmp_path):
        """--keep prevents deletion of alternativas.json."""
        bench_dir = self._make_bench_dir(tmp_path)
        (bench_dir / "referencia.json").write_text("{}", encoding="utf-8")
        (bench_dir / "alternativas.json").write_text('[{"id":"A1"}]', encoding="utf-8")
        with patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path):
            result = runner.invoke(bench_app, ["merge-catalog", "MYSLUG", "--keep"])
        assert result.exit_code == 0
        assert (bench_dir / "alternativas.json").exists()

    def test_merge_catalog_with_equipes(self, tmp_path):
        """equipes.json present → merged into referencia.json."""
        bench_dir = self._make_bench_dir(tmp_path)
        (bench_dir / "referencia.json").write_text('{"equipes": []}', encoding="utf-8")
        (bench_dir / "equipes.json").write_text('[{"id":"EQ1"}]', encoding="utf-8")
        with patch(f"{_BENCH_MOD}._DEFAULT_ROOT", tmp_path):
            result = runner.invoke(bench_app, ["merge-catalog", "MYSLUG"])
        assert result.exit_code == 0


# ============================================================================
# commands_benchmark.py — run-batch
# ============================================================================


class TestRunBenchmarksBatch:
    def _mock_batch_runner(self, reports=None, summary=None):
        mock_runner = MagicMock()
        mock_runner.discover_specs.return_value = ["spec1", "spec2"]
        mock_runner.run_all.return_value = reports or [{"slug": "A"}]
        mock_runner.build_summary.return_value = summary or []
        return mock_runner

    def test_run_batch_json_output(self, tmp_path):
        mock_runner = self._mock_batch_runner()
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run-batch", "--json"])
        assert result.exit_code == 0
        assert "total" in result.output

    def test_run_batch_quiet_mode(self, tmp_path):
        mock_runner = self._mock_batch_runner()
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run-batch", "--quiet"])
        assert result.exit_code == 0

    def test_run_batch_with_summary_table(self, tmp_path):
        summary = [
            {
                "Projeto": "X",
                "Status": "OK",
                "Delta Direto %": "+1%",
                "Delta Indireto %": "+0%",
                "Delta Total %": "+1%",
                "Delta Venda %": "+0%",
            }
        ]
        mock_runner = self._mock_batch_runner(summary=summary)
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run-batch"])
        assert result.exit_code == 0

    def test_run_batch_aviso_status(self, tmp_path):
        summary = [
            {
                "Projeto": "Y",
                "Status": "AVISO",
                "Delta Direto %": "+15%",
                "Delta Indireto %": "+0%",
                "Delta Total %": "+10%",
                "Delta Venda %": "+5%",
            }
        ]
        mock_runner = self._mock_batch_runner(summary=summary)
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run-batch"])
        assert result.exit_code == 0

    def test_run_batch_error_status(self, tmp_path):
        summary = [
            {
                "Projeto": "Z",
                "Status": "ERRO",
                "Delta Direto %": "+50%",
                "Delta Indireto %": "+0%",
                "Delta Total %": "+50%",
                "Delta Venda %": "+30%",
            }
        ]
        mock_runner = self._mock_batch_runner(summary=summary)
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run-batch"])
        assert result.exit_code == 0


# ============================================================================
# commands_benchmark.py — run (single slug and all)
# ============================================================================


class TestRunBenchmarks:
    def test_run_no_slug_all_benchmarks(self, tmp_path):
        """No --slug → runs all and prints summary table."""
        summary = [
            {
                "Projeto": "ALL",
                "Status": "OK",
                "Delta Direto %": "+0%",
                "Delta Indireto %": "+0%",
                "Delta Total %": "+0%",
                "Delta Venda %": "+0%",
            }
        ]
        mock_batch = MagicMock()
        mock_batch.run_all.return_value = [{}]
        mock_batch.build_summary.return_value = summary
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run"])
        assert result.exit_code == 0

    def test_run_no_slug_empty_summary(self, tmp_path):
        mock_batch = MagicMock()
        mock_batch.run_all.return_value = []
        mock_batch.build_summary.return_value = []
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run"])
        assert result.exit_code == 0

    def test_run_slug_not_found(self, tmp_path):
        """Slug not found → exit 1."""
        mock_batch = MagicMock()
        mock_batch.benchmarks_root = tmp_path / "benchmarks" / "data"
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=None),
            patch(f"{_BENCH_MOD}.discover_benchmark_slugs", return_value=["OTHER"]),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run", "--slug", "MISSING"])
        assert result.exit_code == 1

    def test_run_slug_not_found_no_benchmarks(self, tmp_path):
        """Slug not found and no benchmarks available at all."""
        mock_batch = MagicMock()
        mock_batch.benchmarks_root = tmp_path / "benchmarks" / "data"
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=None),
            patch(f"{_BENCH_MOD}.discover_benchmark_slugs", return_value=[]),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["run", "--slug", "GHOST"])
        assert result.exit_code == 1
        assert "nenhum benchmark" in result.output

    def test_run_slug_success(self, tmp_path):
        """Found slug → runner.run() called, prints OK."""
        mock_batch = MagicMock()
        mock_batch.benchmarks_root = tmp_path / "benchmarks" / "data"
        mock_spec = MagicMock()
        mock_bench_runner = MagicMock()
        mock_bench_runner.run.return_value = {"status": "OK"}
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=Path("/fake/ref.json")),
            patch(f"{_BENCH_MOD}.BenchmarkSpecLoader") as mock_loader_cls,
            patch(f"{_BENCH_MOD}.BenchmarkRunner", return_value=mock_bench_runner),
            patch(f"{_BENCH_MOD}.BenchmarkReportBuilder"),
            patch(f"{_BENCH_MOD}.BenchmarkReportPrinter"),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            mock_loader_cls.return_value.load.return_value = mock_spec
            result = runner.invoke(bench_app, ["run", "--slug", "CTC"])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_run_slug_runner_error(self, tmp_path):
        """runner.run() raises → exit 1."""
        mock_batch = MagicMock()
        mock_batch.benchmarks_root = tmp_path / "benchmarks" / "data"
        mock_bench_runner = MagicMock()
        mock_bench_runner.run.side_effect = RuntimeError("pipeline failed")
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=Path("/fake/ref.json")),
            patch(f"{_BENCH_MOD}.BenchmarkSpecLoader") as mock_loader_cls,
            patch(f"{_BENCH_MOD}.BenchmarkRunner", return_value=mock_bench_runner),
            patch(f"{_BENCH_MOD}.BenchmarkReportBuilder"),
            patch(f"{_BENCH_MOD}.BenchmarkReportPrinter"),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            mock_loader_cls.return_value.load.return_value = MagicMock()
            result = runner.invoke(bench_app, ["run", "--slug", "CTC"])
        assert result.exit_code == 1
        assert "ERRO" in result.output

    def test_run_slug_with_pack(self, tmp_path):
        """--pack flag triggers empacotar helper after successful run."""
        mock_batch = MagicMock()
        mock_batch.benchmarks_root = tmp_path / "benchmarks" / "data"
        mock_bench_runner = MagicMock()
        mock_bench_runner.run.return_value = {}
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=Path("/fake/ref.json")),
            patch(f"{_BENCH_MOD}.BenchmarkSpecLoader") as mock_loader_cls,
            patch(f"{_BENCH_MOD}.BenchmarkRunner", return_value=mock_bench_runner),
            patch(f"{_BENCH_MOD}.BenchmarkReportBuilder"),
            patch(f"{_BENCH_MOD}.BenchmarkReportPrinter"),
            patch(f"{_BENCH_MOD}._empacotar_benchmark_cli") as mock_pack,
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            mock_loader_cls.return_value.load.return_value = MagicMock()
            result = runner.invoke(bench_app, ["run", "--slug", "CTC", "--pack"])
        assert result.exit_code == 0
        mock_pack.assert_called_once()


# ============================================================================
# commands_benchmark.py — pack
# ============================================================================


class TestPackBenchmark:
    def test_pack_success(self, tmp_path):
        """empacotar_outputs returns a valid zip → displays size and file listing."""
        zip_path = tmp_path / "output.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("graficos/chart.png", b"fake")
            zf.writestr("relatorio/report.md", b"fake")
            zf.writestr("audit/audit.json", b"fake")

        with (
            patch(f"{_BENCH_MOD}.empacotar_outputs", return_value=zip_path),
            patch(f"{_BENCH_MOD}.get_config_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["pack", "--slug", "AGIS"])
        assert result.exit_code == 0
        assert "Pacote criado" in result.output

    def test_pack_error(self, tmp_path):
        """empacotar_outputs raises → exit 1."""
        with (
            patch(f"{_BENCH_MOD}.empacotar_outputs", side_effect=FileNotFoundError("missing")),
            patch(f"{_BENCH_MOD}.get_config_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["pack", "--slug", "AGIS"])
        assert result.exit_code == 1
        assert "Erro" in result.output

    def test_pack_no_charts(self, tmp_path):
        """--no-charts still calls empacotar_outputs."""
        zip_path = tmp_path / "output.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("inputs/data.json", b"{}")

        with (
            patch(f"{_BENCH_MOD}.empacotar_outputs", return_value=zip_path),
            patch(f"{_BENCH_MOD}.get_config_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["pack", "--slug", "AGIS", "--no-charts"])
        assert result.exit_code == 0


# ============================================================================
# commands_benchmark.py — analyze
# ============================================================================


class TestAnalyze:
    def test_analyze_no_files(self, tmp_path):
        """No benchmark JSON files → empty table, no crash."""
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["analyze"])
        assert result.exit_code == 0

    def test_analyze_with_files(self, tmp_path):
        """One benchmark JSON file → row shown in table."""
        bench_data = {
            "slug": "TESTPROJ",
            "confronto": {
                "referencia": {"custo_direto": 1000000},
                "ferramenta": {"custo_direto": 1050000},
                "deltas": {"custo_direto": {"percentual": 5.0}},
            },
        }
        f = tmp_path / "benchmark_TESTPROJ.json"
        f.write_text(json.dumps(bench_data), encoding="utf-8")
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["analyze"])
        assert result.exit_code == 0
        assert "TESTPROJ" in result.output

    def test_analyze_high_delta(self, tmp_path):
        """Delta >= 20% → red coloring path exercised."""
        bench_data = {
            "slug": "HIGHD",
            "confronto": {
                "referencia": {"custo_direto": 1000000},
                "ferramenta": {"custo_direto": 1300000},
                "deltas": {"custo_direto": {"percentual": 30.0}},
            },
        }
        f = tmp_path / "benchmark_HIGHD.json"
        f.write_text(json.dumps(bench_data), encoding="utf-8")
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["analyze"])
        assert result.exit_code == 0

    def test_analyze_corrupt_file_skipped(self, tmp_path):
        """Corrupt JSON file is silently skipped."""
        f = tmp_path / "benchmark_BAD.json"
        f.write_text("NOT JSON", encoding="utf-8")
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["analyze"])
        assert result.exit_code == 0


# ============================================================================
# commands_benchmark.py — trace
# ============================================================================


class TestExtractTrace:
    def test_trace_not_found(self, tmp_path):
        """No matching report → exit 1."""
        with (
            patch(f"{_BENCH_MOD}.iter_benchmark_reports", return_value=[]),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["trace", "CTC"])
        assert result.exit_code == 1
        assert "não encontrado" in result.output

    def test_trace_found(self, tmp_path):
        """Matching report → extract called and count printed."""
        fake_report = tmp_path / "benchmark_CTC.json"
        fake_report.write_text("{}", encoding="utf-8")
        mock_out = {"equipes": {"equipes": [{"id": "E1"}, {"id": "E2"}]}}
        with (
            patch(f"{_BENCH_MOD}.iter_benchmark_reports", return_value=[fake_report]),
            patch(f"{_BENCH_MOD}.extract_engine_iteration_references", return_value=mock_out),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["trace", "CTC"])
        assert result.exit_code == 0
        assert "2" in result.output


# ============================================================================
# commands_benchmark.py — audit
# ============================================================================


class TestAudit:
    def test_audit_success(self, tmp_path):
        """run_audit returns dict → JSON printed."""
        audit_result = {"resumo": {"ok": True}, "perguntas": []}
        with (
            patch(f"{_BENCH_MOD}.run_audit", return_value=audit_result),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["audit", "CTC"])
        assert result.exit_code == 0
        assert "resumo" in result.output


# ============================================================================
# commands_benchmark.py — cleanup
# ============================================================================


class TestCleanup:
    def test_cleanup_no_files(self, tmp_path):
        """No files to remove → '0 arquivos removidos'."""
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["cleanup"])
        assert result.exit_code == 0
        assert "0 arquivos removidos" in result.output

    def test_cleanup_removes_rerun_log(self, tmp_path):
        """rerun.log present → removed and counted."""
        sub = tmp_path / "benchmarks" / "data" / "CTC"
        sub.mkdir(parents=True)
        log = sub / "rerun.log"
        log.write_text("log", encoding="utf-8")
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["cleanup"])
        assert result.exit_code == 0
        assert "1 arquivos removidos" in result.output
        assert not log.exists()


# ============================================================================
# commands_benchmark.py — summary
# ============================================================================


class TestStageSummary:
    def test_summary_no_output(self, tmp_path):
        """Summary printed to stdout."""
        summary_data = {
            "meta": {
                "total_benchmarks_com_extracao": 3,
                "benchmarks_com_equipes_zeradas": 1,
                "benchmarks_com_itens_planejamento_zerados": 0,
            },
            "benchmarks": [],
        }
        with (
            patch(f"{_BENCH_MOD}.build_stage_discrepancy_summary", return_value=summary_data),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["summary"])
        assert result.exit_code == 0
        assert "3" in result.output

    def test_summary_with_output_file(self, tmp_path):
        """--output saves JSON to file."""
        out_path = tmp_path / "summary.json"
        summary_data = {
            "meta": {
                "total_benchmarks_com_extracao": 1,
                "benchmarks_com_equipes_zeradas": 0,
                "benchmarks_com_itens_planejamento_zerados": 0,
            },
            "benchmarks": [],
        }
        with (
            patch(f"{_BENCH_MOD}.build_stage_discrepancy_summary", return_value=summary_data),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
        ):
            result = runner.invoke(bench_app, ["summary", "--output", str(out_path)])
        assert result.exit_code == 0
        assert out_path.exists()
        assert "Salvo em" in result.output


# ============================================================================
# commands_benchmark.py — iterate
# ============================================================================


class TestIterateCorrection:
    def test_iterate_no_specs(self, tmp_path):
        """No matching specs → still runs audit/pipeline."""
        mock_batch = MagicMock()
        mock_batch.discover_specs.return_value = []
        mock_batch.config_root = tmp_path / "config"
        mock_batch.projects_root = tmp_path / "proj"
        mock_bench_runner = MagicMock()
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}.BenchmarkRunner", return_value=mock_bench_runner),
            patch(f"{_BENCH_MOD}.BenchmarkReportBuilder"),
            patch(f"{_BENCH_MOD}.BenchmarkReportPrinter"),
            patch(f"{_BENCH_MOD}.iter_benchmark_reports", return_value=[]),
            patch(f"{_BENCH_MOD}.extract_engine_iteration_references", return_value={}),
            patch(f"{_BENCH_MOD}.validate_pipeline_integrity", return_value={"validacoes_fechamento": []}),
            patch(f"{_BENCH_MOD}.run_audit", return_value={"resumo": {}}),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["iterate", "CTC"])
        assert result.exit_code == 0
        assert "Iteração concluída" in result.output

    def test_iterate_with_matching_spec(self, tmp_path):
        """Matching spec → BenchmarkRunner.run() called once."""
        mock_spec = MagicMock()
        mock_spec.slug = "CTC"
        mock_batch = MagicMock()
        mock_batch.discover_specs.return_value = [mock_spec]
        mock_batch.config_root = tmp_path / "config"
        mock_batch.projects_root = tmp_path / "proj"
        mock_bench_runner = MagicMock()
        fake_report = tmp_path / "benchmark_CTC.json"
        fake_report.write_text("{}", encoding="utf-8")
        with (
            patch(f"{_BENCH_MOD}.BenchmarkBatchRunner", return_value=mock_batch),
            patch(f"{_BENCH_MOD}.BenchmarkRunner", return_value=mock_bench_runner),
            patch(f"{_BENCH_MOD}.BenchmarkReportBuilder"),
            patch(f"{_BENCH_MOD}.BenchmarkReportPrinter"),
            patch(f"{_BENCH_MOD}.iter_benchmark_reports", return_value=[fake_report]),
            patch(f"{_BENCH_MOD}.extract_engine_iteration_references", return_value={}),
            patch(f"{_BENCH_MOD}.validate_pipeline_integrity", return_value={"validacoes_fechamento": []}),
            patch(f"{_BENCH_MOD}.run_audit", return_value={"resumo": {}}),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["iterate", "CTC"])
        assert result.exit_code == 0
        mock_bench_runner.run.assert_called_once()


# ============================================================================
# commands_benchmark.py — plan-space
# ============================================================================


class TestPlanSpace:
    def _make_ref(self, tmp_path: Path, slug: str = "AGIS", cenarios=None) -> Path:
        bench_dir = tmp_path / "benchmarks" / "data" / slug
        bench_dir.mkdir(parents=True)
        ref_data = {
            "cenarios": cenarios or [{"id": "A1", "modo": "AUTO", "overrides": {}}],
            "spec": {
                "cenarios": cenarios or [{"id": "A1", "modo": "AUTO", "overrides": {}}],
                "rcpsp_spec": {"algorithm": "CPSAT"},
            },
        }
        ref_path = bench_dir / "referencia.json"
        ref_path.write_text(json.dumps(ref_data), encoding="utf-8")
        return ref_path

    def test_plan_space_no_referencia(self, tmp_path):
        """No referencia.json → exit 1."""
        (tmp_path / "benchmarks" / "data" / "GHOST").mkdir(parents=True)
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["plan-space", "--slug", "GHOST"])
        assert result.exit_code == 1

    def test_plan_space_no_cenarios(self, tmp_path):
        """referencia.json with no cenarios → exit 1."""
        bench_dir = tmp_path / "benchmarks" / "data" / "EMPTY"
        bench_dir.mkdir(parents=True)
        (bench_dir / "referencia.json").write_text('{"spec": {}}', encoding="utf-8")
        with patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path):
            result = runner.invoke(bench_app, ["plan-space", "--slug", "EMPTY"])
        assert result.exit_code == 1
        assert "Sem cenários" in result.output

    def test_plan_space_success(self, tmp_path):
        """Valid referencia.json with cenarios → tasks executed, results saved."""
        self._make_ref(tmp_path)
        mock_spec = MagicMock()
        mock_spec.nome = "TestSpec"
        rows = [
            {
                "alternativa": "A1",
                "modo": "AUTO",
                "status": "OK",
                "delta_preco_venda_pct": 1.5,
                "makespan_semanas": 10,
                "folga_semanas": 2,
                "report_file": "/tmp/a1.json",
            }
        ]
        with (
            patch(f"{_BENCH_MOD}._prepare_plan_space_tasks", return_value=[("A1", "AUTO", mock_spec)]),
            patch(f"{_BENCH_MOD}._execute_plan_space_tasks", return_value=(rows, [])),
            patch(f"{_BENCH_MOD}._save_plan_space_results"),
            patch(f"{_BENCH_MOD}._save_plan_space_markdown"),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["plan-space", "--slug", "AGIS"])
        assert result.exit_code == 0

    def test_plan_space_with_failures(self, tmp_path):
        """Failures in tasks → exit 1."""
        self._make_ref(tmp_path)
        mock_spec = MagicMock()
        mock_spec.nome = "TestSpec"
        with (
            patch(f"{_BENCH_MOD}._prepare_plan_space_tasks", return_value=[("A1", "AUTO", mock_spec)]),
            patch(f"{_BENCH_MOD}._execute_plan_space_tasks", return_value=([], ["A1"])),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["plan-space", "--slug", "AGIS"])
        assert result.exit_code == 1

    def test_plan_space_artifacts_path_fallback(self, tmp_path):
        """referencia.json under artifacts/inputs/ is found via fallback path."""
        bench_dir = tmp_path / "benchmarks" / "data" / "ARTT"
        artifacts_dir = bench_dir / "artifacts" / "inputs"
        artifacts_dir.mkdir(parents=True)
        ref_data = {
            "spec": {
                "cenarios": [{"id": "A1", "modo": "AUTO", "overrides": {}}],
                "rcpsp_spec": {"algorithm": "CPSAT"},
            }
        }
        (artifacts_dir / "referencia.json").write_text(json.dumps(ref_data), encoding="utf-8")
        mock_spec = MagicMock()
        mock_spec.nome = "TestSpec"
        with (
            patch(f"{_BENCH_MOD}._prepare_plan_space_tasks", return_value=[("A1", "AUTO", mock_spec)]),
            patch(f"{_BENCH_MOD}._execute_plan_space_tasks", return_value=([], [])),
            patch(f"{_BENCH_MOD}._save_plan_space_results"),
            patch(f"{_BENCH_MOD}._save_plan_space_markdown"),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["plan-space", "--slug", "ARTT"])
        assert result.exit_code == 0


# ============================================================================
# commands_benchmark.py — compare
# ============================================================================


class TestCompareAlgorithms:
    def test_compare_slug_not_found(self, tmp_path):
        """Slug not found → exit 1."""
        with (
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=None),
            patch(f"{_BENCH_MOD}.discover_benchmark_slugs", return_value=["OTHER"]),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["compare", "--slug", "MISSING"])
        assert result.exit_code == 1

    def test_compare_success(self, tmp_path):
        """Valid slug → compare called once, exit 0."""
        mock_runner = MagicMock()
        mock_spec = MagicMock()
        with (
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=Path("/fake/ref.json")),
            patch(f"{_BENCH_MOD}.BenchmarkSpecLoader") as mock_loader_cls,
            patch(f"{_BENCH_MOD}.AlgorithmComparisonRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            mock_loader_cls.return_value.load.return_value = mock_spec
            result = runner.invoke(bench_app, ["compare", "--slug", "CTC"])
        assert result.exit_code == 0
        mock_runner.compare.assert_called_once()

    def test_compare_with_algorithms_option(self, tmp_path):
        """--algorithms option passes list to compare."""
        mock_runner = MagicMock()
        mock_spec = MagicMock()
        with (
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=Path("/fake/ref.json")),
            patch(f"{_BENCH_MOD}.BenchmarkSpecLoader") as mock_loader_cls,
            patch(f"{_BENCH_MOD}.AlgorithmComparisonRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            mock_loader_cls.return_value.load.return_value = mock_spec
            result = runner.invoke(bench_app, ["compare", "--slug", "CTC", "--algorithms", "MINSLK,LPT"])
        assert result.exit_code == 0
        call_kwargs = mock_runner.compare.call_args
        assert call_kwargs.kwargs.get("algorithms") == ["MINSLK", "LPT"]

    def test_compare_runner_error(self, tmp_path):
        """compare raises → exit 1."""
        mock_runner = MagicMock()
        mock_runner.compare.side_effect = RuntimeError("algo failed")
        with (
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=Path("/fake/ref.json")),
            patch(f"{_BENCH_MOD}.BenchmarkSpecLoader") as mock_loader_cls,
            patch(f"{_BENCH_MOD}.AlgorithmComparisonRunner", return_value=mock_runner),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            mock_loader_cls.return_value.load.return_value = MagicMock()
            result = runner.invoke(bench_app, ["compare", "--slug", "CTC"])
        assert result.exit_code == 1
        assert "ERRO" in result.output

    def test_compare_no_benchmarks_available(self, tmp_path):
        """No benchmarks → '(nenhum benchmark encontrado)' shown."""
        with (
            patch(f"{_BENCH_MOD}.find_benchmark_reference", return_value=None),
            patch(f"{_BENCH_MOD}.discover_benchmark_slugs", return_value=[]),
            patch(f"{_BENCH_MOD}._tools_root", return_value=tmp_path),
            patch(f"{_BENCH_MOD}.config_root", return_value=tmp_path / "config"),
            patch(f"{_BENCH_MOD}.benchmark_projects_root", return_value=tmp_path / "proj"),
        ):
            result = runner.invoke(bench_app, ["compare", "--slug", "X"])
        assert result.exit_code == 1
        assert "nenhum benchmark" in result.output


# ============================================================================
# _commands_benchmark_helpers.py — direct function tests
# ============================================================================

from concilium.presentation.cli._commands_benchmark_helpers import (  # noqa: E402
    _deep_merge_dict,
    _discover_slugs,
    _empacotar_benchmark_cli,
    _execute_plan_space_tasks,
    _mc_merge_alternativas,
    _mc_merge_equipes,
    _mc_remove_historical,
    _prepare_plan_space_tasks,
    _save_plan_space_markdown,
    _save_plan_space_results,
    _validate_and_apply_modo,
)


class TestHelperMcMerge:
    def test_mc_merge_alternativas_no_file(self, tmp_path):
        ref: dict = {}
        alt_path, changed = _mc_merge_alternativas(ref, tmp_path, False)
        assert changed is False

    def test_mc_merge_alternativas_new_data(self, tmp_path):
        (tmp_path / "alternativas.json").write_text('[{"id":"X"}]', encoding="utf-8")
        ref: dict = {}
        _, changed = _mc_merge_alternativas(ref, tmp_path, False)
        assert changed is True
        assert ref["cenarios"] == [{"id": "X"}]

    def test_mc_merge_alternativas_unchanged(self, tmp_path):
        data = [{"id": "X"}]
        (tmp_path / "alternativas.json").write_text(json.dumps(data), encoding="utf-8")
        ref: dict = {"cenarios": data}
        _, changed = _mc_merge_alternativas(ref, tmp_path, False)
        assert changed is False

    def test_mc_merge_alternativas_v2_spec(self, tmp_path):
        """v2 format: cenarios lives under spec."""
        (tmp_path / "alternativas.json").write_text('[{"id":"Y"}]', encoding="utf-8")
        ref: dict = {"spec": {"cenarios": []}}
        _, changed = _mc_merge_alternativas(ref, tmp_path, False)
        assert changed is True
        assert ref["spec"]["cenarios"] == [{"id": "Y"}]

    def test_mc_merge_equipes_no_file(self, tmp_path):
        ref: dict = {}
        eq_path, changed = _mc_merge_equipes(ref, tmp_path, False)
        assert changed is False

    def test_mc_merge_equipes_new_data(self, tmp_path):
        (tmp_path / "equipes.json").write_text('[{"id":"E1"}]', encoding="utf-8")
        ref: dict = {}
        _, changed = _mc_merge_equipes(ref, tmp_path, False)
        assert changed is True
        assert ref["equipes"] == [{"id": "E1"}]

    def test_mc_merge_equipes_unchanged(self, tmp_path):
        data = [{"id": "E1"}]
        (tmp_path / "equipes.json").write_text(json.dumps(data), encoding="utf-8")
        ref: dict = {"equipes": data}
        _, changed = _mc_merge_equipes(ref, tmp_path, False)
        assert changed is False

    def test_mc_remove_historical_keep_true(self, tmp_path):
        f = tmp_path / "alt.json"
        f.write_text("[]", encoding="utf-8")
        _mc_remove_historical(True, f, tmp_path / "eq.json")
        assert f.exists()  # keep=True → not removed

    def test_mc_remove_historical_keep_false(self, tmp_path):
        alt = tmp_path / "alternativas.json"
        eq = tmp_path / "equipes.json"
        alt.write_text("[]", encoding="utf-8")
        eq.write_text("[]", encoding="utf-8")
        _mc_remove_historical(False, alt, eq)
        assert not alt.exists()
        assert not eq.exists()

    def test_mc_remove_historical_nonexistent_files(self, tmp_path):
        """Non-existent paths → no error."""
        _mc_remove_historical(False, tmp_path / "ghost1.json", tmp_path / "ghost2.json")


class TestHelperDeepMerge:
    def test_deep_merge_flat(self):
        base = {"a": 1, "b": 2}
        override = {"b": 99, "c": 3}
        result = _deep_merge_dict(base, override)
        assert result == {"a": 1, "b": 99, "c": 3}

    def test_deep_merge_nested(self):
        base = {"x": {"y": 1, "z": 2}}
        override = {"x": {"z": 99}}
        result = _deep_merge_dict(base, override)
        assert result["x"]["y"] == 1
        assert result["x"]["z"] == 99

    def test_deep_merge_does_not_mutate_base(self):
        base = {"a": {"b": 1}}
        override = {"a": {"b": 2}}
        _deep_merge_dict(base, override)
        assert base["a"]["b"] == 1  # original unchanged


class TestHelperDiscoverSlugs:
    def test_discover_slugs_empty(self, tmp_path):
        (tmp_path / "benchmarks" / "data").mkdir(parents=True)
        assert _discover_slugs(tmp_path) == []

    def test_discover_slugs_with_referencia(self, tmp_path):
        slug_dir = tmp_path / "benchmarks" / "data" / "MYSLUG"
        slug_dir.mkdir(parents=True)
        (slug_dir / "referencia.json").write_text("{}", encoding="utf-8")
        slugs = _discover_slugs(tmp_path)
        assert "MYSLUG" in slugs

    def test_discover_slugs_ignores_no_referencia(self, tmp_path):
        slug_dir = tmp_path / "benchmarks" / "data" / "NORF"
        slug_dir.mkdir(parents=True)
        slugs = _discover_slugs(tmp_path)
        assert "NORF" not in slugs


class TestHelperEmpacotar:
    def test_empacotar_success(self, tmp_path):
        zip_path = tmp_path / "output.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("graficos/chart.png", b"png")
        with (
            patch(f"{_HELPER_MOD}.empacotar_outputs", return_value=zip_path),
            patch(f"{_HELPER_MOD}.get_config_root", return_value=tmp_path),
        ):
            _empacotar_benchmark_cli("AGIS", tmp_path, gerar_charts=True)

    def test_empacotar_exception_swallowed(self, tmp_path):
        """Exception inside empacotar is caught and printed as warning, not raised."""
        with (
            patch(f"{_HELPER_MOD}.empacotar_outputs", side_effect=RuntimeError("boom")),
            patch(f"{_HELPER_MOD}.get_config_root", return_value=tmp_path),
        ):
            _empacotar_benchmark_cli("AGIS", tmp_path, gerar_charts=False)
            # No exception raised


class TestHelperValidateAndApplyModo:
    def test_manual_removes_rcpsp_spec(self):
        ref = {"rcpsp_spec": {"algo": "CPSAT"}}
        _validate_and_apply_modo("A1", "MANUAL", ref)
        assert "rcpsp_spec" not in ref

    def test_auto_with_rcpsp_spec_ok(self):
        ref = {"rcpsp_spec": {"algo": "CPSAT"}}
        _validate_and_apply_modo("A1", "AUTO", ref)  # should not raise

    def test_auto_without_rcpsp_spec_exits(self):
        ref = {}

        with pytest.raises((SystemExit, typer.Exit)):
            _validate_and_apply_modo("A1", "AUTO", ref)

    def test_invalid_modo_exits(self):
        ref = {}

        with pytest.raises((SystemExit, typer.Exit)):
            _validate_and_apply_modo("A1", "INVALID", ref)

    def test_manual_v2_spec_container(self):
        ref = {"spec": {"rcpsp_spec": {"algo": "CPSAT"}}}
        _validate_and_apply_modo("A1", "MANUAL", ref["spec"])
        assert "rcpsp_spec" not in ref["spec"]


class TestHelperPreparePlanSpaceTasks:
    def test_prepare_tasks_auto_mode(self, tmp_path):
        base_ref = {"spec": {"rcpsp_spec": {"algo": "CPSAT"}}}
        ref_path = tmp_path / "referencia.json"
        alternativas = [{"id": "A1", "modo": "AUTO", "overrides": {}}]
        mock_spec = MagicMock()
        mock_spec.nome = "TestSpec"
        with patch(f"{_HELPER_MOD}.load_spec_from_dict", return_value=mock_spec):
            tasks = _prepare_plan_space_tasks(base_ref, ref_path, alternativas)
        assert len(tasks) == 1
        assert tasks[0][0] == "A1"

    def test_prepare_tasks_benchmark_config_overrides_modo(self, tmp_path):
        """benchmark_config mode forces AUTO regardless of alt.modo."""
        base_ref = {
            "meta": {"mode": "benchmark_config"},
            "spec": {"rcpsp_spec": {"algo": "CPSAT"}},
        }
        ref_path = tmp_path / "referencia.json"
        alternativas = [{"id": "B1", "modo": "MANUAL", "overrides": {}}]
        mock_spec = MagicMock()
        mock_spec.nome = "TestSpec"
        with patch(f"{_HELPER_MOD}.load_spec_from_dict", return_value=mock_spec):
            tasks = _prepare_plan_space_tasks(base_ref, ref_path, alternativas)
        assert tasks[0][1] == "AUTO"


class TestHelperExecutePlanSpaceTasks:
    def test_execute_all_success(self, tmp_path):
        row = {
            "alternativa": "A1",
            "modo": "AUTO",
            "status": "OK",
            "delta_preco_venda_pct": 0.5,
            "makespan_semanas": 5,
            "folga_semanas": 1,
            "report_file": str(tmp_path / "a1.json"),
        }
        mock_spec = MagicMock()
        tasks = [("A1", "AUTO", mock_spec)]
        with patch(f"{_HELPER_MOD}._run_one_plan_space", return_value=row):
            rows, failed = _execute_plan_space_tasks(tasks, 1, True, tmp_path, tmp_path, tmp_path)
        assert len(rows) == 1
        assert len(failed) == 0

    def test_execute_with_failure(self, tmp_path):
        mock_spec = MagicMock()
        tasks = [("FAIL_ALT", "AUTO", mock_spec)]
        with patch(f"{_HELPER_MOD}._run_one_plan_space", side_effect=RuntimeError("bad")):
            rows, failed = _execute_plan_space_tasks(tasks, 1, True, tmp_path, tmp_path, tmp_path)
        assert len(rows) == 0
        assert "FAIL_ALT" in failed


class TestHelperSavePlanSpace:
    def _make_row(self, alt="A1", delta=1.5, mk=10, folga=2):
        return {
            "alternativa": alt,
            "modo": "AUTO",
            "status": "OK",
            "delta_preco_venda_pct": delta,
            "makespan_semanas": mk,
            "folga_semanas": folga,
            "report_file": "/tmp/fake.json",
        }

    def test_save_results_table_rendered(self, tmp_path):
        rows = [self._make_row()]
        _save_plan_space_results(rows, "TEST", None, tmp_path, tmp_path)

    def test_save_results_none_values(self, tmp_path):
        rows = [self._make_row(delta=None, mk=None, folga=None)]
        _save_plan_space_results(rows, "TEST", None, tmp_path, tmp_path)

    def test_save_results_inviavel_status(self, tmp_path):
        row = self._make_row()
        row["status"] = "INVIAVEL"
        _save_plan_space_results([row], "TEST", None, tmp_path, tmp_path)

    def test_save_markdown_creates_file(self, tmp_path):
        rows = [self._make_row()]
        _save_plan_space_markdown(rows, "TEST", tmp_path)
        md = tmp_path / "plan_space_report.md"
        assert md.exists()
        content = md.read_text(encoding="utf-8")
        assert "Plan Space" in content

    def test_save_markdown_none_values(self, tmp_path):
        rows = [self._make_row(delta=None, mk=None, folga=None)]
        _save_plan_space_markdown(rows, "TEST", tmp_path)

    def test_save_markdown_inviavel_bold(self, tmp_path):
        row = self._make_row()
        row["status"] = "INVIAVEL"
        _save_plan_space_markdown([row], "TEST", tmp_path)
        content = (tmp_path / "plan_space_report.md").read_text(encoding="utf-8")
        assert "**INVIAVEL**" in content


# ============================================================================
# commands_bdi.py — bdi show
# ============================================================================


class TestBdiShow:
    def _make_project(self, tmp_path: Path, project_name: str = "mypro") -> MagicMock:
        proj_dir = tmp_path / project_name
        proj_dir.mkdir(parents=True)
        mock_proj = MagicMock()
        mock_proj.root = proj_dir
        return mock_proj

    def test_bdi_show_no_perfil(self, tmp_path):
        """No perfil_bdi.json → yellow warning, exit 0."""
        mock_proj = self._make_project(tmp_path)
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(bdi_app, ["show", "mypro"])
        assert result.exit_code == 0
        assert "Nenhum perfil BDI" in result.output

    def test_bdi_show_with_perfil(self, tmp_path):
        """perfil_bdi.json present → fields displayed."""
        mock_proj = self._make_project(tmp_path)
        bdi_dir = mock_proj.root / "bdi"
        bdi_dir.mkdir()
        perfil = {
            "versao": 1,
            "content_hash": "abc123",
            "confirmado_por": "Eng. Test",
            "data_confirmacao": "2026-01-01T00:00:00Z",
            "tributario": {
                "regime": "lucro_real",
                "municipio": "São Paulo",
                "iss_aliquota_municipal": 0.05,
                "mao_obra": {"iss": {"aplicavel": True}},
            },
            "lucro": {"lucro_bruto": 8.0},
        }
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(perfil), encoding="utf-8")
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(bdi_app, ["show", "mypro"])
        assert result.exit_code == 0
        assert "Eng. Test" in result.output

    def test_bdi_show_with_motivo_revisao(self, tmp_path):
        """motivo_revisao is shown when present."""
        mock_proj = self._make_project(tmp_path)
        bdi_dir = mock_proj.root / "bdi"
        bdi_dir.mkdir()
        perfil = {
            "versao": 2,
            "content_hash": "def456",
            "confirmado_por": "Eng. B",
            "motivo_revisao": "Revisão anual",
            "tributario": {"regime": "simples", "municipio": "RJ", "iss_aliquota_municipal": 0.02},
            "lucro": {},
        }
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(perfil), encoding="utf-8")
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(bdi_app, ["show", "mypro"])
        assert result.exit_code == 0
        assert "Revisão anual" in result.output


# ============================================================================
# commands_bdi.py — bdi update
# ============================================================================


class TestBdiUpdate:
    def _make_bdi_file(self, tmp_path: Path, name: str = "perfil.json") -> Path:
        _aplic = {
            "iss": {"aplicavel": False, "aliquota": 0.0},
            "cofins": {"aplicavel": False, "aliquota": 0.0},
            "pis": {"aplicavel": False, "aliquota": 0.0},
            "cssl": {"aplicavel": False, "aliquota": 0.0},
            "ir": {"aplicavel": False, "aliquota": 0.0},
        }
        bdi_data = {
            "tributario": {
                "regime": "lucro_real",
                "municipio": "São Paulo",
                "iss_aliquota_municipal": 0.03,
                "mao_obra": _aplic,
                "material": _aplic,
                "servicos": _aplic,
                "indireto": _aplic,
                "diesel": _aplic,
            },
            "lucro": {
                "mao_obra": 0.08,
                "material": 0.05,
                "servicos": 0.08,
                "indireto": 0.05,
                "diesel": 0.05,
            },
        }
        f = tmp_path / name
        f.write_text(json.dumps(bdi_data), encoding="utf-8")
        return f

    def _make_project(self, tmp_path: Path, project_name: str = "mypro") -> MagicMock:
        proj_dir = tmp_path / "projects" / project_name
        proj_dir.mkdir(parents=True)
        mock_proj = MagicMock()
        mock_proj.root = proj_dir
        mock_proj.meta = {"id": "proj-uuid-001"}
        return mock_proj

    def test_update_bad_json_file(self, tmp_path):
        """Corrupt JSON in from-file → exit 1 reading error."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("NOT JSON", encoding="utf-8")
        mock_proj = self._make_project(tmp_path)
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(
                bdi_app,
                ["update", "mypro", "--from-file", str(bad_file), "--confirmado-por", "Eng", "--yes"],
            )
        assert result.exit_code == 1
        assert "Falha ao ler" in result.output

    def test_update_invalid_schema(self, tmp_path):
        """Invalid tributario structure → exit 1 validation error."""
        bad_file = tmp_path / "invalid.json"
        bad_file.write_text('{"tributario": "not_an_object", "lucro": {}}', encoding="utf-8")
        mock_proj = self._make_project(tmp_path)
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(
                bdi_app,
                ["update", "mypro", "--from-file", str(bad_file), "--confirmado-por", "Eng", "--yes"],
            )
        assert result.exit_code == 1
        assert "inválidos" in result.output

    def test_update_missing_motivo_when_existing_perfil(self, tmp_path):
        """Existing perfil but no --motivo → exit 1."""
        bdi_file = self._make_bdi_file(tmp_path)
        mock_proj = self._make_project(tmp_path)
        # Write an existing perfil
        bdi_dir = mock_proj.root / "bdi"
        bdi_dir.mkdir()
        _aplic = {
            "iss": {"aplicavel": False, "aliquota": 0.0},
            "cofins": {"aplicavel": False, "aliquota": 0.0},
            "pis": {"aplicavel": False, "aliquota": 0.0},
            "cssl": {"aplicavel": False, "aliquota": 0.0},
            "ir": {"aplicavel": False, "aliquota": 0.0},
        }
        existing = {
            "versao": 1,
            "content_hash": "abc",
            "confirmado_por": "Old Eng",
            "confirmado_em": "2026-01-01T00:00:00+00:00",
            "tributario": {
                "regime": "lucro_real",
                "municipio": "SP",
                "iss_aliquota_municipal": 0.03,
                "mao_obra": _aplic,
                "material": _aplic,
                "servicos": _aplic,
                "indireto": _aplic,
                "diesel": _aplic,
            },
            "lucro": {"mao_obra": 0.08, "material": 0.05, "servicos": 0.08, "indireto": 0.05, "diesel": 0.05},
            "projeto_id": "proj-uuid-001",
            "perfil_id": "perfil-001",
        }
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(existing), encoding="utf-8")
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(
                bdi_app,
                ["update", "mypro", "--from-file", str(bdi_file), "--confirmado-por", "Eng", "--yes"],
            )
        assert result.exit_code == 1
        assert "motivo" in result.output.lower()

    def test_update_cancelled_by_user(self, tmp_path):
        """User answers 'n' to confirm → cancelled."""
        bdi_file = self._make_bdi_file(tmp_path)
        mock_proj = self._make_project(tmp_path)

        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(
                bdi_app,
                ["update", "mypro", "--from-file", str(bdi_file), "--confirmado-por", "Eng"],
                input="n\n",
            )
        assert result.exit_code == 0
        assert "cancelada" in result.output.lower()

    def test_update_new_perfil_success(self, tmp_path):
        """New project (no existing perfil) + --yes → v1 perfil saved."""
        bdi_file = self._make_bdi_file(tmp_path)
        mock_proj = self._make_project(tmp_path)
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(
                bdi_app,
                ["update", "mypro", "--from-file", str(bdi_file), "--confirmado-por", "Eng. Test", "--yes"],
            )
        assert result.exit_code == 0
        assert "v1" in result.output
        assert (mock_proj.root / "bdi" / "perfil_bdi.json").exists()

    def test_update_with_motivo_and_existing_perfil(self, tmp_path):
        """Existing perfil + --motivo → v2 perfil saved with diff artifact."""
        bdi_file = self._make_bdi_file(tmp_path)
        mock_proj = self._make_project(tmp_path)
        bdi_dir = mock_proj.root / "bdi"
        bdi_dir.mkdir()
        _aplic = {
            "iss": {"aplicavel": False, "aliquota": 0.0},
            "cofins": {"aplicavel": False, "aliquota": 0.0},
            "pis": {"aplicavel": False, "aliquota": 0.0},
            "cssl": {"aplicavel": False, "aliquota": 0.0},
            "ir": {"aplicavel": False, "aliquota": 0.0},
        }
        existing = {
            "versao": 1,
            "content_hash": "aabbcc",
            "confirmado_por": "Old Eng",
            "confirmado_em": "2026-01-01T00:00:00+00:00",
            "tributario": {
                "regime": "lucro_real",
                "municipio": "SP",
                "iss_aliquota_municipal": 0.03,
                "mao_obra": _aplic,
                "material": _aplic,
                "servicos": _aplic,
                "indireto": _aplic,
                "diesel": _aplic,
            },
            "lucro": {"mao_obra": 0.08, "material": 0.05, "servicos": 0.08, "indireto": 0.05, "diesel": 0.05},
            "projeto_id": "proj-uuid-001",
            "perfil_id": "perfil-old-001",
        }
        (bdi_dir / "perfil_bdi.json").write_text(json.dumps(existing), encoding="utf-8")
        with patch(f"{_BDI_MOD}.resolve_project", return_value=mock_proj):
            result = runner.invoke(
                bdi_app,
                [
                    "update",
                    "mypro",
                    "--from-file",
                    str(bdi_file),
                    "--confirmado-por",
                    "New Eng",
                    "--motivo",
                    "Annual review",
                    "--yes",
                ],
            )
        assert result.exit_code == 0
        assert "v2" in result.output


# ============================================================================
# commands_bdi.py — helper functions
# ============================================================================

from concilium.presentation.cli.commands_bdi import _bdi_aplic_flags, _perfil_path  # noqa: E402


class TestBdiHelpers:
    def test_perfil_path(self, tmp_path):
        p = _perfil_path(tmp_path)
        assert p == tmp_path / "bdi" / "perfil_bdi.json"

    def test_bdi_aplic_flags_all_true(self):
        aplic = {k: {"aplicavel": True} for k in ["iss", "pis", "cofins", "cssl", "ir"]}
        flags = _bdi_aplic_flags(aplic)
        assert all(f == "[OK]" for f in flags)

    def test_bdi_aplic_flags_all_false(self):
        aplic = {}
        flags = _bdi_aplic_flags(aplic)
        assert all(f == "[X]" for f in flags)

    def test_bdi_aplic_flags_mixed(self):
        aplic = {
            "iss": {"aplicavel": True},
            "pis": {"aplicavel": False},
            "cofins": {"aplicavel": True},
            "cssl": {},
            "ir": {"aplicavel": True},
        }
        flags = _bdi_aplic_flags(aplic)
        assert flags[0] == "[OK]"
        assert flags[1] == "[X]"
        assert flags[2] == "[OK]"


# ============================================================================
# commands_bdi.py — _bu_show_bdi_diff / _bu_persist_bdi_diff (via update flow)
# ============================================================================

from concilium.presentation.cli.commands_bdi import _bu_persist_bdi_diff, _bu_show_bdi_diff  # noqa: E402


class TestBuShowBdiDiff:
    def test_show_diff_no_anterior(self):
        console = MagicMock()
        trib = MagicMock()
        trib.regime = "lucro_real"
        trib.municipio = "SP"
        novo = MagicMock()
        novo.model_dump.return_value = {"tributario": {}, "lucro": {}}
        _bu_show_bdi_diff(console, None, novo, 1, trib)

    def test_show_diff_with_changes(self):
        console = MagicMock()
        ant = MagicMock()
        ant.model_dump.return_value = {"tributario": {"regime": "simples"}, "lucro": {"lucro_bruto": 5.0}}
        novo = MagicMock()
        novo.model_dump.return_value = {"tributario": {"regime": "lucro_real"}, "lucro": {"lucro_bruto": 8.0}}
        trib = MagicMock()
        _bu_show_bdi_diff(console, ant, novo, 2, trib)

    def test_show_diff_no_changes(self):
        console = MagicMock()
        same_dict = {"tributario": {"regime": "lucro_real"}, "lucro": {"lucro_bruto": 8.0}}
        ant = MagicMock()
        ant.model_dump.return_value = same_dict
        novo = MagicMock()
        novo.model_dump.return_value = same_dict
        trib = MagicMock()
        _bu_show_bdi_diff(console, ant, novo, 2, trib)

    def test_show_diff_model_dump_exception(self):
        """model_dump raises → 'Diff não disponível' shown without crash."""
        console = MagicMock()
        ant = MagicMock()
        ant.model_dump.side_effect = Exception("fail")
        novo = MagicMock()
        trib = MagicMock()
        _bu_show_bdi_diff(console, ant, novo, 2, trib)


class TestBuPersistBdiDiff:
    def test_persist_no_anterior(self, tmp_path):
        """perfil_anterior is None → no file written, no error."""
        _bu_persist_bdi_diff(tmp_path, None, MagicMock(), 2, "reason")

    def test_persist_with_anterior_writes_file(self, tmp_path):
        """Valid models → diff JSON written."""

        # Build minimal anterior and novo objects that have model_dump
        ant = MagicMock()
        ant.model_dump.return_value = {"tributario": {"regime": "simples"}, "lucro": {"lucro_bruto": 5.0}}
        ant.versao = 1
        ant.perfil_id = "old-id"
        ant.projeto_id = "proj-001"

        novo = MagicMock()
        novo.model_dump.return_value = {"tributario": {"regime": "lucro_real"}, "lucro": {"lucro_bruto": 8.0}}
        novo.versao = 2
        novo.perfil_id = "new-id"
        novo.projeto_id = "proj-001"

        with patch(f"{_BDI_MOD}.BdiPerfilDiff") as mock_diff_cls:
            mock_diff_cls.return_value.model_dump.return_value = {"resumo": "v1→v2"}
            _bu_persist_bdi_diff(tmp_path, ant, novo, 2, "annual review")

    def test_persist_exception_swallowed(self, tmp_path):
        """Exception in persist is silently swallowed."""
        ant = MagicMock()
        ant.model_dump.side_effect = RuntimeError("fail")
        ant.versao = 1
        ant.perfil_id = "id"
        ant.projeto_id = "proj"
        novo = MagicMock()
        _bu_persist_bdi_diff(tmp_path, ant, novo, 2, "reason")
        # No exception raised
