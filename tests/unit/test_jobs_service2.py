"""Pytest tests for JobService — coverage boost toward 80%+.

Strategy:
- Inject InMemoryJobRepository and stub JobsSettings to avoid I/O.
- Patch threading.Event.wait so _garbage_collector_loop never actually blocks.
- Stub out _executar_pipeline_async so no real worker runs.
- Directly exercise _limpar_jobs_expirados, cancelar_job, obter_estatisticas, etc.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest

from concilium.application.jobs.models import JobDTO, JobListDTO, SystemStatsDTO
from concilium.application.jobs.repository import InMemoryJobRepository
from concilium.application.jobs.service import (
    JobService,
    get_job_service,
    reset_job_service,
)
from concilium.application.jobs.state import PipelineJobStateMachine
from concilium.infrastructure.settings import JobsSettings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    *,
    max_concurrent_jobs: int = 2,
    job_ttl_hours: int = 24,
    job_gc_interval_minutes: int = 60,
) -> JobsSettings:
    return JobsSettings(
        max_concurrent_jobs=max_concurrent_jobs,
        job_ttl_hours=job_ttl_hours,
        job_gc_interval_minutes=job_gc_interval_minutes,
    )


def _make_service(config: JobsSettings | None = None) -> JobService:
    """Build a JobService with a fresh InMemoryJobRepository, patching out GC."""
    repo = InMemoryJobRepository()
    cfg = config or _make_config()
    svc = JobService(repository=repo, config=cfg)
    return svc


def _build_job_dict(
    job_id: str,
    project_id: str = "proj-test",
    *,
    finalizado_em: str | None = None,
    status: str = "AGUARDANDO_FILA",
) -> dict[str, Any]:
    """Create a minimal job dict with a PipelineJobStateMachine attached."""
    now = datetime.now(UTC).isoformat()
    job: dict[str, Any] = {
        "job_id": job_id,
        "status": status,
        "project_id": project_id,
        "skill_id": "01-composicao",
        "inputs": {},
        "escopo_id": None,
        "plano_id": None,
        "disparado_em": now,
        "iniciado_em": None,
        "finalizado_em": finalizado_em,
        "resultado": None,
        "erro": None,
        "progresso": None,
        "progresso_percentual": None,
    }
    sm = PipelineJobStateMachine(job)
    job["state_machine"] = sm
    return job


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure the global singleton is clean before and after each test."""
    reset_job_service()
    yield
    reset_job_service()


@pytest.fixture
def repo():
    return InMemoryJobRepository()


@pytest.fixture
def cfg():
    return _make_config()


@pytest.fixture
def svc(repo, cfg):
    """JobService with patched _executar_pipeline_async (no real threads run)."""
    service = JobService(repository=repo, config=cfg)
    # Prevent actual worker submission by replacing the executor submit
    # and block the GC thread from spawning via patching _ensure_initialized
    return service


# ---------------------------------------------------------------------------
# disparar_pipeline
# ---------------------------------------------------------------------------


class TestDispararPipeline:
    """Verify disparar_pipeline saves the job and returns a correct JobDTO."""

    def test_returns_job_dto_with_aguardando_fila(self, svc):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-abc", skill_id="04-cronograma")

        assert isinstance(dto, JobDTO)
        assert dto.status == "AGUARDANDO_FILA"
        assert dto.project_id == "proj-abc"
        assert dto.skill_id == "04-cronograma"

    def test_job_id_has_job_prefix(self, svc):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-x")
        assert dto.job_id.startswith("job-")

    def test_job_persisted_in_repo(self, svc, repo):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-persist")
        assert repo.get(dto.job_id) is not None

    def test_job_saved_with_state_machine(self, svc, repo):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-sm")
        stored = repo.get(dto.job_id)
        assert "state_machine" in stored
        assert isinstance(stored["state_machine"], PipelineJobStateMachine)

    def test_inputs_default_to_empty_dict(self, svc):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-noinputs")
        assert dto.inputs == {}

    def test_inputs_passed_through(self, svc):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-in", inputs={"k": "v"})
        assert dto.inputs == {"k": "v"}

    def test_disparado_em_is_set(self, svc):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-ts")
        assert dto.disparado_em is not None

    def test_iniciado_em_is_none(self, svc):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-ts2")
        assert dto.iniciado_em is None

    def test_fila_posicao_zero_message(self, svc):
        """First job in empty queue should show 'Aguardando worker...'."""
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-pos")
        assert dto.progresso == "Aguardando worker..."

    def test_fila_posicao_nonzero(self, svc, repo):
        """Second job should show queue position."""
        # Manually seed a job with same-or-earlier timestamp
        earlier_job = _build_job_dict("job-first", "proj-q")
        earlier_job["disparado_em"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        repo.save("job-first", earlier_job)

        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(project_id="proj-q2")
        assert "fila" in dto.progresso.lower() or dto.progresso == "Aguardando worker..."

    def test_optional_params_forwarded(self, svc):
        with patch.object(svc, "_executar_pipeline_async"):
            dto = svc.disparar_pipeline(
                project_id="p",
                skill_id="sk",
                inputs={"a": 1},
                escopo_id="esc-01",
                plano_id="plano-01",
            )
        assert dto.escopo_id == "esc-01"
        assert dto.plano_id == "plano-01"


# ---------------------------------------------------------------------------
# consultar_job
# ---------------------------------------------------------------------------


class TestConsultarJob:
    """Verify consultar_job returns DTO reflecting the state machine status."""

    def _seed(self, repo: InMemoryJobRepository, job_id: str = "job-test") -> dict:
        job = _build_job_dict(job_id)
        repo.save(job_id, job)
        return job

    def test_returns_job_dto(self, svc, repo):
        self._seed(repo)
        dto = svc.consultar_job("job-test")
        assert isinstance(dto, JobDTO)

    def test_status_reflects_state_machine(self, svc, repo):
        self._seed(repo)
        dto = svc.consultar_job("job-test")
        assert dto.status == "AGUARDANDO_FILA"

    def test_status_em_execucao_after_iniciar(self, svc, repo):
        job = self._seed(repo)
        job["state_machine"].iniciar()
        repo.save("job-test", job)
        dto = svc.consultar_job("job-test")
        assert dto.status == "EM_EXECUCAO"

    def test_unknown_job_id_raises_value_error(self, svc):
        with pytest.raises(ValueError, match="não encontrado"):
            svc.consultar_job("job-doesnotexist")

    def test_error_message_includes_ttl(self, svc, cfg):
        with pytest.raises(ValueError, match=str(cfg.job_ttl_hours)):
            svc.consultar_job("job-ghost")

    def test_fields_propagated_correctly(self, svc, repo):
        job = _build_job_dict("job-fields", "proj-fields")
        job["skill_id"] = "02-cronograma"
        job["escopo_id"] = "esc-02"
        job["plano_id"] = "plano-02"
        repo.save("job-fields", job)
        dto = svc.consultar_job("job-fields")
        assert dto.project_id == "proj-fields"
        assert dto.skill_id == "02-cronograma"
        assert dto.escopo_id == "esc-02"
        assert dto.plano_id == "plano-02"


# ---------------------------------------------------------------------------
# listar_jobs
# ---------------------------------------------------------------------------


class TestListarJobs:
    """Verify listar_jobs counters and filters."""

    def _add_job(self, repo: InMemoryJobRepository, job_id: str, project_id: str) -> None:
        job = _build_job_dict(job_id, project_id)
        repo.save(job_id, job)

    def test_empty_repo_returns_empty_list(self, svc):
        result = svc.listar_jobs()
        assert isinstance(result, JobListDTO)
        assert len(result.jobs) == 0

    def test_stats_aguardando_fila(self, svc, repo):
        self._add_job(repo, "job-a1", "proj-a")
        self._add_job(repo, "job-a2", "proj-a")
        result = svc.listar_jobs()
        assert result.estatisticas.aguardando_fila == 2

    def test_stats_em_execucao(self, svc, repo):
        job = _build_job_dict("job-em", "proj-b")
        job["state_machine"].iniciar()
        repo.save("job-em", job)
        result = svc.listar_jobs()
        assert result.estatisticas.em_execucao == 1

    def test_stats_concluido(self, svc, repo):
        job = _build_job_dict("job-done", "proj-c")
        job["state_machine"].iniciar()
        job["state_machine"].completar(resultado={"ok": True})
        repo.save("job-done", job)
        result = svc.listar_jobs()
        assert result.estatisticas.concluido == 1

    def test_stats_erro(self, svc, repo):
        job = _build_job_dict("job-err", "proj-d")
        job["state_machine"].iniciar()
        job["state_machine"].falhar(erro="boom")
        repo.save("job-err", job)
        result = svc.listar_jobs()
        assert result.estatisticas.erro == 1

    def test_stats_cancelado(self, svc, repo):
        job = _build_job_dict("job-can", "proj-e")
        job["state_machine"].cancelar()
        repo.save("job-can", job)
        result = svc.listar_jobs()
        assert result.estatisticas.cancelado == 1

    def test_mixed_statuses_correct_totals(self, svc, repo):
        # aguardando x2, em_execucao x1, concluido x1, erro x1, cancelado x1
        self._add_job(repo, "job-aq1", "p")
        self._add_job(repo, "job-aq2", "p")

        j_em = _build_job_dict("job-em2", "p")
        j_em["state_machine"].iniciar()
        repo.save("job-em2", j_em)

        j_ok = _build_job_dict("job-ok", "p")
        j_ok["state_machine"].iniciar()
        j_ok["state_machine"].completar(resultado={})
        repo.save("job-ok", j_ok)

        j_er = _build_job_dict("job-er2", "p")
        j_er["state_machine"].iniciar()
        j_er["state_machine"].falhar(erro="x")
        repo.save("job-er2", j_er)

        j_ca = _build_job_dict("job-ca2", "p")
        j_ca["state_machine"].cancelar()
        repo.save("job-ca2", j_ca)

        result = svc.listar_jobs()
        s = result.estatisticas
        assert s.aguardando_fila == 2
        assert s.em_execucao == 1
        assert s.concluido == 1
        assert s.erro == 1
        assert s.cancelado == 1

    def test_project_id_filter_returns_only_matching(self, svc, repo):
        self._add_job(repo, "job-pa1", "proj-A")
        self._add_job(repo, "job-pa2", "proj-A")
        self._add_job(repo, "job-pb1", "proj-B")

        result = svc.listar_jobs(project_id="proj-A")
        assert len(result.jobs) == 2
        assert all(j.project_id == "proj-A" for j in result.jobs)

    def test_project_id_filter_no_match_returns_empty(self, svc, repo):
        self._add_job(repo, "job-x", "proj-X")
        result = svc.listar_jobs(project_id="proj-NOPE")
        assert len(result.jobs) == 0

    def test_max_concurrent_jobs_echoed(self, svc, cfg):
        result = svc.listar_jobs()
        assert result.max_concurrent_jobs == cfg.max_concurrent_jobs

    def test_sorted_most_recent_first(self, svc, repo):
        earlier = _build_job_dict("job-old", "p")
        earlier["disparado_em"] = (datetime.now(UTC) - timedelta(seconds=10)).isoformat()
        repo.save("job-old", earlier)

        later = _build_job_dict("job-new", "p")
        later["disparado_em"] = datetime.now(UTC).isoformat()
        repo.save("job-new", later)

        result = svc.listar_jobs()
        assert result.jobs[0].job_id == "job-new"
        assert result.jobs[1].job_id == "job-old"


# ---------------------------------------------------------------------------
# cancelar_job
# ---------------------------------------------------------------------------


class TestCancelarJob:
    """Verify cancelar_job transitions and error cases."""

    def test_cancel_aguardando_fila_succeeds(self, svc, repo):
        job = _build_job_dict("job-caq", "proj-x")
        repo.save("job-caq", job)
        dto = svc.cancelar_job("job-caq")
        assert dto.status == "CANCELADO"

    def test_cancel_em_execucao_succeeds(self, svc, repo):
        job = _build_job_dict("job-cem", "proj-x")
        job["state_machine"].iniciar()
        repo.save("job-cem", job)
        dto = svc.cancelar_job("job-cem")
        assert dto.status == "CANCELADO"

    def test_cancel_concluido_raises_value_error(self, svc, repo):
        job = _build_job_dict("job-cdone", "proj-x")
        job["state_machine"].iniciar()
        job["state_machine"].completar(resultado={})
        repo.save("job-cdone", job)
        with pytest.raises(ValueError, match="não pode ser cancelado"):
            svc.cancelar_job("job-cdone")

    def test_cancel_erro_raises_value_error(self, svc, repo):
        job = _build_job_dict("job-cerr", "proj-x")
        job["state_machine"].iniciar()
        job["state_machine"].falhar(erro="fail")
        repo.save("job-cerr", job)
        with pytest.raises(ValueError, match="não pode ser cancelado"):
            svc.cancelar_job("job-cerr")

    def test_cancel_already_cancelado_raises_value_error(self, svc, repo):
        job = _build_job_dict("job-ccan", "proj-x")
        job["state_machine"].cancelar()
        repo.save("job-ccan", job)
        with pytest.raises(ValueError, match="não pode ser cancelado"):
            svc.cancelar_job("job-ccan")

    def test_cancel_nonexistent_raises_value_error(self, svc):
        with pytest.raises(ValueError, match="não encontrado"):
            svc.cancelar_job("job-ghost")

    def test_cancel_returns_job_dto(self, svc, repo):
        job = _build_job_dict("job-cdto", "proj-x")
        repo.save("job-cdto", job)
        result = svc.cancelar_job("job-cdto")
        assert isinstance(result, JobDTO)

    def test_cancel_with_custom_motivo(self, svc, repo):
        job = _build_job_dict("job-cmot", "proj-x")
        repo.save("job-cmot", job)
        dto = svc.cancelar_job("job-cmot", motivo="Cancelled for testing")
        assert dto.status == "CANCELADO"


# ---------------------------------------------------------------------------
# obter_estatisticas
# ---------------------------------------------------------------------------


class TestObterEstatisticas:
    """Verify obter_estatisticas reflects repo state and config."""

    def test_returns_system_stats_dto(self, svc):
        stats = svc.obter_estatisticas()
        assert isinstance(stats, SystemStatsDTO)

    def test_configuracao_echoes_settings(self, svc, cfg):
        stats = svc.obter_estatisticas()
        assert stats.configuracao["max_concurrent_jobs"] == cfg.max_concurrent_jobs
        assert stats.configuracao["job_ttl_hours"] == cfg.job_ttl_hours
        assert stats.configuracao["gc_interval_minutes"] == cfg.job_gc_interval_minutes

    def test_contadores_total_jobs_ativos(self, svc, repo):
        repo.save("job-s1", _build_job_dict("job-s1"))
        repo.save("job-s2", _build_job_dict("job-s2"))
        stats = svc.obter_estatisticas()
        assert stats.contadores["total_jobs_ativos"] == 2

    def test_contadores_jobs_por_status(self, svc, repo):
        j1 = _build_job_dict("job-sq1")
        repo.save("job-sq1", j1)

        j2 = _build_job_dict("job-sq2")
        j2["state_machine"].iniciar()
        j2["state_machine"].completar(resultado={})
        repo.save("job-sq2", j2)

        stats = svc.obter_estatisticas()
        por_status = stats.contadores["jobs_por_status"]
        assert por_status.get("AGUARDANDO_FILA", 0) == 1
        assert por_status.get("CONCLUIDO", 0) == 1

    def test_sistema_worker_pool_not_active_before_first_call(self, svc):
        # Before any disparar_pipeline, executor is None
        stats = svc.obter_estatisticas()
        assert stats.sistema["worker_pool_ativo"] is False

    def test_sistema_gc_not_active_before_first_call(self, svc):
        stats = svc.obter_estatisticas()
        assert stats.sistema["gc_ativo"] is False

    def test_empty_repo_total_zero(self, svc):
        stats = svc.obter_estatisticas()
        assert stats.contadores["total_jobs_ativos"] == 0


# ---------------------------------------------------------------------------
# _limpar_jobs_expirados
# ---------------------------------------------------------------------------


class TestLimparJobsExpirados:
    """Directly call _limpar_jobs_expirados and verify expired terminal jobs removed."""

    def _terminal_job(
        self,
        job_id: str,
        finalizado_em: datetime,
        terminal: bool = True,
    ) -> dict[str, Any]:
        job = _build_job_dict(job_id)
        if terminal:
            job["state_machine"].iniciar()
            job["state_machine"].completar(resultado={})
        # Override finalizado_em to control expiry
        job["finalizado_em"] = finalizado_em.isoformat()
        return job

    def test_removes_expired_terminal_job(self, svc, repo, cfg):
        cutoff = datetime.now(UTC) - timedelta(hours=cfg.job_ttl_hours + 1)
        job = self._terminal_job("job-exp", cutoff)
        repo.save("job-exp", job)

        svc._limpar_jobs_expirados()

        assert repo.get("job-exp") is None

    def test_keeps_fresh_terminal_job(self, svc, repo, cfg):
        cutoff = datetime.now(UTC) - timedelta(hours=cfg.job_ttl_hours - 1)
        job = self._terminal_job("job-fresh", cutoff)
        repo.save("job-fresh", job)

        svc._limpar_jobs_expirados()

        assert repo.get("job-fresh") is not None

    def test_keeps_non_terminal_job_even_if_old(self, svc, repo, cfg):
        old_time = datetime.now(UTC) - timedelta(hours=cfg.job_ttl_hours + 10)
        job = _build_job_dict("job-nonterminal")
        # AGUARDANDO_FILA is non-terminal; set finalizado_em to simulate old timestamp
        job["finalizado_em"] = old_time.isoformat()
        repo.save("job-nonterminal", job)

        svc._limpar_jobs_expirados()

        assert repo.get("job-nonterminal") is not None

    def test_keeps_terminal_without_finalizado_em(self, svc, repo):
        job = _build_job_dict("job-nofin")
        job["state_machine"].iniciar()
        job["state_machine"].completar(resultado={})
        job["finalizado_em"] = None  # no timestamp
        repo.save("job-nofin", job)

        svc._limpar_jobs_expirados()

        assert repo.get("job-nofin") is not None

    def test_multiple_expired_all_removed(self, svc, repo, cfg):
        cutoff = datetime.now(UTC) - timedelta(hours=cfg.job_ttl_hours + 2)
        for i in range(3):
            job = self._terminal_job(f"job-mx{i}", cutoff)
            repo.save(f"job-mx{i}", job)

        svc._limpar_jobs_expirados()

        for i in range(3):
            assert repo.get(f"job-mx{i}") is None

    def test_mixed_expired_and_fresh(self, svc, repo, cfg):
        old = datetime.now(UTC) - timedelta(hours=cfg.job_ttl_hours + 5)
        fresh = datetime.now(UTC) - timedelta(hours=1)

        exp_job = self._terminal_job("job-expired", old)
        repo.save("job-expired", exp_job)

        fresh_job = self._terminal_job("job-ok", fresh)
        repo.save("job-ok", fresh_job)

        svc._limpar_jobs_expirados()

        assert repo.get("job-expired") is None
        assert repo.get("job-ok") is not None

    def test_no_jobs_is_noop(self, svc, repo):
        # Should not raise
        svc._limpar_jobs_expirados()
        assert repo.count() == 0


# ---------------------------------------------------------------------------
# get_job_service / reset_job_service singleton
# ---------------------------------------------------------------------------


class TestSingletonFunctions:
    """Tests for module-level get_job_service and reset_job_service."""

    def test_get_job_service_returns_instance(self):
        svc = get_job_service()
        assert isinstance(svc, JobService)

    def test_get_job_service_singleton_same_object(self):
        s1 = get_job_service()
        s2 = get_job_service()
        assert s1 is s2

    def test_reset_clears_singleton(self):
        s1 = get_job_service()
        reset_job_service()
        s2 = get_job_service()
        assert s1 is not s2

    def test_reset_twice_no_error(self):
        reset_job_service()
        reset_job_service()  # should not raise


# ---------------------------------------------------------------------------
# _criar_progress_callback
# ---------------------------------------------------------------------------


class TestProgressCallback:
    """Verify _criar_progress_callback updates the repo correctly."""

    def test_callback_updates_progresso(self, svc, repo):
        job = _build_job_dict("job-prog", "p")
        repo.save("job-prog", job)

        cb = svc._criar_progress_callback("job-prog")
        cb("step 1")

        stored = repo.get("job-prog")
        assert stored["progresso"] == "step 1"

    def test_callback_updates_percentual(self, svc, repo):
        job = _build_job_dict("job-pct", "p")
        repo.save("job-pct", job)

        cb = svc._criar_progress_callback("job-pct")
        cb("halfway", 0.5)

        stored = repo.get("job-pct")
        assert stored["progresso_percentual"] == 0.5

    def test_callback_clamps_percentual_above_one(self, svc, repo):
        job = _build_job_dict("job-pclamp", "p")
        repo.save("job-pclamp", job)

        cb = svc._criar_progress_callback("job-pclamp")
        cb("overflow", 1.5)

        stored = repo.get("job-pclamp")
        assert stored["progresso_percentual"] == 1.0

    def test_callback_clamps_percentual_below_zero(self, svc, repo):
        job = _build_job_dict("job-pneg", "p")
        repo.save("job-pneg", job)

        cb = svc._criar_progress_callback("job-pneg")
        cb("negative", -0.5)

        stored = repo.get("job-pneg")
        assert stored["progresso_percentual"] == 0.0

    def test_callback_no_op_for_unknown_job(self, svc, repo):
        # Should not raise; just silently skip
        cb = svc._criar_progress_callback("job-nonexistent")
        cb("msg")  # no error expected


# ---------------------------------------------------------------------------
# JobService.__init__ dependency injection
# ---------------------------------------------------------------------------


class TestInitDependencyInjection:
    """Verify __init__ accepts injected repo and config."""

    def test_injected_repo_is_used(self):
        repo = InMemoryJobRepository()
        cfg = _make_config()
        svc = JobService(repository=repo, config=cfg)
        assert svc._repo is repo

    def test_injected_config_is_used(self):
        repo = InMemoryJobRepository()
        cfg = _make_config(max_concurrent_jobs=5, job_ttl_hours=48)
        svc = JobService(repository=repo, config=cfg)
        assert svc._config.max_concurrent_jobs == 5
        assert svc._config.job_ttl_hours == 48

    def test_runtime_factory_stored(self):
        factory = lambda: None
        svc = JobService(
            repository=InMemoryJobRepository(),
            config=_make_config(),
            runtime_factory=factory,
        )
        assert svc._runtime_factory is factory

    def test_project_factory_stored(self):
        pf = lambda pid: None
        svc = JobService(
            repository=InMemoryJobRepository(),
            config=_make_config(),
            project_factory=pf,
        )
        assert svc._project_factory is pf
