"""Backward-compat shim — moved to adapters/blob_storage/gdrive.py."""
from .blob_storage.gdrive import GoogleDriveBlobStorage  # noqa: F401
__all__ = ["GoogleDriveBlobStorage"]
