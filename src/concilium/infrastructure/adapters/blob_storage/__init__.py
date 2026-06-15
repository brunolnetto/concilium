"""Blob storage adapters — one module per backend.

Public API (all backends re-exported):
    from concilium.infrastructure.adapters.blob_storage import LocalBlobStorage
    from concilium.infrastructure.adapters.blob_storage import SharePointBlobStorage
    ...
"""
from .local import LocalBlobStorage
from .azure import AzureBlobStorage
from .sharepoint import SharePointBlobStorage, SharePointCredential, StorageConcurrencyError
from .s3 import S3BlobStorage
from .gdrive import GoogleDriveBlobStorage
from .cloud import CloudBlobStorageAdapter

__all__ = [
    "LocalBlobStorage",
    "AzureBlobStorage",
    "SharePointBlobStorage",
    "SharePointCredential",
    "StorageConcurrencyError",
    "S3BlobStorage",
    "GoogleDriveBlobStorage",
    "CloudBlobStorageAdapter",
]
