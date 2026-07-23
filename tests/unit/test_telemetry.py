"""Coverage sweep 4 — telemetry, benchmark input derivation, inference."""

from __future__ import annotations

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



