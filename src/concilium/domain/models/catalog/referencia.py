"""Camada 1 — Tabela de Referência (snapshot imutável de fonte externa)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ComposicaoReferencia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    codigo_referencia: str
    descricao: str
    unidade: str
    preco_unitario_publicado: float | None = Field(default=None, ge=0)
    data_referencia_preco: date | None = None


class InsumoReferencia(BaseModel):
    model_config = ConfigDict(extra="ignore")

    codigo_referencia: str
    descricao: str
    tipo: Literal["MATERIAL", "MAO_OBRA", "EQUIPAMENTO"]
    unidade: str
    preco_publicado: float = Field(ge=0)


class TabelaReferencia(BaseModel):
    """Camada 1 — versão específica de tabela externa publicada."""

    model_config = ConfigDict(extra="ignore")

    codigo: str
    provedor: str
    versao: str
    regiao: str = Field(pattern=r"^[A-Z]{2}$")
    data_vigencia: date
    url_fonte: str | None = None
    imutavel: bool = True
    composicoes_referencia: list[ComposicaoReferencia] = Field(default_factory=list)
    insumos_referencia: list[InsumoReferencia] = Field(default_factory=list)
