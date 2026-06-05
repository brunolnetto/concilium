"""DTOs e modelos de dados para o sistema de jobs.

ADR-103: Jobs na Camada de Aplicação
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobDTO(BaseModel):
    """DTO representando um job de pipeline."""

    job_id: str = Field(..., description="ID único do job")
    status: str = Field(..., description="Status atual: AGUARDANDO_FILA | EM_EXECUCAO | CONCLUIDO | ERRO | CANCELADO")
    project_id: str = Field(..., description="ID do projeto")
    skill_id: str | None = Field(None, description="ID da skill (None = próxima pendente)")
    escopo_id: str | None = Field(None, description="ID do escopo")
    plano_id: str | None = Field(None, description="ID do plano")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Inputs da skill")
    
    disparado_em: str = Field(..., description="Timestamp ISO 8601 de disparo")
    iniciado_em: str | None = Field(None, description="Timestamp ISO 8601 de início")
    finalizado_em: str | None = Field(None, description="Timestamp ISO 8601 de finalização")
    
    resultado: dict[str, Any] | None = Field(None, description="Resultado da skill quando CONCLUIDO")
    erro: str | None = Field(None, description="Mensagem de erro quando ERRO")
    progresso: str | None = Field(None, description="Mensagem textual de progresso")
    progresso_percentual: float | None = Field(None, ge=0.0, le=1.0, description="Progresso de 0.0 a 1.0")

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "job-abc123def456",
                "status": "EM_EXECUCAO",
                "project_id": "rodovia-ce040-lote09",
                "skill_id": "04-cronograma",
                "escopo_id": "esc-01",
                "plano_id": "plano-baseline",
                "inputs": {"num_equipes_por_item": {"eap-1_1": 2}},
                "disparado_em": "2026-06-03T19:45:00Z",
                "iniciado_em": "2026-06-03T19:45:01Z",
                "finalizado_em": None,
                "resultado": None,
                "erro": None,
                "progresso": "Resolvendo RCPSP... 45%",
                "progresso_percentual": 0.45,
            }
        }


class JobStatsDTO(BaseModel):
    """DTO com estatísticas agregadas de jobs."""

    aguardando_fila: int = Field(0, description="Jobs aguardando execução")
    em_execucao: int = Field(0, description="Jobs em execução")
    concluido: int = Field(0, description="Jobs concluídos com sucesso")
    erro: int = Field(0, description="Jobs com erro")
    cancelado: int = Field(0, description="Jobs cancelados")


class JobListDTO(BaseModel):
    """DTO para listagem de jobs com estatísticas."""

    jobs: list[JobDTO] = Field(default_factory=list, description="Lista de jobs")
    estatisticas: JobStatsDTO = Field(default_factory=JobStatsDTO, description="Estatísticas agregadas")
    max_concurrent_jobs: int = Field(..., description="Máximo de jobs simultâneos configurado")


class SystemStatsDTO(BaseModel):
    """DTO com estatísticas do sistema de jobs."""

    configuracao: dict[str, Any] = Field(..., description="Configuração atual do sistema")
    contadores: dict[str, Any] = Field(..., description="Contadores em tempo real")
    sistema: dict[str, bool] = Field(..., description="Status de componentes do sistema")

    class Config:
        json_schema_extra = {
            "example": {
                "configuracao": {
                    "max_concurrent_jobs": 3,
                    "job_ttl_hours": 24,
                    "gc_interval_minutes": 60,
                },
                "contadores": {
                    "total_jobs_ativos": 5,
                    "jobs_por_status": {
                        "AGUARDANDO_FILA": 1,
                        "EM_EXECUCAO": 2,
                        "CONCLUIDO": 2,
                    },
                },
                "sistema": {
                    "worker_pool_ativo": True,
                    "gc_ativo": True,
                },
            }
        }
