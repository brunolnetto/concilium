"""Coverage batch 21 — price_trend, circular_deps small gaps."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# price_trend.py line 72: _parse_date returns None when s is falsy
# price_trend.py lines 75-76: _parse_date except path on invalid date string
# price_trend.py lines 91-92: _preco_historico_mais_antigo except on bad preco
# price_trend.py line 99: _preco_sicro_regional returns None when no regionalizacao
# price_trend.py line 105: _preco_sicro_regional returns None for unknown type
# ---------------------------------------------------------------------------


class TestParseDateEdgeCases:
    def test_returns_none_for_none_input(self):
        """Line 72: s is None → not s → return None."""
        from concilium.application.catalog.price_trend import _parse_date

        assert _parse_date(None) is None

    def test_returns_none_for_empty_string(self):
        """Line 72: s='' → not s → return None."""
        from concilium.application.catalog.price_trend import _parse_date

        assert _parse_date("") is None

    def test_returns_none_for_invalid_date_string(self):
        """Lines 75-76: date.fromisoformat raises ValueError → except → return None."""
        from concilium.application.catalog.price_trend import _parse_date

        assert _parse_date("not-a-date") is None

    def test_returns_date_for_valid_string(self):
        """Normal path: valid ISO date string → returns date object."""
        from datetime import date

        from concilium.application.catalog.price_trend import _parse_date

        result = _parse_date("2026-06-30")
        assert result == date(2026, 6, 30)


class TestPrecoHistoricoMaisAntigoException:
    def test_returns_none_tuple_when_preco_not_floatable(self):
        """Lines 91-92: float(dict_value) raises TypeError → except → return None, None."""
        from concilium.application.catalog.price_trend import _preco_historico_mais_antigo

        insumo = {
            "historico_precos": [
                {"preco_unitario": {"bad": "nested_dict"}, "data_inicio_vigencia": "2026-01-01"},
            ]
        }
        result = _preco_historico_mais_antigo(insumo)
        assert result == (None, None)


class TestPrecoSicroRegional:
    def test_returns_none_when_no_regionalizacao(self):
        """Line 99: regz is None/falsy → return None."""
        from concilium.application.catalog.price_trend import _preco_sicro_regional

        insumo = {"codigo": "MA-01"}  # no regionalizacao key
        assert _preco_sicro_regional(insumo, "SP") is None

    def test_returns_none_for_unknown_regz_type(self):
        """Line 105: regz is neither dict nor list → return None."""
        from concilium.application.catalog.price_trend import _preco_sicro_regional

        insumo = {"regionalizacao": "plain-string-value"}  # str → neither dict nor list
        assert _preco_sicro_regional(insumo, "SP") is None

    def test_returns_price_for_dict_regionalizacao(self):
        """Normal path: regz is dict → return float(preco)."""
        from concilium.application.catalog.price_trend import _preco_sicro_regional

        insumo = {"regionalizacao": {"SP": {"preco": 42.50}}}
        result = _preco_sicro_regional(insumo, "SP")
        assert result == 42.50


# ---------------------------------------------------------------------------
# circular_deps.py line 34->33: item.categoria_custo != "TERCEIRIZADO" → continue
# ---------------------------------------------------------------------------


class TestCircularDepsNonTerceirizadoItem:
    def test_branch_skips_non_terceirizado_items(self):
        """Line 34->33: composicao_itens with non-TERCEIRIZADO categoria → if False → continue."""
        from concilium.domain.validations.circular_deps import verificar_ciclos_cpu

        # cpu_referencia_id is set, but composicao_itens has non-TERCEIRIZADO items only
        catalogo = {
            "cpus": [
                {
                    "codigo": "CPU-A",
                    "cpu_referencia_id": "CPU-B",  # has ref_id → enters inner for loop
                    "composicao_itens": [
                        {"insumo_id": "MA-01", "categoria_custo": "MATERIAL"},  # not TERCEIRIZADO → skip
                        {"insumo_id": "MO-01", "categoria_custo": "MAO_OBRA"},  # not TERCEIRIZADO → skip
                    ],
                },
                {
                    "codigo": "CPU-B",
                    "composicao_itens": [],
                },
            ]
        }
        # Should run without raising and find no cycles
        result = verificar_ciclos_cpu(catalogo)
        assert isinstance(result, list)
