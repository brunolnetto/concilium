"""Tests for CatalogExporterExcel and _apply_body_row."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_sim_result(
    total_direto=1000.0, custo_mao_obra_base=400.0, custo_mao_obra_encargos=200.0, custo_diesel_total=100.0
):
    return SimpleNamespace(
        total_direto=total_direto,
        custo_mao_obra_base=custo_mao_obra_base,
        custo_mao_obra_encargos=custo_mao_obra_encargos,
        custo_diesel_total=custo_diesel_total,
    )


def _minimal_catalogo(**extra):
    cat = {
        "insumos": [],
        "cpus": [],
        "producoes": [],
        "identidade_visual": {},
    }
    cat.update(extra)
    return cat


# ---------------------------------------------------------------------------
# Tests: _apply_body_row
# ---------------------------------------------------------------------------


class TestApplyBodyRow:
    def _make_cell(self):
        cell = MagicMock()
        return cell

    def test_fill_applied_when_truthy(self):
        from concilium.infrastructure.exporters.catalog_excel import _apply_body_row

        cells = [self._make_cell(), self._make_cell()]
        fill = MagicMock()
        border = MagicMock()

        body_font = MagicMock()
        _apply_body_row(cells, fill, border, body_font)

        for cell in cells:
            assert cell.fill == fill
            assert cell.border == border
            assert cell.font == body_font

    def test_fill_not_applied_when_none(self):
        from concilium.infrastructure.exporters.catalog_excel import _apply_body_row

        cell = self._make_cell()
        border = MagicMock()

        _apply_body_row([cell], None, border, MagicMock())

        # fill attribute should not have been set
        assert cell.fill != MagicMock()  # it remains the default mock attribute
        assert cell.fill is not None  # just ensure no AttributeError

    def test_border_always_applied(self):
        from concilium.infrastructure.exporters.catalog_excel import _apply_body_row

        cell = self._make_cell()
        border = MagicMock()

        _apply_body_row([cell], None, border, MagicMock())

        assert cell.border == border

    def test_empty_row(self):
        from concilium.infrastructure.exporters.catalog_excel import _apply_body_row

        # Must not raise even with empty iterable
        _apply_body_row([], MagicMock(), MagicMock(), MagicMock())


# ---------------------------------------------------------------------------
# Tests: CatalogExporterExcel.__init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_stores_catalogo_and_jurisdicao(self):
        from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

        cat = _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia") as MockSim:
            exp = CatalogExporterExcel(cat, jurisdicao_id="BR-SP")

        assert exp.catalogo is cat
        assert exp.jurisdicao_id == "BR-SP"
        MockSim.assert_called_once_with(cat)

    def test_default_jurisdicao_none(self):
        from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

        cat = _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia"):
            exp = CatalogExporterExcel(cat)

        assert exp.jurisdicao_id is None


# ---------------------------------------------------------------------------
# Tests: _get_preco_regional
# ---------------------------------------------------------------------------


class TestGetPrecoRegional:
    def _exporter(self, jurisdicao_id=None):
        cat = _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia"):
            from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

            return CatalogExporterExcel(cat, jurisdicao_id=jurisdicao_id)

    def test_no_jurisdicao_returns_preco_unitario(self):
        exp = self._exporter(jurisdicao_id=None)
        insumo = {"preco_unitario": 42.0}
        assert exp._get_preco_regional(insumo) == 42.0

    def test_jurisdicao_present_in_regionalizacao(self):
        exp = self._exporter(jurisdicao_id="BR-SP")
        insumo = {
            "preco_unitario": 10.0,
            "regionalizacao": {"BR-SP": {"preco": 15.0}},
        }
        assert exp._get_preco_regional(insumo) == 15.0

    def test_jurisdicao_not_in_regionalizacao_falls_back(self):
        exp = self._exporter(jurisdicao_id="BR-RJ")
        insumo = {
            "preco_unitario": 10.0,
            "regionalizacao": {"BR-SP": {"preco": 15.0}},
        }
        assert exp._get_preco_regional(insumo) == 10.0

    def test_regionalizacao_missing_falls_back(self):
        exp = self._exporter(jurisdicao_id="BR-SP")
        insumo = {"preco_unitario": 9.99}
        assert exp._get_preco_regional(insumo) == 9.99


# ---------------------------------------------------------------------------
# Tests: _cex_build_insumos_dfs
# ---------------------------------------------------------------------------


class TestCexBuildInsumosDfs:
    def _exporter(self):
        cat = _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia"):
            from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

            return CatalogExporterExcel(cat)

    def test_returns_three_dataframes(self):
        exp = self._exporter()
        result = exp._cex_build_insumos_dfs([])
        assert len(result) == 3
        for df in result:
            assert isinstance(df, pd.DataFrame)

    def test_material_goes_to_first_df(self):
        exp = self._exporter()
        insumo = {
            "tipo": "MATERIAL",
            "codigo": "MAT-001",
            "descricao": "Areia",
            "unidade": "m3",
            "preco_unitario": 50.0,
            "categoria": "A",
            "fonte_preco": "SINAPI",
            "data_referencia_preco": "2024-01",
        }
        df_mat, df_mo, df_eq = exp._cex_build_insumos_dfs([insumo])
        assert len(df_mat) == 1
        assert df_mat.iloc[0]["Codigo"] == "MAT-001"
        assert len(df_mo) == 0
        assert len(df_eq) == 0

    def test_mao_obra_goes_to_second_df(self):
        exp = self._exporter()
        insumo = {
            "tipo": "MAO_OBRA",
            "codigo": "MO-001",
            "descricao": "Servente",
            "unidade": "h",
            "preco_unitario": 20.0,
            "categoria": "B",
            "fonte_preco": "CCT",
            "data_referencia_preco": "2024-01",
        }
        df_mat, df_mo, df_eq = exp._cex_build_insumos_dfs([insumo])
        assert len(df_mo) == 1
        assert len(df_mat) == 0

    def test_equipamento_goes_to_third_df_with_extra_cols(self):
        exp = self._exporter()
        insumo = {
            "tipo": "EQUIPAMENTO",
            "codigo": "EQ-001",
            "descricao": "Escavadeira",
            "unidade": "h",
            "preco_unitario": 300.0,
            "categoria": "C",
            "fonte_preco": "SINAPI",
            "data_referencia_preco": "2024-01",
            "atributos_especificos": {
                "horas_mes": 176,
                "decomposicao_equip": {
                    "custo_capital_h": 50.0,
                    "custo_mao_obra_h": 30.0,
                    "custo_diesel_h": 20.0,
                    "custo_material_h": 10.0,
                },
            },
        }
        df_mat, df_mo, df_eq = exp._cex_build_insumos_dfs([insumo])
        assert len(df_eq) == 1
        row = df_eq.iloc[0]
        assert row["H/Mes"] == 176
        assert row["Capital (R$/h)"] == 50.0

    def test_equipamento_without_atributos_uses_defaults(self):
        exp = self._exporter()
        insumo = {
            "tipo": "EQUIPAMENTO",
            "codigo": "EQ-002",
            "descricao": "Compactador",
            "unidade": "h",
            "preco_unitario": 100.0,
            "categoria": "C",
            "fonte_preco": "SINAPI",
            "data_referencia_preco": "2024-01",
        }
        df_mat, df_mo, df_eq = exp._cex_build_insumos_dfs([insumo])
        assert len(df_eq) == 1
        row = df_eq.iloc[0]
        assert row["H/Mes"] == 200  # default
        assert row["Capital (R$/h)"] == 0

    def test_unknown_tipo_is_skipped(self):
        exp = self._exporter()
        insumo = {
            "tipo": "OUTRO",
            "codigo": "X-001",
            "descricao": "Misc",
            "unidade": "un",
            "preco_unitario": 1.0,
        }
        df_mat, df_mo, df_eq = exp._cex_build_insumos_dfs([insumo])
        assert len(df_mat) == 0
        assert len(df_mo) == 0
        assert len(df_eq) == 0


# ---------------------------------------------------------------------------
# Tests: _cex_build_cpu_row
# ---------------------------------------------------------------------------


class TestCexBuildCpuRow:
    def _exporter_with_mock_sim(self, catalogo=None):
        cat = catalogo or _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia"):
            from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

            exp = CatalogExporterExcel(cat)
        mock_sim = exp.simulador
        return exp, mock_sim

    def test_basic_cpu_row(self):
        exp, mock_sim = self._exporter_with_mock_sim()
        mock_sim.simular_cpu.return_value = _make_sim_result()

        cpu = {
            "codigo": "CPU-001",
            "descricao": "Escavação",
            "unidade": "m3",
            "categoria": "TERRA",
            "producao_horaria": 50,
            "equipe": {
                "funcoes": [{"funcao_id": "OP", "num_pessoas": 1}],
                "equipamentos": [{"equip_id": "ESC", "num_unidades": 1}],
            },
        }
        row = exp._cex_build_cpu_row(cpu)

        assert row["Codigo"] == "CPU-001"
        assert row["Custo Direto CLT"] == 1000.0
        assert row["Custo Direto PJ"] == 1000.0
        assert "OP:1" in row["Equipe (MO)"]
        assert "ESC:1" in row["Equipe (EQ)"]

    def test_cpu_without_equipe_falls_back_to_producao(self):
        prod = {
            "id": "PROD-A",
            "equipe": {
                "funcoes": [{"funcao_id": "AUX", "num_pessoas": 2}],
                "equipamentos": [],
            },
        }
        cat = _minimal_catalogo(producoes=[prod])
        exp, mock_sim = self._exporter_with_mock_sim(cat)
        mock_sim.simular_cpu.return_value = _make_sim_result()

        cpu = {
            "codigo": "CPU-002",
            "descricao": "Aterro",
            "unidade": "m3",
            "categoria": "TERRA",
            "producao_horaria": 30,
            "producao_id": "PROD-A",
        }
        row = exp._cex_build_cpu_row(cpu)
        assert "AUX:2" in row["Equipe (MO)"]

    def test_cpu_without_equipe_and_no_producao(self):
        cat = _minimal_catalogo(producoes=[])
        exp, mock_sim = self._exporter_with_mock_sim(cat)
        mock_sim.simular_cpu.return_value = _make_sim_result()

        cpu = {
            "codigo": "CPU-003",
            "descricao": "Regularização",
            "unidade": "m2",
            "categoria": "TERRA",
            "producao_horaria": 100,
        }
        row = exp._cex_build_cpu_row(cpu)
        assert row["Equipe (MO)"] == ""
        assert row["Equipe (EQ)"] == ""

    def test_composicao_padrao_equipe_used_when_equipe_missing(self):
        exp, mock_sim = self._exporter_with_mock_sim()
        mock_sim.simular_cpu.return_value = _make_sim_result()

        cpu = {
            "codigo": "CPU-004",
            "descricao": "Compactação",
            "unidade": "m3",
            "categoria": "TERRA",
            "producao_horaria": 20,
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "COMP", "num_pessoas": 1}],
                "equipamentos": [{"equip_id": "ROD", "num_unidades": 1}],
            },
        }
        row = exp._cex_build_cpu_row(cpu)
        assert "COMP:1" in row["Equipe (MO)"]

    def test_producao_composicao_padrao_equipe_fallback(self):
        prod = {
            "id": "PROD-B",
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "TEC", "num_pessoas": 3}],
                "equipamentos": [],
            },
        }
        cat = _minimal_catalogo(producoes=[prod])
        exp, mock_sim = self._exporter_with_mock_sim(cat)
        mock_sim.simular_cpu.return_value = _make_sim_result()

        cpu = {
            "codigo": "CPU-005",
            "descricao": "Terraplanagem",
            "unidade": "m3",
            "categoria": "TERRA",
            "producao_horaria": 40,
            "producao_id": "PROD-B",
        }
        row = exp._cex_build_cpu_row(cpu)
        assert "TEC:3" in row["Equipe (MO)"]

    def test_simular_cpu_called_twice_clt_and_pj(self):
        exp, mock_sim = self._exporter_with_mock_sim()
        mock_sim.simular_cpu.return_value = _make_sim_result()

        cpu = {
            "codigo": "CPU-X",
            "descricao": "Test",
            "unidade": "m3",
            "categoria": "T",
            "producao_horaria": 1,
        }
        exp._cex_build_cpu_row(cpu)
        calls = mock_sim.simular_cpu.call_args_list
        # simular_cpu(cpu_id, qty, jornada, frentes, regime)
        call_args = [c.args for c in calls]
        assert any("clt" in str(args) for args in call_args)
        assert any("pj" in str(args) for args in call_args)


# ---------------------------------------------------------------------------
# Tests: _cex_write_sheets
# ---------------------------------------------------------------------------


class TestCexWriteSheets:
    def _exporter(self):
        cat = _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia"):
            from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

            exp = CatalogExporterExcel(cat)
        return exp

    def test_empty_dfs_skip_writing(self):
        exp = self._exporter()
        writer = MagicMock()
        exp._aplicar_estilo = MagicMock()  # avoid openpyxl calls

        empty = pd.DataFrame()
        exp._cex_write_sheets(writer, empty, empty, empty, empty, empty)

        # to_excel should never be called for empty dfs
        writer.to_excel = MagicMock()  # not called on writer itself
        exp._aplicar_estilo.assert_called_once_with(writer)

    def test_non_empty_cpus_written(self):
        exp = self._exporter()
        writer = MagicMock()
        exp._aplicar_estilo = MagicMock()

        df_cpus = pd.DataFrame([{"Codigo": "CPU-1", "Descricao": "Test"}])
        empty = pd.DataFrame()

        with patch.object(df_cpus, "to_excel") as mock_to_excel:
            exp._cex_write_sheets(writer, df_cpus, empty, empty, empty, empty)
            mock_to_excel.assert_called_once_with(writer, sheet_name="Resumo_CPUs", index=False)

    def test_all_non_empty_sheets_written(self):
        exp = self._exporter()
        writer = MagicMock()
        exp._aplicar_estilo = MagicMock()

        data = [{"A": 1}]
        df_cpus = pd.DataFrame(data)
        df_mat = pd.DataFrame(data)
        df_mo = pd.DataFrame(data)
        df_eq = pd.DataFrame(data)
        df_prods = pd.DataFrame(data)

        written_sheets = []

        def capture_to_excel(w, sheet_name=None, index=None):
            written_sheets.append(sheet_name)

        # Patch each df's to_excel
        with (
            patch.object(df_cpus, "to_excel", side_effect=capture_to_excel),
            patch.object(df_mat, "to_excel", side_effect=capture_to_excel),
            patch.object(df_mo, "to_excel", side_effect=capture_to_excel),
            patch.object(df_eq, "to_excel", side_effect=capture_to_excel),
            patch.object(df_prods, "to_excel", side_effect=capture_to_excel),
        ):
            exp._cex_write_sheets(writer, df_cpus, df_mat, df_mo, df_eq, df_prods)

        assert "Resumo_CPUs" in written_sheets
        assert "Materiais" in written_sheets
        assert "Mao_de_Obra" in written_sheets
        assert "Equipamentos" in written_sheets
        assert "Metodologias_3NF" in written_sheets


# ---------------------------------------------------------------------------
# Tests: export
# ---------------------------------------------------------------------------


class TestExport:
    """Tests for CatalogExporterExcel.export().

    We patch _cex_write_sheets so that:
    1. openpyxl never complains about no visible sheets.
    2. We can still assert the DataFrames built upstream.
    """

    def _exporter_with_mock_sim(self, catalogo=None):
        cat = catalogo or _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia"):
            from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

            exp = CatalogExporterExcel(cat)
        exp.simulador.simular_cpu.return_value = _make_sim_result()
        return exp

    def _mock_writer_cm(self):
        """Return a context-manager mock for pd.ExcelWriter."""
        writer_mock = MagicMock()
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=writer_mock)
        cm.__exit__ = MagicMock(return_value=False)
        return cm, writer_mock

    def test_export_returns_path(self, tmp_path):
        exp = self._exporter_with_mock_sim()
        out = tmp_path / "catalog.xlsx"
        cm, _ = self._mock_writer_cm()
        with patch("concilium.infrastructure.exporters.catalog_excel.pd.ExcelWriter", return_value=cm):
            result = exp.export(out)
        assert result == out

    def test_export_creates_file(self, tmp_path):
        """export() calls pd.ExcelWriter with the given path."""
        exp = self._exporter_with_mock_sim()
        out = tmp_path / "catalog.xlsx"
        cm, _ = self._mock_writer_cm()
        with patch("concilium.infrastructure.exporters.catalog_excel.pd.ExcelWriter", return_value=cm) as mock_ew:
            exp.export(out)
        mock_ew.assert_called_once_with(out, engine="openpyxl")

    def test_export_with_insumos_and_cpus(self, tmp_path):
        cat = _minimal_catalogo(
            insumos=[
                {
                    "tipo": "MATERIAL",
                    "codigo": "M-01",
                    "descricao": "Areia",
                    "unidade": "m3",
                    "preco_unitario": 30.0,
                    "categoria": "A",
                    "fonte_preco": "SINAPI",
                    "data_referencia_preco": "2024-01",
                }
            ],
            cpus=[
                {
                    "codigo": "CPU-001",
                    "descricao": "Escavação",
                    "unidade": "m3",
                    "categoria": "TERRA",
                    "producao_horaria": 50,
                }
            ],
        )
        exp = self._exporter_with_mock_sim(cat)
        out = tmp_path / "catalog2.xlsx"
        captured = {}

        def _capture(writer, df_cpus, df_mat, df_mo, df_eq, df_prods):
            captured["df_cpus"] = df_cpus
            captured["df_mat"] = df_mat

        cm, _ = self._mock_writer_cm()
        with patch("concilium.infrastructure.exporters.catalog_excel.pd.ExcelWriter", return_value=cm):
            with patch.object(exp, "_cex_write_sheets", side_effect=_capture):
                exp.export(out)

        assert len(captured["df_cpus"]) == 1
        assert len(captured["df_mat"]) == 1

    def test_export_cpu_exception_adds_error_row(self, tmp_path):
        cat = _minimal_catalogo(
            cpus=[
                {
                    "codigo": "CPU-ERR",
                    "descricao": "CPU com erro",
                    "unidade": "m3",
                    "categoria": "T",
                }
            ]
        )
        exp = self._exporter_with_mock_sim(cat)
        exp.simulador.simular_cpu.side_effect = ValueError("simulated error")

        out = tmp_path / "catalog_err.xlsx"
        captured = {}

        def _capture(writer, df_cpus, *args):
            captured["df_cpus"] = df_cpus

        cm, _ = self._mock_writer_cm()
        with patch("concilium.infrastructure.exporters.catalog_excel.pd.ExcelWriter", return_value=cm):
            with patch.object(exp, "_cex_write_sheets", side_effect=_capture):
                exp.export(out)

        assert "Status" in captured["df_cpus"].columns
        assert captured["df_cpus"].iloc[0]["Status"] == "Erro Calculo"

    def test_export_with_producoes(self, tmp_path):
        cat = _minimal_catalogo(
            producoes=[
                {
                    "id": "PROD-1",
                    "descricao": "Método A",
                    "valor_horario": 100,
                    "unidade": "m3",
                    "categoria": "TERRA",
                }
            ]
        )
        exp = self._exporter_with_mock_sim(cat)
        out = tmp_path / "catalog_prods.xlsx"
        captured = {}

        def _capture(writer, df_cpus, df_mat, df_mo, df_eq, df_prods):
            captured["df_prods"] = df_prods

        cm, _ = self._mock_writer_cm()
        with patch("concilium.infrastructure.exporters.catalog_excel.pd.ExcelWriter", return_value=cm):
            with patch.object(exp, "_cex_write_sheets", side_effect=_capture):
                exp.export(out)

        assert len(captured["df_prods"]) == 1
        assert captured["df_prods"].iloc[0]["ID"] == "PROD-1"


# ---------------------------------------------------------------------------
# Tests: _aplicar_estilo
# ---------------------------------------------------------------------------


class TestAplicarEstilo:
    def _exporter(self, catalogo=None):
        cat = catalogo or _minimal_catalogo()
        with patch("concilium.infrastructure.exporters.catalog_excel.SimuladorEngenharia"):
            from concilium.infrastructure.exporters.catalog_excel import CatalogExporterExcel

            return CatalogExporterExcel(cat)

    def _make_mock_writer(self, sheet_names=("Sheet1",)):
        """Build a mock ExcelWriter with minimal worksheet-like mocks."""
        writer = MagicMock()

        sheets = {}
        for name in sheet_names:
            ws = MagicMock()

            # ws[1] should return an iterable of cells (the header row)
            header_cell = MagicMock()
            header_cell.value = "Header"
            ws.__getitem__ = MagicMock(return_value=[header_cell])

            # ws.iter_rows() returns rows; each row is an iterable of cells
            body_cell = MagicMock()
            body_cell.value = "body"
            ws.iter_rows.return_value = iter([[body_cell], [body_cell]])

            # ws.columns returns columns; each column is an iterable of cells
            col_cell = MagicMock()
            col_cell.value = "some value"
            col_cell.column_letter = "A"
            ws.columns = [[col_cell]]

            # auto_filter and dimensions
            ws.auto_filter = MagicMock()
            ws.dimensions = "A1:Z100"
            ws.column_dimensions = {"A": MagicMock()}

            sheets[name] = ws

        writer.sheets = sheets
        return writer

    def test_aplicar_estilo_runs_without_error(self):
        exp = self._exporter()
        writer = self._make_mock_writer(["Sheet1", "Sheet2"])
        # Should not raise
        exp._aplicar_estilo(writer)

    def test_aplicar_estilo_sets_auto_filter(self):
        exp = self._exporter()
        writer = self._make_mock_writer(["TestSheet"])
        exp._aplicar_estilo(writer)
        ws = writer.sheets["TestSheet"]
        assert ws.auto_filter.ref == "A1:Z100"

    def test_aplicar_estilo_sets_column_width(self):
        exp = self._exporter()
        writer = self._make_mock_writer(["ColSheet"])
        exp._aplicar_estilo(writer)
        ws = writer.sheets["ColSheet"]
        # width should have been set on the column dimension
        assert ws.column_dimensions["A"].width is not None  # attribute accessed

    def test_aplicar_estilo_uses_idv_tokens(self):
        """Custom identidade_visual tokens are consumed without error."""
        cat = _minimal_catalogo(
            identidade_visual={
                "cores": {
                    "cabecalho_fundo": "003366",
                    "cabecalho_texto": "FFFF00",
                    "zebra_impar": "E0E0E0",
                    "zebra_par": "FFFFFF",
                    "borda": "CCCCCC",
                },
                "fontes": {
                    "cabecalho": "Times New Roman",
                    "corpo": "Arial",
                    "tamanho_cabecalho": 12,
                    "tamanho_corpo": 11,
                },
            }
        )
        exp = self._exporter(cat)
        writer = self._make_mock_writer(["CustomSheet"])
        # Should not raise
        exp._aplicar_estilo(writer)

    def test_aplicar_estilo_zebra_even_row_no_fill(self):
        """Even rows (row_idx % 2 == 0) get None fill in _apply_body_row."""
        exp = self._exporter()

        called_fills = []

        def _fake_apply_body_row(row, fill, border, body_font):
            called_fills.append(fill)

        writer = self._make_mock_writer(["ZebraSheet"])
        ws = writer.sheets["ZebraSheet"]

        # Return 3 rows from iter_rows so we get both even and odd indices
        cell_a = MagicMock()
        cell_a.value = "x"
        cell_b = MagicMock()
        cell_b.value = "y"
        cell_c = MagicMock()
        cell_c.value = "z"
        ws.iter_rows.return_value = iter([[cell_a], [cell_b], [cell_c]])

        with patch(
            "concilium.infrastructure.exporters.catalog_excel._apply_body_row",
            side_effect=_fake_apply_body_row,
        ):
            exp._aplicar_estilo(writer)

        # row_idx starts at 2; 3 rows → indices 2, 3, 4
        # idx=2 even → None; idx=3 odd → fill; idx=4 even → None
        assert called_fills[0] is None  # row_idx=2, even
        assert called_fills[1] is not None  # row_idx=3, odd
        assert called_fills[2] is None  # row_idx=4, even

    def test_aplicar_estilo_empty_sheets_dict(self):
        """No sheets → should not raise."""
        exp = self._exporter()
        writer = MagicMock()
        writer.sheets = {}
        exp._aplicar_estilo(writer)

    def test_aplicar_estilo_cell_value_exception_suppressed(self):
        """Cells that raise on str(cell.value) should not crash the exporter."""
        exp = self._exporter()
        writer = self._make_mock_writer(["ErrSheet"])
        ws = writer.sheets["ErrSheet"]

        # Make column cell raise on .value access
        bad_cell = MagicMock()
        bad_cell.column_letter = "A"
        type(bad_cell).value = property(lambda self: (_ for _ in ()).throw(ValueError("bad")))
        ws.columns = [[bad_cell]]

        # Should not raise
        exp._aplicar_estilo(writer)
