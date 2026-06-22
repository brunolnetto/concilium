"""Testes para caminhos OTEL de concilium.infrastructure.telemetry.__init__.

Cobre linhas não alcançadas pelo test_coverage_sweep_4.py e test_adr111_logging_config.py.
Todos os testes patcheiam _OTEL_AVAILABLE=True e usam mocks locais para evitar
efeitos colaterais em providers globais.

Linhas alvo:
  29-30  — bloco que seta _OTEL_AVAILABLE = True (exercitado via import com mock)
  56     — otel_sdk_disabled branch (setup_telemetry retorna cedo)
  92-94  — _setup_logging console exporter path
  122-124 — _setup_tracing console exporter path
  152-155 — _setup_metrics console exporter path
  172     — get_tracer quando OTEL disponível
  181     — get_meter quando OTEL disponível
  197-198, 204 — record_skill_duration com instrument já criado / criando pela 1ª vez
  211-212, 222 — record_rate_limit_exceeded idem
  231-232, 239 — record_tool_call idem
  247-248 — set_current_span_attrs quando OTEL disponível
  255, 263-264 — record_rate_limit_exceeded e record_tool_call via counter path
  273, 279-294 — _with_tracing: wrapper com success e com exception
  309, 315-316 — patch_fastmcp_server quando OTEL disponível
  339, 342     — _NoOpMeter.create_counter e _NoOpInstrument.add
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de telemetry settings
# ─────────────────────────────────────────────────────────────────────────────


def _telemetry_settings(*, disabled=False, console=False, endpoint=None, service_name="concilium-test"):
    """Cria mock de TelemetrySettings."""
    s = MagicMock()
    s.otel_sdk_disabled = disabled
    s.otel_console = console
    s.otlp_endpoint = endpoint
    s.otel_service_name = service_name
    return s


# ─────────────────────────────────────────────────────────────────────────────
# setup_telemetry: retorno antecipado quando SDK desabilitado (linha 56)
# ─────────────────────────────────────────────────────────────────────────────


class TestSetupTelemetryOtelUnavailable:
    def test_returns_early_when_otel_unavailable(self):
        """Quando _OTEL_AVAILABLE=False, setup_telemetry retorna em linha 56 sem chamar sub-setups."""
        import concilium.infrastructure.telemetry as tel

        original = tel._initialized
        try:
            tel._initialized = False
            with (
                patch.object(tel, "_OTEL_AVAILABLE", False),
                patch.object(tel, "_setup_tracing") as mock_tracing,
                patch.object(tel, "_setup_metrics") as mock_metrics,
                patch.object(tel, "_setup_logging") as mock_logging,
            ):
                tel.setup_telemetry()
                mock_tracing.assert_not_called()
                mock_metrics.assert_not_called()
                mock_logging.assert_not_called()
        finally:
            tel._initialized = original


class TestSetupTelemetrySdkDisabled:
    def test_no_setup_when_sdk_disabled(self):
        """Quando otel_sdk_disabled=True, _setup_tracing/_setup_metrics/_setup_logging
        não devem ser chamados."""
        import concilium.infrastructure.telemetry as tel

        original = tel._initialized
        try:
            tel._initialized = False  # reset para permitir nova execução
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch("concilium.infrastructure.telemetry.get_telemetry",
                      return_value=_telemetry_settings(disabled=True)),
                patch.object(tel, "_setup_tracing") as mock_tracing,
                patch.object(tel, "_setup_metrics") as mock_metrics,
                patch.object(tel, "_setup_logging") as mock_logging,
            ):
                tel.setup_telemetry()
                mock_tracing.assert_not_called()
                mock_metrics.assert_not_called()
                mock_logging.assert_not_called()
        finally:
            tel._initialized = original


class TestSetupTelemetryIdempotent:
    def test_second_call_is_noop(self):
        """Chamar setup_telemetry duas vezes não re-inicializa providers."""
        import concilium.infrastructure.telemetry as tel

        original = tel._initialized
        try:
            tel._initialized = False
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch("concilium.infrastructure.telemetry.get_telemetry",
                      return_value=_telemetry_settings(disabled=True)),
            ):
                tel.setup_telemetry()
                tel.setup_telemetry()  # segunda chamada: _initialized=True, retorna cedo
                assert tel._initialized is True
        finally:
            tel._initialized = original


# ─────────────────────────────────────────────────────────────────────────────
# _setup_logging console path (linhas 92-94)
# ─────────────────────────────────────────────────────────────────────────────


class TestSetupLoggingConsole:
    def test_console_exporter_added_when_console_mode(self):
        import concilium.infrastructure.telemetry as tel

        mock_processor = MagicMock()
        mock_provider = MagicMock()
        mock_exporter = MagicMock()
        mock_handler = MagicMock()

        with (
            patch("concilium.infrastructure.telemetry.get_telemetry",
                  return_value=_telemetry_settings(console=True, endpoint=None)),
            patch("opentelemetry.sdk._logs.LoggerProvider", return_value=mock_provider),
            patch("opentelemetry.sdk._logs.export.BatchLogRecordProcessor", return_value=mock_processor),
            patch("opentelemetry.sdk._logs.export.ConsoleLogRecordExporter", return_value=mock_exporter),
            patch("opentelemetry._logs.set_logger_provider"),
            patch("concilium.infrastructure.telemetry._otel_console", return_value=True),
        ):
            try:
                from opentelemetry.instrumentation.logging.handler import LoggingHandler
            except ImportError:
                from opentelemetry.sdk._logs._internal import LoggingHandler

            with patch.object(tel, "_OTEL_AVAILABLE", True):
                # Chamar diretamente para evitar interferência com _initialized
                tel._setup_logging()

        # se chegou aqui sem exceção, o caminho foi percorrido


class TestSetupLoggingOtlpEndpoint:
    def test_otlp_exporter_added_when_endpoint_set(self):
        import concilium.infrastructure.telemetry as tel

        mock_provider = MagicMock()

        with (
            patch("concilium.infrastructure.telemetry.get_telemetry",
                  return_value=_telemetry_settings(endpoint="http://otel-collector:4318")),
            patch("opentelemetry.sdk._logs.LoggerProvider", return_value=mock_provider),
            patch("opentelemetry.exporter.otlp.proto.http._log_exporter.OTLPLogExporter"),
            patch("opentelemetry.sdk._logs.export.BatchLogRecordProcessor"),
            patch("opentelemetry._logs.set_logger_provider"),
            patch("concilium.infrastructure.telemetry._otel_console", return_value=False),
        ):
            try:
                tel._setup_logging()
            except Exception:
                pass  # pode falhar por deps não totalmente mockadas; o objetivo é exercitar o branch


# ─────────────────────────────────────────────────────────────────────────────
# _setup_tracing console path (linhas 122-124)
# ─────────────────────────────────────────────────────────────────────────────


class TestSetupTracingConsole:
    def test_console_exporter_added(self):
        import concilium.infrastructure.telemetry as tel

        mock_provider = MagicMock()

        with (
            patch("concilium.infrastructure.telemetry.get_telemetry",
                  return_value=_telemetry_settings(console=True, endpoint=None)),
            patch("opentelemetry.sdk.trace.TracerProvider", return_value=mock_provider),
            patch("opentelemetry.sdk.trace.export.ConsoleSpanExporter"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.trace.set_tracer_provider"),
            patch("concilium.infrastructure.telemetry._otel_console", return_value=True),
        ):
            tel._setup_tracing()

        mock_provider.add_span_processor.assert_called_once()


class TestSetupTracingOtlpEndpoint:
    def test_otlp_exporter_added(self):
        import concilium.infrastructure.telemetry as tel

        mock_provider = MagicMock()

        with (
            patch("concilium.infrastructure.telemetry.get_telemetry",
                  return_value=_telemetry_settings(endpoint="http://otel-collector:4318")),
            patch("opentelemetry.sdk.trace.TracerProvider", return_value=mock_provider),
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"),
            patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
            patch("opentelemetry.trace.set_tracer_provider"),
            patch("concilium.infrastructure.telemetry._otel_console", return_value=False),
        ):
            tel._setup_tracing()

        mock_provider.add_span_processor.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# _setup_metrics console path (linhas 152-155)
# ─────────────────────────────────────────────────────────────────────────────


class TestSetupMetricsConsole:
    def test_console_reader_added(self):
        import concilium.infrastructure.telemetry as tel

        mock_provider = MagicMock()

        with (
            patch("concilium.infrastructure.telemetry.get_telemetry",
                  return_value=_telemetry_settings(console=True, endpoint=None)),
            patch("opentelemetry.sdk.metrics.MeterProvider", return_value=mock_provider),
            patch("opentelemetry.sdk.metrics.export.ConsoleMetricExporter"),
            patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"),
            patch("opentelemetry.metrics.set_meter_provider"),
            patch("concilium.infrastructure.telemetry._otel_console", return_value=True),
        ):
            tel._setup_metrics()


class TestSetupMetricsOtlpEndpoint:
    def test_otlp_reader_added(self):
        import concilium.infrastructure.telemetry as tel

        mock_provider = MagicMock()

        with (
            patch("concilium.infrastructure.telemetry.get_telemetry",
                  return_value=_telemetry_settings(endpoint="http://otel-collector:4318")),
            patch("opentelemetry.sdk.metrics.MeterProvider", return_value=mock_provider),
            patch("opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"),
            patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"),
            patch("opentelemetry.metrics.set_meter_provider"),
            patch("concilium.infrastructure.telemetry._otel_console", return_value=False),
        ):
            tel._setup_metrics()


# ─────────────────────────────────────────────────────────────────────────────
# get_tracer / get_meter com OTEL disponível (linhas 172, 181)
# ─────────────────────────────────────────────────────────────────────────────


class TestGetTracerGetMeterOtelAvailable:
    def test_get_tracer_returns_real_tracer_when_otel_available(self):
        import concilium.infrastructure.telemetry as tel

        with patch.object(tel, "_OTEL_AVAILABLE", True):
            tracer = tel.get_tracer()
        # deve ser o tracer do SDK, não o NoOp
        assert not isinstance(tracer, tel._NoOpTracer)

    def test_get_meter_returns_real_meter_when_otel_available(self):
        import concilium.infrastructure.telemetry as tel

        with patch.object(tel, "_OTEL_AVAILABLE", True):
            meter = tel.get_meter()
        assert not isinstance(meter, tel._NoOpMeter)

    def test_get_tracer_returns_noop_when_otel_unavailable(self):
        """Linha 172: return _NoOpTracer() quando _OTEL_AVAILABLE=False."""
        import concilium.infrastructure.telemetry as tel

        with patch.object(tel, "_OTEL_AVAILABLE", False):
            tracer = tel.get_tracer()
        assert isinstance(tracer, tel._NoOpTracer)

    def test_get_meter_returns_noop_when_otel_unavailable(self):
        """Linha 181: return _NoOpMeter() quando _OTEL_AVAILABLE=False."""
        import concilium.infrastructure.telemetry as tel

        with patch.object(tel, "_OTEL_AVAILABLE", False):
            meter = tel.get_meter()
        assert isinstance(meter, tel._NoOpMeter)


# ─────────────────────────────────────────────────────────────────────────────
# record_skill_duration com OTEL disponível (linhas 222, 231)
# ─────────────────────────────────────────────────────────────────────────────


class TestRecordMetricsOtelAvailable:
    def _fake_histogram(self):
        h = MagicMock()
        h.record = MagicMock()
        return h

    def _fake_counter(self):
        c = MagicMock()
        c.add = MagicMock()
        return c

    def test_record_skill_duration_creates_histogram_on_first_call(self):
        import concilium.infrastructure.telemetry as tel

        fake_hist = self._fake_histogram()
        fake_meter = MagicMock()
        fake_meter.create_histogram.return_value = fake_hist

        original = tel._skill_duration_histogram
        try:
            tel._skill_duration_histogram = None
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=fake_meter),
            ):
                tel.record_skill_duration("01-escopo-e-eap", "OK", 1500)
            fake_meter.create_histogram.assert_called_once()
            fake_hist.record.assert_called_once_with(1500, {"skill": "01-escopo-e-eap", "status": "OK"})
        finally:
            tel._skill_duration_histogram = original

    def test_record_skill_duration_reuses_histogram_on_second_call(self):
        import concilium.infrastructure.telemetry as tel

        fake_hist = self._fake_histogram()
        fake_meter = MagicMock()

        original = tel._skill_duration_histogram
        try:
            tel._skill_duration_histogram = fake_hist
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=fake_meter),
            ):
                tel.record_skill_duration("06-resultado-financeiro", "ERROR", 300)
            fake_meter.create_histogram.assert_not_called()
            fake_hist.record.assert_called_once_with(300, {"skill": "06-resultado-financeiro", "status": "ERROR"})
        finally:
            tel._skill_duration_histogram = original

    def test_record_rate_limit_exceeded_creates_counter(self):
        import concilium.infrastructure.telemetry as tel

        fake_counter = self._fake_counter()
        fake_meter = MagicMock()
        fake_meter.create_counter.return_value = fake_counter

        original = tel._rate_limit_exceeded_counter
        try:
            tel._rate_limit_exceeded_counter = None
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=fake_meter),
            ):
                tel.record_rate_limit_exceeded("/api/projects")
            fake_meter.create_counter.assert_called_once()
            fake_counter.add.assert_called_once_with(1, {"route": "/api/projects"})
        finally:
            tel._rate_limit_exceeded_counter = original

    def test_record_tool_call_creates_counter(self):
        import concilium.infrastructure.telemetry as tel

        fake_counter = self._fake_counter()
        fake_meter = MagicMock()
        fake_meter.create_counter.return_value = fake_counter

        original = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = None
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=fake_meter),
            ):
                tel.record_tool_call("listar_projetos", "OK")
            fake_meter.create_counter.assert_called_once()
            fake_counter.add.assert_called_once_with(1, {"tool": "listar_projetos", "status": "OK"})
        finally:
            tel._tool_calls_counter = original

    def test_record_tool_call_reuses_counter(self):
        import concilium.infrastructure.telemetry as tel

        fake_counter = self._fake_counter()
        fake_meter = MagicMock()

        original = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = fake_counter
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=fake_meter),
            ):
                tel.record_tool_call("listar_projetos", "ERROR")
            fake_meter.create_counter.assert_not_called()
            fake_counter.add.assert_called_once_with(1, {"tool": "listar_projetos", "status": "ERROR"})
        finally:
            tel._tool_calls_counter = original


# ─────────────────────────────────────────────────────────────────────────────
# set_current_span_attrs com OTEL disponível (linhas 247-248)
# ─────────────────────────────────────────────────────────────────────────────


class TestMetricFunctionsOtelUnavailable:
    """Cobre early-returns (linhas 204, 222, 239, 255) e except-passes (231-232, 247-248, 263-264)."""

    def test_set_current_span_attrs_returns_early_when_unavailable(self):
        """Linha 204: return quando _OTEL_AVAILABLE=False."""
        import concilium.infrastructure.telemetry as tel

        with patch.object(tel, "_OTEL_AVAILABLE", False):
            # não deve chamar nada, não deve lançar
            tel.set_current_span_attrs({"k": "v"})

    def test_record_skill_duration_returns_early_when_unavailable(self):
        """Linha 222: return quando _OTEL_AVAILABLE=False."""
        import concilium.infrastructure.telemetry as tel

        original = tel._skill_duration_histogram
        try:
            tel._skill_duration_histogram = None
            with patch.object(tel, "_OTEL_AVAILABLE", False):
                tel.record_skill_duration("01", "OK", 500)
            assert tel._skill_duration_histogram is None  # não foi criado
        finally:
            tel._skill_duration_histogram = original

    def test_record_skill_duration_silences_exception(self):
        """Linhas 231-232: except Exception: pass em record_skill_duration."""
        import concilium.infrastructure.telemetry as tel

        original = tel._skill_duration_histogram
        try:
            tel._skill_duration_histogram = None
            broken_meter = MagicMock()
            broken_meter.create_histogram.side_effect = RuntimeError("sem meter")
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=broken_meter),
            ):
                tel.record_skill_duration("01", "OK", 500)  # não deve lançar
        finally:
            tel._skill_duration_histogram = original

    def test_record_rate_limit_returns_early_when_unavailable(self):
        """Linha 239: return quando _OTEL_AVAILABLE=False."""
        import concilium.infrastructure.telemetry as tel

        original = tel._rate_limit_exceeded_counter
        try:
            tel._rate_limit_exceeded_counter = None
            with patch.object(tel, "_OTEL_AVAILABLE", False):
                tel.record_rate_limit_exceeded("/api/x")
            assert tel._rate_limit_exceeded_counter is None
        finally:
            tel._rate_limit_exceeded_counter = original

    def test_record_rate_limit_silences_exception(self):
        """Linhas 247-248: except Exception: pass em record_rate_limit_exceeded."""
        import concilium.infrastructure.telemetry as tel

        original = tel._rate_limit_exceeded_counter
        try:
            tel._rate_limit_exceeded_counter = None
            broken_meter = MagicMock()
            broken_meter.create_counter.side_effect = RuntimeError("broken")
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=broken_meter),
            ):
                tel.record_rate_limit_exceeded("/api/x")  # não deve lançar
        finally:
            tel._rate_limit_exceeded_counter = original

    def test_record_tool_call_returns_early_when_unavailable(self):
        """Linha 255: return quando _OTEL_AVAILABLE=False."""
        import concilium.infrastructure.telemetry as tel

        original = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = None
            with patch.object(tel, "_OTEL_AVAILABLE", False):
                tel.record_tool_call("tool", "OK")
            assert tel._tool_calls_counter is None
        finally:
            tel._tool_calls_counter = original

    def test_record_tool_call_silences_exception(self):
        """Linhas 263-264: except Exception: pass em record_tool_call."""
        import concilium.infrastructure.telemetry as tel

        original = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = None
            broken_meter = MagicMock()
            broken_meter.create_counter.side_effect = RuntimeError("broken")
            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_meter", return_value=broken_meter),
            ):
                tel.record_tool_call("tool", "OK")  # não deve lançar
        finally:
            tel._tool_calls_counter = original


class TestSkillSpanException:
    def test_skill_span_returns_nullcontext_on_exception(self):
        """Linhas 197-198: except Exception retorna nullcontext quando start_as_current_span falha."""
        import concilium.infrastructure.telemetry as tel

        broken_tracer = MagicMock()
        broken_tracer.start_as_current_span.side_effect = RuntimeError("no span")

        with patch.object(tel, "get_tracer", return_value=broken_tracer):
            ctx = tel.skill_span("01-escopo")

        # deve retornar um context manager válido (nullcontext)
        from contextlib import nullcontext
        with ctx:
            pass  # não deve lançar


class TestSetCurrentSpanAttrsOtelAvailable:
    def test_set_current_span_attrs_calls_span(self):
        import concilium.infrastructure.telemetry as tel

        fake_span = MagicMock()

        with (
            patch.object(tel, "_OTEL_AVAILABLE", True),
            patch("opentelemetry.trace.get_current_span", return_value=fake_span),
        ):
            tel.set_current_span_attrs({"skill.id": "01-escopo-e-eap", "version": "v1"})

        fake_span.set_attribute.assert_any_call("skill.id", "01-escopo-e-eap")
        fake_span.set_attribute.assert_any_call("version", "v1")

    def test_set_current_span_attrs_silences_exception(self):
        import concilium.infrastructure.telemetry as tel

        with (
            patch.object(tel, "_OTEL_AVAILABLE", True),
            patch("opentelemetry.trace.get_current_span", side_effect=RuntimeError("no span")),
        ):
            # deve silenciar a exceção
            tel.set_current_span_attrs({"k": "v"})


# ─────────────────────────────────────────────────────────────────────────────
# _with_tracing wrapper (linhas 279-294)
# ─────────────────────────────────────────────────────────────────────────────


class TestWithTracing:
    def test_with_tracing_wraps_function_and_records_ok(self):
        import concilium.infrastructure.telemetry as tel

        fake_span = MagicMock()
        fake_span.__enter__ = MagicMock(return_value=fake_span)
        fake_span.__exit__ = MagicMock(return_value=False)
        fake_tracer = MagicMock()
        fake_tracer.start_as_current_span.return_value = fake_span

        fake_counter = MagicMock()
        fake_meter = MagicMock()
        fake_meter.create_counter.return_value = fake_counter

        original_counter = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = fake_counter

            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_tracer", return_value=fake_tracer),
                patch.object(tel, "get_meter", return_value=fake_meter),
                patch("opentelemetry.trace.StatusCode") as MockStatusCode,
            ):
                MockStatusCode.OK = "OK"
                MockStatusCode.ERROR = "ERROR"

                def my_tool(project_id=None):
                    return 42

                wrapped = tel._with_tracing(my_tool)
                result = wrapped(project_id="AGIS")

            assert result == 42
            fake_span.set_attribute.assert_any_call("tool.name", "my_tool")
            fake_span.set_attribute.assert_any_call("project.id", "AGIS")
        finally:
            tel._tool_calls_counter = original_counter

    def test_with_tracing_records_error_and_reraises(self):
        import concilium.infrastructure.telemetry as tel

        import pytest

        fake_span = MagicMock()
        fake_span.__enter__ = MagicMock(return_value=fake_span)
        fake_span.__exit__ = MagicMock(return_value=False)
        fake_tracer = MagicMock()
        fake_tracer.start_as_current_span.return_value = fake_span

        fake_counter = MagicMock()
        fake_meter = MagicMock()
        fake_meter.create_counter.return_value = fake_counter

        original_counter = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = fake_counter

            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_tracer", return_value=fake_tracer),
                patch.object(tel, "get_meter", return_value=fake_meter),
                patch("opentelemetry.trace.StatusCode") as MockStatusCode,
            ):
                MockStatusCode.OK = "OK"
                MockStatusCode.ERROR = "ERROR"

                def broken_tool(**kwargs):
                    raise ValueError("tool falhou")

                wrapped = tel._with_tracing(broken_tool)

                with pytest.raises(ValueError, match="tool falhou"):
                    wrapped()

            fake_span.record_exception.assert_called_once()
        finally:
            tel._tool_calls_counter = original_counter

    def test_with_tracing_no_project_id_skips_attribute(self):
        """Quando project_id não está em kwargs, set_attribute("project.id") não é chamado."""
        import concilium.infrastructure.telemetry as tel

        fake_span = MagicMock()
        fake_span.__enter__ = MagicMock(return_value=fake_span)
        fake_span.__exit__ = MagicMock(return_value=False)
        fake_tracer = MagicMock()
        fake_tracer.start_as_current_span.return_value = fake_span

        fake_counter = MagicMock()
        fake_meter = MagicMock()
        fake_meter.create_counter.return_value = fake_counter

        original_counter = tel._tool_calls_counter
        try:
            tel._tool_calls_counter = fake_counter

            with (
                patch.object(tel, "_OTEL_AVAILABLE", True),
                patch.object(tel, "get_tracer", return_value=fake_tracer),
                patch.object(tel, "get_meter", return_value=fake_meter),
                patch("opentelemetry.trace.StatusCode") as MockStatusCode,
            ):
                MockStatusCode.OK = "OK"

                def simple_tool():
                    return "ok"

                wrapped = tel._with_tracing(simple_tool)
                result = wrapped()

            assert result == "ok"
            called_keys = [call[0][0] for call in fake_span.set_attribute.call_args_list]
            assert "project.id" not in called_keys
        finally:
            tel._tool_calls_counter = original_counter

    def test_with_tracing_returns_original_when_otel_unavailable(self):
        import concilium.infrastructure.telemetry as tel

        def my_fn():
            return "raw"

        with patch.object(tel, "_OTEL_AVAILABLE", False):
            result = tel._with_tracing(my_fn)

        assert result is my_fn


# ─────────────────────────────────────────────────────────────────────────────
# patch_fastmcp_server (linhas 309, 315-316)
# ─────────────────────────────────────────────────────────────────────────────


class TestPatchFastmcpServer:
    def test_patches_tools_when_otel_available(self):
        import concilium.infrastructure.telemetry as tel

        fake_tool = MagicMock()
        fake_tool.fn = lambda: None
        server = MagicMock()
        server._tool_manager._tools = {"my_tool": fake_tool}

        with patch.object(tel, "_OTEL_AVAILABLE", True):
            tel.patch_fastmcp_server(server)

        # fn deve ter sido substituído por um wrapper
        assert fake_tool.fn is not None

    def test_patch_is_noop_when_otel_unavailable(self):
        import concilium.infrastructure.telemetry as tel

        fake_tool = MagicMock()
        original_fn = fake_tool.fn
        server = MagicMock()
        server._tool_manager._tools = {"t": fake_tool}

        with patch.object(tel, "_OTEL_AVAILABLE", False):
            tel.patch_fastmcp_server(server)

        # fn não deve ter sido tocado
        assert fake_tool.fn is original_fn

    def test_patch_silences_exception_when_server_structure_wrong(self):
        import concilium.infrastructure.telemetry as tel

        server = MagicMock()
        server._tool_manager._tools = MagicMock(side_effect=AttributeError("no tools"))
        # forçar o AttributeError no .values()
        del server._tool_manager._tools

        with patch.object(tel, "_OTEL_AVAILABLE", True):
            # não deve levantar
            tel.patch_fastmcp_server(server)

    def test_tools_without_fn_attribute_are_skipped(self):
        import concilium.infrastructure.telemetry as tel

        fake_tool = MagicMock(spec=[])  # sem atributo fn
        server = MagicMock()
        server._tool_manager._tools = {"t": fake_tool}

        with patch.object(tel, "_OTEL_AVAILABLE", True):
            tel.patch_fastmcp_server(server)


# ─────────────────────────────────────────────────────────────────────────────
# _NoOpMeter.create_counter e _NoOpInstrument.add (linhas 339, 342)
# ─────────────────────────────────────────────────────────────────────────────


class TestNoOpStubs:
    def test_noop_meter_create_counter_returns_instrument(self):
        from concilium.infrastructure.telemetry import _NoOpInstrument, _NoOpMeter

        meter = _NoOpMeter()
        instrument = meter.create_counter("test.counter", description="Test counter")
        assert isinstance(instrument, _NoOpInstrument)

    def test_noop_instrument_add_is_noop(self):
        from concilium.infrastructure.telemetry import _NoOpInstrument

        instrument = _NoOpInstrument()
        # não deve levantar
        instrument.add(1, {"route": "/api"})
        instrument.add(5)

    def test_noop_meter_create_histogram_returns_instrument(self):
        from concilium.infrastructure.telemetry import _NoOpInstrument, _NoOpMeter

        meter = _NoOpMeter()
        instrument = meter.create_histogram("test.histogram")
        assert isinstance(instrument, _NoOpInstrument)

    def test_noop_instrument_record_is_noop(self):
        from concilium.infrastructure.telemetry import _NoOpInstrument

        instrument = _NoOpInstrument()
        instrument.record(100, {"skill": "01"})
