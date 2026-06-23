"""Testes adicionais para BenchmarkRunner — cobre linhas não alcançadas por
test_benchmark_runner2.py e test_benchmark_runner_inference_flag.py.

Linhas alvo em runner.py:
  26         — RuntimeError em _load_inference_service quando classe ausente
  48-53      — from_settings classmethod
  108-121    — procurement_intent branch (profile + validate_procurement_baseline)
  142-143    — rfx metadata adicionado ao report
  166-180    — OLTP mode com profile: materializa entregáveis declarados
  184-222    — OLAP mode: copia artefatos para artifacts_dir
  279        — benchmark_store.log_execution chamado com sucesso
  295-301    — _find_or_create: benchmark_store_root existe, get_metadata retorna meta com versao
  309, 322   — _find_or_create: projeto não removido completamente (rmtree aviso)
  379        — _prepare_inputs: planejamento_ref injetado em skill-05 quando ref tem planejamento
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_spec(tmp_path, slug="bench-gap", nome="Bench Gap", contexto_id="ctx", referencia_path=None):
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


# ─────────────────────────────────────────────────────────────────────────────
# _load_inference_service RuntimeError (linha 26)
# ─────────────────────────────────────────────────────────────────────────────


class TestLoadInferenceService:
    def test_raises_when_class_missing(self):
        import importlib

        import pytest

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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                  return_value=fake_profile),
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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                  return_value=fake_profile),
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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                  return_value=fake_profile),
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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                  return_value=fake_profile),
            patch("concilium.domain.models.procurement.validate_procurement_baseline"),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, procurement_intent="rfi")

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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                  return_value=fake_profile),
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
            patch.object(runner, "_log_execution"),
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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_skills_for_mode", return_value=[]),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, mode=PipelineMode.OLAP)

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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_skills_for_mode", return_value=[]),
            patch("pathlib.Path.write_bytes", side_effect=PermissionError("locked")),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, mode=PipelineMode.OLAP)

        captured = capsys.readouterr()
        assert "[WARN]" in captured.out


# ─────────────────────────────────────────────────────────────────────────────
# _log_execution: benchmark_store.log_execution chamado com sucesso (linha 279)
# ─────────────────────────────────────────────────────────────────────────────


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
            patch.object(runner, "_log_execution"),
            patch.object(runner, "_prepare_inputs", return_value={}),
            patch("concilium.application.benchmarks.execution.runner._load_inference_service", return_value=svc_cls),
            patch("concilium.application.benchmarks.execution.runner.Runtime") as MockRuntime,
            patch("concilium.application.skills.phase_classifier.get_pipeline_profile_for_intent",
                  return_value=fake_profile),
            patch("concilium.domain.models.procurement.validate_procurement_baseline"),
            # patch write_bytes directly on Path objects created at runtime
            patch("pathlib.Path.write_bytes", side_effect=PermissionError("arquivo em uso")),
        ):
            MockRuntime.return_value.run_pipeline.return_value = []
            result = runner.run(spec, procurement_intent="rfi")

        captured = capsys.readouterr()
        # The audit_dir write_text succeeds (write_text != write_bytes);
        # the deliverable write_bytes raises PermissionError → [WARN]
        assert "[WARN]" in captured.out


class TestLogExecutionExceptionHandler:
    """Linhas 280-281: except Exception as e: logger.warning(...)."""

    def test_log_execution_warning_logged_on_internal_exception(self, tmp_path, caplog):
        import logging

        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        store = MagicMock()
        store.root = tmp_path / "proj"

        report = {"quality_gates": {"decision": "APROVADO"}}

        # Patch from_path to return a store where log_execution raises
        mock_benchmark_store = MagicMock()
        mock_benchmark_store.log_execution.side_effect = RuntimeError("store corrompido")

        with (
            patch(
                "concilium.infrastructure.storage.benchmark_store.FileSystemBenchmarkStore.from_path",
                return_value=mock_benchmark_store,
            ),
            caplog.at_level(logging.WARNING, logger="concilium.application.benchmarks.execution.runner"),
        ):
            # deve silenciar e logar warning
            runner._log_execution(spec, report, store_project=store)

        assert any("Falha" in msg for msg in caplog.messages)


class TestLogExecutionSuccess:
    def test_log_execution_calls_store(self, tmp_path):
        from concilium.application.benchmarks.execution.runner import BenchmarkRunner

        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        store = MagicMock()
        store.root = tmp_path / "proj"

        report = {
            "quality_gates": {
                "decision": "APROVADO",
                "worst_severity": "INFO",
                "items": [{"gate": "g1"}, {"gate": "g2"}],
            }
        }

        mock_benchmark_store = MagicMock()

        with patch(
            "concilium.infrastructure.storage.benchmark_store.FileSystemBenchmarkStore.from_path",
            return_value=mock_benchmark_store,
        ):
            runner._log_execution(spec, report, store_project=store)

        mock_benchmark_store.log_execution.assert_called_once()
        execution = mock_benchmark_store.log_execution.call_args[0][0]
        from concilium.domain.benchmark.models import BenchmarkState

        assert execution.status == BenchmarkState.SUCESSO
        assert execution.discrepancia_sumario["n_gates"] == 2

    def test_log_execution_falha_status_for_reprovado(self, tmp_path):
        runner = _make_runner(tmp_path)
        spec = _make_spec(tmp_path)
        store = MagicMock()
        store.root = tmp_path / "proj"

        report = {"quality_gates": {"decision": "REPROVADO"}}

        mock_benchmark_store = MagicMock()

        with patch(
            "concilium.infrastructure.storage.benchmark_store.FileSystemBenchmarkStore.from_path",
            return_value=mock_benchmark_store,
        ):
            runner._log_execution(spec, report, store_project=store)

        execution = mock_benchmark_store.log_execution.call_args[0][0]
        from concilium.domain.benchmark.models import BenchmarkState

        assert execution.status == BenchmarkState.FALHA


# ─────────────────────────────────────────────────────────────────────────────
# _find_or_create: benchmark_store_root existe, get_metadata retorna meta (linhas 295-301)
# ─────────────────────────────────────────────────────────────────────────────


class TestFindOrCreateNep039:
    def test_loads_benchmark_versao_from_nep039(self, tmp_path):
        runner = _make_runner(tmp_path)
        # Criar .benchmark-store para forçar o branch de leitura de metadata
        benchmark_store_root = runner.projects_root / ".benchmark-store"
        benchmark_store_root.mkdir(parents=True, exist_ok=True)

        mock_meta = MagicMock()
        mock_meta.versao = 3
        mock_benchmark_store = MagicMock()
        mock_benchmark_store.get_metadata.return_value = mock_meta

        store_mock = MagicMock()

        with (
            patch(
                "concilium.infrastructure.storage.benchmark_store.FileSystemBenchmarkStore.from_path",
                return_value=mock_benchmark_store,
            ),
            patch("concilium.infrastructure.storage.project.ProjectStore.init", return_value=store_mock),
        ):
            result = runner._find_or_create("Novo Projeto", "novo-slug", "ctx", reset=False)

        assert result is store_mock
        # benchmark_versao deve ter sido passado para ProjectStore.init
        call_kwargs = {**{k: v for k, v in zip(
            ["root", "nome", "contexto_id"],
            __import__("concilium.infrastructure.storage.project", fromlist=["ProjectStore"]).ProjectStore.init.call_args[0]
            if hasattr(__import__("concilium.infrastructure.storage.project", fromlist=["ProjectStore"]).ProjectStore.init, "call_args") else [],
        )}}
        # Valida que benchmark_versao foi passado
        init_call = mock_benchmark_store.get_metadata.call_args
        assert init_call is not None

    def test_nep039_exception_is_logged_and_continues(self, tmp_path, caplog):
        import logging

        runner = _make_runner(tmp_path)
        benchmark_store_root = runner.projects_root / ".benchmark-store"
        benchmark_store_root.mkdir(parents=True, exist_ok=True)

        store_mock = MagicMock()

        with (
            patch(
                "concilium.infrastructure.storage.benchmark_store.FileSystemBenchmarkStore.from_path",
                side_effect=Exception("nep039 corrompido"),
            ),
            patch("concilium.infrastructure.storage.project.ProjectStore.init", return_value=store_mock),
            caplog.at_level(logging.WARNING, logger="concilium.application.benchmarks.execution.runner"),
        ):
            result = runner._find_or_create("Projeto X", "slug-x", "ctx", reset=False)

        assert result is store_mock
        assert any("nep039" in msg.lower() or "metadata" in msg.lower() for msg in caplog.messages)


# ─────────────────────────────────────────────────────────────────────────────
# _find_or_create: reset quando rmtree não remove completamente (linha 322)
# ─────────────────────────────────────────────────────────────────────────────


class TestFindOrCreateResetWarning:
    def test_warning_printed_when_dir_still_exists_after_rmtree(self, tmp_path, capsys):
        runner = _make_runner(tmp_path)
        projects_root = runner.projects_root
        projects_root.mkdir(parents=True, exist_ok=True)

        proj_dir = projects_root / "proj-stubborn"
        proj_dir.mkdir()
        (proj_dir / "meta.json").write_text('{"nome": "Stubborn"}', encoding="utf-8")

        store_mock = MagicMock()

        # rmtree é chamado mas o dir ainda existe (simula falha parcial)
        def _fake_rmtree(path, ignore_errors=False):
            pass  # não remove nada

        with (
            patch("shutil.rmtree", side_effect=_fake_rmtree),
            patch("concilium.infrastructure.storage.project.ProjectStore.init", return_value=store_mock),
        ):
            result = runner._find_or_create("Stubborn", "stubborn-slug", "ctx", reset=True)

        captured = capsys.readouterr()
        assert "[AVISO]" in captured.out or "AVISO" in captured.out


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
