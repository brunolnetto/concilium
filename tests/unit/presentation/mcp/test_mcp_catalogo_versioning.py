"""Tests for MCP catalogo.py — version tools and wrapper coverage."""

from __future__ import annotations

import json
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


# ─── _com_deadline_de_catalogo decorator ───────────────────────────────────────


class TestComDeadlineDeCatalogo:
    """2026-08-12: substitui _run_catalog_write_with_deadline — mesma proteção
    (thread + wait_for), mas aplicada direto sobre a função `def` original em
    vez de exigir um wrapper `async def` manual repetindo os parâmetros."""

    def test_preserva_nome_e_assinatura_da_funcao_original(self):
        import inspect

        from concilium.presentation.mcp.tools.catalogo import _com_deadline_de_catalogo

        def minha_tool(contexto_id: str, insumo_id: str) -> dict:
            return {"ok": True}

        wrapped = _com_deadline_de_catalogo(minha_tool)
        assert wrapped.__name__ == "minha_tool"
        assert list(inspect.signature(wrapped).parameters) == ["contexto_id", "insumo_id"]

    async def test_decorator_produz_funcao_async_que_executa_o_corpo_original(self):
        import inspect

        from concilium.presentation.mcp.tools.catalogo import _com_deadline_de_catalogo

        def minha_tool(x: int) -> dict:
            return {"x": x}

        wrapped = _com_deadline_de_catalogo(minha_tool)
        assert inspect.iscoroutinefunction(wrapped)
        assert await wrapped(5) == {"x": 5}

    async def test_decorator_aplica_deadline_e_nao_propaga_o_timeout_error(self, monkeypatch):
        import time

        import concilium.presentation.mcp.tools.catalogo as catalogo_mod

        monkeypatch.setattr(catalogo_mod, "TOOL_IO_TIMEOUT_S", 0.01)

        def minha_tool_lenta(x: int) -> dict:
            time.sleep(0.2)
            return {"x": x}

        wrapped = catalogo_mod._com_deadline_de_catalogo(minha_tool_lenta)
        result = await wrapped(5)
        assert "erro" in result
        assert "minha_tool_lenta" in result["erro"]
        assert "excedeu" in result["erro"]


# ─── Wrapper tools (thin delegation) ──────────────────────────────────────────


class TestCatalogoWrappers:
    async def test_listar_contextos(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_listar_contextos",
            return_value={"contextos": ["ctx-1"]},
        ):
            result = await tools["listar_contextos"]()
        assert "contextos" in result

    async def test_pesquisar_catalogo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_pesquisar_catalogo",
            return_value={"cpus": []},
        ):
            result = await tools["pesquisar_catalogo"](contexto_id="ctx", query="escavação")
        assert "cpus" in result

    async def test_pesquisar_catalogo_times_out_returns_erro_instead_of_hanging(self, monkeypatch, tmp_path):
        """issue #147/#148/#149: mesmo achado do ping() — load_catalogo() sem
        deadline pendura o tool até o timeout opaco de 60s do client."""
        import time

        tools = _register_tools(monkeypatch, tmp_path)

        def _slow(*args, **kwargs):
            time.sleep(0.2)
            return {"cpus": []}

        with (
            patch(f"{_CATALOGO_MOD}.TOOL_IO_TIMEOUT_S", 0.01),
            patch(f"{_CATALOGO_MOD}._impl_pesquisar_catalogo", side_effect=_slow),
        ):
            result = await tools["pesquisar_catalogo"](contexto_id="ctx", query="escavação")

        assert "erro" in result
        assert "excedeu" in result["erro"]

    async def test_auditar_catalogo_saude(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='saude' substitui consultar_saude_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_consultar_saude_catalogo",
            return_value={"cobertura_pct": 80},
        ):
            result = await tools["auditar_catalogo"](contexto_id="ctx", modo="saude")
        assert "cobertura_pct" in result

    async def test_auditar_catalogo_plausibilidade(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='plausibilidade' substitui avaliar_plausibilidade_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_avaliar_plausibilidade_catalogo",
            return_value={"alertas": []},
        ):
            result = await tools["auditar_catalogo"](contexto_id="ctx", modo="plausibilidade")
        assert "alertas" in result

    async def test_auditar_catalogo_integridade(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='integridade' substitui verificar_integridade_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_verificar_integridade_catalogo",
            return_value={"erros": []},
        ):
            result = await tools["auditar_catalogo"](contexto_id="ctx", modo="integridade")
        assert "erros" in result

    async def test_auditar_catalogo_modo_invalido(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = await tools["auditar_catalogo"](contexto_id="ctx", modo="invalido")
        assert "erro" in result

    async def test_auditar_catalogo_times_out_returns_erro_instead_of_hanging(self, monkeypatch, tmp_path):
        """2026-08-12: uma das ~15 tools que não tinham a proteção de #147/#153 —
        cobertura representativa de que @_com_deadline_de_catalogo protege
        também as tools de leitura/validação, não só as de escrita."""
        import time

        tools = _register_tools(monkeypatch, tmp_path)

        def _slow(*args, **kwargs):
            time.sleep(0.2)
            return {"cobertura_pct": 80}

        with (
            patch(f"{_CATALOGO_MOD}.TOOL_IO_TIMEOUT_S", 0.01),
            patch(f"{_CATALOGO_MOD}._impl_consultar_saude_catalogo", side_effect=_slow),
        ):
            result = await tools["auditar_catalogo"](contexto_id="ctx", modo="saude")
        assert "erro" in result
        assert "excedeu" in result["erro"]

    async def test_atualizar_preco_insumo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_atualizar_preco_insumo",
            return_value={"ok": True},
        ):
            result = await tools["atualizar_preco_insumo"](contexto_id="ctx", insumo_id="INS-1", novo_preco=10.0)
        assert result["ok"] is True

    async def test_adicionar_variante_producao(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_adicionar_variante_producao",
            return_value={"variante_id": "VAR-1"},
        ):
            result = await tools["adicionar_variante_producao"](
                contexto_id="ctx",
                producao_id="P1",
                variante_id="VAR-1",
                nome_variante="v1",
                producao_horaria=50.0,
                equipe_json='{"op": 1}',
            )
        assert result["variante_id"] == "VAR-1"

    async def test_atualizar_composicao_item_cpu(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_atualizar_composicao_item_cpu",
            return_value={"status": "RASCUNHO"},
        ) as impl:
            result = await tools["atualizar_composicao_item_cpu"](
                contexto_id="ctx",
                cpu_id="CPU-001",
                insumo_id="MA-001",
                acao="adicionar",
                rascunho_id="v1",
                coeficiente=0.5,
                categoria_custo="MATERIAL",
            )
        assert result["status"] == "RASCUNHO"
        impl.assert_called_once_with("ctx", "CPU-001", "adicionar", "MA-001", "v1", 0.5, "MATERIAL", None, None, None)

    async def test_atualizar_composicao_item_cpu_listar_nao_exige_insumo_id_nem_rascunho_id(
        self, monkeypatch, tmp_path
    ):
        """acao='listar' — leitura, sem insumo_id/rascunho_id (ação que não existia;
        usuário tentou usá-la e ficou sem retorno por hang de outra tool, não desta)."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_atualizar_composicao_item_cpu",
            return_value={"cpu_id": "CPU-001", "composicao_itens": []},
        ) as impl:
            result = await tools["atualizar_composicao_item_cpu"](contexto_id="ctx", cpu_id="CPU-001", acao="listar")
        assert result["composicao_itens"] == []
        impl.assert_called_once_with("ctx", "CPU-001", "listar", None, None, None, None, None, None, None)

    async def test_atualizar_composicao_item_cpu_times_out_returns_erro_instead_of_hanging(self, monkeypatch, tmp_path):
        """2026-08-12: bug real reportado — acao='listar'/'remover' travaram 4min sem
        retorno em produção. Causa raiz: nenhuma tool MCP síncrona roda fora do event
        loop; uma chamada travada (ex.: catálogo via SharePoint sob throttling) congela
        o processo pra todas as outras, mesmo tools leves como esta. Mesma mitigação de
        pesquisar_catalogo (issue #147/#148/#149/#153)."""
        import time

        tools = _register_tools(monkeypatch, tmp_path)

        def _slow(*args, **kwargs):
            time.sleep(0.2)
            return {"status": "RASCUNHO"}

        with (
            patch(f"{_CATALOGO_MOD}.TOOL_IO_TIMEOUT_S", 0.01),
            patch(f"{_CATALOGO_MOD}._impl_atualizar_composicao_item_cpu", side_effect=_slow),
        ):
            result = await tools["atualizar_composicao_item_cpu"](contexto_id="ctx", cpu_id="CPU-001", acao="listar")
        assert "erro" in result

    async def test_historico_preco_insumo_pontual_sem_insumo_id_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = await tools["historico_preco_insumo"](contexto_id="ctx", modo="pontual", data_referencia="2026-01-01")
        assert "erro" in result

    async def test_historico_preco_insumo_pontual_sem_data_referencia_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = await tools["historico_preco_insumo"](contexto_id="ctx", modo="pontual", insumo_id="INS-1")
        assert "erro" in result

    async def test_historico_preco_insumo_modo_invalido_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = await tools["historico_preco_insumo"](contexto_id="ctx", modo="invalido")
        assert "erro" in result

    async def test_historico_preco_insumo_pontual(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='pontual' substitui consultar_preco_insumo_temporal."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_consultar_preco_insumo_temporal",
            return_value={"preco": 5.5},
        ):
            result = await tools["historico_preco_insumo"](
                contexto_id="ctx", modo="pontual", insumo_id="INS-1", data_referencia="2026-01-01"
            )
        assert result["preco"] == 5.5

    async def test_historico_preco_insumo_tendencia(self, monkeypatch, tmp_path):
        """ADR-116 F5: modo='tendencia' substitui tendencia_precos_catalogo."""
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_tendencia_precos_catalogo",
            return_value={"tendencias": []},
        ):
            result = await tools["historico_preco_insumo"](contexto_id="ctx", modo="tendencia")
        assert "tendencias" in result

    async def test_comparar_catalogo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_comparar_catalogo",
            return_value={"divergencias": []},
        ):
            result = await tools["comparar_catalogo"](origem_a="catA", origem_b="catB", tipo="todos")
        assert "divergencias" in result

    async def test_mesclar_catalogo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_mesclar_catalogo",
            return_value={"mode": "DRY_RUN"},
        ):
            result = await tools["mesclar_catalogo"](destino="dest", origem="orig", dry_run=True, tipo="todos")
        assert result["mode"] == "DRY_RUN"

    async def test_calcular_pu_producao(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch(
            f"{_CATALOGO_MOD}._impl_calcular_pu_producao",
            return_value={"pu": 1500.0},
        ):
            result = await tools["calcular_pu_producao"](contexto_id="ctx", producao_id="P1")
        assert result["pu"] == 1500.0


class TestVersionTools:
    async def test_versoes_catalogo_listar(self, monkeypatch, tmp_path):
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
            result = await tools["versoes_catalogo"](contexto_id="ctx-1", modo="listar")
        assert result["contexto_id"] == "ctx-1"
        assert result["versao_atual"] == "v2"
        assert result["total_versoes"] == 2

    async def test_versoes_catalogo_listar_exception(self, monkeypatch, tmp_path):
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
            result = await tools["versoes_catalogo"](contexto_id="ctx-missing", modo="listar")
        assert "erro" in result

    async def test_versoes_catalogo_comparar(self, monkeypatch, tmp_path):
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
            result = await tools["versoes_catalogo"](contexto_id="ctx-1", modo="comparar", versao_a="v1", versao_b="v2")
        assert result["contexto_id"] == "ctx-1"
        assert "diff" in result

    async def test_versoes_catalogo_comparar_exception(self, monkeypatch, tmp_path):
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
            result = await tools["versoes_catalogo"](
                contexto_id="ctx-1", modo="comparar", versao_a="v1", versao_b="bad"
            )
        assert "erro" in result

    async def test_versoes_catalogo_comparar_sem_versao_a_ou_b_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["versoes_catalogo"](contexto_id="ctx-1", modo="comparar", versao_a="v1", versao_b=None)
        assert "erro" in result

    async def test_versoes_catalogo_modo_invalido_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["versoes_catalogo"](contexto_id="ctx-1", modo="invalido")
        assert "erro" in result


class TestCatalogLifecycleADR120:
    """Ciclo de vida de rascunho de catálogo: criar, listar divergências, impacto, aprovar/rejeitar merge."""

    async def test_criar_rascunho_catalogo_sucesso(self, monkeypatch, tmp_path):
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
            result = await tools["criar_rascunho_catalogo"](contexto_id="ctx-1", descricao="Reajuste INCC")
        assert result["rascunho_id"] == "v2"
        assert result["versao_ativa"] == "v1"
        assert result["status"] == "RASCUNHO"
        assert result["criado_por"] == "eng-1"

    async def test_criar_rascunho_catalogo_excecao_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["criar_rascunho_catalogo"](contexto_id="ctx-1", descricao="Reajuste INCC")
        assert "erro" in result

    async def test_novo_rascunho_nao_herda_estado_de_rascunho_anterior_aprovado(self, monkeypatch, tmp_path):
        """Regressão (achada durante ADR-166): ContextoVersionService.create_version clona
        `existing[-1]` inteiro como base (só remove version/created_at/created_by/motivo) —
        se o rascunho anterior já foi aprovado, o novo nascia com `_aprovado=True` e os
        `_deltas` antigos herdados, rejeitando qualquer edição nova como "rascunho em
        estado terminal". Usa o ContextoVersionService REAL (sem mock) para exercitar o
        bug de verdade, não a versão mockada dos outros testes desta classe."""
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"

        with patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="autor-1"):
            r1 = await tools["criar_rascunho_catalogo"](contexto_id="ctx-1", descricao="primeiro rascunho")
        assert "erro" not in r1
        v1_id = r1["rascunho_id"]

        # Simula o estado de v1 após um aprovar_merge_catalogo real: aprovado, com deltas.
        v1_file = config_root / "contextos" / "ctx-1" / "versions" / f"{v1_id}.json"
        v1_data = json.loads(v1_file.read_text(encoding="utf-8"))
        v1_data["_revisado"] = True
        v1_data["_revisado_por"] = "autor-1"
        v1_data["_aprovado"] = True
        v1_data["_aprovado_por"] = "aprovador-1"
        v1_data["_deltas"] = [{"tipo": "criacao_insumo", "insumo": {"codigo": "EPI-X"}}]
        v1_file.write_text(json.dumps(v1_data), encoding="utf-8")

        with patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="autor-2"):
            r2 = await tools["criar_rascunho_catalogo"](contexto_id="ctx-1", descricao="segundo rascunho")
        assert "erro" not in r2
        v2_id = r2["rascunho_id"]
        assert v2_id != v1_id

        v2_file = config_root / "contextos" / "ctx-1" / "versions" / f"{v2_id}.json"
        v2_data = json.loads(v2_file.read_text(encoding="utf-8"))
        assert v2_data.get("_aprovado") is not True, "novo rascunho não pode nascer já aprovado"
        assert not v2_data.get("_revisado"), "novo rascunho não pode nascer já revisado"
        assert not v2_data.get("_rejeitado")
        assert v2_data.get("_deltas") in (None, []), "novo rascunho não pode herdar deltas do anterior"

    async def test_listar_divergencias_rascunho_sucesso(self, monkeypatch, tmp_path):
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
            result = await tools["listar_divergencias_rascunho"](contexto_id="ctx-1", rascunho_id="v2")
        assert result["versao_ativa"] == "v1"
        assert result["rascunho_id"] == "v2"
        assert "divergencias" in result

    async def test_listar_divergencias_rascunho_marca_revisado(self, monkeypatch, tmp_path):
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
            await tools["listar_divergencias_rascunho"](contexto_id="ctx-1", rascunho_id="v2")
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_revisado"] is True
        assert data["_revisado_por"] == "eng-1"

    async def test_listar_divergencias_rascunho_excecao_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["listar_divergencias_rascunho"](contexto_id="ctx-1", rascunho_id="v2")
        assert "erro" in result

    async def test_consultar_impacto_reajuste_sucesso(self, monkeypatch, tmp_path):
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
            result = await tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        assert result["n_insumos_afetados"] == 2
        assert set(result["insumos_modificados"]) == {"INS-1", "INS-2"}

    async def test_consultar_impacto_reajuste_marca_revisado(self, monkeypatch, tmp_path):
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
            await tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_revisado"] is True

    async def test_consultar_impacto_reajuste_excecao_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["consultar_impacto_reajuste"](contexto_id="ctx-1", rascunho_id="v2")
        assert "erro" in result

    async def test_aprovar_merge_catalogo_rascunho_nao_encontrado(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result

    async def test_aprovar_merge_catalogo_entity_dir_inexistente_ainda_retorna_sucesso(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"

    async def test_aprovar_merge_catalogo_sem_meta_file_ainda_atualiza_ponteiro(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"
        assert (entity_dir / "current").read_text(encoding="utf-8") == "v2"

    async def test_aprovar_merge_catalogo_sucesso_promove_ponteiro_current(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"
        assert result["versao_ativa"] == "v2"
        assert result["aprovado_por"] == "mgr-1"
        assert (entity_dir / "current").read_text(encoding="utf-8") == "v2"
        import json as _json

        assert _json.loads(meta_file.read_text(encoding="utf-8"))["current_version"] == "v2"

    async def test_aprovar_merge_catalogo_marca_aprovado_no_arquivo(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        versions_dir = entity_dir / "versions"
        versions_dir.mkdir(parents=True)
        rascunho_file = versions_dir / "v2.json"
        rascunho_file.write_text('{"foo": "bar", "_revisado": true}', encoding="utf-8")
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_aprovado"] is True
        assert data["_aprovado_por"] == "mgr-1"

    async def test_aprovar_merge_catalogo_multiplos_deltas_itera_o_loop_inteiro(self, monkeypatch, tmp_path):
        # branch 527->514 — o ramo `elif tipo == "variante_producao"` precisa
        # avaliar False (tipo desconhecido) com um próximo item na lista, para
        # que o loop volte ao topo (514) em vez de sair/entrar em algum ramo.
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        entity_dir.mkdir(parents=True)

        rascunho_data = {
            "version": "v2",
            "_revisado": True,
            "_deltas": [
                {"tipo": "tipo_desconhecido_futuro"},
                {
                    "tipo": "preco_insumo",
                    "insumo_id": "INS-1",
                    "novo_preco": 55.0,
                    "jurisdicao_id": None,
                    "nota": None,
                    "autor": "mgr-1",
                },
            ],
        }
        version_svc = MagicMock()
        version_svc.resolve.return_value = rascunho_data
        version_svc.current_version.return_value = "v1"

        ctx = MagicMock()
        ctx.catalogo_id = "cat-1"
        rt = MagicMock()
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {"cpus": [], "insumos": [], "producoes": []}

        apply_preco_mock = MagicMock()
        apply_variante_mock = MagicMock()

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.presentation.mcp.tools._catalogo_tools_helpers_a._apply_preco_insumo_delta",
                apply_preco_mock,
            ),
            patch(
                "concilium.presentation.mcp.tools._catalogo_tools_helpers_a._apply_variante_producao_delta",
                apply_variante_mock,
            ),
        ):
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")

        assert result["status"] == "APROVADO"
        # o delta de tipo desconhecido não bate em nenhum ramo (nem preco_insumo
        # nem variante_producao) — só o segundo delta (preco_insumo) é aplicado.
        assert apply_variante_mock.call_count == 0
        assert apply_preco_mock.call_count == 1
        assert result["deltas_aplicados"] == 1

    async def test_aprovar_merge_catalogo_aplica_delta_criacao_insumo(self, monkeypatch, tmp_path):
        """ADR-163 D5: delta tipo=criacao_insumo é aplicado via _apply_criar_insumo_delta."""
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        entity_dir.mkdir(parents=True)

        insumo_novo = {
            "codigo": "EQ-999",
            "tipo": "EQUIPAMENTO",
            "descricao": "Retroescavadeira",
            "unidade": "h",
            "preco_unitario": 120.0,
            "categoria": "TERRAPLENAGEM",
            "fonte_preco": "cotacao_mercado",
            "atributos_especificos": {},
        }
        rascunho_data = {
            "version": "v2",
            "_revisado": True,
            "_deltas": [{"tipo": "criacao_insumo", "insumo": insumo_novo, "autor": "mgr-1"}],
        }
        version_svc = MagicMock()
        version_svc.resolve.return_value = rascunho_data
        version_svc.current_version.return_value = "v1"

        ctx = MagicMock()
        ctx.catalogo_id = "cat-1"
        rt = MagicMock()
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {"cpus": [], "insumos": [], "producoes": []}

        apply_criar_mock = MagicMock()

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.presentation.mcp.tools._catalogo_tools_helpers_a._apply_criar_insumo_delta",
                apply_criar_mock,
            ),
        ):
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")

        assert result["status"] == "APROVADO"
        assert apply_criar_mock.call_count == 1
        assert result["deltas_aplicados"] == 1

    async def test_aprovar_merge_catalogo_aplica_delta_descontinuacao_insumo(self, monkeypatch, tmp_path):
        """ADR-163 D6: delta tipo=descontinuacao_insumo é aplicado via _apply_descontinuacao_insumo_delta."""
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        entity_dir.mkdir(parents=True)

        rascunho_data = {
            "version": "v2",
            "_revisado": True,
            "_deltas": [
                {"tipo": "descontinuacao_insumo", "insumo_id": "EQ-001", "motivo": "obsoleto", "autor": "mgr-1"}
            ],
        }
        version_svc = MagicMock()
        version_svc.resolve.return_value = rascunho_data
        version_svc.current_version.return_value = "v1"

        ctx = MagicMock()
        ctx.catalogo_id = "cat-1"
        rt = MagicMock()
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {"cpus": [], "insumos": [], "producoes": []}

        apply_descontinuar_mock = MagicMock()

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.presentation.mcp.tools._catalogo_tools_helpers_a._apply_descontinuacao_insumo_delta",
                apply_descontinuar_mock,
            ),
        ):
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")

        assert result["status"] == "APROVADO"
        assert apply_descontinuar_mock.call_count == 1
        assert result["deltas_aplicados"] == 1

    async def test_aprovar_merge_catalogo_aplica_delta_composicao_item(self, monkeypatch, tmp_path):
        """Delta tipo=composicao_item é aplicado via _apply_composicao_item_delta (governança
        de composicao_itens de CPU, mesmo padrão de criacao_insumo/descontinuacao_insumo)."""
        tools = _register_tools(monkeypatch, tmp_path)
        config_root = tmp_path / "config"
        entity_dir = config_root / "contextos" / "ctx-1"
        entity_dir.mkdir(parents=True)

        rascunho_data = {
            "version": "v2",
            "_revisado": True,
            "_deltas": [
                {
                    "tipo": "composicao_item",
                    "cpu_id": "CPU-001",
                    "insumo_id": "MA-DIESEL-S10",
                    "acao": "remover",
                    "coeficiente": None,
                    "categoria_custo": None,
                    "unidade": None,
                    "tipo_combustivel": None,
                    "autor": "mgr-1",
                }
            ],
        }
        version_svc = MagicMock()
        version_svc.resolve.return_value = rascunho_data
        version_svc.current_version.return_value = "v1"

        ctx = MagicMock()
        ctx.catalogo_id = "cat-1"
        rt = MagicMock()
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {"cpus": [], "insumos": [], "producoes": []}

        apply_composicao_mock = MagicMock()

        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch("concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=config_root)),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch(
                "concilium.presentation.mcp.tools._catalogo_tools_helpers_a._apply_composicao_item_delta",
                apply_composicao_mock,
            ),
        ):
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")

        assert result["status"] == "APROVADO"
        assert apply_composicao_mock.call_count == 1
        call_args = apply_composicao_mock.call_args[0]
        assert call_args[1:] == ("CPU-001", "MA-DIESEL-S10", "remover", None, None, None, None)
        assert result["deltas_aplicados"] == 1

    async def test_aprovar_merge_catalogo_ainda_nao_revisado_bloqueia(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result
        assert "revisado" in result["erro"]

    async def test_aprovar_merge_catalogo_rascunho_rejeitado_nao_pode_ser_promovido(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result
        assert "rejeitado" in result["erro"]

    async def test_aprovar_merge_catalogo_mesmo_ator_viola_quatro_olhos(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result
        assert "quatro olhos" in result["erro"]

    async def test_aprovar_merge_catalogo_atores_diferentes_permite_aprovacao(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert result["status"] == "APROVADO"

    async def test_aprovar_merge_catalogo_excecao_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result

    async def test_aprovar_merge_catalogo_times_out_returns_erro_instead_of_hanging(self, monkeypatch, tmp_path):
        """2026-08-12: cobertura representativa das tools de merge/escrita crítica
        que ganharam a proteção de #147/#153 nesta rodada (aprovar_merge_catalogo,
        rejeitar_rascunho_catalogo, promover_override_projeto, mesclar_catalogo)."""
        import time

        tools = _register_tools(monkeypatch, tmp_path)
        version_svc = MagicMock()
        version_svc.resolve.side_effect = lambda *a, **k: time.sleep(0.2) or {"version": "v2", "_revisado": True}
        with (
            patch(
                "concilium.application.services.catalog.contexto_version_service.ContextoVersionService",
                return_value=version_svc,
            ),
            patch(
                "concilium.infrastructure.settings.get_storage", return_value=MagicMock(config_root=tmp_path / "config")
            ),
            patch("concilium.infrastructure.auth.permission_guard.get_current_user_id", return_value="mgr-1"),
            patch(f"{_CATALOGO_MOD}.TOOL_IO_TIMEOUT_S", 0.01),
        ):
            result = await tools["aprovar_merge_catalogo"](contexto_id="ctx-1", rascunho_id="v2", justificativa="ok")
        assert "erro" in result
        assert "excedeu" in result["erro"]

    async def test_rejeitar_rascunho_catalogo_nao_encontrado(self, monkeypatch, tmp_path):
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
            result = await tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert "erro" in result

    async def test_rejeitar_rascunho_catalogo_arquivo_inexistente_ainda_retorna_sucesso(self, monkeypatch, tmp_path):
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
            result = await tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert result["status"] == "REJEITADO"

    async def test_rejeitar_rascunho_catalogo_sucesso_marca_arquivo(self, monkeypatch, tmp_path):
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
            result = await tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert result["status"] == "REJEITADO"
        assert result["rejeitado_por"] == "mgr-1"
        import json as _json

        data = _json.loads(rascunho_file.read_text(encoding="utf-8"))
        assert data["_rejeitado"] is True
        assert data["_motivo_rejeicao"] == "ruim"

    async def test_rejeitar_rascunho_catalogo_ja_aprovado_bloqueia(self, monkeypatch, tmp_path):
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
            result = await tools["rejeitar_rascunho_catalogo"](
                contexto_id="ctx-1", rascunho_id="v2", motivo="tarde demais"
            )
        assert "erro" in result
        assert "aprovado" in result["erro"]

    async def test_rejeitar_rascunho_catalogo_ja_rejeitado_bloqueia(self, monkeypatch, tmp_path):
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
            result = await tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="de novo")
        assert "erro" in result
        assert "rejeitado" in result["erro"]

    async def test_rejeitar_rascunho_catalogo_excecao_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["rejeitar_rascunho_catalogo"](contexto_id="ctx-1", rascunho_id="v2", motivo="ruim")
        assert "erro" in result


class TestExportarPesquisaMercado:
    async def test_tipo_invalido_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        result = await tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="invalido")
        assert "erro" in result

    async def test_falha_ao_carregar_contexto_retorna_erro(self, monkeypatch, tmp_path):
        tools = _register_tools(monkeypatch, tmp_path)
        with patch("concilium.presentation.mcp._context._runtime", side_effect=RuntimeError("sem contexto")):
            result = await tools["exportar_pesquisa_mercado"](contexto_id="ctx-inexistente", tipo="price")
        assert "erro" in result

    async def test_price_survey_sucesso(self, monkeypatch, tmp_path):
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
            result = await tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="price")
        assert result["tipo"] == "price"
        assert result["encoding"] == "base64"
        assert "conteudo_base64" in result

    async def test_productivity_survey_sucesso(self, monkeypatch, tmp_path):
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
            result = await tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="productivity")
        assert result["tipo"] == "productivity"
        assert "conteudo_base64" in result

    async def test_falha_ao_gerar_pesquisa_retorna_erro(self, monkeypatch, tmp_path):
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
            result = await tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="price")
        assert "erro" in result

    async def test_planilha_grande_demais_retorna_aviso(self, monkeypatch, tmp_path):
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
            result = await tools["exportar_pesquisa_mercado"](contexto_id="ctx-1", tipo="price")
        assert "aviso" in result
        assert "conteudo_base64" not in result
