"""Modelos de domínio para Benchmarks (NEP-039)."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BenchmarkState(StrEnum):
    """Estados de uma execução de benchmark."""

    PENDENTE = "PENDENTE"
    EM_PROGRESSO = "EM_PROGRESSO"
    SUCESSO = "SUCESSO"
    FALHA = "FALHA"


@dataclass
class BenchmarkMetadata:
    """Metadados de um benchmark — entidade versionada."""

    benchmark_id: str  # "AGIS_2025_Q1"
    nome: str
    origem: str
    tags: list[str]
    criado_em: datetime
    versao: int  # auto-incrementado
    imutavel: bool  # True após primeira execução bem-sucedida

    def mark_immutable(self) -> None:
        """Marca benchmark como imutável."""
        self.imutavel = True


@dataclass
class BenchmarkExecution:
    """Registro de execução de benchmark com rastreabilidade."""

    execution_id: str
    benchmark_id: str
    versao: int
    projeto_id: str  # Link para projeto criado/atualizado
    status: str  # BenchmarkState
    executado_em: datetime
    discrepancia_sumario: dict | None = None  # Diff com referência anterior
