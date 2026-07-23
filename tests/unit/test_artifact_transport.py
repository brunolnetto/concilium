"""Tests for artifact_transport, pdf_renderer, settings, project storage, catalog mixin,
telemetry, and 04-cronograma/_skill_helpers/_dag."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── application/services/artifact/artifact_transport.py (10 missing) ─────────


class TestBlobPortFromEnv:
    """Cover _blob_port_from_env branches (lines 121-133)."""

    def test_azure_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        mock_storage = MagicMock()
        with patch(
            "concilium.infrastructure.adapters.blob_storage.azure.AzureBlobStorage.from_env", return_value=mock_storage
        ):
            result = _blob_port_from_env("azure")
        assert result is mock_storage

    def test_azure_blob_alias(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.azure.AzureBlobStorage.from_env", return_value=MagicMock()
        ):
            result = _blob_port_from_env("azure_blob")
        assert result is not None

    def test_sharepoint_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.sharepoint.SharePointBlobStorage.from_env",
            return_value=MagicMock(),
        ):
            result = _blob_port_from_env("sharepoint")
        assert result is not None

    def test_gdrive_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.gdrive.GoogleDriveBlobStorage.from_env",
            return_value=MagicMock(),
        ):
            result = _blob_port_from_env("gdrive")
        assert result is not None

    def test_s3_backend(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with patch(
            "concilium.infrastructure.adapters.blob_storage.s3.S3BlobStorage.from_env", return_value=MagicMock()
        ):
            result = _blob_port_from_env("s3")
        assert result is not None

    def test_unknown_backend_raises(self):
        from concilium.application.services.artifact.artifact_transport import _blob_port_from_env

        with pytest.raises(ValueError, match="desconhecido"):
            _blob_port_from_env("unknown-backend")



