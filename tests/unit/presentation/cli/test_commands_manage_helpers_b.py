"""Coverage sweep 7 — jobs/service, backtracking_pe_builder, catalog_loader, helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ─── presentation/cli/_commands_manage_helpers_b.py ──────────────────────────


class TestManageHelpersBFunctions:
    def test_module_importable(self):
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        assert mod is not None

    def test_functions_exist(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_layer

        assert callable(_cs_resolve_layer)

    def test_cs_resolve_layer_target_wins(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_layer

        layer, output = _cs_resolve_layer("master", "some/path.xlsx")
        assert layer == "master"
        assert output == "some/path.xlsx"

    def test_cs_resolve_layer_output_as_layer_project(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_layer

        layer, output = _cs_resolve_layer(None, "Project")
        assert layer == "project"
        assert output is None

    def test_cs_resolve_layer_output_as_layer_master(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_layer

        layer, output = _cs_resolve_layer(None, "MASTER")
        assert layer == "master"
        assert output is None

    def test_cs_resolve_layer_defaults_to_project(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_layer

        layer, output = _cs_resolve_layer(None, None)
        assert layer == "project"
        assert output is None

    def test_cs_resolve_layer_output_path_kept_when_not_layer_keyword(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_layer

        layer, output = _cs_resolve_layer(None, "/tmp/out.xlsx")
        assert layer == "project"
        assert output == "/tmp/out.xlsx"

    def test_cs_resolve_layer_invalid_raises(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_layer

        with pytest.raises(typer.Exit):
            _cs_resolve_layer("invalido", None)

    def test_cs_validate_layer_project_without_projeto_raises(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_b import _cs_validate_layer

        with pytest.raises(typer.Exit):
            _cs_validate_layer("project", None, False)

    def test_cs_validate_layer_master_without_confirm_raises(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_b import _cs_validate_layer

        with pytest.raises(typer.Exit):
            _cs_validate_layer("master", None, False)

    def test_cs_validate_layer_project_with_projeto_ok(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_validate_layer

        assert _cs_validate_layer("project", "proj1", False) is None

    def test_cs_validate_layer_master_with_confirm_ok(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_validate_layer

        assert _cs_validate_layer("master", None, True) is None

    def test_cs_resolve_path_explicit_output(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_path

        result = _cs_resolve_path("/tmp/custom.xlsx", "project", "price", "ctx1", None, "cat1", lambda: Path("/cfg"))
        assert result == Path("/tmp/custom.xlsx")

    def test_cs_resolve_path_project_layer(self, monkeypatch, tmp_path):
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)
        result = mod._cs_resolve_path(None, "project", "price", "ctx1", "proj1", "cat1", lambda: Path("/cfg"))
        assert result == tmp_path / "overrides" / "surveys" / "pesquisa_price_ctx1.xlsx"

    def test_cs_resolve_path_master_layer(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cs_resolve_path

        result = _cs_resolve_path(None, "master", "productivity", "ctx1", None, "cat1", lambda: Path("/cfg"))
        assert result == Path("/cfg") / "catalogos" / "cat1" / "surveys" / "pesquisa_productivity_ctx1.xlsx"

    def test_impl_catalog_search_prints_matches(self, monkeypatch, capsys):
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {
            "cpus": [
                {"codigo": "C001", "descricao": "Concreto usinado"},
                {"codigo": "C002", "descricao": "Aço CA-50"},
            ]
        }

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.presentation.mcp._context",
            mcp_context,
        )

        mod._impl_catalog_search(contexto_id="ctx1", query="concreto")
        captured = capsys.readouterr()
        assert "C001" in captured.out or "Concreto" in captured.out

    def test_impl_catalog_survey_export_success_project_layer(self, monkeypatch, tmp_path):
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        ctx.jurisdicao_id = "jur1"
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        mcp_context._config_root = lambda: tmp_path / "cfg"
        monkeypatch.setitem(__import__("sys").modules, "concilium.presentation.mcp._context", mcp_context)

        fake_store = MagicMock()
        fake_store.root = tmp_path / "proj"
        (tmp_path / "proj").mkdir()
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)

        exporter_instance = MagicMock()
        exporter_module = MagicMock()
        exporter_module.PriceSurveyExporter.return_value = exporter_instance
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.price_survey",
            exporter_module,
        )
        prod_module = MagicMock()
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.productivity_survey",
            prod_module,
        )

        mod._impl_catalog_survey(
            contexto_id="ctx1",
            jurisdicao_id=None,
            survey_type="price",
            output=None,
            target="project",
            projeto="proj1",
            confirm_master=False,
            actor="tester",
        )
        exporter_instance.export.assert_called_once()
        audit_file = fake_store.root / "audit_log.jsonl"
        assert audit_file.exists()

    def test_impl_catalog_survey_productivity_type_uses_productivity_exporter(self, monkeypatch, tmp_path):
        """survey_type != 'price' -> usa ProductivitySurveyExporter (linha 97)."""
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        ctx.jurisdicao_id = "jur1"
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        mcp_context._config_root = lambda: tmp_path / "cfg"
        monkeypatch.setitem(__import__("sys").modules, "concilium.presentation.mcp._context", mcp_context)

        fake_store = MagicMock()
        fake_store.root = tmp_path / "proj2"
        (tmp_path / "proj2").mkdir()
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)

        price_module = MagicMock()
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.price_survey",
            price_module,
        )
        prod_instance = MagicMock()
        prod_module = MagicMock()
        prod_module.ProductivitySurveyExporter.return_value = prod_instance
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.productivity_survey",
            prod_module,
        )

        mod._impl_catalog_survey(
            contexto_id="ctx1",
            jurisdicao_id=None,
            survey_type="productivity",
            output=None,
            target="project",
            projeto="proj2",
            confirm_master=False,
            actor="tester",
        )
        prod_instance.export.assert_called_once()
        price_module.PriceSurveyExporter.assert_not_called()

    def test_impl_catalog_survey_master_layer_skips_audit_log(self, monkeypatch, tmp_path):
        """layer='master' -> não grava audit_log.jsonl (cobre o ramo falso de 'if layer == project')."""
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        ctx.jurisdicao_id = "jur1"
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        mcp_context._config_root = lambda: tmp_path / "cfg"
        monkeypatch.setitem(__import__("sys").modules, "concilium.presentation.mcp._context", mcp_context)

        exporter_instance = MagicMock()
        exporter_module = MagicMock()
        exporter_module.PriceSurveyExporter.return_value = exporter_instance
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.price_survey",
            exporter_module,
        )
        prod_module = MagicMock()
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.productivity_survey",
            prod_module,
        )

        mod._impl_catalog_survey(
            contexto_id="ctx1",
            jurisdicao_id=None,
            survey_type="price",
            output=None,
            target="master",
            projeto=None,
            confirm_master=True,
            actor="tester",
        )
        exporter_instance.export.assert_called_once()
        assert not (tmp_path / "cfg").exists() or not list((tmp_path / "cfg").rglob("audit_log.jsonl"))

    def test_impl_catalog_survey_export_error_raises_exit(self, monkeypatch, tmp_path):
        import typer

        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        ctx.jurisdicao_id = "jur1"
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        mcp_context._config_root = lambda: tmp_path / "cfg"
        monkeypatch.setitem(__import__("sys").modules, "concilium.presentation.mcp._context", mcp_context)

        fake_store = MagicMock()
        fake_store.root = tmp_path / "proj"
        (tmp_path / "proj").mkdir()
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)

        exporter_module = MagicMock()
        exporter_module.PriceSurveyExporter.side_effect = RuntimeError("boom")
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.price_survey",
            exporter_module,
        )
        prod_module = MagicMock()
        monkeypatch.setitem(
            __import__("sys").modules,
            "concilium.infrastructure.exporters.productivity_survey",
            prod_module,
        )

        with pytest.raises(typer.Exit):
            mod._impl_catalog_survey(
                contexto_id="ctx1",
                jurisdicao_id=None,
                survey_type="price",
                output=None,
                target="project",
                projeto="proj1",
                confirm_master=False,
                actor="tester",
            )

    def test_impl_catalog_promote_without_force_raises(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_b import _impl_catalog_promote

        with pytest.raises(typer.Exit):
            _impl_catalog_promote(
                projeto="proj1",
                justificativa="motivo",
                contexto_id=None,
                actor="tester",
                force=False,
            )

    def test_impl_catalog_promote_delegates_to_gated_core_com_contexto_de_autor_e_role_admin(
        self, monkeypatch, tmp_path
    ):
        """ADR-150 D4: CLI não escreve mais direto — delega ao mesmo core gated do
        tool MCP promover_override_projeto, com role admin e o --actor informado."""
        from concilium.infrastructure.auth.permission_guard import _current_roles, get_current_user_id
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path / "PROJ-001"
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)

        captured: dict = {}

        def fake_core(projeto_id, contexto_id, justificativa):
            captured["projeto_id"] = projeto_id
            captured["contexto_id"] = contexto_id
            captured["justificativa"] = justificativa
            captured["actor"] = get_current_user_id()
            captured["roles"] = set(_current_roles.get())
            return {"status": "APROVADO", "deltas_aplicados": 2}

        monkeypatch.setattr(
            "concilium.presentation.mcp.tools._catalogo_tools_helpers_c._impl_promover_override_projeto",
            fake_core,
        )

        # Estado de auth ANTES da chamada — capturado em vez de assumido vazio,
        # já que outros testes da suíte completa podem deixar contextvars
        # setados sem resetar (isolamento é responsabilidade de cada teste,
        # não uma garantia do processo pytest).
        actor_antes = get_current_user_id()
        roles_antes = set(_current_roles.get())

        mod._impl_catalog_promote(
            projeto="proj1",
            justificativa="preço negociado",
            contexto_id="ctx-1",
            actor="bruno",
            force=True,
        )

        assert captured == {
            "projeto_id": "PROJ-001",
            "contexto_id": "ctx-1",
            "justificativa": "preço negociado",
            "actor": "bruno",
            "roles": {"admin"},
        }
        # Contexto de auth é restaurado ao estado anterior à chamada — não vaza
        # para o resto do processo CLI.
        assert get_current_user_id() == actor_antes
        assert set(_current_roles.get()) == roles_antes

    def test_impl_catalog_promote_erro_do_core_gated_levanta_exit(self, monkeypatch, tmp_path):
        """Gate (ownership/quatro-olhos) ou ausência de contexto retornam {"erro": ...} do
        core gated — CLI propaga como typer.Exit(1), sem tentar escrever nada."""
        import typer

        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path / "PROJ-001"
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)
        monkeypatch.setattr(
            "concilium.presentation.mcp.tools._catalogo_tools_helpers_c._impl_promover_override_projeto",
            lambda *a, **k: {"erro": "Ação restrita ao dono do projeto ou a um admin."},
        )

        with pytest.raises(typer.Exit):
            mod._impl_catalog_promote(
                projeto="proj1",
                justificativa="motivo",
                contexto_id="ctx-1",
                actor="tester",
                force=True,
            )
