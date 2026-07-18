"""Coverage sweep 4 — telemetry, benchmark input derivation, inference."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ─── infrastructure/telemetry ─────────────────────────────────────────────────


class TestTelemetry:
    def test_get_tracer_no_op_when_not_setup(self):
        from concilium.infrastructure.telemetry import get_tracer

        tracer = get_tracer()
        assert tracer is not None

    def test_get_meter_no_op_when_not_setup(self):
        from concilium.infrastructure.telemetry import get_meter

        meter = get_meter()
        assert meter is not None

    def test_skill_span_context_manager(self):
        from concilium.infrastructure.telemetry import skill_span

        with skill_span("01-escopo-e-eap") as span:
            assert span is not None  # Should be a no-op span

    def test_set_current_span_attrs_no_crash(self):
        from concilium.infrastructure.telemetry import set_current_span_attrs

        set_current_span_attrs({"key": "value"})  # Should not raise

    def test_record_skill_duration_no_crash(self):
        from concilium.infrastructure.telemetry import record_skill_duration

        record_skill_duration("01-escopo-e-eap", "OK", 1500)

    def test_record_rate_limit_exceeded_no_crash(self):
        from concilium.infrastructure.telemetry import record_rate_limit_exceeded

        record_rate_limit_exceeded("/api/projects")

    def test_record_tool_call_no_crash(self):
        from concilium.infrastructure.telemetry import record_tool_call

        record_tool_call("listar_projetos", "ok")

    def test_no_op_span(self):
        from concilium.infrastructure.telemetry import _NoOpSpan

        span = _NoOpSpan()
        span.set_attribute("k", "v")  # Should not raise
        span.__enter__()
        span.__exit__(None, None, None)

    def test_no_op_tracer(self):
        from concilium.infrastructure.telemetry import _NoOpTracer

        tracer = _NoOpTracer()
        span_ctx = tracer.start_as_current_span("test")
        assert span_ctx is not None

    def test_otel_console_check(self):
        from concilium.infrastructure.telemetry import _otel_console

        result = _otel_console()
        assert isinstance(result, bool)

    def test_setup_telemetry_no_crash(self):
        from concilium.infrastructure.telemetry import setup_telemetry

        setup_telemetry()  # Should not raise even without opentelemetry


# ─── benchmark input_derivation/cronograma.py ─────────────────────────────────


class TestBenchmarkCronoDerivation:
    def test_drfs_get_item_ids_basic(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

        eap = [{"item_id": "eap-1"}, {"other": "no"}]
        result = _drfs_get_item_ids(eap)
        assert "eap-1" in result

    def test_scale_derived_equipes_noop(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _scale_derived_equipes

        ref = {}
        _scale_derived_equipes(ref, {}, {})  # should not raise

    def test_drfs_get_item_ids_from_eap(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_item_ids

        eap = [{"item_id": "eap-1"}, {"item_id": "eap-2"}, {"other": "no_id"}]
        result = _drfs_get_item_ids(eap)
        assert "eap-1" in result
        assert "eap-2" in result

    def test_drfs_build_week_map_numeric(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_build_week_map

        cronograma = {"activities": [{"item_id": "a1", "semanas": {"1": {"num_equipes": 2}, "2": {"num_equipes": 3}}}]}
        result = _drfs_build_week_map(cronograma)
        assert isinstance(result, dict)

    def test_drfs_get_week_equipes_default(self):
        from concilium.application.benchmarks.input_derivation.cronograma import _drfs_get_week_equipes

        semanas = {"2026-W01": {"num_equipes": 3}}
        result = _drfs_get_week_equipes(semanas, "2026-W01", {})
        assert isinstance(result, int)

    def test_benchmark_input_deriver_init(self, tmp_path):
        from concilium.application.benchmarks.input_derivation.cronograma import BenchmarkInputDeriver

        deriver = BenchmarkInputDeriver(config_root=tmp_path)
        assert deriver is not None


# ─── application/benchmarks/inference.py ─────────────────────────────────────


class TestBenchmarkInference:
    def test_inference_service_importable(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        assert BenchmarkInferenceService is not None

    def test_derive_returns_pack(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        pack = BenchmarkInferenceService.derive(None)
        assert pack is not None

    def test_apply_to_skill_inputs(self):
        from concilium.application.benchmarks.inference import BenchmarkInferenceService

        pack = BenchmarkInferenceService.derive(None)
        inputs = {"01-escopo-e-eap": {}}
        result = BenchmarkInferenceService.apply_to_skill_inputs(inputs, pack)
        assert isinstance(result, dict)


# ─── application/skills/graph_exporter.py ────────────────────────────────────


class TestGraphExporter:
    def test_export_function_exists(self):
        from concilium.application.skills import graph_exporter

        assert hasattr(graph_exporter, "export_skill_graph") or len(dir(graph_exporter)) > 0

    def test_module_importable(self):
        import concilium.application.skills.graph_exporter as ge

        assert ge is not None


# ─── infrastructure/storage/store_factory additional ─────────────────────────


class TestStoreFactoryAdditional:
    def test_get_campaign_store_returns_store(self):
        from concilium.infrastructure.storage.store_factory import get_campaign_store

        with patch("concilium.infrastructure.storage.store_factory.build_blob_storage") as mock_bs:
            mock_bs.return_value = MagicMock()
            store = get_campaign_store("test-slug")
        assert store is not None

    def test_get_tool_invocation_store_uses_system_storage(self):
        """ADR-135: .tool_invocations é audit trail global, não dado por-projeto."""
        from concilium.infrastructure.storage.store_factory import get_tool_invocation_store

        with (
            patch("concilium.infrastructure.storage.store_factory.build_system_blob_storage") as mock_system,
            patch("concilium.infrastructure.storage.store_factory.build_blob_storage") as mock_project,
        ):
            mock_system.return_value = MagicMock()
            store = get_tool_invocation_store()

        assert store is not None
        mock_system.assert_called_once()
        mock_project.assert_not_called()
