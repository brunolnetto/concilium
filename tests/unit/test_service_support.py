"""Coverage batch 4 — small missing-line targets across many files."""

from __future__ import annotations

from types import SimpleNamespace

# service_support.py line 25: build_summary with resultado=None → short dict
# ---------------------------------------------------------------------------


class TestBuildSummaryResultadoNone:
    def test_resultado_none_returns_short_dict(self):
        """Line 25: result is None → return pe_deficit/alerta only."""
        from concilium.application.services.service_support import build_summary

        pe1 = SimpleNamespace(status_validacao="ERRO")
        pe2 = SimpleNamespace(status_validacao="AVISO")
        canonical = SimpleNamespace(resultado=None, ponto_equilibrio=[pe1, pe2])
        result = build_summary(canonical)
        assert result == {"pe_deficit_items": 1, "pe_alerta_items": 1}
        assert "preco_venda_total" not in result


# ---------------------------------------------------------------------------





# service_support.py line 25: build_summary returns early when result is None
# ---------------------------------------------------------------------------


class TestServiceSupportBuildSummaryNoneResult:
    def test_returns_partial_dict_when_no_resultado(self):
        """Line 25: canonical has no resultado → result=None → early return dict."""
        from concilium.application.services.service_support import build_summary

        canonical = SimpleNamespace(ponto_equilibrio=[])
        result = build_summary(canonical)
        assert "pe_deficit_items" in result
        assert "pe_alerta_items" in result
        assert "custo_total" not in result  # early return, not full dict


# ---------------------------------------------------------------------------

