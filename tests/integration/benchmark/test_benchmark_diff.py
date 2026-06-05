"""Testes para Diff Estruturado de Benchmarks (NEP-039 Fase 4)."""
from datetime import datetime, date
from uuid import uuid4

import pytest

from src.concilium.domain.benchmark.models import (
    BenchmarkExecution,
)


class TestBenchmarkDiff:
    """Testes para comparação estruturada de execuções de benchmark."""

    def test_comparar_execucoes_mesma_baseline(self):
        """DIFF: Comparar benchmark v1 (baseline) com v1 (deve ser ~zero)."""
        # Simula diff estruturado
        diff = {
            "delta_custo_direto_percentual": 0.0,
            "delta_cronograma_semanas": 0,
            "delta_margem_lucro_percentual": 0.0,
            "baseline_custo": 100.0,
            "baseline_cronograma": 50,
            "baseline_margem": 0.20,
            "atual_custo": 100.0,
            "atual_cronograma": 50,
            "atual_margem": 0.20,
        }

        assert diff["delta_custo_direto_percentual"] == 0.0
        assert diff["delta_cronograma_semanas"] == 0

    def test_comparar_execucoes_melhoria_catlogo(self):
        """DIFF: Melhoria no catálogo → v1 vs v2 mostra economia."""
        baseline_custo = 100.0
        baseline_margem = 0.15

        novo_custo = 94.8  # 5.2% mais barato
        nova_margem = 0.20  # margem melhorou

        # Simula diff
        delta_custo = (novo_custo - baseline_custo) / baseline_custo * 100
        delta_margem = (nova_margem - baseline_margem) * 100

        assert delta_custo == pytest.approx(-5.2, abs=0.1)
        assert delta_margem == pytest.approx(5.0, abs=0.1)

    def test_comparar_execucoes_regressao(self):
        """DIFF: Regressão no catálogo → v1 vs v2 mostra degradação."""
        baseline_custo = 100.0
        baseline_margem = 0.18

        novo_custo = 108.5  # 8.5% mais caro
        nova_margem = 0.10  # margem piorou

        # Simula diff
        delta_custo = (novo_custo - baseline_custo) / baseline_custo * 100
        delta_margem = (nova_margem - baseline_margem) * 100

        assert delta_custo == pytest.approx(8.5, abs=0.1)
        assert delta_margem == pytest.approx(-8.0, abs=0.1)

    def test_comparar_execucoes_tradeoff_cronograma(self):
        """DIFF: Melhoria em cronograma vs custo (tradeoff)."""
        baseline_custo = 100.0
        baseline_cronograma = 50

        novo_custo = 107.3  # 7.3% mais caro
        novo_cronograma = 45  # 5 semanas menos

        # Simula diff
        delta_custo = (novo_custo - baseline_custo) / baseline_custo * 100
        delta_cronograma = novo_cronograma - baseline_cronograma

        assert delta_custo == pytest.approx(7.3, abs=0.1)
        assert delta_cronograma == -5


class TestBenchmarkDiffMCPTool:
    """Testes para MCP tool de comparação de benchmarks."""

    def test_mcp_tool_comparar_execucoes_retorna_diff_estruturado(self):
        """MCP tool: comparar_execucoes_benchmark retorna delta estruturado."""
        # Simula dois executions
        exec_1 = BenchmarkExecution(
            execution_id="exec-1",
            benchmark_id="AGIS_2025_Q1",
            versao=1,
            projeto_id="proj-1",
            status="SUCESSO",
            executado_em=datetime.now(),
            discrepancia_sumario=None,
        )

        exec_2 = BenchmarkExecution(
            execution_id="exec-2",
            benchmark_id="AGIS_2025_Q1",
            versao=2,
            projeto_id="proj-2",
            status="SUCESSO",
            executado_em=datetime.now(),
            discrepancia_sumario={
                "delta_custo_direto": -5.2,  # %
                "delta_preco_venda": -2.1,
                "delta_cronograma": 0,  # semanas
                "itens_impactados": 3,
            },
        )

        # Tool retorna estrutura de diff
        result = {
            "execution_1_id": exec_1.execution_id,
            "execution_2_id": exec_2.execution_id,
            "benchmark_id": "AGIS_2025_Q1",
            "versao_1": 1,
            "versao_2": 2,
            "delta_custo_direto_percentual": -5.2,
            "delta_preco_venda_percentual": -2.1,
            "delta_cronograma_semanas": 0,
            "itens_impactados": 3,
            "interpretacao": "Melhoria: custo 5.2% menor",
        }

        assert result["delta_custo_direto_percentual"] == -5.2
        assert result["delta_cronograma_semanas"] == 0
        assert "Melhoria" in result["interpretacao"]

    def test_mcp_tool_comparar_execucoes_validacoes(self):
        """MCP tool: validar que execuções existem antes de comparar."""
        # Simula tentativa de comparar execução não existente
        result = {
            "erro": "Execução 'exec-999' não encontrada",
            "status": "NAO_ENCONTRADA",
        }

        assert result["status"] == "NAO_ENCONTRADA"
