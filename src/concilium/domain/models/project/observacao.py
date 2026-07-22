"""ADR-017 — Modelos de observação e proposta de atualização do catálogo.

Cada projeto em execução é uma oportunidade de validar, desafiar ou enriquecer
os valores do catálogo. Estes modelos formalizam o canal de feedback.

Fluxo:
  Observacao (gerada por Skill 12 ou campo)
    -> fila de revisão (PENDENTE | ANOMALIA)
    -> CONFIRMADA pelo engenheiro sênior
    -> PropostaAtualizacao gerada se thresholds atingidos
    -> APROVADA -> aplicada via o caminho unificado de escrita do catálogo
       mestre (ADR-145): rascunho -> aprovar_merge_catalogo
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── Tipos de observação ───────────────────────────────────────────────────────

TipoObservacao = Literal[
    "produtividade",  # produção realizada vs. catálogo
    "custo_insumo",  # custo real vs. catálogo
    "classe_recurso",  # comportamento de compartilhamento difere da anotação ADR-016
    "cpu_ausente",  # atividade precisou de CPU não catalogada
]

StatusObservacao = Literal["PENDENTE", "ANOMALIA", "CONFIRMADA", "REJEITADA", "INVESTIGANDO"]


class ObservacaoProdutividade(BaseModel):
    """Produção realizada vs. planejada — gerada por Skill 12 ou entrada manual."""

    model_config = ConfigDict(extra="ignore")

    observacao_id: str
    tipo: Literal["produtividade"] = "produtividade"
    obra_id: str
    cpu_id: str
    producao_id: str

    producao_realizada: float = Field(gt=0)
    unidade: str
    horas_trabalhadas: float = Field(gt=0)
    semanas_observadas: int = Field(ge=1)

    # Contexto para calibração condicional (ADR-007)
    tipo_solo: str | None = None
    dmt_medio: float | None = None
    season: str
    condicoes_site: Literal["normal", "chuvoso", "acesso_ruim", "ideal"]

    confiabilidade: float = Field(ge=0, le=1)
    notas: str = ""

    # Derivados
    delta_pct: float  # (realizada / catalogo - 1) × 100
    is_anomalia: bool  # |delta_pct| > 30%

    status: StatusObservacao = "PENDENTE"
    registrado_por: str
    timestamp: datetime

    nota_revisao: str = ""
    revisado_por: str | None = None
    data_revisao: date | None = None


class ObservacaoCustoInsumo(BaseModel):
    """Custo real vs. catálogo — gerada pela reconciliação financeira."""

    model_config = ConfigDict(extra="ignore")

    observacao_id: str
    tipo: Literal["custo_insumo"] = "custo_insumo"
    obra_id: str
    insumo_id: str

    custo_catalogo: float = Field(ge=0)
    custo_realizado: float = Field(ge=0)
    unidade: str
    data_referencia: date

    delta_pct: float
    is_anomalia: bool
    motivo_delta: str | None = None  # "reajuste_salarial" | "cambio" | "escassez" | "negociacao"

    status: StatusObservacao = "PENDENTE"
    registrado_por: str
    timestamp: datetime

    nota_revisao: str = ""
    revisado_por: str | None = None
    data_revisao: date | None = None


class ObservacaoClasseRecurso(BaseModel):
    """Comportamento de compartilhamento observado difere da anotação ADR-016."""

    model_config = ConfigDict(extra="ignore")

    observacao_id: str
    tipo: Literal["classe_recurso"] = "classe_recurso"
    obra_id: str
    insumo_id: str

    classe_atual: str
    classe_observada: str

    capacidade_cobertura_atual: int | None = None
    capacidade_cobertura_observada: int | None = None

    descricao: str
    semanas_observadas: int = Field(ge=1)
    confiabilidade: float = Field(ge=0, le=1)

    status: StatusObservacao = "PENDENTE"
    registrado_por: str
    timestamp: datetime

    nota_revisao: str = ""
    revisado_por: str | None = None
    data_revisao: date | None = None


class ObservacaoCPUAusente(BaseModel):
    """CPU necessária para um serviço não existe no catálogo."""

    model_config = ConfigDict(extra="ignore")

    observacao_id: str
    tipo: Literal["cpu_ausente"] = "cpu_ausente"
    obra_id: str

    descricao_servico: str
    unidade: str
    quantidade_estimada: float = Field(gt=0)

    cpu_aproximada_id: str | None = None
    motivo_ausencia: Literal["dominio_novo", "variante_nao_catalogada", "jurisdicao"]
    fonte_sugerida: str | None = None  # "SICRO_2024_CE" | "SINAPI" | "calibrar_obra"

    status: StatusObservacao = "PENDENTE"
    registrado_por: str
    timestamp: datetime

    nota_revisao: str = ""
    revisado_por: str | None = None
    data_revisao: date | None = None


# ── Proposta de atualização ───────────────────────────────────────────────────


class PropostaAtualizacao(BaseModel):
    """Mudança proposta a um artefato do catálogo — nunca modifica diretamente.

    Gerada quando observações confirmadas atingem os thresholds mínimos.
    Requer aprovação explícita antes da aplicação (D5 do ADR-017).
    """

    model_config = ConfigDict(extra="ignore")

    proposta_id: str
    tipo_artefato: Literal["producao", "insumo", "cpu", "cobertura"]
    artefato_id: str

    # Evidências
    observacoes: list[str] = Field(default_factory=list)  # IDs das observações de suporte
    n_obras_suporte: int = Field(ge=1)
    delta_medio_pct: float
    confianca_estimada: float = Field(ge=0, le=1)

    # Mudança proposta
    campo: str  # "valor_horario" | "preco_unitario" | "capacidade_cobertura"
    valor_atual: Any
    valor_proposto: Any

    justificativa: str
    fonte: Literal["observacao_obra", "reajuste_mercado", "sicro_atualizado", "sinapi_atualizado"]

    # Governança
    status: Literal["PENDENTE", "APROVADA", "REJEITADA"] = "PENDENTE"
    aprovador: str | None = None
    data_aprovacao: date | None = None
    nota_aprovacao: str = ""

    criado_em: datetime
    criado_por: str
