"""Coverage sweep 3 — files with 20-35 lines missing."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    Venda,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )

def _minimal_canonical(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)

def _canonical_com_resultado():
    resultado = Resultado(
        venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
        custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
        resultado_financeiro=200_000.0,
        margem_pct=0.20,
        status_margem="VERDE",
        validacoes=[],
    )
    return _minimal_canonical(resultado=resultado)


# ─── presentation/mcp/server.py ───────────────────────────────────────────────


@pytest.mark.slow
class TestMcpServer:
    @pytest.fixture(scope="class")
    def _server(self):
        from concilium.presentation.mcp.server import build_server

        return build_server()

    def test_build_server_returns_server(self, _server):
        assert _server is not None

    def test_server_has_tools(self, _server):
        tools = list(_server._tool_manager._tools.keys())
        assert len(tools) > 20  # should have many tools registered




# ══ mcp_server/__main__.py ════════════════════════════════════════════════════


class TestMcpServerMain:
    def test_main_function_importable(self):
        """Importing mcp_server.__main__ should expose main (covers lines 2,4)."""
        import importlib

        mod = importlib.import_module("concilium.presentation.mcp.__main__")
        assert hasattr(mod, "main")

    def test_main_is_callable(self):
        from concilium.presentation.mcp.server import main

        assert callable(main)







# ─── presentation/mcp/server.py ───────────────────────────────────────────────


class TestMcpServer2:
    def test_build_server_returns_fastmcp(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path / "config"))
        (tmp_path / "config").mkdir()
        from concilium.presentation.mcp.server import build_server

        server = build_server()
        assert server is not None

    def test_patch_mcp_with_auth(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path / "config"))
        (tmp_path / "config").mkdir()
        from concilium.presentation.mcp.middleware import McpAuthMiddleware
        from concilium.presentation.mcp.server import _AuthenticatedFastMCP

        server = _AuthenticatedFastMCP("test")
        result = server.streamable_http_app()
        assert isinstance(result, McpAuthMiddleware)
        result_sse = server.sse_app()
        assert isinstance(result_sse, McpAuthMiddleware)

    def test_main_config_not_found(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(tmp_path / "nonexistent"))
        from concilium.presentation.mcp.server import main

        with pytest.raises(RuntimeError, match="não encontrado"):
            main()

    def test_main_config_not_dir(self, monkeypatch, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_file))
        from concilium.presentation.mcp.server import main

        with pytest.raises(RuntimeError, match="não é diretório"):
            main()




# ─── presentation/mcp/__main__.py (1 missing: line 6) ─────────────────────────


class TestMcpMain:
    def test_module_has_main(self):
        import concilium.presentation.mcp.__main__ as mod

        assert hasattr(mod, "main")

    def test_main_importable_from_module(self):
        from concilium.presentation.mcp.__main__ import main

        assert callable(main)



