"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class MembroEquipeReal(BaseModel):
    """Membro real de equipe (roster) — ADR-154.

    Individualiza custo de mão-de-obra a partir de uma pessoa real (salário,
    encargos, data de admissão/desligamento), em vez do custo calibrado agregado
    por função (custo_hora_total_referencia). Sem nenhuma ligação com
    InstanciaRecurso/segmentos_atividade/identidade_fisica_id (ADR-153) — o pool
    RCPSP permanece fungível; isto é puramente um input de custo bottom-up.
    """

    model_config = ConfigDict(extra="ignore")

    individuo_id: str
    funcao_id: str
    salario_base_mensal: float = Field(ge=0)
    categoria_sindical: str | None = None  # resolvido via resolver_encargo, precedência ADR-097
    percentual_encargos_local: float | None = None  # override explícito, mesma precedência
    data_admissao: date
    data_desligamento: date | None = None  # None = ainda ativo
