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


@dataclass
class VetorEspacoO:
    prazo_semanas: int | None = None
    folga_semanas: float | None = None          # prazo_contratual - prazo_semanas (positive = on time)
    fe_nec_medio: float | None = None
    itens_criticos_pct: float | None = None     # fraction of items with fe_nec > 1.25
    gap_pool_total: float | None = None
    custo_mob_window_total: float | None = None


@dataclass
class VetorEspacoEF:
    margem_pct: float | None = None
    custo_execucao_pool: float | None = None
    custo_indireto: float | None = None
    preco_venda: float | None = None
    ratio_pool_vs_cat: float | None = None      # custo_execucao_pool / PU_cat_Q (< 1.0 = good)
    fidelidade_gates: bool | None = None


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
