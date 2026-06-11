"""Camada 2 — Catálogo: Insumo, CPU, TemplateObra."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from concilium.domain.models.bdi import DecomposicaoEquipamento
from concilium.domain.units import normalize_unidade

TipoInsumo = Literal["MATERIAL", "MAO_OBRA", "EQUIPAMENTO", "TERCEIRIZADO"]

# ADR-107 D1: "DIESEL" mantido como alias legado; "COMBUSTIVEL" é o termo canônico.
# Novos dados devem usar "COMBUSTIVEL"; leitura de dados legados aceita "DIESEL".
CategoriaCusto = Literal["MATERIAL", "COMBUSTIVEL", "DIESEL", "MAO_OBRA", "EQUIPAMENTO"]


class TipoCombustivel(StrEnum):
    """ADR-107 D3 — Tipos de combustível suportados."""

    DIESEL_S10 = "diesel_s10"
    DIESEL_S500 = "diesel_s500"
    CNG = "cng"  # Gás Natural Comprimido (GNV)
    BIODIESEL = "biodiesel"
    ELETRICO = "eletrico"
    OUTRO = "outro"


def _infer_tipo_combustivel(insumo_id: str) -> TipoCombustivel:
    """ADR-107 D6 — Infere TipoCombustivel a partir do código do insumo (fallback para DIESEL_S10)."""
    upper = insumo_id.upper()
    if "GNV" in upper or "CNG" in upper or "GAS-NATURAL" in upper:
        return TipoCombustivel.CNG
    if "BIODIESEL" in upper or "B100" in upper:
        return TipoCombustivel.BIODIESEL
    if "ELETRIC" in upper or "ELÉTR" in upper:
        return TipoCombustivel.ELETRICO
    if "S500" in upper:
        return TipoCombustivel.DIESEL_S500
    return TipoCombustivel.DIESEL_S10  # fallback seguro para todo diesel legacy


CategoriaCPU = Literal["TERRAPLENAGEM", "PAVIMENTACAO", "DRENAGEM", "SANEAMENTO", "OBRAS_ARTE", "DIVERSOS"]

ClasseInsumo = Literal[
    "exclusivo_dedicado",  # Classe A: uma instância -> uma atividade
    "exclusivo_compartilhavel",  # Classe B: alterna entre atividades no mesmo período
    "concorrente_compartilhavel",  # Classe C: cobre N atividades simultâneas
]

PapelFuncao = Literal[
    "direto",  # Produção direta — custo contabilizado em equipes diretas
    "indireto",  # Suporte de campo — custo contabilizado em indiretos (skill 05)
    "gestao",  # Gestão de obra — atribuído separadamente, fora da CPU padrão
]


class ClasseCompartilhamento(BaseModel):
    """Taxonomia de compartilhamento de insumo (ADR-016).

    Classe A — exclusivo_dedicado: custo integral por atividade.
    Classe B — exclusivo_compartilhavel: custo pro-rated por fracao_uso.
    Classe C — concorrente_compartilhavel: custo dividido por n_atividades_simultaneas,
               limitado a capacidade_cobertura instâncias.
    """

    model_config = ConfigDict(extra="forbid")

    classe: ClasseInsumo
    fracao_uso: float | None = Field(default=None, gt=0, le=1)
    capacidade_cobertura: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def _validate_fields_per_class(self) -> ClasseCompartilhamento:
        if self.classe == "exclusivo_compartilhavel" and self.fracao_uso is None:
            raise ValueError("exclusivo_compartilhavel requer fracao_uso definida")
        if self.classe == "concorrente_compartilhavel" and self.fracao_uso is not None:
            raise ValueError("concorrente_compartilhavel não usa fracao_uso")
        return self


class HistoricoPreco(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preco_unitario: float = Field(ge=0)
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None
    fonte: str | None = None


class AtributosInsumo(BaseModel):
    """Atributos específicos por tipo de insumo.

    Campos cobrem os três tipos elementares (MAO_OBRA, EQUIPAMENTO, MATERIAL).
    Todos são opcionais; campos irrelevantes para um dado tipo ficam como None.

    MAO_OBRA
    --------
    categoria_sindical      : categoria sindical / faixa salarial (ex: "horista_CE")
    horas_extras_pct_padrao : percentual padrão de horas extras (ex: 0.25 = 25 %)
    custo_com_encargos      : custo mensal total incluindo encargos sociais (R$/mês)
    tipo_contrato           : regime de contratação ("CLT" ou "PJ")
    salario_mensal          : salário mensal base sem encargos (R$/mês)
    horas_mes               : horas trabalhadas por mês (h/mês) — também usado em EQ

    EQUIPAMENTO
    -----------
    consumo_litros_hora     : consumo de combustível (L/h)
    potencia_cv             : potência nominal (cv)
    codigo_planilha         : código na planilha de origem (ex: "E0001")
    valor_locacao_mensal    : custo mensal de locação (R$/mês)
    horas_mes               : horas produtivas por mês (h/mês)
    tipo_propriedade        : forma de aquisição ("proprio" ou "locacao")
    custo_produtivo_hora    : parcela produtiva do custo horário (R$/h)
    pct_manutencao          : percentual de manutenção aplicado sobre custo produtivo
    custo_manutencao_hora   : custo de manutenção por hora (R$/h)
    decomposicao_equip      : decomposição BDI por sub-categoria (ADR-023 §D3)

    MATERIAL
    --------
    fornecedor_referencia   : fornecedor de referência para cotação
    prazo_entrega           : prazo de entrega típico (texto livre, ex: "Imediato")
    """

    model_config = ConfigDict(extra="ignore")

    # ── MAO_OBRA ──────────────────────────────────────────────────────
    categoria_sindical: str | None = None
    horas_extras_pct_padrao: float | None = Field(default=None, ge=0, le=1)
    custo_com_encargos: float | None = Field(default=None, ge=0)
    tipo_contrato: Literal["CLT", "PJ"] | None = None
    salario_mensal: float | None = Field(default=None, ge=0)
    horas_mes: float | None = Field(default=None, gt=0)

    # ── EQUIPAMENTO ───────────────────────────────────────────────────
    consumo_litros_hora: float | None = Field(default=None, ge=0)
    potencia_cv: float | None = None
    codigo_planilha: str | None = None
    valor_locacao_mensal: float | None = Field(default=None, ge=0)
    tipo_propriedade: Literal["proprio", "locacao"] | None = None
    custo_produtivo_hora: float | None = Field(default=None, ge=0)
    pct_manutencao: float | None = Field(default=None, ge=0, le=1)
    custo_manutencao_hora: float | None = Field(default=None, ge=0)
    # ADR-023 §D3: decomposição de custo por sub-categoria para BDI correto (Phase 5)
    decomposicao_equip: DecomposicaoEquipamento | None = None

    # ── MATERIAL ──────────────────────────────────────────────────────
    fornecedor_referencia: str | None = None
    prazo_entrega: str | None = None


class Insumo(BaseModel):
    """Item elementar do catálogo: material, mão de obra, equipamento ou terceirizado."""

    model_config = ConfigDict(extra="ignore")

    codigo: str = Field(pattern=r"^[A-Z0-9-]{3,40}$")
    tipo: TipoInsumo
    descricao: str
    unidade: str
    preco_unitario: float = Field(ge=0)

    @field_validator("unidade", mode="before")
    @classmethod
    def _normalizar_unidade(cls, v: str) -> str:
        return normalize_unidade(v)

    fonte_preco: Literal["catalogo_proprio", "tabela_referencia", "cotacao_mercado", "negociado"]
    tabela_referencia_id: str | None = None
    codigo_referencia_externa: str | None = None
    historico_precos: list[HistoricoPreco] = Field(default_factory=list)
    atributos_especificos: AtributosInsumo = Field(default_factory=AtributosInsumo)
    # ADR-016: classe de compartilhamento (None = não anotado ainda -> VAL-INS-CLASS-01)
    classe_compartilhamento: ClasseCompartilhamento | None = None


class ComposicaoItem(BaseModel):
    """Linha da composição de uma CPU: insumo × coeficiente × categoria de custo."""

    model_config = ConfigDict(extra="forbid")

    insumo_id: str
    coeficiente: float = Field(gt=0)
    categoria_custo: CategoriaCusto
    unidade: str | None = None
    # ADR-107 D2: tipo de combustível quando categoria_custo == "COMBUSTIVEL".
    # None = legado (assume DIESEL_S10 quando categoria == COMBUSTIVEL/DIESEL).
    tipo_combustivel: TipoCombustivel | None = None


class FuncaoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funcao_id: str
    num_pessoas: int = Field(ge=1)
    horas_extras_pct: float | None = Field(default=None, ge=0, le=1)
    # Papel funcional na atividade — determina em qual pool de custo este membro é contabilizado.
    # direto   -> equipes diretas (skill 03)    | padrão para retrocompatibilidade
    # indireto -> custos indiretos de campo (skill 05)
    # gestao   -> equipe de gestão de obra (atribuída fora da CPU, per-projeto)
    papel: PapelFuncao = "direto"


class EquipamentoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equip_id: str
    num_unidades: int = Field(ge=1)
    # ADR-030 D1: consumo estimado na especificação da equipe (sobrepõe Insumo.atributos_especificos)
    consumo_litros_hora_estimado: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Consumo de combustível por unidade de equipamento por hora, em L/h. "
            "Sobrepõe Insumo.atributos_especificos.consumo_litros_hora na skill 03. "
            "Permite estimativas iniciais sem catálogo de insumos completo."
        ),
    )


class MaterialEquipe(BaseModel):
    """ADR-030 D2: Material direto consumido por hora de operação da equipe."""

    model_config = ConfigDict(extra="forbid")

    insumo_id: str
    consumo_por_hora: float = Field(
        gt=0,
        description="Quantidade consumida por hora de operação (ex: m³/h, kg/h, t/h)",
    )
    unidade: str
    descricao: str | None = None


class ComposicaoPadraoEquipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    funcoes: list[FuncaoEquipe]
    equipamentos: list[EquipamentoEquipe]
    # ADR-030 D2: materiais diretos consumidos pela equipe por hora
    materiais: list[MaterialEquipe] = Field(default_factory=list)

    @property
    def funcoes_diretas(self) -> list[FuncaoEquipe]:
        """Membros com papel='direto' — contabilizados em equipes diretas."""
        return [f for f in self.funcoes if f.papel == "direto"]

    @property
    def funcoes_indiretas(self) -> list[FuncaoEquipe]:
        """Membros com papel='indireto' — contabilizados em custos indiretos."""
        return [f for f in self.funcoes if f.papel == "indireto"]

    @property
    def funcoes_gestao(self) -> list[FuncaoEquipe]:
        """Membros com papel='gestao' — atribuídos separadamente, fora da CPU."""
        return [f for f in self.funcoes if f.papel == "gestao"]

    @property
    def num_pessoas_diretas(self) -> int:
        return sum(f.num_pessoas for f in self.funcoes_diretas)

    @property
    def num_pessoas_total(self) -> int:
        return sum(f.num_pessoas for f in self.funcoes)


class AtributosCategoriaCPU(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dmt_min_metros: float | None = Field(default=None, ge=0)
    dmt_max_metros: float | None = None
    # DMT médio das condições de calibração desta CPU (rastreabilidade ADR-007)
    dmt_referencia_m: float | None = Field(default=None, ge=0)


class Funcao(BaseModel):
    """Mapeamento canônico entre papel funcional, insumo de mão de obra e código SICRO/SINAPI.

    funcao_id -> insumo_id é a ligação de preço autorizada: uma CPU deve sempre referenciar
    funcao_id e o runtime resolve para o Insumo correto via este catálogo, eliminando a
    ambiguidade entre códigos P (SICRO) e IDs descritivos MendesLobo.
    """

    model_config = ConfigDict(extra="forbid")

    funcao_id: str = Field(pattern=r"^[A-Z0-9-]{3,40}$")
    descricao: str
    insumo_id: str  # -> Insumo(MAO_OBRA).codigo — fonte canônica de preço
    codigo_sicro: str | None = None  # ex: "P0040"
    codigo_sinapi: str | None = None


class CPU(BaseModel):
    """Composição de Preço Unitário — dimensão de insumos e custos (ADR-053 Fase 3).

    CPU é responsável por: composicao_itens (coeficientes de insumo), atributos de categoria
    e a referência estrangeira producao_id_ref para a entidade Produtividade.

    NÃO contém mais: producao_horaria (removido), composicao_padrao_equipe (removido).
    Esses campos eram redundantes e geravam assincronia com o catálogo de Produtividades.
    Catálogos legados que ainda enviam esses campos têm-nos silenciosamente ignorados
    via extra='ignore' e devem ser migrados com scripts/refactor_cpu_producao_adr053.py.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    codigo: str = Field(pattern=r"^[A-Z0-9-]{4,40}$")
    descricao: str
    unidade: str
    origem: Literal["REFERENCIA", "PROPRIA"]

    @field_validator("unidade", mode="before")
    @classmethod
    def _normalizar_unidade(cls, v: str) -> str:
        return normalize_unidade(v)

    cpu_referencia_id: str | None = None
    # FK para Produtividade — única fonte de producao_horaria e composicao_padrao_equipe.
    producao_id_ref: str
    categoria: CategoriaCPU
    composicao_itens: list[ComposicaoItem] = Field(default_factory=list)
    # composicao_padrao_equipe REMOVIDO em ADR-053 Fase 3 — leia de Produtividade via producao_id_ref.
    atributos_categoria: AtributosCategoriaCPU = Field(default_factory=AtributosCategoriaCPU)

    @property
    def composicao_completa(self) -> list[ComposicaoItem]:
        """Retorna composição fixa da CPU (somente insumos da própria CPU)."""
        return list(self.composicao_itens)

    @model_validator(mode="after")
    def _validar_producao_e_coeficientes(self) -> CPU:
        if not self.producao_id_ref:
            raise ValueError(f"CPU {self.codigo!r}: producao_id_ref é obrigatório (ADR-053)")
        return self


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
