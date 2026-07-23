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

