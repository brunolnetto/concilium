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

import atexit
from contextlib import nullcontext
from functools import wraps
from typing import TYPE_CHECKING, Any

from concilium.infrastructure.settings import get_telemetry

if TYPE_CHECKING:
    from concilium.domain.repositories.blob_storage_port import BlobStoragePort

# ── OTEL availability guard ───────────────────────────────────────────────────

_OTEL_AVAILABLE = False
try:
    import opentelemetry  # noqa: F401

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover
    pass

_initialized = False

# ── Contrato de labels de métricas (ADR-146) ─────────────────────────────────
# Chaves canônicas: são as ÚNICAS que a Silver promove a colunas de primeira
# classe (normalize_metric_record → skill_id/tool_name/project_id). Os valores
# são os já emitidos historicamente — mudá-los quebraria séries existentes e a
# projeção retroativa sobre Bronze antigo. Instrumentos novos devem usá-las,
# nunca variantes ("skill_id", "toolName") que a projeção não reconhece.
# Labels fora do contrato (ex.: "route", "pipeline.mode") continuam válidas —
# ficam acessíveis só via o dict `labels` na Silver, sem coluna própria.

METRIC_LABEL_SKILL = "skill"
METRIC_LABEL_TOOL = "tool"
METRIC_LABEL_PROJECT = "project.id"
METRIC_LABEL_STATUS = "status"

# ── Metric instruments (singletons, criados na primeira emissão) ──────────────

_skill_duration_histogram = None
_tool_calls_counter = None
_rate_limit_exceeded_counter = None
_project_margin_gauge = None

# ── Provider references (para shutdown em testes e em shutdown_telemetry) ─────
_active_meter_providers: list = []
_active_log_providers: list = []
_active_tracer_providers: list = []


# ── Setup ─────────────────────────────────────────────────────────────────────


def setup_telemetry(bronze_storage: BlobStoragePort | None = None) -> None:
    """Inicializa os providers OTEL. Idempotente — seguro chamar múltiplas vezes.

    Args:
        bronze_storage: BlobStoragePort opcional. Quando fornecido, spans e
            métricas passam a ser gravados também em Bronze (observability/bronze/
            traces|metrics/), em paralelo a qualquer exporter OTLP/console
            configurado — sem isso, traces/metrics nunca alimentavam o pipeline
            Medallion (só logs, via BronzeLogHandler em configure_logging).
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    if not _OTEL_AVAILABLE:
        return
    telemetry = get_telemetry()
    if telemetry.otel_sdk_disabled:
        return

    _setup_tracing(bronze_storage=bronze_storage)
    _setup_metrics(bronze_storage=bronze_storage)
    _setup_logging()

    # Drena o último lote de spans/métricas/logs OTel pendente no encerramento
    # do processo — sem isso, BatchSpanProcessor/PeriodicExportingMetricReader
    # só exportam no próximo ciclo periódico, que pode nunca chegar a rodar em
    # Container Apps com scale-to-zero.
    atexit.register(shutdown_telemetry)


def shutdown_telemetry() -> None:
    """Desliga todos os providers OTEL ativos, drenando buffers pendentes (best-effort).

    Chamado automaticamente no encerramento normal do processo (ver
    `setup_telemetry`). Cada provider é desligado independentemente — uma
    falha em um não deve impedir os demais.
    """
    for provider in (*_active_tracer_providers, *_active_meter_providers, *_active_log_providers):
        try:
            provider.shutdown()
        except Exception:
            pass


def _setup_logging() -> None:
    """Configura LoggerProvider OTel e ponte Python logging → OTel (ADR-111 F2)."""
    import logging

    global _active_log_providers

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    # LoggingHandler: preferir opentelemetry-instrumentation-logging (se instalado),
    # com fallback para o SDK nativo (_internal). O linter tende a reescrever para o
    # pacote de instrumentação; o try/except torna o import resiliente a ambos.
    try:
        from opentelemetry.instrumentation.logging.handler import LoggingHandler
    except ImportError:
        from opentelemetry.sdk._logs._internal import LoggingHandler

    telemetry = get_telemetry()
    resource = Resource({SERVICE_NAME: telemetry.otel_service_name})
    log_provider = LoggerProvider(resource=resource)
    _active_log_providers.append(log_provider)

    otlp_endpoint = telemetry.otlp_endpoint
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter

        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs"))
        )
    elif _otel_console():
        from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter  # ConsoleLogExporter deprecated

        log_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogRecordExporter()))

    set_logger_provider(log_provider)

    # Ponte: Python logging.Logger → OTel LogRecord (ADR-121 D1)
    # DEBUG — INFO e DEBUG são eventos operacionais relevantes (scheduling, catálogo, pipeline).
    # O BatchLogRecordProcessor e o sampling do coletor OTel gerenciam volume em produção.
    handler = LoggingHandler(level=logging.DEBUG, logger_provider=log_provider)
    logging.getLogger().addHandler(handler)


def _setup_tracing(bronze_storage: BlobStoragePort | None = None) -> None:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    global _active_tracer_providers

    telemetry = get_telemetry()
    resource = Resource({SERVICE_NAME: telemetry.otel_service_name})
    provider = TracerProvider(resource=resource)
    _active_tracer_providers.append(provider)

    otlp_endpoint = telemetry.otlp_endpoint
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces")))
    elif _otel_console():
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter

        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Bronze roda em paralelo ao exporter acima (ou sozinho, se nenhum estiver
    # configurado) — sem isso, spans nunca alimentavam Bronze/Silver/Gold.
    if bronze_storage is not None:
        from concilium.infrastructure.observability.bronze_span_exporter import BronzeSpanExporter
        from concilium.infrastructure.observability.bronze_writer import BronzeWriter

        writer = BronzeWriter(bronze_storage, "traces")
        provider.add_span_processor(BatchSpanProcessor(BronzeSpanExporter(writer)))

    trace.set_tracer_provider(provider)


def _otel_console() -> bool:
    from concilium.infrastructure.settings import get_telemetry

    return get_telemetry().otel_console


def _setup_metrics(bronze_storage: BlobStoragePort | None = None) -> None:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource

    global _active_meter_providers

    telemetry = get_telemetry()
    resource = Resource({SERVICE_NAME: telemetry.otel_service_name})
    readers: list = []

    otlp_endpoint = telemetry.otlp_endpoint
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

        readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=f"{otlp_endpoint}/v1/metrics")))
    elif _otel_console():
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter

        readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))

    # Bronze roda em paralelo ao reader acima (ou sozinho) — sem isso, métricas
    # nunca alimentavam Bronze/Silver/Gold.
    if bronze_storage is not None:
        from concilium.infrastructure.observability.bronze_metric_exporter import BronzeMetricExporter
        from concilium.infrastructure.observability.bronze_writer import BronzeWriter

        writer = BronzeWriter(bronze_storage, "metrics")
        readers.append(PeriodicExportingMetricReader(BronzeMetricExporter(writer), export_interval_millis=30000))

    provider = MeterProvider(resource=resource, metric_readers=readers)
    _active_meter_providers.append(provider)
    metrics.set_meter_provider(provider)


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
        _skill_duration_histogram.record(
            duration_ms, {METRIC_LABEL_SKILL: skill_id, METRIC_LABEL_STATUS: status}
        )
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


def record_tool_call(tool_name: str, status: str, project_id: Any | None = None) -> None:
    """Incrementa contador concilium.mcp.tool.calls.

    project_id (ADR-146): quando presente, a série ganha o label canônico
    "project.id" — chamadas de tool ficam fatiáveis por projeto na Silver/Gold.
    Ausente, o label dict é idêntico ao histórico (sem chave com valor vazio,
    que criaria uma série 'project.id=None' espúria).
    """
    global _tool_calls_counter
    if not _OTEL_AVAILABLE:
        return
    try:
        if _tool_calls_counter is None:
            _tool_calls_counter = get_meter().create_counter(
                "concilium.mcp.tool.calls",
                description="Number of MCP tool invocations",
            )
        labels = {METRIC_LABEL_TOOL: tool_name, METRIC_LABEL_STATUS: status}
        if project_id:
            labels[METRIC_LABEL_PROJECT] = str(project_id)
        _tool_calls_counter.add(1, labels)
    except Exception:
        pass


def record_project_margin(
    project_id: str,
    margem_pct: float,
    custo_direto: float | None = None,
    pipeline_mode: str = "unknown",
) -> None:
    """Emite métricas de negócio (margem, custo direto) por projeto — ADR-095.

    Privacidade: apenas IDs e indicadores financeiros agregados.
    Nenhum dado de insumo, preço unitário ou atividade é enviado.
    """
    global _project_margin_gauge
    if not _OTEL_AVAILABLE:
        return
    try:
        if _project_margin_gauge is None:
            _project_margin_gauge = get_meter().create_gauge(
                "concilium.project.margem_pct",
                description="Margem percentual do projeto após pipeline completo",
                unit="%",
            )
        attrs = {METRIC_LABEL_PROJECT: project_id, "pipeline.mode": pipeline_mode}
        _project_margin_gauge.set(round(margem_pct * 100, 4), attrs)
        if custo_direto is not None:
            _log_business_metric(project_id, "custo_direto", custo_direto, pipeline_mode)
    except Exception:
        pass


def _log_business_metric(project_id: str, metric: str, value: float, pipeline_mode: str) -> None:
    import logging

    _biz_log = logging.getLogger("concilium.business_metrics")
    _biz_log.info(
        "business_metric project_id=%s metric=%s value=%.2f pipeline_mode=%s",
        project_id,
        metric,
        value,
        pipeline_mode,
    )


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
                record_tool_call(tool_fn.__name__, "OK", project_id=project_id)
                return result
            except Exception as exc:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))
                record_tool_call(tool_fn.__name__, "ERROR", project_id=project_id)
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
