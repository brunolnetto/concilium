"""Backward-compat shim — moved to adapters/blob_storage/local.py."""
from .blob_storage.local import LocalBlobStorage  # noqa: F401
__all__ = ["LocalBlobStorage"]
