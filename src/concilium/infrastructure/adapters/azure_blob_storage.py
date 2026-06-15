"""Backward-compat shim — moved to adapters/blob_storage/azure.py."""
from .blob_storage.azure import AzureBlobStorage  # noqa: F401
__all__ = ["AzureBlobStorage"]
