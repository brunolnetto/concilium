from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from concilium.application.services.project.project_repository import ProjectRepository
from concilium.infrastructure.settings import get_storage

from .file_project_repository import FileProjectRepository

if TYPE_CHECKING:
    from concilium.domain.repositories.blob_storage_port import BlobStoragePort
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore
    from concilium.infrastructure.storage.tool_invocation_store import BlobToolInvocationRepository

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
    from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

    from .storage_project_repository import StorageProjectRepository

    cache_dir_raw = get_storage().sharepoint.cache_dir.strip()
    cache_dir = Path(cache_dir_raw).expanduser() if cache_dir_raw else None
    storage = SharePointBlobStorage.from_env(cache_dir=cache_dir)
    # StorageProjectRepository satisfaz ProjectRepository estruturalmente (mesmos
    # métodos), mas seus retornos são list[StorageProjectHandle]/StorageProjectHandle
    # em vez de list[ProjectHandle]/ProjectHandle — list é invariante em Python, então
    # isso nunca casa com a Protocol mesmo com StorageProjectHandle conformante.
    # Estreitar a assinatura pra ProjectHandle quebraria chamadas a métodos extras
    # (escopo, approve, log_invocation...) que não fazem parte do protocolo.
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())  # ty: ignore[invalid-return-type]


def _build_s3_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

    from .storage_project_repository import StorageProjectRepository

    storage = S3BlobStorage.from_env()
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())  # ty: ignore[invalid-return-type] — ver comentário em _build_sharepoint_repository


def _build_azure_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

    from .storage_project_repository import StorageProjectRepository

    storage = AzureBlobStorage.from_env()
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())  # ty: ignore[invalid-return-type] — ver comentário em _build_sharepoint_repository


def _build_gdrive_repository() -> ProjectRepository:
    from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage

    from .storage_project_repository import StorageProjectRepository

    storage = GoogleDriveBlobStorage.from_env()
    return StorageProjectRepository(storage=storage, projects_prefix=_projects_prefix())  # ty: ignore[invalid-return-type] — ver comentário em _build_sharepoint_repository


def resolve_store_backend() -> str:
    """Resolve backend name for project repository from environment."""
    from concilium.infrastructure.settings import get_storage as _get_storage

    value = (_get_storage().backend or DEFAULT_STORE_BACKEND).strip().lower()
    value = value or DEFAULT_STORE_BACKEND
    return _BACKEND_ALIASES.get(value, value)


def build_blob_storage(root_override: Path | None = None) -> BlobStoragePort:
    """Constrói BlobStoragePort de acordo com CONCILIUM__STORE_BACKEND.

    Ponto único de instanciação do backend de storage — benchmark store,
    campaign store e project store todos usam este factory.
    """
    from concilium.infrastructure.settings import get_storage as _get_storage

    backend = resolve_store_backend()
    if backend == "filesystem":
        from concilium.infrastructure.adapters.blob_storage.local import LocalBlobStorage

        storage_cfg = _get_storage()
        root = root_override or storage_cfg.projects_root or (storage_cfg.root / "projetos")
        return LocalBlobStorage(root_dir=root)
    if backend == "sharepoint":
        from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

        return SharePointBlobStorage.from_env()
    if backend == "s3":
        from concilium.infrastructure.adapters.blob_storage.s3 import S3BlobStorage

        return S3BlobStorage.from_env()
    if backend == "azure":
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        return AzureBlobStorage.from_env()
    if backend == "gdrive":
        from concilium.infrastructure.adapters.blob_storage.gdrive import GoogleDriveBlobStorage

        return GoogleDriveBlobStorage.from_env()
    raise ValueError(f"Backend não suportado: {backend}")


def get_tool_invocation_store() -> BlobToolInvocationRepository:
    """Retorna BlobToolInvocationRepository usando o backend configurado (ADR-118 F7)."""
    from concilium.infrastructure.storage.tool_invocation_store import BlobToolInvocationRepository

    storage = build_blob_storage()
    return BlobToolInvocationRepository(storage=storage)


def get_campaign_store(project_slug: str) -> CampaignRunStore:
    """Retorna CampaignRunStore para um projeto usando o backend configurado."""
    from concilium.infrastructure.storage.campaign_store import CampaignRunStore

    storage = build_blob_storage()
    prefix = f"{project_slug}/campaigns"
    return CampaignRunStore(storage=storage, prefix=prefix)


def ensure_storage_root() -> None:
    """Garante que o root_path do backend de storage existe no startup da aplicação.

    No-op para filesystem, S3, Azure e GDrive. Para SharePoint, cria os segmentos
    do CONCILIUM__SP_ROOT_PATH via Graph API se não existirem.
    """
    if resolve_store_backend() != "sharepoint":
        return
    from concilium.infrastructure.adapters.blob_storage.sharepoint import SharePointBlobStorage

    storage = build_blob_storage()
    if isinstance(storage, SharePointBlobStorage):
        storage.ensure_root_path()


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
