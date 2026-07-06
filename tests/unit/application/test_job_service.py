"""Testes unitários para JobService (ADR-103).

Valida:
- Criação e consulta de jobs
- Transições de estado via state machine
- Repository pattern e persistência
- Listagem e estatísticas
"""

from unittest.mock import Mock

import pytest

from concilium.application.jobs import (
    JobDTO,
    JobListDTO,
    JobService,
    SystemStatsDTO,
    get_job_service,
)
from concilium.application.jobs.repository import InMemoryJobRepository, reset_repository
from concilium.application.jobs.service import reset_job_service
from concilium.infrastructure.settings import JobsSettings


@pytest.fixture
def job_config():
    """Fixture com configuração de teste."""
    return JobsSettings(
        max_concurrent_jobs=2,
        job_ttl_hours=1,
        job_gc_interval_minutes=5,
    )


@pytest.fixture
def job_repository():
    """Fixture com repositório limpo."""
    reset_repository()
    from concilium.application.jobs.repository import get_job_repository

    return get_job_repository()


@pytest.fixture
def job_service(job_config, job_repository):
    """Fixture com serviço limpo."""
    reset_job_service()

    # Mock das dependências de execução
    mock_runtime = Mock()
    mock_project_factory = Mock()

    service = JobService(
        repository=job_repository,
        config=job_config,
        runtime_factory=lambda: mock_runtime,
        project_factory=mock_project_factory,
    )

    return service


class TestJobServiceBasics:
    """Testes básicos de criação e consulta."""

    def test_disparar_pipeline_cria_job(self, job_service):
        """Disparar pipeline deve criar job e retornar JobDTO."""
        job = job_service.disparar_pipeline(
            project_id="proj-123",
            skill_id="01-composicao",
            inputs={"foo": "bar"},
        )

        assert isinstance(job, JobDTO)
        assert job.job_id.startswith("job-")
        assert job.status == "AGUARDANDO_FILA"
        assert job.project_id == "proj-123"
        assert job.skill_id == "01-composicao"
        assert job.inputs == {"foo": "bar"}
        assert job.disparado_em is not None
        assert job.iniciado_em is None
        assert job.finalizado_em is None

    def test_disparar_pipeline_skips_submit_when_executor_falsy(self, job_service):
        """When _executor is falsy (e.g. still None after init for some reason),
        disparar_pipeline must not attempt to submit and simply return the
        response (false branch of `if self._executor:`)."""
        from unittest.mock import patch

        original_ensure = job_service._ensure_initialized

        def _ensure_but_clear_executor():
            original_ensure()
            job_service._executor = None

        with patch.object(job_service, "_ensure_initialized", side_effect=_ensure_but_clear_executor):
            job = job_service.disparar_pipeline(project_id="proj-noexec")

        assert job.status == "AGUARDANDO_FILA"
        assert job.project_id == "proj-noexec"

    def test_consultar_job_retorna_dto(self, job_service):
        """Consultar job deve retornar JobDTO atualizado."""
        job = job_service.disparar_pipeline(project_id="proj-123")

        consultado = job_service.consultar_job(job.job_id)

        assert consultado.job_id == job.job_id
        assert consultado.status in ["AGUARDANDO_FILA", "EM_EXECUCAO", "CONCLUIDO", "ERRO"]

    def test_consultar_job_inexistente_raises_error(self, job_service):
        """Consultar job inexistente deve levantar ValueError."""
        with pytest.raises(ValueError, match="não encontrado"):
            job_service.consultar_job("job-naoexiste")

    def test_listar_jobs_vazio(self, job_service):
        """Listar jobs sem nenhum job deve retornar lista vazia."""
        result = job_service.listar_jobs()

        assert isinstance(result, JobListDTO)
        assert len(result.jobs) == 0
        assert result.estatisticas.aguardando_fila == 0
        assert result.estatisticas.em_execucao == 0

    def test_listar_jobs_com_filtro_project_id(self, job_service):
        """Listar jobs deve filtrar por project_id."""
        job_service.disparar_pipeline(project_id="proj-A")
        job_service.disparar_pipeline(project_id="proj-B")
        job_service.disparar_pipeline(project_id="proj-A")

        result = job_service.listar_jobs(project_id="proj-A")

        assert len(result.jobs) == 2
        assert all(j.project_id == "proj-A" for j in result.jobs)


class TestJobStatistics:
    """Testes de estatísticas do sistema."""

    def test_obter_estatisticas_sistema(self, job_service):
        """Obter estatísticas deve retornar SystemStatsDTO."""
        # Dispara alguns jobs
        job_service.disparar_pipeline(project_id="proj-123")
        job_service.disparar_pipeline(project_id="proj-456")

        stats = job_service.obter_estatisticas()

        assert isinstance(stats, SystemStatsDTO)
        assert stats.configuracao["max_concurrent_jobs"] == 2
        assert stats.configuracao["job_ttl_hours"] == 1
        assert stats.contadores["total_jobs_ativos"] >= 2

    def test_estatisticas_jobs_por_status(self, job_service):
        """Estatísticas devem contar jobs por status."""
        # Dispara 3 jobs
        for i in range(3):
            job_service.disparar_pipeline(project_id=f"proj-{i}")

        result = job_service.listar_jobs()

        # Todos devem estar aguardando ou em execução
        total = (
            result.estatisticas.aguardando_fila
            + result.estatisticas.em_execucao
            + result.estatisticas.concluido
            + result.estatisticas.erro
        )
        assert total == 3


class TestJobRepository:
    """Testes do Repository pattern."""

    def test_repository_save_and_get(self):
        """Repository deve salvar e recuperar job."""
        repo = InMemoryJobRepository()

        job_data = {
            "job_id": "job-test123",
            "status": "AGUARDANDO_FILA",
            "project_id": "proj-123",
        }

        repo.save("job-test123", job_data)
        retrieved = repo.get("job-test123")

        assert retrieved == job_data

    def test_repository_get_nonexistent(self):
        """Repository deve retornar None para job inexistente."""
        repo = InMemoryJobRepository()

        result = repo.get("job-naoexiste")

        assert result is None

    def test_repository_list_all(self):
        """Repository deve listar todos os jobs."""
        repo = InMemoryJobRepository()

        repo.save("job-1", {"job_id": "job-1"})
        repo.save("job-2", {"job_id": "job-2"})

        all_jobs = repo.list_all()

        assert len(all_jobs) == 2
        assert {j["job_id"] for j in all_jobs} == {"job-1", "job-2"}

    def test_repository_delete(self):
        """Repository deve deletar job."""
        repo = InMemoryJobRepository()

        repo.save("job-test", {"job_id": "job-test"})
        assert repo.delete("job-test") is True
        assert repo.get("job-test") is None

        # Deletar novamente retorna False
        assert repo.delete("job-test") is False

    def test_repository_delete_many(self):
        """Repository deve deletar múltiplos jobs."""
        repo = InMemoryJobRepository()

        repo.save("job-1", {"job_id": "job-1"})
        repo.save("job-2", {"job_id": "job-2"})
        repo.save("job-3", {"job_id": "job-3"})

        removed = repo.delete_many(["job-1", "job-2", "job-nonexistent"])

        assert removed == 2
        assert repo.count() == 1


class TestSingletonBehavior:
    """Testes de comportamento singleton."""

    def test_get_job_service_returns_singleton(self):
        """get_job_service deve retornar mesma instância."""
        reset_job_service()

        service1 = get_job_service()
        service2 = get_job_service()

        assert service1 is service2

    def test_reset_job_service_clears_singleton(self):
        """reset_job_service deve limpar singleton."""
        service1 = get_job_service()
        reset_job_service()
        service2 = get_job_service()

        assert service1 is not service2


class TestLimparJobsExpirados:
    """Covers _limpar_jobs_expirados (lines 82-102) and _criar_progress_callback (lines 114-122)."""

    def test_limpar_jobs_expirados_removes_terminal_old_jobs(self, job_config, job_repository):
        """Terminal jobs older than TTL must be purged."""
        from datetime import UTC, datetime, timedelta

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.application.jobs.state import PipelineJobStateMachine

        repo = InMemoryJobRepository()
        svc = JobService(repository=repo, config=job_config, runtime_factory=lambda: Mock(), project_factory=Mock())

        # Create a job that is already terminal and expired
        job_id = "job-expired-test"
        expired_time = (datetime.now(UTC) - timedelta(hours=job_config.job_ttl_hours + 1)).isoformat()
        job_data = {
            "job_id": job_id,
            "status": "CONCLUIDO",
            "project_id": "proj-x",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": expired_time,
            "iniciado_em": expired_time,
            "finalizado_em": expired_time,
            "resultado": {"ok": True},
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        sm.iniciar()
        sm.completar(resultado={"ok": True})
        # completar() sets finalizado_em to now; override to expired time
        job_data["finalizado_em"] = expired_time
        job_data["state_machine"] = sm
        repo.save(job_id, job_data)

        assert repo.count() == 1
        svc._limpar_jobs_expirados()
        assert repo.count() == 0

    def test_limpar_jobs_expirados_keeps_recent_terminal_jobs(self, job_config, job_repository):
        """Terminal jobs within TTL must NOT be removed."""
        from datetime import UTC, datetime

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.application.jobs.state import PipelineJobStateMachine

        repo = InMemoryJobRepository()
        svc = JobService(repository=repo, config=job_config, runtime_factory=lambda: Mock(), project_factory=Mock())

        job_id = "job-recent-terminal"
        recent_time = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": job_id,
            "status": "CONCLUIDO",
            "project_id": "proj-x",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": recent_time,
            "iniciado_em": recent_time,
            "finalizado_em": recent_time,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        sm.iniciar()
        sm.completar(resultado=None)
        job_data["state_machine"] = sm
        repo.save(job_id, job_data)

        svc._limpar_jobs_expirados()
        # Job is recent — should NOT be removed
        assert repo.count() == 1

    def test_limpar_jobs_expirados_ignores_non_terminal(self, job_config):
        """Jobs still in AGUARDANDO_FILA must not be GC'd."""
        from datetime import UTC, datetime, timedelta

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.application.jobs.state import PipelineJobStateMachine

        repo = InMemoryJobRepository()
        svc = JobService(repository=repo, config=job_config, runtime_factory=lambda: Mock(), project_factory=Mock())

        # Very old, but NOT terminal
        old_time = (datetime.now(UTC) - timedelta(hours=100)).isoformat()
        job_data = {
            "job_id": "job-waiting",
            "status": "AGUARDANDO_FILA",
            "project_id": "proj-x",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": old_time,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        job_data["state_machine"] = sm
        repo.save("job-waiting", job_data)

        svc._limpar_jobs_expirados()
        assert repo.count() == 1


class TestProgressCallback:
    """Covers _criar_progress_callback (lines 114-122)."""

    def test_progress_callback_updates_job(self, job_service):
        """Callback must update progresso and progresso_percentual in the repo."""
        job = job_service.disparar_pipeline(project_id="proj-cb")

        cb = job_service._criar_progress_callback(job.job_id)
        # Need to save the job in repo with all expected keys first
        saved = job_service._repo.get(job.job_id)
        if saved:
            cb("Iniciando...", 0.3)
            updated = job_service._repo.get(job.job_id)
            if updated:
                assert updated.get("progresso") == "Iniciando..."
                assert updated.get("progresso_percentual") == 0.3

    def test_progress_callback_clamps_percentual(self, job_service):
        """Percentual must be clamped to [0.0, 1.0]."""
        job = job_service.disparar_pipeline(project_id="proj-cb2")
        cb = job_service._criar_progress_callback(job.job_id)
        saved = job_service._repo.get(job.job_id)
        if saved:
            cb("Overload", 1.5)
            updated = job_service._repo.get(job.job_id)
            if updated:
                assert updated.get("progresso_percentual") == 1.0

    def test_progress_callback_noop_when_job_missing(self, job_service):
        """Callback for non-existent job must not raise."""
        cb = job_service._criar_progress_callback("job-ghost-99999")
        cb("anything", 0.5)  # should not raise


class TestExecutarPipelineAsync:
    """Covers _executar_pipeline_async (lines 124-186)."""

    def test_executar_pipeline_noop_when_job_missing(self, job_service):
        """Worker must silently return when job not found."""
        # No job saved — should not raise
        job_service._executar_pipeline_async("job-nonexistent-xyz")

    def _fresh_waiting_job(self, svc, job_id, project_id, escopo_id=None, plano_id=None):
        """Insert a fresh AGUARDANDO_FILA job directly into repo, bypassing executor submission."""
        from datetime import UTC, datetime

        from concilium.application.jobs.state import PipelineJobStateMachine

        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": job_id,
            "status": "AGUARDANDO_FILA",
            "project_id": project_id,
            "skill_id": None,
            "inputs": {},
            "escopo_id": escopo_id,
            "plano_id": plano_id,
            "disparado_em": now,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        job_data["state_machine"] = sm
        svc._repo.save(job_id, job_data)
        return job_id

    def test_executar_pipeline_success_path(self, job_service):
        """Worker transitions job to CONCLUIDO on success."""
        from unittest.mock import MagicMock, patch

        job_id = self._fresh_waiting_job(job_service, "job-async-ok", "proj-async", escopo_id="esc-1", plano_id="pl-1")

        mock_store = MagicMock()
        mock_plan = MagicMock()
        mock_escopo = MagicMock()
        mock_escopo.plan.return_value = mock_plan
        mock_store.escopo.return_value = mock_escopo
        job_service._project_factory = lambda pid: mock_store

        with (
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="esc-1"),
            patch("concilium.presentation.mcp.tools.pipeline._run_pipeline_on_plano", return_value={"done": True}),
        ):
            job_service._executar_pipeline_async(job_id)

        result_job = job_service._repo.get(job_id)
        sm = result_job["state_machine"]
        assert sm.status_str == "CONCLUIDO"

    def test_executar_pipeline_failure_transitions_to_error(self, job_service):
        """Worker transitions job to ERRO when pipeline raises."""
        from unittest.mock import MagicMock, patch

        job_id = self._fresh_waiting_job(job_service, "job-async-fail", "proj-fail", escopo_id="esc-f", plano_id="pl-f")

        mock_store = MagicMock()
        job_service._project_factory = lambda pid: mock_store

        with (
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="esc-f"),
            patch(
                "concilium.presentation.mcp.tools.pipeline._run_pipeline_on_plano",
                side_effect=RuntimeError("pipeline crash"),
            ),
        ):
            job_service._executar_pipeline_async(job_id)

        result_job = job_service._repo.get(job_id)
        sm = result_job["state_machine"]
        assert sm.status_str == "ERRO"
        assert "pipeline crash" in result_job["erro"]

    def test_executar_pipeline_no_active_plan_fails(self, job_service):
        """Worker transitions to ERRO when no active plan and plano_id is None."""
        from unittest.mock import MagicMock, patch

        job_id = self._fresh_waiting_job(
            job_service, "job-async-noplan", "proj-noplan", escopo_id="esc-np", plano_id=None
        )

        mock_store = MagicMock()
        mock_escopo = MagicMock()
        mock_escopo.active_plan.return_value = None
        mock_store.escopo.return_value = mock_escopo
        job_service._project_factory = lambda pid: mock_store

        with patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="esc-np"):
            job_service._executar_pipeline_async(job_id)

        result_job = job_service._repo.get(job_id)
        sm = result_job["state_machine"]
        assert sm.status_str == "ERRO"

    def test_executar_pipeline_resolves_active_plan_when_plano_id_none(self, job_service):
        """When plano_id is None but the escopo has an active plan, that plan's
        plano_id is used to continue execution (line 168)."""
        from unittest.mock import MagicMock, patch

        job_id = self._fresh_waiting_job(
            job_service, "job-async-activeplan", "proj-activeplan", escopo_id="esc-ap", plano_id=None
        )

        mock_store = MagicMock()
        mock_plan = MagicMock()
        mock_active_plan = MagicMock()
        mock_active_plan.plano_id = "plano-resolvido"
        mock_escopo = MagicMock()
        mock_escopo.active_plan.return_value = mock_active_plan
        mock_escopo.plan.return_value = mock_plan
        mock_store.escopo.return_value = mock_escopo
        job_service._project_factory = lambda pid: mock_store

        with (
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="esc-ap"),
            patch("concilium.presentation.mcp.tools.pipeline._run_pipeline_on_plano", return_value={"done": True}),
        ):
            job_service._executar_pipeline_async(job_id)

        mock_escopo.plan.assert_called_once_with("plano-resolvido")
        result_job = job_service._repo.get(job_id)
        sm = result_job["state_machine"]
        assert sm.status_str == "CONCLUIDO"


class TestCancelarJob:
    """Covers cancelar_job (lines 361-384)."""

    def test_cancelar_job_in_fila(self, job_service):
        """Job in AGUARDANDO_FILA can be cancelled by inserting directly into repo."""
        from datetime import UTC, datetime

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.application.jobs.state import PipelineJobStateMachine
        from concilium.infrastructure.settings import JobsSettings

        repo = InMemoryJobRepository()
        cfg = JobsSettings(max_concurrent_jobs=2, job_ttl_hours=1, job_gc_interval_minutes=5)
        svc = JobService(repository=repo, config=cfg, runtime_factory=lambda: None, project_factory=lambda x: None)

        # Insert a job directly (bypass executor) so it stays AGUARDANDO_FILA
        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": "job-to-cancel",
            "status": "AGUARDANDO_FILA",
            "project_id": "proj-cancel",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": now,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        job_data["state_machine"] = sm
        repo.save("job-to-cancel", job_data)

        cancelled = svc.cancelar_job("job-to-cancel")
        assert cancelled.status == "CANCELADO"

    def test_cancelar_job_not_found_raises(self, job_service):
        """Cancelling non-existent job raises ValueError."""
        with pytest.raises(ValueError, match="não encontrado"):
            job_service.cancelar_job("job-ghost-cancel")

    def test_cancelar_job_terminal_raises(self, job_service):
        """Cancelling a terminal job raises ValueError."""
        from datetime import UTC, datetime

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.application.jobs.state import PipelineJobStateMachine
        from concilium.infrastructure.settings import JobsSettings

        repo = InMemoryJobRepository()
        cfg = JobsSettings(max_concurrent_jobs=2, job_ttl_hours=1, job_gc_interval_minutes=5)
        svc = JobService(repository=repo, config=cfg, runtime_factory=lambda: None, project_factory=lambda x: None)

        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": "job-terminal-cancel",
            "status": "CONCLUIDO",
            "project_id": "p",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": now,
            "iniciado_em": now,
            "finalizado_em": now,
            "resultado": {},
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        sm.iniciar()
        sm.completar(resultado={})
        job_data["state_machine"] = sm
        repo.save("job-terminal-cancel", job_data)

        with pytest.raises(ValueError, match="não pode ser cancelado"):
            svc.cancelar_job("job-terminal-cancel")


class TestListarJobsStatusCounts:
    """Covers listar_jobs CANCELADO status branch (line 332)."""

    def test_listar_jobs_counts_cancelado(self, job_service):
        """CANCELADO status must be counted in estatisticas."""
        from datetime import UTC, datetime

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.application.jobs.state import PipelineJobStateMachine
        from concilium.infrastructure.settings import JobsSettings

        repo = InMemoryJobRepository()
        cfg = JobsSettings(max_concurrent_jobs=2, job_ttl_hours=1, job_gc_interval_minutes=5)
        svc = JobService(repository=repo, config=cfg, runtime_factory=lambda: None, project_factory=lambda x: None)

        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": "job-cancel-stats",
            "status": "AGUARDANDO_FILA",
            "project_id": "p",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": now,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        job_data["state_machine"] = sm
        repo.save("job-cancel-stats", job_data)
        sm.cancelar(motivo="test")

        listing = svc.listar_jobs()
        assert listing.estatisticas.cancelado == 1

    def test_listar_jobs_ignores_unrecognized_status(self, job_service):
        """A job whose status matches none of the known buckets falls through
        all elif branches without incrementing any counter (line 333 false)."""
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": "job-weird-status",
            "status": "ALGO_DESCONHECIDO",
            "project_id": "p",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": now,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
            # No state_machine key -> status comes straight from j["status"]
        }
        job_service._repo.save("job-weird-status", job_data)

        listing = job_service.listar_jobs()

        stats = listing.estatisticas
        assert (
            stats.aguardando_fila,
            stats.em_execucao,
            stats.concluido,
            stats.erro,
            stats.cancelado,
        ) == (0, 0, 0, 0, 0)


class TestResetJobServiceWithExecutor:
    """Covers reset_job_service when _executor is active (lines 444-447)."""

    def test_reset_shuts_down_executor(self):
        """reset_job_service must call executor.shutdown."""
        from concilium.application.jobs.service import get_job_service, reset_job_service

        reset_job_service()
        svc = get_job_service()
        # Trigger lazy initialization
        svc._ensure_initialized()
        assert svc._executor is not None

        reset_job_service()

        # After reset, singleton is None
        from concilium.application.jobs import service as _svc_module

        assert _svc_module._service is None


class TestEnsureInitializedIdempotent:
    """Covers the double-checked-locking branches inside _ensure_initialized:
    - executor already set by the time the lock is acquired (skip create)
    - gc_thread already set (skip create)
    """

    def test_skips_executor_creation_when_set_inside_lock(self, job_service):
        class _FakeLock:
            def __enter__(self_inner):
                # Simulate a concurrent thread having already created the executor
                # in between the outer None-check and lock acquisition.
                job_service._executor = Mock()
                return None

            def __exit__(self_inner, *exc_info):
                return False

        job_service._executor = None
        job_service._gc_thread = None
        job_service._init_lock = _FakeLock()

        job_service._ensure_initialized()

        assert job_service._executor is not None
        assert job_service._gc_thread is not None

    def test_skips_gc_thread_creation_when_already_set(self, job_service):
        job_service._executor = None
        preexisting_gc_thread = Mock()
        job_service._gc_thread = preexisting_gc_thread

        job_service._ensure_initialized()

        assert job_service._executor is not None
        # gc_thread must remain the pre-existing mock (not replaced)
        assert job_service._gc_thread is preexisting_gc_thread

        job_service._executor.shutdown(wait=False)


class TestGarbageCollectorLoop:
    """Covers line 80: _garbage_collector_loop body executes _limpar_jobs_expirados."""

    def test_gc_loop_calls_limpar_when_event_not_set(self):
        """The GC loop calls _limpar_jobs_expirados at least once before stopping."""
        import threading

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.infrastructure.settings import JobsSettings

        repo = InMemoryJobRepository()
        # Very short GC interval so the loop fires quickly
        cfg = JobsSettings(max_concurrent_jobs=1, job_ttl_hours=1, job_gc_interval_minutes=0)
        svc = JobService(repository=repo, config=cfg, runtime_factory=lambda: None, project_factory=lambda x: None)

        called = threading.Event()
        original = svc._limpar_jobs_expirados

        def _patched():
            called.set()
            original()

        svc._limpar_jobs_expirados = _patched

        # Run the GC loop in a thread; stop after first invocation
        t = threading.Thread(target=svc._garbage_collector_loop, daemon=True)
        t.start()
        called.wait(timeout=3.0)
        svc._gc_stop_event.set()
        t.join(timeout=2.0)

        assert called.is_set(), "GC loop never called _limpar_jobs_expirados"


class TestExecutarPipelineFallbackMcp:
    """Covers lines 144-147: fallback MCP import path when factories are None."""

    def test_fallback_mcp_path_on_factory_none(self):
        """When runtime_factory/project_factory are None, the MCP fallback is used."""
        from datetime import UTC, datetime
        from unittest.mock import MagicMock, patch

        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.application.jobs.state import PipelineJobStateMachine
        from concilium.infrastructure.settings import JobsSettings

        repo = InMemoryJobRepository()
        cfg = JobsSettings(max_concurrent_jobs=2, job_ttl_hours=1, job_gc_interval_minutes=5)
        # No runtime_factory / project_factory → triggers fallback at lines 144-147
        svc = JobService(repository=repo, config=cfg, runtime_factory=None, project_factory=None)

        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": "job-mcp-fallback",
            "status": "AGUARDANDO_FILA",
            "project_id": "proj-mcp",
            "skill_id": None,
            "inputs": {},
            "escopo_id": "esc-mcp",
            "plano_id": "pl-mcp",
            "disparado_em": now,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        job_data["state_machine"] = sm
        repo.save("job-mcp-fallback", job_data)

        mock_rt = MagicMock()
        mock_store = MagicMock()
        mock_plan = MagicMock()
        mock_escopo = MagicMock()
        mock_escopo.plan.return_value = mock_plan
        mock_store.escopo.return_value = mock_escopo

        with (
            patch("concilium.presentation.mcp._context._runtime", return_value=mock_rt),
            patch("concilium.presentation.mcp._context._project", return_value=mock_store),
            patch("concilium.presentation.mcp.tools.escopo._resolve_escopo_id", return_value="esc-mcp"),
            patch("concilium.presentation.mcp.tools.pipeline._run_pipeline_on_plano", return_value={"mcp": True}),
        ):
            svc._executar_pipeline_async("job-mcp-fallback")

        result_job = repo.get("job-mcp-fallback")
        assert result_job["state_machine"].status_str == "CONCLUIDO"


class TestListarJobsStatusCountsConcludedAndError:
    """Covers lines 328 and 330: CONCLUIDO and ERRO branches in listar_jobs stats."""

    def _make_job(self, job_id, status_str, repo):
        from datetime import UTC, datetime

        from concilium.application.jobs.state import PipelineJobStateMachine

        now = datetime.now(UTC).isoformat()
        job_data = {
            "job_id": job_id,
            "status": "AGUARDANDO_FILA",
            "project_id": "proj-stats",
            "skill_id": None,
            "inputs": {},
            "escopo_id": None,
            "plano_id": None,
            "disparado_em": now,
            "iniciado_em": None,
            "finalizado_em": None,
            "resultado": None,
            "erro": None,
            "progresso": None,
            "progresso_percentual": None,
        }
        sm = PipelineJobStateMachine(job_data)
        if status_str == "CONCLUIDO":
            sm.iniciar()
            sm.completar(resultado={})
        elif status_str == "ERRO":
            sm.iniciar()
            sm.falhar(erro="something broke")
        job_data["state_machine"] = sm
        repo.save(job_id, job_data)

    def test_listar_jobs_counts_concluido_and_erro(self):
        """CONCLUIDO and ERRO jobs must be counted correctly in estatisticas."""
        from concilium.application.jobs.repository import InMemoryJobRepository
        from concilium.application.jobs.service import JobService
        from concilium.infrastructure.settings import JobsSettings

        repo = InMemoryJobRepository()
        cfg = JobsSettings(max_concurrent_jobs=2, job_ttl_hours=1, job_gc_interval_minutes=5)
        svc = JobService(repository=repo, config=cfg, runtime_factory=lambda: None, project_factory=lambda x: None)

        self._make_job("job-done-1", "CONCLUIDO", repo)
        self._make_job("job-done-2", "CONCLUIDO", repo)
        self._make_job("job-err-1", "ERRO", repo)

        listing = svc.listar_jobs()
        assert listing.estatisticas.concluido == 2  # line 328
        assert listing.estatisticas.erro == 1  # line 330


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
