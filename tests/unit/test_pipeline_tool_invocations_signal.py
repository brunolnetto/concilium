"""Testes de integração — tool_invocations como 4º signal_type do pipeline Bronze→Silver.

Cobre o wiring em pipeline.py (_NORMALIZERS, _SIGNAL_TYPES do scheduler), não a
lógica de normalização em si (já coberta em test_silver_normalizer_tool_invocations.py)
nem o dual-write (já coberto em test_tool_invocation_bronze_dualwrite.py).
"""

from __future__ import annotations

import json

import pytest

from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.observability.pipeline import (
    _NORMALIZERS,
    _SIGNAL_TYPES,
    ObservabilityWorker,
)


class TestToolInvocationsNormalizerWiring:
    def test_tool_invocations_normalizer_registered(self):
        from concilium.infrastructure.observability.silver_normalizer import normalize_tool_invocation_record

        assert _NORMALIZERS["tool_invocations"] is normalize_tool_invocation_record


class TestToolInvocationsInSchedulerSignalTypes:
    def test_tool_invocations_is_a_scheduled_signal(self):
        assert "tool_invocations" in _SIGNAL_TYPES


class TestObservabilityWorkerToolInvocationsEndToEnd:
    def test_bronze_tool_invocation_flows_into_silver(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        bronze_record = {
            "id": "inv-1",
            "tool_name": "listar_projetos",
            "input_keys": ["a"],
            "user_id": "u1",
            "tenant_id": "tenant-x",
            "status": "success",
            "started_at": "2026-07-20T10:00:00Z",
            "finished_at": "2026-07-20T10:00:01Z",
            "error_type": None,
            "device_id": "device-1",
            "mcp_session_id": "sess-abc",
        }
        storage.gravar_blob(
            "observability/bronze/tool_invocations/2026-07-20/batch1.ndjson",
            (json.dumps(bronze_record) + "\n").encode("utf-8"),
        )

        worker = ObservabilityWorker(storage)
        result = worker.run(signal_type="tool_invocations")

        assert result == {"blobs_processed": 1, "records_processed": 1}

        silver_records = worker.read_silver("tool_invocations")
        assert len(silver_records) == 1
        assert silver_records[0]["event_id"] == "inv-1"
        assert silver_records[0]["tool_name"] == "listar_projetos"
        assert silver_records[0]["device_id"] == "device-1"

    def test_incremental_fast_forward_skips_already_processed_blob(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        storage.gravar_blob(
            "observability/bronze/tool_invocations/2026-07-20/batch1.ndjson",
            (json.dumps({"id": "inv-1", "tool_name": "ping", "status": "success"}) + "\n").encode("utf-8"),
        )

        worker = ObservabilityWorker(storage)
        worker.run(signal_type="tool_invocations")
        second = worker.run(signal_type="tool_invocations")

        assert second == {"blobs_processed": 0, "records_processed": 0}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
