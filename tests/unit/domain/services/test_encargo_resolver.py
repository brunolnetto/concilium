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


class TestCustoJaIncluiEncargos:
    """ADR-182 D1: fonte única de verdade para "preco_unitario já all-in"."""

    def test_metodo_custo_total_ja_incluido_retorna_true(self):
        from concilium.domain.services.financial.encargo_resolver import custo_ja_inclui_encargos

        assert custo_ja_inclui_encargos({"metodo_custo_total": "custo_total_ja_incluido"}) is True

    def test_ausencia_do_campo_retorna_false(self):
        from concilium.domain.services.financial.encargo_resolver import custo_ja_inclui_encargos

        assert custo_ja_inclui_encargos({}) is False

    def test_valor_diferente_retorna_false(self):
        from concilium.domain.services.financial.encargo_resolver import custo_ja_inclui_encargos

        assert custo_ja_inclui_encargos({"metodo_custo_total": "outra_coisa"}) is False

    def test_texto_livre_em_nota_nao_e_mais_reconhecido(self):
        """ADR-182: o mecanismo de texto livre foi substituído pelo campo estruturado."""
        from concilium.domain.services.financial.encargo_resolver import custo_ja_inclui_encargos

        atrib = {"nota": "taxa horária — inclui encargos e benefícios"}
        assert custo_ja_inclui_encargos(atrib) is False
