"""Camada 4 — Contabilização canônica de recursos consumíveis (ADR-128 F6).

Espelha, na granularidade que o dado permite (recurso, não instância/contrato — consumíveis
não têm slots numerados), as 3 camadas já existentes para pool de recursos:
``RecursoPool``/``RecursoContrato`` (capacidade/custo) e ``ResumoUtilizacaoContrato``
(resumo de utilização, `_pool_recursos.py`). Aqui: ``RecursoConsumivelCanonical`` (snapshot
do ``ReplenishableResource`` construído por skill-04) e ``ResumoEstoqueConsumivel`` (resumo
de saúde de estoque por recurso, análogo a ``ResumoUtilizacaoContrato``).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DisponibilidadeConsumivelCanonical(BaseModel):
    """Espelho canônico de ``DisponibilidadeConsumivel`` (catalog dataclass) — mesmo
    princípio de ``EstoqueDelayCanonical`` espelhando ``EstoqueDelayCause``."""

    model_config = ConfigDict(extra="ignore")

    capacidade_armazenamento: float | None = None
    estoque_inicial: float = 0.0
    taxa_reabastecimento_max: float | None = None
    lead_time_reabastecimento_dias: float | None = None


class RecursoConsumivelCanonical(BaseModel):
    """Snapshot canônico de um ``ReplenishableResource`` construído por skill-04 (ADR-128 F6).

    Permite ao builder do cubo de estoque (``CuboEstoqueConsumivelBuilder``) recomputar
    projeções semanais a partir só do canônico, sem re-tocar o catálogo — mesmo princípio
    de ``RecursoContrato`` para o cubo de pool.
    """

    model_config = ConfigDict(extra="ignore")

    resource_id: str
    disponibilidade: DisponibilidadeConsumivelCanonical
    # activity_id -> taxa de consumo/produção projetada por semana ativa
    consumo_por_semana: dict[str, float] = Field(default_factory=dict)
    producao_por_semana: dict[str, float] = Field(default_factory=dict)


class ResumoEstoqueConsumivel(BaseModel):
    """Resumo agregado de saúde de estoque por recurso consumível — análogo a
    ``ResumoUtilizacaoContrato`` (pool), na granularidade de recurso.

    Regra de status (existence-based, não banda percentual como pool 65%/35% — não há
    métrica contínua natural aqui, já que a projeção é recomputada contra o cronograma
    FINAL, pós-reparo):

        CRITICO  se estoque_minimo < 0   (irreparável — mesmo caso de VAL-ESTOQUE-DELAY-02)
        AVISO    elif delay_total_semanas > 0 ou overflow_total > 0
        OK       caso contrário
    """

    model_config = ConfigDict(extra="ignore")

    resource_id: str
    estoque_inicial: float
    capacidade_armazenamento: float | None = None
    estoque_medio: float
    estoque_minimo: float
    estoque_final: float
    overflow_total: float = 0.0
    n_semanas_overflow: int = 0
    delay_total_semanas: int = 0
    n_atividades_atrasadas: int = 0
    status_estoque: Literal["OK", "AVISO", "CRITICO"] = "OK"
