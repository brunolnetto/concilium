"""Tests for benchmarks comparison and support modules at 0% coverage.

Covers:
- catalog_confronto.py
- equipes_detail.py
- granular.py
- output_packager.py
- cpu_mapper.py (CpuMapper)
- cpu_validator.py (CpuValidator)
"""

from __future__ import annotations

import json
import zipfile
from builtins import __import__ as _builtin_import
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

_SAMPLE_CPU = {
    "codigo": "ATI-001",
    "descricao": "Aterro Compactação",
    "unidade": "m³",
    "categoria": "TERRA",
}

_SAMPLE_CATALOGO = {"cpus": [_SAMPLE_CPU]}

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# 4. output_packager.py
# ===========================================================================

from concilium.application.benchmarks.charts.output_packager import (  # noqa: E402
    _cf_collect_audit,
    _cf_collect_cenarios,
    _cf_collect_graficos,
    _cf_collect_ref,
    _cf_collect_relatorios,
    _collect_files,
    _find_benchmark_dir,
    _gerar_manifest,
    _tentar_gerar_graficos,
    _tools_root_from_config,
    empacotar_outputs,
)


class TestToolsRootFromConfig:
    def test_returns_parent(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        result = _tools_root_from_config(config_root)
        assert result == tmp_path


class TestFindBenchmarkDir:
    def test_no_matching_dir_returns_none(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        result = _find_benchmark_dir("NOEXIST", config_root=config_root)
        assert result is None

    def test_returns_existing_path(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "MYBENCH"
        bench_dir.mkdir(parents=True)
        result = _find_benchmark_dir("MYBENCH", config_root=config_root)
        assert result == bench_dir

    def test_no_config_root_skips_config_candidate(self):
        """Line 32 false branch: config_root=None -> only the fallback candidate is checked."""
        result = _find_benchmark_dir("DEFINITELY-NOT-A-REAL-BENCHMARK-SLUG-XYZ", config_root=None)
        assert result is None


class TestCfCollectGraficos:
    def test_empty_bench_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        assert collected == []

    def test_viz_dir_with_pngs(self, tmp_path):
        viz_dir = tmp_path / "artifacts" / "outputs" / "visualizations"
        viz_dir.mkdir(parents=True)
        (viz_dir / "chart1.png").write_text("fake")
        (viz_dir / "chart2.svg").write_text("fake")
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        arc_names = [arc for _, arc in collected]
        assert "graficos/chart1.png" in arc_names
        assert "graficos/chart2.svg" in arc_names

    def test_fallback_to_outputs_dir(self, tmp_path):
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "plot.png").write_text("fake")
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        assert any(arc == "graficos/plot.png" for _, arc in collected)

    def test_no_outputs_dir_returns_empty(self, tmp_path):
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        assert collected == []


class TestCfCollectRelatorios:
    def test_reports_dir_with_files(self, tmp_path):
        reports_dir = tmp_path / "artifacts" / "outputs" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report.md").write_text("# Report")
        (reports_dir / "data.json").write_text("{}")
        collected: list = []
        _cf_collect_relatorios(tmp_path, collected)
        arc_names = [arc for _, arc in collected]
        assert "relatorio/report.md" in arc_names
        assert "relatorio/data.json" in arc_names

    def test_fallback_to_artifacts_outputs(self, tmp_path):
        art_out = tmp_path / "artifacts" / "outputs"
        art_out.mkdir(parents=True)
        (art_out / "summary.md").write_text("# Summary")
        collected: list = []
        _cf_collect_relatorios(tmp_path, collected)
        assert any(arc == "relatorio/summary.md" for _, arc in collected)

    def test_no_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_relatorios(tmp_path, collected)
        assert collected == []


class TestCfCollectAudit:
    def test_audit_dir_with_jsons(self, tmp_path):
        audit_dir = tmp_path / "artifacts" / "audit"
        audit_dir.mkdir(parents=True)
        (audit_dir / "report.json").write_text("{}")
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        assert ("audit/report.json") in [arc for _, arc in collected]

    def test_fallback_audit_dir(self, tmp_path):
        audit_dir2 = tmp_path / "audit"
        audit_dir2.mkdir()
        (audit_dir2 / "bench.json").write_text("{}")
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        assert any(arc == "audit/bench.json" for _, arc in collected)

    def test_deduplication_of_arc_paths(self, tmp_path):
        # Same filename in artifacts/audit AND audit/ — should appear only once
        audit_primary = tmp_path / "artifacts" / "audit"
        audit_primary.mkdir(parents=True)
        (audit_primary / "shared.json").write_text("{}")
        audit_fallback = tmp_path / "audit"
        audit_fallback.mkdir()
        (audit_fallback / "shared.json").write_text("{}")
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        arcs = [arc for _, arc in collected]
        assert arcs.count("audit/shared.json") == 1

    def test_no_audit_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        assert collected == []


class TestCfCollectCenarios:
    def test_inter_dir_with_matching_files(self, tmp_path):
        inter_dir = tmp_path / "artifacts" / "intermediate"
        inter_dir.mkdir(parents=True)
        (inter_dir / "M0.benchmark_report.json").write_text("{}")
        (inter_dir / "plan_space_report.json").write_text("{}")
        collected: list = []
        _cf_collect_cenarios(tmp_path, collected)
        arcs = [arc for _, arc in collected]
        assert "cenarios/M0.benchmark_report.json" in arcs
        assert "cenarios/plan_space_report.json" in arcs

    def test_no_inter_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_cenarios(tmp_path, collected)
        assert collected == []


class TestCfCollectRef:
    def test_primary_ref_exists(self, tmp_path):
        ref_path = tmp_path / "artifacts" / "inputs" / "referencia.json"
        ref_path.parent.mkdir(parents=True)
        ref_path.write_text("{}")
        collected: list = []
        _cf_collect_ref(tmp_path, collected)
        assert any(arc == "inputs/referencia.json" for _, arc in collected)

    def test_fallback_to_root_ref(self, tmp_path):
        fallback = tmp_path / "referencia.json"
        fallback.write_text("{}")
        collected: list = []
        _cf_collect_ref(tmp_path, collected)
        assert any(arc == "inputs/referencia.json" for _, arc in collected)

    def test_no_ref_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_ref(tmp_path, collected)
        assert collected == []


class TestCollectFiles:
    def test_returns_combined_list(self, tmp_path):
        # Populate multiple artifact types
        ref_path = tmp_path / "referencia.json"
        ref_path.write_text("{}")
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        (audit_dir / "rep.json").write_text("{}")

        result = _collect_files(tmp_path)
        arcs = [arc for _, arc in result]
        assert "inputs/referencia.json" in arcs
        assert "audit/rep.json" in arcs


class TestGerarManifest:
    def test_returns_correct_structure(self, tmp_path):
        files = [
            (tmp_path / "a.png", "graficos/a.png"),
            (tmp_path / "b.json", "relatorio/b.json"),
            (tmp_path / "c.json", "audit/c.json"),
        ]
        manifest = _gerar_manifest("MYBENCH", files, tmp_path)
        assert manifest["slug"] == "MYBENCH"
        assert "gerado_em" in manifest
        assert manifest["arquivos"] == ["graficos/a.png", "relatorio/b.json", "audit/c.json"]
        assert manifest["totais"]["graficos"] == 1
        assert manifest["totais"]["relatorio"] == 1
        assert manifest["totais"]["audit"] == 1
        assert manifest["totais"]["cenarios"] == 0

    def test_slug_is_uppercased(self, tmp_path):
        manifest = _gerar_manifest("lower", [], tmp_path)
        assert manifest["slug"] == "LOWER"


class TestEmpacotar:
    def test_no_bench_dir_raises_file_not_found(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        with pytest.raises(FileNotFoundError):
            empacotar_outputs("MISSING", config_root=config_root, output_path=tmp_path / "out.zip")

    def test_no_files_raises_value_error(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "EMPTY"
        bench_dir.mkdir(parents=True)
        with pytest.raises(ValueError):
            empacotar_outputs("EMPTY", config_root=config_root, output_path=tmp_path / "out.zip", gerar_graficos=False)

    def test_creates_valid_zip_with_manifest(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "MYBENCH"
        # Place a referencia.json so _collect_files finds at least one file
        ref_path = bench_dir / "referencia.json"
        ref_path.parent.mkdir(parents=True)
        ref_path.write_text('{"eap": []}')
        output_zip = tmp_path / "output.zip"

        result = empacotar_outputs(
            "MYBENCH",
            config_root=config_root,
            output_path=output_zip,
            gerar_graficos=False,
        )

        assert result == output_zip
        assert output_zip.exists()
        with zipfile.ZipFile(output_zip) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["slug"] == "MYBENCH"

    def test_skips_collected_file_that_no_longer_exists(self, tmp_path):
        """Line 200 false branch: a collected (path, arc) entry whose real_path
        does not exist on disk is silently skipped when writing the zip."""

        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "GHOSTFILE"
        bench_dir.mkdir(parents=True)
        existing = bench_dir / "referencia.json"
        existing.write_text("{}")
        missing = bench_dir / "vanished.json"  # never created on disk
        output_zip = tmp_path / "out.zip"

        with patch(
            "concilium.application.benchmarks.charts.output_packager._collect_files",
            return_value=[(existing, "relatorio/referencia.json"), (missing, "relatorio/vanished.json")],
        ):
            result = empacotar_outputs(
                "GHOSTFILE",
                config_root=config_root,
                output_path=output_zip,
                gerar_graficos=False,
            )

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
        assert "relatorio/referencia.json" in names
        assert "relatorio/vanished.json" not in names

    def test_incluir_cenarios_includes_cenario_files(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "CENTEST"
        inter_dir = bench_dir / "artifacts" / "intermediate"
        inter_dir.mkdir(parents=True)
        (inter_dir / "M1.benchmark_report.json").write_text("{}")
        # Also add referencia so we have non-cenario files
        (bench_dir / "referencia.json").write_text("{}")
        output_zip = tmp_path / "out.zip"

        result = empacotar_outputs(
            "CENTEST",
            config_root=config_root,
            output_path=output_zip,
            gerar_graficos=False,
            incluir_cenarios=True,
        )

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
        assert "cenarios/M1.benchmark_report.json" in names


class TestTentarGerarGraficos:
    def test_pngs_exist_returns_immediately(self, tmp_path):
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "existing.png").write_text("fake")
        # Should not raise — just return early
        _tentar_gerar_graficos(tmp_path, "SLUG")

    def test_import_error_silent_pass(self, tmp_path, monkeypatch):
        # Simula ImportError só para o módulo de chart_generator.
        def _import_with_forced_error(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "concilium.application.benchmarks.charts.chart_generator":
                raise ImportError("simulated missing matplotlib stack")
            return _builtin_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr("builtins.__import__", _import_with_forced_error)
        _tentar_gerar_graficos(tmp_path, "SLUG")

    def test_generic_exception_logs_warning_and_swallows(self, tmp_path):
        """Lines 223-224: gerar_graficos_benchmark raising a non-ImportError Exception
        is caught and logged as a warning — packaging proceeds without PNGs."""

        with patch(
            "concilium.application.benchmarks.charts.chart_generator.gerar_graficos_benchmark",
            side_effect=RuntimeError("matplotlib backend crashed"),
        ):
            # Must not raise — best-effort chart generation.
            _tentar_gerar_graficos(tmp_path, "SLUG")


# ===========================================================================



from unittest.mock import MagicMock  # noqa: E402

# ─── output_packager.py line 59 (svg in legacy outputs/) ────────────────────


class TestOutputPackagerSvgFallback:
    def test_collects_svg_from_legacy_outputs_dir(self, tmp_path):
        """Line 59: svg glob in fallback path (no viz_dir, outputs_dir has svgs)."""
        from concilium.application.benchmarks.charts.output_packager import _cf_collect_graficos

        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "chart.svg").write_text("<svg/>")

        collected: list = []
        _cf_collect_graficos(tmp_path, collected)

        arcs = [arc for _, arc in collected]
        assert "graficos/chart.svg" in arcs

    def test_collects_png_and_svg_from_legacy_outputs(self, tmp_path):
        from concilium.application.benchmarks.charts.output_packager import _cf_collect_graficos

        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "a.png").write_bytes(b"\x89PNG")
        (outputs_dir / "b.svg").write_text("<svg/>")

        collected: list = []
        _cf_collect_graficos(tmp_path, collected)

        arcs = [arc for _, arc in collected]
        assert "graficos/a.png" in arcs
        assert "graficos/b.svg" in arcs




# ─── output_packager.py line 217 (_tentar_gerar_graficos success call) ───────


class TestTentarGerarGraficos2:
    def test_calls_gerar_graficos_when_import_succeeds(self, tmp_path):
        """Line 217: gerar_graficos_benchmark is called when outputs/ has no pngs."""
        from concilium.application.benchmarks.charts.output_packager import _tentar_gerar_graficos

        bench_dir = tmp_path / "bench"
        bench_dir.mkdir()

        mock_fn = MagicMock()
        fake_module = MagicMock()
        fake_module.gerar_graficos_benchmark = mock_fn

        with patch.dict(
            "sys.modules",
            {"concilium.application.benchmarks.charts.chart_generator": fake_module},
        ):
            _tentar_gerar_graficos(bench_dir, "TEST")

        mock_fn.assert_called_once_with(bench_dir=bench_dir, slug="TEST")

    def test_skips_call_when_pngs_already_exist(self, tmp_path):
        from concilium.application.benchmarks.charts.output_packager import _tentar_gerar_graficos

        bench_dir = tmp_path / "bench"
        outputs_dir = bench_dir / "outputs"
        outputs_dir.mkdir(parents=True)
        (outputs_dir / "existing.png").write_bytes(b"\x89PNG")

        mock_fn = MagicMock()
        with patch.dict(
            "sys.modules",
            {
                "concilium.application.benchmarks.charts.chart_generator": MagicMock(
                    gerar_graficos_benchmark=mock_fn
                )
            },
        ):
            _tentar_gerar_graficos(bench_dir, "TEST")

        mock_fn.assert_not_called()




# ─── output_packager.py lines 175, 187-190 (empacotar_outputs auto path) ─────


class TestEmpacotar2:
    def test_empacotar_auto_output_path_and_gerar_graficos(self, tmp_path):
        """Lines 175, 187-190: gerar_graficos=True + output_path=None."""
        from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

        # _find_benchmark_dir candidate 1: config_root.parent / benchmarks/data/TST
        bench_dir = tmp_path / "benchmarks" / "data" / "TST"
        reports_dir = bench_dir / "artifacts" / "outputs" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report.md").write_text("# Report")

        config_root = tmp_path / "config.json"

        with patch(
            "concilium.application.benchmarks.charts.output_packager._tentar_gerar_graficos"
        ) as mock_gen:
            result = empacotar_outputs(
                "TST",
                config_root=config_root,
                output_path=None,
                gerar_graficos=True,
            )

        mock_gen.assert_called_once()
        assert result.exists()
        assert result.suffix == ".zip"

    def test_empacotar_with_explicit_output_path(self, tmp_path):
        """Complement: output_path provided → auto-path block skipped."""
        from concilium.application.benchmarks.charts.output_packager import empacotar_outputs

        bench_dir = tmp_path / "benchmarks" / "data" / "EXP"
        reports_dir = bench_dir / "artifacts" / "outputs" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report.md").write_text("# Report")

        explicit_path = tmp_path / "out.zip"
        config_root = tmp_path / "config.json"

        with patch(
            "concilium.application.benchmarks.charts.output_packager._tentar_gerar_graficos"
        ):
            result = empacotar_outputs(
                "EXP",
                config_root=config_root,
                output_path=explicit_path,
                gerar_graficos=True,
            )

        assert result == explicit_path
        assert result.exists()

