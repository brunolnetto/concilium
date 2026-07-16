"""Settings (parte extraída de settings.py) — grupo _lifecycle."""

from __future__ import annotations

from ._api import _reset_api, get_api
from ._auth import AuthSettings, _reset_auth, get_auth
from ._campaign import _reset_campaign, get_campaign
from ._catalog_digest import _reset_catalog_digest
from ._core import _reset_env_fingerprint
from ._mcp import _reset_mcp, get_mcp
from ._runtime import _reset_runtime, get_runtime
from ._smtp import _reset_smtp
from ._storage import StorageSettings, _reset_storage, get_storage
from ._telemetry import _reset_telemetry, get_telemetry
from ._ui import _reset_ui, get_ui


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


def _check_storage_azure_blob(st: StorageSettings) -> list[str]:
    errors: list[str] = []
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
    return errors


def _check_storage_sharepoint(st: StorageSettings) -> list[str]:
    errors: list[str] = []
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
    return errors


def _check_storage(st: StorageSettings) -> list[str]:
    b = st.backend
    if b == "azure_blob":
        return _check_storage_azure_blob(st)
    if b == "s3":
        return ["CONCILIUM__S3_BUCKET é obrigatório quando STORE_BACKEND=s3"] if not st.s3.bucket else []
    if b == "sharepoint":
        return _check_storage_sharepoint(st)
    if b == "gdrive":
        if not st.gdrive.root_folder_id:
            return ["CONCILIUM__GDRIVE_ROOT_FOLDER_ID é obrigatório quando STORE_BACKEND=gdrive"]
        return []
    if b not in ("filesystem", "local_json"):
        return [
            f"CONCILIUM__STORE_BACKEND={b!r} desconhecido. "
            "Valores válidos: filesystem, azure_blob, s3, sharepoint, gdrive"
        ]
    return []


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


def _reset_all() -> None:
    """Invalida todos os singletons. Usar em fixtures de teste para isolar env vars."""
    _reset_api()
    _reset_mcp()
    _reset_ui()
    _reset_auth()
    _reset_storage()
    _reset_telemetry()
    _reset_runtime()
    _reset_campaign()
    _reset_smtp()
    _reset_catalog_digest()
    _reset_env_fingerprint()


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
        f"  campaign.threshold  : {get_campaign().cardinality_threshold:,}  "
        f"workers={get_campaign().max_workers}  s/cen={get_campaign().seconds_per_scenario}",
        "────────────────────────────────────────────────────",
    ]
    return "\n".join(lines)
