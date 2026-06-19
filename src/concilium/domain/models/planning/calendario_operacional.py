"""Modelos de calendario operacional semanal (ADR-068)."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class EventoCalendario(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    nome: str
    tipo: Literal["feriado", "ponto_facultativo", "recesso"]
    escopo: Literal["global", "jurisdicao", "projeto"]
    jurisdicao_id: str | None = None
    inicio: date
    fim: date
    recorrencia: Literal["anual", "unica"] = "anual"
    fator_operacao: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class CalendarioOperacionalSemanal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    semana_iso: str = Field(pattern=r"^\d{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$")
    dias_uteis_base: float = Field(ge=0.0)
    dias_uteis_efetivos: float = Field(ge=0.0)
    fator_calendario: float = Field(ge=0.0, le=1.0)
    eventos_aplicados: tuple[str, ...] = ()


class CalendarioOperacional(BaseModel):
    model_config = ConfigDict(extra="ignore")

    versao: str = "1"
    eventos: list[EventoCalendario] = Field(default_factory=list)
