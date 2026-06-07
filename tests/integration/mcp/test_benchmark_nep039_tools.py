"""Testes de integração para MCP Tools de Benchmark (NEP-039)."""

from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pytest

from src.concilium.domain.benchmark.models import BenchmarkMetadata
from src.concilium.infrastructure.storage.benchmark_store import (
    FileSystemBenchmarkStore,
)


@pytest.fixture
def benchmark_store(tmp_path: Path) -> FileSystemBenchmarkStore:
    """Cria store em memória (tmp_path)."""
    return FileSystemBenchmarkStore(root=tmp_path)


class TestBenchmarkToolsConsultar:
    """Tests para tool: consultar_benchmark."""

    def test_consultar_benchmark_retorna_metadados(self, benchmark_store):
        """Tool: consultar_benchmark retorna metadados sem executar."""
        # Registra benchmark
        meta = BenchmarkMetadata(
            benchmark_id="AGIS_2025_Q1",
            nome="AGIS — Obra Terraplenagem Q1/2025",
            origem="AGIS — Obra real 2025 Q1",
            tags=["civil", "terraplenagem", "real"],
            criado_em=datetime.now(),
            versao=1,
            imutavel=False,
        )
        benchmark_store.save_metadata(meta)

        # Simula tool: consultar_benchmark
        result = benchmark_store.get_metadata("AGIS_2025_Q1")
        assert result is not None
        assert result.benchmark_id == "AGIS_2025_Q1"
        assert result.versao == 1
        assert result.imutavel is False

    def test_consultar_benchmark_nao_existe(self, benchmark_store):
        """Tool: consultar_benchmark retorna None se não existe."""
        result = benchmark_store.get_metadata("NAO_EXISTE")
        assert result is None


class TestBenchmarkToolsListar:
    """Tests para tool: listar_benchmarks."""

    def test_listar_benchmarks_retorna_catlogo(self, benchmark_store):
        """Tool: listar_benchmarks retorna catálogo."""
        # Registra 3 benchmarks
        for i in range(3):
            meta = BenchmarkMetadata(
                benchmark_id=f"BENCH_{i}",
                nome=f"Bench {i}",
                origem="Test",
                tags=["test"],
                criado_em=datetime.now(),
                versao=1,
                imutavel=False,
            )
            benchmark_store.save_metadata(meta)

        # Simula tool: listar_benchmarks
        result = benchmark_store.list_all()
        assert len(result) == 3
        ids = {b.benchmark_id for b in result}
        assert ids == {"BENCH_0", "BENCH_1", "BENCH_2"}

    def test_listar_benchmarks_vazio(self, benchmark_store):
        """Tool: listar_benchmarks retorna lista vazia se nenhum benchmark."""
        result = benchmark_store.list_all()
        assert result == []

    def test_listar_benchmarks_versao_mais_recente(self, benchmark_store):
        """Tool: listar_benchmarks retorna apenas versão mais recente."""
        # Cria v1
        meta_v1 = BenchmarkMetadata(
            benchmark_id="AGIS",
            nome="AGIS v1",
            origem="Test",
            tags=["v1"],
            criado_em=datetime.now(),
            versao=1,
            imutavel=False,
        )
        benchmark_store.save_metadata(meta_v1)

        # Cria v2
        meta_v2 = BenchmarkMetadata(
            benchmark_id="AGIS",
            nome="AGIS v2",
            origem="Test",
            tags=["v2"],
            criado_em=datetime.now(),
            versao=2,
            imutavel=False,
        )
        benchmark_store.save_metadata(meta_v2)

        # listar_benchmarks deve retornar apenas v2
        result = benchmark_store.list_all()
        assert len(result) == 1
        assert result[0].versao == 2
        assert result[0].nome == "AGIS v2"


class TestBenchmarkToolsExecutar:
    """Tests para tool: executar_benchmark (conceitual)."""

    def test_executar_benchmark_cria_referencia_em_projeto(self, benchmark_store):
        """Tool: executar_benchmark vincula benchmark a projeto novo."""
        # Registra benchmark
        meta = BenchmarkMetadata(
            benchmark_id="AGIS_2025_Q1",
            nome="AGIS",
            origem="Real",
            tags=["civil"],
            criado_em=datetime.now(),
            versao=1,
            imutavel=False,
        )
        benchmark_store.save_metadata(meta)

        # Simula execução: registra que projeto foi criado do benchmark
        projeto_id = f"proj-{uuid4()}"
        from src.concilium.domain.benchmark.models import BenchmarkExecution

        exec = BenchmarkExecution(
            execution_id=str(uuid4()),
            benchmark_id="AGIS_2025_Q1",
            versao=1,
            projeto_id=projeto_id,
            status="SUCESSO",
            executado_em=datetime.now(),
        )
        benchmark_store.log_execution(exec)

        # Verifica que execução foi registrada
        history = benchmark_store.get_execution_history("AGIS_2025_Q1")
        assert len(history) == 1
        assert history[0].projeto_id == projeto_id


class TestBenchmarkToolsEditar:
    """Tests para tool: editar_benchmark."""

    def test_editar_benchmark_imutvel_gera_versao(self, benchmark_store):
        """Tool: editar_benchmark imutável gera v+1."""
        # Cria v1 imutável
        meta = BenchmarkMetadata(
            benchmark_id="AGIS_2025_Q1",
            nome="AGIS v1",
            origem="Real",
            tags=["v1"],
            criado_em=datetime.now(),
            versao=1,
            imutavel=True,
        )
        benchmark_store.save_metadata(meta)

        # Edita → gera v2
        meta_v2 = benchmark_store.create_new_version("AGIS_2025_Q1", patch={"tags": ["v2"]})

        # Verifica v2
        assert meta_v2.versao == 2
        assert meta_v2.imutavel is False
        assert meta_v2.tags == ["v2"]

        # Verifica que v1 ainda existe e é imutável
        v1 = benchmark_store.get_metadata_by_version("AGIS_2025_Q1", version=1)
        assert v1.versao == 1
        assert v1.imutavel is True

    def test_editar_benchmark_mutavel_in_place(self, benchmark_store):
        """Tool: editar_benchmark mutável atualiza in-place."""
        # Cria v1 mutável
        meta = BenchmarkMetadata(
            benchmark_id="AGIS_2025_Q1",
            nome="AGIS v1",
            origem="Real",
            tags=["v1"],
            criado_em=datetime.now(),
            versao=1,
            imutavel=False,
        )
        benchmark_store.save_metadata(meta)

        # Edita (atualiza in-place)
        benchmark_store.update_metadata("AGIS_2025_Q1", {"tags": ["v1-edited"]})

        # Verifica que versão permanece 1
        loaded = benchmark_store.get_metadata("AGIS_2025_Q1")
        assert loaded.versao == 1
        assert loaded.tags == ["v1-edited"]
