"""Coverage tests for commands_manage.py CLI entrypoints.

Targets:
  - commands_manage.py — catalog_list, catalog_browse, catalog_quality,
    catalog_simulate, catalog_export, catalog_survey, catalog_promote,
    catalog_search, catalog_validate_schema, catalog_cure_schema,
    catalog_tendencia, catalog_audit_reasonability, catalog_merge_rfi,
    catalog_cure_plausibility, structure_list, plan_init
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from concilium.presentation.cli.commands_manage import app_catalog, app_structure

runner = CliRunner()


# ─── helpers ────────────────────────────────────────────────────────────────


def _make_fake_runtime(tmp_path: Path, cat_name: str = "testcat") -> SimpleNamespace:
    """Return a fake Runtime-like object backed by tmp_path."""
    cat_dir = tmp_path / "catalogos" / cat_name
    cat_dir.mkdir(parents=True, exist_ok=True)

    catalogo = {
        "cpus": [
            {"codigo": "CPU-A", "descricao": "CPU Alpha", "unidade": "m3", "categoria": "TERRA"},
            {"codigo": "CPU-B", "descricao": "CPU Beta", "unidade": "m", "categoria": "ASFALTO"},
        ],
        "producoes": [{"id": "PROD-1"}],
        "insumos": [
            {
                "codigo": "INS-01",
                "tipo": "MATERIAL",
                "descricao": "Insumo Um",
                "unidade": "kg",
                "preco_unitario": 10.0,
            }
        ],
    }

    ctx = SimpleNamespace(catalogo_id=cat_name)

    rt = SimpleNamespace(
        config_root=tmp_path,
        load_catalogo=lambda name: catalogo,
        load_contexto=lambda ctx_id: ctx,
    )
    return rt


# ═══════════════════════════════════════════════════════════════════════════════
# catalog list
# ═══════════════════════════════════════════════════════════════════════════════


_RUNTIME_PATCH = "concilium.presentation.mcp._context._runtime"


class TestCatalogList:
    def test_list_shows_existing_catalog(self, tmp_path):
        rt = _make_fake_runtime(tmp_path)
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["list"])
        assert result.exit_code == 0
        assert "testcat" in result.output

    def test_list_no_catalogs_warns(self, tmp_path):
        # catalogos dir exists but is empty
        (tmp_path / "catalogos").mkdir(parents=True)
        rt = SimpleNamespace(
            config_root=tmp_path,
            load_catalogo=lambda n: {},
            load_contexto=lambda c: SimpleNamespace(catalogo_id=""),
        )
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["list"])
        assert result.exit_code == 0
        assert "Nenhum" in result.output

    def test_list_load_catalogo_exception_shows_question_marks(self, tmp_path):
        cat_dir = tmp_path / "catalogos" / "brokencat"
        cat_dir.mkdir(parents=True)
        rt = SimpleNamespace(
            config_root=tmp_path,
            load_catalogo=MagicMock(side_effect=Exception("broken")),
            load_contexto=lambda c: SimpleNamespace(catalogo_id="brokencat"),
        )
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["list"])
        assert result.exit_code == 0
        assert "?" in result.output


# ═══════════════════════════════════════════════════════════════════════════════
# catalog browse
# ═══════════════════════════════════════════════════════════════════════════════


class TestCatalogBrowse:
    def test_browse_cpu_default_page(self, tmp_path):
        rt = _make_fake_runtime(tmp_path)
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["browse", "--contexto", "ctx1"])
        assert result.exit_code == 0
        assert "CPU-A" in result.output or "CPU-B" in result.output

    def test_browse_cpu_with_categoria_filter(self, tmp_path):
        rt = _make_fake_runtime(tmp_path)
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(
                app_catalog, ["browse", "--contexto", "ctx1", "--tipo", "cpu", "--categoria", "TERRA"]
            )
        assert result.exit_code == 0
        # Only CPU-A has TERRA category
        assert "CPU-A" in result.output

    def test_browse_insumo_tipo(self, tmp_path):
        rt = _make_fake_runtime(tmp_path)
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["browse", "--contexto", "ctx1", "--tipo", "insumo"])
        assert result.exit_code == 0
        assert "INS-01" in result.output

    def test_browse_unknown_tipo_exits_1(self, tmp_path):
        rt = _make_fake_runtime(tmp_path)
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["browse", "--contexto", "ctx1", "--tipo", "producao"])
        assert result.exit_code == 1

    def test_browse_pagination_second_page(self, tmp_path):
        """Build 30 CPUs to force two pages; page 2 should show the last items."""
        cat_dir = tmp_path / "catalogos" / "testcat"
        cat_dir.mkdir(parents=True)
        cpus = [
            {"codigo": f"CPU-{i:03d}", "descricao": f"Desc {i}", "unidade": "m", "categoria": "X"} for i in range(30)
        ]
        catalogo = {"cpus": cpus, "producoes": [], "insumos": []}
        ctx = SimpleNamespace(catalogo_id="testcat")
        rt = SimpleNamespace(
            config_root=tmp_path,
            load_catalogo=lambda n: catalogo,
            load_contexto=lambda c: ctx,
        )
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["browse", "--contexto", "ctx1", "--tipo", "cpu", "--pagina", "2"])
        assert result.exit_code == 0
        # Page 2/2 — CPU-025 through CPU-029 should appear
        assert "CPU-025" in result.output

    def test_browse_page_clamped_to_last(self, tmp_path):
        """Requesting page 999 should be clamped to the last page."""
        rt = _make_fake_runtime(tmp_path)
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["browse", "--contexto", "ctx1", "--tipo", "cpu", "--pagina", "999"])
        assert result.exit_code == 0

    def test_browse_empty_insumos(self, tmp_path):
        """Browse insumo with empty list should still show a valid table."""
        cat_dir = tmp_path / "catalogos" / "testcat"
        cat_dir.mkdir(parents=True)
        catalogo = {"cpus": [], "producoes": [], "insumos": []}
        ctx = SimpleNamespace(catalogo_id="testcat")
        rt = SimpleNamespace(
            config_root=tmp_path,
            load_catalogo=lambda n: catalogo,
            load_contexto=lambda c: ctx,
        )
        with patch(_RUNTIME_PATCH, return_value=rt):
            result = runner.invoke(app_catalog, ["browse", "--contexto", "ctx1", "--tipo", "insumo"])
        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Delegating catalog commands — patch _impl_* at their import site
# ═══════════════════════════════════════════════════════════════════════════════

_PATCH_BASE = "concilium.presentation.cli.commands_manage"


class TestCatalogQuality:
    def test_delegates_to_impl(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_quality") as mock_impl:
            result = runner.invoke(app_catalog, ["quality", "--contexto", "ctx1"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1")


class TestCatalogSimulate:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_simulate") as mock_impl:
            result = runner.invoke(app_catalog, ["simulate", "CPU-TERR-01"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("CPU-TERR-01", "mendeslobo", 30, "6x1", 8.0)

    def test_custom_options_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_simulate") as mock_impl:
            result = runner.invoke(
                app_catalog,
                [
                    "simulate",
                    "CPU-TERR-01",
                    "--contexto",
                    "ctx2",
                    "--dias",
                    "15",
                    "--regime",
                    "5x2",
                    "--horas-dia",
                    "10.0",
                ],
            )
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("CPU-TERR-01", "ctx2", 15, "5x2", 10.0)


class TestCatalogExport:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_export") as mock_impl:
            result = runner.invoke(app_catalog, ["export"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("mendeslobo", None)

    def test_with_output_option(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_export") as mock_impl:
            result = runner.invoke(app_catalog, ["export", "--contexto", "mycat", "--output", "/tmp/out.xlsx"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("mycat", "/tmp/out.xlsx")


class TestCatalogSurvey:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_survey") as mock_impl:
            result = runner.invoke(app_catalog, ["survey"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("mendeslobo", None, "price", None, None, None, False, "cli")

    def test_all_options_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_survey") as mock_impl:
            result = runner.invoke(
                app_catalog,
                [
                    "survey",
                    "--contexto",
                    "ctx1",
                    "--jurisdicao",
                    "BR-CE",
                    "--type",
                    "productivity",
                    "--output",
                    "out.xlsx",
                    "--target",
                    "master",
                    "--project",
                    "proj1",
                    "--confirm-master",
                    "--actor",
                    "bot",
                ],
            )
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", "BR-CE", "productivity", "out.xlsx", "master", "proj1", True, "bot")


class TestCatalogPromote:
    def test_required_args_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_promote") as mock_impl:
            result = runner.invoke(
                app_catalog,
                [
                    "promote",
                    "--project",
                    "myprojeto",
                    "--insumo",
                    "INS-01",
                    "--justificativa",
                    "atualização de mercado",
                ],
            )
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("myprojeto", "INS-01", "atualização de mercado", None, None, "cli", False)

    def test_optional_args_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_promote") as mock_impl:
            result = runner.invoke(
                app_catalog,
                [
                    "promote",
                    "--project",
                    "proj",
                    "--insumo",
                    "INS-02",
                    "--justificativa",
                    "ok",
                    "--contexto",
                    "ctx1",
                    "--data-vigencia",
                    "2026-01-01",
                    "--actor",
                    "user",
                    "--force",
                ],
            )
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("proj", "INS-02", "ok", "ctx1", "2026-01-01", "user", True)


class TestCatalogSearch:
    def test_delegates_with_args(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_search") as mock_impl:
            result = runner.invoke(app_catalog, ["search", "--contexto", "ctx1", "escavadeira"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", "escavadeira")


class TestCatalogValidateSchema:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_validate_schema") as mock_impl:
            result = runner.invoke(app_catalog, ["validate", "--contexto", "ctx1"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", False)

    def test_strict_flag_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_validate_schema") as mock_impl:
            result = runner.invoke(app_catalog, ["validate", "--contexto", "ctx1", "--strict"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", True)


class TestCatalogCureSchema:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_cure_schema") as mock_impl:
            result = runner.invoke(app_catalog, ["cure", "--contexto", "ctx1"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", True)

    def test_dry_run_flag(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_cure_schema") as mock_impl:
            result = runner.invoke(app_catalog, ["cure", "--contexto", "ctx1", "--dry-run"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", False)


class TestCatalogTendencia:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_tendencia") as mock_impl:
            result = runner.invoke(app_catalog, ["tendencia", "--contexto", "ctx1"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", None, "")

    def test_all_options_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_tendencia") as mock_impl:
            result = runner.invoke(
                app_catalog,
                [
                    "tendencia",
                    "--contexto",
                    "ctx1",
                    "--jurisdicao",
                    "BR-SP",
                    "--output",
                    "/tmp/trend.json",
                ],
            )
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("ctx1", "BR-SP", "/tmp/trend.json")


class TestCatalogAuditReasonability:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_audit_reasonability") as mock_impl:
            result = runner.invoke(app_catalog, ["audit-reasonability"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("mendeslobo", "", 20)

    def test_all_options_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_catalog_audit_reasonability") as mock_impl:
            result = runner.invoke(
                app_catalog,
                [
                    "audit-reasonability",
                    "--contexto",
                    "myctx",
                    "--output",
                    "/tmp/audit.json",
                    "--max-findings",
                    "50",
                ],
            )
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("myctx", "/tmp/audit.json", 50)


# ═══════════════════════════════════════════════════════════════════════════════
# catalog_merge_rfi and catalog_cure_plausibility — bare functions (no decorator)
# ═══════════════════════════════════════════════════════════════════════════════


class TestCatalogMergeRfi:
    """catalog_merge_rfi is not registered with a @app_catalog.command decorator.
    Calling it with explicit values bypasses Typer option processing."""

    def test_delegates_with_explicit_defaults(self):
        from concilium.presentation.cli.commands_manage import catalog_merge_rfi

        with patch(f"{_PATCH_BASE}._impl_catalog_merge_rfi") as mock_impl:
            catalog_merge_rfi("ctx1", False, False, None)
        mock_impl.assert_called_once_with("ctx1", False, False, None)

    def test_delegates_with_apply_and_verify(self):
        from concilium.presentation.cli.commands_manage import catalog_merge_rfi

        with patch(f"{_PATCH_BASE}._impl_catalog_merge_rfi") as mock_impl:
            catalog_merge_rfi("ctx2", True, True, "/tmp/r.json")
        mock_impl.assert_called_once_with("ctx2", True, True, "/tmp/r.json")


class TestCatalogCurePlausibility:
    """catalog_cure_plausibility is likewise not decorated — call with explicit values."""

    def test_delegates_dry_run(self):
        from concilium.presentation.cli.commands_manage import catalog_cure_plausibility

        with patch(f"{_PATCH_BASE}._impl_catalog_cure_plausibility") as mock_impl:
            catalog_cure_plausibility("ctx1", False)
        mock_impl.assert_called_once_with("ctx1", False)

    def test_delegates_with_apply(self):
        from concilium.presentation.cli.commands_manage import catalog_cure_plausibility

        with patch(f"{_PATCH_BASE}._impl_catalog_cure_plausibility") as mock_impl:
            catalog_cure_plausibility("ctx1", True)
        mock_impl.assert_called_once_with("ctx1", True)


# ═══════════════════════════════════════════════════════════════════════════════
# structure sub-app
# ═══════════════════════════════════════════════════════════════════════════════


class TestStructureList:
    def test_delegates_to_impl(self):
        with patch(f"{_PATCH_BASE}._impl_structure_list") as mock_impl:
            result = runner.invoke(app_structure, ["list", "meu-projeto"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("meu-projeto")


class TestPlanInit:
    def test_defaults_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_plan_init") as mock_impl:
            result = runner.invoke(app_structure, ["plan-init", "meu-projeto"])
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("meu-projeto", "Plano Principal", "default")

    def test_all_options_forwarded(self):
        with patch(f"{_PATCH_BASE}._impl_plan_init") as mock_impl:
            result = runner.invoke(
                app_structure,
                [
                    "plan-init",
                    "meu-projeto",
                    "--nome",
                    "Plano A",
                    "--escopo",
                    "escopo-01",
                ],
            )
        assert result.exit_code == 0
        mock_impl.assert_called_once_with("meu-projeto", "Plano A", "escopo-01")
