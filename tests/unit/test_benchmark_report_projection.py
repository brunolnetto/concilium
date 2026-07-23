"""Coverage batch 33 — projection, cubo_analitico_builder, backtracking_pe_builder."""

from __future__ import annotations

from types import SimpleNamespace

# projection.py line 34:
# _bfc_custo_direto_total when custo_direto is None (no venda, no direto_equipes)
# ---------------------------------------------------------------------------


class TestBfcCustoDiretoTotal:
    def test_custo_direto_none_falls_through_to_line34(self):
        """Line 34: custo_direto is None → return (None, custo.total, None)."""
        from concilium.application.benchmarks.report.projection import _bfc_custo_direto_total

        custo = SimpleNamespace(direto_equipes=None, total=500.0)
        result = _bfc_custo_direto_total(custo, custo_indireto=50.0, venda=None)

        assert result[0] is None  # custo_direto = None
        assert result[1] == 500.0  # custo.total
        assert result[2] is None  # instancial = None


# ---------------------------------------------------------------------------


# projection.py line 59:
# _bfc_preco_venda when all sources are unavailable → "indisponivel"
# ---------------------------------------------------------------------------


class TestBfcPrecoVenda:
    def test_all_sources_unavailable_returns_indisponivel(self):
        """Line 59: no preco_venda from any source → (raw_bdi_lucro, None, 'indisponivel')."""
        from concilium.application.benchmarks.report.projection import _bfc_preco_venda

        # venda with no valid preco fields and raw_bdi_lucro=None → fallback all fail
        venda = SimpleNamespace(
            total_com_bdi=None,
            total_custo_plus_catalogo=None,
            bdi_lucro_impostos=None,  # raw_bdi_lucro=None → nivel 3 also fails
        )

        result = _bfc_preco_venda(venda, custo_total=None)
        assert result[0] is None  # raw_bdi_lucro
        assert result[1] is None  # preco_venda
        assert result[2] == "indisponivel"

    def test_raw_bdi_lucro_but_no_custo_total_returns_indisponivel(self):
        """Line 59: bdi_lucro set but custo_total=None → can't compute nivel 3 → indisponivel."""
        from concilium.application.benchmarks.report.projection import _bfc_preco_venda

        venda = SimpleNamespace(
            total_com_bdi=None,
            total_custo_plus_catalogo=None,
            bdi_lucro_impostos=0.15,
        )
        result = _bfc_preco_venda(venda, custo_total=None)
        assert result[2] == "indisponivel"


# ---------------------------------------------------------------------------


# projection.py line 74:
# _bfc_bdi_lucro returns 0.15 default when raw is None and no preco/custo
# ---------------------------------------------------------------------------


class TestBfcBdiLucro:
    def test_no_inputs_returns_default_015(self):
        """Line 74: raw_bdi_lucro=None, preco_venda=None → return 0.15."""
        from concilium.application.benchmarks.report.projection import _bfc_bdi_lucro

        result = _bfc_bdi_lucro(preco_venda=None, custo_total=None, raw_bdi_lucro=None)
        assert result == 0.15

    def test_no_inputs_with_zero_custo_returns_default(self):
        """Line 74: raw=None, custo_total=0 (falsy) → return 0.15."""
        from concilium.application.benchmarks.report.projection import _bfc_bdi_lucro

        result = _bfc_bdi_lucro(preco_venda=100.0, custo_total=0.0, raw_bdi_lucro=None)
        assert result == 0.15  # custo_total=0 is falsy → falls through to 0.15


# ---------------------------------------------------------------------------

