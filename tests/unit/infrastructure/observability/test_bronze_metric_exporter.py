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
    retorna o MetricsData coletado — usado para gerar Sum/Gauge/Histogram reais do SDK.

    Desde opentelemetry-sdk 1.41, todo MetricReader instrumenta a si mesmo com uma
    métrica de auto-diagnóstico (`otel.sdk.metric_reader.collection.duration`,
    escopo "opentelemetry-sdk") — mas essa duração só pode ser reportada no ciclo
    de export *seguinte* ao `collect()` que ela mede, então só aparece no flush
    final de `provider.shutdown()`. Esse mesmo flush final também **reexporta**
    instrumentos cumulativos (Counter/Histogram) que já tinham saído em
    `reader.collect()`, então usar o último `export()` capturado (`captured[-1]`)
    tanto duplicava dados reais quanto, no caso do Gauge (sem novo valor entre os
    dois ciclos), retornava só a métrica interna do SDK. O primeiro `export()`
    (o de `reader.collect()`) é o único que reflete exatamente a chamada de
    `instrument_fn`, sem a métrica interna do SDK nem duplicação.
    """
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
    return captured[0]


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


class TestNsToIso:
    def test_zero_nanoseconds_returns_empty_string(self):
        from concilium.infrastructure.observability.bronze_metric_exporter import _ns_to_iso

        assert _ns_to_iso(0) == ""


class TestToRecordsEdgeCases:
    def test_resource_metrics_without_resource_defaults_service_to_empty(self):
        """Quando resource_metrics.resource é falsy (None), `service` fica '' em vez de propagar erro."""
        dp = MagicMock()
        dp.attributes = {}
        dp.time_unix_nano = 0
        dp.value = 1.0

        metric = MagicMock()
        metric.name = "concilium.mcp.tool.calls"
        metric.data.data_points = [dp]

        scope_metrics = MagicMock()
        scope_metrics.metrics = [metric]

        resource_metrics = MagicMock()
        resource_metrics.resource = None
        resource_metrics.scope_metrics = [scope_metrics]

        metrics_data = MagicMock()
        metrics_data.resource_metrics = [resource_metrics]

        records = list(BronzeMetricExporter._to_records(metrics_data))

        assert len(records) == 1
        assert records[0]["service"] == ""

    def test_otel_sdk_self_diagnostic_metric_is_skipped(self):
        """Métricas com prefixo 'otel.sdk.' (auto-diagnóstico do SDK) não devem virar records."""
        metric = MagicMock()
        metric.name = "otel.sdk.metric_reader.collection.duration"

        scope_metrics = MagicMock()
        scope_metrics.metrics = [metric]

        resource_metrics = MagicMock()
        resource_metrics.resource.attributes = {"service.name": "concilium"}
        resource_metrics.scope_metrics = [scope_metrics]

        metrics_data = MagicMock()
        metrics_data.resource_metrics = [resource_metrics]

        records = list(BronzeMetricExporter._to_records(metrics_data))

        assert records == []


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
