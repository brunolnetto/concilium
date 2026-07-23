"""Coverage sweep 3 — files with 20-35 lines missing."""

from __future__ import annotations

# ─── infrastructure/repositories/insumo.py ────────────────────────────────────


class TestRepositorioInsumo:
    def _make_repo(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {
            "insumos": [
                {"codigo": "INS-1", "tipo": "MO", "preco_unitario": 100.0, "historico_precos": []},
                {"codigo": "INS-2", "tipo": "EQ", "preco_unitario": 500.0},
            ]
        }
        return RepositorioInsumo(catalogo)

    def test_obter_insumo_found(self):
        repo = self._make_repo()
        result = repo.obter_insumo("INS-1")
        assert result is not None

    def test_obter_insumo_missing_returns_none(self):
        repo = self._make_repo()
        result = repo.obter_insumo("MISSING")
        assert result is None

    def test_insumo_existe(self):
        repo = self._make_repo()
        assert repo.insumo_existe("INS-1") is True
        assert repo.insumo_existe("MISSING") is False

    def test_lookup_preco_historico_empty(self):
        from concilium.infrastructure.repositories.insumo import _lookup_preco_historico

        result = _lookup_preco_historico([], "2026-01-01")
        assert result is None

    def test_resolver_preco_returns_preco(self):
        repo = self._make_repo()
        result = repo.resolver_preco("INS-1", None)
        assert result is not None

    def test_rp_historico_scd2_no_historico(self):
        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        insumo = {"codigo": "INS-1", "preco_unitario": 100.0}
        result = _rp_historico_scd2(insumo, None)
        assert result is None

    # ── New coverage: standalone helper functions ──────────────────────────

    def test_rp_check_override_direct_key(self):
        from concilium.infrastructure.repositories.insumo import _rp_check_override

        overrides = {"INS-1": {"preco_calibrado": 250.0}}
        result = _rp_check_override("INS-1", overrides, None)
        assert result is not None
        preco, fonte = result
        assert preco == 250.0
        assert fonte == "PROJECT_OVERRIDE"

    def test_rp_check_override_composite_key(self):
        from concilium.infrastructure.repositories.insumo import _rp_check_override

        overrides = {"INS-1::SP": {"preco": 300.0}}
        result = _rp_check_override("INS-1", overrides, "SP")
        assert result is not None
        preco, fonte = result
        assert preco == 300.0

    def test_rp_check_override_no_overrides(self):
        from concilium.infrastructure.repositories.insumo import _rp_check_override

        result = _rp_check_override("INS-1", None, None)
        assert result is None

    def test_rp_check_override_missing_key(self):
        from concilium.infrastructure.repositories.insumo import _rp_check_override

        result = _rp_check_override("MISSING", {"OTHER": {"preco_calibrado": 10.0}}, None)
        assert result is None

    def test_rp_sicro_regional_dict_form(self):
        from concilium.infrastructure.repositories.insumo import _rp_sicro_regional

        insumo = {
            "codigo": "INS-1",
            "regionalizacao": {"SP": {"preco": 180.0}},
        }
        result = _rp_sicro_regional(insumo, "SP")
        assert result is not None
        preco, fonte = result
        assert preco == 180.0
        assert fonte == "SICRO_REGIONAL"

    def test_rp_sicro_regional_list_form(self):
        from concilium.infrastructure.repositories.insumo import _rp_sicro_regional

        insumo = {
            "codigo": "INS-1",
            "regionalizacao": [{"jurisdicao_id": "RJ", "preco": 200.0}],
        }
        result = _rp_sicro_regional(insumo, "RJ")
        assert result is not None
        assert result[0] == 200.0

    def test_rp_sicro_regional_no_jurisdicao(self):
        from concilium.infrastructure.repositories.insumo import _rp_sicro_regional

        insumo = {"codigo": "INS-1", "regionalizacao": {"SP": {"preco": 150.0}}}
        result = _rp_sicro_regional(insumo, None)
        assert result is None

    def test_rp_sicro_regional_missing_jurisdicao(self):
        from concilium.infrastructure.repositories.insumo import _rp_sicro_regional

        insumo = {"codigo": "INS-1", "regionalizacao": {"SP": {"preco": 150.0}}}
        result = _rp_sicro_regional(insumo, "MG")
        assert result is None

    def test_rp_historico_scd2_found(self):
        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        insumo = {
            "historico_precos": [
                {
                    "data_inicio_vigencia": "2026-01-01",
                    "data_fim_vigencia": None,
                    "preco_unitario": 120.0,
                }
            ]
        }
        result = _rp_historico_scd2(insumo, "2026-03-15")
        assert result is not None
        assert result[0] == 120.0
        assert result[1] == "HISTORICO_SCD2"

    def test_rp_historico_scd2_out_of_range(self):
        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        insumo = {
            "historico_precos": [
                {
                    "data_inicio_vigencia": "2026-06-01",
                    "data_fim_vigencia": "2026-06-30",
                    "preco_unitario": 99.0,
                }
            ]
        }
        result = _rp_historico_scd2(insumo, "2025-01-01")
        assert result is None

    def test_lookup_preco_historico_found(self):
        from concilium.infrastructure.repositories.insumo import _lookup_preco_historico

        historico = [
            {
                "data_inicio_vigencia": "2026-01-01",
                "data_fim_vigencia": None,
                "preco_unitario": 77.0,
            }
        ]
        result = _lookup_preco_historico(historico, "2026-05-01")
        assert result == 77.0

    # ── New coverage: RepositorioInsumo public methods ─────────────────────

    def test_producao_existe_true(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"producoes": [{"id": "CPU-1", "descricao": "Escavacao"}]}
        repo = RepositorioInsumo(catalogo)
        assert repo.producao_existe("CPU-1") is True

    def test_producao_existe_false(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        repo = RepositorioInsumo({})
        assert repo.producao_existe("MISSING") is False

    def test_obter_producao_found(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"producoes": [{"id": "CPU-1", "valor_horario": 10.0}]}
        repo = RepositorioInsumo(catalogo)
        result = repo.obter_producao("CPU-1")
        assert result is not None
        assert result["valor_horario"] == 10.0

    def test_obter_producao_missing(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        repo = RepositorioInsumo({})
        assert repo.obter_producao("MISSING") is None

    def test_preco_na_data_flat_fallback(self):
        repo = self._make_repo()
        result = repo.preco_na_data("INS-2")
        assert result == 500.0

    def test_preco_na_data_missing_returns_none(self):
        repo = self._make_repo()
        result = repo.preco_na_data("MISSING")
        assert result is None

    def test_preco_na_data_with_historico(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {
            "insumos": [
                {
                    "codigo": "INS-H",
                    "preco_unitario": 50.0,
                    "historico_precos": [
                        {
                            "data_inicio_vigencia": "2026-01-01",
                            "data_fim_vigencia": None,
                            "preco_unitario": 88.0,
                        }
                    ],
                }
            ]
        }
        repo = RepositorioInsumo(catalogo)
        result = repo.preco_na_data("INS-H", "2026-04-01")
        assert result == 88.0

    def test_resolver_preco_with_override(self):
        repo = self._make_repo()
        overrides = {"INS-1": {"preco_calibrado": 999.0}}
        preco, fonte = repo.resolver_preco("INS-1", overrides=overrides)
        assert preco == 999.0
        assert fonte == "PROJECT_OVERRIDE"

    def test_resolver_preco_sicro_regional(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {
            "insumos": [
                {
                    "codigo": "INS-R",
                    "preco_unitario": 100.0,
                    "regionalizacao": {"SP": {"preco": 130.0}},
                }
            ]
        }
        repo = RepositorioInsumo(catalogo)
        preco, fonte = repo.resolver_preco("INS-R", jurisdicao_id="SP")
        assert preco == 130.0
        assert fonte == "SICRO_REGIONAL"

    def test_resolver_preco_historico_scd2(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {
            "insumos": [
                {
                    "codigo": "INS-SCD",
                    "preco_unitario": 50.0,
                    "historico_precos": [
                        {
                            "data_inicio_vigencia": "2026-01-01",
                            "data_fim_vigencia": None,
                            "preco_unitario": 75.0,
                        }
                    ],
                }
            ]
        }
        repo = RepositorioInsumo(catalogo)
        from datetime import date

        preco, fonte = repo.resolver_preco("INS-SCD", data_referencia=date(2026, 4, 1))
        assert preco == 75.0
        assert fonte == "HISTORICO_SCD2"

    def test_resolver_preco_missing_insumo(self):
        repo = self._make_repo()
        preco, fonte = repo.resolver_preco("MISSING")
        assert preco == 0.0
        assert fonte == "MASTER_BASE"

    def test_atualizar_preco_creates_historico(self):
        from datetime import date

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": [{"codigo": "INS-U", "preco_unitario": 100.0}]}
        repo = RepositorioInsumo(catalogo)
        result = repo.atualizar_preco("INS-U", 150.0, date(2026, 6, 1))
        assert result is True
        insumo = repo.obter_insumo("INS-U")
        assert insumo["preco_unitario"] == 150.0
        assert len(insumo["historico_precos"]) == 1

    def test_atualizar_preco_closes_open_record(self):
        from datetime import date

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {
            "insumos": [
                {
                    "codigo": "INS-V",
                    "preco_unitario": 100.0,
                    "historico_precos": [
                        {
                            "data_inicio_vigencia": "2026-01-01",
                            "data_fim_vigencia": None,
                            "preco_unitario": 100.0,
                        }
                    ],
                }
            ]
        }
        repo = RepositorioInsumo(catalogo)
        result = repo.atualizar_preco("INS-V", 200.0, date(2026, 6, 1))
        assert result is True
        insumo = repo.obter_insumo("INS-V")
        # Old record should now be closed
        old = insumo["historico_precos"][0]
        assert old["data_fim_vigencia"] is not None

    def test_atualizar_preco_missing_returns_false(self):
        from datetime import date

        repo = self._make_repo()
        result = repo.atualizar_preco("MISSING", 999.0, date(2026, 1, 1))
        assert result is False

    def test_funcao_existe_true(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": [{"codigo": "FN-1", "tipo": "MAO_OBRA", "preco_unitario": 80.0}]}
        repo = RepositorioInsumo(catalogo)
        assert repo.funcao_existe("FN-1") is True

    def test_funcao_existe_false(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": [{"codigo": "EQ-1", "tipo": "EQUIPAMENTO", "preco_unitario": 500.0}]}
        repo = RepositorioInsumo(catalogo)
        assert repo.funcao_existe("EQ-1") is False

    def test_equipamento_existe_true(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {"insumos": [{"codigo": "EQ-2", "tipo": "EQUIPAMENTO", "preco_unitario": 600.0}]}
        repo = RepositorioInsumo(catalogo)
        assert repo.equipamento_existe("EQ-2") is True

    def test_equipamento_existe_false_missing(self):
        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        repo = RepositorioInsumo({})
        assert repo.equipamento_existe("MISSING") is False






# insumo.py line 45: _rp_sicro_regional with regz not dict nor list → reg = None
# ---------------------------------------------------------------------------


class TestInsumoRpSicroRegionalElse:
    def test_regz_not_dict_nor_list_returns_none(self):
        """Line 45: regz is a string (not dict/list) → reg = None → return None."""
        from concilium.infrastructure.repositories.insumo import _rp_sicro_regional

        insumo = {"regionalizacao": "unexpected_string"}
        result = _rp_sicro_regional(insumo, "SP")
        assert result is None


# ---------------------------------------------------------------------------


# insumo.py lines 68-69: _rp_historico_scd2 with bad date → except
# ---------------------------------------------------------------------------


class TestInsumoRpHistoricoScd2BadDate:
    def test_invalid_date_in_historico_passes(self):
        """Lines 68-69: ValueError from date.fromisoformat → except → return None."""
        from concilium.infrastructure.repositories.insumo import _rp_historico_scd2

        insumo = {"historico_precos_scd2": [{"data_inicio_vigencia": "NOT_A_DATE", "preco_unitario": 100.0}]}
        from datetime import date

        result = _rp_historico_scd2(insumo, date(2024, 1, 1))
        assert result is None


# ---------------------------------------------------------------------------


# insumo.py lines 82-83: _lookup_preco_historico with bad date → except
# ---------------------------------------------------------------------------


class TestInsumoLookupPrecoHistoricoBadDate:
    def test_invalid_date_raises_and_returns_none(self):
        """Lines 82-83: ValueError from date.fromisoformat → except → return None."""
        from concilium.infrastructure.repositories.insumo import _lookup_preco_historico

        historico = [{"data_inicio_vigencia": "INVALID", "preco_unitario": 50.0}]
        result = _lookup_preco_historico(historico, "2024-01-01")
        assert result is None


# ---------------------------------------------------------------------------


# insumo.py lines 126-127: resolve_preco_referencia with bad InsumoVersionado → except
# ---------------------------------------------------------------------------


class TestInsumoVersionadoValidateFails:
    def test_bad_versoes_block_falls_through(self):
        """Lines 126-127: InsumoVersionado.model_validate raises → except Exception → pass."""
        from unittest.mock import patch

        from concilium.infrastructure.repositories.insumo import RepositorioInsumo

        catalogo = {
            "insumos": [
                {
                    "codigo": "MO-01",
                    "preco_unitario": 50.0,
                    "versoes": [{"periodo": "2024-01", "preco_unitario": 50.0}],
                }
            ]
        }
        repo = RepositorioInsumo(catalogo)
        from datetime import date

        from concilium.domain.models.catalog.versioned import InsumoVersionado

        with patch.object(InsumoVersionado, "model_validate", side_effect=ValueError("bad")):
            result = repo.preco_na_data("MO-01", date(2024, 1, 1))
        assert result is not None  # falls through to preco direto


# ---------------------------------------------------------------------------

