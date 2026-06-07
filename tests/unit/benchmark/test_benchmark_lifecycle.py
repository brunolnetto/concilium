"""Testes para ciclo de vida completo benchmark → execução → proveniência."""

from datetime import datetime
from pathlib import Path

import pytest

from src.concilium.domain.benchmark.models import (
    BenchmarkExecution,
    BenchmarkMetadata,
)
from src.concilium.infrastructure.storage.benchmark_store import (
    FileSystemBenchmarkStore,
)


@pytest.fixture
def benchmark_store(tmp_path: Path) -> FileSystemBenchmarkStore:
    """Cria store em memória (tmp_path)."""
    return FileSystemBenchmarkStore(root=tmp_path)


def test_ciclo_vida_benchmark_completo(benchmark_store):
    """FLUXO: Criar → Executar → Marcar imutável → Reeditar gera v2."""
    # Passo 1: Criar benchmark v1
    meta_v1 = BenchmarkMetadata(
        benchmark_id="AGIS_2025_Q1",
        nome="AGIS Q1",
        origem="Real",
        tags=["civil"],
        criado_em=datetime.now(),
        versao=1,
        imutavel=False,
    )
    benchmark_store.save_metadata(meta_v1)

    # Passo 2: Executar
    exec_v1 = BenchmarkExecution(
        execution_id="exec-v1",
        benchmark_id="AGIS_2025_Q1",
        versao=1,
        projeto_id="proj-abc123",
        status="SUCESSO",
        executado_em=datetime.now(),
    )
    benchmark_store.log_execution(exec_v1)
    meta_v1.mark_immutable()
    benchmark_store.save_metadata(meta_v1)

    # Passo 3: Tentar editar v1 deve gerar v2
    meta_v2 = benchmark_store.create_new_version("AGIS_2025_Q1", patch={"tags": ["civil", "updated"]})

    # Verificações
    assert meta_v2.versao == 2
    assert meta_v2.imutavel is False  # Nova versão começa mutável

    v1_stored = benchmark_store.get_metadata_by_version("AGIS_2025_Q1", version=1)
    assert v1_stored.imutavel is True  # v1 permanece imutável


def test_execucoes_multiplas_historico(benchmark_store):
    """AUDITORIA: Múltiplas execuções aparecem no histórico."""
    meta = BenchmarkMetadata(
        benchmark_id="BENCH_MULTI",
        nome="Multi execução",
        origem="Test",
        tags=[],
        criado_em=datetime.now(),
        versao=1,
        imutavel=False,
    )
    benchmark_store.save_metadata(meta)

    # Registra 3 execuções
    for i in range(3):
        exec = BenchmarkExecution(
            execution_id=f"exec-{i}",
            benchmark_id="BENCH_MULTI",
            versao=1,
            projeto_id=f"proj-{i}",
            status="SUCESSO",
            executado_em=datetime.now(),
        )
        benchmark_store.log_execution(exec)

    history = benchmark_store.get_execution_history("BENCH_MULTI")
    assert len(history) == 3
    assert all(e.benchmark_id == "BENCH_MULTI" for e in history)


def test_get_metadata_by_version_nao_existe(benchmark_store):
    """NOT_FOUND: Solicitar versão não existente retorna None."""
    meta = BenchmarkMetadata(
        benchmark_id="AGIS_2025_Q1",
        nome="AGIS",
        origem="Real",
        tags=[],
        criado_em=datetime.now(),
        versao=1,
        imutavel=False,
    )
    benchmark_store.save_metadata(meta)

    result = benchmark_store.get_metadata_by_version("AGIS_2025_Q1", version=999)
    assert result is None
