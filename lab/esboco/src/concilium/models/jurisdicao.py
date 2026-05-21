"""Camada 0 — Jurisdição."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProvedorReferencia(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    nome: str
    mantenedor: str
    cadencia_atualizacao: Literal["mensal", "trimestral", "anual", "irregular"]
    uso_tipico: str


class FonteClimatica(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provedor: str
    url_base: str | None = None
    metodo_consulta: str
    granularidade: Literal["diaria", "mensal", "horaria"] = "mensal"


class ComponenteEncargo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str
    percentual: float = Field(ge=0, le=2)


class MotorEncargosSociais(BaseModel):
    model_config = ConfigDict(extra="forbid")

    versao: str
    percentual_total: float = Field(ge=0, le=2)
    componentes: list[ComponenteEncargo] = Field(default_factory=list)


class Jurisdicao(BaseModel):
    """Camada 0 — contexto regulatório e geográfico."""

    model_config = ConfigDict(extra="ignore")  # ignora $comment, $schema

    codigo: str = Field(pattern=r"^[A-Z]{2,5}$")
    nome: str
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    regime_trabalhista: Literal["CLT", "OUTRO"]
    provedores_referencia: list[ProvedorReferencia] = Field(min_length=1)
    fonte_climatica: FonteClimatica
    motor_encargos_sociais: MotorEncargosSociais
