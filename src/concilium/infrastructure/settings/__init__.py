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

Dividido em submódulos por grupo de configuração; ver cada arquivo em
settings/ para o detalhamento de variáveis por classe.
"""

from __future__ import annotations

from ._api import ApiSettings, get_api
from ._auth import AuthSettings, get_auth
from ._campaign import CampaignSettings, get_campaign
from ._core import _flag, _int, _path, _str
from ._jobs import JobsSettings, get_jobs
from ._lifecycle import (
    ConfigurationError,
    _check_auth,
    _check_storage,
    _reset_all,
    env_summary,
    startup_check,
)
from ._mcp import McpProxySettings, McpSettings, get_mcp, get_mcp_proxy
from ._runtime import RuntimeSettings, get_runtime
from ._smtp import SmtpSettings, _read_smtp_password_from_kv, get_smtp
from ._storage import (
    AzureSettings,
    GDriveSettings,
    S3Settings,
    SharePointSettings,
    StorageSettings,
    get_storage,
)
from ._telemetry import TelemetrySettings, get_telemetry
from ._ui import UiSettings, get_ui

__all__ = [
    "ApiSettings",
    "AuthSettings",
    "AzureSettings",
    "CampaignSettings",
    "ConfigurationError",
    "GDriveSettings",
    "JobsSettings",
    "McpProxySettings",
    "McpSettings",
    "RuntimeSettings",
    "S3Settings",
    "SharePointSettings",
    "SmtpSettings",
    "StorageSettings",
    "TelemetrySettings",
    "UiSettings",
    "_check_auth",
    "_check_storage",
    "_flag",
    "_int",
    "_path",
    "_read_smtp_password_from_kv",
    "_reset_all",
    "_str",
    "env_summary",
    "get_api",
    "get_auth",
    "get_campaign",
    "get_jobs",
    "get_mcp",
    "get_mcp_proxy",
    "get_runtime",
    "get_smtp",
    "get_storage",
    "get_telemetry",
    "get_ui",
    "startup_check",
]
