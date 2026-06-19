"""Tests for blob storage adapters in the blob_storage/ subdirectory."""

from __future__ import annotations


class TestAzureBlobStorage:
    def test_import_azure_blob_storage(self):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage  # noqa: F401

        assert AzureBlobStorage is not None


class TestCloudBlobStorage:
    def test_import_cloud_blob_storage(self):
        from concilium.infrastructure.adapters.blob_storage.cloud import CloudBlobStorageAdapter  # noqa: F401

        assert CloudBlobStorageAdapter is not None


class TestGdriveBlobStorage:
    def test_import_gdrive_blob_storage(self):
        from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage  # noqa: F401

        assert GoogleDriveBlobStorage is not None


class TestLocalBlobStorage:
    def test_import_local_blob_storage(self):
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage  # noqa: F401

        assert LocalBlobStorage is not None


class TestS3BlobStorage:
    def test_import_s3_blob_storage(self):
        from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage  # noqa: F401

        assert S3BlobStorage is not None


class TestSharePointBlobStorage:
    def test_import_sharepoint_blob_storage(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage  # noqa: F401

        assert SharePointBlobStorage is not None

    def test_sharepoint_credential_imported(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointCredential  # noqa: F401

        assert SharePointCredential is not None

    def test_sharepoint_concurrency_error_imported(self):
        from concilium.infrastructure.adapters.blob_storage.sharepoint import StorageConcurrencyError  # noqa: F401

        assert StorageConcurrencyError is not None
