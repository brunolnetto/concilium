"""Camada 3 - Perfil de Construtora."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Faixa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float
    max: float


class CategoriaIndireto(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    descricao: str


class TransicaoAprovacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    de: str
    para: str
    papel_requerido: str


class PoliticaAprovacao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo: Literal["rigida", "condicional_por_valor", "configuravel_por_obra"]
    transicoes: list[TransicaoAprovacao]


class PerfilConstrutora(BaseModel):
    """Camada 3 - perfil especifico de uma construtora."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    nome: str
    jurisdicao_id: str
    faixa_margem_alvo: Faixa
    faixa_margem_aceitavel: Faixa
    categorias_indireto: list[CategoriaIndireto] = Field(min_length=1)
    razao_indireto_direto_alvo: Faixa | None = None
