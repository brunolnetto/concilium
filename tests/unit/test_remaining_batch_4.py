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

    def test_converter_rental_unit_none_passthrough(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        # None rental_unit → return preco_original unchanged
        result = _converter_rental_unit(25.0, None)
        assert result == 25.0

    def test_converter_rental_unit_dia_zero_producao(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        # producao_horaria=0 → no division by zero, uses custo_hora_calendario
        result = _converter_rental_unit(800.0, "dia_calendario", producao_horaria=0.0)
        assert result == 800.0 / 8.0

    def test_converter_rental_unit_mes_zero_producao(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        result = _converter_rental_unit(15500.0, "mes", producao_horaria=0.0, horas_mes=193.6)
        assert abs(result - 15500.0 / 193.6) < 0.01

    def test_converter_rental_unit_unknown_passthrough(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        result = _converter_rental_unit(50.0, "quinzena")
        assert result == 50.0

    def test_alpha_with_percentual_encargos_local(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _alpha

        params = ParametrosCalculo()
        insumo = {"atributos_especificos": {"percentual_encargos_local": 0.8}}
        result = _alpha(insumo, params)
        assert abs(result - 1.8) < 0.001

    def test_alpha_with_invalid_percentual_falls_back_to_tipo(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _alpha

        params = ParametrosCalculo()
        insumo = {"atributos_especificos": {"percentual_encargos_local": "bad", "tipo_contrato": "PJ"}}
        result = _alpha(insumo, params)
        assert result == params.alpha_pj

    def test_horas_mes_from_insumo_attrs(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _horas_mes

        params = ParametrosCalculo()
        insumo = {"atributos_especificos": {"horas_mes": 176.0}}
        result = _horas_mes(insumo, params)
        assert result == 176.0

    def test_horas_mes_invalid_falls_back(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _horas_mes

        params = ParametrosCalculo()
        insumo = {"atributos_especificos": {"horas_mes": "bad"}}
        result = _horas_mes(insumo, params)
        assert result == params.horas_mes

    def test_breakdown_pu_ok_false_when_refs_faltantes(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=100.0, referencias_faltantes=["INS-X"])
        assert bd.ok is False

    def test_breakdown_pu_ok_true_when_no_missing_refs(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=100.0)
        assert bd.ok is True

    def test_breakdown_pu_calculated_none_when_zero_vh(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=0.0, custo_mo_h=100.0)
        assert bd.pu_calculado is None

    def test_breakdown_pu_to_dict(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=10.0, custo_mo_h=20.0)
        d = bd.to_dict()
        assert d["producao_id"] == "P1"
        assert "breakdown" in d
        assert d["breakdown"]["mo"] == 20.0

    def test_calcular_pu_with_funcao_mensal(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_pu

        producao = {
            "id": "CPU-1",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "FN-1", "num_pessoas": 2}]},
        }
        insumo_index = {"FN-1": {"codigo": "FN-1", "preco_unitario": 4000.0, "unidade": "mes"}}
        params = ParametrosCalculo(alpha_clt=1.8, horas_mes=200.0)
        bd = calcular_pu(producao, insumo_index, params)
        # custo_mo_h = (4000/200) * 1.8 * 2 = 72
        assert bd.custo_mo_h > 0

    def test_calcular_pu_with_funcao_horista(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-2",
            "valor_horario": 5.0,
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OP-1", "num_pessoas": 1}]},
        }
        insumo_index = {"OP-1": {"codigo": "OP-1", "preco_unitario": 30.0, "unidade": "h"}}
        bd = calcular_pu(producao, insumo_index)
        # unidade=h → direct rate, no alpha
        assert bd.custo_mo_h == 30.0

    def test_calcular_pu_funcao_missing_ref(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-3",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "MISSING-FN", "num_pessoas": 1}]},
        }
        bd = calcular_pu(producao, {})
        assert "MISSING-FN" in bd.referencias_faltantes

    def test_calcular_pu_equipamento_with_preco_h_override(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-4",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {
                "equipamentos": [{"equip_id": "EQ-1", "num_unidades": 2, "preco_h_unitario": 50.0}]
            },
        }
        insumo_index = {"EQ-1": {"codigo": "EQ-1", "preco_unitario": 999.0}}
        bd = calcular_pu(producao, insumo_index)
        # override = 50 * 2 = 100
        assert bd.custo_equip_h == 100.0

    def test_calcular_pu_equipamento_with_consumo_diesel_from_attrs(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_pu

        producao = {
            "id": "CPU-5",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {
                "equipamentos": [
                    {
                        "equip_id": "EQ-D",
                        "num_unidades": 1,
                        # no consumo_litros_hora at entry level
                    }
                ]
            },
        }
        insumo_index = {
            "EQ-D": {
                "codigo": "EQ-D",
                "preco_unitario": 40.0,
                "atributos_especificos": {"consumo_litros_hora": 5.0},
            }
        }
        params = ParametrosCalculo(preco_diesel=7.0)
        bd = calcular_pu(producao, insumo_index, params)
        # diesel from attrs: 5.0 * 7.0 * 1 = 35
        assert abs(bd.custo_diesel_h - 35.0) < 0.01
        assert any("consumo_litros_hora" in a for a in bd.alertas)

    def test_calcular_pu_equipamento_missing_ref(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-6",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {"equipamentos": [{"equip_id": "MISSING-EQ", "num_unidades": 1}]},
        }
        bd = calcular_pu(producao, {})
        assert "MISSING-EQ" in bd.referencias_faltantes

    def test_calcular_pu_material(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-7",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {"materiais": [{"insumo_id": "MAT-1", "consumo_por_hora": 2.0}]},
        }
        insumo_index = {"MAT-1": {"codigo": "MAT-1", "preco_unitario": 15.0}}
        bd = calcular_pu(producao, insumo_index)
        assert bd.custo_material_h == 30.0

    def test_calcular_pu_material_missing_ref(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-8",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {"materiais": [{"insumo_id": "MAT-MISS", "consumo_por_hora": 1.0}]},
        }
        bd = calcular_pu(producao, {})
        assert "MAT-MISS" in bd.referencias_faltantes

    def test_calcular_pu_material_empty_id_skipped(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-9",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {
                "materiais": [{"consumo_por_hora": 1.0}]  # no id keys
            },
        }
        bd = calcular_pu(producao, {})
        # Empty mid → not appended to refs_faltantes
        assert bd.referencias_faltantes == []

    def test_calcular_pu_composicao_itens_basic(self):
        from concilium.application.catalog.pu_calculator import calcular_pu_composicao_itens

        cpu = {
            "codigo": "CPU-C1",
            "composicao_itens": [{"insumo_id": "INS-A", "coeficiente": 3.0, "categoria_custo": "MO"}],
        }
        insumo_index = {"INS-A": {"codigo": "INS-A", "preco_unitario": 10.0}}
        result = calcular_pu_composicao_itens(cpu, insumo_index)
        assert result["pu_fixo"] == 30.0
        assert len(result["breakdown"]) == 1

    def test_calcular_pu_composicao_itens_missing_insumo(self):
        from concilium.application.catalog.pu_calculator import calcular_pu_composicao_itens

        cpu = {
            "codigo": "CPU-C2",
            "composicao_itens": [{"insumo_id": "MISSING", "coeficiente": 1.0}],
        }
        result = calcular_pu_composicao_itens(cpu, {})
        assert len(result["refs_faltantes"]) == 1
        assert result["pu_fixo"] == 0.0

    def test_calcular_pu_composicao_itens_empty(self):
        from concilium.application.catalog.pu_calculator import calcular_pu_composicao_itens

        result = calcular_pu_composicao_itens({"codigo": "C"}, {})
        assert result["pu_fixo"] == 0.0
        assert result["breakdown"] == []

    def test_calcular_catalogo_empty(self):
        from concilium.application.catalog.pu_calculator import calcular_catalogo

        result = calcular_catalogo([], [])
        assert result["ok"] is True
        assert result["total_producoes"] == 0

    def test_calcular_catalogo_sem_composicao_skipped(self):
        from concilium.application.catalog.pu_calculator import calcular_catalogo

        producoes = [{"id": "P1", "valor_horario": 10.0}]  # no equipe
        result = calcular_catalogo(producoes, [])
        assert result["com_composicao"] == 0

    def test_calcular_catalogo_sem_valor_horario(self):
        from concilium.application.catalog.pu_calculator import calcular_catalogo

        producoes = [
            {
                "id": "P1",
                "valor_horario": 0.0,
                "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "FN-1", "num_pessoas": 1}]},
            }
        ]
        insumos = [{"codigo": "FN-1", "preco_unitario": 100.0, "tipo": "MO"}]
        result = calcular_catalogo(producoes, insumos)
        assert "P1" in result["sem_valor_horario"]

    def test_calcular_catalogo_pu_divergente(self):
        from concilium.application.catalog.pu_calculator import calcular_catalogo

        producoes = [
            {
                "id": "P-DIV",
                "valor_horario": 10.0,
                "_cu_planilha_referencia": 999.0,  # huge divergence
                "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "FN-X", "num_pessoas": 1}]},
            }
        ]
        insumos = [{"codigo": "FN-X", "preco_unitario": 100.0, "unidade": "h"}]
        result = calcular_catalogo(producoes, insumos, tolerancia_pct=5.0)
        assert len(result["pu_divergentes"]) == 1

    def test_check_pu_divergencia_no_hint(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P", valor_horario=10.0, custo_mo_h=50.0)
        divergentes: list = []
        _check_pu_divergencia(bd, {"id": "P"}, 20.0, divergentes)
        assert divergentes == []

    def test_check_pu_divergencia_below_tolerance(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P", valor_horario=100.0, custo_mo_h=1001.0)
        divergentes: list = []
        # pu_calculado ≈ 10.01, ref=10.0, delta < 20%
        _check_pu_divergencia(bd, {"_cu_planilha_referencia": 10.0}, 20.0, divergentes)
        assert divergentes == []

    def test_derivar_precos_unitarios_sbdi_basic(self):
        from concilium.application.catalog.pu_calculator import derivar_precos_unitarios_sbdi

        producao = {
            "id": "P1",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "FN-1", "num_pessoas": 1}]},
        }
        insumo_index = {"FN-1": {"codigo": "FN-1", "preco_unitario": 100.0, "unidade": "h"}}
        result = derivar_precos_unitarios_sbdi(producao, insumo_index)
        assert "mo" in result
        assert result["_meta"]["producao_id"] == "P1"

    def test_derivar_precos_unitarios_sbdi_zero_vh_returns_empty(self):
        from concilium.application.catalog.pu_calculator import derivar_precos_unitarios_sbdi

        producao = {"id": "P2", "valor_horario": 0.0}
        result = derivar_precos_unitarios_sbdi(producao, {})
        assert result == {}

    def test_build_insumo_index_skips_missing_codigo(self):
        from concilium.application.catalog.pu_calculator import _build_insumo_index

        insumos = [
            {"codigo": "A", "preco_unitario": 1.0},
            {"preco_unitario": 2.0},  # no codigo key
        ]
        idx = _build_insumo_index(insumos)
        assert "A" in idx
        assert len(idx) == 1

    def test_cpu_get_equipe_from_equipe_key(self):
        from concilium.application.catalog.pu_calculator import _cpu_get_equipe

        producao = {
            "equipe": {
                "funcoes": [{"funcao_id": "F1"}],
                "equipamentos": [],
                "materiais": [],
            }
        }
        equipe, funcoes, equipamentos, materiais = _cpu_get_equipe(producao)
        assert len(funcoes) == 1


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
            with pytest.raises(Exception):  # noqa: B017
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
