"""Settings (parte extraída de settings.py) — grupo _storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ._core import _path, _refresh_if_env_changed, _str


@dataclass(frozen=True)
class AzureSettings:
    """Azure Blob Storage — lido por AzureBlobStorage.from_env()."""

    account: str
    """CONCILIUM__AZURE_ACCOUNT — Storage Account name."""

    container: str
    """CONCILIUM__AZURE_CONTAINER — blob container (obrigatório para backend azure_blob)."""

    key: str
    """CONCILIUM__AZURE_KEY — Storage Account key (ou omitir para Managed Identity)."""

    connection_string: str
    """CONCILIUM__AZURE_CONNECTION_STRING — connection string completa (alternativa a account+key)."""

    root_prefix: str
    """CONCILIUM__AZURE_ROOT_PREFIX — prefixo raiz dentro do container."""

    @classmethod
    def from_env(cls) -> AzureSettings:
        return cls(
            account=_str("CONCILIUM__AZURE_ACCOUNT", ""),
            container=_str("CONCILIUM__AZURE_CONTAINER", ""),
            key=_str("CONCILIUM__AZURE_KEY", ""),
            connection_string=_str("CONCILIUM__AZURE_CONNECTION_STRING", ""),
            root_prefix=_str("CONCILIUM__AZURE_ROOT_PREFIX", ""),
        )


@dataclass(frozen=True)
class S3Settings:
    """AWS S3 / S3-compatible — lido por S3BlobStorage.from_env()."""

    bucket: str
    """CONCILIUM__S3_BUCKET — nome do bucket (obrigatório)."""

    region: str
    """CONCILIUM__S3_REGION — região AWS (default: us-east-1)."""

    root_prefix: str
    """CONCILIUM__S3_ROOT_PREFIX — prefixo raiz dentro do bucket."""

    endpoint_url: str
    """CONCILIUM__S3_ENDPOINT_URL — endpoint customizado (MinIO, LocalStack…)."""

    addressing_style: str
    """CONCILIUM__S3_ADDRESSING_STYLE — "virtual" (default) ou "path"."""

    access_key_id: str
    """CONCILIUM__S3_ACCESS_KEY_ID — AWS access key ID."""

    secret_access_key: str
    """CONCILIUM__S3_SECRET_ACCESS_KEY — AWS secret access key."""

    session_token: str
    """CONCILIUM__S3_SESSION_TOKEN — STS session token (temporário)."""

    server_side_encryption: str
    """CONCILIUM__S3_SERVER_SIDE_ENCRYPTION — "AES256" ou "aws:kms"."""

    @classmethod
    def from_env(cls) -> S3Settings:
        return cls(
            bucket=_str("CONCILIUM__S3_BUCKET", ""),
            region=_str("CONCILIUM__S3_REGION", "us-east-1"),
            root_prefix=_str("CONCILIUM__S3_ROOT_PREFIX", ""),
            endpoint_url=_str("CONCILIUM__S3_ENDPOINT_URL", ""),
            addressing_style=_str("CONCILIUM__S3_ADDRESSING_STYLE", "virtual"),
            access_key_id=_str("CONCILIUM__S3_ACCESS_KEY_ID", ""),
            secret_access_key=_str("CONCILIUM__S3_SECRET_ACCESS_KEY", ""),
            session_token=_str("CONCILIUM__S3_SESSION_TOKEN", ""),
            server_side_encryption=_str("CONCILIUM__S3_SERVER_SIDE_ENCRYPTION", ""),
        )


@dataclass(frozen=True)
class SharePointSettings:
    """Microsoft SharePoint / OneDrive — lido por SharePointBlobStorage.from_env()."""

    tenant_id: str
    """CONCILIUM__SP_TENANT_ID — Microsoft Entra tenant ID."""

    client_id: str
    """CONCILIUM__SP_CLIENT_ID — App Registration client ID."""

    client_secret: str
    """CONCILIUM__SP_CLIENT_SECRET — client secret (dev/CI; usar certificado em produção)."""

    cert_path: str
    """CONCILIUM__SP_CERT_PATH — caminho para certificado de autenticação (produção)."""

    drive_id: str
    """CONCILIUM__SP_DRIVE_ID — Drive ID raiz para armazenamento (obrigatório)."""

    root_path: str
    """CONCILIUM__SP_ROOT_PATH — caminho raiz dentro do Drive (default: Concilium/producao)."""

    cache_dir: str
    """CONCILIUM__SP_CACHE_DIR — cache local de metadados SharePoint."""

    @classmethod
    def from_env(cls) -> SharePointSettings:
        return cls(
            tenant_id=_str("CONCILIUM__SP_TENANT_ID", ""),
            client_id=_str("CONCILIUM__SP_CLIENT_ID", ""),
            client_secret=_str("CONCILIUM__SP_CLIENT_SECRET", ""),
            cert_path=_str("CONCILIUM__SP_CERT_PATH", ""),
            drive_id=_str("CONCILIUM__SP_DRIVE_ID", ""),
            root_path=_str("CONCILIUM__SP_ROOT_PATH", "Concilium/producao"),
            cache_dir=_str("CONCILIUM__SP_CACHE_DIR", ""),
        )


@dataclass(frozen=True)
class GDriveSettings:
    """Google Drive — lido por GDriveBlobStorage.from_env() e catalog_loader."""

    root_folder_id: str
    """CONCILIUM__GDRIVE_ROOT_FOLDER_ID — folder ID raiz no Google Drive (obrigatório)."""

    service_account_json: str
    """CONCILIUM__GDRIVE_SA_JSON — JSON de credenciais de Service Account."""

    google_credentials_path: str
    """CONCILIUM__GOOGLE_CREDENTIALS — caminho para credenciais Google (catalog loader legado)."""

    @classmethod
    def from_env(cls) -> GDriveSettings:
        return cls(
            root_folder_id=_str("CONCILIUM__GDRIVE_ROOT_FOLDER_ID", ""),
            service_account_json=_str("CONCILIUM__GDRIVE_SA_JSON", ""),
            google_credentials_path=_str("CONCILIUM__GOOGLE_CREDENTIALS", ""),
        )


@dataclass(frozen=True)
class StorageSettings:
    """Configuração de onde e como projetos e configuração são armazenados.

    Inclui caminhos de workspace (root, config) porque projetos e configuração
    vivem na mesma árvore de diretórios. Sub-settings de provider são
    instanciados sob demanda — não leem env vars até .azure/.s3/.sharepoint/.gdrive.
    """

    root: Path
    """CONCILIUM__ROOT — raiz do workspace (config/, benchmarks/, pyproject.toml)."""

    config_root: Path
    """CONCILIUM__CONFIG_ROOT — catálogos, perfis, contextos (default: root/config)."""

    runtime_config_file: Path | None
    """CONCILIUM__RUNTIME_CONFIG_FILE — arquivo de config runtime (YAML/JSON/TOML)."""

    backend: str
    """CONCILIUM__STORE_BACKEND — "filesystem" (default), "azure_blob", "s3", "sharepoint", "gdrive"."""

    projects_prefix: str
    """CONCILIUM__STORE_PROJECTS_PREFIX — prefixo lógico de projetos no backend (default: projetos)."""

    projects_root: Path | None
    """CONCILIUM__PROJECTS_ROOT — diretório raiz local de projetos (backend filesystem)."""

    benchmark_projects_root: Path | None
    """CONCILIUM__BENCHMARK_PROJECTS_ROOT — diretório raiz de projetos de benchmark."""

    azure: AzureSettings = field(default_factory=AzureSettings.from_env)
    sharepoint: SharePointSettings = field(default_factory=SharePointSettings.from_env)
    s3: S3Settings = field(default_factory=S3Settings.from_env)
    gdrive: GDriveSettings = field(default_factory=GDriveSettings.from_env)

    @classmethod
    def from_env(cls) -> StorageSettings:
        root_raw = _str("CONCILIUM__ROOT", "")
        root = Path(root_raw).expanduser().resolve() if root_raw else Path(__file__).resolve().parents[4]
        config_root_raw = _str("CONCILIUM__CONFIG_ROOT", "")
        config_root = Path(config_root_raw).expanduser().resolve() if config_root_raw else root / "config"
        return cls(
            root=root,
            config_root=config_root,
            runtime_config_file=_path("CONCILIUM__RUNTIME_CONFIG_FILE"),
            backend=_str("CONCILIUM__STORE_BACKEND", "filesystem"),
            projects_prefix=_str("CONCILIUM__STORE_PROJECTS_PREFIX", "projetos"),
            projects_root=_path("CONCILIUM__PROJECTS_ROOT", root / "projetos"),
            benchmark_projects_root=_path("CONCILIUM__BENCHMARK_PROJECTS_ROOT", root / "benchmarks" / "projetos"),
        )


_storage: StorageSettings | None = None


def get_storage() -> StorageSettings:
    _refresh_if_env_changed()
    global _storage
    if _storage is None:
        _storage = StorageSettings.from_env()
    return _storage




def _reset_storage() -> None:
    global _storage
    _storage = None
