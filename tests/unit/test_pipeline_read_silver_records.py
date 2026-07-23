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


from unittest.mock import MagicMock  # noqa: E402

# pipeline.py line 62->60: _read_ndjson with blank lines → if line: False
# pipeline.py line 82->81: _upsert_silver existing blob has blank lines
# pipeline.py line 112->111: read_silver blob has blank lines
# ---------------------------------------------------------------------------


def _make_worker():
    """ObservabilityWorker backed by a MagicMock storage."""
    from concilium.infrastructure.observability.pipeline import ObservabilityWorker

    mock_storage = MagicMock()
    return ObservabilityWorker(mock_storage), mock_storage


class TestObservabilityWorkerBlankLines:
    def test_read_ndjson_skips_blank_lines(self):
        """Line 62->60: blank line in NDJSON → if line: False → back to loop."""
        worker, mock_storage = _make_worker()

        content = '\n{"event_id": "E1", "ts": 1}\n\n{"event_id": "E2", "ts": 2}\n'
        mock_storage.ler_blob.return_value = content.encode("utf-8")

        result = worker._read_ndjson("some/path.ndjson")
        assert len(result) == 2  # blank lines skipped, 2 valid records

    def test_upsert_silver_skips_blank_lines_in_existing(self):
        """Line 82->81: blank line in existing silver blob → if line.strip(): False → skip."""
        worker, mock_storage = _make_worker()

        existing_content = '\n{"event_id": "EX-1", "ts": 1}\n\n'
        mock_storage.ler_blob.return_value = existing_content.encode("utf-8")

        new_records = [{"event_id": "NEW-1", "ts": 2}]
        worker._upsert_silver("logs", new_records, "2026-06-18")

        # gravar_blob should have been called once with merged content
        mock_storage.gravar_blob.assert_called_once()
        written = mock_storage.gravar_blob.call_args[0][1].decode("utf-8")
        assert "EX-1" in written
        assert "NEW-1" in written

    def test_read_silver_skips_blank_lines(self):
        """Line 112->111: blank line in silver blob → if line.strip(): False → skip."""
        worker, mock_storage = _make_worker()

        blob_content = '\n{"event_id": "S1"}\n\n{"event_id": "S2"}\n'
        mock_storage.listar_blobs.return_value = ["silver/logs/today/records.ndjson"]
        mock_storage.ler_blob.return_value = blob_content.encode("utf-8")

        result = worker.read_silver("logs")
        assert len(result) == 2


# ---------------------------------------------------------------------------

