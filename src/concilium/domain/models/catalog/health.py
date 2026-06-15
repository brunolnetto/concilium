"""ADR-012 — Catalog Completeness: Authoritative Sources and Health Metrics.

Models for tracking catalog coverage per domain/jurisdiction and resolving gaps
from authoritative sources (SICRO, SINAPI, TCPO, AGIS real data).
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FonteAutoritativa(BaseModel):
    """Fonte autoritativa de dados de catálogo por jurisdição (ADR-012 §D1)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    nome: str
    entidade: str
    url: str = ""
    jurisdicao: str
    dominio: list[str] = Field(default_factory=list)
    granularidade: Literal["cpu_completa", "insumo_unitario", "produtividade"]
    cobertura: str = ""
    ciclo_atualizacao: Literal["mensal", "trimestral", "semestral", "anual", "por_obra"]
    ultima_consulta: date | None = None
    prioridade: int = Field(ge=1, le=5)
    notas: str = ""


class GrupoCoberturaServico(BaseModel):
    """Grupo de serviços esperados para um domínio (ADR-012 §D2)."""

    model_config = ConfigDict(extra="ignore")

    nome: str
    servicos_esperados: list[str] = Field(default_factory=list)
    status_catalogo: Literal["COMPLETO", "PARCIAL", "AUSENTE"] = "PARCIAL"
    lacunas: list[str] = Field(default_factory=list)
    fonte_preenchimento: str = ""


class CoberturaConfig(BaseModel):
    """Configuração de cobertura esperada para um domínio/jurisdição (ADR-012 §D2)."""

    model_config = ConfigDict(extra="ignore")

    dominio: str
    jurisdicao: str
    fonte_referencia: str
    grupos_servico: dict[str, GrupoCoberturaServico] = Field(default_factory=dict)


class CatalogGap(BaseModel):
    """Gap detectado entre cobertura esperada e catálogo atual (ADR-012 §D3)."""

    model_config = ConfigDict(extra="ignore")

    grupo: str
    servico_esperado: str
    status: Literal["AUSENTE", "SEM_PRODUTIVIDADE", "BAIXA_CONFIANCA"]
    cpu_existente: str | None = None
    confianca_atual: float | None = Field(default=None, ge=0, le=100)
    fonte_sugerida: str = ""
    prioridade: Literal["ALTA", "MEDIA", "BAIXA"] = "MEDIA"


class ResolutionProposal(BaseModel):
    """Proposta de resolução de gap gerada a partir de fonte autoritativa (ADR-012 §D3)."""

    model_config = ConfigDict(extra="ignore")

    gap: CatalogGap
    status: Literal["PROPOSTO", "NAO_ENCONTRADO", "APROVADO", "REJEITADO"]
    cpu_codigo_proposto: str | None = None
    producao_horaria_proposta: float | None = None
    custo_unitario_proposto: float | None = None
    unidade: str | None = None
    fonte_id: str = ""
    requer_aprovacao: bool = True
    aprovado_por: str | None = None
    data_aprovacao: date | None = None
    nota_aprovacao: str = ""


class CatalogHealthReport(BaseModel):
    """Relatório de saúde do catálogo para um domínio/jurisdição (ADR-012 §D5, ADR-017 §D6)."""

    model_config = ConfigDict(extra="ignore")

    dominio: str
    jurisdicao: str
    data_avaliacao: date

    total_servicos_esperados: int = Field(ge=0)
    total_cpus_presentes: int = Field(ge=0)
    total_gaps: int = Field(ge=0)
    cobertura_pct: float = Field(ge=0, le=100)

    producoes_com_dados_reais: int = Field(ge=0)
    producoes_apenas_tabulares: int = Field(ge=0)
    producoes_confianca_baixa: int = Field(ge=0)
    confianca_media: float = Field(ge=0, le=100)

    gaps_ausente: int = Field(ge=0)
    gaps_sem_produtividade: int = Field(ge=0)
    gaps_baixa_confianca: int = Field(ge=0)

    status: Literal["COMPLETO", "ADEQUADO", "PARCIAL", "INSUFICIENTE"]
    gaps: list[CatalogGap] = Field(default_factory=list)

    # ── ADR-017 §D6: métricas de staleness e fila de revisão ─────────────────
    producoes_desatualizadas: int = Field(default=0, ge=0)  # calibradas há > 12 meses
    insumos_preco_desatualizado: int = Field(default=0, ge=0)  # preço sem atualização > 6 meses
    observacoes_pendentes: int = Field(default=0, ge=0)  # na fila, não processadas
    propostas_pendentes: int = Field(default=0, ge=0)  # propostas aguardando aprovação

    # Qualidade de dados
    producoes_sem_obra_real: int = Field(default=0, ge=0)  # origen = "tabela_referencia"
    insumos_sem_classe: int = Field(default=0, ge=0)  # sem classe_compartilhamento (ADR-016)
    cpus_sem_producao: int = Field(default=0, ge=0)  # CPU sem producao_id

    # Atividade do catálogo
    ultima_calibracao: date | None = None
    obras_contribuindo: int = Field(default=0, ge=0)

    # Status de dados (complementa status de cobertura)
    status_dados: Literal["ATUALIZADO", "DEFASADO", "CRITICO"] = "ATUALIZADO"

    @classmethod
    def compute_status(cls, cobertura_pct: float, confianca_media: float) -> str:
        if cobertura_pct >= 95 and confianca_media >= 80:
            return "COMPLETO"
        if cobertura_pct >= 80 and confianca_media >= 70:
            return "ADEQUADO"
        if cobertura_pct >= 60:
            return "PARCIAL"
        return "INSUFICIENTE"

    @classmethod
    def compute_status_dados(cls, producoes_desatualizadas: int, observacoes_pendentes: int) -> str:
        if producoes_desatualizadas == 0 and observacoes_pendentes < 5:
            return "ATUALIZADO"
        if observacoes_pendentes > 20:
            return "CRITICO"
        return "DEFASADO"
