"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class AtivoEquipamentoReal(BaseModel):
    """Ativo real de equipamento (roster) — ADR-155.

    Individualiza custo de equipamento a partir de um ativo real (contrato de
    locação real, com valores e datas reais), em vez do custo calibrado agregado
    por tipo (custo_unit_semanal_eq). Sem nenhuma ligação com InstanciaRecurso/
    segmentos_atividade/identidade_fisica_id (ADR-153) — o pool RCPSP permanece
    fungível; isto é puramente um input de custo bottom-up.
    """

    model_config = ConfigDict(extra="ignore")

    ativo_id: str
    tipo_id: str
    custo_locacao_mensal_real: float = Field(ge=0)
    custo_manutencao_mensal_real: float = 0.0
    data_contrato_inicio: date
    data_contrato_fim: date | None = None  # None = contrato ainda ativo/aberto
