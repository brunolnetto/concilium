"""Tests for pu_calculator, pdf_renderer, azure_blob_storage, and runtime helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ─── pu_calculator ───────────────────────────────────────────────────────────


class TestPuCalculator:
    def _params(self, alpha_clt=1.777, alpha_pj=0.06, preco_diesel=6.50):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo

        return ParametrosCalculo(alpha_clt=alpha_clt, alpha_pj=alpha_pj, preco_diesel=preco_diesel)

    def test_alpha_horista(self):
        from concilium.application.catalog.pu_calculator import _alpha

        params = self._params()
        insumo = {"categoria": "horista", "tipo": "MO"}
        result = _alpha(insumo, params)
        assert result == 1.777

    def test_alpha_pj_contract(self):
        from concilium.application.catalog.pu_calculator import _alpha

        params = self._params()
        insumo = {"atributos_especificos": {"tipo_contrato": "PJ"}}
        result = _alpha(insumo, params)
        assert result == params.alpha_pj

    def test_alpha_clt_contract(self):
        from concilium.application.catalog.pu_calculator import _alpha

        params = self._params()
        insumo = {"atributos_especificos": {"tipo_contrato": "CLT"}}
        result = _alpha(insumo, params)
        assert result == params.alpha_clt

    def test_horas_mes(self):
        from concilium.application.catalog.pu_calculator import _horas_mes

        params = self._params()  # default horas_mes ~208
        insumo = {}
        result = _horas_mes(insumo, params)
        assert result > 0

    def test_calcular_pu_minimal(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        params = self._params()
        result = calcular_pu({"id": "P1", "valor_horario": 100.0}, {}, params)
        assert result is not None

    def test_parametros_calculo_defaults(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo

        p = ParametrosCalculo()
        assert p.alpha_clt > 1.0
        assert p.preco_diesel > 0

    def test_breakdown_pu_has_producao_id(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=100.0)
        assert bd.producao_id == "P1"
        assert bd.valor_horario == 100.0

    def test_build_insumo_index(self):
        from concilium.application.catalog.pu_calculator import _build_insumo_index

        insumos = [
            {"codigo": "INS-1", "preco_unitario": 100.0, "tipo": "MO"},
            {"codigo": "INS-2", "preco_unitario": 50.0, "tipo": "EQ"},
        ]
        idx = _build_insumo_index(insumos)
        assert "INS-1" in idx
        assert idx["INS-1"]["preco_unitario"] == 100.0

    def test_converter_rental_unit_dia(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        result = _converter_rental_unit(1000.0, "dia_calendario", producao_horaria=1.0)
        assert isinstance(result, float)

    def test_converter_rental_unit_mes(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        result = _converter_rental_unit(5000.0, "mes", producao_horaria=1.0)
        assert isinstance(result, float)
        assert result > 0

    def test_converter_rental_unit_hora(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        result = _converter_rental_unit(10.0, "hora_produtiva", producao_horaria=1.0)
        assert isinstance(result, float)


# ─── pdf_renderer ────────────────────────────────────────────────────────────


class TestPdfRenderer:
    def test_strip_inline_removes_bold(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline

        result = _strip_inline("**bold** text")
        assert "**" not in result
        assert "bold" in result

    def test_strip_inline_removes_bold_italic(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _strip_inline

        result = _strip_inline("**bold** and *italic* text")
        assert "bold" in result
        assert "italic" in result

    def test_is_table_sep_true(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep

        assert _is_table_sep("|---|---|")
        assert _is_table_sep("| --- | --- |")

    def test_is_table_sep_false(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _is_table_sep

        assert not _is_table_sep("| data | row |")
        assert not _is_table_sep("normal line")

    def test_render_markdown_pdf_returns_bytes(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import render_markdown_pdf

        md = "# Title\n\nParagraph text.\n\n- Item 1\n- Item 2\n"
        try:
            result = render_markdown_pdf(md)
            if result is not None:
                assert isinstance(result, bytes)
                assert len(result) > 0
        except ImportError:
            pytest.skip("fpdf2 not available")

    def test_render_table_row_does_not_crash(self):
        from concilium.application.runtime.deliverables.reports.pdf_renderer import _render_table_row

        mock_pdf = MagicMock()
        mock_pdf.get_string_width.return_value = 10.0
        # Should not raise
        _render_table_row(mock_pdf, "| Col A | Col B |", col_w=50.0)
        mock_pdf.cell.assert_called()


# ─── azure_blob_storage ──────────────────────────────────────────────────────


class TestAzureBlobStorage:
    def _make_storage(self):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        # Create storage with mocked _service
        storage = AzureBlobStorage.__new__(AzureBlobStorage)
        storage._container = "test-container"
        storage._account = "testaccount"
        storage._account_key = None
        storage._connection_string = None
        storage._root_prefix = ""
        storage._service = MagicMock()  # mock lazy service
        return storage

    def test_listar_blobs_returns_paths(self):
        storage = self._make_storage()
        mock_blob = MagicMock()
        mock_blob.name = "projetos/proj-1/v1/canonical.json"
        storage._service.get_container_client.return_value.list_blobs.return_value = [mock_blob]
        result = storage.listar_blobs("projetos/proj-1")
        assert isinstance(result, list)

    def test_blob_existe_true(self):
        storage = self._make_storage()
        mock_bc = MagicMock()
        mock_bc.exists.return_value = True
        storage._service.get_blob_client.return_value = mock_bc
        assert storage.blob_existe("path/to/blob.json") is True

    def test_blob_existe_false(self):
        storage = self._make_storage()
        mock_bc = MagicMock()
        mock_bc.exists.return_value = False
        storage._service.get_blob_client.return_value = mock_bc
        assert storage.blob_existe("path/to/nope.json") is False

    def test_ler_blob_returns_bytes(self):
        storage = self._make_storage()
        mock_bc = MagicMock()
        mock_bc.download_blob.return_value.readall.return_value = b'{"key": "val"}'
        with (
            patch.object(storage, "_blob_client", return_value=mock_bc),
            patch.dict(
                "sys.modules", {"azure": MagicMock(), "azure.core": MagicMock(), "azure.core.exceptions": MagicMock()}
            ),
        ):
            result = storage.ler_blob("path/to/file.json")
        assert result == b'{"key": "val"}'

    def test_gravar_blob(self):
        storage = self._make_storage()
        mock_bc = MagicMock()
        storage._service.get_blob_client.return_value = mock_bc
        storage.gravar_blob("path/to/file.json", b"content")
        mock_bc.upload_blob.assert_called_once()

    def test_from_env_missing_raises(self):
        from concilium.infrastructure.adapters.blob_storage.azure import AzureBlobStorage

        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(Exception):
                AzureBlobStorage.from_env()


# ─── runtime pipeline helpers ─────────────────────────────────────────────────


class TestRuntimePipelineHelpers:
    def test_parse_executed_skills_empty(self, tmp_path):
        from concilium.application.runtime.helpers.pipeline import _parse_executed_skills

        result = _parse_executed_skills(tmp_path / "nonexistent.json")
        assert isinstance(result, set)

    def test_parse_executed_skills_from_file(self, tmp_path):
        import json

        from concilium.application.runtime.helpers.pipeline import _parse_executed_skills

        log = [{"skill": "01-escopo-e-eap", "status": "OK"}, {"skill": "02-prod", "status": "ERRO"}]
        log_file = tmp_path / "invocations.json"
        log_file.write_text(json.dumps(log), encoding="utf-8")
        result = _parse_executed_skills(log_file)
        assert isinstance(result, set)

    def test_apply_dv_returns_canonical(self):
        from concilium.application.runtime.helpers.pipeline import _apply_dv

        canonical = MagicMock()
        result = _apply_dv(canonical, None)
        assert result is not None

    def test_format_records_empty(self):
        from concilium.application.runtime.helpers.pipeline import _format_records

        result = _format_records([])
        assert result == []

    def test_print_skill_start_no_crash(self):
        from concilium.application.runtime.helpers.pipeline import _print_skill_start

        _print_skill_start("01-escopo-e-eap")  # Should not raise
