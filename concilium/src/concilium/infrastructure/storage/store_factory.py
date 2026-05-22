from __future__ import annotations

import os
from pathlib import Path

from concilium.application.services.project_repository import ProjectRepository

from .file_project_repository import FileProjectRepository


DEFAULT_STORE_BACKEND = "filesystem"
_BACKEND_ALIASES: dict[str, str] = {
    "filesystem": "filesystem",
    "local_json": "filesystem",
    "local-json": "filesystem",
    "local": "filesystem",
    "sharepoint": "sharepoint",
    "s3": "s3",
}


def _projects_prefix() -> str:
    value = (os.environ.get("CONCILIUM_STORE_PROJECTS_PREFIX") or "projetos").strip().strip("/")
    return value or "projetos"


def _build_sharepoint_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.sharepoint_blob_storage import SharePointBlobStorage

    from .storage_project_repository import StorageProjectRepository

    cache_dir_raw = (os.environ.get("CONCILIUM_SP_CACHE_DIR") or "").strip()
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None
    storage = SharePointBlobStorage.from_env(cache_dir=cache_dir)
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())


def _build_s3_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.s3_blob_storage import S3BlobStorage

    from .storage_project_repository import StorageProjectRepository

    storage = S3BlobStorage.from_env()
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())


def resolve_store_backend() -> str:
    """Resolve backend name for project repository from environment."""
    value = (os.environ.get("CONCILIUM_STORE_BACKEND") or DEFAULT_STORE_BACKEND).strip().lower()
    value = value or DEFAULT_STORE_BACKEND
    return _BACKEND_ALIASES.get(value, value)


def build_project_repository(projects_root: Path) -> ProjectRepository:
    """Build ProjectRepository according to CONCILIUM_STORE_BACKEND.

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

    raise ValueError(
        "Unsupported CONCILIUM_STORE_BACKEND='"
        f"{backend}'. Supported backends: local_json, filesystem, sharepoint, s3."
    )
