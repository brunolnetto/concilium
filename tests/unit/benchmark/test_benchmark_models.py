"""Testes unitários para modelos de domínio de benchmarks."""

from datetime import datetime
from uuid import uuid4

from src.concilium.domain.benchmark.models import (
    BenchmarkExecution,
    BenchmarkMetadata,
    BenchmarkState,
)


def test_benchmark_metadata_criar():
    """CRIAÇÃO: BenchmarkMetadata com valores obrigatórios."""
    meta = BenchmarkMetadata(
        benchmark_id="AGIS_2025_Q1",
        nome="AGIS — Obra Terraplenagem Q1/2025",
        origem="AGIS — Obra real 2025 Q1",
        tags=["civil", "terraplenagem", "real"],
        criado_em=datetime.now(),
        versao=1,
        imutavel=False,
    )
    assert meta.benchmark_id == "AGIS_2025_Q1"
    assert meta.versao == 1
    assert meta.imutavel is False


def test_benchmark_metadata_marca_imutavel_apos_execucao():
    """ESTADO: Após execução bem-sucedida, benchmark fica imutável."""
    meta = BenchmarkMetadata(
        benchmark_id="AGIS_2025_Q1",
        nome="AGIS — Obra Terraplenagem Q1/2025",
        origem="AGIS — Obra real 2025 Q1",
        tags=["civil"],
        criado_em=datetime.now(),
        versao=1,
        imutavel=False,
    )
    # Após execução bem-sucedida
    meta.mark_immutable()
    assert meta.imutavel is True


def test_benchmark_execution_crear_com_ids():
    """CRIAÇÃO: BenchmarkExecution com trace_id e execution_id."""
    exec_id = str(uuid4())
    exec = BenchmarkExecution(
        execution_id=exec_id,
        benchmark_id="AGIS_2025_Q1",
        versao=1,
        projeto_id="proj-abc123",
        status="PENDENTE",
        executado_em=datetime.now(),
    )
    assert exec.execution_id == exec_id
    assert exec.benchmark_id == "AGIS_2025_Q1"
    assert exec.projeto_id == "proj-abc123"
    assert exec.status == "PENDENTE"


def test_benchmark_execution_registra_discrepancia():
    """DISCREPÂNCIA: BenchmarkExecution pode armazenar sumário de diferenças."""
    exec = BenchmarkExecution(
        execution_id=str(uuid4()),
        benchmark_id="AGIS_2025_Q1",
        versao=1,
        projeto_id="proj-abc123",
        status="SUCESSO",
        discrepancia_sumario={
            "delta_custo_direto": -5.2,  # %
            "delta_preco_venda": -2.1,
            "itens_impactados": 3,
        },
        executado_em=datetime.now(),
    )
    assert exec.discrepancia_sumario["delta_custo_direto"] == -5.2


def test_benchmark_state_enum():
    """Estados válidos de BenchmarkState."""
    assert BenchmarkState.PENDENTE == "PENDENTE"
    assert BenchmarkState.EM_PROGRESSO == "EM_PROGRESSO"
    assert BenchmarkState.SUCESSO == "SUCESSO"
    assert BenchmarkState.FALHA == "FALHA"
