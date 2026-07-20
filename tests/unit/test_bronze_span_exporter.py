"""Testes para BronzeSpanExporter — grava spans OTel no Bronze (fix: traces nunca chegavam a Bronze)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export import SpanExportResult as _RealSpanExportResult

from concilium.infrastructure.observability.bronze_span_exporter import BronzeSpanExporter
from concilium.infrastructure.observability.bronze_writer import BronzeWriter


@contextmanager
def _otel_sdk_enabled():
    """TracerProvider.__init__ lê OTEL_SDK_DISABLED uma única vez (opentelemetry-sdk `_disabled`),
    e o ambiente de teste (TEST_ENV) o define como "true" globalmente — sem isso, qualquer
    TracerProvider construído durante a suíte vira NoOpTracer e nenhum span é gerado."""
    previous = os.environ.get("OTEL_SDK_DISABLED")
    os.environ["OTEL_SDK_DISABLED"] = "false"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("OTEL_SDK_DISABLED", None)
        else:
            os.environ["OTEL_SDK_DISABLED"] = previous


def _make_span(name="concilium.skill.05", project_id=None):
    """Gera um ReadableSpan real via um TracerProvider descartável, para exercitar o schema completo."""
    captured = []

    class _Capture:
        def export(self, spans):
            captured.extend(spans)
            return _RealSpanExportResult.SUCCESS

        def shutdown(self):
            return None

        def force_flush(self, timeout_millis=30000):
            return True

    with _otel_sdk_enabled():
        provider = TracerProvider(resource=Resource({SERVICE_NAME: "concilium"}))
        provider.add_span_processor(SimpleSpanProcessor(_Capture()))
        tracer = provider.get_tracer("test")
        with tracer.start_as_current_span(name) as span:
            if project_id:
                span.set_attribute("project.id", project_id)
        provider.shutdown()
    return captured[0]


class TestBronzeSpanExporterSchema:
    def test_writes_expected_bronze_schema(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "traces")
        exporter = BronzeSpanExporter(writer)

        span = _make_span(project_id="AGIS")
        result = exporter.export([span])

        assert result == _RealSpanExportResult.SUCCESS
        storage.gravar_blob.assert_called_once()
        path, content = storage.gravar_blob.call_args[0]
        assert "observability/bronze/traces/" in path

        import json

        record = json.loads(content.decode("utf-8").strip())
        ctx = span.get_span_context()
        assert record["span_id"] == format(ctx.span_id, "016x")
        assert record["trace_id"] == format(ctx.trace_id, "032x")
        assert record["parent_span_id"] is None
        assert record["service"] == "concilium"
        assert record["operation"] == "concilium.skill.05"
        assert record["status"] == "UNSET"
        assert record["project_id"] == "AGIS"
        assert isinstance(record["duration_ms"], int)
        assert record["start_ts"] and record["end_ts"]

    def test_no_project_id_yields_none(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "traces")
        exporter = BronzeSpanExporter(writer)

        span = _make_span()
        exporter.export([span])

        path, content = storage.gravar_blob.call_args[0]
        import json

        record = json.loads(content.decode("utf-8").strip())
        assert record["project_id"] is None

    def test_empty_batch_is_noop(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "traces")
        exporter = BronzeSpanExporter(writer)

        result = exporter.export([])

        assert result == _RealSpanExportResult.SUCCESS
        storage.gravar_blob.assert_not_called()

    def test_storage_failure_returns_failure_without_raising(self):
        storage = MagicMock()
        storage.gravar_blob.side_effect = RuntimeError("storage down")
        writer = BronzeWriter(storage, "traces")
        exporter = BronzeSpanExporter(writer)

        span = _make_span()
        result = exporter.export([span])

        assert result == _RealSpanExportResult.FAILURE

    def test_shutdown_and_force_flush_are_safe_noops(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "traces")
        exporter = BronzeSpanExporter(writer)

        exporter.shutdown()
        assert exporter.force_flush() is True


class TestBronzeSpanExporterParent:
    def test_child_span_records_parent_span_id(self):
        storage = MagicMock()
        writer = BronzeWriter(storage, "traces")
        exporter = BronzeSpanExporter(writer)

        captured = []

        class _Capture:
            def export(self, spans):
                captured.extend(spans)
                return _RealSpanExportResult.SUCCESS

            def shutdown(self):
                return None

            def force_flush(self, timeout_millis=30000):
                return True

        with _otel_sdk_enabled():
            provider = TracerProvider(resource=Resource({SERVICE_NAME: "concilium"}))
            provider.add_span_processor(SimpleSpanProcessor(_Capture()))
            tracer = provider.get_tracer("test")
            with tracer.start_as_current_span("parent") as parent:
                parent_ctx = parent.get_span_context()
                with tracer.start_as_current_span("child"):
                    pass
            provider.shutdown()

        child_span = next(s for s in captured if s.name == "child")
        exporter.export([child_span])

        import json

        path, content = storage.gravar_blob.call_args[0]
        record = json.loads(content.decode("utf-8").strip())
        assert record["parent_span_id"] == format(parent_ctx.span_id, "016x")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
