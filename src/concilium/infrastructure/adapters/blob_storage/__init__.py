"""Blob storage adapters — one module per backend.

Public API (all backends re-exported):
    from concilium.infrastructure.adapters.blob_storage import LocalBlobStorage
    from concilium.infrastructure.adapters.blob_storage import SharePointBlobStorage
    ...
"""

from .azure import AzureBlobStorage
from .cloud import CloudBlobStorageAdapter
from .gdrive import GoogleDriveBlobStorage
from .local import LocalBlobStorage
from .s3 import S3BlobStorage
from .sharepoint import SharePointBlobStorage, SharePointCredential, StorageConcurrencyError

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
