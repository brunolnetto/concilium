"""Backward-compat shim — moved to adapters/blob_storage/s3.py."""
from .blob_storage.s3 import S3BlobStorage  # noqa: F401
__all__ = ["S3BlobStorage"]
