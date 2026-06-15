"""Backward-compat shim — moved to adapters/blob_storage/sharepoint.py."""
from .blob_storage.sharepoint import SharePointBlobStorage, SharePointCredential, StorageConcurrencyError  # noqa: F401
__all__ = ["SharePointBlobStorage", "SharePointCredential", "StorageConcurrencyError"]
