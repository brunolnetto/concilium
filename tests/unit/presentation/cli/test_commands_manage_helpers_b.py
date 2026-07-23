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

    def test_cp_validate_override_missing_insumo_raises(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_b import _cp_validate_override

        with pytest.raises(typer.Exit):
            _cp_validate_override({}, "ins1")

    def test_cp_validate_override_not_dict_raises(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_b import _cp_validate_override

        with pytest.raises(typer.Exit):
            _cp_validate_override({"ins1": "not-a-dict"}, "ins1")

    def test_cp_validate_override_missing_preco_raises(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_b import _cp_validate_override

        with pytest.raises(typer.Exit):
            _cp_validate_override({"ins1": {}}, "ins1")

    def test_cp_validate_override_success_preco_calibrado(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cp_validate_override

        override_item, novo_preco = _cp_validate_override({"ins1": {"preco_calibrado": 10.5}}, "ins1")
        assert override_item == {"preco_calibrado": 10.5}
        assert novo_preco == 10.5

    def test_cp_validate_override_success_preco_unitario_fallback(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cp_validate_override

        _, novo_preco = _cp_validate_override({"ins1": {"preco_unitario": 5.0}}, "ins1")
        assert novo_preco == 5.0

    def test_cp_update_price_history_new_open_entry_diff_price(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cp_update_price_history

        historico = [{"preco_unitario": 3.0, "data_fim_vigencia": None}]
        store = MagicMock()
        store.meta = {"id": "proj1"}
        _cp_update_price_history(historico, 4.0, "2024-01-01", store, "justif")
        assert historico[0]["data_fim_vigencia"] == "2024-01-01"
        assert historico[-1]["preco_unitario"] == 4.0
        assert historico[-1]["data_fim_vigencia"] is None

    def test_cp_update_price_history_same_price_no_new_entry(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cp_update_price_history

        historico = [{"preco_unitario": 4.0, "data_fim_vigencia": None}]
        store = MagicMock()
        store.meta = {"id": "proj1"}
        _cp_update_price_history(historico, 4.0, "2024-01-01", store, "justif")
        assert len(historico) == 1
        assert historico[0]["data_fim_vigencia"] is None

    def test_cp_update_price_history_empty_history(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cp_update_price_history

        historico: list = []
        store = MagicMock()
        store.meta = {}
        store.root = Path("/tmp/proj_xyz")
        _cp_update_price_history(historico, 4.0, "2024-01-01", store, "justif")
        assert len(historico) == 1
        assert historico[0]["projeto_origem"] == "proj_xyz"

    def test_cp_update_price_history_skips_non_dict_entries(self):
        from concilium.presentation.cli._commands_manage_helpers_b import _cp_update_price_history

        historico = ["not-a-dict", {"preco_unitario": 1.0, "data_fim_vigencia": None}]
        store = MagicMock()
        store.meta = {"id": "proj1"}
        _cp_update_price_history(historico, 2.0, "2024-01-01", store, "justif")
        assert historico[1]["data_fim_vigencia"] == "2024-01-01"

    def test_cp_update_price_history_skips_already_closed_entries(self):
        """Cobre o ramo em que o registro mais recente (reversed) já está fechado
        (data_fim_vigencia != None), forçando a busca a continuar para entradas
        anteriores, e o loop forward que só fecha entradas ainda abertas."""
        from concilium.presentation.cli._commands_manage_helpers_b import _cp_update_price_history

        historico = [
            {"preco_unitario": 1.0, "data_fim_vigencia": None},
            {"preco_unitario": 2.0, "data_fim_vigencia": "2023-01-01"},
        ]
        store = MagicMock()
        store.meta = {"id": "proj1"}
        _cp_update_price_history(historico, 5.0, "2024-01-01", store, "justif")

        # Entrada já fechada permanece intocada.
        assert historico[1]["data_fim_vigencia"] == "2023-01-01"
        # Entrada aberta encontrada via reversed() é fechada.
        assert historico[0]["data_fim_vigencia"] == "2024-01-01"
        # Nova entrada aberta com o novo preço é adicionada ao final.
        assert historico[-1]["preco_unitario"] == 5.0
        assert historico[-1]["data_fim_vigencia"] is None

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
                insumo_id="ins1",
                justificativa="motivo",
                contexto_id=None,
                data_vigencia=None,
                actor="tester",
                force=False,
            )

    def test_impl_catalog_promote_invalid_data_vigencia_raises(self, monkeypatch, tmp_path):
        import typer

        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path
        fake_store.meta = {"contexto_id": "ctx1"}
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)
        monkeypatch.setattr(
            mod,
            "_load_json",
            lambda path, default: {"ins1": {"preco_calibrado": 10.0}} if "override" in str(path) else default,
        )

        with pytest.raises(typer.Exit):
            mod._impl_catalog_promote(
                projeto="proj1",
                insumo_id="ins1",
                justificativa="motivo",
                contexto_id=None,
                data_vigencia="not-a-date",
                actor="tester",
                force=True,
            )

    def test_impl_catalog_promote_missing_contexto_raises(self, monkeypatch, tmp_path):
        import typer

        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path
        fake_store.meta = {}
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)
        monkeypatch.setattr(
            mod,
            "_load_json",
            lambda path, default: {"ins1": {"preco_calibrado": 10.0}} if "override" in str(path) else default,
        )

        with pytest.raises(typer.Exit):
            mod._impl_catalog_promote(
                projeto="proj1",
                insumo_id="ins1",
                justificativa="motivo",
                contexto_id=None,
                data_vigencia=None,
                actor="tester",
                force=True,
            )

    def test_impl_catalog_promote_governance_error_raises(self, monkeypatch, tmp_path):
        import typer

        from concilium.application.orchestrators.catalog_governance import CatalogGovernanceError
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path
        fake_store.meta = {"contexto_id": "ctx1"}
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)
        monkeypatch.setattr(
            mod,
            "_load_json",
            lambda path, default: {"ins1": {"preco_calibrado": 10.0}} if "override" in str(path) else default,
        )

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        rt.load_contexto.return_value = ctx

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        mcp_context._config_root = lambda: tmp_path / "cfg"
        monkeypatch.setitem(__import__("sys").modules, "concilium.presentation.mcp._context", mcp_context)

        gov_module = __import__(
            "concilium.application.orchestrators.catalog_governance", fromlist=["validate_and_resolve_insumo_file"]
        )
        monkeypatch.setattr(
            gov_module,
            "validate_and_resolve_insumo_file",
            MagicMock(side_effect=CatalogGovernanceError("bloqueado")),
        )

        with pytest.raises(typer.Exit):
            mod._impl_catalog_promote(
                projeto="proj1",
                insumo_id="ins1",
                justificativa="motivo",
                contexto_id=None,
                data_vigencia=None,
                actor="tester",
                force=True,
            )

    def test_impl_catalog_promote_success_full_flow(self, monkeypatch, tmp_path):
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path
        fake_store.meta = {"contexto_id": "ctx1", "id": "proj1"}
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)

        written = {}

        def fake_load_json(path, default):
            if "override" in str(path):
                return {"ins1": {"preco_calibrado": 10.0}}
            return written.get(str(path), dict(default))

        def fake_write_json(path, data):
            written[str(path)] = data

        monkeypatch.setattr(mod, "_load_json", fake_load_json)
        monkeypatch.setattr(mod, "_write_json", fake_write_json)
        monkeypatch.setattr(mod, "_append_jsonl", MagicMock())

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        rt.load_contexto.return_value = ctx

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        mcp_context._config_root = lambda: tmp_path / "cfg"
        monkeypatch.setitem(__import__("sys").modules, "concilium.presentation.mcp._context", mcp_context)

        gov_module = __import__(
            "concilium.application.orchestrators.catalog_governance", fromlist=["validate_and_resolve_insumo_file"]
        )
        monkeypatch.setattr(
            gov_module,
            "validate_and_resolve_insumo_file",
            MagicMock(return_value=tmp_path / "insumo.json"),
        )

        mod._impl_catalog_promote(
            projeto="proj1",
            insumo_id="ins1",
            justificativa="motivo",
            contexto_id=None,
            data_vigencia="2024-05-01",
            actor="tester",
            force=True,
        )

        saved = written[str(tmp_path / "insumo.json")]
        assert saved["preco_unitario"] == 10.0
        assert len(saved["historico_precos"]) == 1

    def test_impl_catalog_promote_resets_non_list_historico(self, monkeypatch, tmp_path):
        """insumo_master with a corrupt (non-list) historico_precos should be reset to []."""
        from concilium.presentation.cli import _commands_manage_helpers_b as mod

        fake_store = MagicMock()
        fake_store.root = tmp_path
        fake_store.meta = {"contexto_id": "ctx1", "id": "proj1"}
        monkeypatch.setattr(mod, "resolve_project", lambda p: fake_store)

        written = {}

        def fake_load_json(path, default):
            if "override" in str(path):
                return {"ins1": {"preco_calibrado": 10.0}}
            if str(path) == str(tmp_path / "insumo.json"):
                return {"historico_precos": "corrupted-not-a-list"}
            return dict(default)

        def fake_write_json(path, data):
            written[str(path)] = data

        monkeypatch.setattr(mod, "_load_json", fake_load_json)
        monkeypatch.setattr(mod, "_write_json", fake_write_json)
        monkeypatch.setattr(mod, "_append_jsonl", MagicMock())

        rt = MagicMock()
        ctx = MagicMock()
        ctx.catalogo_id = "cat1"
        rt.load_contexto.return_value = ctx

        mcp_context = MagicMock()
        mcp_context._runtime = lambda: rt
        mcp_context._config_root = lambda: tmp_path / "cfg"
        monkeypatch.setitem(__import__("sys").modules, "concilium.presentation.mcp._context", mcp_context)

        gov_module = __import__(
            "concilium.application.orchestrators.catalog_governance", fromlist=["validate_and_resolve_insumo_file"]
        )
        monkeypatch.setattr(
            gov_module,
            "validate_and_resolve_insumo_file",
            MagicMock(return_value=tmp_path / "insumo.json"),
        )

        mod._impl_catalog_promote(
            projeto="proj1",
            insumo_id="ins1",
            justificativa="motivo",
            contexto_id=None,
            data_vigencia=None,
            actor="tester",
            force=True,
        )

        saved = written[str(tmp_path / "insumo.json")]
        assert isinstance(saved["historico_precos"], list)
        assert len(saved["historico_precos"]) == 1



