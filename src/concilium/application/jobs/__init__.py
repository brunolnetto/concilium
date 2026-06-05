"""Camada de aplicação - Jobs de pipeline.

ADR-103: Jobs na Camada de Aplicação

Este pacote contém a lógica de negócio para gerenciamento de jobs assíncronos,
desacoplada das camadas de apresentação (MCP/API REST).

Public API:
    - get_job_service(): Acesso ao serviço singleton
    - JobService: Serviço de casos de uso
    - JobDTO, JobListDTO, JobStatsDTO, SystemStatsDTO: DTOs
    - PipelineJobStateMachine: State machine
    - JobRepository: Interface de persistência
"""

from concilium.application.jobs.models import JobDTO, JobListDTO, JobStatsDTO, SystemStatsDTO
from concilium.application.jobs.repository import JobRepository, get_job_repository
from concilium.application.jobs.service import JobService, get_job_service
from concilium.application.jobs.state import PipelineJobStateMachine, criar_state_machine

__all__ = [
    # Service
    "JobService",
    "get_job_service",
    # DTOs
    "JobDTO",
    "JobListDTO",
    "JobStatsDTO",
    "SystemStatsDTO",
    # State machine
    "PipelineJobStateMachine",
    "criar_state_machine",
    # Repository
    "JobRepository",
    "get_job_repository",
]
