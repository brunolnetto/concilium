"""
Tests for price_trend.py — ADR-041 §D5 (Skill 20).

Covers calcular_tendencia and internal helpers to push coverage from ~32% toward 80%+.
"""

from __future__ import annotations

from datetime import date

import pytest

from concilium.application.catalog.price_trend import (
    IndiceCategoria,
    RelatorioTendencia,
    TendenciaInsumo,
    _mediana,
    calcular_tendencia,
)


# ── _mediana helper ────────────────────────────────────────────────────────────


class TestMediana:
    def test_empty_returns_none(self):
        assert _mediana([]) is None

    def test_single_element(self):
        assert _mediana([7.0]) == 7.0

    def test_odd_length(self):
        # sorted: [1, 3, 5] → middle index 1 → 3
        assert _mediana([5.0, 1.0, 3.0]) == 3.0

    def test_even_length(self):
        # sorted: [1, 3, 5, 7] → (3 + 5) / 2 = 4.0
        assert _mediana([7.0, 1.0, 3.0, 5.0]) == 4.0

    def test_two_elements(self):
        assert _mediana([2.0, 4.0]) == 3.0

    def test_negative_values(self):
        assert _mediana([-10.0, 0.0, 10.0]) == 0.0


# ── calcular_tendencia: empty insumos ──────────────────────────────────────────


class TestCalcularTendenciaEmpty:
    def test_returns_relatorio_tendencia_instance(self):
        result = calcular_tendencia([])
        assert isinstance(result, RelatorioTendencia)

    def test_indices_por_categoria_is_empty(self):
        result = calcular_tendencia([])
        assert result.indices_por_categoria == []

    def test_resumo_total_insumos_zero(self):
        result = calcular_tendencia([])
        assert result.resumo["total_insumos"] == 0

    def test_resumo_total_com_historico_zero(self):
        result = calcular_tendencia([])
        assert result.resumo["total_com_historico"] == 0

    def test_resumo_total_com_sicro_regional_zero(self):
        result = calcular_tendencia([])
        assert result.resumo["total_com_sicro_regional"] == 0

    def test_resumo_indices_is_empty_dict(self):
        result = calcular_tendencia([])
        assert result.resumo["indices"] == {}


# ── data_base and contexto_id propagation ─────────────────────────────────────


class TestPropagation:
    def test_data_base_propagates_to_data_base_analise(self):
        ref_date = date(2024, 1, 15)
        result = calcular_tendencia([], data_base=ref_date)
        assert result.data_base_analise == "2024-01-15"

    def test_contexto_id_propagates(self):
        result = calcular_tendencia([], contexto_id="CTX-42")
        assert result.contexto_id == "CTX-42"

    def test_default_contexto_id(self):
        result = calcular_tendencia([])
        assert result.contexto_id == "?"

    def test_jurisdicao_id_propagates(self):
        result = calcular_tendencia([], jurisdicao_id="RJ")
        assert result.jurisdicao_id == "RJ"

    def test_no_jurisdicao_id_is_none(self):
        result = calcular_tendencia([])
        assert result.jurisdicao_id is None

    def test_gerado_em_is_string(self):
        result = calcular_tendencia([])
        # Should be a date string like "2026-06-14"
        assert isinstance(result.gerado_em, str)
        assert len(result.gerado_em) == 10


# ── insumo with preco_unitario and no historico_precos ─────────────────────────


class TestInsumoSemHistorico:
    def _make_insumo(self):
        return {
            "codigo": "INS-001",
            "descricao": "Areia fina",
            "tipo": "MATERIAL",
            "unidade": "m3",
            "preco_unitario": 50.0,
        }

    def test_tendencia_created(self):
        result = calcular_tendencia([self._make_insumo()])
        assert len(result.indices_por_categoria) == 1
        cat = result.indices_por_categoria[0]
        assert len(cat.insumos) == 1

    def test_variacao_pct_is_none_without_historico(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.variacao_pct is None

    def test_variacao_abs_is_none_without_historico(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.variacao_abs is None

    def test_fonte_atual_is_preco_unitario(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.fonte_atual == "preco_unitario"

    def test_preco_atual_matches(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.preco_atual == 50.0

    def test_n_registros_historico_zero(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.n_registros_historico == 0


# ── insumo with historico_precos computes variation correctly ──────────────────


class TestInsumoComHistorico:
    def _make_insumo(self):
        return {
            "codigo": "INS-002",
            "descricao": "Brita n1",
            "tipo": "MATERIAL",
            "unidade": "m3",
            "preco_unitario": 110.0,
            "historico_precos": [
                {"data_inicio_vigencia": "2022-01-01", "preco_unitario": 100.0},
                {"data_inicio_vigencia": "2023-06-01", "preco_unitario": 105.0},
            ],
        }

    def test_variacao_abs_correct(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        # preco_atual=110, preco_ref=100 (oldest)
        assert ins.variacao_abs == pytest.approx(10.0, abs=1e-3)

    def test_variacao_pct_correct(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        # (110 - 100) / 100 * 100 = 10%
        assert ins.variacao_pct == pytest.approx(10.0, abs=0.01)

    def test_preco_referencia_is_oldest(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.preco_referencia == 100.0

    def test_n_registros_historico_correct(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.n_registros_historico == 2

    def test_resumo_total_com_historico(self):
        result = calcular_tendencia([self._make_insumo()])
        assert result.resumo["total_com_historico"] == 1

    def test_fonte_atual_without_jurisdicao(self):
        result = calcular_tendencia([self._make_insumo()])
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.fonte_atual == "preco_unitario"


# ── jurisdicao_id path: regionalizacao as dict ────────────────────────────────


class TestJurisdicaoDict:
    def _make_insumo(self):
        return {
            "codigo": "INS-003",
            "descricao": "Cimento CP-II",
            "tipo": "MATERIAL",
            "unidade": "kg",
            "preco_unitario": 0.80,
            "regionalizacao": {
                "RJ": {"preco": 1.20},
                "SP": {"preco": 1.10},
            },
        }

    def test_fonte_atual_is_sicro_regional(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="RJ")
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.fonte_atual == "SICRO_REGIONAL"

    def test_preco_atual_from_regionalizacao(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="RJ")
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.preco_atual == pytest.approx(1.20)

    def test_total_com_sicro_regional_in_resumo(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="RJ")
        assert result.resumo["total_com_sicro_regional"] == 1

    def test_different_jurisdicao_picks_correct_price(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="SP")
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.preco_atual == pytest.approx(1.10)

    def test_unknown_jurisdicao_falls_back_to_preco_unitario(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="MG")
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.fonte_atual == "preco_unitario"
        assert ins.preco_atual == pytest.approx(0.80)


# ── jurisdicao_id path: regionalizacao as list ────────────────────────────────


class TestJurisdicaoList:
    def _make_insumo(self):
        return {
            "codigo": "INS-004",
            "descricao": "Cal virgem",
            "tipo": "MATERIAL",
            "unidade": "kg",
            "preco_unitario": 0.50,
            "regionalizacao": [
                {"jurisdicao_id": "RJ", "preco": 0.70},
                {"jurisdicao_id": "SP", "preco": 0.65},
            ],
        }

    def test_fonte_atual_is_sicro_regional(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="RJ")
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.fonte_atual == "SICRO_REGIONAL"

    def test_preco_atual_from_list_regionalizacao(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="RJ")
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.preco_atual == pytest.approx(0.70)

    def test_total_com_sicro_regional_in_resumo(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="RJ")
        assert result.resumo["total_com_sicro_regional"] == 1

    def test_sp_picks_correct_price(self):
        result = calcular_tendencia([self._make_insumo()], jurisdicao_id="SP")
        ins = result.indices_por_categoria[0].insumos[0]
        assert ins.preco_atual == pytest.approx(0.65)


# ── insumo with preco_unitario=0 is excluded ──────────────────────────────────


class TestInsumoExcluido:
    def test_zero_preco_unitario_excluded(self):
        insumo = {
            "codigo": "INS-ZERO",
            "descricao": "Insumo sem preco",
            "tipo": "MATERIAL",
            "unidade": "un",
            "preco_unitario": 0,
        }
        result = calcular_tendencia([insumo])
        assert result.indices_por_categoria == []

    def test_none_preco_unitario_excluded(self):
        insumo = {
            "codigo": "INS-NONE",
            "descricao": "Insumo sem preco",
            "tipo": "MATERIAL",
            "unidade": "un",
        }
        result = calcular_tendencia([insumo])
        assert result.indices_por_categoria == []

    def test_excluded_insumo_not_in_resumo_total(self):
        # total_insumos counts the raw list, not the filtered one
        insumo = {
            "codigo": "INS-ZERO2",
            "tipo": "MATERIAL",
            "preco_unitario": 0,
        }
        result = calcular_tendencia([insumo])
        assert result.resumo["total_insumos"] == 1


# ── multiple insumos of different tipos ───────────────────────────────────────


class TestMultiplosTipos:
    def _make_insumos(self):
        return [
            {
                "codigo": "M-001",
                "descricao": "Areia",
                "tipo": "MATERIAL",
                "unidade": "m3",
                "preco_unitario": 60.0,
            },
            {
                "codigo": "E-001",
                "descricao": "Escavadeira",
                "tipo": "EQUIPAMENTO",
                "unidade": "h",
                "preco_unitario": 300.0,
            },
            {
                "codigo": "M-002",
                "descricao": "Brita",
                "tipo": "MATERIAL",
                "unidade": "m3",
                "preco_unitario": 80.0,
            },
            {
                "codigo": "S-001",
                "descricao": "Pedreiro",
                "tipo": "MAO_DE_OBRA",
                "unidade": "h",
                "preco_unitario": 25.0,
            },
        ]

    def test_one_indice_per_tipo(self):
        result = calcular_tendencia(self._make_insumos())
        tipos = [idx.tipo for idx in result.indices_por_categoria]
        assert len(tipos) == len(set(tipos))
        assert set(tipos) == {"MATERIAL", "EQUIPAMENTO", "MAO_DE_OBRA"}

    def test_indices_sorted_alphabetically(self):
        result = calcular_tendencia(self._make_insumos())
        tipos = [idx.tipo for idx in result.indices_por_categoria]
        assert tipos == sorted(tipos)

    def test_material_category_has_two_insumos(self):
        result = calcular_tendencia(self._make_insumos())
        material_idx = next(
            i for i in result.indices_por_categoria if i.tipo == "MATERIAL"
        )
        assert material_idx.n_insumos_total == 2

    def test_resumo_total_insumos(self):
        result = calcular_tendencia(self._make_insumos())
        assert result.resumo["total_insumos"] == 4


# ── IndiceCategoria statistics ────────────────────────────────────────────────


class TestIndiceCategoriaStatistics:
    """Three insumos in MATERIAL, with known variacao_pct values: 10%, 20%, 30%."""

    def _make_insumos(self):
        return [
            {
                "codigo": "M-A",
                "tipo": "MATERIAL",
                "unidade": "m3",
                "preco_unitario": 110.0,
                "historico_precos": [
                    {"data_inicio_vigencia": "2022-01-01", "preco_unitario": 100.0}
                ],
            },
            {
                "codigo": "M-B",
                "tipo": "MATERIAL",
                "unidade": "m3",
                "preco_unitario": 120.0,
                "historico_precos": [
                    {"data_inicio_vigencia": "2022-01-01", "preco_unitario": 100.0}
                ],
            },
            {
                "codigo": "M-C",
                "tipo": "MATERIAL",
                "unidade": "m3",
                "preco_unitario": 130.0,
                "historico_precos": [
                    {"data_inicio_vigencia": "2022-01-01", "preco_unitario": 100.0}
                ],
            },
        ]

    def _cat(self):
        result = calcular_tendencia(self._make_insumos())
        return result.indices_por_categoria[0]

    def test_variacao_media_pct(self):
        # (10 + 20 + 30) / 3 = 20.0
        assert self._cat().variacao_media_pct == pytest.approx(20.0, abs=0.01)

    def test_variacao_mediana_pct(self):
        # sorted [10, 20, 30] → middle = 20
        assert self._cat().variacao_mediana_pct == pytest.approx(20.0, abs=0.01)

    def test_variacao_max_pct(self):
        assert self._cat().variacao_max_pct == pytest.approx(30.0, abs=0.01)

    def test_variacao_min_pct(self):
        assert self._cat().variacao_min_pct == pytest.approx(10.0, abs=0.01)

    def test_n_insumos_total(self):
        assert self._cat().n_insumos_total == 3

    def test_n_insumos_com_historico(self):
        assert self._cat().n_insumos_com_historico == 3

    def test_insumos_sorted_by_variacao_desc(self):
        cat = self._cat()
        variacoes = [ins.variacao_pct for ins in cat.insumos]
        assert variacoes == sorted(variacoes, reverse=True)


# ── IndiceCategoria with no historico — statistics are None ───────────────────


class TestIndiceCategoriaNoHistorico:
    def _make_insumos(self):
        return [
            {
                "codigo": "X-001",
                "tipo": "SERVICO",
                "unidade": "m2",
                "preco_unitario": 50.0,
            }
        ]

    def test_variacao_media_pct_none(self):
        result = calcular_tendencia(self._make_insumos())
        cat = result.indices_por_categoria[0]
        assert cat.variacao_media_pct is None

    def test_variacao_mediana_pct_none(self):
        result = calcular_tendencia(self._make_insumos())
        cat = result.indices_por_categoria[0]
        assert cat.variacao_mediana_pct is None

    def test_variacao_max_pct_none(self):
        result = calcular_tendencia(self._make_insumos())
        cat = result.indices_por_categoria[0]
        assert cat.variacao_max_pct is None

    def test_variacao_min_pct_none(self):
        result = calcular_tendencia(self._make_insumos())
        cat = result.indices_por_categoria[0]
        assert cat.variacao_min_pct is None


# ── resumo keys correctness ───────────────────────────────────────────────────


class TestResumoKeys:
    def test_all_keys_present(self):
        result = calcular_tendencia([])
        assert "total_insumos" in result.resumo
        assert "total_com_historico" in result.resumo
        assert "total_com_sicro_regional" in result.resumo
        assert "indices" in result.resumo

    def test_indices_in_resumo_maps_tipo(self):
        insumo = {
            "codigo": "R-001",
            "tipo": "MATERIAL",
            "unidade": "m3",
            "preco_unitario": 50.0,
        }
        result = calcular_tendencia([insumo])
        assert "MATERIAL" in result.resumo["indices"]

    def test_indices_resumo_nested_keys(self):
        insumo = {
            "codigo": "R-002",
            "tipo": "MATERIAL",
            "unidade": "m3",
            "preco_unitario": 50.0,
        }
        result = calcular_tendencia([insumo])
        entry = result.resumo["indices"]["MATERIAL"]
        assert "variacao_media_pct" in entry
        assert "variacao_mediana_pct" in entry
        assert "n_com_historico" in entry
        assert "n_total" in entry

    def test_total_com_sicro_regional_zero_when_no_jurisdicao(self):
        insumo = {
            "codigo": "R-003",
            "tipo": "MATERIAL",
            "unidade": "m3",
            "preco_unitario": 50.0,
            "regionalizacao": {"RJ": {"preco": 60.0}},
        }
        result = calcular_tendencia([insumo])
        assert result.resumo["total_com_sicro_regional"] == 0


# ── SICRO price zero falls back to preco_unitario ────────────────────────────


class TestSICROFallback:
    def test_sicro_price_zero_falls_back(self):
        insumo = {
            "codigo": "SZ-001",
            "tipo": "MATERIAL",
            "unidade": "m3",
            "preco_unitario": 80.0,
            "regionalizacao": {"RJ": {"preco": 0}},
        }
        result = calcular_tendencia([insumo], jurisdicao_id="RJ")
        ins = result.indices_por_categoria[0].insumos[0]
        # zero SICRO price falls back to preco_unitario
        assert ins.fonte_atual == "preco_unitario"
        assert ins.preco_atual == pytest.approx(80.0)
