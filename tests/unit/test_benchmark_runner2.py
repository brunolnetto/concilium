"""Tests for BenchmarkRunner to boost coverage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def _make_spec(tmp_path, slug="bench-test", nome="Bench Test", contexto_id="ctx"):
    from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

    return ProjectSpec(
        nome=nome,
        slug=slug,
        contexto_id=contexto_id,
        referencia_path=None,
        inputs_escopo=None,
        inputs_01A=None,
        inputs_cronograma=None,
        inputs_indiretos=None,
        extra_inputs={},
    )


def _make_runner(tmp_path):
    from concilium.application.benchmarks.execution.runner import BenchmarkRunner
    from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder
    from concilium.application.benchmarks.report.report_printer import BenchmarkReportPrinter

    return BenchmarkRunner(
        config_root=tmp_path / "config",
        projects_root=tmp_path / "projetos",
        report_builder=MagicMock(spec=BenchmarkReportBuilder),
        report_printer=MagicMock(spec=BenchmarkReportPrinter),
    )


class TestGetOutputSubdir:
    def test_png_goes_to_visualizations(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("chart.png") == "visualizations"

    def test_jpg_goes_to_visualizations(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("photo.jpg") == "visualizations"

    def test_pdf_goes_to_reports(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("report.pdf") == "reports"

    def test_xlsx_goes_to_reports(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("data.xlsx") == "reports"

    def test_json_fallback_to_reports(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("output.json") == "reports"

    def test_svg_goes_to_visualizations(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("graph.svg") == "visualizations"


class TestLoadReferencia:
    def test_returns_none_when_path_is_none(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        result = runner._load_referencia(spec)
        assert result is None

    def test_returns_none_when_path_missing(self, tmp_path):
        from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

        runner = _make_runner(tmp_path)
        spec = ProjectSpec(
            nome="x",
            slug="x",
            contexto_id="ctx",
            referencia_path=tmp_path / "nonexistent.json",
            inputs_escopo=None,
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={},
        )
        result = runner._load_referencia(spec)
        assert result is None

    def test_loads_json_when_file_exists(self, tmp_path):
        from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

        ref_file = tmp_path / "ref.json"
        ref_file.write_text('{"key": "value"}', encoding="utf-8")
        runner = _make_runner(tmp_path)
        spec = ProjectSpec(
            nome="x",
            slug="x",
            contexto_id="ctx",
            referencia_path=ref_file,
            inputs_escopo=None,
            inputs_01A=None,
            inputs_cronograma=None,
            inputs_indiretos=None,
            extra_inputs={},
        )
        result = runner._load_referencia(spec)
        assert result == {"key": "value"}


class TestPrepareInputs:
    def _make_inference_svc_cls(self):
        svc_cls = MagicMock()
        svc_cls.derive.return_value = {}
        svc_cls.apply_to_skill_inputs.side_effect = lambda inputs, pack: inputs
        return svc_cls

    def test_inputs_escopo_added(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        spec.inputs_escopo = {"eap": []}
        svc_cls = self._make_inference_svc_cls()
        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec)
        assert "01-escopo-e-eap" in result
        assert result["01-escopo-e-eap"]["contexto_id"] == spec.contexto_id

    def test_inputs_01A_added(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        spec.inputs_01A = {"catalog": "mendeslobo"}
        svc_cls = self._make_inference_svc_cls()
        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec)
        assert "03-catalogo-de-recursos" in result

    def test_inputs_cronograma_added(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        spec.inputs_cronograma = {"tipo": "semanal"}
        svc_cls = self._make_inference_svc_cls()
        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec)
        assert "04-cronograma" in result

    def test_inputs_indiretos_merged(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        spec.inputs_indiretos = {"bdi": 0.22}
        svc_cls = self._make_inference_svc_cls()
        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec)
        assert result.get("06-resultado-financeiro", {}).get("bdi") == 0.22

    def test_benchmark_mode_always_set(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        svc_cls = self._make_inference_svc_cls()
        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec)
        assert result["06-resultado-financeiro"]["benchmark_mode"] is True

    def test_contexto_id_injected_into_escopo(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path, contexto_id="ctx-123")
        spec.inputs_escopo = {"eap": []}  # non-empty but missing contexto_id
        svc_cls = self._make_inference_svc_cls()
        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec)
        assert result["01-escopo-e-eap"]["contexto_id"] == "ctx-123"


class TestRunShortCircuit:
    def test_run_returns_cached_report_when_exists(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {"data": "canonical"}

        artifacts_dir = runner._artifact_output_dir(spec)
        audit_dir = artifacts_dir.parent / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        cached_report = {"resultado": "ok", "quality_gates": {}}
        report_file = audit_dir / "benchmark_report.json"
        report_file.write_text(json.dumps(cached_report), encoding="utf-8")

        with patch.object(runner, "_find_or_create", return_value=store):
            result = runner.run(spec, reset=False)

        assert result == cached_report


class TestRunSkipArtifacts:
    def test_run_skip_artifacts_writes_report_and_returns(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = None
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = []

        fake_report = {"resultado": "ok", "quality_gates": {}}
        runner.report_builder.build.return_value = fake_report

        inference_pack = {}
        svc_cls = MagicMock()
        svc_cls.derive.return_value = inference_pack
        svc_cls.apply_to_skill_inputs.side_effect = lambda inputs, pack: inputs

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, skip_artifacts=True)

        assert result == fake_report
        artifacts_dir = runner._artifact_output_dir(spec)
        audit_dir = artifacts_dir.parent / "audit"
        assert (audit_dir / "benchmark_report.json").exists()


class TestFindOrCreate:
    def test_creates_new_when_projects_root_missing(self, tmp_path):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        runner = BenchmarkRunner(
            config_root=tmp_path / "config",
            projects_root=tmp_path / "projetos_nonexistent",
            report_builder=MagicMock(),
            report_printer=MagicMock(),
        )
        store_mock = MagicMock()
        with patch(
            "concilium.infrastructure.storage.project.ProjectStore.init",
            return_value=store_mock,
        ):
            result = runner._find_or_create("Test", "bench-slug", "ctx", reset=False)
        assert result is store_mock

    def test_finds_existing_project(self, tmp_path):
        runner = _make_runner(tmp_path)
        projects_root = runner.projects_root
        proj_dir = projects_root / "proj-abc"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text('{"nome": "Bench Test"}', encoding="utf-8")

        with patch(
            "concilium.infrastructure.storage.project.ProjectStore",
        ) as MockPS:
            MockPS.return_value = MagicMock()
            result = runner._find_or_create("Bench Test", "bench-test", "ctx", reset=False)
        assert result is not None

    def test_reset_removes_and_recreates(self, tmp_path):
        runner = _make_runner(tmp_path)
        projects_root = runner.projects_root
        proj_dir = projects_root / "proj-del"
        proj_dir.mkdir(parents=True)
        (proj_dir / "meta.json").write_text('{"nome": "Bench Test"}', encoding="utf-8")
        overrides_dir = proj_dir / "overrides"
        overrides_dir.mkdir()
        (overrides_dir / "cpus_overlay.json").write_bytes(b"{}")

        store_mock = MagicMock()
        with patch(
            "concilium.infrastructure.storage.project.ProjectStore.init",
            return_value=store_mock,
        ):
            result = runner._find_or_create("Bench Test", "bench-test", "ctx", reset=True)
        assert result is store_mock
