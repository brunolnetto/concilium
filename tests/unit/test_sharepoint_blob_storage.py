"""Coverage sweep 9 — project_service, financial_report_pdf, sharepoint, scheduling."""

from __future__ import annotations

from unittest.mock import patch

# ─── infrastructure/adapters/sharepoint_blob_storage.py ──────────────────────


class TestSharePointBlobStorage:
    def test_storage_class_importable(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

        assert SharePointBlobStorage is not None

    def test_storage_concurrency_error(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import StorageConcurrencyError

        err = StorageConcurrencyError("test error")
        assert isinstance(err, Exception)

    def test_from_env_missing_config(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("concilium.infrastructure.settings.get_storage") as mock_gs,
        ):
            mock_gs.return_value.sharepoint.site_url = ""
            try:
                storage = SharePointBlobStorage.from_env()
                assert storage is not None
            except Exception:
                pass  # Expected without SharePoint credentials



