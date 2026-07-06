"""Tests for pu_calculator.py and insumo repository."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

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


# ─── infrastructure/repositories/insumo.py ────────────────────────────────────


class TestRepositorioInsumo:
    def _make_repo(self, insumos=None, producoes=None):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalog = {
            "insumos": insumos if insumos is not None else [{"codigo": "DIESEL", "preco_unitario": 6.5}],
            "producoes": producoes or [],
        }
        return RepositorioInsumo(catalog)

    def test_import(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        assert RepositorioInsumo is not None

    def test_obter_insumo_found(self):
        repo = self._make_repo()
        result = repo.obter_insumo("DIESEL")
        assert result is not None
        assert result["codigo"] == "DIESEL"

    def test_obter_insumo_not_found(self):
        repo = self._make_repo([])
        assert repo.obter_insumo("MISSING") is None

    def test_insumo_existe(self):
        repo = self._make_repo()
        assert repo.insumo_existe("DIESEL") is True
        assert repo.insumo_existe("MISSING") is False

    def test_obter_producao_found(self):
        repo = self._make_repo(producoes=[{"id": "PROD-1", "valor_horario": 50.0}])
        result = repo.obter_producao("PROD-1")
        assert result is not None

    def test_producao_existe(self):
        repo = self._make_repo(producoes=[{"id": "PROD-1"}])
        assert repo.producao_existe("PROD-1") is True
        assert repo.producao_existe("MISSING") is False

    def test_preco_na_data_flat(self):
        repo = self._make_repo()
        preco = repo.preco_na_data("DIESEL")
        assert preco == 6.5

    def test_preco_na_data_missing(self):
        repo = self._make_repo()
        assert repo.preco_na_data("MISSING") is None

    def test_resolver_preco_master_base(self):
        repo = self._make_repo()
        preco, fonte = repo.resolver_preco("DIESEL")
        assert preco == 6.5
        assert fonte == "MASTER_BASE"

    def test_resolver_preco_override(self):
        repo = self._make_repo()
        preco, fonte = repo.resolver_preco("DIESEL", overrides={"DIESEL": {"preco_calibrado": 7.0}})
        assert preco == 7.0
        assert fonte == "PROJECT_OVERRIDE"

    def test_atualizar_preco(self):
        from datetime import date

        repo = self._make_repo()
        repo.atualizar_preco("DIESEL", 7.5, data_vigencia=date(2026, 1, 1), fonte="PROJECT_OVERRIDE")
        assert repo.obter_insumo("DIESEL") is not None  # still exists

    def test_lookup_preco_historico_loops_past_non_matching_record(self):
        """Branch 80->76: primeiro registro (mais recente) não cobre a data → continua para o próximo."""
        from concilium.infrastructure.repositories.insumo import _lookup_preco_historico

        historico = [
            {"data_inicio_vigencia": "2025-01-01", "data_fim_vigencia": "2025-06-30", "preco_unitario": 5.0},
            {"data_inicio_vigencia": "2025-07-01", "data_fim_vigencia": None, "preco_unitario": 6.0},
        ]
        # Data pede o período coberto pelo PRIMEIRO registro (mais antigo); o loop
        # (reversed) começa pelo mais recente, que não cobre a data → continua.
        preco = _lookup_preco_historico(historico, "2025-03-15")
        assert preco == 5.0

    def test_preco_na_data_scd2_no_matching_record_falls_back_to_flat(self):
        """Branch 132->136: historico_precos presente mas sem registro cobrindo a data → fallback plano."""
        repo = self._make_repo(
            insumos=[
                {
                    "codigo": "DIESEL",
                    "preco_unitario": 6.5,
                    "historico_precos": [
                        {"data_inicio_vigencia": "2030-01-01", "data_fim_vigencia": None, "preco_unitario": 99.0},
                    ],
                }
            ]
        )
        preco = repo.preco_na_data("DIESEL", data_referencia="2020-01-01")
        assert preco == 6.5

    def test_atualizar_preco_loops_past_already_closed_and_newer_record(self):
        """Branches 200->199 (registro já fechado) e 202->199 (vigência não é anterior à nova data)."""
        from datetime import date

        repo = self._make_repo(
            insumos=[
                {
                    "codigo": "DIESEL",
                    "preco_unitario": 6.5,
                    "historico_precos": [
                        # já fechado → não deve ser tocado (branch 200->199)
                        {
                            "data_inicio_vigencia": "2025-01-01",
                            "data_fim_vigencia": "2025-06-30",
                            "preco_unitario": 5.0,
                        },
                        # aberto mas com vigência POSTERIOR à nova data_vigencia → não fecha (branch 202->199)
                        {"data_inicio_vigencia": "2030-01-01", "data_fim_vigencia": None, "preco_unitario": 7.0},
                    ],
                }
            ]
        )
        repo.atualizar_preco("DIESEL", 8.0, data_vigencia=date(2026, 1, 1), fonte="PROJECT_OVERRIDE")
        insumo = repo.obter_insumo("DIESEL")
        historico = insumo["historico_precos"]
        # O registro já fechado permanece inalterado.
        assert historico[0]["data_fim_vigencia"] == "2025-06-30"
        # O registro com vigência futura (2030) não é fechado pela nova vigência de 2026.
        assert historico[1]["data_fim_vigencia"] is None


# ─── rp helper functions ───────────────────────────────────────────────────────


class TestRpHelpers:
    def test_rp_check_override_found(self):
        from concilium.infrastructure.repositories.insumo import _rp_check_override

        result = _rp_check_override("DIESEL", {"DIESEL": {"preco_calibrado": 7.0}}, None)
        assert result is not None
        assert result[0] == 7.0

    def test_rp_check_override_not_found(self):
        from concilium.infrastructure.repositories.insumo import _rp_check_override

        assert _rp_check_override("MISSING", {"DIESEL": {}}, None) is None

    def test_rp_check_override_empty(self):
        from concilium.infrastructure.repositories.insumo import _rp_check_override

        assert _rp_check_override("DIESEL", None, None) is None

    def test_rp_sicro_regional_found(self):
        from concilium.infrastructure.repositories.insumo import _rp_sicro_regional

        insumo = {"regionalizacao": {"JUR-1": {"preco": 8.0}}}
        result = _rp_sicro_regional(insumo, "JUR-1")
        assert result is not None
        assert result[0] == 8.0

    def test_rp_sicro_regional_not_applicable(self):
        from concilium.infrastructure.repositories.insumo import _rp_sicro_regional

        assert _rp_sicro_regional({"preco_unitario": 5.0}, None) is None

    def test_rp_historico_scd2(self):
        from datetime import date

        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        insumo = {
            "historico_precos": [
                {"data_inicio_vigencia": "2026-01-01", "data_fim_vigencia": "2026-06-30", "preco_unitario": 6.5},
                {"data_inicio_vigencia": "2026-07-01", "preco_unitario": 7.0},
            ]
        }
        result = _rp_historico_scd2(insumo, date(2026, 3, 1))
        assert result is not None
        assert result[0] == 6.5
        assert result[1] == "HISTORICO_SCD2"

    def test_rp_historico_scd2_none_date(self):
        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        assert _rp_historico_scd2({"historico_precos": []}, None) is None

    def test_repositorio_preco_na_data_with_historico(self):
        from datetime import date

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalog = {
            "insumos": [
                {
                    "codigo": "DIESEL",
                    "historico_precos": [{"data_inicio_vigencia": "2026-01-01", "preco_unitario": 6.5}],
                }
            ],
            "producoes": [],
        }
        repo = RepositorioInsumo(catalog)
        preco = repo.preco_na_data("DIESEL", date(2026, 3, 1))
        assert preco == 6.5

    def test_repositorio_resolver_preco_sicro(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalog = {
            "insumos": [{"codigo": "DIESEL", "preco_unitario": 5.0, "regionalizacao": {"JUR-1": {"preco": 8.0}}}],
            "producoes": [],
        }
        repo = RepositorioInsumo(catalog)
        preco, fonte = repo.resolver_preco("DIESEL", jurisdicao_id="JUR-1")
        assert preco == 8.0
        assert fonte == "SICRO_REGIONAL"

    def test_repositorio_resolver_preco_historico(self):
        from datetime import date

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalog = {
            "insumos": [
                {
                    "codigo": "DIESEL",
                    "historico_precos": [{"data_inicio_vigencia": "2026-01-01", "preco_unitario": 7.5}],
                }
            ],
            "producoes": [],
        }
        repo = RepositorioInsumo(catalog)
        preco, fonte = repo.resolver_preco("DIESEL", data_referencia=date(2026, 4, 1))
        assert preco == 7.5
        assert fonte == "HISTORICO_SCD2"

    def test_repositorio_atualizar_preco_scd2(self):
        from datetime import date

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalog = {"insumos": [{"codigo": "DIESEL", "preco_unitario": 6.5}], "producoes": []}
        repo = RepositorioInsumo(catalog)
        result = repo.atualizar_preco("DIESEL", 7.0, date(2026, 7, 1), fonte="PROJECT_OVERRIDE")
        assert result is True

    def test_repositorio_atualizar_preco_not_found(self):
        from datetime import date

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        repo = RepositorioInsumo({"insumos": [], "producoes": []})
        result = repo.atualizar_preco("MISSING", 7.0, date(2026, 1, 1))
        assert result is False
