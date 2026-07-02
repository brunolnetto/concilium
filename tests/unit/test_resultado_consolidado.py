"""Tests for domain/models/financial/resultado.py."""

from __future__ import annotations

import pytest


def _make_breakdown(escopo_id="ESC-1", venda=1_000_000.0, custo=800_000.0, margem_pct=0.20, status="VERDE"):
    from concilium.domain.models.financial.resultado import BreakdownEscopo

    return BreakdownEscopo(
        escopo_id=escopo_id,
        nome=f"Escopo {escopo_id}",
        plano_id="plano-1",
        status_plano="ATIVO",
        venda_com_bdi=venda,
        custo_total=custo,
        resultado_financeiro=venda - custo,
        margem_pct=margem_pct,
        status_margem=status,
        peso_relativo=1.0,
    )


class TestBreakdownEscopo:
    def test_create(self):
        b = _make_breakdown()
        assert b.escopo_id == "ESC-1"
        assert b.venda_com_bdi == 1_000_000.0

    def test_peso_relativo_bounds(self):
        with pytest.raises(Exception):  # noqa: B017
            _make_breakdown().__class__(
                escopo_id="x",
                nome="x",
                plano_id="p",
                status_plano="A",
                venda_com_bdi=100,
                custo_total=80,
                resultado_financeiro=20,
                margem_pct=0.2,
                status_margem="VERDE",
                peso_relativo=1.5,  # > 1
            )


class TestResultadoConsolidadoProjeto:
    def test_status_for_verde(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        assert ResultadoConsolidadoProjeto._status_for(0.10) == "VERDE"
        assert ResultadoConsolidadoProjeto._status_for(0.08) == "VERDE"

    def test_status_for_amarelo(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        assert ResultadoConsolidadoProjeto._status_for(0.06) == "AMARELO"
        assert ResultadoConsolidadoProjeto._status_for(0.04) == "AMARELO"

    def test_status_for_vermelho(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        assert ResultadoConsolidadoProjeto._status_for(0.03) == "VERMELHO"
        assert ResultadoConsolidadoProjeto._status_for(0.0) == "VERMELHO"
        assert ResultadoConsolidadoProjeto._status_for(-0.05) == "VERMELHO"

    def test_calcular_single_escopo(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        b = _make_breakdown(venda=1_000_000.0, custo=800_000.0)
        res = ResultadoConsolidadoProjeto.calcular("proj-1", [b])
        assert res.venda_total_com_bdi == 1_000_000.0
        assert res.custo_total == 800_000.0
        assert res.resultado_financeiro == 200_000.0
        assert abs(res.margem_pct - 0.2) < 0.001
        assert res.status_margem == "VERDE"
        assert "ESC-1" in res.escopos_incluidos
        assert res.breakdown[0].peso_relativo == 1.0

    def test_calcular_two_escopos(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        b1 = _make_breakdown("ESC-1", venda=600_000, custo=500_000)
        b2 = _make_breakdown("ESC-2", venda=400_000, custo=350_000)
        res = ResultadoConsolidadoProjeto.calcular("proj-1", [b1, b2])
        assert res.venda_total_com_bdi == 1_000_000.0
        assert res.custo_total == 850_000.0
        assert len(res.escopos_incluidos) == 2
        # Peso relativo: ESC-1 = 0.6, ESC-2 = 0.4
        pesos = {b.escopo_id: b.peso_relativo for b in res.breakdown}
        assert abs(pesos["ESC-1"] - 0.6) < 0.001
        assert abs(pesos["ESC-2"] - 0.4) < 0.001

    def test_calcular_empty_breakdown(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        res = ResultadoConsolidadoProjeto.calcular("proj-1", [])
        assert res.venda_total_com_bdi == 0.0
        assert res.margem_pct == 0.0
        assert res.status_margem == "VERMELHO"

    def test_calcular_with_escopos_excluidos(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        b = _make_breakdown()
        res = ResultadoConsolidadoProjeto.calcular("proj-1", [b], escopos_excluidos=["ESC-X"])
        assert "ESC-X" in res.escopos_excluidos

    def test_calcular_with_avisos(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        b = _make_breakdown()
        res = ResultadoConsolidadoProjeto.calcular("proj-1", [b], avisos=["aviso 1"])
        assert "aviso 1" in res.avisos

    def test_calcular_amarelo_threshold(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        # 5% margin → AMARELO
        b = _make_breakdown(venda=1_000_000, custo=950_000)
        res = ResultadoConsolidadoProjeto.calcular("proj-1", [b])
        assert res.status_margem == "AMARELO"

    def test_calcular_vermelho_threshold(self):
        from concilium.domain.models.financial.resultado import ResultadoConsolidadoProjeto

        # 2% margin → VERMELHO
        b = _make_breakdown(venda=1_000_000, custo=980_000)
        res = ResultadoConsolidadoProjeto.calcular("proj-1", [b])
        assert res.status_margem == "VERMELHO"
