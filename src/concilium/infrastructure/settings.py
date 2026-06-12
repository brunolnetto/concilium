"""Registro centralizado de variáveis de ambiente CONCILIUM__*.

Cada variável tem uma classificação que determina como ela deve ser configurada:

  [opt]   Optional   — tem default sensato; funciona sem configurar
  [req]   Required   — sem default; startup_check() falha se ausente
  [cond]  Conditional — obrigatória somente quando uma escolha específica é feita
  [cloud] Cloud      — valor buscado em runtime de um serviço externo (Key Vault);
                       a variável em si é o localizador (URL), não o segredo
  [comp]  Computed   — derivada de outras variáveis se não configurada explicitamente

Startup validation: startup_check() — chame no início de cada entry point.
Falha com ConfigurationError listando todos os problemas de uma vez.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Variável                              Tipo    Default          Domínio
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
── Workspace e configuração (StorageSettings) ───────────────────────────────
CONCILIUM__ROOT                       [opt]   <cwd do pkg>     StorageSettings.root
CONCILIUM__CONFIG_ROOT                [opt]   ROOT/config      StorageSettings.config_root
CONCILIUM__RUNTIME_CONFIG_FILE        [opt]   —                StorageSettings.runtime_config_file
── Storage (StorageSettings) ────────────────────────────────────────────────
CONCILIUM__STORE_BACKEND              [opt]   filesystem       StorageSettings.backend
CONCILIUM__STORE_PROJECTS_PREFIX      [opt]   projetos         StorageSettings.projects_prefix
CONCILIUM__PROJECTS_ROOT              [opt]   ROOT/projetos    StorageSettings.projects_root
CONCILIUM__BENCHMARK_PROJECTS_ROOT    [opt]   ROOT/bench…      StorageSettings.benchmark_projects_root
── Azure Blob (AzureSettings) — [cond: STORE_BACKEND=azure_blob] ────────────
CONCILIUM__AZURE_ACCOUNT              [cond]  —                AzureSettings.account
CONCILIUM__AZURE_CONTAINER            [req]   —                AzureSettings.container
CONCILIUM__AZURE_KEY                  [cond]  —                AzureSettings.key (ou Managed Identity)
CONCILIUM__AZURE_CONNECTION_STRING    [cond]  —                AzureSettings.connection_string (alternativa)
CONCILIUM__AZURE_ROOT_PREFIX          [opt]   —                AzureSettings.root_prefix
── AWS S3 (S3Settings) — [cond: STORE_BACKEND=s3] ──────────────────────────
CONCILIUM__S3_BUCKET                  [req]   —                S3Settings.bucket
CONCILIUM__S3_REGION                  [opt]   us-east-1        S3Settings.region
CONCILIUM__S3_ROOT_PREFIX             [opt]   —                S3Settings.root_prefix
CONCILIUM__S3_ENDPOINT_URL            [opt]   —                S3Settings.endpoint_url (MinIO, LocalStack)
CONCILIUM__S3_ADDRESSING_STYLE        [opt]   virtual          S3Settings.addressing_style
CONCILIUM__S3_ACCESS_KEY_ID           [opt]   —                S3Settings.access_key_id (IAM se ausente)
CONCILIUM__S3_SECRET_ACCESS_KEY       [opt]   —                S3Settings.secret_access_key
CONCILIUM__S3_SESSION_TOKEN           [opt]   —                S3Settings.session_token (STS)
CONCILIUM__S3_SERVER_SIDE_ENCRYPTION  [opt]   —                S3Settings.server_side_encryption
── SharePoint (SharePointSettings) — [cond: STORE_BACKEND=sharepoint] ───────
CONCILIUM__SP_TENANT_ID               [req]   —                SharePointSettings.tenant_id
CONCILIUM__SP_CLIENT_ID               [req]   —                SharePointSettings.client_id
CONCILIUM__SP_DRIVE_ID                [req]   —                SharePointSettings.drive_id
CONCILIUM__SP_CLIENT_SECRET           [cond]  —                SharePointSettings.client_secret (ou CERT)
CONCILIUM__SP_CERT_PATH               [cond]  —                SharePointSettings.cert_path (prod-preferred)
CONCILIUM__SP_ROOT_PATH               [opt]   Concilium/prod   SharePointSettings.root_path
CONCILIUM__SP_CACHE_DIR               [opt]   —                SharePointSettings.cache_dir
── Google Drive (GDriveSettings) — [cond: STORE_BACKEND=gdrive] ─────────────
CONCILIUM__GDRIVE_ROOT_FOLDER_ID      [req]   —                GDriveSettings.root_folder_id
CONCILIUM__GDRIVE_SA_JSON             [opt]   —                GDriveSettings.service_account_json
CONCILIUM__GOOGLE_CREDENTIALS         [opt]   —                GDriveSettings.google_credentials_path
── API REST (ApiSettings) ───────────────────────────────────────────────────
CONCILIUM__API_HOST                   [opt]   127.0.0.1        ApiSettings.host
CONCILIUM__API_PORT                   [opt]   8000             ApiSettings.port
CONCILIUM__API_RELOAD                 [opt]   false            ApiSettings.reload
CONCILIUM__API_BASE_URL               [comp]  http://host:port ApiSettings.base_url
── MCP Server (McpSettings) ─────────────────────────────────────────────────
CONCILIUM__MCP_TRANSPORT              [opt]   stdio            McpSettings.transport
CONCILIUM__MCP_HOST                   [opt]   0.0.0.0          McpSettings.host
CONCILIUM__MCP_PORT                   [opt]   8080             McpSettings.port
CONCILIUM__MCP_RATE_LIMIT_CALLS       [opt]   10               McpSettings.rate_limit_calls
CONCILIUM__MCP_RATE_LIMIT_PERIOD_S    [opt]   60               McpSettings.rate_limit_period_s
── UI Streamlit (UiSettings) ────────────────────────────────────────────────
CONCILIUM__UI_HOST                    [opt]   127.0.0.1        UiSettings.host
CONCILIUM__UI_PORT                    [opt]   8501             UiSettings.port
CONCILIUM__UI_API_BASE_URL            [comp]  API_BASE_URL     UiSettings.api_base_url_override
CONCILIUM__UI_ENTRYPOINT              [opt]   —                UiSettings.entrypoint
── Autenticação JWT (AuthSettings) ──────────────────────────────────────────
CONCILIUM__AUTH_ENABLED               [opt]   false            AuthSettings.enabled
CONCILIUM__AUTH_CLIENTS               [cond]  —                AuthSettings.clients_json (req se enabled)
CONCILIUM__JWT_PRIVATE_KEY_PEM        [cond]  —                AuthSettings.jwt_private_key_pem (dev)
CONCILIUM__JWT_PRIVATE_KEY_PATH       [cond]  —                AuthSettings.jwt_private_key_path (dev)
CONCILIUM__JWT_PUBLIC_KEY_PEM         [cond]  —                AuthSettings.jwt_public_key_pem (dev)
CONCILIUM__JWT_PUBLIC_KEY_PATH        [cond]  —                AuthSettings.jwt_public_key_path (dev)
CONCILIUM__JWT_KEY_VAULT_URL          [cloud] —                AuthSettings.key_vault_url (prod; ADR-094)
CONCILIUM__AUTH_DATA_PATH             [opt]   ~/.concilium/auth AuthSettings.data_path
── Telemetria e Rate Limit (TelemetrySettings) ──────────────────────────────
CONCILIUM__OTEL_CONSOLE               [opt]   false            TelemetrySettings.otel_console
CONCILIUM__RATE_LIMIT_GLOBAL          [opt]   200/minute       TelemetrySettings.rate_limit_global
CONCILIUM__RATE_LIMIT_STORAGE_URI     [opt]   memory://        TelemetrySettings.rate_limit_storage_uri
── Runtime do pipeline (RuntimeSettings) ────────────────────────────────────
CONCILIUM__PDF_RENDERER               [opt]   reportlab        RuntimeSettings.pdf_renderer
CONCILIUM__ARTIFACT_TRANSPORT         [opt]   local            RuntimeSettings.artifact_transport
CONCILIUM__LOCK_TTL_SECONDS           [opt]   86400            RuntimeSettings.lock_ttl_seconds
CONCILIUM__DUCKDB_MEMORY              [opt]   512MB            RuntimeSettings.duckdb_memory
CONCILIUM__DUCKDB_SPILL_DIR           [opt]   tmpdir           RuntimeSettings.duckdb_spill_dir
── Sistema de Jobs (JobsSettings — ADR-102) ─────────────────────────────────
CONCILIUM__MAX_CONCURRENT_JOBS        [opt]   3                JobsSettings.max_concurrent_jobs
CONCILIUM__JOB_TTL_HOURS              [opt]   24               JobsSettings.job_ttl_hours
CONCILIUM__JOB_GC_INTERVAL_MINUTES    [opt]   60               JobsSettings.job_gc_interval_minutes
── Campanha GO (CampaignSettings — ADR-109) ─────────────────────────────────
CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD  [opt]  10000        CampaignSettings.cardinality_threshold
CONCILIUM__CAMPAIGN_MAX_WORKERS           [opt]  6             CampaignSettings.max_workers
CONCILIUM__CAMPAIGN_SECONDS_PER_SCENARIO  [opt]  6             CampaignSettings.seconds_per_scenario
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Variáveis de infra de testes (não produção):
  CONCILIUM__SAMPLES_DIR  — lida diretamente por tests/conftest.py

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Onde cada variável mora por ambiente
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─ cd/development/.env.api  ─────────────────────────────────────────────────
│  Lido pelo docker-compose para o container da API.
│  Não commitado; cada dev mantém o seu.
│
│  CONCILIUM__API_HOST=0.0.0.0
│  CONCILIUM__API_PORT=8000
│  CONCILIUM__STORE_BACKEND=filesystem        # trocar para azure_blob ao testar cloud
│  CONCILIUM__AUTH_ENABLED=0                  # 1 para testar auth localmente
│  CONCILIUM__JWT_PRIVATE_KEY_PEM=<pem>       # apenas se AUTH_ENABLED=1
│  CONCILIUM__JWT_PUBLIC_KEY_PEM=<pem>        # apenas se AUTH_ENABLED=1
│  CONCILIUM__AUTH_CLIENTS=[{"client_id":…}]  # apenas se AUTH_ENABLED=1
│  OTEL_SDK_DISABLED=true                     # sem telemetria em dev
│  CONCILIUM__API_RELOAD=1

├─ cd/development/.env.ui  ──────────────────────────────────────────────────
│  Lido pelo docker-compose para o container da UI.
│
│  CONCILIUM__UI_HOST=0.0.0.0
│  CONCILIUM__UI_PORT=8501
│  CONCILIUM__UI_API_BASE_URL=http://api:8000

├─ .github/workflows/deploy.yml  env:  ─────────────────────────────────────
│  Variáveis não-secretas passadas ao ACI. Visíveis no log do Actions.
│  Hardcoded no workflow — sem GitHub Secrets.
│
│  CONCILIUM__API_HOST=0.0.0.0
│  CONCILIUM__API_PORT=8000
│  CONCILIUM__MCP_TRANSPORT=streamable-http
│  CONCILIUM__MCP_HOST=0.0.0.0
│  CONCILIUM__MCP_PORT=8080
│  CONCILIUM__STORE_BACKEND=azure_blob
│  CONCILIUM__JWT_KEY_VAULT_URL=https://concilium-kv.vault.azure.net   # [cloud]
│  OTEL_SERVICE_NAME=concilium-api
│  OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_ENDPOINT}  # vem de GitHub Secret

├─ GitHub Secrets → ACI --secure-environment-variables  ─────────────────────
│  Mascarados no log. Injetados pelo deploy.yml via ${{ secrets.* }}.
│
│  CONCILIUM__AZURE_ACCOUNT    ← secrets.CONCILIUM__AZURE_ACCOUNT
│  CONCILIUM__AZURE_CONTAINER  ← secrets.CONCILIUM__AZURE_CONTAINER
│  CONCILIUM__AZURE_KEY        ← secrets.CONCILIUM__AZURE_KEY
│  OTEL_EXPORTER_OTLP_ENDPOINT ← secrets.OTEL_EXPORTER_OTLP_ENDPOINT

└─ Azure Key Vault  ──────────────────────────────────────────────────────────
   Buscado em runtime pelo container via Managed Identity (ADR-094 Fase 1).
   Zero variáveis de processo — o container só recebe a URL do vault.

   jwt-private-key  →  CONCILIUM__JWT_PRIVATE_KEY_PEM  (em memória)
   jwt-public-key   →  CONCILIUM__JWT_PUBLIC_KEY_PEM   (em memória)
   tls-cert         →  lido pelo Application Gateway para HTTPS

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Uso
───
    from concilium.infrastructure.settings import get_api, get_storage, startup_check

    startup_check()          # chame no main() de cada entry point
    host = get_api().host
    backend = get_storage().backend

Reset (testes)
──────────────
    from concilium.infrastructure.settings import _reset_all
    _reset_all()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_fingerprint() -> tuple[tuple[str, str], ...]:
    """Fingerprint determinístico das env vars relevantes para settings."""
    tracked: list[tuple[str, str]] = []
    for key, value in os.environ.items():
        if key.startswith("CONCILIUM__") or key in {
            "OTEL_SDK_DISABLED",
            "OTEL_SERVICE_NAME",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
        }:
            tracked.append((key, value))
    tracked.sort(key=lambda item: item[0])
    return tuple(tracked)


_last_env_fingerprint: tuple[tuple[str, str], ...] | None = None


def _refresh_if_env_changed() -> None:
    """Invalida cache de settings quando env vars mudam no mesmo processo."""
    global _last_env_fingerprint
    current = _env_fingerprint()
    if _last_env_fingerprint != current:
        _reset_all()
        _last_env_fingerprint = current


# ── Helpers de parsing ────────────────────────────────────────────────────────


def _str(name: str, default: str = "") -> str:
    """Lê variável de ambiente como string com fallback."""
    return (os.environ.get(name) or default).strip() or default


def _int(name: str, default: int = 0) -> int:
    """Lê variável de ambiente como inteiro com fallback."""
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw.strip())
    except (ValueError, TypeError):
        return default


def _flag(name: str, default: bool = False) -> bool:
    """Lê variável de ambiente como booleano. Falsy: '0', 'false', 'no', 'off', ''."""
    val = (os.environ.get(name) or "").strip().lower()
    if not val:
        return default
    return val not in ("0", "false", "no", "off")


def _path(name: str, default: Path | None = None) -> Path | None:
    """Lê variável de ambiente como Path expandido. None se ausente."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


# ── ApiSettings ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ApiSettings:
    """Configuração do servidor FastAPI REST (porta 8000)."""

    host: str
    """CONCILIUM__API_HOST — bind host (default: 127.0.0.1)."""

    port: int
    """CONCILIUM__API_PORT — bind port (default: 8000)."""

    reload: bool
    """CONCILIUM__API_RELOAD — hot-reload uvicorn (default: False)."""

    base_url: str
    """CONCILIUM__API_BASE_URL — URL canônica da API para consumidores (UI, scripts)."""

    @classmethod
    def from_env(cls) -> ApiSettings:
        return cls(
            host=_str("CONCILIUM__API_HOST", "127.0.0.1"),
            port=_int("CONCILIUM__API_PORT", 8000),
            reload=_flag("CONCILIUM__API_RELOAD"),
            base_url=_str("CONCILIUM__API_BASE_URL", ""),
        )


_api: ApiSettings | None = None


def get_api() -> ApiSettings:
    _refresh_if_env_changed()
    global _api
    if _api is None:
        _api = ApiSettings.from_env()
    return _api


# ── McpSettings ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class McpSettings:
    """Configuração do MCP server (FastMCP)."""

    transport: str
    """CONCILIUM__MCP_TRANSPORT — "stdio" (default), "streamable-http", "sse"."""

    host: str
    """CONCILIUM__MCP_HOST — bind host para transporte HTTP (default: 0.0.0.0)."""

    port: int
    """CONCILIUM__MCP_PORT — bind port para transporte HTTP (default: 8080)."""

    rate_limit_calls: int
    """CONCILIUM__MCP_RATE_LIMIT_CALLS — máx chamadas por janela (default: 10)."""

    rate_limit_period_s: int
    """CONCILIUM__MCP_RATE_LIMIT_PERIOD_S — janela de rate limit em segundos (default: 60)."""

    @classmethod
    def from_env(cls) -> McpSettings:
        return cls(
            transport=_str("CONCILIUM__MCP_TRANSPORT", "stdio"),
            host=_str("CONCILIUM__MCP_HOST", "0.0.0.0"),
            port=_int("CONCILIUM__MCP_PORT", 8080),
            rate_limit_calls=_int("CONCILIUM__MCP_RATE_LIMIT_CALLS", 10),
            rate_limit_period_s=_int("CONCILIUM__MCP_RATE_LIMIT_PERIOD_S", 60),
        )


_mcp: McpSettings | None = None


def get_mcp() -> McpSettings:
    _refresh_if_env_changed()
    global _mcp
    if _mcp is None:
        _mcp = McpSettings.from_env()
    return _mcp


@dataclass(frozen=True)
class McpProxySettings:
    """Configuração do proxy stdio -> HTTP do MCP."""

    server_url: str
    """CONCILIUM_SERVER_URL — URL base do servidor MCP HTTP."""

    device_id: str
    """CONCILIUM_DEVICE_ID — identificador local do dispositivo."""

    device_code: str
    """CONCILIUM_DEVICE_CODE — código de ativação para bootstrap de refresh token."""

    @classmethod
    def from_env(cls) -> McpProxySettings:
        return cls(
            server_url=_str("CONCILIUM_SERVER_URL", "https://mcp.mendesloboconstrucao.com.br").rstrip("/"),
            device_id=_str("CONCILIUM_DEVICE_ID", "default"),
            device_code=_str("CONCILIUM_DEVICE_CODE", ""),
        )


_mcp_proxy: McpProxySettings | None = None


def get_mcp_proxy() -> McpProxySettings:
    _refresh_if_env_changed()
    global _mcp_proxy
    if _mcp_proxy is None:
        _mcp_proxy = McpProxySettings.from_env()
    return _mcp_proxy


# ── UiSettings ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class UiSettings:
    """Configuração da UI Streamlit."""

    host: str
    """CONCILIUM__UI_HOST — bind host (default: 127.0.0.1)."""

    port: int
    """CONCILIUM__UI_PORT — bind port (default: 8501)."""

    api_base_url_override: str
    """CONCILIUM__UI_API_BASE_URL — URL da API vista pela UI (sobrescreve CONCILIUM__API_BASE_URL)."""

    entrypoint: str
    """CONCILIUM__UI_ENTRYPOINT — caminho para script Streamlit customizado."""

    def resolved_api_base_url(self, api: ApiSettings | None = None) -> str:
        """Resolve a URL da API com precedência: UI_override > API_BASE_URL > host:port."""
        if self.api_base_url_override:
            return self.api_base_url_override.rstrip("/")
        if api and api.base_url:
            return api.base_url.rstrip("/")
        _api = api or get_api()
        return f"http://{_api.host}:{_api.port}"

    @classmethod
    def from_env(cls) -> UiSettings:
        return cls(
            host=_str("CONCILIUM__UI_HOST", "127.0.0.1"),
            port=_int("CONCILIUM__UI_PORT", 8501),
            api_base_url_override=_str("CONCILIUM__UI_API_BASE_URL", ""),
            entrypoint=_str("CONCILIUM__UI_ENTRYPOINT", ""),
        )


_ui: UiSettings | None = None


def get_ui() -> UiSettings:
    _refresh_if_env_changed()
    global _ui
    if _ui is None:
        _ui = UiSettings.from_env()
    return _ui


# ── AuthSettings ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AuthSettings:
    """Configuração de autenticação JWT (ADR-094)."""

    enabled: bool
    """CONCILIUM__AUTH_ENABLED — habilita middleware JWT (default: False)."""

    clients_json: str
    """CONCILIUM__AUTH_CLIENTS — JSON com client_id/secret/scopes dos consumidores."""

    jwt_private_key_pem: str
    """CONCILIUM__JWT_PRIVATE_KEY_PEM — chave RS256 privada em PEM (inline)."""

    jwt_private_key_path: str
    """CONCILIUM__JWT_PRIVATE_KEY_PATH — caminho para arquivo PEM da chave privada."""

    jwt_public_key_pem: str
    """CONCILIUM__JWT_PUBLIC_KEY_PEM — chave RS256 pública em PEM (inline)."""

    jwt_public_key_path: str
    """CONCILIUM__JWT_PUBLIC_KEY_PATH — caminho para arquivo PEM da chave pública."""

    key_vault_url: str
    """CONCILIUM__JWT_KEY_VAULT_URL — URL do Azure Key Vault (ex: https://concilium-kv.vault.azure.net).
    Usado em produção via Managed Identity — segredos 'jwt-private-key' e 'jwt-public-key'."""

    data_path: str
    """CONCILIUM__AUTH_DATA_PATH — [opt] Diretório para clients.json e refresh_tokens.json.
    Default: ~/.concilium/auth/"""

    @classmethod
    def from_env(cls) -> AuthSettings:
        return cls(
            enabled=_flag("CONCILIUM__AUTH_ENABLED"),
            clients_json=_str("CONCILIUM__AUTH_CLIENTS", ""),
            jwt_private_key_pem=_str("CONCILIUM__JWT_PRIVATE_KEY_PEM", ""),
            jwt_private_key_path=_str("CONCILIUM__JWT_PRIVATE_KEY_PATH", ""),
            jwt_public_key_pem=_str("CONCILIUM__JWT_PUBLIC_KEY_PEM", ""),
            jwt_public_key_path=_str("CONCILIUM__JWT_PUBLIC_KEY_PATH", ""),
            key_vault_url=_str("CONCILIUM__JWT_KEY_VAULT_URL", ""),
            data_path=_str("CONCILIUM__AUTH_DATA_PATH", ""),
        )


_auth: AuthSettings | None = None


def get_auth() -> AuthSettings:
    _refresh_if_env_changed()
    global _auth
    if _auth is None:
        _auth = AuthSettings.from_env()
    return _auth


# ── Storage sub-settings ──────────────────────────────────────────────────────


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


# ── StorageSettings ───────────────────────────────────────────────────────────


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
        root = Path(root_raw).expanduser().resolve() if root_raw else Path(__file__).resolve().parents[3]
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


# ── TelemetrySettings ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TelemetrySettings:
    """Observabilidade (ADR-095) e rate limiting (ADR-098).

    Variáveis OTEL padrão (OTEL_EXPORTER_OTLP_ENDPOINT, OTEL_SERVICE_NAME,
    OTEL_SDK_DISABLED) são lidas diretamente pelo OTEL SDK — não mapeadas aqui.
    """

    otel_console: bool
    """CONCILIUM__OTEL_CONSOLE — habilita console exporter OTEL em dev local."""

    otel_sdk_disabled: bool
    """OTEL_SDK_DISABLED — desativa telemetria OTEL por completo."""

    otel_service_name: str
    """OTEL_SERVICE_NAME — nome lógico do serviço exportado."""

    otlp_endpoint: str
    """OTEL_EXPORTER_OTLP_ENDPOINT — endpoint OTLP HTTP (sem sufixo /v1/*)."""

    rate_limit_global: str
    """CONCILIUM__RATE_LIMIT_GLOBAL — limite global de requests (default: 200/minute)."""

    rate_limit_storage_uri: str
    """CONCILIUM__RATE_LIMIT_STORAGE_URI — backend de rate limit (default: memory://)."""

    @classmethod
    def from_env(cls) -> TelemetrySettings:
        return cls(
            otel_console=_flag("CONCILIUM__OTEL_CONSOLE"),
            otel_sdk_disabled=_flag("OTEL_SDK_DISABLED"),
            otel_service_name=_str("OTEL_SERVICE_NAME", "concilium"),
            otlp_endpoint=_str("OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            rate_limit_global=_str("CONCILIUM__RATE_LIMIT_GLOBAL", "200/minute"),
            rate_limit_storage_uri=_str("CONCILIUM__RATE_LIMIT_STORAGE_URI", "memory://"),
        )


_telemetry: TelemetrySettings | None = None


def get_telemetry() -> TelemetrySettings:
    _refresh_if_env_changed()
    global _telemetry
    if _telemetry is None:
        _telemetry = TelemetrySettings.from_env()
    return _telemetry


# ── BenchmarkSettings ─────────────────────────────────────────────────────────

# ── RuntimeSettings ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RuntimeSettings:
    """Configuração de runtime do pipeline de produção."""

    pdf_renderer: str
    """CONCILIUM__PDF_RENDERER — "reportlab" (default) ou "fpdf2" (legado, NEP-033)."""

    artifact_transport: str
    """CONCILIUM__ARTIFACT_TRANSPORT — transporte de artefatos MCP: "local" (default), "zipurl", "presigned"."""

    lock_ttl_seconds: int
    """CONCILIUM__LOCK_TTL_SECONDS — TTL do lock de catálogo em segundos (default: 86400 = 24h)."""

    duckdb_memory: str
    """CONCILIUM__DUCKDB_MEMORY — [opt] Limite de RAM para DuckDB antes de drive-spill (default: 512MB)."""

    duckdb_spill_dir: str
    """CONCILIUM__DUCKDB_SPILL_DIR — [opt] Diretório para overflow DuckDB (default: tmpdir do OS)."""

    @classmethod
    def from_env(cls) -> RuntimeSettings:
        import tempfile

        return cls(
            pdf_renderer=_str("CONCILIUM__PDF_RENDERER", "reportlab"),
            artifact_transport=_str("CONCILIUM__ARTIFACT_TRANSPORT", "local"),
            lock_ttl_seconds=_int("CONCILIUM__LOCK_TTL_SECONDS", 86400),
            duckdb_memory=_str("CONCILIUM__DUCKDB_MEMORY", "512MB"),
            duckdb_spill_dir=_str("CONCILIUM__DUCKDB_SPILL_DIR", tempfile.gettempdir()),
        )


_runtime: RuntimeSettings | None = None


def get_runtime() -> RuntimeSettings:
    _refresh_if_env_changed()
    global _runtime
    if _runtime is None:
        _runtime = RuntimeSettings.from_env()
    return _runtime


# ── JobsSettings ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class JobsSettings:
    """Configuração do sistema de jobs assíncronos de pipeline (ADR-102)."""

    max_concurrent_jobs: int
    """CONCILIUM__MAX_CONCURRENT_JOBS — máximo de jobs simultâneos no worker pool (default: 3)."""

    job_ttl_hours: int
    """CONCILIUM__JOB_TTL_HOURS — tempo de vida de jobs finalizados antes de GC (default: 24h)."""

    job_gc_interval_minutes: int
    """CONCILIUM__JOB_GC_INTERVAL_MINUTES — intervalo de garbage collection em minutos (default: 60)."""

    @classmethod
    def from_env(cls) -> JobsSettings:
        return cls(
            max_concurrent_jobs=_int("CONCILIUM__MAX_CONCURRENT_JOBS", 3),
            job_ttl_hours=_int("CONCILIUM__JOB_TTL_HOURS", 24),
            job_gc_interval_minutes=_int("CONCILIUM__JOB_GC_INTERVAL_MINUTES", 60),
        )


_jobs: JobsSettings | None = None


def get_jobs() -> JobsSettings:
    global _jobs
    if _jobs is None:
        _jobs = JobsSettings.from_env()
    return _jobs


# ── CampaignSettings ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CampaignSettings:
    """Configuração do motor de exploração de campanha GO (ADR-070, ADR-109)."""

    cardinality_threshold: int
    """CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD — cardinalidade máxima para busca exaustiva
    sem aviso (ADR-109: fronteira de tratabilidade). Acima desse valor, executar_campanha()
    emite warnings.warn sugerindo busca guiada (default: 10000)."""

    max_workers: int
    """CONCILIUM__CAMPAIGN_MAX_WORKERS — número de workers paralelos para avaliação de cenários
    (default: 6). Afeta o cálculo de tempo estimado no aviso de tratabilidade."""

    seconds_per_scenario: int
    """CONCILIUM__CAMPAIGN_SECONDS_PER_SCENARIO — estimativa de tempo por cenário em segundos
    usada no cálculo de aviso de tratabilidade (default: 6)."""

    @classmethod
    def from_env(cls) -> "CampaignSettings":
        return cls(
            cardinality_threshold=_int("CONCILIUM__CAMPAIGN_CARDINALITY_THRESHOLD", 10_000),
            max_workers=_int("CONCILIUM__CAMPAIGN_MAX_WORKERS", 6),
            seconds_per_scenario=_int("CONCILIUM__CAMPAIGN_SECONDS_PER_SCENARIO", 6),
        )


_campaign: CampaignSettings | None = None


def get_campaign() -> CampaignSettings:
    _refresh_if_env_changed()
    global _campaign
    if _campaign is None:
        _campaign = CampaignSettings.from_env()
    return _campaign


# ── Validação de startup ──────────────────────────────────────────────────────


class ConfigurationError(RuntimeError):
    """Levantada por startup_check() quando a configuração está incompleta ou inválida."""


def startup_check() -> None:
    """Valida todas as configurações no startup. Levanta ConfigurationError com diagnóstico completo.

    Chame no main() de cada entry point (API, MCP, CLI). Não chame em create_app()
    para não interferir com testes que importam o módulo sem todas as vars configuradas.

    O check não falha em modo efêmero de dev — apenas quando AUTH_ENABLED=1 sem
    chaves configuradas ou quando um backend cloud é escolhido sem credenciais.
    """
    errors: list[str] = []
    errors.extend(_check_storage(get_storage()))
    errors.extend(_check_auth(get_auth()))
    if errors:
        lines = [
            "",
            "  ┌─ ConfigurationError " + "─" * 48,
            *[f"  │  ✗ {e}" for e in errors],
            "  └" + "─" * 69,
            "  Corrija as variáveis acima antes de iniciar o serviço.",
            "",
        ]
        raise ConfigurationError("\n".join(lines))


def _check_storage(st: StorageSettings) -> list[str]:
    errors: list[str] = []
    b = st.backend
    if b == "azure_blob":
        if not st.azure.account:
            errors.append("CONCILIUM__AZURE_ACCOUNT é obrigatório quando STORE_BACKEND=azure_blob")
        if not st.azure.container:
            errors.append("CONCILIUM__AZURE_CONTAINER é obrigatório quando STORE_BACKEND=azure_blob")
        has_cred = st.azure.key or st.azure.connection_string
        # sem key e sem connection_string = usa Managed Identity; aceitável em ACI
        if not st.azure.account and not st.azure.connection_string:
            errors.append(
                "CONCILIUM__AZURE_ACCOUNT (ou CONCILIUM__AZURE_CONNECTION_STRING) "
                "é obrigatório quando STORE_BACKEND=azure_blob"
            )
        _ = has_cred  # Managed Identity é válido sem key explícita
    elif b == "s3":
        if not st.s3.bucket:
            errors.append("CONCILIUM__S3_BUCKET é obrigatório quando STORE_BACKEND=s3")
    elif b == "sharepoint":
        for var, val in [
            ("CONCILIUM__SP_TENANT_ID", st.sharepoint.tenant_id),
            ("CONCILIUM__SP_CLIENT_ID", st.sharepoint.client_id),
            ("CONCILIUM__SP_DRIVE_ID", st.sharepoint.drive_id),
        ]:
            if not val:
                errors.append(f"{var} é obrigatório quando STORE_BACKEND=sharepoint")
        if not st.sharepoint.client_secret and not st.sharepoint.cert_path:
            errors.append(
                "CONCILIUM__SP_CLIENT_SECRET ou CONCILIUM__SP_CERT_PATH é obrigatório quando STORE_BACKEND=sharepoint"
            )
    elif b == "gdrive":
        if not st.gdrive.root_folder_id:
            errors.append("CONCILIUM__GDRIVE_ROOT_FOLDER_ID é obrigatório quando STORE_BACKEND=gdrive")
    elif b not in ("filesystem", "local_json"):
        errors.append(
            f"CONCILIUM__STORE_BACKEND={b!r} desconhecido. "
            "Valores válidos: filesystem, azure_blob, s3, sharepoint, gdrive"
        )
    return errors


def _check_auth(auth: AuthSettings) -> list[str]:
    if not auth.enabled:
        return []
    errors: list[str] = []
    has_pem = bool(auth.jwt_private_key_pem or auth.jwt_private_key_path)
    has_kv = bool(auth.key_vault_url)
    if not has_pem and not has_kv:
        errors.append(
            "Auth habilitado (CONCILIUM__AUTH_ENABLED=1) mas nenhuma fonte de chave JWT configurada. "
            "Defina CONCILIUM__JWT_KEY_VAULT_URL (produção) ou "
            "CONCILIUM__JWT_PRIVATE_KEY_PEM/_PATH (dev)."
        )
    if not auth.clients_json:
        errors.append(
            "CONCILIUM__AUTH_CLIENTS está vazio mas auth está habilitado. Defina um JSON com client_id/secret/scopes."
        )
    return errors


# ── Reset (testes) ────────────────────────────────────────────────────────────


def _reset_all() -> None:
    """Invalida todos os singletons. Usar em fixtures de teste para isolar env vars."""
    global _api, _mcp, _mcp_proxy, _ui, _auth, _storage, _telemetry, _runtime, _campaign, _last_env_fingerprint
    _api = _mcp = _mcp_proxy = _ui = _auth = _storage = _telemetry = _runtime = _campaign = None
    _last_env_fingerprint = None


# ── Resumo de diagnóstico ─────────────────────────────────────────────────────


def env_summary() -> str:
    """Retorna string formatada com todos os settings ativos. Útil para logs de startup."""
    st = get_storage()
    api = get_api()
    mcp = get_mcp()
    ui = get_ui()
    auth = get_auth()
    tel = get_telemetry()
    rt = get_runtime()

    lines = [
        "── Concilium Settings ──────────────────────────────",
        f"  root                : {st.root}",
        f"  config_root         : {st.config_root}",
        f"  storage.backend     : {st.backend}  prefix={st.projects_prefix}",
        f"  projects_root       : {st.projects_root}",
        f"  bench_root          : {st.benchmark_projects_root}",
        f"  api                 : {api.host}:{api.port}  reload={api.reload}",
        f"  mcp                 : transport={mcp.transport}  {mcp.host}:{mcp.port}",
        f"  ui                  : {ui.host}:{ui.port}",
        f"  auth.enabled        : {auth.enabled}",
        f"  otel.console        : {tel.otel_console}",
        f"  rate_limit          : {tel.rate_limit_global}  storage={tel.rate_limit_storage_uri}",
        f"  mcp.rate_limit      : {mcp.rate_limit_calls}/{mcp.rate_limit_period_s}s",
        f"  pdf_renderer        : {rt.pdf_renderer}",
        f"  artifact_transport  : {rt.artifact_transport}",
        f"  campaign.threshold  : {get_campaign().cardinality_threshold:,}  workers={get_campaign().max_workers}  s/cen={get_campaign().seconds_per_scenario}",
        "────────────────────────────────────────────────────",
    ]
    return "\n".join(lines)
