"""Tests for BenchmarkRunner to boost coverage."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

# Força o import real de `procurement` antes de qualquer patch de
# `phase_classifier.get_pipeline_profile_for_intent` nos testes abaixo.
# `procurement.py` faz `from ...phase_classifier import get_pipeline_profile_
# for_intent` (name-import por valor, não por referência) — se essa primeira
# importação ocorrer enquanto o patch estiver ativo (runner.py importa
# `procurement` lazily, dentro de `_resolve_procurement_profile`, chamado por
# `runner.run()` dentro do `with patch(...)` de alguns testes abaixo),
# `procurement.get_pipeline_profile_for_intent` fica permanentemente vinculado
# ao MagicMock — o `patch()` só restaura o atributo em `phase_classifier`, não
# essa cópia em `procurement`. Sintoma: KeyError com um MagicMock em
# test_adr115_procurement_rfx.py, só na suíte completa (nunca isolado).
import concilium.domain.models.procurement  # noqa: F401


def _make_spec(tmp_path, slug="bench-test", nome="Bench Test", contexto_id="ctx", referencia_path=None):
    from concilium.application.benchmarks.spec.spec_loader import ProjectSpec

    return ProjectSpec(
        nome=nome,
        slug=slug,
        contexto_id=contexto_id,
        referencia_path=referencia_path,
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


def _make_svc_cls():
    svc_cls = MagicMock()
    svc_cls.derive.return_value = {}
    svc_cls.apply_to_skill_inputs.side_effect = lambda inputs, pack: inputs
    return svc_cls


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
        result = runner._find_or_create("Test", "bench-slug", "ctx", reset=False)
        assert result.meta["nome"] == "Test"
        assert result.meta["id"] == "bench-slug"

    def test_finds_existing_project(self, tmp_path):
        runner = _make_runner(tmp_path)
        # Cria via a mesma abstração que _find_or_create usa (project_id determinístico
        # = benchmark_id), depois chama de novo e espera reuso, não recriação.
        repo = runner._benchmark_repository()
        repo.create_project("Bench Test", "ctx", project_id="bench-test")

        result = runner._find_or_create("Bench Test", "bench-test", "ctx", reset=False)
        assert result.meta["nome"] == "Bench Test"
        assert result.meta["id"] == "bench-test"

    def test_reset_removes_and_recreates(self, tmp_path):
        runner = _make_runner(tmp_path)
        repo = runner._benchmark_repository()
        handle = repo.create_project("Bench Test", "ctx", project_id="bench-test")
        handle.write_bytes("overrides/cpus_overlay.json", b"{}")

        result = runner._find_or_create("Bench Test", "bench-test", "ctx", reset=True)
        assert result.meta["nome"] == "Bench Test"
        # overrides preservados através do reset
        assert result.read_bytes("overrides/cpus_overlay.json") == b"{}"


from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

# _load_inference_service RuntimeError (linha 26)
# ─────────────────────────────────────────────────────────────────────────────


class TestLoadInferenceService:
    def test_raises_when_class_missing(self):
        import importlib

        from concilium.application.benchmarks.execution.runner import _load_inference_service

        fake_mod = MagicMock()
        fake_mod.BenchmarkInferenceService = None  # classe ausente

        with patch.object(importlib, "import_module", return_value=fake_mod):
            with pytest.raises(RuntimeError, match="BenchmarkInferenceService indisponivel"):
                _load_inference_service()

    def test_returns_class_when_present(self):
        from concilium.application.benchmarks.execution.runner import _load_inference_service

        svc_cls = _load_inference_service()
        assert svc_cls is not None


# ─────────────────────────────────────────────────────────────────────────────
# from_settings classmethod (linhas 48-53)
# ─────────────────────────────────────────────────────────────────────────────


class TestFromSettings:
    def test_from_settings_uses_storage_config(self, tmp_path):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        storage = MagicMock()
        storage.config_root = tmp_path / "config"
        storage.benchmark_projects_root = tmp_path / "bench"
        storage.root = tmp_path

        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            runner = BenchmarkRunner.from_settings()

        assert runner.config_root == tmp_path / "config"
        assert runner.projects_root == tmp_path / "bench"

    def test_from_settings_derives_projects_root_when_none(self, tmp_path):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        storage = MagicMock()
        storage.config_root = tmp_path / "config"
        storage.benchmark_projects_root = None  # não configurado
        storage.root = tmp_path

        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            runner = BenchmarkRunner.from_settings()

        assert runner.projects_root == tmp_path / "benchmarks" / "projetos"

    def test_from_settings_uses_provided_builders(self, tmp_path):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner
        from concilium.application.benchmarks.report.report_builder import BenchmarkReportBuilder
        from concilium.application.benchmarks.report.report_printer import BenchmarkReportPrinter

        storage = MagicMock()
        storage.config_root = tmp_path / "config"
        storage.benchmark_projects_root = tmp_path / "bench"
        storage.root = tmp_path

        custom_builder = MagicMock(spec=BenchmarkReportBuilder)
        custom_printer = MagicMock(spec=BenchmarkReportPrinter)

        with patch("concilium.infrastructure.settings.get_storage", return_value=storage):
            runner = BenchmarkRunner.from_settings(
                report_builder=custom_builder,
                report_printer=custom_printer,
            )

        assert runner.report_builder is custom_builder
        assert runner.report_printer is custom_printer


# ─────────────────────────────────────────────────────────────────────────────
# procurement_intent branch (linhas 108-121) + rfx metadata (142-143)
# ─────────────────────────────────────────────────────────────────────────────


class TestRunProcurementIntent:
    def _setup_run_mocks(self, runner, store, fake_report):
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        ctx = patch.multiple(
            "concilium.application.benchmarks.execution.runner",
            Runtime=MagicMock(**{"return_value.run_pipeline.return_value": []}),
            _load_inference_service=MagicMock(return_value=svc_cls),
        )
        return ctx

    def test_procurement_intent_rfi_populates_rfx_in_report(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = None
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = []

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        fake_profile = MagicMock()
        fake_profile.mode = PipelineMode.OLTP
        fake_profile.skill_sequence = []
        fake_profile.intent.value = "rfi"
        fake_profile.path_name = "rfi-path"
        fake_profile.deliverables = []

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch(
                "concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                return_value=fake_profile,
            ),
            patch("concilium.domain.models.procurement.validate_procurement_baseline"),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, procurement_intent="rfi")

        assert "rfx" in result
        assert result["rfx"]["intent"] == "rfi"
        assert result["rfx"]["path_name"] == "rfi-path"
        assert result["rfx"]["pipeline_mode"] == PipelineMode.OLTP.value

    def test_procurement_intent_with_referencia_path(self, tmp_path):
        """Quando spec.referencia_path existe, _baseline_ref = str(referencia_path) (linha 116)."""
        ref_file = tmp_path / "ref.json"
        ref_file.write_text('{"planejamento": []}', encoding="utf-8")

        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path, referencia_path=ref_file)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = None
        store.list_output_files.return_value = []

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        fake_profile = MagicMock()
        fake_profile.mode = PipelineMode.OLTP
        fake_profile.skill_sequence = []
        fake_profile.intent.value = "rfp"
        fake_profile.path_name = "rfp-path"
        fake_profile.deliverables = []

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch(
                "concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                return_value=fake_profile,
            ),
            patch("concilium.domain.models.procurement.validate_procurement_baseline") as mock_validate,
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            runner.run(spec, procurement_intent="rfp")

        # baseline deve ser o path da referência, não a versão do store
        call_args = mock_validate.call_args
        assert str(ref_file) in str(call_args)

    def test_procurement_intent_fallback_to_store_version_when_no_ref(self, tmp_path):
        """Sem referencia_path, _baseline_ref = store.current_version() (linha 118)."""
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)  # referencia_path=None

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = []

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        fake_profile = MagicMock()
        fake_profile.mode = PipelineMode.OLTP
        fake_profile.skill_sequence = []
        fake_profile.intent.value = "rfi"
        fake_profile.path_name = "rfi-path"
        fake_profile.deliverables = []

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch(
                "concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                return_value=fake_profile,
            ),
            patch("concilium.domain.models.procurement.validate_procurement_baseline") as mock_validate,
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            runner.run(spec, procurement_intent="rfi")

        call_args = mock_validate.call_args
        assert "v1" in str(call_args)


# ─────────────────────────────────────────────────────────────────────────────
# OLTP mode com profile: materializa entregáveis (linhas 166-180)
# ─────────────────────────────────────────────────────────────────────────────


class TestRunOltpWithProfileDeliverables:
    def test_deliverable_files_are_written_when_in_profile(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = ["relatorio.json", "relatorio.pdf"]
        store.load_output_file.side_effect = lambda v, fname: b'{"ok": true}' if fname == "relatorio.json" else b"%PDF"

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        fake_profile = MagicMock()
        fake_profile.mode = PipelineMode.OLTP
        fake_profile.skill_sequence = []
        fake_profile.intent.value = "rfi"
        fake_profile.path_name = "rfi-path"
        fake_profile.deliverables = ["relatorio.json"]  # só relatorio.json declarado

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch(
                "concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                return_value=fake_profile,
            ),
            patch("concilium.domain.models.procurement.validate_procurement_baseline"),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            runner.run(spec, procurement_intent="rfi")

        artifacts_dir = runner._artifact_output_dir(spec)
        audit_dir = artifacts_dir.parent / "audit"
        assert (audit_dir / "benchmark_report.json").exists()
        # relatorio.json deve ter sido materializado
        report_subdir = artifacts_dir / runner._get_output_subdir("relatorio.json")
        assert (report_subdir / "relatorio.json").exists()
        # relatorio.pdf NÃO está em deliverables → não deve existir
        pdf_subdir = artifacts_dir / runner._get_output_subdir("relatorio.pdf")
        assert not (pdf_subdir / "relatorio.pdf").exists()

    def test_deliverable_with_none_data_is_skipped(self, tmp_path):
        """Quando load_output_file retorna None, o arquivo é ignorado (linha 172-173)."""
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = ["relatorio.pdf"]
        store.load_output_file.return_value = None  # sem dados

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        fake_profile = MagicMock()
        fake_profile.mode = PipelineMode.OLTP
        fake_profile.skill_sequence = []
        fake_profile.intent.value = "rfi"
        fake_profile.path_name = "rfi-path"
        fake_profile.deliverables = ["relatorio.pdf"]

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch(
                "concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                return_value=fake_profile,
            ),
            patch("concilium.domain.models.procurement.validate_procurement_baseline"),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, procurement_intent="rfi")

        assert result == fake_report


# ─────────────────────────────────────────────────────────────────────────────
# OLAP mode: copia artefatos (linhas 184-222)
# ─────────────────────────────────────────────────────────────────────────────


class TestRunOlapArtifacts:
    def test_olap_mode_copies_png_to_visualizations(self, tmp_path, capsys):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        # simula PNG e relatorio.json
        store.list_output_files.return_value = ["chart.png", "relatorio.json"]
        store.load_output_file.side_effect = lambda v, fname: b"PNG_DATA" if fname == "chart.png" else b'{"r": 1}'

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_skills_for_mode", return_value=[]),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, mode=PipelineMode.OLAP)

        artifacts_dir = runner._artifact_output_dir(spec)
        vis_dir = artifacts_dir / "visualizations"
        rep_dir = artifacts_dir / "reports"
        assert (vis_dir / "chart.png").exists()
        assert (rep_dir / "relatorio.json").exists()
        assert result == fake_report

        captured = capsys.readouterr()
        assert "[SAVE]" in captured.out

    def test_olap_mode_skips_irrelevant_filename(self, tmp_path):
        """Line 226->225: fname que não termina em .png, não começa com resultado_planejamento
        e não está em keep_names é ignorado (não copiado, não passa por load_output_file)."""
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = ["irrelevante.txt", "chart.png"]
        store.load_output_file.side_effect = lambda v, fname: b"PNG_DATA" if fname == "chart.png" else b"IGNORED"

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_skills_for_mode", return_value=[]),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            runner.run(spec, mode=PipelineMode.OLAP)

        artifacts_dir = runner._artifact_output_dir(spec)
        assert not (artifacts_dir / "reports" / "irrelevante.txt").exists()
        assert (artifacts_dir / "visualizations" / "chart.png").exists()

    def test_olap_mode_skips_none_data(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = ["chart.png"]
        store.load_output_file.return_value = None  # sem dados

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_skills_for_mode", return_value=[]),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            runner.run(spec, mode=PipelineMode.OLAP)

        artifacts_dir = runner._artifact_output_dir(spec)
        assert not (artifacts_dir / "visualizations" / "chart.png").exists()

    def test_olap_mode_permission_error_prints_warn(self, tmp_path, capsys):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = ["chart.png"]
        store.load_output_file.return_value = b"PNG"

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_skills_for_mode", return_value=[]),
            patch("pathlib.Path.write_bytes", side_effect=PermissionError("locked")),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            runner.run(spec, mode=PipelineMode.OLAP)

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out


class TestRunOltpProfilePermissionError:
    """Linha 179-180: PermissionError ao materializar entregável no modo OLTP+profile."""

    def test_permission_error_on_deliverable_write_prints_warn(self, tmp_path, capsys):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        store = MagicMock()
        store.current_version.return_value = "v1"
        store.load_canonical.return_value = {}
        store.list_output_files.return_value = ["relatorio.json"]
        store.load_output_file.return_value = b'{"data": 1}'

        fake_report = {"quality_gates": {}}
        svc_cls = _make_svc_cls()
        runner.report_builder.build.return_value = fake_report

        from concilium.application.skills.phase_classifier import PipelineMode

        fake_profile = MagicMock()
        fake_profile.mode = PipelineMode.OLTP
        fake_profile.skill_sequence = []
        fake_profile.intent.value = "rfi"
        fake_profile.path_name = "rfi-path"
        fake_profile.deliverables = ["relatorio.json"]

        with (
            patch.object(runner, "_find_or_create", return_value=store),
            patch.object(runner, "_load_referencia", return_value=None),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch(
                "concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                return_value=fake_profile,
            ),
            patch("concilium.domain.models.procurement.validate_procurement_baseline"),
            # patch write_bytes directly on Path objects created at runtime
            patch("pathlib.Path.write_bytes", side_effect=PermissionError("arquivo em uso")),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            runner.run(spec, procurement_intent="rfi")

        captured = capsys.readouterr()
        # The audit_dir write_text succeeds (write_text != write_bytes);
        # the deliverable write_bytes raises PermissionError → [WARN]
        assert "[WARN]" in captured.out


# ─────────────────────────────────────────────────────────────────────────────
# _prepare_inputs: planejamento_ref injetado (linha 379)
# ─────────────────────────────────────────────────────────────────────────────


class TestPrepareInputsPlanejamentoRef:
    def test_planejamento_ref_injected_when_ref_has_planejamento_list(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        ref = {
            "planejamento": [{"etapa": "Infraestrutura", "valor": 100_000.0}],
        }
        svc_cls = _make_svc_cls()

        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec, ref=ref)

        skill_05 = result.get("05-equipes-e-alocacao", {})
        assert "planejamento_ref" in skill_05
        assert skill_05["planejamento_ref"] == ref["planejamento"]

    def test_planejamento_ref_not_injected_when_ref_planejamento_not_list(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)

        ref = {"planejamento": "string-nao-lista"}  # não é lista
        svc_cls = _make_svc_cls()

        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec, ref=ref)

        skill_05 = result.get("05-equipes-e-alocacao", {})
        assert "planejamento_ref" not in skill_05

    def test_planejamento_ref_not_injected_when_ref_is_none(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        svc_cls = _make_svc_cls()

        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec, ref=None)

        skill_05 = result.get("05-equipes-e-alocacao", {})
        assert "planejamento_ref" not in skill_05

    def test_contexto_id_not_overwritten_when_already_present(self, tmp_path):
        """Line 319 False branch: contexto_id já presente em inputs_escopo não é sobrescrito."""
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        spec.inputs_escopo = {"contexto_id": "ja-existente", "foo": "bar"}
        svc_cls = _make_svc_cls()

        with patch(
            "concilium.application.benchmarks.execution.runner._load_inference_service",
            return_value=svc_cls,
        ):
            result = runner._prepare_inputs(spec, ref=None)

        assert result["01-escopo-e-eap"]["contexto_id"] == "ja-existente"
        assert result["00-escopo"] == result["01-escopo-e-eap"]


# ─────────────────────────────────────────────────────────────────────────────
# _emit_business_telemetry: margem presente aciona record_project_margin (linha 34)
# ─────────────────────────────────────────────────────────────────────────────


class TestEmitBusinessTelemetry:
    def test_margem_presente_chama_record_project_margin(self):
        from concilium.application.benchmarks.execution.runner import _emit_business_telemetry

        spec = MagicMock()
        spec.benchmark_id = "bench-1"
        spec.project_slug = "slug-1"
        report = {"resultado": {"ferramenta": {"margem_pct": 12.5, "custo_direto": 100000.0}}}
        mode = MagicMock()
        mode.value = "oltp"

        with patch("concilium.infrastructure.telemetry.record_project_margin") as mock_record:
            _emit_business_telemetry(spec, report, mode)

        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert kwargs["project_id"] == "bench-1"
        assert kwargs["margem_pct"] == 12.5
        assert kwargs["custo_direto"] == 100000.0
        assert kwargs["pipeline_mode"] == "oltp"

    def test_margem_ausente_nao_chama_record(self):
        from concilium.application.benchmarks.execution.runner import _emit_business_telemetry

        spec = MagicMock()
        report = {"resultado": {"ferramenta": {}}}
        mode = "oltp"

        with patch("concilium.infrastructure.telemetry.record_project_margin") as mock_record:
            _emit_business_telemetry(spec, report, mode)

        mock_record.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# _find_or_create: nenhum projeto existente casa com "nome" -> cria novo (linha 269->297)
# ─────────────────────────────────────────────────────────────────────────────


class TestFindOrCreateNoMatchCreatesNew:
    def test_creates_new_when_existing_projects_dont_match_nome(self, tmp_path, capsys):
        runner = _make_runner(tmp_path)
        # Projeto existente sob um benchmark_id DIFERENTE — get_project("novo-slug")
        # não o encontra (project_id é determinístico = benchmark_id).
        repo = runner._benchmark_repository()
        repo.create_project("Outro Projeto", "ctx", project_id="outro-projeto")

        result = runner._find_or_create("Projeto Novo", "novo-slug", "ctx", reset=False)

        assert result.meta["nome"] == "Projeto Novo"
        assert result.meta["id"] == "novo-slug"
        captured = capsys.readouterr()
        assert "[NEW]" in captured.out


# ─── BenchmarkRunner helpers ──────────────────────────────────────────────────


class TestBenchmarkRunner:
    def test_from_settings_constructs(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        with patch("concilium.infrastructure.settings.get_storage") as mock_gs:
            mock_storage = MagicMock()
            mock_storage.config_root = Path("/fake/config")
            mock_storage.benchmark_projects_root = None
            mock_storage.root = Path("/fake")
            mock_gs.return_value = mock_storage
            runner = BenchmarkRunner.from_settings()
        assert runner.config_root == Path("/fake/config")

    def test_get_output_subdir_images(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("chart.png") == "visualizations"
        assert BenchmarkRunner._get_output_subdir("chart.jpg") == "visualizations"

    def test_get_output_subdir_reports(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("report.pdf") == "reports"
        assert BenchmarkRunner._get_output_subdir("data.xlsx") == "reports"
        assert BenchmarkRunner._get_output_subdir("relatorio.json") == "reports"

    def test_get_output_subdir_unknown(self):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        assert BenchmarkRunner._get_output_subdir("file.xyz") == "reports"

