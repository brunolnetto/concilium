"""concilium-mcp-proxy — bridge stdio ↔ HTTP MCP com auth automática (ADR-094).

Fluxo de autenticação (totalmente transparente para o usuário):

  1ª execução (sem token em cache):
      CONCILIUM_DEVICE_CODE → POST /auth/device/activate → refresh_token
      refresh_token salvo em ~/.concilium/tokens/<DEVICE_ID>.json (chmod 600)

  Execuções seguintes:
      Lê refresh_token do cache → POST /auth/token/refresh → access_token (8h)
      Se refresh_token expirou → tenta reativar com CONCILIUM_DEVICE_CODE

  Auto-renovação em background:
      Thread monitora TTL do access_token → renova 10min antes do vencimento

Configuração do usuário (claude_desktop_config.json):
  {
    "mcpServers": {
      "concilium": {
        "command": "concilium-mcp-proxy",
        "env": {
          "CONCILIUM_DEVICE_CODE": "RCODE-...",
          "CONCILIUM_DEVICE_ID":   "macbook-nome",
          "CONCILIUM_SERVER_URL":  "https://mcp.mendesloboconstrucao.com.br"
        }
      }
    }
  }
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from pathlib import Path

from concilium.infrastructure.settings import get_mcp_proxy

# ── Config from env ───────────────────────────────────────────────────────────

_MCP_PROXY_SETTINGS = get_mcp_proxy()
_SERVER_URL = _MCP_PROXY_SETTINGS.server_url
_DEVICE_ID = _MCP_PROXY_SETTINGS.device_id
_DEVICE_CODE = _MCP_PROXY_SETTINGS.device_code

_TOKEN_DIR = Path.home() / ".concilium" / "tokens"
_TOKEN_DIR.mkdir(parents=True, exist_ok=True)

_RENEW_BEFORE_S = 600  # renova 10 min antes do vencimento

# ── Token cache (local file) ──────────────────────────────────────────────────


def _token_path() -> Path:
    return _TOKEN_DIR / f"{_DEVICE_ID}.json"


def _load_cache() -> dict:
    p = _token_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_cache(data: dict) -> None:
    p = _token_path()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    p.chmod(0o600)


# ── Auth helpers ──────────────────────────────────────────────────────────────


def _activate(http_client) -> str:
    """Exchange device code for refresh token. Returns token_id."""
    if not _DEVICE_CODE:
        _die(
            "CONCILIUM_DEVICE_CODE não configurado e nenhum token em cache encontrado.\n"
            "Contate o admin para obter um novo device code."
        )
    resp = http_client.post(
        f"{_SERVER_URL}/auth/device/activate",
        json={"device_code": _DEVICE_CODE, "device_name": _DEVICE_ID},
        timeout=30,
    )
    if resp.status_code != 200:
        _die(f"Ativação falhou ({resp.status_code}): {resp.text}")
    data = resp.json()
    cache = _load_cache()
    cache["refresh_token"] = data["refresh_token"]
    cache["scopes"] = data.get("scopes", [])
    _save_cache(cache)
    return data["refresh_token"]


def _get_access_token(http_client) -> tuple[str, float]:
    """Return (access_token, expire_at_unix). Activates or refreshes as needed."""
    import time as _time

    cache = _load_cache()
    refresh_token = cache.get("refresh_token")

    if refresh_token:
        resp = http_client.post(
            f"{_SERVER_URL}/auth/token/refresh",
            json={"refresh_token": refresh_token},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            expires_in = data.get("expires_in", 28800)
            return data["access_token"], _time.time() + expires_in
        # refresh token invalid — re-activate
        _log("Refresh token expirado/revogado. Re-ativando...")

    # Activate device code → new refresh token
    refresh_token = _activate(http_client)
    resp = http_client.post(
        f"{_SERVER_URL}/auth/token/refresh",
        json={"refresh_token": refresh_token},
        timeout=30,
    )
    if resp.status_code != 200:
        _die(f"Falha ao obter access token ({resp.status_code}): {resp.text}")
    data = resp.json()
    expires_in = data.get("expires_in", 28800)
    return data["access_token"], _time.time() + expires_in


# ── Logging ───────────────────────────────────────────────────────────────────


def _log(msg: str) -> None:
    print(f"[concilium-mcp-proxy] {msg}", file=sys.stderr, flush=True)


def _die(msg: str) -> None:
    _log(f"ERRO: {msg}")
    sys.exit(1)


# ── MCP stdio ↔ HTTP bridge ───────────────────────────────────────────────────


class _State:
    """Shared mutable state between the main loop and the token refresh thread."""

    def __init__(self, access_token: str, expire_at: float) -> None:
        self.access_token = access_token
        self.expire_at = expire_at
        self.lock = threading.Lock()


def _refresh_loop(state: _State, http_client) -> None:
    """Background thread: renews access_token before expiry."""
    while True:
        with state.lock:
            remaining = state.expire_at - time.time()
        sleep_for = max(1, remaining - _RENEW_BEFORE_S)
        time.sleep(sleep_for)
        try:
            token, expire_at = _get_access_token(http_client)
            with state.lock:
                state.access_token = token
                state.expire_at = expire_at
            _log("Access token renovado.")
        except Exception as e:
            _log(f"Falha na renovação automática: {e}")


async def _bridge(state: _State, http_client) -> None:
    """Read JSON-RPC from stdin, POST to MCP server, write response to stdout."""
    loop = asyncio.get_event_loop()
    mcp_url = f"{_SERVER_URL}/mcp"

    while True:
        # Non-blocking stdin read
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break

        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        with state.lock:
            token = state.access_token

        try:
            resp = http_client.post(
                mcp_url,
                content=line,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
                timeout=300.0,
            )

            # Handle 401: token might have just expired, retry once with fresh token
            if resp.status_code == 401:
                new_token, expire_at = _get_access_token(http_client)
                with state.lock:
                    state.access_token = new_token
                    state.expire_at = expire_at
                resp = http_client.post(
                    mcp_url,
                    content=line,
                    headers={
                        "Authorization": f"Bearer {new_token}",
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                    timeout=300.0,
                )

            if resp.status_code != 200:
                _write_error(msg, f"HTTP {resp.status_code}: {resp.text[:200]}")
                continue

            content_type = resp.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                # SSE: emit each data event as a separate line
                for event_line in resp.text.splitlines():
                    if event_line.startswith("data:"):
                        data = event_line[5:].strip()
                        if data and data != "[DONE]":
                            sys.stdout.write(data + "\n")
                            sys.stdout.flush()
            else:
                sys.stdout.write(resp.text.strip() + "\n")
                sys.stdout.flush()

        except Exception as e:
            _write_error(msg, str(e))


def _write_error(msg: dict, error: str) -> None:
    err = {
        "jsonrpc": "2.0",
        "id": msg.get("id"),
        "error": {"code": -32000, "message": error},
    }
    sys.stdout.write(json.dumps(err) + "\n")
    sys.stdout.flush()


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Entry point for concilium-mcp-proxy."""
    try:
        import httpx
    except ImportError:
        _die("httpx não instalado. Execute: pip install httpx")

    _log(f"Iniciando proxy → {_SERVER_URL} (device: {_DEVICE_ID})")

    with httpx.Client() as http:
        access_token, expire_at = _get_access_token(http)
        _log("Autenticado com sucesso.")

        state = _State(access_token, expire_at)

        # Background token refresh thread
        t = threading.Thread(target=_refresh_loop, args=(state, http), daemon=True)
        t.start()

        # MCP bridge
        asyncio.run(_bridge(state, http))

    _log("Proxy encerrado.")
