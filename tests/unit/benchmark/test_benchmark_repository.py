"""Testes para Repository Port + Adapter de Benchmarks."""

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


def test_benchmark_store_save_and_load(benchmark_store):
    """PERSISTÊNCIA: Salvar e carregar BenchmarkMetadata."""
    meta = BenchmarkMetadata(
        benchmark_id="AGIS_2025_Q1",
        nome="AGIS — Obra",
        origem="Real",
        tags=["civil"],
        criado_em=datetime.now(),
        versao=1,
        imutavel=False,
    )
    # Salva
    benchmark_store.save_metadata(meta)

    # Carrega
    loaded = benchmark_store.get_metadata("AGIS_2025_Q1")
    assert loaded is not None
    assert loaded.benchmark_id == "AGIS_2025_Q1"
    assert loaded.versao == 1


def test_benchmark_store_list_all(benchmark_store):
    """LISTAGEM: Listar todos os benchmarks."""
    for i in range(3):
        meta = BenchmarkMetadata(
            benchmark_id=f"BENCH_{i}",
            nome=f"Bench {i}",
            origem="Test",
            tags=[],
            criado_em=datetime.now(),
            versao=1,
            imutavel=False,
        )
        benchmark_store.save_metadata(meta)

    all_benchs = benchmark_store.list_all()
    assert len(all_benchs) == 3


def test_benchmark_store_log_execution(benchmark_store):
    """AUDITORIA: Registrar execução com audit log append-only."""
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

    exec1 = BenchmarkExecution(
        execution_id="exec-1",
        benchmark_id="AGIS_2025_Q1",
        versao=1,
        projeto_id="proj-1",
        status="SUCESSO",
        executado_em=datetime.now(),
    )
    benchmark_store.log_execution(exec1)

    # Histórico deve incluir execução
    history = benchmark_store.get_execution_history("AGIS_2025_Q1")
    assert len(history) >= 1
    assert history[-1].execution_id == "exec-1"


def test_benchmark_store_rejeita_edicao_imutavel(benchmark_store):
    """IMUTABILIDADE: Rejeitar edição de benchmark marcado como imutável."""
    meta = BenchmarkMetadata(
        benchmark_id="AGIS_2025_Q1",
        nome="AGIS",
        origem="Real",
        tags=[],
        criado_em=datetime.now(),
        versao=1,
        imutavel=True,  # Marcado como imutável
    )
    benchmark_store.save_metadata(meta)

    # Tentar editar deve falhar
    with pytest.raises(PermissionError, match="imutável"):
        benchmark_store.update_metadata("AGIS_2025_Q1", {"nome": "Novo"})


def test_benchmark_store_gera_nova_versao_apos_edicao(benchmark_store):
    """VERSIONAMENTO: Editar benchmark gera v+1, não sobrescreve v1."""
    meta_v1 = BenchmarkMetadata(
        benchmark_id="AGIS_2025_Q1",
        nome="AGIS v1",
        origem="Real",
        tags=["v1"],
        criado_em=datetime.now(),
        versao=1,
        imutavel=False,
    )
    benchmark_store.save_metadata(meta_v1)

    # Edita → gera v2
    meta_v2 = benchmark_store.create_new_version("AGIS_2025_Q1", patch={"nome": "AGIS v2", "tags": ["v2"]})

    # v1 e v2 devem coexistir
    v1_loaded = benchmark_store.get_metadata_by_version("AGIS_2025_Q1", version=1)
    v2_loaded = benchmark_store.get_metadata_by_version("AGIS_2025_Q1", version=2)

    assert v1_loaded.versao == 1
    assert v2_loaded.versao == 2
    assert v2_loaded.nome == "AGIS v2"
