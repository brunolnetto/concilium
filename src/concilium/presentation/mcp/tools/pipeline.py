"""Ferramentas MCP de execução de pipeline — avancar_pipeline."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from concilium.application.skills.phase_classifier import CANONICAL_SKILL_ORDER
from concilium.presentation.mcp._context import (
    ConciliumRuntimeError,
    _get_or_create_trace_id,
    _lifecycle_coordinator,
    _project,
    _runtime,
    _wrap_response,
)
from concilium.infrastructure.auth.permission_guard import permission
from concilium.presentation.mcp.rate_limit import mcp_rate_limit


def register(server: FastMCP) -> None:
    """Registra as ferramentas de pipeline no servidor MCP."""

    # ── 4a. Disparar pipeline (assíncrono) ───────────────────────────────
    @server.tool()
    @permission("project:run")
    @mcp_rate_limit()
    def disparar_pipeline(
        project_id: str,
        skill_id: str | None = None,
        inputs: dict[str, Any] | None = None,
        escopo_id: str | None = None,
        plano_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispara execução de pipeline em background (não-bloqueante).

        ⚠️ USE ESTA TOOL em vez de avancar_pipeline para evitar timeouts no cliente MCP.

        Args:
            project_id: ID do projeto (vindo de listar_projetos ou iniciar_orcamento)
            skill_id: Opcional. ID da skill a executar. Se omitido, escolhe automaticamente
                      a próxima na sequência canônica.
            inputs: Inputs específicos da skill. Cronograma requer num_equipes_por_item.
            escopo_id: ID do escopo (ADR-031). Auto-inferido se único.
            plano_id: ID do plano (ADR-031). Auto-inferido se escopo tiver plano ativo único.

        Returns:
            job_id, status="EM_EXECUCAO", disparado_em

        Uso:
            # Disparar
            job = disparar_pipeline(project_id="X", skill_id="04-cronograma")
            # → {job_id: "job-abc123", status: "EM_EXECUCAO", disparado_em: "..."}

            # Aguardar alguns segundos e consultar
            resultado = consultar_job_pipeline(job_id="job-abc123")
            # → {status: "CONCLUIDO", skill_executada: "04-cronograma", proxima_sugerida: "05-financeiro"}
        """
        from concilium.application.jobs import get_job_service

        service = get_job_service()
        job_dto = service.disparar_pipeline(project_id, skill_id, inputs, escopo_id, plano_id)
        return _wrap_response(job_dto.model_dump())

    # ── 4b. Consultar job de pipeline ────────────────────────────────────
    @server.tool()
    @permission("project:read")
    @mcp_rate_limit()
    def consultar_job_pipeline(job_id: str) -> dict[str, Any]:
        """Consulta status e resultado de um job de pipeline disparado com disparar_pipeline.

        Args:
            job_id: ID do job retornado por disparar_pipeline

        Returns:
            status (PENDENTE/EM_EXECUCAO/CONCLUIDO/ERRO), resultado (se CONCLUIDO), erro (se ERRO)

        Status possíveis:
            - PENDENTE: Job criado mas ainda não iniciou
            - EM_EXECUCAO: Skill em execução
            - CONCLUIDO: Skill executada com sucesso
            - ERRO: Erro durante execução
        """
        from concilium.application.jobs import get_job_service

        service = get_job_service()
        try:
            job_dto = service.consultar_job(job_id)
            return _wrap_response(job_dto.model_dump())
        except ValueError as e:
            return _wrap_response({"error": str(e)})

    # ── 4c. Listar jobs de pipeline ──────────────────────────────────────
    @server.tool()
    @permission("project:read")
    @mcp_rate_limit()
    def listar_jobs_pipeline(project_id: str | None = None) -> dict[str, Any]:
        """Lista todos os jobs de pipeline (opcionalmente filtrados por projeto).

        Args:
            project_id: Opcional. Se fornecido, retorna apenas jobs deste projeto.

        Returns:
            Lista de jobs com status e timestamps, estatísticas do sistema
        """
        from concilium.application.jobs import get_job_service

        service = get_job_service()
        job_list_dto = service.listar_jobs(project_id)
        return _wrap_response(job_list_dto.model_dump())

    # ── 4d. Estatísticas do sistema de jobs ──────────────────────────────
    @server.tool()
    @permission("project:read")
    @mcp_rate_limit()
    def obter_estatisticas_jobs() -> dict[str, Any]:
        """Retorna estatísticas do sistema de jobs de pipeline.

        Útil para diagnóstico de capacidade e health check do worker pool.

        Returns:
            Configuração (max_concurrent_jobs, TTL), contadores, health status
        """
        from concilium.application.jobs import get_job_service

        service = get_job_service()
        stats_dto = service.obter_estatisticas()
        return _wrap_response(stats_dto.model_dump())

    # ── 4. Avançar pipeline (síncrono — DEPRECATED) ──────────────────────
    @server.tool()
    @permission("project:run")
    @mcp_rate_limit()
    def avancar_pipeline(
        project_id: str,
        skill_id: str | None = None,
        inputs: dict[str, Any] | None = None,
        escopo_id: str | None = None,
        plano_id: str | None = None,
    ) -> dict[str, Any]:
        """[DEPRECATED] Executa a próxima skill pendente do pipeline (BLOQUEANTE).

        ⚠️ ATENÇÃO: Esta tool é SÍNCRONA e pode bloquear o cliente MCP por 30-120s.
        Use disparar_pipeline() + consultar_job_pipeline() para execução assíncrona.

        Args:
            project_id: ID do projeto (vindo de listar_projetos ou iniciar_orcamento)
            skill_id: Opcional. ID da skill a executar. Se omitido, escolhe automaticamente
                      a próxima na sequência canônica.
            inputs: Inputs específicos da skill. Cronograma requer num_equipes_por_item.
            escopo_id: ID do escopo (ADR-031). Auto-inferido se único.
            plano_id: ID do plano (ADR-031). Auto-inferido se escopo tiver plano ativo único.

        Returns:
            skill_executada, status, validacoes, próxima_sugerida
        """
        rt = _runtime()
        store = _project(project_id)

        from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id

        eid = _resolve_escopo_id(store, escopo_id)
        es = store.escopo(eid)
        resolved_plano = plano_id
        if resolved_plano is None:
            active = es.active_plan()
            if active is None:
                return _wrap_response(
                    {"error": (f"Nenhum plano ativo no escopo '{eid}'. Use criar_plano antes de avancar_pipeline.")}
                )
            resolved_plano = active.plano_id
        ps = es.plan(resolved_plano)
        return _run_pipeline_on_plano(rt, store, ps, skill_id, inputs or {})


# ── ADR-031: helper para executar pipeline em PlanoStore ──────────────────────


def _rpl_executadas_ok(log_entries: list) -> set[str]:
    return {e["skill"] for e in log_entries if e.get("status") == "OK"}


def _rpl_next_pending(executadas_ok: set[str]) -> list[str]:
    return [s for s in CANONICAL_SKILL_ORDER if s not in executadas_ok]


def _rpl_next_sugerida(executadas_after: set[str]) -> str | None:
    proximas = [s for s in CANONICAL_SKILL_ORDER if s not in executadas_after]
    return proximas[0] if proximas else None


def _rpl_artifacts_out(artifacts: list) -> list[dict]:
    return [
        {
            "artifact_id": a.meta.artifact_id,
            "kind": a.meta.kind.value,
            "schema_name": a.meta.schema_name,
            "schema_version": a.meta.schema_version,
            "created_at": a.meta.created_at.isoformat(),
            "content_hash": a.meta.content_hash,
        }
        for a in artifacts
    ]


def _rpl_build_result(r: Any, skill_id: str, proxima_sugerida: str | None, ps: Any) -> dict:
    return {
        "skill_executada": skill_id,
        "status": "ERRO" if r.has_errors else "OK",
        "validacoes": [{"codigo": x.codigo, "status": x.status, "mensagem": x.mensagem} for x in r.validacoes],
        "artifacts": _rpl_artifacts_out(r.artifacts),
        "proxima_sugerida": proxima_sugerida,
        "plano_id": ps.plano_id,
    }


def _run_pipeline_on_plano(rt: Any, store: Any, ps: Any, skill_id: str | None, inputs: dict) -> dict:
    """Executa pipeline dentro de um PlanoStore (ADR-031 §D3)."""
    executadas_ok = _rpl_executadas_ok(ps.read_invocations())

    if skill_id is None:
        pendentes = _rpl_next_pending(executadas_ok)
        if not pendentes:
            return _wrap_response({"info": "Pipeline completo. Use aprovar_plano para congelar."})
        skill_id = pendentes[0]

    _get_or_create_trace_id()
    try:
        # ADR-035: Usa o Coordenador para garantir governança
        coord = _lifecycle_coordinator()
        r = coord.avancar_plano(skill_id, store, ps, inputs=inputs)
    except ConciliumRuntimeError as e:
        return _wrap_response({"skill_executada": skill_id, "status": "ERRO_PRECONDICAO", "erro": str(e)})
    except Exception as e:
        return _wrap_response({"skill_executada": skill_id, "status": "ERRO_EXCECAO", "erro": str(e)})

    proxima_sugerida = _rpl_next_sugerida(_rpl_executadas_ok(ps.read_invocations()))
    return _wrap_response(_rpl_build_result(r, skill_id, proxima_sugerida, ps))
