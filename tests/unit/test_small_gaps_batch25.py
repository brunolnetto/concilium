"""Coverage batch 25 — pipeline, gold_aggregator, storage_project_repository
small gaps + telemetry/jwt_config pragmas."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
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
# gold_aggregator.py line 37->36: blank line in blob → if line.strip(): False
# ---------------------------------------------------------------------------


class TestGoldAggregatorBlankLines:
    def test_read_silver_skips_blank_lines(self):
        """Line 37->36: blank line in blob → if line.strip(): False → back to loop."""
        from concilium.infrastructure.observability.gold_aggregator import GoldAggregator

        mock_storage = MagicMock()
        blob_content = '\n{"event_id": "G1"}\n\n{"event_id": "G2"}\n'
        mock_storage.listar_blobs.return_value = ["silver/logs/2026-06-30/records.ndjson"]
        mock_storage.ler_blob.return_value = blob_content.encode("utf-8")

        agg = GoldAggregator(mock_storage)
        result = agg._read_silver("logs")
        assert len(result) == 2  # blank lines skipped


# ---------------------------------------------------------------------------
# storage_project_repository.py line 169-170: pragma added (try: pass never raises)
# storage_project_repository.py line 391->393: project_id already in index → if False
# ---------------------------------------------------------------------------


class TestStorageProjectRepositoryUpdateIndex:
    def test_update_index_skips_append_when_id_already_present(self):
        """Line 391->393: project_id already in index → if False → just write."""
        from concilium.infrastructure.storage.storage_project_repository import (
            StorageProjectRepository,
        )

        mock_storage = MagicMock()
        existing_index = {"project_ids": ["PROJ-EXISTING"]}
        mock_storage.ler_blob.return_value = json.dumps(existing_index).encode("utf-8")

        repo = StorageProjectRepository(mock_storage)
        repo._update_index("PROJ-EXISTING")

        # gravar_blob called once — the list was NOT extended
        mock_storage.gravar_blob.assert_called_once()
        written = json.loads(mock_storage.gravar_blob.call_args[0][1].decode("utf-8"))
        assert written["project_ids"] == ["PROJ-EXISTING"]  # no duplicate

    def test_update_index_appends_new_id(self):
        """Normal path: project_id not in index → append → write."""
        from concilium.infrastructure.storage.storage_project_repository import (
            StorageProjectRepository,
        )

        mock_storage = MagicMock()
        existing_index = {"project_ids": ["PROJ-OLD"]}
        mock_storage.ler_blob.return_value = json.dumps(existing_index).encode("utf-8")

        repo = StorageProjectRepository(mock_storage)
        repo._update_index("PROJ-NEW")

        written = json.loads(mock_storage.gravar_blob.call_args[0][1].decode("utf-8"))
        assert "PROJ-NEW" in written["project_ids"]
        assert "PROJ-OLD" in written["project_ids"]
