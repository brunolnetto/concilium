"""Testes para BronzeMetricExporter — grava métricas OTel no Bronze (fix: metrics nunca chegavam a Bronze)."""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import MetricExporter, MetricExportResult, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from concilium.infrastructure.observability.bronze_metric_exporter import BronzeMetricExporter
from concilium.infrastructure.observability.bronze_writer import BronzeWriter


@contextmanager
def _otel_sdk_enabled():
    """MeterProvider.__init__ lê OTEL_SDK_DISABLED uma única vez, e o ambiente de teste
    (TEST_ENV) o define como "true" globalmente — sem isso, nenhuma métrica é coletada."""
    previous = os.environ.get("OTEL_SDK_DISABLED")
    os.environ["OTEL_SDK_DISABLED"] = "false"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OTEL_SDK_DISABLED", None)
        else:
            os.environ["OTEL_SDK_DISABLED"] = previous


def _collect_metrics_data(instrument_fn):
    """Cria um MeterProvider real com um único reader manual, aplica instrument_fn(meter) e
    retorna o MetricsData coletado — usado para gerar Sum/Gauge/Histogram reais do SDK."""
    captured = []

    class _Capture(MetricExporter):
        def export(self, metrics_data, timeout_millis=10000, **kw):
            captured.append(metrics_data)
            return MetricExportResult.SUCCESS

        def shutdown(self, timeout_millis=30000, **kw):
            return None

        def force_flush(self, timeout_millis=10000):
            return True

    with _otel_sdk_enabled():
        reader = PeriodicExportingMetricReader(_Capture(), export_interval_millis=100_000)
        provider = MeterProvider(resource=Resource({SERVICE_NAME: "concilium"}), metric_readers=[reader])
        meter = provider.get_meter("test")
        instrument_fn(meter)
        reader.collect()
        provider.shutdown()
    return captured[-1]


class TestBronzeMetricExporterCounter:
    def test_writes_counter_data_point(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "metrics")
        exporter = BronzeMetricExporter(writer)

        def use(meter):
            counter = meter.create_counter("concilium.mcp.tool.calls")
            counter.add(1, {"tool": "ping", "status": "OK"})

        metrics_data = _collect_metrics_data(use)
        result = exporter.export(metrics_data)

        assert result == MetricExportResult.SUCCESS
        storage.gravar_blob.assert_called_once()
        path, content = storage.gravar_blob.call_args[0]
        assert "observability/bronze/metrics/" in path

        record = json.loads(content.decode("utf-8").strip())
        assert record["metric_name"] == "concilium.mcp.tool.calls"
        assert record["value"] == 1
        assert record["labels"] == {"tool": "ping", "status": "OK"}
        assert record["service"] == "concilium"
        assert record["ts"]


class TestBronzeMetricExporterGauge:
    def test_writes_gauge_data_point(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "metrics")
        exporter = BronzeMetricExporter(writer)

        def use(meter):
            gauge = meter.create_gauge("concilium.project.margem_pct")
            gauge.set(12.5, {"project.id": "p1"})

        metrics_data = _collect_metrics_data(use)
        exporter.export(metrics_data)

        path, content = storage.gravar_blob.call_args[0]
        record = json.loads(content.decode("utf-8").strip())
        assert record["metric_name"] == "concilium.project.margem_pct"
        assert record["value"] == pytest.approx(12.5)
        assert record["labels"] == {"project.id": "p1"}


class TestBronzeMetricExporterHistogram:
    def test_writes_histogram_as_average_with_count_and_sum_in_labels(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "metrics")
        exporter = BronzeMetricExporter(writer)

        def use(meter):
            hist = meter.create_histogram("concilium.pipeline.skill.duration_ms")
            hist.record(100, {"skill": "05"})
            hist.record(200, {"skill": "05"})

        metrics_data = _collect_metrics_data(use)
        exporter.export(metrics_data)

        path, content = storage.gravar_blob.call_args[0]
        record = json.loads(content.decode("utf-8").strip())
        assert record["metric_name"] == "concilium.pipeline.skill.duration_ms"
        assert record["value"] == pytest.approx(150.0)  # média = sum(300)/count(2)
        assert record["labels"]["_count"] == 2
        assert record["labels"]["_sum"] == pytest.approx(300.0)


class TestBronzeMetricExporterEdgeCases:
    def test_no_data_points_is_noop(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "metrics")
        exporter = BronzeMetricExporter(writer)

        empty = MagicMock()
        empty.resource_metrics = []
        result = exporter.export(empty)

        assert result == MetricExportResult.SUCCESS
        storage.gravar_blob.assert_not_called()

    def test_storage_failure_returns_failure_without_raising(self):
        storage = MagicMock()
        storage.gravar_blob.side_effect = RuntimeError("storage down")
        writer = BronzeWriter(storage, "metrics")
        exporter = BronzeMetricExporter(writer)

        def use(meter):
            counter = meter.create_counter("concilium.mcp.tool.calls")
            counter.add(1)

        metrics_data = _collect_metrics_data(use)
        result = exporter.export(metrics_data)

        assert result == MetricExportResult.FAILURE

    def test_shutdown_and_force_flush_are_safe_noops(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "metrics")
        exporter = BronzeMetricExporter(writer)

        exporter.shutdown()
        assert exporter.force_flush() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
