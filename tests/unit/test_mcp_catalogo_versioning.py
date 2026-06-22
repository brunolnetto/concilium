"""Tests for MCP catalogo.py — version tools and wrapper coverage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP

_CATALOGO_MOD = "concilium.presentation.mcp.tools.catalogo"


def _register_tools(monkeypatch, tmp_path: Path) -> dict:
    import importlib

    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))

    mod = importlib.import_module(_CATALOGO_MOD)
    server = FastMCP("test-cat")
    mod.register(server)

    tools: dict = {}
    for t in server._tool_manager.list_tools():
        fn = getattr(t, "fn", None) or getattr(t, "func", None)
        tools[t.name] = fn
    return tools


# ─── _catalog_root helper ──────────────────────────────────────────────────────


def test_catalog_root(tmp_path):
    from concilium.presentation.mcp.tools.catalogo import _catalog_root

    result = _catalog_root(tmp_path / "config", "mendeslobo")
    assert result == tmp_path / "config" / "catalogos" / "mendeslobo"


# ─── Wrapper tools (thin delegation) ──────────────────────────────────────────


class TestCatalogoWrappers:
    def test_listar_contextos(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_listar_contextos",
            return_value={"contextos": ["ctx-1"]},
        ):
            result = tools["listar_contextos"]()
        assert "contextos" in result

    def test_pesquisar_catalogo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_pesquisar_catalogo",
            return_value={"cpus": []},
        ):
            result = tools["pesquisar_catalogo"](contexto_id="ctx", query="escavação")
        assert "cpus" in result

    def test_auditar_catalogo_saude(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='saude' substitui consultar_saude_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_consultar_saude_catalogo",
            return_value={"cobertura_pct": 80},
        ):
            result = tools["auditar_catalogo"](contexto_id="ctx", modo="saude")
        assert "cobertura_pct" in result

    def test_auditar_catalogo_plausibilidade(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='plausibilidade' substitui avaliar_plausibilidade_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_avaliar_plausibilidade_catalogo",
            return_value={"alertas": []},
        ):
            result = tools["auditar_catalogo"](contexto_id="ctx", modo="plausibilidade")
        assert "alertas" in result

    def test_auditar_catalogo_integridade(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='integridade' substitui verificar_integridade_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_verificar_integridade_catalogo",
            return_value={"erros": []},
        ):
            result = tools["auditar_catalogo"](contexto_id="ctx", modo="integridade")
        assert "erros" in result

    def test_auditar_catalogo_modo_invalido(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = tools["auditar_catalogo"](contexto_id="ctx", modo="invalido")
        assert "erro" in result

    def test_atualizar_preco_insumo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_atualizar_preco_insumo",
            return_value={"ok": True},
        ):
            result = tools["atualizar_preco_insumo"](contexto_id="ctx", insumo_id="INS-1", novo_preco=10.0)
        assert result["ok"] is True

    def test_adicionar_variante_producao(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_adicionar_variante_producao",
            return_value={"variante_id": "VAR-1"},
        ):
            result = tools["adicionar_variante_producao"](
                contexto_id="ctx",
                producao_id="P1",
                variante_id="VAR-1",
                nome_variante="v1",
                valor_horario=50.0,
                equipe_json='{"op": 1}',
            )
        assert result["variante_id"] == "VAR-1"

    def test_consultar_preco_insumo_temporal(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_consultar_preco_insumo_temporal",
            return_value={"preco": 5.5},
        ):
            result = tools["consultar_preco_insumo_temporal"](
                contexto_id="ctx", insumo_id="INS-1", data_referencia="2026-01-01"
            )
        assert result["preco"] == 5.5

    def test_tendencia_precos_catalogo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_tendencia_precos_catalogo",
            return_value={"tendencias": []},
        ):
            result = tools["tendencia_precos_catalogo"](contexto_id="ctx")
        assert "tendencias" in result

    def test_comparar_rfi_catalogo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_comparar_rfi_catalogo",
            return_value={"divergencias": []},
        ):
            result = tools["comparar_rfi_catalogo"](contexto_id="ctx", dry_run=True)
        assert "divergencias" in result

    def test_calcular_pu_producao(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_calcular_pu_producao",
            return_value={"pu": 1500.0},
        ):
            result = tools["calcular_pu_producao"](contexto_id="ctx", producao_id="P1")
        assert result["pu"] == 1500.0


class TestVersionTools:
    def test_listar_versoes_catalogo_happy(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.list_versions.return_value = [{"versao": "v1"}, {"versao": "v2"}]
        version_svc.current_version.return_value = "v2"

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=MagicMock(config_root=tmp_path / "config"),
            ),
        ):
            result = tools["listar_versoes_catalogo"](contexto_id="ctx-1")
        assert result["contexto_id"] == "ctx-1"
        assert result["versao_atual"] == "v2"
        assert result["total_versoes"] == 2

    def test_listar_versoes_catalogo_exception(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.list_versions.side_effect = FileNotFoundError("not found")

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=MagicMock(config_root=tmp_path / "config"),
            ),
        ):
            result = tools["listar_versoes_catalogo"](contexto_id="ctx-missing")
        assert "erro" in result

    def test_comparar_versoes_catalogo_happy(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.compare.return_value = {"adicionados": [], "removidos": [], "modificados": []}

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=MagicMock(config_root=tmp_path / "config"),
            ),
        ):
            result = tools["comparar_versoes_catalogo"](contexto_id="ctx-1", versao_a="v1", versao_b="v2")
        assert result["contexto_id"] == "ctx-1"
        assert "diff" in result

    def test_comparar_versoes_catalogo_exception(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.compare.side_effect = ValueError("versão inválida")

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage",
                return_value=MagicMock(config_root=tmp_path / "config"),
            ),
        ):
            result = tools["comparar_versoes_catalogo"](contexto_id="ctx-1", versao_a="v1", versao_b="bad")
        assert "erro" in result
