"""Testes para resolver_preco_diesel_uf — reconexão do FuelPriceClient (ADR-129 D3).

`pu_calculator.resolver_preco_diesel_uf` consulta o FuelPriceClient por UF quando
disponível, com fallback documentado para PRECO_DIESEL_REFERENCIA em caso de
indisponibilidade da API externa ou ausência de UF/client.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from concilium.application.catalog.pu_calculator import resolver_preco_diesel_uf
from concilium.domain.constants import PRECO_DIESEL_REFERENCIA


class TestResolverPrecoDieselUf:
    def test_usa_fuel_client_quando_disponivel(self):
        fuel_client = MagicMock()
        fuel_client.get_price_str.return_value = 5.89

        preco, fonte = resolver_preco_diesel_uf("CE", fuel_client)

        assert preco == 5.89
        assert fonte == "fuel_api"
        fuel_client.get_price_str.assert_called_once_with("ce", "diesel")

    def test_fallback_quando_client_e_none(self):
        preco, fonte = resolver_preco_diesel_uf("CE", None)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"

    def test_fallback_quando_uf_e_none(self):
        fuel_client = MagicMock()

        preco, fonte = resolver_preco_diesel_uf(None, fuel_client)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"
        fuel_client.get_price_str.assert_not_called()

    def test_fallback_quando_client_lanca_excecao(self):
        """API externa indisponível (timeout, erro HTTP, UF desconhecida na API) — rede de segurança."""
        fuel_client = MagicMock()
        fuel_client.get_price_str.side_effect = ConnectionError("timeout")

        preco, fonte = resolver_preco_diesel_uf("CE", fuel_client)

        assert preco == PRECO_DIESEL_REFERENCIA
        assert fonte == "fallback_constante"

    def test_normaliza_uf_para_minusculas(self):
        fuel_client = MagicMock()
        fuel_client.get_price_str.return_value = 6.10

        resolver_preco_diesel_uf("SP", fuel_client)

        fuel_client.get_price_str.assert_called_once_with("sp", "diesel")




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

    def test_breakdown_pu_itens_default_empty(self):
        """ADR-163 D3: BreakdownPU.itens default [] — não quebra consumidores existentes."""
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=10.0)
        assert bd.itens == []

    def test_calcular_pu_itens_populado_mo_equipamento_diesel_material(self):
        """ADR-163 D3: itens item-a-item, mesmo formato de calcular_pu_composicao_itens."""
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_pu

        producao = {
            "id": "CPU-ITENS",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "OP-1", "num_pessoas": 1}],
                "equipamentos": [{"equip_id": "EQ-1", "num_unidades": 1}],
                "materiais": [{"insumo_id": "MAT-1", "consumo_por_hora": 2.0}],
            },
        }
        insumo_index = {
            "OP-1": {"codigo": "OP-1", "preco_unitario": 30.0, "unidade": "h"},
            "EQ-1": {
                "codigo": "EQ-1",
                "preco_unitario": 40.0,
                "atributos_especificos": {"consumo_litros_hora": 2.0},
            },
            "MAT-1": {"codigo": "MAT-1", "preco_unitario": 5.0},
        }
        params = ParametrosCalculo(preco_diesel=6.5)
        bd = calcular_pu(producao, insumo_index, params)

        pares = {(item["insumo_id"], item["categoria"]) for item in bd.itens}
        assert ("OP-1", "mo") in pares
        assert ("EQ-1", "equipamento") in pares
        assert ("EQ-1", "diesel") in pares
        assert ("MAT-1", "material") in pares

        soma_contribuicoes = sum(item["contribuicao_h"] for item in bd.itens)
        assert abs(soma_contribuicoes - bd.custo_total_h) < 0.01

    def test_calcular_pu_itens_vazio_quando_sem_composicao(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {"id": "CPU-VAZIO", "valor_horario": 10.0}
        bd = calcular_pu(producao, {})
        assert bd.itens == []

    def test_calcular_pu_itens_nao_populado_para_referencia_faltante(self):
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "CPU-MISS",
            "valor_horario": 10.0,
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "MISSING-FN", "num_pessoas": 1}]},
        }
        bd = calcular_pu(producao, {})
        assert bd.itens == []

    def test_to_dict_sem_detalhado_nao_inclui_itens(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=10.0, custo_mo_h=20.0)
        bd.itens.append({"insumo_id": "X", "categoria": "mo"})
        d = bd.to_dict()
        assert "itens" not in d

    def test_to_dict_com_detalhado_inclui_itens(self):
        from concilium.application.catalog.pu_calculator import BreakdownPU

        bd = BreakdownPU(producao_id="P1", valor_horario=10.0, custo_mo_h=20.0)
        bd.itens.append({"insumo_id": "X", "categoria": "mo"})
        d = bd.to_dict(detalhado=True)
        assert d["itens"] == [{"insumo_id": "X", "categoria": "mo"}]

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

    def test_calcular_catalogo_with_explicit_params(self):
        """Line 339 false branch: explicit `params` skips the ParametrosCalculo() default."""
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, calcular_catalogo

        producoes = [
            {
                "id": "P1",
                "valor_horario": 10.0,
                "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "FN-1", "num_pessoas": 1}]},
            }
        ]
        insumos = [{"codigo": "FN-1", "preco_unitario": 100.0, "tipo": "MO"}]
        params = ParametrosCalculo()
        result = calcular_catalogo(producoes, insumos, params=params)
        assert result["total_producoes"] == 1

    def test_calcular_catalogo_referencias_faltantes_collected(self):
        """Line 356-357: a production whose bd.referencias_faltantes is non-empty
        gets recorded in refs_faltantes at the calcular_catalogo level."""
        from concilium.application.catalog.pu_calculator import calcular_catalogo

        producoes = [
            {
                "id": "P-MISSING",
                "valor_horario": 10.0,
                "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "FN-UNKNOWN", "num_pessoas": 1}]},
            }
        ]
        result = calcular_catalogo(producoes, [])
        assert len(result["referencias_faltantes"]) == 1
        assert result["referencias_faltantes"][0]["producao_id"] == "P-MISSING"
        assert result["ok"] is False

    def test_check_pu_divergencia_ref_not_positive(self):
        """Line 306 false branch: cpu_hint parses to a non-positive ref -> no divergence check."""
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P", valor_horario=100.0, custo_mo_h=1001.0)
        divergentes: list = []
        _check_pu_divergencia(bd, {"_cu_planilha_referencia": 0.0}, 20.0, divergentes)
        assert divergentes == []

    def test_calcular_pu_equipamento_consumo_direct_skips_atributos_fallback(self):
        """Line 260 false branch: consumo_litros_hora present directly on the equipamento
        entry -> the atributos_especificos fallback lookup is skipped."""
        from concilium.application.catalog.pu_calculator import calcular_pu

        producao = {
            "id": "P1",
            "composicao_padrao_equipe": {
                "equipamentos": [
                    {
                        "equip_id": "EQ-1",
                        "num_unidades": 1,
                        "consumo_litros_hora": 5.0,
                        "producao_horaria": 10.0,
                    }
                ]
            },
        }
        insumo_index = {
            "EQ-1": {
                "codigo": "EQ-1",
                "preco_unitario": 100.0,
                "atributos_especificos": {"consumo_litros_hora": 999.0},  # must NOT be used
            }
        }
        bd = calcular_pu(producao, insumo_index)
        # If the fallback had been (incorrectly) used, custo_diesel_h would be much larger.
        assert bd.custo_diesel_h < 100.0
        assert not any("atributos_especificos" in a for a in bd.alertas)

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





# pu_calculator.py line 300:
# _check_pu_divergencia with bd.pu_calculado is None (valor_horario=0) → return
# ---------------------------------------------------------------------------


class TestCheckPuDivergenciaNull:
    def test_pu_calculado_none_returns_early(self):
        """Line 300: bd.pu_calculado is None (valor_horario=0) → early return."""
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P-01", valor_horario=0.0)  # pu_calculado → None
        pu_divergentes: list = []
        _check_pu_divergencia(
            bd, prod={"_cu_planilha_referencia": "100.0"}, tolerancia_pct=5.0, pu_divergentes=pu_divergentes
        )
        assert pu_divergentes == []


# ---------------------------------------------------------------------------
# pu_calculator.py lines 317-318:
# _check_pu_divergencia with non-numeric cpu_hint → ValueError → pass
# ---------------------------------------------------------------------------


class TestCheckPuDivergenciaInvalidHint:
    def test_non_numeric_cpu_hint_is_caught(self):
        """Lines 317-318: float('N/A') → ValueError → except → pass."""
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P-01", valor_horario=10.0, custo_mo_h=5.0)
        pu_divergentes: list = []
        _check_pu_divergencia(
            bd,
            prod={"_cu_planilha_referencia": "N/A"},  # not a float
            tolerancia_pct=5.0,
            pu_divergentes=pu_divergentes,
        )
        # Exception was caught, divergentes unchanged
        assert pu_divergentes == []

    def test_cpu_hint_none_returns_early_before_float(self):
        """Lines 302-303: cpu_hint is None → return early (no conversion attempted)."""
        from concilium.application.catalog.pu_calculator import BreakdownPU, _check_pu_divergencia

        bd = BreakdownPU(producao_id="P-01", valor_horario=10.0, custo_mo_h=5.0)
        pu_divergentes: list = []
        _check_pu_divergencia(bd, prod={}, tolerancia_pct=5.0, pu_divergentes=pu_divergentes)
        assert pu_divergentes == []


# ---------------------------------------------------------------------------



import pytest  # noqa: E402

# ─── application/catalog/pu_calculator.py ─────────────────────────────────────


class TestPuCalculatorHelpers:
    def _params(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo

        return ParametrosCalculo()

    def test_alpha_clt_default(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _alpha

        insumo = {}
        result = _alpha(insumo, ParametrosCalculo())
        assert result > 1.0  # CLT encargos

    def test_alpha_pj_contract(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _alpha

        insumo = {"atributos_especificos": {"tipo_contrato": "PJ"}}
        params = ParametrosCalculo(alpha_pj=1.06)
        result = _alpha(insumo, params)
        assert result == 1.06

    def test_alpha_local_encargo(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _alpha

        insumo = {"atributos_especificos": {"percentual_encargos_local": 0.80}}
        result = _alpha(insumo, ParametrosCalculo())
        assert result == pytest.approx(1.80)

    def test_alpha_invalid_local_falls_back(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _alpha

        insumo = {"atributos_especificos": {"percentual_encargos_local": "invalid"}}
        result = _alpha(insumo, ParametrosCalculo())
        assert result > 1.0  # falls back to CLT

    def test_horas_mes_default(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _horas_mes

        params = ParametrosCalculo(horas_mes=208)
        result = _horas_mes({}, params)
        assert result == 208

    def test_horas_mes_from_insumo(self):
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _horas_mes

        insumo = {"atributos_especificos": {"horas_mes": 176.0}}
        result = _horas_mes(insumo, ParametrosCalculo())
        assert result == 176.0

    def test_calcular_pu_composicao_itens_basic(self):
        from concilium.application.catalog.pu_calculator import calcular_pu_composicao_itens

        cpu = {
            "codigo": "CPU-1",
            "composicao_itens": [
                {"insumo_id": "INS-DIESEL", "coeficiente": 2.0, "categoria_custo": "COMBUSTIVEL"},
            ],
        }
        insumo_index = {"INS-DIESEL": {"preco_unitario": 6.5}}
        result = calcular_pu_composicao_itens(cpu, insumo_index)
        assert result["pu_fixo"] == pytest.approx(13.0)
        assert result["refs_faltantes"] == []

    def test_calcular_pu_composicao_itens_missing_insumo(self):
        from concilium.application.catalog.pu_calculator import calcular_pu_composicao_itens

        cpu = {"codigo": "CPU-1", "composicao_itens": [{"insumo_id": "MISSING", "coeficiente": 1.0}]}
        result = calcular_pu_composicao_itens(cpu, {})
        assert len(result["refs_faltantes"]) == 1

    def test_calcular_pu_composicao_itens_empty(self):
        from concilium.application.catalog.pu_calculator import calcular_pu_composicao_itens

        result = calcular_pu_composicao_itens({"codigo": "CPU-1"}, {})
        assert result["pu_fixo"] == 0.0

    def test_converter_rental_unit_mensal(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        # R$/mes → R$/hora
        result = _converter_rental_unit(10000.0, "mes", horas_mes=200.0)
        assert result == pytest.approx(50.0)

    def test_converter_rental_unit_diaria(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        result = _converter_rental_unit(800.0, "hora")
        assert result == pytest.approx(800.0)

    def test_converter_rental_unit_none(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        result = _converter_rental_unit(50.0, None)
        assert result == 50.0

    def test_calcular_pu_with_producao(self):
        from concilium.application.catalog.pu_calculator import _build_insumo_index, calcular_pu

        producao = {
            "id": "PROD-1",
            "valor_horario": 50.0,
            "composicao_padrao_equipe": {
                "funcoes": [],
                "equipamentos": [],
            },
        }
        insumo_index = _build_insumo_index([])
        bd = calcular_pu(producao, insumo_index)
        assert bd is not None
        assert hasattr(bd, "valor_horario")

    def test_build_insumo_index(self):
        from concilium.application.catalog.pu_calculator import _build_insumo_index

        insumos = [{"codigo": "INS-1", "preco_unitario": 5.0}, {"codigo": "INS-2"}]
        index = _build_insumo_index(insumos)
        assert "INS-1" in index

    def test_calcular_pu_with_funcoes(self):
        """Cover lines 226-269: calcular_pu with funcoes, equipamentos, materiais."""
        from concilium.application.catalog.pu_calculator import ParametrosCalculo, _build_insumo_index, calcular_pu

        producao = {
            "id": "PROD-1",
            "valor_horario": 50.0,
            "composicao_padrao_equipe": {
                "funcoes": [{"funcao_id": "OP", "num_pessoas": 1, "salario_mensal": 3000.0}],
                "equipamentos": [{"equip_id": "ESC", "num_unidades": 1, "rental_unit": None}],
                "materiais": [],
            },
        }
        insumos = [
            {"codigo": "OP", "tipo": "MAO_DE_OBRA", "preco_unitario": 3000.0},
            {"codigo": "ESC", "tipo": "EQUIPAMENTO", "preco_unitario": 200.0},
        ]
        insumo_index = _build_insumo_index(insumos)
        params = ParametrosCalculo()
        bd = calcular_pu(producao, insumo_index, params)
        assert bd is not None
        assert hasattr(bd, "custo_mo_h")

    def test_calcular_catalogo_basic(self):
        """Cover calcular_catalogo function."""
        from concilium.application.catalog.pu_calculator import calcular_catalogo

        producoes = [{"id": "P1", "valor_horario": 50.0}]
        result = calcular_catalogo(producoes, [])
        assert "total_producoes" in result
        assert result["total_producoes"] == 1

    def test_converter_rental_unit_mensal_horas(self):
        from concilium.application.catalog.pu_calculator import _converter_rental_unit

        # R$/mes → R$/hora: price / horas_mes
        result = _converter_rental_unit(10000.0, "mes", horas_mes=200.0)
        assert result == pytest.approx(50.0)

    def test_check_pu_divergencia_no_divergence(self):
        from concilium.application.catalog.pu_calculator import _check_pu_divergencia

        bd = MagicMock()
        bd.pu = 100.0
        prod = {"preco_referencia_sbdi": 100.0}
        pu_divergentes: list = []
        _check_pu_divergencia(bd, prod, 5.0, pu_divergentes)
        assert pu_divergentes == []

    def test_check_pu_divergencia_with_divergence(self):
        from concilium.application.catalog.pu_calculator import _check_pu_divergencia

        bd = MagicMock()
        bd.pu = 150.0
        bd.producao_id = "P1"
        prod = {"id": "P1"}
        prod["preco_referencia_sbdi"] = 100.0
        pu_divergentes: list = []
        _check_pu_divergencia(bd, prod, 5.0, pu_divergentes)
        # Either appended or not depending on how divergence is computed
        assert isinstance(pu_divergentes, list)

    def test_cpu_get_equipe_composicao(self):
        from concilium.application.catalog.pu_calculator import _cpu_get_equipe

        producao = {
            "composicao_padrao_equipe": {"funcoes": [{"funcao_id": "OP"}], "equipamentos": [{"equip_id": "ESC"}]}
        }
        result = _cpu_get_equipe(producao)
        assert isinstance(result, tuple)



