"""Testes para pipeline.read_silver_records — extraído de 3 cópias idênticas
(ObservabilityWorker.read_silver, GoldAggregator._read_silver,
CrossDomainBuilder._read_silver_logs) para servir também os cubos novos."""

from __future__ import annotations

import json

import pytest

from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage
from concilium.infrastructure.observability.pipeline import ObservabilityWorker, read_silver_records


class TestReadSilverRecords:
    def test_empty_storage_returns_empty_list(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        assert read_silver_records(storage, "traces") == []

    def test_reads_and_deduplicates_across_files(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        storage.gravar_blob(
            "observability/silver/traces/2026-07-21/records.ndjson",
            (json.dumps({"span_id": "a", "duration_ms": 100}) + "\n").encode("utf-8"),
        )
        storage.gravar_blob(
            "observability/silver/traces/2026-07-22/records.ndjson",
            (
                json.dumps({"span_id": "a", "duration_ms": 100}) + "\n" + json.dumps({"span_id": "b"}) + "\n"
            ).encode("utf-8"),
        )

        records = read_silver_records(storage, "traces")

        assert len(records) == 2
        assert {r["span_id"] for r in records} == {"a", "b"}

    def test_malformed_blob_is_skipped_not_raised(self, tmp_path):
        storage = LocalBlobStorage(tmp_path)
        storage.gravar_blob("observability/silver/logs/2026-07-21/records.ndjson", b"not valid ndjson at all {{{")

        assert read_silver_records(storage, "logs") == []

    def test_observability_worker_read_silver_delegates_to_shared_function(self, tmp_path):
        """ObservabilityWorker.read_silver deve ser um wrapper fino, não uma cópia."""
        storage = LocalBlobStorage(tmp_path)
        storage.gravar_blob(
            "observability/silver/metrics/2026-07-21/records.ndjson",
            (json.dumps({"metric_name": "x", "ts": "2026-07-21T10:00:00Z"}) + "\n").encode("utf-8"),
        )

        worker = ObservabilityWorker(storage)

        assert worker.read_silver("metrics") == read_silver_records(storage, "metrics")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
