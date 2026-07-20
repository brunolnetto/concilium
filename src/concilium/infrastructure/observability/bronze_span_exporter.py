"""BronzeSpanExporter — grava spans OTel no Bronze (extensão de ADR-112 F1 a traces).

Antes deste exporter, spans só saíam via OTLP (endpoint externo) ou console —
nunca chegavam à camada Bronze/Silver/Gold, mesmo com `normalize_span_record`
(silver_normalizer.py) já pronto para recebê-los. Roda em paralelo ao exporter
OTLP/console já configurado em `_setup_tracing`, sempre que há storage de
sistema disponível, independentemente de haver endpoint OTLP configurado.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Sequence
from typing import Any

from opentelemetry.sdk.resources import SERVICE_NAME
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from concilium.infrastructure.observability.bronze_writer import BronzeWriter

logger = logging.getLogger(__name__)


def _ns_to_iso(ns: int) -> str:
    if not ns:
        return ""
    return datetime.datetime.fromtimestamp(ns / 1_000_000_000, tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class BronzeSpanExporter(SpanExporter):
    """Exporta spans finalizados para `observability/bronze/traces/`.

    Schema de saída compatível com `silver_normalizer.normalize_span_record`.
    """

    def __init__(self, writer: BronzeWriter) -> None:
        self._writer = writer

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if not spans:
            return SpanExportResult.SUCCESS
        records = [self._to_record(s) for s in spans]
        try:
            self._writer.write_batch(records)
            return SpanExportResult.SUCCESS
        except Exception:
            logger.warning("Falha ao gravar spans no Bronze.", exc_info=True)
            return SpanExportResult.FAILURE

    @staticmethod
    def _to_record(span: ReadableSpan) -> dict[str, Any]:
        ctx = span.get_span_context()
        parent = span.parent
        attrs = dict(span.attributes or {})
        resource_attrs = dict(span.resource.attributes) if span.resource else {}
        start_ns = span.start_time or 0
        end_ns = span.end_time or 0
        status = span.status.status_code.name if span.status else "UNSET"
        return {
            "span_id": format(ctx.span_id, "016x") if ctx else "",
            "trace_id": format(ctx.trace_id, "032x") if ctx else "",
            "parent_span_id": format(parent.span_id, "016x") if parent else None,
            "service": resource_attrs.get(SERVICE_NAME, ""),
            "operation": span.name,
            "start_ts": _ns_to_iso(start_ns),
            "end_ts": _ns_to_iso(end_ns),
            "duration_ms": max(0, (end_ns - start_ns) // 1_000_000),
            "status": status,
            "project_id": attrs.get("project.id"),
            "tool_name": attrs.get("tool.name"),  # gravado por _with_tracing em toda tool MCP
            "user_id": attrs.get("user.id"),  # gravado por AuthContextMiddleware em todo request de API
            "request_id": attrs.get("request.id"),  # idem
            "skill_id": None,  # normalize_span_record extrai de `operation` quando ausente
        }

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True
