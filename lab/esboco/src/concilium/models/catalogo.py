"""Camada 2 — Catálogo: Insumo, CPU, TemplateObra."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TipoInsumo = Literal["MATERIAL", "MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO"]
CategoriaCusto = Literal["MATERIAL", "DIESEL", "MAO_OBRA", "EQUIPAMENTO"]
CategoriaCPU = Literal[
    "TERRAPLENAGEM", "PAVIMENTACAO", "DRENAGEM", "SANEAMENTO", "OBRAS_ARTE", "DIVERSOS"
]


class HistoricoPreco(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preco_unitario: float = Field(ge=0)
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None
    fonte: str | None = None


class AtributosInsumo(BaseModel):
    """Atributos específicos por tipo de insumo. Schema flexível."""

    model_config = ConfigDict(extra="ignore")

    consumo_litros_hora: float | None = Field(default=None, ge=0)
    potencia_cv: float | None = None
    categoria_sindical: str | None = None
    horas_extras_pct_padrao: float | None = Field(default=None, ge=0, le=1)


class Insumo(BaseModel):
    """Item elementar do catálogo: material, mão de obra, equipamento ou terceirizado."""

    model_config = ConfigDict(extra="ignore")

    codigo: str = Field(pattern=r"^[A-Z0-9-]{3,40}$")
    tipo: TipoInsumo
    descricao: str
    unidade: str
    preco_unitario: float = Field(ge=0)
    fonte_preco: Literal["catalogo_proprio", "tabela_referencia", "cotacao_mercado", "negociado"]
    tabela_referencia_id: str | None = None
    codigo_referencia_externa: str | None = None
    historico_precos: list[HistoricoPreco] = Field(default_factory=list)
    atributos_especificos: AtributosInsumo = Field(default_factory=AtributosInsumo)


class ComposicaoItem(BaseModel):
    """Linha da composição de uma CPU: insumo × coeficiente × categoria de custo."""

    model_config = ConfigDict(extra="forbid")

    insumo_id: str
    coeficiente: float = Field(gt=0)
    categoria_custo: CategoriaCusto


class FuncaoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funcao_id: str
    num_pessoas: int = Field(ge=1)
    horas_extras_pct: float | None = Field(default=None, ge=0, le=1)


class EquipamentoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equip_id: str
    num_unidades: int = Field(ge=1)


class ComposicaoPadraoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funcoes: list[FuncaoEquipe]
    equipamentos: list[EquipamentoEquipe]


class AtributosCategoriaCPU(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dmt_min_metros: float | None = Field(default=None, ge=0)
    dmt_max_metros: float | None = None


class CPU(BaseModel):
    """Composição de Preço Unitário."""

    model_config = ConfigDict(extra="ignore")

    codigo: str = Field(pattern=r"^[A-Z0-9-]{4,40}$")
    descricao: str
    unidade: str
    origem: Literal["REFERENCIA", "PROPRIA"]
    cpu_referencia_id: str | None = None
    producao_horaria: float = Field(gt=0)
    categoria: CategoriaCPU
    composicao_itens: list[ComposicaoItem] = Field(min_length=1)
    composicao_padrao_equipe: ComposicaoPadraoEquipe
    atributos_categoria: AtributosCategoriaCPU = Field(default_factory=AtributosCategoriaCPU)


class ServicoSugerido(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_id: str
    ordem: int = Field(ge=1)
    obrigatoriedade: Literal["essencial", "tipico", "opcional"]
    nota: str | None = None


class AtividadeSugerida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atividade_id: str
    cpu_id_pai: str
    fracao_quantitativo: float = Field(gt=0, le=1)
    descricao: str | None = None


class PrecedenciaSugerida(BaseModel):
    model_config = ConfigDict(extra="forbid")

    predecessora: str
    sucessora: str


class TemplateObra(BaseModel):
    """EAP-base sugerida por tipo de obra (DEC-03)."""

    model_config = ConfigDict(extra="ignore")

    codigo: str = Field(pattern=r"^TPL-[A-Z0-9-]+$")
    tipo_obra: Literal["TERRAPLENAGEM", "PAVIMENTACAO", "SANEAMENTO"]
    descricao: str
    criterios_aplicacao: str | None = None
    servicos_sugeridos: list[ServicoSugerido] = Field(min_length=1)
    atividades_sugeridas: list[AtividadeSugerida] = Field(default_factory=list)
    precedencias_sugeridas: list[PrecedenciaSugerida] = Field(default_factory=list)
