"""Serviço de jobs de pipeline - casos de uso.

ADR-103: Jobs na Camada de Aplicação

Este módulo contém a lógica de negócio para gerenciamento de jobs assíncronos,
desacoplada da camada de apresentação (MCP/API).
"""

from __future__ import annotations

import sys
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

from concilium.application.jobs.models import JobDTO, JobListDTO, JobStatsDTO, SystemStatsDTO
from concilium.application.jobs.repository import JobRepository, get_job_repository
from concilium.application.jobs.state import PipelineJobStateMachine
from concilium.infrastructure.settings import JobsSettings, get_jobs


class JobService:
    """Serviço de gerenciamento de jobs de pipeline.

    Responsabilidades:
    - Disparar execução assíncrona de jobs
    - Consultar status e resultados
    - Listar jobs com filtros
    - Fornecer estatísticas do sistema
    - Gerenciar worker pool e garbage collection
    """

    def __init__(
        self,
        repository: JobRepository | None = None,
        config: JobsSettings | None = None,
        # Injeção de dependências para execução de pipeline
        runtime_factory: Callable | None = None,
        project_factory: Callable[[str], Any] | None = None,
    ):
        """Inicializa o serviço.

        Args:
            repository: Repository para persistência (None = usa singleton)
            config: Configuração (None = usa singleton)
            runtime_factory: Factory para obter runtime (None = usa padrão MCP)
            project_factory: Factory para obter project store (None = usa padrão MCP)
        """
        self._repo = repository or get_job_repository()
        self._config = config or get_jobs()
        self._runtime_factory = runtime_factory
        self._project_factory = project_factory

        self._executor: ThreadPoolExecutor | None = None
        self._gc_thread: threading.Thread | None = None
        self._gc_stop_event = threading.Event()
        self._init_lock = threading.Lock()

    def _ensure_initialized(self) -> None:
        """Garante que worker pool e GC estão inicializados (lazy init)."""
        if self._executor is None:
            with self._init_lock:
                if self._executor is None:
                    self._executor = ThreadPoolExecutor(
                        max_workers=self._config.max_concurrent_jobs, thread_name_prefix="pipeline-worker"
                    )

                if self._gc_thread is None:
                    self._gc_thread = threading.Thread(
                        target=self._garbage_collector_loop, daemon=True, name="pipeline-gc"
                    )
                    self._gc_thread.start()

    def _garbage_collector_loop(self) -> None:
        """Loop de garbage collection que limpa jobs finalizados antigos."""
        while not self._gc_stop_event.wait(timeout=self._config.job_gc_interval_minutes * 60):
            self._limpar_jobs_expirados()

    def _limpar_jobs_expirados(self) -> None:
        """Remove jobs finalizados há mais de job_ttl_hours."""
        agora = datetime.now(UTC)
        cutoff = agora - timedelta(hours=self._config.job_ttl_hours)

        jobs = self._repo.list_all()
        jobs_para_remover = []

        for job in jobs:
            sm: PipelineJobStateMachine | None = job.get("state_machine")
            if sm and sm.is_terminal and job.get("finalizado_em"):
                finalizado_em = datetime.fromisoformat(job["finalizado_em"])
                if finalizado_em < cutoff:
                    jobs_para_remover.append(job["job_id"])

        if jobs_para_remover:
            removed = self._repo.delete_many(jobs_para_remover)
            print(
                f"[pipeline-gc] Removidos {removed} jobs expirados (TTL: {self._config.job_ttl_hours}h)",
                file=sys.stderr,
            )

    def _criar_progress_callback(self, job_id: str) -> Callable[[str, float | None], None]:
        """Cria callback de progresso para uma skill.

        Args:
            job_id: ID do job

        Returns:
            Função callback(mensagem, percentual)
        """

        def callback(mensagem: str, percentual: float | None = None) -> None:
            job = self._repo.get(job_id)
            if job:
                job["progresso"] = mensagem
                if percentual is not None:
                    job["progresso_percentual"] = max(0.0, min(1.0, percentual))
                self._repo.save(job_id, job)

        return callback

    def _executar_pipeline_async(self, job_id: str) -> None:
        """Worker thread que executa o pipeline.

        Args:
            job_id: ID do job a executar
        """
        job = self._repo.get(job_id)
        if not job:
            return

        sm: PipelineJobStateMachine = job["state_machine"]

        try:
            # Transição: AGUARDANDO_FILA → EM_EXECUCAO
            sm.iniciar()
            self._repo.save(job_id, job)

            # Obtém dependências
            if self._runtime_factory is None or self._project_factory is None:
                # Fallback para imports de MCP (manter compatibilidade)
                from concilium.presentation.mcp._context import _project, _runtime

                rt = _runtime()
                store = _project(job["project_id"])
            else:
                rt = self._runtime_factory()
                store = self._project_factory(job["project_id"])

            from concilium.presentation.mcp.tools.escopo import _resolve_escopo_id
            from concilium.presentation.mcp.tools.pipeline import _run_pipeline_on_plano

            # Cria callback de progresso
            progress_callback = self._criar_progress_callback(job_id)

            eid = _resolve_escopo_id(store, job["escopo_id"])
            es = store.escopo(eid)
            resolved_plano = job["plano_id"]

            if resolved_plano is None:
                active = es.active_plan()
                if active is None:
                    sm.falhar(erro=f"Nenhum plano ativo no escopo '{eid}'")
                    self._repo.save(job_id, job)
                    return
                resolved_plano = active.plano_id

            ps = es.plan(resolved_plano)

            progress_callback("Executando skill...", 0.1)

            # Executa pipeline
            resultado = _run_pipeline_on_plano(rt, store, ps, job["skill_id"], job["inputs"])

            progress_callback("Finalizando...", 1.0)

            # Transição: EM_EXECUCAO → CONCLUIDO
            sm.completar(resultado=resultado)
            self._repo.save(job_id, job)

        except Exception as e:
            # Transição: EM_EXECUCAO → ERRO
            sm.falhar(erro=str(e))
            self._repo.save(job_id, job)

    def disparar_pipeline(
        self,
        project_id: str,
        skill_id: str | None = None,
        inputs: dict[str, Any] | None = None,
        escopo_id: str | None = None,
        plano_id: str | None = None,
    ) -> JobDTO:
        """Dispara execução de pipeline em background.

        Args:
            project_id: ID do projeto
            skill_id: ID da skill (None = próxima pendente)
            inputs: Inputs da skill
            escopo_id: ID do escopo (auto-inferido se único)
            plano_id: ID do plano (auto-inferido se único)

        Returns:
            JobDTO com job_id e status inicial
        """
        self._ensure_initialized()

        # Cria job
        job_id = f"job-{uuid.uuid4().hex[:12]}"
        job_data = {
            "job_id": job_id,
            "status": "AGUARDANDO_FILA",
            "project_id": project_id,
            "skill_id": skill_id,
            "inputs": inputs or {},
            "escopo_id": escopo_id,
            "plano_id": plano_id,
            "disparado_em": datetime.now(UTC).isoformat(),
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }

        # Cria state machine
        sm = PipelineJobStateMachine(job_data)
        job_data["state_machine"] = sm

        # Salva no repositório
        self._repo.save(job_id, job_data)

        # Calcula posição na fila
        jobs = self._repo.list_all()
        posicao_fila = sum(
            1 for j in jobs if j["status"] == "AGUARDANDO_FILA" and j["disparado_em"] < job_data["disparado_em"]
        )

        response = JobDTO(
            job_id=job_id,
            status="AGUARDANDO_FILA",
            project_id=project_id,
            skill_id=skill_id,
            escopo_id=escopo_id,
            plano_id=plano_id,
            inputs=inputs or {},
            disparado_em=job_data["disparado_em"],
            iniciado_em=None,
            finalizado_em=None,
            resultado=None,
            erro=None,
            progresso=f"Posição na fila: {posicao_fila}" if posicao_fila > 0 else "Aguardando worker...",
            progresso_percentual=None,
        )

        # Submete ao executor após montar a resposta inicial para evitar condição de corrida.
        if self._executor:
            self._executor.submit(self._executar_pipeline_async, job_id)

        return response

    def consultar_job(self, job_id: str) -> JobDTO:
        """Consulta status e resultado de um job.

        Args:
            job_id: ID do job

        Returns:
            JobDTO com status atual

        Raises:
            ValueError: Se job não encontrado
        """
        job = self._repo.get(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' não encontrado (pode ter expirado após {self._config.job_ttl_hours}h)")

        sm: PipelineJobStateMachine = job["state_machine"]

        return JobDTO(
            job_id=job["job_id"],
            status=sm.status_str,
            project_id=job["project_id"],
            skill_id=job["skill_id"],
            escopo_id=job["escopo_id"],
            plano_id=job["plano_id"],
            inputs=job["inputs"],
            disparado_em=job["disparado_em"],
            iniciado_em=job["iniciado_em"],
            finalizado_em=job["finalizado_em"],
            resultado=job["resultado"],
            erro=job["erro"],
            progresso=job.get("progresso"),
            progresso_percentual=job.get("progresso_percentual"),
        )

    def listar_jobs(self, project_id: str | None = None) -> JobListDTO:
        """Lista todos os jobs (opcionalmente filtrados por projeto).

        Args:
            project_id: Opcional. Se fornecido, retorna apenas jobs deste projeto.

        Returns:
            JobListDTO com lista de jobs e estatísticas
        """
        jobs = self._repo.list_all()

        if project_id:
            jobs = [j for j in jobs if j["project_id"] == project_id]

        # Ordena por data de disparo (mais recente primeiro)
        jobs.sort(key=lambda j: j["disparado_em"], reverse=True)

        # Estatísticas
        stats = JobStatsDTO()
        for j in jobs:
            sm: PipelineJobStateMachine | None = j.get("state_machine")
            status = sm.status_str if sm else j["status"]

            if status == "AGUARDANDO_FILA":
                stats.aguardando_fila += 1
            elif status == "EM_EXECUCAO":
                stats.em_execucao += 1
            elif status == "CONCLUIDO":
                stats.concluido += 1
            elif status == "ERRO":
                stats.erro += 1
            elif status == "CANCELADO":
                stats.cancelado += 1

        # Converte para DTOs
        job_dtos = [
            JobDTO(
                job_id=j["job_id"],
                status=j.get("state_machine").status_str if j.get("state_machine") else j["status"],
                project_id=j["project_id"],
                skill_id=j["skill_id"],
                escopo_id=j["escopo_id"],
                plano_id=j["plano_id"],
                inputs=j["inputs"],
                disparado_em=j["disparado_em"],
                iniciado_em=j["iniciado_em"],
                finalizado_em=j["finalizado_em"],
                resultado=j["resultado"],
                erro=j["erro"],
                progresso=j.get("progresso"),
                progresso_percentual=j.get("progresso_percentual"),
            )
            for j in jobs
        ]

        return JobListDTO(
            jobs=job_dtos,
            estatisticas=stats,
            max_concurrent_jobs=self._config.max_concurrent_jobs,
        )

    def cancelar_job(self, job_id: str, motivo: str = "Cancelado pelo usuário") -> JobDTO:
        """Cancela um job em fila ou em execução.

        Args:
            job_id: ID do job a cancelar.
            motivo: Motivo do cancelamento (registrado no histórico).

        Returns:
            JobDTO com status CANCELADO.

        Raises:
            ValueError: Se job não encontrado ou já em estado final.
        """
        job = self._repo.get(job_id)
        if not job:
            raise ValueError(f"Job '{job_id}' não encontrado (pode ter expirado)")
        sm: PipelineJobStateMachine = job["state_machine"]
        if not sm.pode_cancelar:
            raise ValueError(
                f"Job '{job_id}' está em estado '{sm.status_str}' e não pode ser cancelado. "
                "Apenas jobs AGUARDANDO_FILA ou EM_EXECUCAO podem ser cancelados."
            )
        sm.cancelar(motivo=motivo)
        return self.consultar_job(job_id)

    def obter_estatisticas(self) -> SystemStatsDTO:
        """Retorna estatísticas do sistema de jobs.

        Returns:
            SystemStatsDTO com configuração e contadores
        """
        jobs = self._repo.list_all()
        jobs_por_status: dict[str, int] = {}

        for job in jobs:
            sm: PipelineJobStateMachine | None = job.get("state_machine")
            status = sm.status_str if sm else job["status"]
            jobs_por_status[status] = jobs_por_status.get(status, 0) + 1

        return SystemStatsDTO(
            configuracao={
                "max_concurrent_jobs": self._config.max_concurrent_jobs,
                "job_ttl_hours": self._config.job_ttl_hours,
                "gc_interval_minutes": self._config.job_gc_interval_minutes,
            },
            contadores={
                "total_jobs_ativos": len(jobs),
                "jobs_por_status": jobs_por_status,
            },
            sistema={
                "worker_pool_ativo": self._executor is not None,
                "gc_ativo": self._gc_thread is not None and self._gc_thread.is_alive(),
            },
        )


# Singleton global
_service: JobService | None = None
_service_lock = threading.Lock()


def get_job_service() -> JobService:
    """Retorna serviço singleton.

    Returns:
        Instância de JobService
    """
    global _service

    if _service is None:
        with _service_lock:
            if _service is None:
                _service = JobService()

    return _service


def reset_job_service() -> None:
    """Reseta serviço (apenas para testes).

    WARNING: Esta função NÃO é thread-safe e deve ser usada apenas em testes.
    """
    global _service
    with _service_lock:
        if _service and _service._executor:
            _service._executor.shutdown(wait=False)
            _service._gc_stop_event.set()
        _service = None
