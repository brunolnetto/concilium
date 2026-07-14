"""Proxy MCP (tools/mcp-proxy/proxy.py) — falha de conexão com retries e erro acionável.

Contexto: em campo (Windows, .exe PyInstaller), uma falha de DNS (errno 11001,
`getaddrinfo failed`) derrubava o proxy com traceback cru ("Failed to execute
script 'proxy'"). O usuário final precisa de mensagem acionável (checar DNS/VPN,
override CONCILIUM_SERVER_URL) e de retries para blips transitórios.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest

_PROXY_PATH = Path(__file__).resolve().parents[2] / "tools" / "mcp-proxy" / "proxy.py"


@pytest.fixture(scope="module")
def proxy():
    spec = importlib.util.spec_from_file_location("concilium_mcp_proxy", _PROXY_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["concilium_mcp_proxy"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestDeteccaoDns:
    def test_getaddrinfo_e_dns(self, proxy):
        assert proxy._e_erro_de_dns(httpx.ConnectError("[Errno 11001] getaddrinfo failed"))

    def test_linux_name_resolution_e_dns(self, proxy):
        assert proxy._e_erro_de_dns(httpx.ConnectError("[Errno -2] Name or service not known"))

    def test_connection_refused_nao_e_dns(self, proxy):
        assert not proxy._e_erro_de_dns(httpx.ConnectError("[Errno 111] Connection refused"))


class TestInitializeComRetries:
    def test_sucesso_na_segunda_tentativa(self, proxy, monkeypatch):
        chamadas = {"n": 0}

        def fake_init(_http):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                raise httpx.ConnectError("blip transitório")
            return "sessao-ok"

        monkeypatch.setattr(proxy, "_initialize_session", fake_init)
        monkeypatch.setattr(proxy.time, "sleep", lambda _s: None)
        assert proxy._initialize_session_com_retries(object(), tentativas=3) == "sessao-ok"
        assert chamadas["n"] == 2

    def test_dns_esgotado_morre_com_mensagem_acionavel(self, proxy, monkeypatch, capsys):
        def fake_init(_http):
            raise httpx.ConnectError("[Errno 11001] getaddrinfo failed")

        monkeypatch.setattr(proxy, "_initialize_session", fake_init)
        monkeypatch.setattr(proxy.time, "sleep", lambda _s: None)
        with pytest.raises(SystemExit) as exc:
            proxy._initialize_session_com_retries(object(), tentativas=2)
        assert exc.value.code == 1
        err = capsys.readouterr().err
        assert "RESOLVER" in err
        assert "nslookup" in err
        assert "CONCILIUM_SERVER_URL" in err

    def test_conexao_recusada_morre_com_mensagem_de_firewall(self, proxy, monkeypatch, capsys):
        def fake_init(_http):
            raise httpx.ConnectError("[Errno 111] Connection refused")

        monkeypatch.setattr(proxy, "_initialize_session", fake_init)
        monkeypatch.setattr(proxy.time, "sleep", lambda _s: None)
        with pytest.raises(SystemExit):
            proxy._initialize_session_com_retries(object(), tentativas=2)
        err = capsys.readouterr().err
        assert "CONECTAR" in err
        assert "firewall" in err

    def test_timeout_tambem_e_retryado(self, proxy, monkeypatch):
        chamadas = {"n": 0}

        def fake_init(_http):
            chamadas["n"] += 1
            if chamadas["n"] < 3:
                raise httpx.ConnectTimeout("timed out")
            return "sessao-ok"

        monkeypatch.setattr(proxy, "_initialize_session", fake_init)
        monkeypatch.setattr(proxy.time, "sleep", lambda _s: None)
        assert proxy._initialize_session_com_retries(object(), tentativas=3) == "sessao-ok"
