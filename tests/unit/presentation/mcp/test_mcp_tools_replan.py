"""Tests for small-gap files: benchmark repository port, week_sequence, config mixin,
permission_guard, rate_limit, jwt_auth, replan MCP tool."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── presentation/mcp/tools/replan.py (missing lines 122-129, 145-146) ────────


class TestReplanMcpTool:
    def _register_tools(self, monkeypatch, tmp_path):
        import importlib

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
        from mcp.server.fastmcp import FastMCP

        mod = importlib.import_module("concilium.presentation.mcp.tools.replan")
        server = FastMCP("test-replan")
        mod.register(server)
        tools: dict = {}
        for t in server._tool_manager.list_tools():
            fn = getattr(t, "fn", None) or getattr(t, "func", None)
            tools[t.name] = fn
        return tools

    def _make_flat_store(self, canonical):
        store = MagicMock()
        store.escopo.side_effect = RuntimeError("sem escopos")
        store.load_canonical.return_value = canonical
        return store

    def test_simular_cenario_no_canonical(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        store = self._make_flat_store(None)
        with patch("concilium.presentation.mcp._context._project", return_value=store):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="lever_adjust", parametros={})
        assert "erro" in result

    def test_simular_cenario_unsupported_type(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        store = self._make_flat_store(MagicMock())
        with patch("concilium.presentation.mcp._context._project", return_value=store):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="unsupported_type", parametros={})
        assert "erro" in result
        assert "tipos_suportados" in result

    def test_simular_cenario_exception(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        with patch(
            "concilium.presentation.mcp._context._project",
            side_effect=RuntimeError("boom"),
        ):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="lever_adjust", parametros={})
        assert "erro" in result

    def test_simular_cenario_resolve_via_escopo_ativo(self, monkeypatch, tmp_path):
        """Caminho feliz: escopo -> plano ativo -> canonical, sem cair no fallback flat."""
        tools = self._register_tools(monkeypatch, tmp_path)
        canonical = MagicMock(ponto_equilibrio=[], resultado=None, projeto=None)
        active = MagicMock(plano_id="v1")
        plano = MagicMock()
        plano.load_canonical.return_value = canonical
        es = MagicMock()
        es.active_plan.return_value = active
        es.plan.return_value = plano
        store = MagicMock()
        store.escopo.return_value = es
        with (
            patch("concilium.presentation.mcp._context._project", return_value=store),
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="default"),
        ):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="lever_adjust", parametros={})
        assert "resumo" in result
        store.load_canonical.assert_not_called()

    def test_simular_cenario_no_active_plan_falls_back_to_flat(self, monkeypatch, tmp_path):
        """Branch 142->146: es.active_plan() é None -> cai no fallback store.load_canonical()."""
        tools = self._register_tools(monkeypatch, tmp_path)
        canonical = MagicMock(ponto_equilibrio=[], resultado=None, projeto=None)
        es = MagicMock()
        es.active_plan.return_value = None
        store = MagicMock()
        store.escopo.return_value = es
        store.load_canonical.return_value = canonical
        with (
            patch("concilium.presentation.mcp._context._project", return_value=store),
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="default"),
        ):
            result = tools["simular_cenario_replan"](project_id="proj-1", tipo="lever_adjust", parametros={})
        assert "resumo" in result
        store.load_canonical.assert_called_once()

    def test_ui_metas_missing_tool_is_skipped_silently(self, monkeypatch, tmp_path):
        """register(): se 'simular_cenario_replan' não estiver no tool_manager, o loop apenas pula."""
        import importlib

        from mcp.server.fastmcp import FastMCP

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
        mod = importlib.import_module("concilium.presentation.mcp.tools.replan")

        class _NoneForReplan(dict):
            def get(self, key, default=None):
                if key == "simular_cenario_replan":
                    return None
                return super().get(key, default)

        server = FastMCP("test-replan-ui-metas-missing")
        server._tool_manager._tools = _NoneForReplan()

        mod.register(server)  # should not raise

    def test_ui_metas_exception_setting_meta_is_swallowed(self, monkeypatch, tmp_path):
        """register(): exceção ao atribuir tool.meta é silenciada."""
        import importlib

        from mcp.server.fastmcp import FastMCP

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
        mod = importlib.import_module("concilium.presentation.mcp.tools.replan")

        class _RaisingMetaTool:
            @property
            def meta(self):
                return None

            @meta.setter
            def meta(self, value):
                raise RuntimeError("cannot set meta")

        class _RaisingForReplan(dict):
            def get(self, key, default=None):
                if key == "simular_cenario_replan":
                    return _RaisingMetaTool()
                return super().get(key, default)

        server = FastMCP("test-replan-ui-metas-raise")
        server._tool_manager._tools = _RaisingForReplan()

        mod.register(server)  # should not raise

    def test_simular_lever_adjust_sem_resultado_ignora_custo_indireto(self):
        from concilium.presentation.mcp.tools.replan import _simular_lever_adjust

        canonical = MagicMock(ponto_equilibrio=[], resultado=None, projeto=None)
        result = _simular_lever_adjust(canonical, {})
        assert result["resumo"]["custo_direto_atual"] == 0.0
        assert result["resumo"]["margem_pct_atual"] == 0.0


class TestConsultarPontoEquilibrio:
    """consultar_ponto_equilibrio — tabela equipe-a-equipe não-interativa (ADR-162 P1)."""

    def _register_tools(self, monkeypatch, tmp_path):
        import importlib

        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv("CONCILIUM__CONFIG_ROOT", str(config_dir))
        from mcp.server.fastmcp import FastMCP

        mod = importlib.import_module("concilium.presentation.mcp.tools.replan")
        server = FastMCP("test-replan-pe")
        mod.register(server)
        tools: dict = {}
        for t in server._tool_manager.list_tools():
            fn = getattr(t, "fn", None) or getattr(t, "func", None)
            tools[t.name] = fn
        return tools

    def _make_flat_store(self, canonical):
        store = MagicMock()
        store.escopo.side_effect = RuntimeError("sem escopos")
        store.load_canonical.return_value = canonical
        return store

    def test_build_tabela_ponto_equilibrio_usa_nome_eap_com_fallback_item_id(self):
        from concilium.presentation.mcp.tools.replan import _build_tabela_ponto_equilibrio

        eap_item_com_nome = MagicMock(item_id="ITEM-1", descricao="Equipe Terraplenagem")
        eap_item_sem_nome = MagicMock(item_id="ITEM-2", descricao=None)
        # custo_fixo_equipe (apesar do nome) é o custo operacional agregado real que
        # compõe `delta` — custo_operacional_real é uma grandeza diferente (não usada aqui).
        pe1 = MagicMock(
            item_id="ITEM-1",
            custo_venda_cpu=120000.0,
            custo_fixo_equipe=98000.0,
            custo_operacional_real=999999.0,
            pu_catalogo_unitario=120.0,
            pu_operacional_unitario=98.0,
        )
        pe2 = MagicMock(
            item_id="ITEM-2",
            custo_venda_cpu=85000.0,
            custo_fixo_equipe=91000.0,
            custo_operacional_real=999999.0,
            pu_catalogo_unitario=85.0,
            pu_operacional_unitario=91.0,
        )
        canonical = MagicMock(eap=[eap_item_com_nome, eap_item_sem_nome], ponto_equilibrio=[pe1, pe2])

        rows = _build_tabela_ponto_equilibrio(canonical)

        assert rows == [
            {
                "equipe": "Equipe Terraplenagem",
                "custo_venda": 120000.0,
                "custo_operacional": 98000.0,
                "pu_catalogo": 120.0,
                "pu_operacional": 98.0,
            },
            {
                "equipe": "ITEM-2",
                "custo_venda": 85000.0,
                "custo_operacional": 91000.0,
                "pu_catalogo": 85.0,
                "pu_operacional": 91.0,
            },
        ]

    def test_build_tabela_ponto_equilibrio_diferenca_reconcilia_com_delta_real(self):
        """A diferença (custo_venda - custo_operacional) exibida pela tabela deve bater
        com o `delta` real (ADR-162) — não com `custo_venda_cpu - custo_operacional_real`,
        que é uma grandeza diferente e divergiria sempre que há overhead de pool/rampa."""
        from concilium.presentation.mcp.tools.replan import _build_tabela_ponto_equilibrio

        custo_venda_total = 120000.0
        custo_operacional_agregado = 98000.0  # o que de fato compõe delta
        delta_real = custo_venda_total - custo_operacional_agregado
        pe = MagicMock(
            item_id="ITEM-1",
            custo_venda_cpu=custo_venda_total,
            custo_fixo_equipe=custo_operacional_agregado,
            delta=delta_real,
            custo_operacional_real=70000.0,  # grandeza distinta — deve ser ignorada aqui
            pu_catalogo_unitario=120.0,
            pu_operacional_unitario=98.0,
        )
        canonical = MagicMock(eap=[], ponto_equilibrio=[pe])

        row = _build_tabela_ponto_equilibrio(canonical)[0]

        assert row["custo_venda"] - row["custo_operacional"] == pytest.approx(delta_real)

    def test_consultar_ponto_equilibrio_no_canonical(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        store = self._make_flat_store(None)
        with patch("concilium.presentation.mcp._context._project", return_value=store):
            result = tools["consultar_ponto_equilibrio"](project_id="proj-1")
        assert "erro" in result

    def test_consultar_ponto_equilibrio_exception(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        with patch(
            "concilium.presentation.mcp._context._project",
            side_effect=RuntimeError("boom"),
        ):
            result = tools["consultar_ponto_equilibrio"](project_id="proj-1")
        assert "erro" in result

    def test_consultar_ponto_equilibrio_resolve_via_escopo_ativo(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        pe = MagicMock(
            item_id="ITEM-1",
            custo_venda_cpu=100.0,
            custo_fixo_equipe=80.0,
            pu_catalogo_unitario=1.0,
            pu_operacional_unitario=0.8,
        )
        canonical = MagicMock(eap=[], ponto_equilibrio=[pe])
        active = MagicMock(plano_id="v1")
        plano = MagicMock()
        plano.load_canonical.return_value = canonical
        es = MagicMock()
        es.active_plan.return_value = active
        es.plan.return_value = plano
        store = MagicMock()
        store.escopo.return_value = es
        with (
            patch("concilium.presentation.mcp._context._project", return_value=store),
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="default"),
        ):
            result = tools["consultar_ponto_equilibrio"](project_id="proj-1")
        assert result["equipes"] == [
            {
                "equipe": "ITEM-1",
                "custo_venda": 100.0,
                "custo_operacional": 80.0,
                "pu_catalogo": 1.0,
                "pu_operacional": 0.8,
            }
        ]
        store.load_canonical.assert_not_called()

    def test_consultar_ponto_equilibrio_no_active_plan_falls_back_to_flat(self, monkeypatch, tmp_path):
        tools = self._register_tools(monkeypatch, tmp_path)
        canonical = MagicMock(eap=[], ponto_equilibrio=[])
        es = MagicMock()
        es.active_plan.return_value = None
        store = MagicMock()
        store.escopo.return_value = es
        store.load_canonical.return_value = canonical
        with (
            patch("concilium.presentation.mcp._context._project", return_value=store),
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="default"),
        ):
            result = tools["consultar_ponto_equilibrio"](project_id="proj-1")
        assert result["equipes"] == []
        store.load_canonical.assert_called_once()

