"""OpenTelemetry telemetry layer — ADR-095.

Sink configurável por variáveis de ambiente (vendor-agnostic):

  OTEL_SERVICE_NAME            — nome do serviço (default: concilium)
  OTEL_EXPORTER_OTLP_ENDPOINT  — habilita exporter OTLP HTTP (Azure Monitor, Datadog…)
  CONCILIUM__OTEL_CONSOLE       — "true" → console exporter (dev local)
  OTEL_SDK_DISABLED            — "true" → desativa toda telemetria (CI/testes)

Privacy (D5 do ADR): nenhum dado de projeto (quantitativos, preços, nomes de atividades)
entra em traces. Apenas metadados operacionais: IDs, durações, status, contagens.
"""

from __future__ import annotations

from contextlib import nullcontext
from functools import wraps
from typing import Any

from concilium.infrastructure.settings import get_telemetry

# ── OTEL availability guard ───────────────────────────────────────────────────

_OTEL_AVAILABLE = False
try:
    import opentelemetry  # noqa: F401

    _OTEL_AVAILABLE = True
except ImportError:
    pass

_initialized = False

# ── Metric instruments (singletons, criados na primeira emissão) ──────────────

_skill_duration_histogram = None
_tool_calls_counter = None
_rate_limit_exceeded_counter = None


# ── Setup ─────────────────────────────────────────────────────────────────────


def setup_telemetry() -> None:
    """Inicializa os providers OTEL. Idempotente — seguro chamar múltiplas vezes."""
    global _initialized
    if _initialized:
        return
    _initialized = True

    if not _OTEL_AVAILABLE:
        return
    telemetry = get_telemetry()
    if telemetry.otel_sdk_disabled:
        return

    _setup_tracing()
    _setup_metrics()
    _setup_logging()


def _setup_logging() -> None:
    """Configura LoggerProvider OTel e ponte Python logging → OTel (ADR-111 F2)."""
    import logging

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    telemetry = get_telemetry()
    resource = Resource({SERVICE_NAME: telemetry.otel_service_name})
    log_provider = LoggerProvider(resource=resource)

    otlp_endpoint = telemetry.otlp_endpoint
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs"))
        )
    elif _otel_console():
        from opentelemetry.sdk._logs.export import ConsoleLogExporter

        log_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogExporter()))

    set_logger_provider(log_provider)

    # Ponte: Python logging.Logger → OTel LogRecord (ADR-111 D2)
    # Nível WARNING para não inundar o sink OTel com DEBUG/INFO
    handler = LoggingHandler(level=logging.WARNING, logger_provider=log_provider)
    logging.getLogger().addHandler(handler)


def _setup_tracing() -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    telemetry = get_telemetry()
    resource = Resource({SERVICE_NAME: telemetry.otel_service_name})
    provider = TracerProvider(resource=resource)

    otlp_endpoint = telemetry.otlp_endpoint
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")))
    elif _otel_console():
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)


def _otel_console() -> bool:
    from concilium.infrastructure.settings import get_telemetry

    return get_telemetry().otel_console


def _setup_metrics() -> None:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    telemetry = get_telemetry()
    resource = Resource({SERVICE_NAME: telemetry.otel_service_name})
    readers: list = []

    otlp_endpoint = telemetry.otlp_endpoint
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")))
    elif _otel_console():
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader

        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))

    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))


# ── Tracer / Meter ────────────────────────────────────────────────────────────


def get_tracer() -> Any:
    """Retorna tracer global. No-op se OTEL indisponível."""
    if not _OTEL_AVAILABLE:
        return _NoOpTracer()
    from opentelemetry import trace

    return trace.get_tracer("concilium")


def get_meter() -> Any:
    """Retorna meter global. No-op se OTEL indisponível."""
    if not _OTEL_AVAILABLE:
        return _NoOpMeter()
    from opentelemetry import metrics

    return metrics.get_meter("concilium")


# ── Span helpers ──────────────────────────────────────────────────────────────


def skill_span(skill_id: str) -> Any:
    """Context manager: span OTEL para uma skill, ou nullcontext se OTEL indisponível."""
    try:
        return get_tracer().start_as_current_span(
            f"concilium.skill.{skill_id}",
            attributes={"skill.id": skill_id},
        )
    except Exception:
        return nullcontext(None)


def set_current_span_attrs(attrs: dict[str, Any]) -> None:
    """Define atributos no span OTEL ativo (best-effort, sem exceções)."""
    if not _OTEL_AVAILABLE:
        return
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        for k, v in attrs.items():
            span.set_attribute(k, v)
    except Exception:
        pass


# ── Metrics ───────────────────────────────────────────────────────────────────


def record_skill_duration(skill_id: str, status: str, duration_ms: int) -> None:
    """Emite histograma concilium.pipeline.skill.duration_ms."""
    global _skill_duration_histogram
    if not _OTEL_AVAILABLE:
        return
    try:
        if _skill_duration_histogram is None:
            _skill_duration_histogram = get_meter().create_histogram(
                "concilium.pipeline.skill.duration_ms",
                unit="ms",
                description="Duration of individual skill executions",
            )
        _skill_duration_histogram.record(duration_ms, {"skill": skill_id, "status": status})
    except Exception:
        pass


def record_rate_limit_exceeded(route: str) -> None:
    """Incrementa contador de requests bloqueados por rate limit (ADR-098)."""
    global _rate_limit_exceeded_counter
    if not _OTEL_AVAILABLE:
        return
    try:
        if _rate_limit_exceeded_counter is None:
            _rate_limit_exceeded_counter = get_meter().create_counter(
                "concilium.api.rate_limit.exceeded",
                description="Number of requests rejected by the rate limiter",
            )
        _rate_limit_exceeded_counter.add(1, {"route": route})
    except Exception:
        pass


def record_tool_call(tool_name: str, status: str) -> None:
    """Incrementa contador concilium.mcp.tool.calls."""
    global _tool_calls_counter
    if not _OTEL_AVAILABLE:
        return
    try:
        if _tool_calls_counter is None:
            _tool_calls_counter = get_meter().create_counter(
                "concilium.mcp.tool.calls",
                description="Number of MCP tool invocations",
            )
        _tool_calls_counter.add(1, {"tool": tool_name, "status": status})
    except Exception:
        pass


# ── MCP tool decorator ────────────────────────────────────────────────────────


def _with_tracing(tool_fn: Any) -> Any:
    """Decora uma função de tool MCP com span OTEL e contador de chamadas."""
    if not _OTEL_AVAILABLE:
        return tool_fn

    from opentelemetry.trace import StatusCode

    @wraps(tool_fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        project_id = kwargs.get("project_id")
        tracer = get_tracer()
        with tracer.start_as_current_span(f"mcp.tool.{tool_fn.__name__}") as span:
            span.set_attribute("tool.name", tool_fn.__name__)
            if project_id:
                span.set_attribute("project.id", str(project_id))
            try:
                result = tool_fn(*args, **kwargs)
                span.set_status(StatusCode.OK)
                record_tool_call(tool_fn.__name__, "OK")
                return result
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))
                record_tool_call(tool_fn.__name__, "ERROR")
                raise

    return wrapper


# ── FastMCP patcher ───────────────────────────────────────────────────────────


def patch_fastmcp_server(server: Any) -> None:
    """Envolve todas as tools MCP registradas com tracing OTEL (best-effort).

    Acessa server._tool_manager._tools (API interna do FastMCP).
    Se a estrutura interna mudar em versões futuras, o patch é silenciosamente ignorado.
    """
    if not _OTEL_AVAILABLE:
        return
    try:
        tools = server._tool_manager._tools
        for tool in tools.values():
            if hasattr(tool, "fn") and callable(tool.fn):
                tool.fn = _with_tracing(tool.fn)
    except Exception:
        pass


# ── No-op stubs ───────────────────────────────────────────────────────────────


class _NoOpSpan:
    def set_attribute(self, *a: Any, **kw: Any) -> None: ...
    def set_status(self, *a: Any, **kw: Any) -> None: ...
    def record_exception(self, *a: Any, **kw: Any) -> None: ...
    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *a: Any) -> None: ...


class _NoOpTracer:
    def start_as_current_span(self, *a: Any, **kw: Any) -> _NoOpSpan:
        return _NoOpSpan()


class _NoOpMeter:
    def create_histogram(self, *a: Any, **kw: Any) -> _NoOpInstrument:
        return _NoOpInstrument()

    def create_counter(self, *a: Any, **kw: Any) -> _NoOpInstrument:
        return _NoOpInstrument()


class _NoOpInstrument:
    def record(self, *a: Any, **kw: Any) -> None: ...
    def add(self, *a: Any, **kw: Any) -> None: ...
