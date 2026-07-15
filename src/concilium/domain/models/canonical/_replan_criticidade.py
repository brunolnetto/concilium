"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ._base import StatusMargem, ValidacaoItem
from ._financeiro_resultado import ControleVariavel


class ItemCustoAquisicao(BaseModel):
    """Custo de aquisição/contratação derivado de uma recomendação BUY/HIRE de 03C."""

    model_config = ConfigDict(extra="ignore")

    conflito_idx: int
    recurso_id: str
    tipo_recurso_id: str
    tipo_nome: str
    acao: Literal["BUY", "HIRE"]
    quantidade: float
    custo_unitario_dia: float
    dias: int
    custo_total: float
    categoria_bdi: Literal["EQUIPAMENTO", "MAO_OBRA"]


class ResultadoReconciliado(BaseModel):
    """LEGADO — resultado após delta de aquisição de recurso (skill 06A, removida).

    Todos os campos são populados com zeros pela skill-08 atual. Mantido apenas para
    retrocompatibilidade de serialização e fixtures de testes. Não usar em código novo.
    Candidato a remoção quando os fixtures de teste forem migrados.
    """

    model_config = ConfigDict(extra="ignore")

    itens_aquisicao: list[ItemCustoAquisicao] = Field(default_factory=list)
    delta_custo_total: float = 0.0
    venda_total_com_bdi: float = 0.0
    custo_total_reconciliado: float = 0.0
    margem_reconciliada_pct: float = 0.0
    status_margem_reconciliado: StatusMargem = "VERDE"
    delta_status: str | None = None


class ReplanSugestao(BaseModel):
    """Sugestão concreta de re-planejamento com checkpoint e parâmetros (08-replanejamento-e-cenarios)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    tipo: Literal["CRONOGRAMA", "EQUIPES", "RECURSOS", "ESCOPO", "BDI"]
    checkpoint_skill: str
    parametros_sugeridos: dict
    delta_margem_estimado: float
    confianca: Literal["ALTA", "MEDIA", "BAIXA"]
    justificativa: str
    restricoes: list[str] = Field(default_factory=list)
    controle: ControleVariavel = "TUNAVEL"  # ADR-028


class ReplanSuggestions(BaseModel):
    """Seção canônica produzida por 08-replanejamento-e-cenarios."""

    model_config = ConfigDict(extra="ignore")

    status_gatilho: StatusMargem
    delta_margem_necessario: float
    sugestoes: list[ReplanSugestao] = Field(default_factory=list)
    sugestao_prioritaria: str | None = None


# ── ADR-020: Criticidade multi-dimensional sem score sintético ───────────────


class DimensaoCriticidade(BaseModel):
    """Raw value + rank para uma única dimensão de criticidade."""

    model_config = ConfigDict(extra="ignore")

    valor_raw: float
    rank: int  # 1 = mais crítico
    percentil: float  # 0.0–1.0, 1.0 = mais crítico


class CriticidadeProfile(BaseModel):
    """Perfil multi-dimensional de uma atividade — sem score agregado."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    custo: DimensaoCriticidade
    duracao: DimensaoCriticidade
    recurso: DimensaoCriticidade
    sensibilidade: DimensaoCriticidade
    pareto_frontier: bool
    rank_lexicografico: int  # 1 = mais crítico
    classe: Literal["A+", "A", "B", "C"]
    interpretacao: str


class CostCriticalityResult(BaseModel):
    """Substitui o dict cost_criticality_report com tipo estruturado (ADR-020)."""

    model_config = ConfigDict(extra="ignore")

    atividades: list[CriticidadeProfile] = Field(default_factory=list)
    n_pareto_frontier: int = 0
    criterio_primario: Literal["custo", "duracao", "recurso"] = "custo"
    n_atividades: int = 0


# ── ADR-021: Espaço combinatorial de planos ──────────────────────────────────


# ── ADR-027: Perfil de exposição a custos por CPU ────────────────────────────


class VetorExposuraCpu(BaseModel):
    """Ponto no simplex de exposição de custo da CPU — ∑ coordenadas = 1,0.

    Cada coordenada é a fração do custo da CPU exposta a um indexador de mercado
    distinto. Preservado sem colapso escalar para permitir clustering por perfil
    de risco de custo (ADR-027).

    Derivação a partir de composicao_itens (categoria_custo):
        equip    ← EQUIPAMENTO + MAQUINARIO + DIESEL + COMBUSTIVEL
        mao_obra ← MAO_OBRA + PESSOAL
        material ← MATERIAL e demais categorias classificadas
        outros   ← residual = 1 – equip – mao_obra – material
    """

    model_config = ConfigDict(extra="ignore")

    equip: float = Field(ge=0.0, le=1.0)  # combustível / aluguel / depreciação de máquinas
    mao_obra: float = Field(ge=0.0, le=1.0)  # SINAPI / dissídio coletivo
    material: float = Field(ge=0.0, le=1.0)  # índices de insumos materiais
    outros: float = Field(ge=0.0, le=1.0)  # residual: mobilização, praticabilidade, outros

    @model_validator(mode="after")
    def _check_simplex(self) -> "VetorExposuraCpu":
        total = round(self.equip + self.mao_obra + self.material + self.outros, 6)
        if abs(total - 1.0) > 1e-4:
            raise ValueError(
                f"VetorExposuraCpu deve somar 1,0; soma={total:.6f} "
                f"(equip={self.equip}, mao_obra={self.mao_obra}, "
                f"material={self.material}, outros={self.outros})"
            )
        return self


class CpuExposurePerfil(BaseModel):
    """Perfil de exposição de custo de uma CPU — ponto no simplex de risco (ADR-027).

    O vetor é preservado sem colapso escalar para clustering.
    O escalar de sensibilidade para a análise Pareto (skill 09) é derivado
    on-the-fly via produto interno com pesos de volatilidade do perfil.
    """

    model_config = ConfigDict(extra="ignore")

    cpu_id: str
    vetor: VetorExposuraCpu  # ponto no simplex — não-colapsado
    fator_praticabilidade: float = Field(ge=0.0, le=1.0)  # multiplicador ortogonal: 0=insensível, 1=altamente sazonal
    fonte: Literal["CATALOGO", "CALCULADO"] = "CALCULADO"


class Lever(BaseModel):
    """Intervenção paramétrica que melhora a margem do plano."""

    model_config = ConfigDict(extra="ignore")

    tipo: Literal[
        # Legado (ADR-021)
        "EXPAND_POOL",
        "REDUCE_DURATION",
        "ADD_TEAMS",
        "REVIEW_BDI",
        # Baseados em LeverEquilibrio real (ADR-082) — pool-aware
        "SERIALIZAR_CRONOGRAMA",  # fechar_gap_escala: serializar equipes, estender prazo
        "MELHORAR_PRATICABILIDADE",  # fechar_gap_praticabilidade: reordenar por época climática
        "OTIMIZAR_POOL",  # fechar_gap_pool: reduzir overhead mob/demob/ociosidade
        "RECALIBRAR_PU",  # revisao_bdi_minima: recalibrar PU para cobrir custo real
    ]
    checkpoint_skill: str
    parametros: dict = Field(default_factory=dict)
    delta_margem_estimado: float
    custo_aplicacao: float  # custo adicional estimado em R$ para aplicar
    ratio_beneficio: float  # delta_margem / max(custo_aplicacao_norm, 1e-6)
    confianca: Literal["ALTA", "MEDIA", "BAIXA"]
    justificativa: str
    controle: ControleVariavel = "TUNAVEL"  # ADR-028


class RepairStep(BaseModel):
    """Um passo na sequência de repair (AMARELO/VERMELHO -> VERDE)."""

    model_config = ConfigDict(extra="ignore")

    ordem: int
    lever: Lever
    margem_acumulada_apos: float
    status_apos: StatusMargem


class RepairPath(BaseModel):
    """Sequência mínima de intervenções para atingir VERDE."""

    model_config = ConfigDict(extra="ignore")

    viavel: bool  # True se o caminho atinge faixa_alvo.min
    passos: list[RepairStep] = Field(default_factory=list)
    margem_projetada: float
    status_projetado: StatusMargem


class OportunidadeVerde(BaseModel):
    """Oportunidade de aumentar margem num plano já VERDE."""

    model_config = ConfigDict(extra="ignore")

    lever: Lever
    margem_adicional_estimada: float
    risco: Literal["BAIXO", "MEDIO", "ALTO"]


class PlanSpaceResult(BaseModel):
    """Resultado do 08-replanejamento-e-cenarios (estágio explorador): repair_path e/ou oportunidades."""

    model_config = ConfigDict(extra="ignore")

    status_entrada: StatusMargem
    margem_entrada: float
    repair_path: RepairPath | None = None
    oportunidades: list[OportunidadeVerde] = Field(default_factory=list)


# ── ADR-051: Validação Convergente de Preço Unitário ────────────────────────


class CategoriaConvergencia(BaseModel):
    """Convergência de preço unitário em uma categoria de custo."""

    model_config = ConfigDict(extra="ignore")

    pu_teorico: float  # PU teórico derivado de composição/produção
    pu_planejado: float  # PU calculado pelo pipeline
    desvio_pct: float  # (planejado - teorico) / teorico × 100%
    status: Literal["VERDE", "AMARELO", "VERMELHO"]


class ValidacaoCatalogoPUItem(BaseModel):
    """Validação de PU teórico vs catalogado para CPU isolada (ADR-051 §Camada 1)."""

    model_config = ConfigDict(extra="ignore")

    cpu_id: str
    unidade: str

    producao_horaria: float
    custo_hora_teorico: float  # soma de componentes

    pu_teorico_sem_bdi: float  # = custo_hora / producao_hora
    pu_catalogado_sem_bdi: float | None = None  # precos_unitarios_sbdi.total (se existe)

    desvio_pct: float  # (catalogado - teorico) / teorico × 100% (se catalogado existe)
    status_convergencia: Literal["VERDE", "AMARELO", "VERMELHO"]  # ±5% / ±10% / >10%

    # Por categoria
    detalhes: dict[str, CategoriaConvergencia] = Field(
        default_factory=dict
    )  # {material, diesel, mao_obra, equipamentos}

    validacoes: list[ValidacaoItem] = Field(default_factory=list)


class ValidacaoPUResumida(BaseModel):
    """Resumo consolidado de validações de PU (catálogo) para relatório."""

    model_config = ConfigDict(extra="ignore")

    # Nível catálogo
    validacoes_catalogo: list[ValidacaoCatalogoPUItem] = Field(default_factory=list)

    # Resumo
    num_verde: int = 0
    num_amarelo: int = 0
    num_vermelho: int = 0
    status_geral: Literal["VERDE", "AMARELO", "VERMELHO"] = "VERDE"

    recomendacoes: list[str] = Field(default_factory=list)


