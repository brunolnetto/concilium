"""Settings (parte extraída de settings.py) — grupo _mcp."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _int, _refresh_if_env_changed, _str


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


def _reset_mcp() -> None:
    global _mcp, _mcp_proxy
    _mcp = None
    _mcp_proxy = None


@dataclass(frozen=True)
class McpProxySettings:
    """Configuração do proxy stdio -> HTTP do MCP (simplificada)."""

    server_url: str
    """CONCILIUM_SERVER_URL — URL base do servidor MCP HTTP (streamable-http)."""

    client_code: str
    """CONCILIUM_CLIENT_CODE — código de ativação para bootstrap de refresh token."""

    device_id: str
    """Device ID auto-detectado (hostname ou username)."""

    @classmethod
    def from_env(cls) -> McpProxySettings:
        import platform
        import socket

        server_url = _str("CONCILIUM_SERVER_URL", "https://mcp.mendesloboconstrucao.com.br").rstrip("/")
        # CONCILIUM_DEVICE_CODE é o nome legado (pré-#17) — mantido como fallback pois
        # configs sincronizadas externamente (ex.: perfil de conta do Claude Desktop)
        # podem reverter para o nome antigo fora do nosso controle.
        client_code = _str("CONCILIUM_CLIENT_CODE", "") or _str("CONCILIUM_DEVICE_CODE", "")

        # Auto-detecta device_id: hostname ou username@hostname
        try:
            hostname = socket.gethostname()
            username = platform.node() or ""
            device_id = f"{username}-{hostname}" if username else hostname
        except Exception:
            device_id = "unknown-device"

        return cls(
            server_url=server_url,
            client_code=client_code,
            device_id=device_id,
        )


_mcp_proxy: McpProxySettings | None = None


def get_mcp_proxy() -> McpProxySettings:
    _refresh_if_env_changed()
    global _mcp_proxy
    if _mcp_proxy is None:
        _mcp_proxy = McpProxySettings.from_env()
    return _mcp_proxy


