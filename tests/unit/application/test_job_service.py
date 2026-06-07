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
        job1 = job_service.disparar_pipeline(project_id="proj-A")
        job2 = job_service.disparar_pipeline(project_id="proj-B")
        job3 = job_service.disparar_pipeline(project_id="proj-A")

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
