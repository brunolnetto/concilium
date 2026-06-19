"""TDD para ADR-111 — Logging Centralizado e Ponte Python → OTel.

Cobre:
  F1 · _JsonFormatter: formato JSON, campos obrigatórios, exc_info, trace context
  F1 · configure_logging(): nível, handlers, silenciamento de loggers ruidosos, idempotência
  F2 · _setup_logging() em setup_telemetry(): LoggingHandler adicionado ao root logger
  F3 · Entry points (API, MCP) chamam configure_logging() na inicialização
"""

from __future__ import annotations

import json
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures de limpeza do root logger
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=False)
def clean_root_logger():
    """Isola cada teste que altera o root logger: remove handlers ANTES e restaura DEPOIS."""
    root = logging.getLogger()
    original_handlers = root.handlers[:]
    original_level = root.level
    # Limpa ANTES do teste para garantir estado virgem
    for h in root.handlers[:]:
        root.removeHandler(h)
    yield
    # Restaura estado original após o teste
    for h in root.handlers[:]:
        root.removeHandler(h)
    for h in original_handlers:
        root.addHandler(h)
    root.setLevel(original_level)


@pytest.fixture(autouse=False)
def reset_telemetry():
    """Reseta o flag _initialized da telemetria e faz shutdown dos providers OTel."""
    import concilium.infrastructure.telemetry as tel
    original = tel._initialized
    tel._initialized = False
    yield
    tel._initialized = original
    # Shutdown de TODOS os providers criados (tracked no módulo telemetry).
    # set_meter_provider() só funciona uma vez — providers subsequentes ficam órfãos
    # com threads rodando; é preciso fechar cada instância explicitamente.
    try:
        for mp in list(tel._active_meter_providers):
            if hasattr(mp, "shutdown"):
                mp.shutdown()
        tel._active_meter_providers.clear()
    except Exception:
        pass
    try:
        for lp in list(tel._active_log_providers):
            if hasattr(lp, "shutdown"):
                lp.shutdown()
        tel._active_log_providers.clear()
    except Exception:
        pass
    # Reseta o lock Once do OTel para permitir set_meter_provider() em múltiplos testes
    try:
        import opentelemetry.metrics._internal as _m_internal
        _m_internal._METER_PROVIDER_SET_ONCE._done = False
        _m_internal._METER_PROVIDER = None
    except Exception:
        pass
    try:
        import opentelemetry._logs._internal as _l_internal
        _l_internal._LOGGER_PROVIDER_SET_ONCE._done = False
        _l_internal._LOGGER_PROVIDER = None
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# F1-A: _JsonFormatter
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonFormatter:
    """_JsonFormatter emite JSON-lines com campos obrigatórios por ADR-111 D4."""

    @pytest.fixture(autouse=True)
    def formatter(self):
        from concilium.infrastructure.observability.logging_config import _JsonFormatter
        self.fmt = _JsonFormatter()

    def _record(self, msg="mensagem de teste", level=logging.WARNING, name="concilium.test"):
        return logging.LogRecord(
            name=name, level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )

    def test_output_is_valid_json(self):
        payload = json.loads(self.fmt.format(self._record()))
        assert isinstance(payload, dict)

    def test_mandatory_fields_present(self):
        payload = json.loads(self.fmt.format(self._record()))
        for field in ("ts", "severity", "logger", "message", "trace_id", "span_id", "service"):
            assert field in payload, f"Campo obrigatório ausente: '{field}'"

    def test_severity_maps_to_levelname(self):
        for level, expected in [(logging.DEBUG, "DEBUG"), (logging.WARNING, "WARNING"), (logging.ERROR, "ERROR")]:
            payload = json.loads(self.fmt.format(self._record(level=level)))
            assert payload["severity"] == expected

    def test_message_is_formatted(self):
        record = logging.LogRecord(
            name="t", level=logging.INFO, pathname="", lineno=0,
            msg="CPU %s ausente no catálogo %s", args=("P0046", "mendeslobo"), exc_info=None,
        )
        payload = json.loads(self.fmt.format(record))
        assert payload["message"] == "CPU P0046 ausente no catálogo mendeslobo"

    def test_logger_name_preserved(self):
        payload = json.loads(self.fmt.format(self._record(name="concilium.domain.services.simulation")))
        assert payload["logger"] == "concilium.domain.services.simulation"

    def test_service_field_is_concilium(self):
        payload = json.loads(self.fmt.format(self._record()))
        assert payload["service"] == "concilium"

    def test_no_active_span_yields_empty_trace_ids(self):
        """Sem span OTel ativo, trace_id e span_id são strings vazias."""
        payload = json.loads(self.fmt.format(self._record()))
        assert payload["trace_id"] == ""
        assert payload["span_id"] == ""

    def test_exception_info_included_when_present(self):
        try:
            raise ValueError("preco_unitario inválido")
        except ValueError:
            record = logging.LogRecord(
                name="t", level=logging.ERROR, pathname="", lineno=0,
                msg="falha na simulação", args=(), exc_info=sys.exc_info(),
            )
        payload = json.loads(self.fmt.format(record))
        assert "exception" in payload
        assert "ValueError" in payload["exception"]
        assert "preco_unitario inválido" in payload["exception"]

    def test_no_exception_field_without_exc_info(self):
        payload = json.loads(self.fmt.format(self._record()))
        assert "exception" not in payload

    def test_output_is_single_line(self):
        """JSON-lines: sem quebras de linha internas."""
        output = self.fmt.format(self._record())
        assert "\n" not in output


# ─────────────────────────────────────────────────────────────────────────────
# F1-B: configure_logging()
# ─────────────────────────────────────────────────────────────────────────────

class TestConfigureLogging:
    """configure_logging() configura root logger corretamente."""

    @pytest.fixture(autouse=True)
    def isolate(self, clean_root_logger):
        pass  # garante isolamento via fixture

    def test_sets_root_level_info(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="INFO", json_format=False)
        assert logging.getLogger().level == logging.INFO

    def test_sets_root_level_warning(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="WARNING", json_format=False)
        assert logging.getLogger().level == logging.WARNING

    def test_sets_root_level_debug(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="DEBUG", json_format=False)
        assert logging.getLogger().level == logging.DEBUG

    def test_json_format_adds_stream_handler_with_json_formatter(self):
        from concilium.infrastructure.observability.logging_config import configure_logging, _JsonFormatter
        configure_logging(level="INFO", json_format=True)
        json_handlers = [h for h in logging.getLogger().handlers if isinstance(h.formatter, _JsonFormatter)]
        assert len(json_handlers) >= 1, "Deve ter pelo menos 1 handler com _JsonFormatter"

    def test_no_json_formatter_when_json_format_false(self):
        from concilium.infrastructure.observability.logging_config import configure_logging, _JsonFormatter
        configure_logging(level="INFO", json_format=False)
        json_handlers = [h for h in logging.getLogger().handlers if isinstance(h.formatter, _JsonFormatter)]
        assert len(json_handlers) == 0, "json_format=False não deve adicionar _JsonFormatter"

    def test_silences_httpx(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="DEBUG", json_format=False)
        assert logging.getLogger("httpx").level == logging.WARNING

    def test_silences_httpcore(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="DEBUG", json_format=False)
        assert logging.getLogger("httpcore").level == logging.WARNING

    def test_silences_urllib3(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="DEBUG", json_format=False)
        assert logging.getLogger("urllib3").level == logging.WARNING

    def test_silences_azure(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="DEBUG", json_format=False)
        assert logging.getLogger("azure").level == logging.WARNING

    def test_silences_opentelemetry_sdk(self):
        from concilium.infrastructure.observability.logging_config import configure_logging
        configure_logging(level="DEBUG", json_format=False)
        assert logging.getLogger("opentelemetry.sdk").level == logging.WARNING

    def test_idempotent_no_duplicate_json_handlers(self):
        """Chamar configure_logging duas vezes não cria handlers duplicados."""
        from concilium.infrastructure.observability.logging_config import configure_logging, _JsonFormatter
        configure_logging(level="INFO", json_format=True)
        configure_logging(level="INFO", json_format=True)
        json_handlers = [h for h in logging.getLogger().handlers if isinstance(h.formatter, _JsonFormatter)]
        assert len(json_handlers) == 1, f"Esperado 1 handler JSON, encontrado {len(json_handlers)}"


# ─────────────────────────────────────────────────────────────────────────────
# F1-C: trace context injetado quando span OTel ativo
# ─────────────────────────────────────────────────────────────────────────────

class TestJsonFormatterWithActiveSpan:
    """_JsonFormatter extrai trace_id/span_id do span OTel ativo."""

    @pytest.fixture(autouse=True)
    def formatter(self):
        from concilium.infrastructure.observability.logging_config import _JsonFormatter
        self.fmt = _JsonFormatter()

    def _record(self):
        return logging.LogRecord(
            name="t", level=logging.WARNING, pathname="", lineno=0,
            msg="teste", args=(), exc_info=None,
        )

    def test_trace_id_injected_when_span_active(self):
        """Quando há span OTel ativo com contexto válido, trace_id != ''."""
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("test_span"):
            payload = json.loads(self.fmt.format(self._record()))
        # O span tem contexto válido → trace_id não deve ser vazio
        assert payload["trace_id"] != "", "trace_id deve ser preenchido com span ativo"
        assert payload["span_id"] != "", "span_id deve ser preenchido com span ativo"

    def test_trace_id_is_32_hex_chars(self):
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider()
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span("test_span"):
            payload = json.loads(self.fmt.format(self._record()))
        assert len(payload["trace_id"]) == 32
        assert all(c in "0123456789abcdef" for c in payload["trace_id"])


# ─────────────────────────────────────────────────────────────────────────────
# F2: _setup_logging() em setup_telemetry()
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupLogging:
    """setup_telemetry() configura LoggerProvider e adiciona LoggingHandler ao root."""

    @pytest.fixture(autouse=True)
    def isolate(self, clean_root_logger, reset_telemetry):
        pass

    def test_setup_telemetry_adds_logging_handler_in_console_mode(self, monkeypatch):
        """Com CONCILIUM__OTEL_CONSOLE=true, root logger recebe LoggingHandler OTel."""
        from opentelemetry.sdk._logs._internal import LoggingHandler

        monkeypatch.setenv("CONCILIUM__OTEL_CONSOLE", "true")
        monkeypatch.setenv("OTEL_SDK_DISABLED", "false")

        from concilium.infrastructure.telemetry import setup_telemetry
        setup_telemetry()

        otel_handlers = [h for h in logging.getLogger().handlers if isinstance(h, LoggingHandler)]
        assert len(otel_handlers) >= 1, "Deve haver LoggingHandler OTel no root logger"

    def test_setup_telemetry_no_logging_handler_when_sdk_disabled(self, monkeypatch):
        """Com OTEL_SDK_DISABLED=true, nenhum LoggingHandler é adicionado."""
        from opentelemetry.sdk._logs._internal import LoggingHandler

        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")

        from concilium.infrastructure.telemetry import setup_telemetry
        setup_telemetry()

        otel_handlers = [h for h in logging.getLogger().handlers if isinstance(h, LoggingHandler)]
        assert len(otel_handlers) == 0, "Não deve haver LoggingHandler quando SDK desativado"

    def test_setup_logging_sets_logger_provider(self, monkeypatch):
        """setup_telemetry() em modo console configura um LoggerProvider não-noop."""
        from opentelemetry._logs import get_logger_provider
        from opentelemetry.sdk._logs import LoggerProvider

        monkeypatch.setenv("CONCILIUM__OTEL_CONSOLE", "true")
        monkeypatch.setenv("OTEL_SDK_DISABLED", "false")

        from concilium.infrastructure.telemetry import setup_telemetry
        setup_telemetry()

        provider = get_logger_provider()
        assert isinstance(provider, LoggerProvider), (
            f"LoggerProvider deve ser SdkLoggerProvider, não {type(provider)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# F3: Entry points chamam configure_logging()
# ─────────────────────────────────────────────────────────────────────────────

class TestEntryPointsCallConfigureLogging:
    """API, MCP e CLI chamam configure_logging() na inicialização."""

    def test_create_app_calls_configure_logging(self, monkeypatch):
        """create_app() deve chamar configure_logging() durante a inicialização."""
        mock_configure = MagicMock()
        monkeypatch.setattr("concilium.presentation.api.app.setup_telemetry", MagicMock())
        monkeypatch.setattr("concilium.presentation.api.app.configure_logging", mock_configure)

        from concilium.presentation.api import app as app_module
        app_module.create_app()

        mock_configure.assert_called_once()

    def test_build_server_calls_configure_logging(self, monkeypatch):
        """build_server() deve chamar configure_logging() durante a inicialização."""
        mock_configure = MagicMock()
        monkeypatch.setattr("concilium.presentation.mcp.server.setup_telemetry", MagicMock())
        monkeypatch.setattr("concilium.presentation.mcp.server.configure_logging", mock_configure)

        from concilium.presentation.mcp import server as mcp_module
        mcp_module.build_server()

        mock_configure.assert_called_once()
