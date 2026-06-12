"""ADR-070 — Campaign model: typed contracts for GO configuration space exploration."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

ClassificacaoO = Literal["IDEAL", "ATENCAO", "CRITICO"]
ClassificacaoEF = Literal["DENTRO_EXPECTATIVA", "ATENCAO", "FORA_EXPECTATIVA"]
ViabilidadeStatus = Literal[
    "APROVADO",
    "APROVADO_COM_RESSALVAS",
    "BLOQUEADO_COM_INVESTIGACAO",
    "BLOQUEADO",
    "ERRO",
]
CampaignStatus = Literal[
    "SUCESSO",
    "SUCESSO_PARCIAL",
    "FRONTEIRA_UNICA",
    "INFEASIBLE",
    "INCONCLUSO",
    "ABORTADO",
]


@dataclass
class ParametroSweep:
    campo: str        # dot-path into the spec dict, e.g. "spec.inputs_cronograma.rcpsp_spec.pool_config.objetivo"
    valores: list[Any]
    scope: str = "global"           # "global" = mesma valor para todos (padrão)
                                    # "per_item" = varia independentemente por item_id (k^n cenários)
                                    # "cpu_alternativo" = substitui cpu_id no EAP para item_ids
    item_ids: list[str] | None = None  # para per_item / cpu_alternativo: quais item_ids variar


@dataclass
class PerfilExpectativas:
    meta_margem_pct: float = 0.10
    tolerancia_margem: float = 0.03
    prazo_contratual_semanas: int | None = None  # if None, derived from data_termino - data_inicio


@dataclass
class GoResearchCampaignBundle:
    base_spec: dict                                    # referencia.json or ProjetoSpec dict
    sweep: list[ParametroSweep]
    perfil_expectativas: PerfilExpectativas = field(default_factory=PerfilExpectativas)
    constraints: list[str] = field(default_factory=list)
    top_k: int = 5
    campaign_version: str = "v1"
    campaign_id: str = ""

    def __post_init__(self):
        if not self.campaign_id:
            h = hashlib.sha1(json.dumps(self.base_spec, sort_keys=True, default=str).encode()).hexdigest()[:8]
            self.campaign_id = f"campaign-{h}"

    def cardinality(self) -> int:
        """Produto cartesiano do espaço discretizado: Π |valores_i| para cada dimensão.

        Para scope="global": contribui com len(valores).
        Para scope="per_item" ou "cpu_alternativo": contribui com len(valores)^len(item_ids)
        (cada item_id é uma dimensão independente com k valores).
        """
        result = 1
        for s in self.sweep:
            k = len(s.valores)
            if s.scope in ("per_item", "cpu_alternativo") and s.item_ids:
                result *= k ** len(s.item_ids)
            else:
                result *= k
        return result

    def cardinality_breakdown(self) -> list[dict]:
        """Retorna contribuição de cada dimensão para a cardinalidade total."""
        rows = []
        acc = 1
        for s in self.sweep:
            k = len(s.valores)
            if s.scope in ("per_item", "cpu_alternativo") and s.item_ids:
                contrib = k ** len(s.item_ids)
                acc *= contrib
                rows.append({"campo": s.campo, "k": k, "n_items": len(s.item_ids),
                              "contrib": contrib, "acumulado": acc, "scope": s.scope})
            else:
                acc *= k
                rows.append({"campo": s.campo, "k": k, "acumulado": acc, "scope": s.scope})
        return rows


@dataclass
class VetorEspacoO:
    prazo_semanas: int | None = None
    folga_semanas: float | None = None          # prazo_contratual - prazo_semanas (positive = on time)
    fe_nec_medio: float | None = None
    itens_criticos_pct: float | None = None     # fraction of items with fe_nec > 1.25
    gap_pool_total: float | None = None
    custo_mob_window_total: float | None = None
    # ADR-108: métricas do cronograma
    utilizacao_recursos_pct: float | None = None  # semanas produtivas / semanas mobilizadas
    paralelismo_medio: float | None = None         # atividades ativas em simultâneo (média semanal)
    idle_pool_pct: float | None = None             # cubo_pool_face quando disponível


@dataclass
class VetorEspacoEF:
    margem_pct: float | None = None
    custo_execucao_pool: float | None = None
    custo_indireto: float | None = None
    preco_venda: float | None = None
    ratio_pool_vs_cat: float | None = None      # custo_execucao_pool / PU_cat_Q (< 1.0 = good)
    fidelidade_gates: bool | None = None
    # ADR-108: composição de custo do cubo_analitico
    share_mo_pct: float | None = None           # MO / custo_direto_total
    share_eq_pct: float | None = None           # equipamento / custo_direto_total
    share_comb_pct: float | None = None         # combustivel / custo_direto_total
    concentracao_atividade: float | None = None  # HHI de concentração por atividade (1/N..1)


@dataclass
class CenarioAvaliado:
    cenario_id: str
    parametros_variados: dict
    viabilidade: ViabilidadeStatus
    vetor_O: VetorEspacoO
    vetor_EF: VetorEspacoEF
    classificacao_O: ClassificacaoO
    classificacao_EF: ClassificacaoEF
    pareto_O: bool = False
    pareto_EF: bool = False
    pareto_intersecao: bool = False
    rank_final: int | None = None
    erro: str | None = None


@dataclass
class JustificativaCenario:
    motivo_inclusao: str
    destaques_O: list[str]
    destaques_EF: list[str]
    alertas: list[str]
    parametros_chave: dict


@dataclass
class CenarioRankeado:
    rank: int
    cenario: CenarioAvaliado
    justificativa: JustificativaCenario


@dataclass
class CampaignOutputBundle:
    campaign_id: str
    campaign_version: str
    gerado_em: datetime
    n_cenarios_avaliados: int
    n_cenarios_viaveis: int
    n_falhas: int
    status: CampaignStatus
    cenarios: list[CenarioAvaliado]
    shortlist: list[CenarioRankeado]


# ---------------------------------------------------------------------------
# CampaignBundleCube — camada analítica multidimensional (ADR-070 §4b + §D8)
# ---------------------------------------------------------------------------

TendenciaMarginal = Literal["crescente", "decrescente", "nao_monotona", "indeterminado"]


@dataclass
class CuboDimensao:
    """Uma dimensão do espaço de exploração (= um ParametroSweep)."""

    nome: str          # label legível, ex: "regime_trabalho" ou "deadline_weeks"
    campo: str         # campo do ProjetoSpec, ex: "meta.regime_trabalho"
    valores: list[Any] # valores únicos ordenados nesta dimensão


@dataclass
class CelulaAnalitica:
    """Grão mínimo do cubo: uma combinação de valores de dimensões + métricas."""

    dimensoes: dict[str, Any]          # {nome_dim: valor} para esta célula
    cenario_id: str | None             # None se esta célula não foi avaliada
    vetor_O: "VetorEspacoO | None"
    vetor_EF: "VetorEspacoEF | None"
    classificacao_O: ClassificacaoO | None
    classificacao_EF: ClassificacaoEF | None
    viabilidade: ViabilidadeStatus | None
    pareto_O: bool = False
    pareto_EF: bool = False
    pareto_intersecao: bool = False


@dataclass
class FaceAnalitica:
    """Projeção 2D do cubo em duas dimensões para uma métrica específica.

    Permite visualizar o mapa de calor de qualquer métrica na interseção
    de dois parâmetros do sweep, mantendo os demais fixos no valor mediano.
    """

    dim_x: str                              # nome da dimensão no eixo X
    dim_y: str                              # nome da dimensão no eixo Y
    metrica: str                            # métrica exibida (ex: "prazo_semanas")
    valores_x: list[Any]                    # valores únicos da dim X (colunas)
    valores_y: list[Any]                    # valores únicos da dim Y (linhas)
    grade: list[list[float | None]]         # grade[i_y][i_x] = valor da métrica


@dataclass
class ResumoMarginal:
    """Efeito marginal de uma dimensão numa métrica (mantendo as demais fixas na mediana)."""

    dimensao: str
    metrica: str
    valores: list[Any]                      # valores da dimensão, em ordem
    medias: list[float | None]              # média da métrica para cada valor
    tendencia: TendenciaMarginal


@dataclass
class CampaignBundleCube:
    """Cubo analítico multidimensional sobre um CampaignOutputBundle.

    Dimensões = parâmetros do sweep. Medidas = vetores O e EF/F.
    Faces = projeções 2D para qualquer par de dimensões.
    Resumos marginais = efeito isolado de cada dimensão.

    Invariantes:
    - len(celulas) = Π len(dim.valores) para todas as dimensões
    - Células não avaliadas têm cenario_id=None e vetores=None
    - cobertura_pct = n_celulas_avaliadas / n_celulas_total
    """

    campaign_id: str
    dimensoes: list[CuboDimensao]
    celulas: list[CelulaAnalitica]
    faces: list[FaceAnalitica]              # uma face por par de dimensões
    resumos_marginais: list[ResumoMarginal]  # uma por (dimensão × métrica)
    n_celulas_total: int
    n_celulas_avaliadas: int
    n_celulas_viaveis: int
    n_celulas_pareto: int
    cobertura_pct: float                    # n_avaliadas / n_total
