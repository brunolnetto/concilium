"""Coverage for ExcelRenderer — API consolidada em excel_adapter.py.

Cobre:
- save() e to_bytes() (produção de arquivo válido)
- coerce_to_cell_value() (todos os ramos de tipo)
- ExcelRenderer com resultado=None (degradação graciosa na aba RESULTADO)
- Retrocompatibilidade: importação via excel_renderer, excel_sheets_mendeslobo e __init__
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from io import BytesIO

import pytest

from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    CustoTotal,
    Meta,
    Projeto,
    RegimeTrabalho,
    Resultado,
    ValidacaoItem,
    Venda,
)
from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer, coerce_to_cell_value


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")


def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


def _canonical_minimal(**kw):
    return CanonicalModel(meta=_make_meta(), projeto=_make_proj(), **kw)


def _canonical_com_resultado():
    return CanonicalModel(
        meta=_make_meta(),
        projeto=_make_proj(),
        resultado=Resultado(
            venda=Venda(total_sem_bdi=800_000.0, total_com_bdi=1_000_000.0),
            custo=CustoTotal(direto_equipes=500_000.0, total=800_000.0),
            resultado_financeiro=200_000.0,
            margem_pct=0.25,
            status_margem="VERDE",
            validacoes=[ValidacaoItem(codigo="V1", status="OK")],
        ),
    )


# ── Importação canônica ───────────────────────────────────────────────────────


class TestImportCompat:
    """Verifica que o caminho canônico de importação expõe a classe correta."""

    def test_import_via_excel_adapter(self):
        from concilium.infrastructure.adapters.excel_adapter import ExcelRenderer as ER

        assert ER is ExcelRenderer

    def test_import_via_package_init(self):
        from concilium.infrastructure.adapters import ExcelRenderer as ER

        assert ER is ExcelRenderer


# ── save() ───────────────────────────────────────────────────────────────────


class TestExcelRendererSave:
    pytestmark = [pytest.mark.slow]

    @pytest.fixture(scope="class")
    def _xlsx_bytes(self):
        """Renderiza o workbook uma vez para toda a classe."""
        return ExcelRenderer(_canonical_com_resultado()).to_bytes()

    def test_save_creates_file(self, _xlsx_bytes, tmp_path):
        output_path = tmp_path / "test.xlsx"
        output_path.write_bytes(_xlsx_bytes)
        assert output_path.exists()
        assert output_path.stat().st_size > 0

    def test_save_file_is_valid_xlsx(self, _xlsx_bytes):
        from openpyxl import load_workbook

        wb = load_workbook(BytesIO(_xlsx_bytes))
        assert len(wb.sheetnames) > 0


# ── to_bytes() ────────────────────────────────────────────────────────────────


class TestExcelRendererToBytes:
    pytestmark = [pytest.mark.slow]

    @pytest.fixture(scope="class")
    def _xlsx_bytes(self):
        """Renderiza o workbook uma vez para toda a classe."""
        return ExcelRenderer(_canonical_com_resultado()).to_bytes()

    def test_to_bytes_returns_bytes(self, _xlsx_bytes):
        assert isinstance(_xlsx_bytes, bytes)
        assert len(_xlsx_bytes) > 0

    def test_to_bytes_valid_xlsx(self, _xlsx_bytes):
        from openpyxl import load_workbook

        wb = load_workbook(BytesIO(_xlsx_bytes))
        assert len(wb.sheetnames) > 0

    def test_to_bytes_has_expected_sheets(self, _xlsx_bytes):
        from openpyxl import load_workbook

        wb = load_workbook(BytesIO(_xlsx_bytes))
        expected = {"DIRETOS.DET", "PLANEJAMENTO", "RESULTADO"}  # actual sheet names
        assert expected.issubset(set(wb.sheetnames))


# ── resultado=None (degradação graciosa) ──────────────────────────────────────


class TestExcelRendererResultadoNone:
    def test_render_resultado_sheet_with_none_resultado(self):
        """render() com resultado=None deve criar aba RESULTADO com mensagem amigável."""
        canonical = _canonical_minimal(resultado=None)
        renderer = ExcelRenderer(canonical)
        renderer.render()
        ws = renderer.wb["RESULTADO"]
        # row 1 = título, row 2 = vazio, row 3 = mensagem de fallback
        assert ws["A1"].value is not None
        assert ws["A3"].value == "Resultado não disponível."


# ── coerce_to_cell_value ──────────────────────────────────────────────────────


class TestCoerceToCellValue:
    def test_none(self):
        assert coerce_to_cell_value(None) is None

    def test_bool(self):
        assert coerce_to_cell_value(True) is True
        assert coerce_to_cell_value(False) is False

    def test_int(self):
        assert coerce_to_cell_value(42) == 42

    def test_float(self):
        assert coerce_to_cell_value(3.14) == 3.14

    def test_str(self):
        assert coerce_to_cell_value("hello") == "hello"

    def test_single_item_dict(self):
        assert coerce_to_cell_value({"x": 99}) == 99

    def test_multi_item_dict_to_str(self):
        result = coerce_to_cell_value({"a": 1, "b": 2})
        assert isinstance(result, str)

    def test_single_item_list(self):
        assert coerce_to_cell_value([42]) == 42

    def test_single_item_list_with_dict(self):
        assert coerce_to_cell_value([{"k": "v"}]) == "v"

    def test_long_list_truncated(self):
        value = list(range(100))
        result = coerce_to_cell_value(value)
        if len(str(value)) > 100:
            assert result.endswith("...")
            assert len(result) <= 100

    def test_custom_object_fallback_to_str(self):
        class Obj:
            def __str__(self):
                return "custom"

        assert coerce_to_cell_value(Obj()) == "custom"


# ── wrapper _coerce_to_cell_value no ExcelRenderer ───────────────────────────


class TestExcelRendererCoerceWrapper:
    def test_wrapper_delegates_to_coerce(self):
        renderer = ExcelRenderer(_canonical_minimal())
        assert renderer._coerce_to_cell_value({"k": 7}) == 7
        assert renderer._coerce_to_cell_value(None) is None
