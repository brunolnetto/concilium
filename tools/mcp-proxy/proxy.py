"""concilium-mcp-proxy — bridge stdio ↔ HTTP MCP com auth automática.

Fluxo de autenticação (totalmente transparente para o usuário):

  1ª execução (sem token em cache):
      CONCILIUM_CLIENT_CODE → MCP tool ativar_dispositivo() → refresh_token
      refresh_token salvo em ~/.concilium/tokens/<device_id>.json (chmod 600)

  Execuções seguintes:
      Lê refresh_token do cache → MCP tool renovar_token() → access_token (8h)
      Se refresh_token expirou → tenta reativar com CONCILIUM_CLIENT_CODE

  Auto-renovação em background:
      Thread monitora TTL do access_token → renova 10min antes do vencimento

Configuração simplificada (claude_desktop_config.json):
  {
    "mcpServers": {
      "concilium": {
        "command": "concilium-mcp-proxy",
        "env": {
          "CONCILIUM_SERVER_URL":  "https://mcp.mendesloboconstrucao.com.br",
          "CONCILIUM_CLIENT_CODE": "RCODE-..."
        }
      }
    }
  }

  device_id é auto-detectado (hostname ou username@hostname).
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import re
import socket
import sys
import threading
import time
from pathlib import Path
from typing import NoReturn


def _ensure_utf8_io(out=None, in_=None, err=None) -> None:
    """Força UTF-8 em stdout/stdin/stderr — no-op se já forem UTF-8.

    No Windows, quando stdin/stdout são redirecionados (pipes — sempre o caso
    quando o Claude Desktop spawna este processo), Python NÃO usa UTF-8 por
    padrão: cai no codepage legado do console (ex.: cp1252), diferente do
    console interativo real (PEP 528/529 só cobre esse caso). Toda descrição de
    tool em português tem acentuação (ex.: "saúde", "código", "configuração") —
    sem forçar UTF-8 aqui, tools/list (grande, cheio de texto acentuado)
    corrompe ao ser escrito/lido, enquanto prompts/list e resources/list
    (praticamente vazios) nunca acionam o bug.

    `errors="strict"` em stdout/stdin é intencional: preferimos falhar alto a
    mascarar corrupção silenciosa do protocolo JSON-RPC com "replace"/"ignore".
    stderr usa "replace" pois é só log/diagnóstico, não deve derrubar o
    processo por causa de um caractere num log.
    """
    out = out if out is not None else sys.stdout
    in_ = in_ if in_ is not None else sys.stdin
    err = err if err is not None else sys.stderr
    if out.encoding is None or out.encoding.lower() != "utf-8":
        out.reconfigure(encoding="utf-8", errors="strict")
    if in_.encoding is None or in_.encoding.lower() != "utf-8":
        in_.reconfigure(encoding="utf-8", errors="strict")
    if err.encoding is None or err.encoding.lower() != "utf-8":
        err.reconfigure(encoding="utf-8", errors="replace")


_ensure_utf8_io()

# ── Config from env ───────────────────────────────────────────────────────────
#
# Lido diretamente via os.environ em vez de `concilium.infrastructure.settings`
# de propósito: este script é empacotado standalone (PyInstaller, build-proxy.yml)
# e importar o pacote `concilium` arrasta suas dependências obrigatórias (rich,
# typer, matplotlib, streamlit, ortools...) — inflava o executável de ~9MB para
# ~35MB porque o `httpx` tem um `try: from ._main import main` (CLI opcional,
# extra "httpx[cli]") que passa a importar rich/pygments/PIL/numpy quando esses
# pacotes já estão instalados no mesmo venv por coincidência.


def _env_str(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip() or default


_SERVER_URL = _env_str("CONCILIUM_SERVER_URL", "https://mcp.mendesloboconstrucao.com.br").rstrip("/")
# CONCILIUM_DEVICE_CODE é o nome legado (pré-#17) — mantido como fallback pois
# configs sincronizadas externamente (ex.: perfil de conta do Claude Desktop)
# podem reverter para o nome antigo fora do nosso controle.
_CLIENT_CODE = _env_str("CONCILIUM_CLIENT_CODE", "") or _env_str("CONCILIUM_DEVICE_CODE", "")

try:
    _hostname = socket.gethostname()
    _username = platform.node() or ""
    _DEVICE_ID = f"{_username}-{_hostname}" if _username else _hostname
except Exception:
    _DEVICE_ID = "unknown-device"

_TOKEN_DIR = Path.home() / ".concilium" / "tokens"
_TOKEN_DIR.mkdir(parents=True, exist_ok=True)

_RENEW_BEFORE_S = 600  # renova 10 min antes do vencimento
_REQUEST_ID_COUNTER = 0  # contador para IDs de requisições MCP internas

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


# ── MCP Tool Call Helpers ─────────────────────────────────────────────────────


def _build_mcp_request_headers(access_token: str | None, session_id: str) -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    if session_id:
        headers["mcp-session-id"] = session_id
    return headers


# SSE (RFC 8895) só reconhece CRLF/CR/LF como terminador de linha — o mesmo
# conjunto usado por `ServerSentEvent._LINE_SEP_EXPR` no sse_starlette (servidor)
# para codificar o evento. NÃO usar `str.splitlines()` (nem `httpx.Response.
# iter_lines()`, cuja doc diz textualmente "has the same behaviour as the
# stdlib splitlines"): ambos também quebram em U+2028/U+2029 (LINE/PARAGRAPH
# SEPARATOR) e em \v, \f, \x1c-\x1e, \x85 — caracteres VÁLIDOS e NÃO-ESCAPADOS
# dentro de uma string JSON (nem `json.dumps` nem o `model_dump_json` do
# pydantic os escapam). Uma description de tool ou campo de schema contendo um
# desses caracteres — muito mais provável num payload grande de tools/list do
# que nos payloads quase vazios de prompts/list e resources/list — fragmenta o
# evento `data:` no meio: só o prefixo (que ainda começa com "data:") é
# capturado, e o resto da mensagem — inclusive as chaves de fechamento — é
# descartado silenciosamente, corrompendo a resposta JSON-RPC.
_SSE_LINE_SEP = re.compile(r"\r\n|\r|\n")


def _split_sse_lines(text: str) -> list[str]:
    """Divide texto SSE em linhas lógicas — apenas por CRLF/CR/LF (ver nota acima)."""
    return _SSE_LINE_SEP.split(text)


def _parse_sse_stream_response(resp) -> dict:
    # Resposta SSE - extrai linha "data: {...}". Lê os bytes brutos em vez de
    # usar resp.iter_lines() (que fragmenta em U+2028/U+2029, ver _split_sse_lines).
    body_bytes = b""
    try:
        for chunk in resp.iter_bytes():
            body_bytes += chunk
    except Exception:
        # Servidor pode fechar conexão prematuramente - isso é OK se já temos dados
        pass

    result_json = None
    for line in _split_sse_lines(body_bytes.decode("utf-8", errors="replace")):
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]":
                result_json = data
                break

    if not result_json:
        raise RuntimeError("Nenhum dado recebido no SSE stream")

    return json.loads(result_json)


def _parse_plain_json_response(resp) -> dict:
    # Resposta JSON pura
    body_bytes = b""
    try:
        for chunk in resp.iter_bytes():
            body_bytes += chunk
    except Exception:
        # Servidor pode fechar conexão - tenta parsear o que foi recebido
        pass

    if not body_bytes:
        raise RuntimeError("Resposta vazia do servidor")

    return json.loads(body_bytes.decode("utf-8"))


def _read_mcp_stream_result(resp) -> dict:
    if resp.status_code != 200:
        error_text = b"".join(resp.iter_bytes()).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {resp.status_code}: {error_text[:200]}")

    # Lê o body - pode ser JSON puro ou SSE (text/event-stream)
    content_type = resp.headers.get("content-type", "")

    if "text/event-stream" in content_type:
        result = _parse_sse_stream_response(resp)
    else:
        result = _parse_plain_json_response(resp)

    if "error" in result:
        raise RuntimeError(f"MCP error: {result['error']}")

    return result.get("result", {})


def _mcp_call(http_client, tool_name: str, args: dict, access_token: str | None = None, session_id: str = "") -> dict:
    """Faz uma chamada MCP tool via HTTP.

    Args:
        http_client: httpx.Client
        tool_name: Nome do tool MCP (ex: "ativar_dispositivo")
        args: Argumentos do tool
        access_token: Bearer token (None para tools públicos)
        session_id: MCP session ID (streamable-http)

    Returns:
        Resultado do tool (dict) ou levanta exceção
    """
    global _REQUEST_ID_COUNTER
    _REQUEST_ID_COUNTER += 1

    request = {
        "jsonrpc": "2.0",
        "id": _REQUEST_ID_COUNTER,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": args,
        },
    }

    headers = _build_mcp_request_headers(access_token, session_id)

    # Use stream para SSE responses - FastMCP pode retornar SSE mesmo para tools/call
    with http_client.stream(
        "POST",
        f"{_SERVER_URL}/mcp",
        json=request,
        headers=headers,
        timeout=30.0,
    ) as resp:
        return _read_mcp_stream_result(resp)


# ── Session initialization (streamable-http protocol) ─────────────────────────


def _initialize_session(http_client, access_token: str | None = None) -> str:
    """Inicializa sessão MCP via protocolo streamable-http.

    Args:
        http_client: httpx.Client
        access_token: Bearer token (None para handshake público)

    Returns:
        mcp-session-id extraído do header da resposta
    """
    global _REQUEST_ID_COUNTER
    _REQUEST_ID_COUNTER += 1

    request = {
        "jsonrpc": "2.0",
        "id": _REQUEST_ID_COUNTER,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "concilium-mcp-proxy", "version": "1.0"},
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    # Usa stream=True mas fecha logo após receber o header
    with http_client.stream(
        "POST",
        f"{_SERVER_URL}/mcp",
        json=request,
        headers=headers,
        timeout=30.0,
    ) as resp:
        if resp.status_code != 200:
            # Lê body apenas em caso de erro
            error_text = b"".join(resp.iter_bytes()).decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {resp.status_code}: {error_text[:200]}")

        session_id = resp.headers.get("mcp-session-id", "")
        if not session_id:
            raise RuntimeError("Servidor não retornou mcp-session-id no header")

        # Tenta ler um chunk do SSE stream, mas ignora se o servidor fechar prematuramente
        # O importante é ter o session_id do header
        try:
            # Lê um chunk para evitar "ASGI callable returned without completing response"
            _ = next(resp.iter_bytes(chunk_size=1024), None)
        except Exception:
            # Servidor pode fechar conexão - não é erro se já temos session_id
            pass

    # Handshake MCP: o servidor só processa tools/call depois de receber
    # notifications/initialized — sem isso o SSE fica aberto sem dados para sempre.
    notif_headers = dict(headers)
    notif_headers["mcp-session-id"] = session_id
    http_client.post(
        f"{_SERVER_URL}/mcp",
        json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers=notif_headers,
        timeout=30.0,
    )

    return session_id


# ── Auth helpers ──────────────────────────────────────────────────────────────


def _activate(http_client, session_id: str) -> str:
    """Exchange client code for refresh token via MCP tool ativar_dispositivo."""
    if not _CLIENT_CODE:
        _die(
            "CONCILIUM_CLIENT_CODE não configurado e nenhum token em cache encontrado.\n"
            "Contate o admin para obter um novo código de cliente."
        )

    try:
        result = _mcp_call(
            http_client,
            "ativar_dispositivo",
            {"client_code": _CLIENT_CODE, "device_name": _DEVICE_ID},
            access_token=None,  # tool público
            session_id=session_id,
        )

        # Extrai o resultado do content
        content = result.get("content", [])
        if not content:
            raise RuntimeError("Resposta vazia de ativar_dispositivo")

        data = json.loads(content[0].get("text", "{}"))

        if data.get("status") != "ok":
            raise RuntimeError(data.get("message", "Ativação falhou"))

        refresh_token = data["refresh_token"]
        cache = _load_cache()
        cache["refresh_token"] = refresh_token
        cache["device_id"] = data.get("device_id", _DEVICE_ID)
        cache["client_id"] = data.get("client_id")
        _save_cache(cache)

        return refresh_token

    except Exception as e:
        _die(f"Ativação falhou: {e}")


def _get_access_token(http_client, session_id: str) -> tuple[str, float]:
    """Return (access_token, expire_at_unix). Activates or refreshes as needed."""
    import time as _time

    cache = _load_cache()
    refresh_token = cache.get("refresh_token")

    if refresh_token:
        try:
            result = _mcp_call(
                http_client,
                "renovar_token",
                {"refresh_token": refresh_token},
                access_token=None,  # tool público
                session_id=session_id,
            )

            # Extrai o resultado do content
            content = result.get("content", [])
            if not content:
                raise RuntimeError("Resposta vazia de renovar_token")

            data = json.loads(content[0].get("text", "{}"))

            if data.get("status") != "ok":
                raise RuntimeError(data.get("message", "Renovação falhou"))

            access_token = data["access_token"]
            expires_in = data.get("expires_in", 28800)
            return access_token, _time.time() + expires_in

        except Exception:
            _log("Refresh token expirado/revogado. Re-ativando...")

    # Activate client code → new refresh token
    refresh_token = _activate(http_client, session_id)

    # Tenta novamente renovar com o novo refresh_token
    result = _mcp_call(
        http_client,
        "renovar_token",
        {"refresh_token": refresh_token},
        access_token=None,
        session_id=session_id,
    )

    content = result.get("content", [])
    if not content:
        _die("Falha ao obter access token: resposta vazia")

    data = json.loads(content[0].get("text", "{}"))

    if data.get("status") != "ok":
        _die(f"Falha ao obter access token: {data.get('message')}")

    access_token = data["access_token"]
    expires_in = data.get("expires_in", 28800)
    return access_token, _time.time() + expires_in


# ── Logging ───────────────────────────────────────────────────────────────────


def _log(msg: str) -> None:
    print(f"[concilium-mcp-proxy] {msg}", file=sys.stderr, flush=True)


def _die(msg: str) -> NoReturn:
    _log(f"ERRO: {msg}")
    sys.exit(1)


def _e_erro_de_dns(erro: Exception) -> bool:
    """True quando a causa é resolução de nome (getaddrinfo/11001), não conectividade."""
    texto = str(erro)
    return any(t in texto for t in ("getaddrinfo", "11001", "Name or service not known", "nodename nor servname"))


def _initialize_session_com_retries(http_client, tentativas: int = 3):
    """Inicializa a sessão MCP com retries e mensagem de erro acionável.

    Falha de DNS (errno 11001 no Windows) ou de conexão não deve virar traceback
    cru do PyInstaller ("Failed to execute script") — o usuário final do .exe
    precisa saber O QUE checar. Retries cobrem blips transitórios (VPN
    reconectando, resolver lento)."""
    import httpx

    for tentativa in range(1, tentativas + 1):
        try:
            return _initialize_session(http_client)
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            if tentativa < tentativas:
                espera = 2**tentativa
                _log(
                    f"Falha ao conectar em {_SERVER_URL} ({e}) — "
                    f"tentativa {tentativa}/{tentativas}, novo teste em {espera}s…"
                )
                time.sleep(espera)
                continue
            if _e_erro_de_dns(e):
                _die(
                    f"Não foi possível RESOLVER o endereço do servidor: {_SERVER_URL}\n"
                    "  Isso é um problema de DNS/rede DESTA máquina (o servidor não chegou a ser contatado):\n"
                    "    1. Teste:  nslookup mcp.mendesloboconstrucao.com.br  (e com 8.8.8.8 ao final)\n"
                    "    2. Windows: ipconfig /flushdns  e verifique VPN/proxy corporativo\n"
                    "    3. Alternativa: defina a variável CONCILIUM_SERVER_URL com o FQDN direto do\n"
                    "       Container App (az containerapp show -n concilium-mcp -g concilium-rg\n"
                    "       --query properties.configuration.ingress.fqdn)"
                )
            _die(
                f"Não foi possível CONECTAR ao servidor {_SERVER_URL}: {e}\n"
                "  O nome resolveu, mas a conexão falhou — verifique firewall/proxy corporativo e\n"
                "  se a porta 443 de saída está liberada."
            )


# ── MCP stdio ↔ HTTP bridge ───────────────────────────────────────────────────


class _State:
    """Shared mutable state between the main loop and the token refresh thread."""

    def __init__(self, access_token: str, expire_at: float, session_id: str = "") -> None:
        self.access_token = access_token
        self.expire_at = expire_at
        self.session_id = session_id
        self.lock = threading.Lock()


def _refresh_loop(state: _State, http_client) -> None:
    """Background thread: renews access_token before expiry."""
    while True:
        with state.lock:
            remaining = state.expire_at - time.time()
            session_id = state.session_id
        sleep_for = max(1, remaining - _RENEW_BEFORE_S)
        time.sleep(sleep_for)
        try:
            token, expire_at = _get_access_token(http_client, session_id)
            with state.lock:
                state.access_token = token
                state.expire_at = expire_at
            _log("Access token renovado.")
        except Exception as e:
            _log(f"Falha na renovação automática: {e}")


def _post_bridge_message(http_client, mcp_url: str, line: str, token: str, session_id: str):
    return http_client.post(
        mcp_url,
        content=line,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "mcp-session-id": session_id,
        },
        timeout=300.0,
    )


def _write_bridge_response(resp) -> None:
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        # SSE: emit each data event as a separate line. Usa _split_sse_lines
        # (não resp.text.splitlines()) — ver nota em _parse_sse_stream_response.
        for event_line in _split_sse_lines(resp.text):
            if event_line.startswith("data:"):
                data = event_line[5:].strip()
                if data and data != "[DONE]":
                    sys.stdout.write(data + "\n")
                    sys.stdout.flush()
    else:
        sys.stdout.write(resp.text.strip() + "\n")
        sys.stdout.flush()


async def _bridge_handle_message(state: _State, http_client, mcp_url: str, line: str, msg: dict) -> None:
    with state.lock:
        token = state.access_token
        session_id = state.session_id

    try:
        resp = _post_bridge_message(http_client, mcp_url, line, token, session_id)

        # Handle 401: token might have just expired, retry once with fresh token
        if resp.status_code == 401:
            new_token, expire_at = _get_access_token(http_client, session_id)
            with state.lock:
                state.access_token = new_token
                state.expire_at = expire_at
            resp = _post_bridge_message(http_client, mcp_url, line, new_token, session_id)

        if resp.status_code != 200:
            _write_error(msg, f"HTTP {resp.status_code}: {resp.text[:200]}")
            return

        _write_bridge_response(resp)

    except Exception as e:
        _write_error(msg, str(e))


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

        await _bridge_handle_message(state, http_client, mcp_url, line, msg)


def _write_error(msg: dict, error: str) -> None:
    """Escreve uma resposta JSON-RPC de erro no stdout — mas só se `msg` for uma
    requisição (tem 'id'). Notifications (sem 'id') nunca recebem resposta pelo
    protocolo JSON-RPC; ecoar 'id: null' de volta é inválido e alguns clientes
    (ex.: Claude Desktop) rejeitam a mensagem inteira por causa disso."""
    if "id" not in msg:
        _log(f"Notification '{msg.get('method', '?')}' falhou (sem resposta, por protocolo): {error}")
        return
    err = {
        "jsonrpc": "2.0",
        "id": msg["id"],
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
        # Inicializa sessão MCP (streamable-http protocol) — com retries e erro
        # acionável em falha de DNS/conexão (nada de traceback cru no .exe)
        session_id = _initialize_session_com_retries(http)
        _log(f"Sessão MCP iniciada (ID: {session_id[:12]}...)")

        # Obtém access token via tools públicos (ativar_dispositivo + renovar_token)
        access_token, expire_at = _get_access_token(http, session_id)
        _log("Autenticado com sucesso.")

        state = _State(access_token, expire_at, session_id)

        # Background token refresh thread
        t = threading.Thread(target=_refresh_loop, args=(state, http), daemon=True)
        t.start()

        # MCP bridge
        asyncio.run(_bridge(state, http))

    _log("Proxy encerrado.")


if __name__ == "__main__":
    main()
