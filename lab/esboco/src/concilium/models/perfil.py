"""Camada 3 — Perfil de Construtora."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Faixa(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: float
    max: float


class FaixasBdiPorCategoria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material: Faixa
    diesel: Faixa
    mao_obra: Faixa
    equipamentos: Faixa


class FormulaBDI(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referencia: str
    faixas_por_categoria: FaixasBdiPorCategoria


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


class AdapterSaida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    formato: Literal["XLSM", "XLSX", "PDF", "JSON", "CUSTOM"]
    template_path: str | None = None
    implementacao: str | None = None


class PesosCriticality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alpha_duration: float = Field(default=0.5, ge=0, le=1)
    beta_bottleneck: float = Field(default=0.3, ge=0, le=1)
    gamma_downstream: float = Field(default=0.2, ge=0, le=1)


class PesosCostCriticality(BaseModel):
    model_config = ConfigDict(extra="forbid")

    w_cost: float = Field(default=0.4, ge=0, le=1)
    w_duration: float = Field(default=0.3, ge=0, le=1)
    w_sensitivity: float = Field(default=0.3, ge=0, le=1)


class PesosAnaliticos(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criticality: PesosCriticality = Field(default_factory=PesosCriticality)
    cost_criticality: PesosCostCriticality = Field(default_factory=PesosCostCriticality)


class CriteriosModoExploracao(BaseModel):
    model_config = ConfigDict(extra="forbid")

    margem_min: float | None = None
    margem_max: float | None = None
    delta_pe_max_pct: float | None = None
    prazo_max_dias: int | None = None


class PerfilConstrutora(BaseModel):
    """Camada 3 — perfil específico de uma construtora."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    nome: str
    jurisdicao_id: str
    faixa_margem_alvo: Faixa
    faixa_margem_aceitavel: Faixa
    limiar_ponto_equilibrio: float = Field(ge=0, le=1)
    formula_bdi: FormulaBDI
    categorias_indireto: list[CategoriaIndireto] = Field(min_length=1)
    razao_indireto_direto_alvo: Faixa | None = None
    politica_aprovacao: PoliticaAprovacao
    adapter_saida: AdapterSaida
    pesos_analiticos: PesosAnaliticos = Field(default_factory=PesosAnaliticos)
    criterios_modo_exploracao_default: CriteriosModoExploracao | None = None
