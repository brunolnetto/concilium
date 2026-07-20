"""BronzeMetricExporter — grava métricas OTel no Bronze (extensão de ADR-112 F1 a metrics).

Mesma motivação de bronze_span_exporter.py: antes deste exporter, métricas só
saíam via OTLP/console, nunca chegavam à camada Bronze/Silver/Gold. Roda em
paralelo ao reader OTLP/console já configurado em `_setup_metrics`, sempre
que há storage de sistema disponível.
"""

from __future__ import annotations

import datetime
import logging
from collections.abc import Iterator
from typing import Any

from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, MetricsData

from concilium.infrastructure.observability.bronze_writer import BronzeWriter

logger = logging.getLogger(__name__)


def _ns_to_iso(ns: int) -> str:
    if not ns:
        return ""
    return datetime.datetime.fromtimestamp(ns / 1_000_000_000, tz=datetime.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class BronzeMetricExporter(MetricExporter):
    """Exporta data points para `observability/bronze/metrics/`.

    Schema de saída compatível com `silver_normalizer.normalize_metric_record`.
    """

    def __init__(self, writer: BronzeWriter) -> None:
        super().__init__()
        self._writer = writer

    def export(self, metrics_data: MetricsData, timeout_millis: float = 10000, **kwargs: Any) -> MetricExportResult:
        records = list(self._to_records(metrics_data))
        if not records:
            return MetricExportResult.SUCCESS
        try:
            self._writer.write_batch(records)
            return MetricExportResult.SUCCESS
        except Exception:
            logger.warning("Falha ao gravar métricas no Bronze.", exc_info=True)
            return MetricExportResult.FAILURE

    @staticmethod
    def _to_records(metrics_data: MetricsData) -> Iterator[dict[str, Any]]:
        for resource_metrics in metrics_data.resource_metrics:
            service = ""
            if resource_metrics.resource:
                service = resource_metrics.resource.attributes.get("service.name", "")
            for scope_metrics in resource_metrics.scope_metrics:
                for metric in scope_metrics.metrics:
                    yield from BronzeMetricExporter._points_for_metric(metric, service)

    @staticmethod
    def _points_for_metric(metric: Any, service: str) -> Iterator[dict[str, Any]]:
        for dp in getattr(metric.data, "data_points", []):
            labels = dict(getattr(dp, "attributes", None) or {})
            ts_ns = getattr(dp, "time_unix_nano", 0)
            if hasattr(dp, "value"):
                value = float(dp.value)
            else:
                # HistogramDataPoint não tem `.value` — usa a média do intervalo
                # (sum/count) como valor representativo; sum/count completos vão
                # para labels, para não perder fidelidade.
                count = getattr(dp, "count", 0) or 0
                total = getattr(dp, "sum", 0.0) or 0.0
                value = (total / count) if count else 0.0
                labels["_count"] = count
                labels["_sum"] = total
            yield {
                "metric_name": metric.name,
                "ts": _ns_to_iso(ts_ns),
                "value": value,
                "labels": labels,
                "service": service,
            }

    def force_flush(self, timeout_millis: float = 10000) -> bool:
        return True

    def shutdown(self, timeout_millis: float = 30000, **kwargs: Any) -> None:
        return None
