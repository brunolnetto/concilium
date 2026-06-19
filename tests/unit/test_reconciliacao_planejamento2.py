"""Tests for application/benchmarks/reconciliacao_planejamento.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


class TestParseValor:
    def test_none_returns_zero(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor(None) == 0.0

    def test_empty_string(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor("") == 0.0

    def test_pt_number(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor("1.234,56") == pytest.approx(1234.56)

    def test_invalid(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import _parse_valor

        assert _parse_valor("abc") == 0.0


class TestDisparityAnalysis:
    def test_empty(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import DisparityAnalysis

        a = DisparityAnalysis()
        assert a.total_canonical_direto == 0.0
        assert a.disparidades == []


class TestGerarRelatorio:
    def test_generates_string(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            gerar_relatorio_reconciliacao,
        )

        analise = DisparityAnalysis()
        analise.disparidades = [
            {
                "item_id": "2.1",
                "descricao": "Test",
                "planejamento_sem_bdi": 100.0,
                "planejamento_com_bdi": 120.0,
                "canonical": 150.0,
                "delta": 50.0,
                "delta_pct": 50.0,
                "tipo": "FALTA_PLANEJ",
            }
        ]
        result = gerar_relatorio_reconciliacao(analise)
        assert isinstance(result, str)
        assert "RECONCILIAÇÃO" in result or "RECONCILIA" in result
        assert "2.1" in result

    def test_empty_no_disparidades(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            gerar_relatorio_reconciliacao,
        )

        result = gerar_relatorio_reconciliacao(DisparityAnalysis())
        assert isinstance(result, str)


class TestReconciliadorPlanejamento:
    def _make_canonical(self):
        canonical = MagicMock()
        canonical.equipes_diretas = []
        canonical.resultado = None
        return canonical

    def test_identificar_disparidades_nao_executado(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        # Build analise manually to test _identificar_disparidades
        from concilium.application.benchmarks.reconciliacao_planejamento import CustoPlanejamento

        analise = DisparityAnalysis()
        analise.planejamento = {
            "2.1": CustoPlanejamento(
                item_id="2.1",
                descricao="Item",
                unidade="m³",
                quantidade=100.0,
                total_sem_bdi=1000.0,
                total_com_bdi=1200.0,
            )
        }
        analise.canonical_direto = {}  # no canonical → NAO_EXECUTADO

        reconciliador._identificar_disparidades(analise)
        assert any(d["tipo"] == "NAO_EXECUTADO" for d in analise.disparidades)

    def test_identificar_disparidades_nao_planejado(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        analise = DisparityAnalysis()
        analise.planejamento = {}  # no planejamento
        analise.canonical_direto = {"3.1": 5000.0}

        reconciliador._identificar_disparidades(analise)
        assert any(d["tipo"] == "NAO_PLANEJADO" for d in analise.disparidades)

    def test_identificar_disparidades_delta(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            CustoPlanejamento,
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = self._make_canonical()
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))

        analise = DisparityAnalysis()
        analise.planejamento = {
            "2.1": CustoPlanejamento(
                item_id="2.1",
                descricao="Item",
                unidade="m³",
                quantidade=100.0,
                total_sem_bdi=1000.0,
                total_com_bdi=1200.0,
            )
        }
        analise.canonical_direto = {"2.1": 1200.0}  # delta = 200 > 1

        reconciliador._identificar_disparidades(analise)
        disp = [d for d in analise.disparidades if d["item_id"] == "2.1"]
        assert len(disp) == 1

    def test_agregar_canonical_with_resultado(self):
        from concilium.application.benchmarks.reconciliacao_planejamento import (
            DisparityAnalysis,
            ReconciliadorPlanejamento,
        )

        canonical = MagicMock()
        canonical.equipes_diretas = []
        canonical.resultado.custo.indireto_adm = 10000.0
        canonical.resultado.custo.indireto_top = 5000.0
        canonical.resultado.custo.indireto_lab = 0.0
        canonical.resultado.custo.indireto_qsms = 0.0
        canonical.resultado.custo.indireto_mob = 0.0
        reconciliador = ReconciliadorPlanejamento(canonical, Path("x.txt"))
        analise = DisparityAnalysis()
        reconciliador._agregar_canonical(analise)
        assert analise.total_canonical_indireto == 15000.0
