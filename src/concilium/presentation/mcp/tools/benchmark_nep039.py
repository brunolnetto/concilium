"""MCP Tools para Benchmarks — NEP-039.

Implementa 5 ferramentas:
1. consultar_benchmark — Leitura sem execução
2. listar_benchmarks — Catálogo disponível
3. executar_benchmark — Atrelado a projeto (conceitual)
4. editar_benchmark — Com controle de imutabilidade
5. comparar_execucoes_benchmark — Diff estruturado (Fase 4)
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from mcp.server.fastmcp import FastMCP

from concilium.application.benchmarks.diff_service import BenchmarkDiffService
from concilium.domain.benchmark.models import (
    BenchmarkExecution,
)
from concilium.infrastructure.storage.benchmark_store import (
    FileSystemBenchmarkStore,
)


from concilium.infrastructure.auth.permission_guard import permission

def register(server: FastMCP, store: FileSystemBenchmarkStore) -> None:
    """Registra ferramentas de benchmark no servidor MCP."""

    @server.tool(description=(
        "Consulta benchmarks NEP-039: lista todos ou detalha um específico. "
        "Omita benchmark_id para listar todos; informe-o para obter metadados e histórico."
    ))
    @permission("project:read")
    def consultar_benchmark(benchmark_id: str | None = None) -> dict[str, Any]:
        """Lista benchmarks disponíveis ou retorna metadados de um benchmark específico.

        Args:
            benchmark_id: Omita para listar todos; informe para detalhar um benchmark.
        """
        if benchmark_id is None:
            all_benchs = store.list_all()
            return {
                "total": len(all_benchs),
                "benchmarks": [
                    {"benchmark_id": b.benchmark_id, "nome": b.nome, "origem": b.origem,
                     "tags": b.tags, "versao": b.versao, "imutavel": b.imutavel,
                     "criado_em": b.criado_em.isoformat()}
                    for b in all_benchs
                ],
            }
        meta = store.get_metadata(benchmark_id)
        if not meta:
            return {"erro": f"Benchmark '{benchmark_id}' não encontrado", "status": "NAO_ENCONTRADO"}
        history = store.get_execution_history(benchmark_id, limit=10)
        return {
            "benchmark_id": meta.benchmark_id,
            "nome": meta.nome,
            "origem": meta.origem,
            "tags": meta.tags,
            "versao": meta.versao,
            "imutavel": meta.imutavel,
            "criado_em": meta.criado_em.isoformat(),
            "execucoes_historico": [
                {"execution_id": e.execution_id, "projeto_id": e.projeto_id,
                 "status": e.status, "executado_em": e.executado_em.isoformat(),
                 "discrepancia_sumario": e.discrepancia_sumario}
                for e in history
            ],
            "total_projetos_derivados": len({e.projeto_id for e in history if e.status == "SUCESSO"}),
        }

    @server.tool(
        description="Enfileira execução de benchmark NEP-039 (registra vínculo com projeto e retorna execution_id)."
    )
    @permission("project:run")
    def executar_benchmark_nep039(
        benchmark_id: str,
        criar_novo_projeto: bool = True,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Executa benchmark e registra vínculo com projeto.

        Args:
            benchmark_id: ID do benchmark
            criar_novo_projeto: True para criar projeto novo, False para reusar
            project_id: ID do projeto existente (se criar_novo_projeto=False)

        Returns:
            Dicionário com: project_id, execution_id, status, benchmark_versao.
        """
        meta = store.get_metadata(benchmark_id)
        if not meta:
            return {"erro": f"Benchmark '{benchmark_id}' não encontrado"}

        # Create execution record (will be updated after job completes)
        exec = BenchmarkExecution(
            execution_id=str(uuid4()),
            benchmark_id=benchmark_id,
            versao=meta.versao,
            projeto_id=project_id or f"proj-{uuid4()}",
            status="PENDENTE",
            executado_em=datetime.now(),
        )
        store.log_execution(exec)

        return {
            "project_id": exec.projeto_id,
            "execution_id": exec.execution_id,
            "benchmark_id": benchmark_id,
            "benchmark_versao": meta.versao,
            "status": "PENDENTE",
            "mensagem": f"Benchmark '{benchmark_id}' v{meta.versao} enfileirado para execução. Project: {exec.projeto_id}",
        }

    @server.tool(description="Edita um benchmark com controle de imutabilidade. Imutável → gera v+1.")
    @permission("project:run")
    def editar_benchmark(benchmark_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        """Edita benchmark. Se imutável, gera nova versão.

        Args:
            benchmark_id: ID do benchmark
            patch: Dicionário com campos a atualizar (nome, tags, origem, etc.)

        Returns:
            Dicionário com metadados atualizados: benchmark_id, versao, imutavel, etc.
        """
        meta = store.get_metadata(benchmark_id)
        if not meta:
            return {"erro": f"Benchmark '{benchmark_id}' não encontrado"}

        if meta.imutavel:
            # Imutável → gera v+1
            new_meta = store.create_new_version(benchmark_id, patch=patch)
            return {
                "benchmark_id": new_meta.benchmark_id,
                "versao_anterior": meta.versao,
                "versao_nova": new_meta.versao,
                "nome": new_meta.nome,
                "tags": new_meta.tags,
                "imutavel": new_meta.imutavel,
                "mensagem": f"Benchmark v{meta.versao} era imutável. Criada nova versão v{new_meta.versao}.",
            }
        else:
            # Mutável → atualiza in-place
            store.update_metadata(benchmark_id, patch=patch)
            updated = store.get_metadata(benchmark_id)
            return {
                "benchmark_id": updated.benchmark_id,
                "versao": updated.versao,
                "nome": updated.nome,
                "tags": updated.tags,
                "imutavel": updated.imutavel,
                "mensagem": f"Benchmark v{updated.versao} atualizado in-place (ainda mutável).",
            }

    @server.tool(description="Marca um benchmark como imutável (após primeira execução).")
    @permission("project:approve")
    def marcar_benchmark_imutavel(benchmark_id: str) -> dict[str, Any]:
        """Marca benchmark como imutável.

        Args:
            benchmark_id: ID do benchmark

        Returns:
            Confirmação de imutabilidade.
        """
        meta = store.get_metadata(benchmark_id)
        if not meta:
            return {"erro": f"Benchmark '{benchmark_id}' não encontrado"}

        meta.mark_immutable()
        store.save_metadata(meta)

        return {
            "benchmark_id": meta.benchmark_id,
            "versao": meta.versao,
            "imutavel": True,
            "mensagem": f"Benchmark '{benchmark_id}' v{meta.versao} marcado como imutável.",
        }

    @server.tool(description="Compara duas execuções de benchmark e retorna diff estruturado (Fase 4).")
    @permission("project:read")
    def comparar_execucoes_benchmark(execution_1_id: str, execution_2_id: str) -> dict[str, Any]:
        """Compara duas execuções e retorna deltas estruturados.

        Args:
            execution_1_id: ID da execução baseline (v1)
            execution_2_id: ID da execução nova (v2)

        Returns:
            Dicionário com: delta_custo, delta_cronograma, delta_margem,
            itens_impactados, interpretacao.
        """
        # Busca execuções no histórico (simulado)
        # Em produção, isso seria buscado em banco de dados ou storage permanente
        history = []
        for bid in [e.benchmark_id for e in store.list_all()]:
            history.extend(store.get_execution_history(bid))

        exec_1 = next((e for e in history if e.execution_id == execution_1_id), None)
        exec_2 = next((e for e in history if e.execution_id == execution_2_id), None)

        if not exec_1:
            return {"erro": f"Execução '{execution_1_id}' não encontrada"}
        if not exec_2:
            return {"erro": f"Execução '{execution_2_id}' não encontrada"}

        # Usa DiffService para comparar
        diff_service = BenchmarkDiffService()
        try:
            diff_result = diff_service.compare(exec_1, exec_2)
        except ValueError as e:
            return {"erro": str(e)}

        return diff_result.to_dict()
