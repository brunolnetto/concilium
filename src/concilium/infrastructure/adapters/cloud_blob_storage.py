"""Backward-compat shim — moved to adapters/blob_storage/cloud.py."""
from .blob_storage.cloud import CloudBlobStorageAdapter  # noqa: F401
__all__ = ["CloudBlobStorageAdapter"]
