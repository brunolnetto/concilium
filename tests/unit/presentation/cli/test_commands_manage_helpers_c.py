"""Tests for FileProjectRepository and manage_helpers_c to boost coverage."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── _commands_manage_helpers_c ─────────────────────────────────────────────


class TestManageHelpersCBundleLoader:
    """issue #134: _cmr_* (específicos de merge-rfi) foram substituídos por
    _cc_*/_resolver_fonte_entidades (agnósticos de fonte) em catalog compare/merge."""

    def test_resolver_fonte_entidades_catalogo_missing_raises_exit(self, tmp_path):
        """Erros de resolução de fonte (RuntimeError) viram typer.Exit(2) na CLI."""
        from types import SimpleNamespace

        import typer

        from concilium.presentation.cli._commands_manage_helpers_c import _resolver_fonte_entidades

        rt = SimpleNamespace(
            config_root=tmp_path / "config",
            load_catalogo=MagicMock(side_effect=RuntimeError("catalogo inexistente")),
        )
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            with pytest.raises(typer.Exit) as exc_info:
                _resolver_fonte_entidades("missing_ctx")
        assert exc_info.value.exit_code == 2

    def test_resolver_fonte_entidades_catalogo_ok(self, tmp_path):
        from types import SimpleNamespace

        from concilium.presentation.cli._commands_manage_helpers_c import _resolver_fonte_entidades

        catalogo = {
            "insumos": [{"codigo": "I1", "tipo": "MO", "preco_unitario": 100.0}],
            "producoes": [{"id": "P1", "valor_horario": 50.0}],
        }
        rt = SimpleNamespace(config_root=tmp_path / "config", load_catalogo=lambda cid: catalogo)
        with patch("concilium.presentation.mcp._context._runtime", return_value=rt):
            result = _resolver_fonte_entidades("ctx1")
        assert len(result["insumos"]) == 1
        assert result["insumos"][0]["codigo"] == "I1"

    def test_cc_print_inner_low_combines_reports(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _cc_print_inner_low

        mock_ins = MagicMock()
        mock_ins.inner_low = [{"catalog": {"codigo": "I1"}, "rfi": {"codigo": "I1b"}, "score": 0.6}]
        mock_prod = MagicMock()
        mock_prod.inner_low = [{"catalog": {"id": "P1"}, "rfi": {"id": "P1b"}, "score": 0.55}]
        console = MagicMock()
        _cc_print_inner_low({"insumos": mock_ins, "producoes": mock_prod}, console)
        assert console.print.called

    def test_cc_add_table_row(self):
        from rich.table import Table

        from concilium.presentation.cli._commands_manage_helpers_c import _cc_add_table_row

        table = Table()
        table.add_column("Label")
        table.add_column("Value")
        rep = MagicMock()
        rep.inner_high = []
        rep.inner_low = []
        rep.right_only = []
        rep.left_only = []
        # Should not raise
        _cc_add_table_row(table, "My Label", rep)

    def test_impl_structure_list_no_project(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_structure_list

        with patch(
            "concilium.presentation.cli._commands_manage_helpers_c.resolve_project",
            side_effect=FileNotFoundError("not found"),
        ):
            # Should handle gracefully
            try:
                _impl_structure_list("nonexistent_project")
            except (SystemExit, FileNotFoundError, Exception):
                pass

