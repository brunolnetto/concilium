from __future__ import annotations

import os
from pathlib import Path

from concilium.application.services.project_repository import ProjectRepository
from concilium.infrastructure.settings import get_storage

from .file_project_repository import FileProjectRepository

DEFAULT_STORE_BACKEND = "filesystem"
_BACKEND_ALIASES: dict[str, str] = {
    "filesystem": "filesystem",
    "local_json": "filesystem",
    "local-json": "filesystem",
    "local": "filesystem",
    "sharepoint": "sharepoint",
    "s3": "s3",
    "azure": "azure",
    "azure_blob": "azure",
    "gdrive": "gdrive",
    "google_drive": "gdrive",
    "drive": "gdrive",
}


def _projects_prefix() -> str:
    value = get_storage().projects_prefix.strip().strip("/")
    return value or "projetos"


def _build_sharepoint_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.sharepoint_blob_storage import SharePointBlobStorage

    from .storage_project_repository import StorageProjectRepository

    cache_dir_raw = get_storage().sharepoint.cache_dir.strip()
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None
    storage = SharePointBlobStorage.from_env(cache_dir=cache_dir)
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())


def _build_s3_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.s3_blob_storage import S3BlobStorage

    from .storage_project_repository import StorageProjectRepository

    storage = S3BlobStorage.from_env()
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())


def _build_azure_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.azure_blob_storage import AzureBlobStorage

    from .storage_project_repository import StorageProjectRepository

    storage = AzureBlobStorage.from_env()
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())


def _build_gdrive_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.gdrive_blob_storage import GoogleDriveBlobStorage

    from .storage_project_repository import StorageProjectRepository

    storage = GoogleDriveBlobStorage.from_env()
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())


def resolve_store_backend() -> str:
    """Resolve backend name for project repository from environment."""
    value = (get_storage().backend or DEFAULT_STORE_BACKEND).strip().lower()
    value = value or DEFAULT_STORE_BACKEND
    return _BACKEND_ALIASES.get(value, value)


def build_project_repository(projects_root: Path) -> ProjectRepository:
    """Build ProjectRepository according to CONCILIUM__STORE_BACKEND.

    Current supported backends:
    - filesystem/local_json (default)
    - sharepoint
    - s3
    """
    backend = resolve_store_backend()
    if backend == "filesystem":
        return FileProjectRepository(projects_root)
    if backend == "sharepoint":
        return _build_sharepoint_repository()
    if backend == "s3":
        return _build_s3_repository()
    if backend == "azure":
        return _build_azure_repository()
    if backend == "gdrive":
        return _build_gdrive_repository()

    raise ValueError(
        "Unsupported CONCILIUM__STORE_BACKEND='"
        f"{backend}'. Supported backends: local_json, filesystem, sharepoint, s3, azure, gdrive."
    )
