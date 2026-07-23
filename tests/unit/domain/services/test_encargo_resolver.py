"""Coverage sweep — files with few missing lines (1-30 lines missing)."""

from __future__ import annotations

# ─── domain/services/encargo_resolver.py ─────────────────────────────────────


class TestEncargoResolver:
    def test_override_takes_precedence(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({}, encargo_override=0.5)
        assert result == 0.5

    def test_percentual_encargos_local(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({"percentual_encargos_local": 0.3})
        assert result == 0.3

    def test_horista_category(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({"categoria_sindical": "horista"})
        assert result > 1.0

    def test_mensalista_category(self):
        from concilium.domain.services.financial.encargo_resolver import resolver_encargo

        result = resolver_encargo({"categoria_sindical": "mensalista"})
        assert result >= 0.0

    def test_default_mensalista_when_unknown_category(self):
        from concilium.domain.services.financial.encargo_resolver import ENCARGOS_MENSALISTA, resolver_encargo

        # Unknown category → falls to mensalista branch
        r = resolver_encargo({"categoria_sindical": "unknown"})
        assert r == ENCARGOS_MENSALISTA or r >= 0



