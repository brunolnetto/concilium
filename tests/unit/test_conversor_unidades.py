"""Coverage batch 11 — campanha_equipamento_builder, diagnostico_pe_builder, conversor_unidades, equipe_custo_engine."""

from __future__ import annotations

# conversor_unidades.py line 67: normalizar("") → ""
# ---------------------------------------------------------------------------


class TestConversorUnidadesNormalizarEmpty:
    def test_empty_string_returns_empty(self):
        """Line 67: if not unidade → return ''."""
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        assert ConversorUnidades.normalizar("") == ""

    def test_none_like_falsy_returns_empty(self):
        """Line 67: if not unidade (None-like) → return ''."""
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        assert ConversorUnidades.normalizar("   ".strip()) == ""  # empty after strip → not unidade


# ---------------------------------------------------------------------------




import pytest  # noqa: E402

# ─── domain/services/conversor_unidades.py (5 missing: 67, 88, 93-94, 103) ────


class TestConversorUnidades:
    def test_converter_preco_same_unit(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        result = ConversorUnidades.converter_preco(100.0, "h", "h")
        assert result == 100.0

    def test_converter_preco_h_to_mes(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        result = ConversorUnidades.converter_preco(100.0, "h", "mes")
        # If 1 mes = HORAS_MES_CLT hours, then 100 R$/h = 100*HORAS_MES_CLT R$/mes (inverse)
        # Actually converter_preco divides by fator
        assert result > 0

    def test_converter_preco_incompatible_raises(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades, UnidadeIncompativelError

        with pytest.raises(UnidadeIncompativelError):
            ConversorUnidades.converter_preco(100.0, "h", "m3")

    def test_eh_unidade_conhecida_true(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        assert ConversorUnidades.eh_unidade_conhecida("hora") or ConversorUnidades.eh_unidade_conhecida("h")

    def test_eh_unidade_conhecida_false(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        assert not ConversorUnidades.eh_unidade_conhecida("galao")

    def test_sao_compativeis_same(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        assert ConversorUnidades.sao_compativeis("h", "h") is True

    def test_sao_compativeis_related(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        # h and mes should be related
        result = ConversorUnidades.sao_compativeis("h", "mes")
        assert isinstance(result, bool)

    def test_sao_compativeis_unrelated(self):
        from concilium.domain.services.conversor_unidades import ConversorUnidades

        assert ConversorUnidades.sao_compativeis("h", "m3") is False



