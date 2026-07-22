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

    def test_historico_preco_insumo_pontual_sem_insumo_id_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = tools["historico_preco_insumo"](contexto_id="ctx", modo="pontual", data_referencia="2026-01-01")
        assert "erro" in result

    def test_historico_preco_insumo_pontual_sem_data_referencia_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = tools["historico_preco_insumo"](contexto_id="ctx", modo="pontual", insumo_id="INS-1")
        assert "erro" in result

    def test_historico_preco_insumo_modo_invalido_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = tools["historico_preco_insumo"](contexto_id="ctx", modo="invalido")
        assert "erro" in result

    def test_historico_preco_insumo_pontual(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='pontual' substitui consultar_preco_insumo_temporal."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_consultar_preco_insumo_temporal",
            return_value={"preco": 5.5},
        ):
            result = tools["historico_preco_insumo"](
                contexto_id="ctx", modo="pontual", insumo_id="INS-1", data_referencia="2026-01-01"
            )
        assert result["preco"] == 5.5

    def test_historico_preco_insumo_tendencia(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='tendencia' substitui tendencia_precos_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_tendencia_precos_catalogo",
            return_value={"tendencias": []},
        ):
            result = tools["historico_preco_insumo"](contexto_id="ctx", modo="tendencia")
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
    def test_versoes_catalogo_listar(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='listar' substitui listar_versoes_catalogo."""
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
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["versoes_catalogo"](contexto_id="ctx-1", modo="listar")
        assert result["contexto_id"] == "ctx-1"
        assert result["versao_atual"] == "v2"
        assert result["total_versoes"] == 2

    def test_versoes_catalogo_listar_exception(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.list_versions.side_effect = FileNotFoundError("not found")
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["versoes_catalogo"](contexto_id="ctx-missing", modo="listar")
        assert "erro" in result

    def test_versoes_catalogo_comparar(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='comparar' substitui comparar_versoes_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.compare.return_value = {"adicionados": [], "removidos": [], "modificados": []}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["versoes_catalogo"](contexto_id="ctx-1", modo="comparar", versao_a="v1", versao_b="v2")
        assert result["contexto_id"] == "ctx-1"
        assert "diff" in result

    def test_versoes_catalogo_comparar_exception(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.compare.side_effect = ValueError("versão inválida")
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["versoes_catalogo"](contexto_id="ctx-1", modo="comparar", versao_a="v1", versao_b="bad")
        assert "erro" in result

    def test_versoes_catalogo_comparar_sem_versao_a_ou_b_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=MagicMock(),
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["versoes_catalogo"](contexto_id="ctx-1", modo="comparar", versao_a="v1", versao_b=None)
        assert "erro" in result

    def test_versoes_catalogo_modo_invalido_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=MagicMock(),
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["versoes_catalogo"](contexto_id="ctx-1", modo="invalido")
        assert "erro" in result


class TestCatalogLifecycleADR120:
    """Ciclo de vida de rascunho de catálogo: criar, listar divergências, impacto, aprovar/rejeitar merge."""

    def test_criar_rascunho_catalogo_sucesso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.current_version.return_value = "v1"
        version_svc.create_version.return_value = {"version": "v2"}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="eng-1"),
        ):
            result = tools["criar_rascunho_catalogo"](contexto_id="ctx-1", descricao="Reajuste INCC")
        assert result["rascunho_id"] == "v2"
        assert result["versao_ativa"] == "v1"
        assert result["status"] == "RASCUNHO"
        assert result["criado_por"] == "eng-1"

    def test_criar_rascunho_catalogo_excecao_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.current_version.side_effect = FileNotFoundError("contexto ausente")
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="eng-1"),
        ):
            result = tools["criar_rascunho_catalogo"](contexto_id="ctx-1", descricao="Reajuste INCC")
        assert "erro" in result

    def test_listar_divergencias_rascunho_sucesso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.current_version.return_value = "v1"
        version_svc.compare.return_value = {"modificados": {"INS-1": {}}}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["listar_divergencias_rascunho"](contexto_id="ctx-1", rascunho_id="v2")
        assert result["versao_ativa"] == "v1"
        assert result["rascunho_id"] == "v2"
        assert "divergencias" in result

    def test_listar_divergencias_rascunho_marca_revisado(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        versions_dir = config_root / "contextos" / "ctx-1" / "versions"
        versions_dir.mkdir(parents=True)
        rascunho_file = versions_dir / "v2.json"
        rascunho_file.write_text('{"foo": "bar"}', encoding="utf-8")
        version_svc = MagicMock()
        version_svc.current_version.return_value = "v1"
        version_svc.compare.return_value = {"modificados": {}}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="eng-1"),
        ):
            tools["listar_divergencias_rascunho"](contexto_id="ctx-1", rascunho_id="v2")
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_revisado"] is True
        assert data["_revisado_por"] == "eng-1"

    def test_listar_divergencias_rascunho_excecao_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.compare.side_effect = ValueError("versão inexistente")
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["listar_divergencias_rascunho"](contexto_id="ctx-1", rascunho_id="v2")
        assert "erro" in result

    def test_consultar_impacto_reajuste_sucesso(self, monkeypatch, tmp_path):
        # ADR-145 P11: n_insumos_afetados vem dos deltas do rascunho (_deltas),
        # não mais de uma chave "modificados" que ContextoVersionService.compare()
        # nunca produziu.
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.current_version.return_value = "v1"
        version_svc.resolve.return_value = {
            "_deltas": [
                {"tipo": "preco_insumo", "insumo_id": "INS-1"},
                {"tipo": "preco_insumo", "insumo_id": "INS-2"},
                {"tipo": "variante_producao", "producao_id": "PROD-1"},  # não conta como insumo
            ]
        }
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        assert result["n_insumos_afetados"] == 2
        assert set(result["insumos_modificados"]) == {"INS-1", "INS-2"}

    def test_consultar_impacto_reajuste_marca_revisado(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        versions_dir = config_root / "contextos" / "ctx-1" / "versions"
        versions_dir.mkdir(parents=True)
        rascunho_file = versions_dir / "v2.json"
        rascunho_file.write_text('{"foo": "bar"}', encoding="utf-8")
        version_svc = MagicMock()
        version_svc.current_version.return_value = "v1"
        version_svc.compare.return_value = {"modificados": {}}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="eng-1"),
        ):
            tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_revisado"] is True

    def test_consultar_impacto_reajuste_excecao_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.side_effect = ValueError("versão inexistente")
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
        ):
            result = tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        assert "erro" in result

    def test_aprovar_merge_catalogo_rascunho_nao_encontrado(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = None
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result

    def test_aprovar_merge_catalogo_entity_dir_inexistente_ainda_retorna_sucesso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "_revisado": True}
        version_svc.current_version.return_value = "v1"
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"

    def test_aprovar_merge_catalogo_sem_meta_file_ainda_atualiza_ponteiro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        entity_dir.mkdir(parents=True)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "_revisado": True}
        version_svc.current_version.return_value = "v1"
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"
        assert (entity_dir / "current").read_text(encoding="utf-8") == "v2"

    def test_aprovar_merge_catalogo_sucesso_promove_ponteiro_current(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        entity_dir.mkdir(parents=True)
        meta_file = entity_dir / "ctx-1.json"
        meta_file.write_text('{"current_version": "v1"}', encoding="utf-8")
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "_revisado": True}
        version_svc.current_version.return_value = "v1"
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"
        assert result["versao_ativa"] == "v2"
        assert result["aprovado_por"] == "mgr-1"
        assert (entity_dir / "current").read_text(encoding="utf-8") == "v2"
        import json as _json

        assert _json.loads(meta_file.read_text(encoding="utf-8"))["current_version"] == "v2"

    def test_aprovar_merge_catalogo_marca_aprovado_no_arquivo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        versions_dir = entity_dir / "versions"
        versions_dir.mkdir(parents=True)
        rascunho_file = versions_dir / "v2.json"
        rascunho_file.write_text('{"foo": "bar"}', encoding="utf-8")
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "_revisado": True}
        version_svc.current_version.return_value = "v1"
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_aprovado"] is True
        assert data["_aprovado_por"] == "mgr-1"

    def test_aprovar_merge_catalogo_ainda_nao_revisado_bloqueia(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2"}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result
        assert "revisado" in result["erro"]

    def test_aprovar_merge_catalogo_rascunho_rejeitado_nao_pode_ser_promovido(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {
            "version": "v2",
            "created_by": "eng-1",
            "_rejeitado": True,
            "_motivo_rejeicao": "preço fora do range sensato",
        }
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result
        assert "rejeitado" in result["erro"]

    def test_aprovar_merge_catalogo_mesmo_ator_viola_quatro_olhos(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "created_by": "mgr-1", "_revisado": True}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result
        assert "quatro olhos" in result["erro"]

    def test_aprovar_merge_catalogo_atores_diferentes_permite_aprovacao(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "created_by": "eng-1", "_revisado": True}
        version_svc.current_version.return_value = "v1"
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"

    def test_aprovar_merge_catalogo_excecao_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.side_effect = ValueError("corrompido")
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result

    def test_rejeitar_rascunho_catalogo_nao_encontrado(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = None
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert "erro" in result

    def test_rejeitar_rascunho_catalogo_arquivo_inexistente_ainda_retorna_sucesso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2"}
        version_svc.current_version.return_value = "v1"
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert result["status"] == "REJEITADO"

    def test_rejeitar_rascunho_catalogo_sucesso_marca_arquivo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        versions_dir = config_root / "contextos" / "ctx-1" / "versions"
        versions_dir.mkdir(parents=True)
        rascunho_file = versions_dir / "v2.json"
        rascunho_file.write_text('{"foo": "bar"}', encoding="utf-8")
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2"}
        version_svc.current_version.return_value = "v1"
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert result["status"] == "REJEITADO"
        assert result["rejeitado_por"] == "mgr-1"
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_rejeitado"] is True
        assert data["_motivo_rejeicao"] == "ruim"

    def test_rejeitar_rascunho_catalogo_ja_aprovado_bloqueia(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "_aprovado": True, "_aprovado_por": "mgr-1"}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-2"),
        ):
            result = tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="tarde demais")
        assert "erro" in result
        assert "aprovado" in result["erro"]

    def test_rejeitar_rascunho_catalogo_ja_rejeitado_bloqueia(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.return_value = {"version": "v2", "_rejeitado": True, "_motivo_rejeicao": "primeira vez"}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="de novo")
        assert "erro" in result
        assert "rejeitado" in result["erro"]

    def test_rejeitar_rascunho_catalogo_excecao_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.side_effect = ValueError("corrompido")
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
        ):
            result = tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert "erro" in result


class TestExportarPesquisaMercado:
    def test_tipo_invalido_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="invalido")
        assert "erro" in result

    def test_falha_ao_carregar_contexto_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch("concilium.presentation.mcp._context._runtime", side_effect=RuntimeError("sem contexto")):
            result = tools["exportar_pesquisa_mercado"](contexto_id="ctx-inexistente", tipo="price")
        assert "erro" in result

    def test_price_survey_sucesso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        rt = MagicMock()
        ctx = MagicMock(jurisdicao_id="jur-1", tema_id="tema-1", catalogo_id="cat-1")
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}
        exporter = MagicMock()

        def _fake_export(path):
            path.write_bytes(b"fake-xlsx-bytes")

        exporter.export.side_effect = _fake_export
        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.infrastructure.exporters.price_survey.PriceSurveyExporter",
                return_value=exporter,
            ),
        ):
            result = tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="price")
        assert result["tipo"] == "price"
        assert result["encoding"] == "base64"
        assert "conteudo_base64" in result

    def test_productivity_survey_sucesso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        rt = MagicMock()
        ctx = MagicMock(jurisdicao_id="jur-1", tema_id="tema-1", catalogo_id="cat-1")
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}
        exporter = MagicMock()

        def _fake_export(path):
            path.write_bytes(b"fake-xlsx-bytes")

        exporter.export.side_effect = _fake_export
        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.infrastructure.exporters.productivity_survey.ProductivitySurveyExporter",
                return_value=exporter,
            ),
        ):
            result = tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="productivity")
        assert result["tipo"] == "productivity"
        assert "conteudo_base64" in result

    def test_falha_ao_gerar_pesquisa_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        rt = MagicMock()
        ctx = MagicMock(jurisdicao_id="jur-1", tema_id="tema-1", catalogo_id="cat-1")
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}
        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.infrastructure.exporters.price_survey.PriceSurveyExporter",
                side_effect=RuntimeError("disco cheio"),
            ),
        ):
            result = tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="price")
        assert "erro" in result

    def test_planilha_grande_demais_retorna_aviso(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        rt = MagicMock()
        ctx = MagicMock(jurisdicao_id="jur-1", tema_id="tema-1", catalogo_id="cat-1")
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}
        exporter = MagicMock()

        def _fake_export(path):
            path.write_bytes(b"\0" * (21 * 1024 * 1024))

        exporter.export.side_effect = _fake_export
        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.infrastructure.exporters.price_survey.PriceSurveyExporter",
                return_value=exporter,
            ),
        ):
            result = tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="price")
        assert "aviso" in result
        assert "conteudo_base64" not in result
