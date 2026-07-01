"""Coverage batch 20 — tool_invocations repo, campaign_store small gaps."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# tool_invocations/repository.py lines 100-101: ValueError path in _max_size
# ---------------------------------------------------------------------------


class TestMaxSizeValueError:
    def test_returns_default_when_env_var_is_not_integer(self):
        """Lines 100-101: env var set to non-integer → int(raw) raises ValueError → return 10_000."""
        with patch.dict(os.environ, {"CONCILIUM__TOOL_INVOCATIONS_MAX_SIZE": "not-a-number"}):
            # Reload the function to pick up patched env
            from concilium.application.tool_invocations.repository import _max_size

            result = _max_size()
            assert result == 10_000

    def test_returns_parsed_int_for_valid_value(self):
        """Normal path: valid integer env var → return max(0, int(raw))."""
        with patch.dict(os.environ, {"CONCILIUM__TOOL_INVOCATIONS_MAX_SIZE": "500"}):
            from concilium.application.tool_invocations.repository import _max_size

            result = _max_size()
            assert result == 500


# ---------------------------------------------------------------------------
# campaign_store.py line 188: non-LocalBlobStorage → run_path returns logical Path
# campaign_store.py line 240->242: save_meta with gerado_em already present → if False
# campaign_store.py line 269: load_config returns None when no current run
# ---------------------------------------------------------------------------


def _make_store_with_mock_storage():
    """Create CampaignRunStore backed by a MagicMock (not LocalBlobStorage)."""
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore

    mock_storage = MagicMock()
    # Ensure it's not an instance of LocalBlobStorage (MagicMock isn't)
    mock_storage.blob_existe.return_value = False
    mock_storage.listar_blobs.return_value = []

    store = CampaignRunStore(storage=mock_storage, prefix="PROJ-01/campaigns")
    return store, mock_storage


class TestCampaignRunStoreMockBackend:
    def test_run_path_uses_logical_path_for_non_local_backend(self):
        """Line 188: storage is not LocalBlobStorage → return Path(prefix)/runs/run."""
        from pathlib import Path

        store, _ = _make_store_with_mock_storage()
        result = store.run_path("run-001")

        assert isinstance(result, Path)
        assert "run-001" in str(result)
        assert "runs" in str(result)

    def test_save_meta_skips_adding_gerado_em_when_present(self):
        """Line 240->242: meta already has 'gerado_em' → if False → write directly."""
        store, mock_storage = _make_store_with_mock_storage()

        meta_with_timestamp = {"status": "concluida", "gerado_em": "2026-06-30T10:00:00Z"}
        store.save_meta("run-001", meta_with_timestamp)

        # _write_json should have been called once
        mock_storage.gravar_blob.assert_called_once()
        # The written content should contain the original gerado_em unchanged
        call_args = mock_storage.gravar_blob.call_args
        import json

        written = json.loads(call_args[0][1].decode("utf-8"))
        assert written["gerado_em"] == "2026-06-30T10:00:00Z"

    def test_load_config_returns_none_when_no_current_run(self):
        """Line 269: current_run() returns None → load_config returns None."""
        store, mock_storage = _make_store_with_mock_storage()
        # blob_existe returns False → current_run returns None → load_config → None
        result = store.load_config()
        assert result is None
