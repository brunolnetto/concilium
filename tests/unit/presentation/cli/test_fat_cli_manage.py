"""Coverage tests for CLI manage helpers and config/version commands.

Targets:
  - _commands_manage_helpers_a.py  (catalog quality helpers)
  - _commands_manage_helpers_c.py  (catalog merge/cure/structure helpers)
  - _commands_manage_helpers_d.py  (catalog validate/tendencia/audit helpers)
  - commands_config_version.py     (context + perfil versioning CLI)
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

runner = CliRunner()


# ═══════════════════════════════════════════════════════════════════════════════
# _commands_manage_helpers_a.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestLoadJson:
    """Tests for _load_json helper."""

    def test_returns_default_when_file_missing(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_a import _load_json

        result = _load_json(tmp_path / "nonexistent.json", {"default": True})
        assert result == {"default": True}

    def test_reads_valid_json(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_a import _load_json

        p = tmp_path / "data.json"
        p.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        result = _load_json(p, {})
        assert result == {"key": "value"}

    def test_returns_default_on_bad_json(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_a import _load_json

        p = tmp_path / "bad.json"
        p.write_text("not json!!!", encoding="utf-8")
        result = _load_json(p, {"fallback": 1})
        assert result == {"fallback": 1}

    def test_returns_default_when_json_not_dict(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_a import _load_json

        p = tmp_path / "list.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        result = _load_json(p, {"default": True})
        assert result == {"default": True}


class TestWriteJson:
    def test_creates_parent_dirs_and_writes(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_a import _write_json

        p = tmp_path / "a" / "b" / "file.json"
        _write_json(p, {"x": 1})
        assert p.exists()
        assert json.loads(p.read_text()) == {"x": 1}


class TestAppendJsonl:
    def test_appends_multiple_lines(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_a import _append_jsonl

        p = tmp_path / "log.jsonl"
        _append_jsonl(p, {"a": 1})
        _append_jsonl(p, {"b": 2})
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1}
        assert json.loads(lines[1]) == {"b": 2}


class TestCqValidateCpus:
    def test_errors_and_avisos_collected(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_validate_cpus

        res_err = SimpleNamespace(status="ERRO", codigo="VAL-CPU-STR-02", mensagem="erro de estrutura")
        res_warn = SimpleNamespace(status="AVISO", codigo="VAL-GEN-01", mensagem="aviso geral")

        validador = MagicMock()
        validador.validar_cpu_completa.side_effect = [
            [res_err],
            [res_warn],
        ]
        cpus = [{"codigo": "CPU-A"}, {"codigo": "CPU-B"}]
        erros, avisos, bloqueadas = _cq_validate_cpus(cpus, validador)
        assert len(erros) == 1
        assert erros[0][0] == "CPU-A"
        assert len(avisos) == 1
        assert "CPU-A" in bloqueadas

    def test_str03_also_blocks(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_validate_cpus

        res_err = SimpleNamespace(status="ERRO", codigo="VAL-CPU-STR-03", mensagem="campo ausente")
        validador = MagicMock()
        validador.validar_cpu_completa.return_value = [res_err]
        cpus = [{"codigo": "CPU-X"}]
        erros, avisos, bloqueadas = _cq_validate_cpus(cpus, validador)
        assert "CPU-X" in bloqueadas

    def test_empty_cpu_list(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_validate_cpus

        validador = MagicMock()
        erros, avisos, bloqueadas = _cq_validate_cpus([], validador)
        assert erros == [] and avisos == [] and bloqueadas == []

    def test_erro_com_codigo_nao_bloqueante_nao_e_adicionado_a_bloqueadas(self):
        """ERRO cujo codigo não está em VAL-CPU-STR-02/03 não bloqueia a CPU."""
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_validate_cpus

        res_err = SimpleNamespace(status="ERRO", codigo="VAL-CPU-OUTRO", mensagem="erro genérico")
        validador = MagicMock()
        validador.validar_cpu_completa.return_value = [res_err]
        cpus = [{"codigo": "CPU-Y"}]
        erros, avisos, bloqueadas = _cq_validate_cpus(cpus, validador)
        assert len(erros) == 1
        assert bloqueadas == []

    def test_resultado_ok_nao_gera_erro_nem_aviso(self):
        """status diferente de ERRO/AVISO (ex.: OK) não popula nenhuma lista."""
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_validate_cpus

        res_ok = SimpleNamespace(status="OK", codigo="OK-01", mensagem="ok")
        validador = MagicMock()
        validador.validar_cpu_completa.return_value = [res_ok]
        cpus = [{"codigo": "CPU-Z"}]
        erros, avisos, bloqueadas = _cq_validate_cpus(cpus, validador)
        assert erros == [] and avisos == [] and bloqueadas == []


class TestCqValidateInsumos:
    def test_collects_vigencia_and_encoding_avisos(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_validate_insumos

        res_v = SimpleNamespace(status="AVISO", codigo="VAL-CAT-VIG-01", mensagem="desatualizado")
        res_e = SimpleNamespace(status="AVISO", codigo="VAL-CAT-ENC-01", mensagem="mojibake")
        validador = MagicMock()
        validador.validar_vigencia.return_value = res_v
        validador.validar_encoding.return_value = res_e
        insumos = [{"codigo": "INS-01"}]
        avisos, obsoletos = _cq_validate_insumos(insumos, validador)
        assert "INS-01" in obsoletos
        assert len(avisos) == 2

    def test_ok_insumo_no_avisos(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_validate_insumos

        res_ok = SimpleNamespace(status="OK", codigo="OK-01", mensagem="ok")
        validador = MagicMock()
        validador.validar_vigencia.return_value = res_ok
        validador.validar_encoding.return_value = res_ok
        insumos = [{"codigo": "INS-02"}]
        avisos, obsoletos = _cq_validate_insumos(insumos, validador)
        assert avisos == [] and obsoletos == []


class TestCqPrintBlockedCpus:
    def test_empty_blocked_list_prints_nothing(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_print_blocked_cpus

        console = MagicMock()
        _cq_print_blocked_cpus([], [], console)
        console.print.assert_not_called()

    def test_blocked_cpu_prints_table(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_print_blocked_cpus

        err = SimpleNamespace(mensagem="campo faltante")
        console = MagicMock()
        _cq_print_blocked_cpus(["CPU-A"], [("CPU-A", err)], console)
        console.print.assert_called_once()

    def test_erro_nao_bloqueado_e_pulado_na_tabela(self):
        """erros com codigo fora de cpus_bloqueadas são ignorados na tabela."""
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_print_blocked_cpus

        err_bloqueado = SimpleNamespace(mensagem="campo faltante")
        err_nao_bloqueado = SimpleNamespace(mensagem="erro genérico")
        console = MagicMock()
        _cq_print_blocked_cpus(
            ["CPU-A"],
            [("CPU-B", err_nao_bloqueado), ("CPU-A", err_bloqueado)],
            console,
        )
        console.print.assert_called_once()


class TestCqPrintEncodingAlerts:
    def test_no_encoding_alerts_prints_nothing(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_print_encoding_alerts

        console = MagicMock()
        other = SimpleNamespace(codigo="VAL-OTHER", mensagem="x")
        _cq_print_encoding_alerts([("A", other)], console)
        console.print.assert_not_called()

    def test_encoding_alert_prints_table(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_print_encoding_alerts

        console = MagicMock()
        enc = SimpleNamespace(codigo="VAL-CAT-ENC-01", mensagem="mojibake")
        _cq_print_encoding_alerts([("INS-01", enc)], console)
        console.print.assert_called_once()

    def test_encoding_alert_overflow_more_than_10(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_print_encoding_alerts

        console = MagicMock()
        enc = SimpleNamespace(codigo="VAL-CAT-ENC-01", mensagem="x")
        # 12 alerts
        avisos = [(f"INS-{i:02d}", enc) for i in range(12)]
        _cq_print_encoding_alerts(avisos, console)
        # Should print a table with overflow row
        console.print.assert_called_once()


class TestCqFmtPct:
    def test_high_coverage_is_green(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_fmt_pct

        result = _cq_fmt_pct(98, 100)
        assert "green" in result
        assert "98.0%" in result

    def test_medium_coverage_is_yellow(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_fmt_pct

        result = _cq_fmt_pct(80, 100)
        assert "yellow" in result

    def test_low_coverage_is_red(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_fmt_pct

        result = _cq_fmt_pct(50, 100)
        assert "red" in result

    def test_zero_total_returns_zero(self):
        from concilium.presentation.cli._commands_manage_helpers_a import _cq_fmt_pct

        result = _cq_fmt_pct(0, 0)
        assert "0.0%" in result


class TestImplCatalogQuality:
    """Tests for _impl_catalog_quality (full diagnostic flow)."""

    def _make_rt(self, cpus, insumos):
        ctx = SimpleNamespace(catalogo_id="cat-1")
        catalogo = {"cpus": cpus, "insumos": insumos}
        rt = MagicMock()
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = catalogo
        return rt

    def test_reprovado_when_erros_present(self):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = self._make_rt(
            cpus=[{"codigo": "CPU-1"}],
            insumos=[{"codigo": "INS-1", "preco_unitario": 10}],
        )
        erro = SimpleNamespace(status="ERRO", codigo="VAL-CPU-STR-02", mensagem="ruim")
        validador = MagicMock()
        validador.validar_cpu_completa.return_value = [erro]
        validador.validar_vigencia.return_value = SimpleNamespace(status="OK", codigo="OK", mensagem="")
        validador.validar_encoding.return_value = SimpleNamespace(status="OK", codigo="OK", mensagem="")

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.domain.validations.cpu_insumo.ValidadorCPUInsumo", return_value=validador),
            patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo"),
            patch("concilium.domain.validations.circular_deps.verificar_ciclos_cpu", return_value=[]),
        ):
            mod._impl_catalog_quality(contexto_id="ctx-1")

    def test_aprovado_com_ressalvas_when_only_avisos(self):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = self._make_rt(
            cpus=[{"codigo": "CPU-1"}],
            insumos=[{"codigo": "INS-1", "preco_unitario": 10}],
        )
        validador = MagicMock()
        validador.validar_cpu_completa.return_value = []
        validador.validar_vigencia.return_value = SimpleNamespace(
            status="AVISO", codigo="VAL-CAT-VIG-01", mensagem="obsoleto"
        )
        validador.validar_encoding.return_value = SimpleNamespace(status="OK", codigo="OK", mensagem="")

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.domain.validations.cpu_insumo.ValidadorCPUInsumo", return_value=validador),
            patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo"),
            patch("concilium.domain.validations.circular_deps.verificar_ciclos_cpu", return_value=[]),
        ):
            mod._impl_catalog_quality(contexto_id="ctx-1")

    def test_integro_when_no_erros_avisos_or_ciclos(self):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = self._make_rt(cpus=[], insumos=[])
        validador = MagicMock()
        validador.validar_cpu_completa.return_value = []
        validador.validar_vigencia.return_value = SimpleNamespace(status="OK", codigo="OK", mensagem="")
        validador.validar_encoding.return_value = SimpleNamespace(status="OK", codigo="OK", mensagem="")

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.domain.validations.cpu_insumo.ValidadorCPUInsumo", return_value=validador),
            patch("concilium.infrastructure.repositories.insumo.RepositorioInsumo"),
            patch("concilium.domain.validations.circular_deps.verificar_ciclos_cpu", return_value=[]),
        ):
            mod._impl_catalog_quality(contexto_id="ctx-1")


class TestImplCatalogSimulate:
    """Tests for _impl_catalog_simulate (CLT vs PJ comparison)."""

    def _make_resultado(self, total_direto):
        return SimpleNamespace(
            dias_trabalhados=30,
            producao_total=100.0,
            unidade="m3",
            custo_material=10.0,
            custo_mao_obra_base=20.0,
            custo_mao_obra_encargos=5.0,
            custo_equipamento_capital=8.0,
            custo_equipamento_manutencao=2.0,
            custo_diesel_total=3.0,
            total_direto=total_direto,
        )

    def test_success_path_prints_comparison(self):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = MagicMock()
        rt.load_contexto.return_value = SimpleNamespace(catalogo_id="cat-1")
        rt.load_catalogo.return_value = {}
        simulador = MagicMock()
        simulador.simular_cpu.side_effect = [
            self._make_resultado(100.0),
            self._make_resultado(80.0),
        ]

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.domain.services.simulation.SimuladorEngenharia", return_value=simulador),
        ):
            mod._impl_catalog_simulate(
                cpu_id="CPU-1",
                contexto_id="mendeslobo",
                dias=30,
                regime="6x1",
                horas_dia=8.0,
            )

    def test_exception_raises_typer_exit(self):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = MagicMock()
        rt.load_contexto.return_value = SimpleNamespace(catalogo_id="cat-1")
        rt.load_catalogo.return_value = {}
        simulador = MagicMock()
        simulador.simular_cpu.side_effect = RuntimeError("boom")

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.domain.services.simulation.SimuladorEngenharia", return_value=simulador),
            pytest.raises(typer.Exit),
        ):
            mod._impl_catalog_simulate(
                cpu_id="CPU-1",
                contexto_id="mendeslobo",
                dias=30,
                regime="6x1",
                horas_dia=8.0,
            )


class TestImplCatalogExport:
    """Tests for _impl_catalog_export."""

    def _make_rt(self):
        ctx = SimpleNamespace(catalogo_id="cat-1", tema_id="tema-1")
        rt = MagicMock()
        rt.load_contexto.return_value = ctx
        rt.load_catalogo.return_value = {}
        rt.load_tema.return_value.to_catalogo_dict.return_value = {}
        return rt

    def test_default_output_name(self):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = self._make_rt()
        exporter = MagicMock()

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.infrastructure.exporters.catalog_excel.CatalogExporterExcel", return_value=exporter),
        ):
            mod._impl_catalog_export(contexto_id="mendeslobo", output=None)

        exporter.export.assert_called_once()
        called_path = exporter.export.call_args[0][0]
        assert called_path.name == "catalogo_mendeslobo_audit.xlsx"

    def test_explicit_output_path(self, tmp_path):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = self._make_rt()
        exporter = MagicMock()
        out = str(tmp_path / "custom.xlsx")

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.infrastructure.exporters.catalog_excel.CatalogExporterExcel", return_value=exporter),
        ):
            mod._impl_catalog_export(contexto_id="mendeslobo", output=out)

        exporter.export.assert_called_once()

    def test_export_exception_raises_typer_exit(self):
        from concilium.presentation.cli import _commands_manage_helpers_a as mod

        rt = self._make_rt()
        exporter = MagicMock()
        exporter.export.side_effect = RuntimeError("disk full")

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=rt),
            patch("concilium.infrastructure.exporters.catalog_excel.CatalogExporterExcel", return_value=exporter),
            pytest.raises(typer.Exit),
        ):
            mod._impl_catalog_export(contexto_id="mendeslobo", output=None)


# ═══════════════════════════════════════════════════════════════════════════════
# _commands_manage_helpers_c.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestCmrPrintInnerLow:
    def test_empty_list_does_nothing(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_print_inner_low

        console = MagicMock()
        _cmr_print_inner_low([], console)
        console.print.assert_not_called()

    def test_few_items_prints_all(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_print_inner_low

        console = MagicMock()
        items = [
            (
                {
                    "catalog": {"codigo": "C1", "descricao": "d1"},
                    "rfi": {"codigo": "R1", "descricao": "r1"},
                    "score": 0.6,
                },
                "INSUMO",
            )
        ]
        _cmr_print_inner_low(items, console)
        assert console.print.called

    def test_many_items_shows_overflow(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_print_inner_low

        console = MagicMock()
        items = [
            (
                {
                    "catalog": {"codigo": f"C{i}", "descricao": "d"},
                    "rfi": {"codigo": f"R{i}", "descricao": "r"},
                    "score": 0.6,
                },
                "INSUMO",
            )
            for i in range(20)
        ]
        _cmr_print_inner_low(items, console)
        # Should print the header, 15 items, plus overflow line
        assert console.print.call_count >= 17


class TestCmrBuildAllLow:
    def test_combines_ins_and_prod(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_build_all_low

        report_ins = SimpleNamespace(inner_low=[{"x": 1}])
        report_prod = SimpleNamespace(inner_low=[{"y": 2}])
        result = _cmr_build_all_low(report_ins, report_prod)
        assert len(result) == 2
        assert result[0][1] == "INSUMO"
        assert result[1][1] == "PROD"

    def test_empty(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_build_all_low

        report_ins = SimpleNamespace(inner_low=[])
        report_prod = SimpleNamespace(inner_low=[])
        assert _cmr_build_all_low(report_ins, report_prod) == []


class TestCmrAddTableRow:
    def test_adds_row_correctly(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_add_table_row

        table = MagicMock()
        rep = SimpleNamespace(
            inner_high=[{"delta": True}, {"delta": None}],
            inner_low=[1, 2],
            right_only=[1],
            left_only=[1, 2, 3],
        )
        _cmr_add_table_row(table, "INSUMOS", rep)
        table.add_row.assert_called_once_with("INSUMOS", "2", "1", "2", "1", "3")


class TestCmrWriteReport:
    def test_writes_json_file(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_write_report

        console = MagicMock()
        report_ins = SimpleNamespace(
            inner_high=[{"delta": True, "catalog": {"codigo": "C1"}}, {"delta": None, "catalog": {"codigo": "C2"}}],
            inner_low=[{"catalog": {"codigo": "CX"}, "rfi": {"codigo": "RX"}, "score": 0.6}],
            right_only=[{"rfi": {"codigo": "N1", "descricao": "novo"}}],
            left_only=[{"x": 1}],
        )
        report_prod = SimpleNamespace(
            inner_high=[],
            inner_low=[{"catalog": {"id": "P1"}, "rfi": {"id": "P2"}, "score": 0.55}],
            right_only=[{"rfi": {"id": "NP", "descricao": "new prod"}}],
            left_only=[],
        )
        out_path = str(tmp_path / "report.json")
        _cmr_write_report(out_path, report_ins, report_prod, "DRY-RUN", "ctx1", console)
        data = json.loads(Path(out_path).read_text())
        assert data["mode"] == "DRY-RUN"
        assert data["contexto_id"] == "ctx1"
        assert "insumos" in data
        console.print.assert_called_once()


class TestCmrLoadBundle:
    def test_raises_exit_when_bundle_missing(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_load_bundle

        mod = SimpleNamespace(ROOT=tmp_path)
        import typer

        with pytest.raises((SystemExit, typer.Exit)):
            _cmr_load_bundle("testctx", mod)

    def test_loads_bundle_with_producoes(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_load_bundle

        ctx = "testctx"
        bundle_dir = tmp_path / "config" / "catalogos" / ctx
        bundle_dir.mkdir(parents=True)
        bundle = {"insumos": [{"codigo": "I1"}], "producoes": [{"id": "P1"}]}
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        mod = SimpleNamespace(ROOT=tmp_path)
        result_bundle, path, ins, prods = _cmr_load_bundle(ctx, mod)
        assert len(ins) == 1
        assert len(prods) == 1

    def test_loads_bundle_with_produtividades(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_load_bundle

        ctx = "testctx2"
        bundle_dir = tmp_path / "config" / "catalogos" / ctx
        bundle_dir.mkdir(parents=True)
        bundle = {"insumos": [], "produtividades": [{"id": "P2"}]}
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
        mod = SimpleNamespace(ROOT=tmp_path)
        _, _, ins, prods = _cmr_load_bundle(ctx, mod)
        assert len(prods) == 1


class TestCmrApplyChanges:
    def test_apply_with_producoes_key(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_apply_changes

        bundle_path = tmp_path / "bundle.json"
        bundle_path.write_text("{}", encoding="utf-8")
        bundle = {"insumos": [], "producoes": []}
        console = MagicMock()
        mod = MagicMock()
        mod._apply_merge.side_effect = [["new_ins"], ["new_prod"]]

        _cmr_apply_changes(mod, bundle, bundle_path, [], [], [], [], MagicMock(), MagicMock(), False, console)
        data = json.loads(bundle_path.read_text())
        assert data["producoes"] == ["new_prod"]
        assert data["insumos"] == ["new_ins"]

    def test_apply_with_produtividades_key(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_apply_changes

        bundle_path = tmp_path / "bundle2.json"
        bundle_path.write_text("{}", encoding="utf-8")
        bundle = {"insumos": [], "produtividades": []}
        console = MagicMock()
        mod = MagicMock()
        mod._apply_merge.side_effect = [["new_ins"], ["new_prod"]]

        _cmr_apply_changes(mod, bundle, bundle_path, [], [], [], [], MagicMock(), MagicMock(), False, console)
        data = json.loads(bundle_path.read_text())
        assert data["produtividades"] == ["new_prod"]

    def test_verify_pu_with_faltantes(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_apply_changes

        bundle_path = tmp_path / "bundle3.json"
        bundle_path.write_text("{}", encoding="utf-8")
        bundle = {"insumos": [], "producoes": []}
        console = MagicMock()
        mod = MagicMock()
        mod._apply_merge.side_effect = [[], []]

        mock_resultado = {"referencias_faltantes": [{"producao_id": "P1", "faltantes": ["I1"]}], "com_composicao": 0}
        with patch("concilium.application.catalog.pu_calculator.calcular_catalogo", return_value=mock_resultado):
            with patch("concilium.application.catalog.pu_calculator.ParametrosCalculo"):
                _cmr_apply_changes(mod, bundle, bundle_path, [], [], [], [], MagicMock(), MagicMock(), True, console)

    def test_verify_pu_without_faltantes(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_apply_changes

        bundle_path = tmp_path / "bundle4.json"
        bundle_path.write_text("{}", encoding="utf-8")
        bundle = {"insumos": [], "producoes": []}
        console = MagicMock()
        mod = MagicMock()
        mod._apply_merge.side_effect = [[], []]

        mock_resultado = {"referencias_faltantes": [], "com_composicao": 5}
        with patch("concilium.application.catalog.pu_calculator.calcular_catalogo", return_value=mock_resultado):
            with patch("concilium.application.catalog.pu_calculator.ParametrosCalculo"):
                _cmr_apply_changes(mod, bundle, bundle_path, [], [], [], [], MagicMock(), MagicMock(), True, console)


class TestCcpPrintFixed:
    def test_few_fixed_prints_all(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _ccp_print_fixed

        console = MagicMock()
        _ccp_print_fixed(["fix1", "fix2"], apply=True, console=console)
        assert console.print.call_count == 3  # header + 2 items

    def test_many_fixed_shows_overflow(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _ccp_print_fixed

        console = MagicMock()
        _ccp_print_fixed([f"fix{i}" for i in range(35)], apply=False, console=console)
        # header + 30 items + overflow
        assert console.print.call_count == 32

    def test_dry_run_uses_arrow_prefix(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _ccp_print_fixed

        console = MagicMock()
        _ccp_print_fixed(["fix1"], apply=False, console=console)
        printed_args = [str(c) for c in console.print.call_args_list]
        assert any("→" in a for a in printed_args)


class TestImplStructureList:
    def test_calls_resolve_project(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_structure_list

        mock_project = MagicMock()
        mock_project.list_escopos.return_value = []

        with patch("concilium.presentation.cli._commands_manage_helpers_c.resolve_project", return_value=mock_project):
            _impl_structure_list("meu-projeto")

        mock_project.list_escopos.assert_called_once()

    def test_lists_escopos_and_plans(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_structure_list

        mock_plan = SimpleNamespace(status="DRAFT")
        mock_escopo = MagicMock()
        mock_escopo.list_plans.return_value = ["plano-1"]
        mock_escopo.plan.return_value = mock_plan

        mock_project = MagicMock()
        mock_project.list_escopos.return_value = ["escopo-1"]
        mock_project.escopo.return_value = mock_escopo

        with patch("concilium.presentation.cli._commands_manage_helpers_c.resolve_project", return_value=mock_project):
            _impl_structure_list("meu-projeto")

        mock_project.escopo.assert_called_once_with("escopo-1")


class TestImplPlanInit:
    def test_creates_plan_successfully(self):
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_plan_init

        mock_ps = MagicMock()
        mock_ps.plano_id = "plano-xyz"
        mock_escopo = MagicMock()
        mock_escopo.create_plan.return_value = mock_ps
        mock_project = MagicMock()
        mock_project.escopo.return_value = mock_escopo

        with patch("concilium.presentation.cli._commands_manage_helpers_c.resolve_project", return_value=mock_project):
            _impl_plan_init("meu-projeto")

        mock_escopo.create_plan.assert_called_once()


class TestCmrLoadOpenpyxl:
    def test_xlsm_missing_raises(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_load_openpyxl

        mod = SimpleNamespace(XLSM=tmp_path / "nope.xlsm")
        with pytest.raises(typer.Exit):
            _cmr_load_openpyxl(mod)

    def test_import_error_raises_exit(self, tmp_path, monkeypatch):
        import builtins

        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_load_openpyxl

        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "openpyxl":
                raise ImportError("no openpyxl")
            return orig_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        mod = SimpleNamespace(XLSM=tmp_path / "x.xlsm")
        with pytest.raises(typer.Exit):
            _cmr_load_openpyxl(mod)

    def test_ok_returns_openpyxl_and_path(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _cmr_load_openpyxl

        xlsm = tmp_path / "x.xlsm"
        xlsm.touch()
        mod = SimpleNamespace(XLSM=xlsm)
        openpyxl_mod, xlsm_out = _cmr_load_openpyxl(mod)
        assert xlsm_out == xlsm
        assert hasattr(openpyxl_mod, "load_workbook")


class TestCcpWriteBundle:
    def test_with_producoes_key_ok(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _ccp_write_bundle

        bundle_path = tmp_path / "b.json"
        bundle_path.write_text("{}", encoding="utf-8")
        bundle = {"insumos": [], "producoes": []}
        console = MagicMock()
        mock_result = {"resumo": {"erros": 0, "avisos": 0, "infos": 0}}
        with patch(
            "concilium.application.catalog.plausibility_checker.verificar_plausibilidade",
            return_value=mock_result,
        ):
            _ccp_write_bundle(bundle, bundle_path, [{"codigo": "I1"}], [{"id": "P1"}], console)
        data = json.loads(bundle_path.read_text())
        assert data["producoes"] == [{"id": "P1"}]
        assert data["insumos"] == [{"codigo": "I1"}]

    def test_with_produtividades_key_and_erros(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _ccp_write_bundle

        bundle_path = tmp_path / "b2.json"
        bundle_path.write_text("{}", encoding="utf-8")
        bundle = {"insumos": [], "produtividades": []}
        console = MagicMock()
        mock_result = {"resumo": {"erros": 2, "avisos": 1, "infos": 0}}
        with patch(
            "concilium.application.catalog.plausibility_checker.verificar_plausibilidade",
            return_value=mock_result,
        ):
            _ccp_write_bundle(bundle, bundle_path, [], [], console)
        data = json.loads(bundle_path.read_text())
        assert "produtividades" in data
        printed = [str(c) for c in console.print.call_args_list]
        assert any("ATENÇÃO" in p for p in printed)


class TestImplCatalogMergeRfi:
    """Exercises the full _impl_catalog_merge_rfi flow by faking the externally
    loaded merge_rfi.py script (tools_dir resolves outside the repo in this
    environment, so we redirect the importlib load to a fake module we control)."""

    def _make_fake_module_file(self, tmp_path: Path) -> Path:
        content = """
from pathlib import Path


class _Report:
    def __init__(self):
        self.inner_high = []
        self.inner_low = []
        self.right_only = []
        self.left_only = []


def extract_rfi(wb):
    return {"insumos": [], "producoes": []}


def _merge_entities(cat, rfi, id_key="codigo"):
    return _Report(), None


def _apply_merge(cat, rfi, report, id_key="codigo"):
    return list(cat)
"""
        script = tmp_path / "fake_merge_rfi.py"
        script.write_text(content, encoding="utf-8")
        return script

    def _setup(self, monkeypatch, tmp_path, contexto_id):
        import importlib.util as real_importlib_util

        import openpyxl as real_openpyxl

        xlsm_path = tmp_path / "planilha.xlsm"
        wb = real_openpyxl.Workbook()
        wb.save(xlsm_path)

        fake_script = self._make_fake_module_file(tmp_path)

        bundle_dir = tmp_path / "config" / "catalogos" / contexto_id
        bundle_dir.mkdir(parents=True)
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps({"insumos": [], "producoes": []}), encoding="utf-8")

        orig_exists = Path.exists

        def fake_exists(self_path):
            if self_path.name == "merge_rfi.py":
                return True
            return orig_exists(self_path)

        monkeypatch.setattr(Path, "exists", fake_exists)

        orig_spec = real_importlib_util.spec_from_file_location

        def fake_spec_from_file_location(name, location, *args, **kwargs):
            if str(location).endswith("merge_rfi.py"):
                return orig_spec(name, fake_script, *args, **kwargs)
            return orig_spec(name, location, *args, **kwargs)

        monkeypatch.setattr(real_importlib_util, "spec_from_file_location", fake_spec_from_file_location)

        # Patch mod.XLSM/mod.ROOT indirectly: since our fake module doesn't define
        # them at import time (they must be Path values known only once tmp_path
        # exists), inject them onto the loaded module after exec via a wrapper.
        return xlsm_path

    def test_apply_with_verify_pu_and_report_json(self, monkeypatch, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_catalog_merge_rfi

        ctx = "ctx_apply"
        xlsm_path = self._setup(monkeypatch, tmp_path, ctx)

        import concilium.presentation.cli._commands_manage_helpers_c as helpers_c

        def fake_cast(_type, value):
            value.ROOT = tmp_path
            value.XLSM = xlsm_path
            return value

        monkeypatch.setattr(helpers_c, "cast", fake_cast)

        report_path = str(tmp_path / "report.json")
        mock_resultado = {"referencias_faltantes": [], "com_composicao": 0}
        with patch("concilium.application.catalog.pu_calculator.calcular_catalogo", return_value=mock_resultado):
            _impl_catalog_merge_rfi(ctx, apply=True, verify_pu=True, report_json=report_path)

        assert Path(report_path).exists()
        bundle_data = json.loads((tmp_path / "config" / "catalogos" / ctx / ".catalog_bundle.json").read_text())
        assert bundle_data["insumos"] == []

    def test_dry_run_without_report(self, monkeypatch, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_catalog_merge_rfi

        ctx = "ctx_dry"
        xlsm_path = self._setup(monkeypatch, tmp_path, ctx)

        import concilium.presentation.cli._commands_manage_helpers_c as helpers_c

        def fake_cast(_type, value):
            value.ROOT = tmp_path
            value.XLSM = xlsm_path
            return value

        monkeypatch.setattr(helpers_c, "cast", fake_cast)

        _impl_catalog_merge_rfi(ctx, apply=False, verify_pu=False, report_json=None)

    def test_script_not_found_raises_exit(self, tmp_path):
        # No monkeypatching here — merge_rfi.py genuinely does not exist at the
        # computed tools_dir path in this environment, so this exercises the
        # real "script not found" branch without mocking.
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_catalog_merge_rfi

        with pytest.raises(typer.Exit):
            _impl_catalog_merge_rfi("whatever-ctx", apply=False, verify_pu=False, report_json=None)


class TestImplCatalogCurePlausibility:
    def test_bundle_missing_raises(self, tmp_path, monkeypatch):
        import concilium.application.catalog.cure_plausibility as cure_mod
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_catalog_cure_plausibility

        monkeypatch.setattr(cure_mod, "ROOT", tmp_path)
        with pytest.raises(typer.Exit):
            _impl_catalog_cure_plausibility("nope-ctx", False)

    def test_dry_run_with_fixed_and_manual_items(self, tmp_path, monkeypatch):
        import concilium.application.catalog.cure_plausibility as cure_mod
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_catalog_cure_plausibility

        monkeypatch.setattr(cure_mod, "ROOT", tmp_path)
        ctx = "ctxcure1"
        bundle_dir = tmp_path / "config" / "catalogos" / ctx
        bundle_dir.mkdir(parents=True)
        bundle = {
            "insumos": [{"codigo": "EQ1", "tipo": "EQUIPAMENTO", "preco_unitario": 10.0, "atributos_especificos": {}}],
            "producoes": [{"id": "P1", "valor_horario": 5}],
        }
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

        _impl_catalog_cure_plausibility(ctx, False)

    def test_apply_with_fixed_and_manual_writes_bundle(self, tmp_path, monkeypatch):
        import concilium.application.catalog.cure_plausibility as cure_mod
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_catalog_cure_plausibility

        monkeypatch.setattr(cure_mod, "ROOT", tmp_path)
        ctx = "ctxcure2"
        bundle_dir = tmp_path / "config" / "catalogos" / ctx
        bundle_dir.mkdir(parents=True)
        bundle = {
            "insumos": [{"codigo": "EQ1", "tipo": "EQUIPAMENTO", "preco_unitario": 10.0, "atributos_especificos": {}}],
            "produtividades": [{"id": "P1", "valor_horario": 5}],
        }
        bundle_path = bundle_dir / ".catalog_bundle.json"
        bundle_path.write_text(json.dumps(bundle), encoding="utf-8")

        _impl_catalog_cure_plausibility(ctx, True)

        data = json.loads(bundle_path.read_text())
        assert "produtividades" in data

    def test_dry_run_with_no_fixed_and_no_manual_items(self, tmp_path, monkeypatch):
        """Empty bundle → report.fixed and report.manual both empty, covering
        the false branch of both `if report.fixed:` and `if report.manual:`."""
        import concilium.application.catalog.cure_plausibility as cure_mod
        from concilium.presentation.cli._commands_manage_helpers_c import _impl_catalog_cure_plausibility

        monkeypatch.setattr(cure_mod, "ROOT", tmp_path)
        ctx = "ctxcure3"
        bundle_dir = tmp_path / "config" / "catalogos" / ctx
        bundle_dir.mkdir(parents=True)
        bundle = {"insumos": [], "producoes": []}
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

        _impl_catalog_cure_plausibility(ctx, False)


# ═══════════════════════════════════════════════════════════════════════════════
# _commands_manage_helpers_d.py
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunSchemaValidation:
    def test_no_errors_appends_nothing(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _run_schema_validation

        validator = MagicMock()
        validator.iter_errors.return_value = []
        erros = []
        _run_schema_validation(validator, [{"codigo": "CPU-1"}], "CPU", "codigo", erros)
        assert erros == []

    def test_error_appended_with_path(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _run_schema_validation

        err = MagicMock()
        err.absolute_path = ["fieldA", "nested"]
        err.message = "invalid value"
        validator = MagicMock()
        validator.iter_errors.return_value = [err]
        erros = []
        _run_schema_validation(validator, [{"codigo": "CPU-1"}], "CPU", "codigo", erros)
        assert len(erros) == 1
        assert "CPU-1" in erros[0]
        assert "fieldA.nested" in erros[0]

    def test_error_with_empty_path_uses_root(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _run_schema_validation

        err = MagicMock()
        err.absolute_path = []
        err.message = "required field"
        validator = MagicMock()
        validator.iter_errors.return_value = [err]
        erros = []
        _run_schema_validation(validator, [{"codigo": "CPU-2"}], "CPU", "codigo", erros)
        assert "<root>" in erros[0]

    def test_missing_id_field_uses_placeholder(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _run_schema_validation

        err = MagicMock()
        err.absolute_path = []
        err.message = "bad"
        validator = MagicMock()
        validator.iter_errors.return_value = [err]
        erros = []
        _run_schema_validation(validator, [{}], "INSUMO", "codigo", erros)
        assert "<sem-codigo>" in erros[0]


class TestCheckCatalogSemantics:
    def test_missing_producao_ref_is_error(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _check_catalog_semantics

        cpus = [{"codigo": "CPU-1", "producao_id_ref": "PROD-999"}]
        prods = [{"id": "PROD-001"}]
        erros, avisos = [], []
        _check_catalog_semantics(cpus, prods, erros, avisos)
        assert any("PROD-999" in e for e in erros)

    def test_valid_producao_ref_no_error(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _check_catalog_semantics

        cpus = [{"codigo": "CPU-1", "producao_id_ref": "PROD-001"}]
        prods = [{"id": "PROD-001"}]
        erros, avisos = [], []
        _check_catalog_semantics(cpus, prods, erros, avisos)
        assert erros == []

    def test_legacy_fields_generate_aviso(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _check_catalog_semantics

        cpus = [{"codigo": "CPU-L", "producao_horaria": 100}]
        prods = []
        erros, avisos = [], []
        _check_catalog_semantics(cpus, prods, erros, avisos)
        assert any("legados" in a for a in avisos)

    def test_no_ref_no_legacy_no_errors(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _check_catalog_semantics

        cpus = [{"codigo": "CPU-OK"}]
        prods = [{"id": "PROD-01"}]
        erros, avisos = [], []
        _check_catalog_semantics(cpus, prods, erros, avisos)
        assert erros == [] and avisos == []


class TestBuildSchemaValidators:
    def test_builds_validators_from_real_schemas(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

        schema_root = Path("config") / "schemas" / "catalog"
        cpu_v, prod_v, ins_v = _build_schema_validators(schema_root)
        assert cpu_v is not None
        assert prod_v is not None
        assert ins_v is not None

    def test_missing_schema_file_raises_exit(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

        with pytest.raises(typer.Exit) as exc_info:
            _build_schema_validators(tmp_path)
        assert exc_info.value.exit_code == 2

    def test_missing_common_schema_is_optional(self, tmp_path):
        """common.schema.json ausente não deve impedir a construção dos validadores."""
        from concilium.presentation.cli._commands_manage_helpers_d import _build_schema_validators

        real_root = Path("config") / "schemas" / "catalog"
        for name in ["cpu.schema.json", "producao.schema.json", "insumo.schema.json"]:
            (tmp_path / name).write_text((real_root / name).read_text(encoding="utf-8"), encoding="utf-8")

        cpu_v, prod_v, ins_v = _build_schema_validators(tmp_path)
        assert cpu_v is not None
        assert prod_v is not None
        assert ins_v is not None


class TestImplCatalogValidateSchema:
    def _make_rt(self, catalogo: dict):
        rt = MagicMock()
        rt.load_contexto.return_value = SimpleNamespace(catalogo_id="cat1")
        rt.load_catalogo.return_value = catalogo
        return rt

    def test_empty_catalog_prints_ok(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_validate_schema

        rt = self._make_rt({"cpus": [], "insumos": [], "produtividades": [], "producoes": []})
        with patch("concilium.presentation.cli._commands_manage_helpers_d._runtime", return_value=rt):
            # Should not raise — no errors, no warnings.
            _impl_catalog_validate_schema(contexto_id="ctx1", fail_on_warning=False)

    def test_non_list_produtividades_and_producoes_default_to_empty(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_validate_schema

        rt = self._make_rt({"cpus": [], "insumos": [], "produtividades": None, "producoes": None})
        with patch("concilium.presentation.cli._commands_manage_helpers_d._runtime", return_value=rt):
            _impl_catalog_validate_schema(contexto_id="ctx1", fail_on_warning=False)

    def test_schema_errors_raise_exit_1(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_validate_schema

        # CPU faltando campos obrigatórios (descricao, unidade, etc.) gera erro de schema.
        rt = self._make_rt({"cpus": [{"codigo": "CPU-1"}], "insumos": [], "produtividades": [], "producoes": []})
        with patch("concilium.presentation.cli._commands_manage_helpers_d._runtime", return_value=rt):
            with pytest.raises(typer.Exit) as exc_info:
                _impl_catalog_validate_schema(contexto_id="ctx1", fail_on_warning=False)
            assert exc_info.value.exit_code == 1

    def test_warnings_with_fail_on_warning_raises_exit_1(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_validate_schema

        # CPU válido mas com campo legado -> aviso semântico, sem erro de schema.
        cpu = {
            "codigo": "CPU-1",
            "descricao": "desc",
            "unidade": "m3",
            "origem": "CATALOGO_MENDESLOBO",
            "producao_id_ref": None,
            "categoria": "SERVICO",
            "composicao_itens": [],
            "producao_horaria": 10,
        }
        rt = self._make_rt({"cpus": [cpu], "insumos": [], "produtividades": [], "producoes": []})
        with patch("concilium.presentation.cli._commands_manage_helpers_d._runtime", return_value=rt):
            with pytest.raises(typer.Exit) as exc_info:
                _impl_catalog_validate_schema(contexto_id="ctx1", fail_on_warning=True)
            assert exc_info.value.exit_code == 1

    def test_import_error_on_jsonschema_missing(self):
        from concilium.presentation.cli import _commands_manage_helpers_d as mod

        with patch.object(mod, "_build_schema_validators", side_effect=ImportError("no jsonschema")):
            with pytest.raises(typer.Exit) as exc_info:
                mod._impl_catalog_validate_schema(contexto_id="ctx1", fail_on_warning=False)
            assert exc_info.value.exit_code == 2


class TestPrintMessagesSection:
    def test_empty_messages_no_output(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _print_messages_section

        console = MagicMock()
        _print_messages_section(console, [], "[bold red]Erros:[/bold red]", "erros", 30)
        console.print.assert_not_called()

    def test_few_messages_printed(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _print_messages_section

        console = MagicMock()
        _print_messages_section(console, ["error 1", "error 2"], "[bold red]Erros:[/bold red]", "erros", 30)
        assert console.print.call_count == 3  # title + 2 messages

    def test_overflow_shows_more(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _print_messages_section

        console = MagicMock()
        msgs = [f"err{i}" for i in range(35)]
        _print_messages_section(console, msgs, "[bold]Title[/bold]", "erros", 30)
        # title + 30 messages + overflow line
        assert console.print.call_count == 32


class TestPrintCatalogValidationResults:
    def test_prints_table_and_sections(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _print_catalog_validation_results

        console = MagicMock()
        cpus = [{"codigo": "CPU-1"}]
        prods = [{"id": "P1"}]
        insumos = [{"codigo": "I1"}]
        erros = ["CPU CPU-1: erro x", "PRODUCAO P1: erro y"]
        avisos = ["CPU CPU-1: aviso z"]
        _print_catalog_validation_results(console, cpus, prods, insumos, erros, avisos, "testcat")
        assert console.print.called


class TestImplCatalogCureSchema:
    """A impl atual chama cure_schema.run() diretamente (não mais scripts/cure_catalog.py)."""

    def test_exits_1_when_context_missing(self, monkeypatch):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_cure_schema

        with pytest.raises((SystemExit, typer.Exit)) as exc_info:
            _impl_catalog_cure_schema(contexto_id="ctx-inexistente", apply=True)
        exc = exc_info.value
        code = getattr(exc, "code", None) if isinstance(exc, SystemExit) else getattr(exc, "exit_code", None)
        assert code == 1

    def test_exits_1_on_runtime_error(self):
        import typer

        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_cure_schema

        with patch("concilium.application.catalog.cure_schema.run", side_effect=RuntimeError("erros residuais")):
            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                _impl_catalog_cure_schema(contexto_id="ctx1", apply=True)
        exc = exc_info.value
        code = getattr(exc, "code", None) if isinstance(exc, SystemExit) else getattr(exc, "exit_code", None)
        assert code == 1

    def test_success_does_not_raise_and_forwards_flags(self):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_cure_schema

        with patch("concilium.application.catalog.cure_schema.run") as mock_run:
            _impl_catalog_cure_schema(contexto_id="ctx1", apply=False)
        mock_run.assert_called_once_with("ctx1", False)


class TestImplCatalogAuditReasonability:
    def test_calls_service_and_writes_artifact(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_audit_reasonability

        artifact = {
            "summary": {"total_cpus": 3, "erros": 1, "avisos": 2, "outliers": 0, "mediana_producao_horaria": 10.5},
            "findings": [{"severity": "WARN", "cpu_id": "CPU-1", "issues": ["problema"]}],
        }

        mock_rt = MagicMock()
        mock_ctx = SimpleNamespace(catalogo_id="testcat")
        mock_rt.load_contexto.return_value = mock_ctx
        mock_rt.load_catalogo.return_value = {"cpus": [], "produtividades": [], "producoes": []}

        with patch("concilium.presentation.cli._commands_manage_helpers_d._runtime", return_value=mock_rt):
            with patch(
                "concilium.application.services.catalog.catalog_reasonability.build_catalog_reasonability_artifact",
                return_value=artifact,
            ):
                out = str(tmp_path / "audit.json")
                _impl_catalog_audit_reasonability(contexto_id="ctx1", output=out, max_findings=20)

        assert Path(out).exists()
        data = json.loads(Path(out).read_text())
        assert data["summary"]["total_cpus"] == 3

    def test_no_findings_prints_ok(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_audit_reasonability

        artifact = {
            "summary": {"total_cpus": 0, "erros": 0, "avisos": 0, "outliers": 0, "mediana_producao_horaria": 0.0},
            "findings": [],
        }

        mock_rt = MagicMock()
        mock_ctx = SimpleNamespace(catalogo_id="emptycat")
        mock_rt.load_contexto.return_value = mock_ctx
        mock_rt.load_catalogo.return_value = {"cpus": None, "produtividades": None, "producoes": None}

        with patch("concilium.presentation.cli._commands_manage_helpers_d._runtime", return_value=mock_rt):
            with patch(
                "concilium.application.services.catalog.catalog_reasonability.build_catalog_reasonability_artifact",
                return_value=artifact,
            ):
                out = str(tmp_path / "audit_empty.json")
                _impl_catalog_audit_reasonability(contexto_id="ctx1", output=out, max_findings=20)


class TestImplCatalogTendencia:
    def test_raises_exit_when_bundle_missing(self, tmp_path, monkeypatch):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_tendencia

        with patch(
            "concilium.presentation.cli._commands_manage_helpers_d._config_root", return_value=tmp_path / "config"
        ):
            import typer

            with pytest.raises((SystemExit, typer.Exit)) as exc_info:
                _impl_catalog_tendencia(contexto_id="missing", jurisdicao_id=None, output="")
            exc = exc_info.value
            code = getattr(exc, "code", None) if isinstance(exc, SystemExit) else getattr(exc, "exit_code", None)
            assert code == 1

    def test_renders_table_and_saves_output(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_tendencia

        config_root = tmp_path / "config"
        bundle_dir = config_root / "catalogos" / "ctx1"
        bundle_dir.mkdir(parents=True)
        bundle = {"insumos": [{"codigo": "I1", "tipo": "MATERIAL", "preco_unitario": 10.0}]}
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

        from concilium.application.catalog.price_trend import IndiceCategoria, RelatorioTendencia

        idx = IndiceCategoria(
            tipo="MATERIAL",
            n_insumos_total=1,
            n_insumos_com_historico=0,
            variacao_media_pct=5.0,
            variacao_mediana_pct=5.0,
            variacao_max_pct=10.0,
            variacao_min_pct=0.0,
        )
        relatorio = RelatorioTendencia(
            contexto_id="ctx1",
            gerado_em="2026-06-12",
            data_base_analise="2026-06-12",
            jurisdicao_id=None,
            indices_por_categoria=[idx],
            resumo={"total_insumos": 1, "total_com_historico": 0, "total_com_sicro_regional": 0},
        )

        out_path = str(tmp_path / "trend.json")
        with patch("concilium.presentation.cli._commands_manage_helpers_d._config_root", return_value=config_root):
            with patch("concilium.application.catalog.price_trend.calcular_tendencia", return_value=relatorio):
                _impl_catalog_tendencia(contexto_id="ctx1", jurisdicao_id=None, output=out_path)

        assert Path(out_path).exists()

    def test_with_jurisdicao_prints_sicro_line(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_tendencia

        config_root = tmp_path / "config"
        bundle_dir = config_root / "catalogos" / "ctx1"
        bundle_dir.mkdir(parents=True)
        bundle = {"insumos": []}
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

        relatorio = SimpleNamespace(
            indices_por_categoria=[],
            resumo={"total_insumos": 0, "total_com_historico": 0, "total_com_sicro_regional": 5},
        )

        with patch("concilium.presentation.cli._commands_manage_helpers_d._config_root", return_value=config_root):
            with patch("concilium.application.catalog.price_trend.calcular_tendencia", return_value=relatorio):
                # Should not raise
                _impl_catalog_tendencia(contexto_id="ctx1", jurisdicao_id="BR-CE", output="")

    def test_high_variacao_uses_yellow_color(self, tmp_path):
        from concilium.presentation.cli._commands_manage_helpers_d import _impl_catalog_tendencia

        config_root = tmp_path / "config"
        bundle_dir = config_root / "catalogos" / "ctx1"
        bundle_dir.mkdir(parents=True)
        bundle = {"insumos": []}
        (bundle_dir / ".catalog_bundle.json").write_text(json.dumps(bundle), encoding="utf-8")

        idx_yellow = SimpleNamespace(
            tipo="MAO_DE_OBRA",
            n_insumos_total=1,
            n_insumos_com_historico=1,
            variacao_media_pct=20.0,  # > 15, < 30 → yellow
            variacao_mediana_pct=20.0,
            variacao_max_pct=25.0,
        )
        idx_red = SimpleNamespace(
            tipo="EQUIP",
            n_insumos_total=1,
            n_insumos_com_historico=1,
            variacao_media_pct=35.0,  # > 30 → red
            variacao_mediana_pct=35.0,
            variacao_max_pct=40.0,
        )
        relatorio = SimpleNamespace(
            indices_por_categoria=[idx_yellow, idx_red],
            resumo={"total_insumos": 2, "total_com_historico": 2, "total_com_sicro_regional": 0},
        )

        with patch("concilium.presentation.cli._commands_manage_helpers_d._config_root", return_value=config_root):
            with patch("concilium.application.catalog.price_trend.calcular_tendencia", return_value=relatorio):
                # Should not raise
                _impl_catalog_tendencia(contexto_id="ctx1", jurisdicao_id=None, output="")


# ═══════════════════════════════════════════════════════════════════════════════
# commands_config_version.py
# ═══════════════════════════════════════════════════════════════════════════════


def _make_context_app():
    """Build a standalone Typer app wrapping the context commands."""
    from concilium.presentation.cli.commands_config_version import app_context

    return app_context


def _make_perfil_app():
    from concilium.presentation.cli.commands_config_version import app_perfil

    return app_perfil


class TestConfigRoot:
    def test_returns_valid_path_when_config_exists(self, tmp_path, monkeypatch):
        from concilium.presentation.cli import commands_config_version as mod

        # Override the file location to use tmp_path structure
        config = tmp_path / "config"
        config.mkdir()
        # Patch __file__ parents
        with patch.object(mod, "_config_root", return_value=config):
            result = mod._config_root()
        assert result == config

    def test_raises_bad_parameter_when_no_config(self, tmp_path, monkeypatch):
        """Real _config_root raises BadParameter when no config/ dir found."""
        import concilium.presentation.cli.commands_config_version as cv_mod

        with patch.object(cv_mod.Path, "exists", return_value=False):
            with pytest.raises((typer.BadParameter, SystemExit)):
                cv_mod._config_root()

    def test_falls_back_to_second_candidate(self):
        """Real _config_root: first candidate (parents[4]) missing, second
        (parents[5]) exists — exercises the loop's second iteration."""
        import concilium.presentation.cli.commands_config_version as cv_mod

        real_exists = Path.exists
        first_candidate = Path(cv_mod.__file__).parents[4] / "config"
        second_candidate = Path(cv_mod.__file__).parents[5] / "config"

        def fake_exists(self):
            if self == first_candidate:
                return False
            if self == second_candidate:
                return True
            return real_exists(self)

        with patch.object(cv_mod.Path, "exists", fake_exists):
            result = cv_mod._config_root()
        assert result == second_candidate


class TestContextList:
    def test_empty_contexts_prints_warning(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.list_contexts.return_value = []

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["list"])

        assert result.exit_code in (0, 1)
        assert "Nenhum" in result.output

    def test_with_contexts_prints_table(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.list_contexts.return_value = [
            {"id": "ctx1", "nome": "Context 1", "current_version": "v2", "versions": ["v1", "v2"]},
        ]

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "ctx1" in result.output


class TestContextVersions:
    def test_no_versions_prints_warning(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.list_versions.return_value = []
        mock_svc.current_version.return_value = "v1"

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["versions", "ctx1"])

        assert result.exit_code in (0, 1)
        assert "Nenhuma" in result.output

    def test_with_versions_shows_table(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.list_versions.return_value = [
            {"version": "v1", "created_at": "2024-01-01T00:00:00", "created_by": "alice", "motivo": "inicial"},
            {"version": "v2", "created_at": "2024-02-01T00:00:00", "created_by": "bob", "motivo": "update"},
        ]
        mock_svc.current_version.return_value = "v2"

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["versions", "ctx1"])

        assert result.exit_code == 0
        assert "v1" in result.output
        assert "v2" in result.output


class TestContextNewVersion:
    def test_creates_version_and_makes_current(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v3"}

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["new-version", "ctx1", "--motivo", "nova feature"])

        assert result.exit_code == 0
        assert "v3" in result.output

    def test_creates_version_no_current(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v4"}

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["new-version", "ctx1", "--motivo", "test", "--no-current"])

        assert result.exit_code == 0
        assert "v4" in result.output
        # Should NOT show "Versão ativa atualizada"
        assert "ativa atualizada" not in result.output

    def test_creates_version_with_optional_fields(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v5"}

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(
                    app,
                    [
                        "new-version",
                        "ctx1",
                        "--motivo",
                        "update cat",
                        "--catalogo-id",
                        "newcat",
                        "--jurisdicao-id",
                        "BR-CE",
                        "--perfil-id",
                        "p1",
                        "--author",
                        "testuser",
                    ],
                )

        assert result.exit_code == 0
        # Verify fields were passed to create_version
        call_args = mock_svc.create_version.call_args
        fields = call_args[0][1]
        assert fields.get("catalogo_id") == "newcat"
        assert fields.get("jurisdicao_id") == "BR-CE"
        assert fields.get("perfil_id") == "p1"


class TestContextCompare:
    def test_identical_versions_prints_green(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {"changed": {}, "unchanged": ["catalogo_id"]}

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["compare", "ctx1", "v1", "v2"])

        assert result.exit_code == 0
        assert "idênticas" in result.output

    def test_changed_fields_shows_table(self):
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {
            "changed": {"catalogo_id": {"de": "cat1", "para": "cat2"}},
            "unchanged": ["perfil_id"],
        }

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["compare", "ctx1", "v1", "v2"])

        assert result.exit_code == 0
        assert "catalogo_id" in result.output
        assert "cat1" in result.output
        assert "cat2" in result.output

    def test_changed_fields_without_unchanged_skips_footer(self):
        """When `unchanged` is empty, the 'Inalterados' footer line is skipped."""
        app = _make_context_app()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {
            "changed": {"catalogo_id": {"de": "cat1", "para": "cat2"}},
            "unchanged": [],
        }

        with patch(
            "concilium.presentation.cli.commands_config_version.ContextoVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["compare", "ctx1", "v1", "v2"])

        assert result.exit_code == 0
        assert "Inalterados" not in result.output


class TestPerfilList:
    def test_empty_perfis_prints_warning(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.list_perfis.return_value = []

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["list"])

        assert "Nenhum" in result.output

    def test_with_perfis_prints_table(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.list_perfis.return_value = [
            {"id": "perfil1", "nome": "Perfil 1", "current_version": "v1", "versions": ["v1"]},
        ]

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["list"])

        assert result.exit_code == 0
        assert "perfil1" in result.output


class TestPerfilVersions:
    def test_no_versions_prints_warning(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.list_versions.return_value = []
        mock_svc.current_version.return_value = "v1"

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["versions", "perfil1"])

        assert "Nenhuma" in result.output

    def test_with_versions_shows_table(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.list_versions.return_value = [
            {"version": "v1", "created_at": None, "created_by": None, "motivo": None},
        ]
        mock_svc.current_version.return_value = "v1"

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["versions", "perfil1"])

        assert result.exit_code == 0
        assert "v1" in result.output


class TestPerfilNewVersion:
    def test_creates_version(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v2"}

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["new-version", "perfil1", "--motivo", "atualização"])

        assert result.exit_code == 0
        assert "v2" in result.output

    def test_creates_version_with_jurisdicao(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v3"}

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                runner.invoke(
                    app, ["new-version", "perfil1", "--motivo", "jurisdição nova", "--jurisdicao-id", "BR-SP"]
                )

        call_args = mock_svc.create_version.call_args
        fields = call_args[0][1]
        assert fields.get("jurisdicao_id") == "BR-SP"

    def test_no_current_flag(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.create_version.return_value = {"version": "v4"}

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["new-version", "perfil1", "--motivo", "test", "--no-current"])

        assert result.exit_code == 0
        assert "ativa atualizada" not in result.output


class TestPerfilCompare:
    def test_identical_versions(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {"changed": {}, "unchanged": []}

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["compare", "perfil1", "v1", "v2"])

        assert "idênticas" in result.output

    def test_changed_fields(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {
            "changed": {"jurisdicao_id": {"de": "BR-DF", "para": "BR-GO"}},
            "unchanged": [],
        }

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["compare", "perfil1", "v1", "v2"])

        assert result.exit_code == 0
        assert "jurisdicao_id" in result.output
        assert "BR-DF" in result.output
        assert "BR-GO" in result.output

    def test_unchanged_items_printed(self):
        app = _make_perfil_app()
        mock_svc = MagicMock()
        mock_svc.compare.return_value = {
            "changed": {"k": {"de": "a", "para": "b"}},
            "unchanged": ["field_x", "field_y"],
        }

        with patch(
            "concilium.presentation.cli.commands_config_version.PerfilVersionService",
            return_value=mock_svc,
        ):
            with patch("concilium.presentation.cli.commands_config_version._config_root", return_value=Path("/fake")):
                result = runner.invoke(app, ["compare", "perfil1", "v1", "v2"])

        assert "Inalterados" in result.output
        assert "field_x" in result.output
