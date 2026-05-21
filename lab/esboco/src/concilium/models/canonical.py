"""Camada 4 — Modelo canônico do orçamento (produzido pelo pipeline)."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

StatusValidacao = Literal["OK", "AVISO", "ERRO"]
StatusMargem = Literal["VERDE", "AMARELO", "VERMELHO"]
StatusProjeto = Literal["RASCUNHO", "EM_VALIDACAO", "APROVADO", "EM_EXECUCAO", "CONCLUIDO"]


class ValidacaoItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    codigo: str
    status: StatusValidacao
    mensagem: str | None = None


class Meta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    versao_schema: str = "1.0.0"
    gerado_em: datetime
    framework: Literal["concilium"] = "concilium"
    perfil_construtora_id: str
    jurisdicao_id: str


class Coordenadas(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class RegimeTrabalho(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dias_semana: int = Field(ge=1, le=7)
    horas_dia: int = Field(ge=1, le=24)


class Projeto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID | str
    nome: str
    tipo_obra: Literal["terraplenagem", "pavimentacao", "saneamento"]
    localizacao: str
    coordenadas: Coordenadas
    regime_trabalho: RegimeTrabalho
    data_inicio: date
    data_termino: date
    status: StatusProjeto = "RASCUNHO"
    versao_referencia_id: str
    snapshot_catalogo_id: str
    snapshot_perfil_id: str
    revisao: int = Field(default=1, ge=1)


class Praticabilidade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fonte: str
    limiar_inviabilidade_mm: float = Field(ge=0)
    calculada_em: datetime
    percentual_produtivo_mensal: dict[str, float]


class EapItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    ordem: int = Field(ge=1)
    cpu_id: str
    descricao: str
    unidade: str
    quantitativo: float = Field(gt=0)
    origem_template: bool = False


# Eap é apenas alias para list[EapItem] — exposto como nome no canônico
Eap = list[EapItem]


class Atividade(BaseModel):
    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    eap_item_id: str
    descricao: str
    fracao_quantitativo: float = Field(gt=0, le=1)
    quantitativo_atividade: float = Field(gt=0)
    cpu_id: str


class ArestaActivityDag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    de: str
    para: str


class ActivityDag(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nos: list[str]
    arestas: list[ArestaActivityDag]
    ordem_topologica: list[str]


class DistribuicaoMensal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    num_equipes: int = Field(ge=0)
    qtd_executada: float = Field(ge=0)
    qtd_acumulada: float = Field(ge=0)
    pct: float = Field(ge=0, le=1)


class Cronograma(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    dias_trabalhados_semana: int
    distribuicao_mensal: dict[str, DistribuicaoMensal]
    pct_completude: float = Field(ge=0, le=1)


class FuncaoEquipeDireta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    funcao_id: str
    descricao: str
    num_pessoas: int
    salario_base: float
    percentual_encargos: float
    horas_extras_pct: float
    custo_mensal_unitario: float


class EquipamentoEquipeDireta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equip_id: str
    descricao: str
    num_unidades: int
    custo_mensal: float
    consumo_litros_hora: float | None = None
    preco_diesel_litro: float | None = None
    custo_combustivel_mensal: float
    custo_mensal_total: float


class EquipeDireta(BaseModel):
    model_config = ConfigDict(extra="ignore")

    equipe_id: str
    item_id: str
    cpu_id: str
    nome: str
    num_equipes_base: int = 1
    funcoes: list[FuncaoEquipeDireta]
    equipamentos: list[EquipamentoEquipeDireta]
    custo_mao_obra_mensal: float
    custo_equipamentos_mensal: float
    custo_fixo_mensal: float
    permanencia_meses: float = Field(ge=0)
    custo_total: float


class PrecoUnitarioCategoria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material: float
    diesel: float
    mao_obra: float
    equipamentos: float
    total: float


class BdiCategorias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material: float
    diesel: float
    mao_obra: float
    equipamentos: float


class SubtotalCategorias(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material: float
    diesel: float
    mao_obra: float
    equipamentos: float
    total: float


class SubtotalSemBdiComBdi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sem_bdi: SubtotalCategorias
    com_bdi: SubtotalCategorias


class Planejamento(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    cpu_id: str
    quantitativo: float
    preco_unitario: PrecoUnitarioCategoria
    bdi: BdiCategorias
    preco_unitario_com_bdi: PrecoUnitarioCategoria
    subtotal: SubtotalSemBdiComBdi


class Mobilizacao(BaseModel):
    model_config = ConfigDict(extra="ignore")

    descricao: str
    num_unidades: int
    origem: str
    destino: str
    distancia_km: float
    custo_km: float
    custo_total: float


class Indireto(BaseModel):
    model_config = ConfigDict(extra="ignore")

    categoria: Literal["ADM", "TOP", "LAB", "QSMS", "MOB"]
    descricao: str
    funcoes: list[dict] = Field(default_factory=list)
    equipamentos: list[dict] = Field(default_factory=list)
    verbas_mensais: list[dict] = Field(default_factory=list)
    verbas_fixas: list[dict] = Field(default_factory=list)
    mobilizacoes: list[Mobilizacao] = Field(default_factory=list)
    baixadas: list[dict] = Field(default_factory=list)
    permanencia_meses: float | None = None
    custo_total: float


class PontoEquilibrio(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    custo_fixo_equipe: float
    custo_venda_cpu: float
    delta: float
    delta_pct: float
    status_validacao: StatusValidacao


class Venda(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_sem_bdi: float
    total_com_bdi: float


class CustoTotal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    direto_equipes: float
    indireto_adm: float = 0
    indireto_top: float = 0
    indireto_lab: float = 0
    indireto_qsms: float = 0
    indireto_mob: float = 0
    total: float


class Resultado(BaseModel):
    model_config = ConfigDict(extra="ignore")

    venda: Venda
    custo: CustoTotal
    resultado_financeiro: float
    margem_pct: float
    status_margem: StatusMargem
    validacoes: list[ValidacaoItem]


class CanonicalModel(BaseModel):
    """Estado completo do orçamento — produzido incrementalmente pelo pipeline."""

    model_config = ConfigDict(extra="ignore")

    meta: Meta
    projeto: Projeto
    praticabilidade: Praticabilidade | None = None
    eap: list[EapItem] = Field(default_factory=list)
    atividades: list[Atividade] | None = None
    activity_dag: ActivityDag | None = None
    cronograma: list[Cronograma] = Field(default_factory=list)
    equipes_diretas: list[EquipeDireta] = Field(default_factory=list)
    planejamento: list[Planejamento] = Field(default_factory=list)
    indiretos: list[Indireto] = Field(default_factory=list)
    ponto_equilibrio: list[PontoEquilibrio] = Field(default_factory=list)
    resultado: Resultado | None = None
