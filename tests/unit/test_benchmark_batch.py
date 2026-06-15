"""Tests for concilium.application.benchmarks.execution.batch — coverage boost toward 80%+."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from concilium.application.benchmarks.execution.batch import (
    BenchmarkBatchRunner,
    discover_benchmark_slugs,
    find_benchmark_reference,
)


# ══ find_benchmark_reference ══════════════════════════════════════════════════


class TestFindBenchmarkReference:
    def test_missing_root_returns_none(self, tmp_path: Path):
        """Raiz inexistente deve retornar None."""
        missing = tmp_path / "does_not_exist"
        result = find_benchmark_reference(missing, "AGIS")
        assert result is None

    def test_existing_root_no_subdir_returns_none(self, tmp_path: Path):
        """Raiz existe mas slug não tem subdiretório → None."""
        # tmp_path exists but has no AGIS subdir
        result = find_benchmark_reference(tmp_path, "AGIS")
        assert result is None

    def test_slug_case_insensitive_uppercase(self, tmp_path: Path):
        """Slug é convertido para maiúsculo ao montar o caminho."""
        bench_dir = tmp_path / "AGIS"
        bench_dir.mkdir()
        ref = bench_dir / "referencia.json"
        ref.write_text('{"projeto": "agis"}', encoding="utf-8")

        result = find_benchmark_reference(tmp_path, "agis")
        assert result == ref

    def test_candidate_path_1_referencia_at_root_of_bench_dir(self, tmp_path: Path):
        """Encontra referencia.json diretamente na pasta do benchmark."""
        bench_dir = tmp_path / "PROJ1"
        bench_dir.mkdir()
        ref = bench_dir / "referencia.json"
        ref.write_text("{}", encoding="utf-8")

        result = find_benchmark_reference(tmp_path, "PROJ1")
        assert result == ref

    def test_candidate_path_2_artifacts_inputs(self, tmp_path: Path):
        """Encontra referencia.json em artifacts/inputs/."""
        bench_dir = tmp_path / "PROJ2"
        (bench_dir / "artifacts" / "inputs").mkdir(parents=True)
        ref = bench_dir / "artifacts" / "inputs" / "referencia.json"
        ref.write_text("{}", encoding="utf-8")

        result = find_benchmark_reference(tmp_path, "PROJ2")
        assert result == ref

    def test_candidate_path_3_artifacts_direct(self, tmp_path: Path):
        """Encontra referencia.json em artifacts/ (sem inputs/)."""
        bench_dir = tmp_path / "PROJ3"
        (bench_dir / "artifacts").mkdir(parents=True)
        ref = bench_dir / "artifacts" / "referencia.json"
        ref.write_text("{}", encoding="utf-8")

        result = find_benchmark_reference(tmp_path, "PROJ3")
        assert result == ref

    def test_path_1_takes_precedence_over_path_2(self, tmp_path: Path):
        """Quando há referencia.json na raiz e em artifacts/inputs/, retorna a raiz."""
        bench_dir = tmp_path / "MULTI"
        (bench_dir / "artifacts" / "inputs").mkdir(parents=True)
        ref_root = bench_dir / "referencia.json"
        ref_root.write_text("{}", encoding="utf-8")
        ref_nested = bench_dir / "artifacts" / "inputs" / "referencia.json"
        ref_nested.write_text("{}", encoding="utf-8")

        result = find_benchmark_reference(tmp_path, "MULTI")
        assert result == ref_root

    def test_no_referencia_json_anywhere_returns_none(self, tmp_path: Path):
        """Diretório existe mas sem nenhum referencia.json → None."""
        bench_dir = tmp_path / "EMPTY"
        bench_dir.mkdir()
        # Create some unrelated files
        (bench_dir / "other.json").write_text("{}", encoding="utf-8")

        result = find_benchmark_reference(tmp_path, "EMPTY")
        assert result is None


# ══ discover_benchmark_slugs ══════════════════════════════════════════════════


class TestDiscoverBenchmarkSlugs:
    def test_missing_root_returns_empty_list(self, tmp_path: Path):
        """Raiz inexistente retorna lista vazia."""
        missing = tmp_path / "no_such_root"
        assert discover_benchmark_slugs(missing) == []

    def test_root_is_a_file_returns_empty_list(self, tmp_path: Path):
        """Quando o caminho existe mas é um arquivo (não dir) retorna []."""
        a_file = tmp_path / "not_a_dir.json"
        a_file.write_text("{}", encoding="utf-8")
        assert discover_benchmark_slugs(a_file) == []

    def test_empty_root_returns_empty_list(self, tmp_path: Path):
        """Raiz vazia retorna lista vazia."""
        assert discover_benchmark_slugs(tmp_path) == []

    def test_dirs_without_referencia_ignored(self, tmp_path: Path):
        """Diretórios sem referencia.json não são incluídos."""
        (tmp_path / "PROJ_A").mkdir()
        (tmp_path / "PROJ_A" / "other.json").write_text("{}", encoding="utf-8")
        assert discover_benchmark_slugs(tmp_path) == []

    def test_files_in_root_ignored(self, tmp_path: Path):
        """Arquivos na raiz (não diretórios) são ignorados."""
        (tmp_path / "some_file.json").write_text("{}", encoding="utf-8")
        assert discover_benchmark_slugs(tmp_path) == []

    def test_discovers_dir_with_referencia_at_root(self, tmp_path: Path):
        """Dir com referencia.json na raiz é descoberto."""
        bench = tmp_path / "AGIS"
        bench.mkdir()
        (bench / "referencia.json").write_text("{}", encoding="utf-8")
        result = discover_benchmark_slugs(tmp_path)
        assert result == ["AGIS"]

    def test_discovers_dir_with_referencia_in_artifacts_inputs(self, tmp_path: Path):
        """Dir com referencia.json em artifacts/inputs é descoberto."""
        bench = tmp_path / "PROJ"
        (bench / "artifacts" / "inputs").mkdir(parents=True)
        (bench / "artifacts" / "inputs" / "referencia.json").write_text("{}", encoding="utf-8")
        result = discover_benchmark_slugs(tmp_path)
        assert result == ["PROJ"]

    def test_discovers_dir_with_referencia_in_artifacts_direct(self, tmp_path: Path):
        """Dir com referencia.json em artifacts/ é descoberto."""
        bench = tmp_path / "PROJ"
        (bench / "artifacts").mkdir(parents=True)
        (bench / "artifacts" / "referencia.json").write_text("{}", encoding="utf-8")
        result = discover_benchmark_slugs(tmp_path)
        assert result == ["PROJ"]

    def test_multiple_benchmarks_returned_sorted(self, tmp_path: Path):
        """Múltiplos benchmarks são retornados em ordem alfabética."""
        for name in ["CHARLIE", "ALPHA", "BETA"]:
            d = tmp_path / name
            d.mkdir()
            (d / "referencia.json").write_text("{}", encoding="utf-8")

        result = discover_benchmark_slugs(tmp_path)
        assert result == ["ALPHA", "BETA", "CHARLIE"]

    def test_mixed_valid_and_invalid_dirs(self, tmp_path: Path):
        """Apenas dirs com referencia.json são incluídos."""
        valid = tmp_path / "VALID"
        valid.mkdir()
        (valid / "referencia.json").write_text("{}", encoding="utf-8")

        invalid = tmp_path / "INVALID"
        invalid.mkdir()
        (invalid / "nope.txt").write_text("x", encoding="utf-8")

        result = discover_benchmark_slugs(tmp_path)
        assert result == ["VALID"]

    def test_slugs_returned_as_uppercase(self, tmp_path: Path):
        """Nome dos diretórios é retornado como está (já uppercase pelo padrão)."""
        bench = tmp_path / "lowercase"
        bench.mkdir()
        (bench / "referencia.json").write_text("{}", encoding="utf-8")
        # discover_benchmark_slugs returns benchmark_dir.name.upper()
        result = discover_benchmark_slugs(tmp_path)
        assert result == ["LOWERCASE"]


# ══ BenchmarkBatchRunner.discover_specs ═══════════════════════════════════════


class TestDiscoverSpecs:
    def _make_runner(self, tmp_path: Path) -> BenchmarkBatchRunner:
        return BenchmarkBatchRunner(
            benchmarks_root=tmp_path / "benchmarks",
            config_root=tmp_path / "config",
            projects_root=tmp_path / "projects",
        )

    def test_missing_benchmarks_root_returns_empty(self, tmp_path: Path):
        """benchmarks_root inexistente retorna lista vazia."""
        runner = self._make_runner(tmp_path)
        assert runner.discover_specs() == []

    def test_empty_benchmarks_root_returns_empty(self, tmp_path: Path):
        """benchmarks_root vazio retorna lista vazia."""
        runner = self._make_runner(tmp_path)
        runner.benchmarks_root.mkdir(parents=True)
        assert runner.discover_specs() == []

    def test_benchmark_dir_without_referencia_skipped(self, tmp_path: Path):
        """Dir sem referencia.json é ignorado."""
        runner = self._make_runner(tmp_path)
        runner.benchmarks_root.mkdir(parents=True)
        (runner.benchmarks_root / "NOREFERENCE").mkdir()
        assert runner.discover_specs() == []

    def test_discovers_spec_from_referencia_json(self, tmp_path: Path):
        """Dir com referencia.json válido gera um ProjectSpec."""
        runner = self._make_runner(tmp_path)
        runner.benchmarks_root.mkdir(parents=True)

        bench = runner.benchmarks_root / "AGIS"
        bench.mkdir()

        ref_data = {
            "projeto": "AGIS",
            "slug": "AGIS",
            "data_inicio": "2025-01-01",
            "data_termino": "2025-12-31",
        }
        (bench / "referencia.json").write_text(json.dumps(ref_data), encoding="utf-8")

        with patch(
            "concilium.application.benchmarks.execution.batch.load_spec_from_dict"
        ) as mock_load, patch(
            "concilium.application.benchmarks.execution.batch.normalize_referencia_weeks"
        ) as mock_norm:
            mock_spec = MagicMock()
            mock_spec.slug = "AGIS"
            mock_load.return_value = mock_spec

            specs = runner.discover_specs()

        assert len(specs) == 1
        assert specs[0].slug == "AGIS"
        mock_norm.assert_called_once()
        mock_load.assert_called_once()

    def test_non_dir_entries_in_benchmarks_root_skipped(self, tmp_path: Path):
        """Arquivos (não diretórios) na raiz de benchmarks são ignorados."""
        runner = self._make_runner(tmp_path)
        runner.benchmarks_root.mkdir(parents=True)
        (runner.benchmarks_root / "some_file.json").write_text("{}", encoding="utf-8")

        assert runner.discover_specs() == []

    def test_referencia_in_artifacts_inputs_path(self, tmp_path: Path):
        """Spec é carregado quando referencia.json está em artifacts/inputs/."""
        runner = self._make_runner(tmp_path)
        runner.benchmarks_root.mkdir(parents=True)

        bench = runner.benchmarks_root / "PROJ"
        (bench / "artifacts" / "inputs").mkdir(parents=True)
        ref_data = {"projeto": "PROJ", "slug": "PROJ"}
        (bench / "artifacts" / "inputs" / "referencia.json").write_text(
            json.dumps(ref_data), encoding="utf-8"
        )

        with patch(
            "concilium.application.benchmarks.execution.batch.load_spec_from_dict"
        ) as mock_load, patch(
            "concilium.application.benchmarks.execution.batch.normalize_referencia_weeks"
        ):
            mock_spec = MagicMock()
            mock_spec.slug = "PROJ"
            mock_load.return_value = mock_spec

            specs = runner.discover_specs()

        assert len(specs) == 1

    def test_multiple_specs_returned_sorted(self, tmp_path: Path):
        """Múltiplos specs retornados na ordem alfabética dos diretórios."""
        runner = self._make_runner(tmp_path)
        runner.benchmarks_root.mkdir(parents=True)

        for name in ["CHARLIE", "ALPHA", "BETA"]:
            d = runner.benchmarks_root / name
            d.mkdir()
            (d / "referencia.json").write_text(
                json.dumps({"projeto": name, "slug": name}), encoding="utf-8"
            )

        with patch(
            "concilium.application.benchmarks.execution.batch.load_spec_from_dict"
        ) as mock_load, patch(
            "concilium.application.benchmarks.execution.batch.normalize_referencia_weeks"
        ):
            mock_load.side_effect = lambda ref, path: MagicMock(
                slug=ref.get("slug", "?")
            )

            specs = runner.discover_specs()

        assert len(specs) == 3
        assert [s.slug for s in specs] == ["ALPHA", "BETA", "CHARLIE"]


# ══ BenchmarkBatchRunner.run_all ══════════════════════════════════════════════


def _make_canned_report(slug: str, status: str = "OK") -> dict:
    return {
        "slug": slug,
        "status_final": status,
        "confronto": {
            "deltas": {
                "custo_direto": {"percentual": 1.5},
                "custo_indireto": {"percentual": -0.3},
                "custo_total": {"percentual": 0.7},
                "preco_venda": {"percentual": 2.1},
            }
        },
        "skills_log": [],
        "quality_gates": {"decision": status},
    }


class TestRunAll:
    def _make_runner(self, tmp_path: Path) -> BenchmarkBatchRunner:
        runner = BenchmarkBatchRunner(
            benchmarks_root=tmp_path / "benchmarks",
            config_root=tmp_path / "config",
            projects_root=tmp_path / "projects",
        )
        return runner

    def _setup_two_specs(self, tmp_path: Path, runner: BenchmarkBatchRunner) -> None:
        """Create filesystem structure for two benchmark specs."""
        runner.benchmarks_root.mkdir(parents=True)
        for name in ["ALPHA", "BETA"]:
            d = runner.benchmarks_root / name
            d.mkdir()
            (d / "referencia.json").write_text(
                json.dumps({"projeto": name, "slug": name}), encoding="utf-8"
            )

    def test_run_all_returns_one_report_per_spec(self, tmp_path: Path, capsys):
        """run_all retorna tantos reports quanto specs descobertos."""
        runner = self._make_runner(tmp_path)
        self._setup_two_specs(tmp_path, runner)

        spec_alpha = MagicMock()
        spec_alpha.slug = "ALPHA"
        spec_beta = MagicMock()
        spec_beta.slug = "BETA"

        report_alpha = _make_canned_report("ALPHA")
        report_beta = _make_canned_report("BETA")

        mock_runner_instance = MagicMock()
        mock_runner_instance.run.side_effect = [report_alpha, report_beta]

        with patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkRunner",
            return_value=mock_runner_instance,
        ), patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkBatchRunner.discover_specs",
            return_value=[spec_alpha, spec_beta],
        ):
            reports = runner.run_all(reset=True, quiet=False)

        assert len(reports) == 2
        assert reports[0] == report_alpha
        assert reports[1] == report_beta

    def test_run_all_verbose_mode_prints_separator(self, tmp_path: Path, capsys):
        """Modo verbose imprime separador '=' e nome do benchmark."""
        runner = self._make_runner(tmp_path)

        spec = MagicMock()
        spec.slug = "MYPROJECT"
        report = _make_canned_report("MYPROJECT")

        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = report

        with patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkRunner",
            return_value=mock_runner_instance,
        ), patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkBatchRunner.discover_specs",
            return_value=[spec],
        ):
            runner.run_all(reset=False, quiet=False)

        captured = capsys.readouterr()
        assert "=" * 60 in captured.out
        assert "MYPROJECT" in captured.out

    def test_run_all_quiet_mode_prints_status(self, tmp_path: Path, capsys):
        """Modo quiet imprime '[N/total] slug... STATUS'."""
        runner = self._make_runner(tmp_path)

        spec = MagicMock()
        spec.slug = "QUIETPROJ"
        report = _make_canned_report("QUIETPROJ", status="PASS")

        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = report

        with patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkRunner",
            return_value=mock_runner_instance,
        ), patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkBatchRunner.discover_specs",
            return_value=[spec],
        ):
            runner.run_all(reset=True, quiet=True)

        captured = capsys.readouterr()
        assert "QUIETPROJ" in captured.out
        assert "PASS" in captured.out

    def test_run_all_quiet_mode_format_n_of_total(self, tmp_path: Path, capsys):
        """Modo quiet usa formato [N/total]."""
        runner = self._make_runner(tmp_path)

        specs = [MagicMock(slug=f"P{i}") for i in range(3)]
        reports = [_make_canned_report(f"P{i}") for i in range(3)]

        mock_runner_instance = MagicMock()
        mock_runner_instance.run.side_effect = reports

        with patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkRunner",
            return_value=mock_runner_instance,
        ), patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkBatchRunner.discover_specs",
            return_value=specs,
        ):
            runner.run_all(quiet=True)

        captured = capsys.readouterr()
        assert "[1/3]" in captured.out
        assert "[2/3]" in captured.out
        assert "[3/3]" in captured.out

    def test_run_all_no_specs_returns_empty_list(self, tmp_path: Path):
        """Sem specs, run_all retorna lista vazia."""
        runner = self._make_runner(tmp_path)

        mock_runner_instance = MagicMock()

        with patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkRunner",
            return_value=mock_runner_instance,
        ), patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkBatchRunner.discover_specs",
            return_value=[],
        ):
            reports = runner.run_all()

        assert reports == []
        mock_runner_instance.run.assert_not_called()

    def test_run_all_passes_reset_flag_to_runner(self, tmp_path: Path, capsys):
        """Flag reset é repassado ao BenchmarkRunner.run."""
        runner = self._make_runner(tmp_path)

        spec = MagicMock()
        spec.slug = "X"
        report = _make_canned_report("X")

        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = report

        with patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkRunner",
            return_value=mock_runner_instance,
        ), patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkBatchRunner.discover_specs",
            return_value=[spec],
        ):
            runner.run_all(reset=False)

        mock_runner_instance.run.assert_called_once_with(spec, reset=False)

    def test_run_all_uses_quality_gates_when_no_status_final(
        self, tmp_path: Path, capsys
    ):
        """Quando status_final ausente, usa quality_gates.decision no quiet mode."""
        runner = self._make_runner(tmp_path)

        spec = MagicMock()
        spec.slug = "QG"
        report = {
            "slug": "QG",
            "quality_gates": {"decision": "ALERTA"},
            "skills_log": [],
        }

        mock_runner_instance = MagicMock()
        mock_runner_instance.run.return_value = report

        with patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkRunner",
            return_value=mock_runner_instance,
        ), patch(
            "concilium.application.benchmarks.execution.batch.BenchmarkBatchRunner.discover_specs",
            return_value=[spec],
        ):
            runner.run_all(quiet=True)

        captured = capsys.readouterr()
        assert "ALERTA" in captured.out


# ══ BenchmarkBatchRunner.build_summary ════════════════════════════════════════


class TestBuildSummary:
    def _make_runner(self, tmp_path: Path) -> BenchmarkBatchRunner:
        return BenchmarkBatchRunner(
            benchmarks_root=tmp_path,
            config_root=tmp_path,
            projects_root=tmp_path,
        )

    def test_empty_reports_returns_empty_summary(self, tmp_path: Path):
        runner = self._make_runner(tmp_path)
        assert runner.build_summary([]) == []

    def test_summary_row_keys(self, tmp_path: Path):
        """Cada linha tem as colunas esperadas."""
        runner = self._make_runner(tmp_path)
        report = _make_canned_report("AGIS")
        rows = runner.build_summary([report])
        assert len(rows) == 1
        row = rows[0]
        assert set(row.keys()) == {
            "Projeto",
            "Status",
            "Delta Direto %",
            "Delta Indireto %",
            "Delta Total %",
            "Delta Venda %",
        }

    def test_summary_slug_from_slug_field(self, tmp_path: Path):
        runner = self._make_runner(tmp_path)
        report = {"slug": "MYSLUG", "status_final": "OK", "skills_log": []}
        rows = runner.build_summary([report])
        assert rows[0]["Projeto"] == "MYSLUG"

    def test_summary_slug_falls_back_to_projeto(self, tmp_path: Path):
        """Quando slug ausente usa campo 'projeto'."""
        runner = self._make_runner(tmp_path)
        report = {"projeto": "MYPROJETO", "status_final": "OK", "skills_log": []}
        rows = runner.build_summary([report])
        assert rows[0]["Projeto"] == "MYPROJETO"

    def test_summary_slug_fallback_to_dash(self, tmp_path: Path):
        """Quando nem slug nem projeto, usa '-'."""
        runner = self._make_runner(tmp_path)
        report = {"status_final": "OK", "skills_log": []}
        rows = runner.build_summary([report])
        assert rows[0]["Projeto"] == "-"

    def test_summary_status_from_status_final(self, tmp_path: Path):
        runner = self._make_runner(tmp_path)
        report = {"slug": "P", "status_final": "PASS", "skills_log": []}
        rows = runner.build_summary([report])
        assert rows[0]["Status"] == "PASS"

    def test_summary_status_falls_back_to_quality_gates_decision(self, tmp_path: Path):
        """status_final ausente → usa quality_gates.decision."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "quality_gates": {"decision": "ALERTA"},
            "skills_log": [],
        }
        rows = runner.build_summary([report])
        assert rows[0]["Status"] == "ALERTA"

    def test_summary_status_falls_back_to_ok_when_neither(self, tmp_path: Path):
        """Sem status_final nem quality_gates → 'OK'."""
        runner = self._make_runner(tmp_path)
        report = {"slug": "P", "skills_log": []}
        rows = runner.build_summary([report])
        assert rows[0]["Status"] == "OK"

    def test_summary_aviso_suffix_when_skill_erro(self, tmp_path: Path):
        """Skill com status ERRO adiciona /AVISO ao status."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "OK",
            "skills_log": [{"skill": "01", "status": "ERRO"}],
        }
        rows = runner.build_summary([report])
        assert rows[0]["Status"] == "OK/AVISO"

    def test_summary_aviso_suffix_when_skill_exception(self, tmp_path: Path):
        """Skill com status EXCEPTION adiciona /AVISO ao status."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "FAIL",
            "skills_log": [{"skill": "02", "status": "EXCEPTION"}],
        }
        rows = runner.build_summary([report])
        assert rows[0]["Status"] == "FAIL/AVISO"

    def test_summary_no_aviso_for_ok_skill(self, tmp_path: Path):
        """Skills com status OK não geram /AVISO."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "PASS",
            "skills_log": [{"skill": "01", "status": "OK"}],
        }
        rows = runner.build_summary([report])
        assert "/AVISO" not in rows[0]["Status"]

    def test_summary_aviso_stops_at_first_error(self, tmp_path: Path):
        """Mesmo com múltiplos erros, /AVISO aparece apenas uma vez."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "OK",
            "skills_log": [
                {"status": "ERRO"},
                {"status": "EXCEPTION"},
                {"status": "ERRO"},
            ],
        }
        rows = runner.build_summary([report])
        assert rows[0]["Status"].count("/AVISO") == 1

    def test_summary_delta_values_formatted_with_sign(self, tmp_path: Path):
        """Deltas positivos têm sinal +, negativos têm sinal -."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "OK",
            "skills_log": [],
            "confronto": {
                "deltas": {
                    "custo_direto": {"percentual": 3.14},
                    "custo_indireto": {"percentual": -1.50},
                    "custo_total": {"percentual": 0.0},
                    "preco_venda": {"percentual": 10.0},
                }
            },
        }
        rows = runner.build_summary([report])
        row = rows[0]
        assert row["Delta Direto %"] == "+3.14%"
        assert row["Delta Indireto %"] == "-1.50%"
        assert row["Delta Total %"] == "+0.00%"
        assert row["Delta Venda %"] == "+10.00%"

    def test_summary_na_when_deltas_missing(self, tmp_path: Path):
        """Deltas ausentes retornam 'N/A'."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "OK",
            "skills_log": [],
            # no confronto key at all
        }
        rows = runner.build_summary([report])
        row = rows[0]
        assert row["Delta Direto %"] == "N/A"
        assert row["Delta Indireto %"] == "N/A"
        assert row["Delta Total %"] == "N/A"
        assert row["Delta Venda %"] == "N/A"

    def test_summary_na_when_confronto_has_empty_deltas(self, tmp_path: Path):
        """confronto.deltas vazio retorna N/A para todos os campos."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "OK",
            "skills_log": [],
            "confronto": {"deltas": {}},
        }
        rows = runner.build_summary([report])
        row = rows[0]
        assert row["Delta Direto %"] == "N/A"

    def test_summary_na_when_percentual_is_none(self, tmp_path: Path):
        """Percentual explicitamente None retorna N/A."""
        runner = self._make_runner(tmp_path)
        report = {
            "slug": "P",
            "status_final": "OK",
            "skills_log": [],
            "confronto": {
                "deltas": {
                    "custo_direto": {"percentual": None},
                }
            },
        }
        rows = runner.build_summary([report])
        assert rows[0]["Delta Direto %"] == "N/A"

    def test_build_summary_multiple_reports(self, tmp_path: Path):
        """build_summary processa múltiplos reports e retorna uma linha por report."""
        runner = self._make_runner(tmp_path)
        reports = [_make_canned_report(f"PROJ_{i}") for i in range(5)]
        rows = runner.build_summary(reports)
        assert len(rows) == 5
        assert [r["Projeto"] for r in rows] == [f"PROJ_{i}" for i in range(5)]

    def test_summary_mixed_aviso_and_clean(self, tmp_path: Path):
        """Mix de reports com e sem erros nas skills."""
        runner = self._make_runner(tmp_path)
        reports = [
            {
                "slug": "CLEAN",
                "status_final": "OK",
                "skills_log": [{"status": "OK"}],
            },
            {
                "slug": "BROKEN",
                "status_final": "FAIL",
                "skills_log": [{"status": "ERRO"}],
            },
        ]
        rows = runner.build_summary(reports)
        assert rows[0]["Status"] == "OK"
        assert rows[1]["Status"] == "FAIL/AVISO"
