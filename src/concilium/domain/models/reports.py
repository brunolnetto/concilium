"""ADR-026 — Payloads dos relatórios analíticos de Saída (skills 15, 16, 17).

RelatorioCriticidade  (Skill 15): ranking Pareto de atividades + decisões do 11.
RelatorioSensibilidade (Skill 16): levers de margem do 11-replanejamento-e-cenarios.
RelatorioIntervencao   (Skill 17): eixos combinados de intervenção do 11-replanejamento-e-cenarios.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from concilium.domain.models.canonical import VetorExposuraCpu


# ── Skill 15 — Relatório de Criticidade ──────────────────────────────────


class ItemCriticidadeRelatorio(BaseModel):
    """Linha do ranking de criticidade por atividade (ADR-026 §D4)."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    descricao: str
    classificacao: Literal["A+", "A", "B", "C"]
    pareto_frontier: bool
    custo_share: float = Field(ge=0, le=1)
    duracao_share: float = Field(ge=0, le=1)
    sensibilidade: float = Field(ge=0)
    recurso_status: Literal["CONSTRANGIDO", "LIVRE"]
    decisoes_vinculadas: list[str] = Field(default_factory=list)  # IDs de DecisionLogEntry


class RelatorioCriticidade(BaseModel):
    """Relatório analítico de criticidade — artefato RELATORIO_CRITICIDADE (ADR-026 §D4)."""

    model_config = ConfigDict(extra="ignore")

    projeto_id: str
    versao: str
    gerado_em: datetime
    itens: list[ItemCriticidadeRelatorio] = Field(default_factory=list)

    # Estatísticas agregadas
    total_atividades: int = 0
    total_A_mais: int = 0
    total_A: int = 0
    total_B: int = 0
    total_C: int = 0
    custo_A_mais_pct: float = Field(default=0.0, ge=0, le=1)  # soma custo_share dos A+

    notas_engenheiro: str | None = None  # do 09-registro-decisoes geral

    def calcular_estatisticas(self) -> RelatorioCriticidade:
        """Recalcula contadores a partir dos itens. Retorna nova instância."""
        from collections import Counter

        c = Counter(item.classificacao for item in self.itens)
        custo_Aplus = sum(i.custo_share for i in self.itens if i.classificacao == "A+")
        return self.model_copy(
            update={
                "total_atividades": len(self.itens),
                "total_A_mais": c["A+"],
                "total_A": c["A"],
                "total_B": c["B"],
                "total_C": c["C"],
                "custo_A_mais_pct": round(custo_Aplus, 4),
            }
        )


# ── Skill 16 — Relatório de Sensibilidade ────────────────────────────────


class ItemSensibilidade(BaseModel):
    """Lever de margem individual (ADR-026 §D4)."""

    model_config = ConfigDict(extra="ignore")

    lever_tipo: Literal["EXPAND_POOL", "REDUCE_DURATION", "ADD_TEAMS", "REVIEW_BDI"]
    lever_checkpoint: str  # skill que implementa o lever
    delta_margem: float  # incremento de margem estimado (fração)
    custo_aplicacao: float | None = None  # custo adicional de aplicar o lever (R$)
    ratio_beneficio: float = 0.0  # delta_margem / custo_aplicacao_normalizado
    confianca: Literal["ALTA", "MEDIA", "BAIXA"] = "MEDIA"
    atividades_afetadas: list[str] = Field(default_factory=list)


class ItemExposureCpu(BaseModel):
    """Exposição a risco de overrun por CPU — seção do RelatorioSensibilidade (ADR-027)."""

    model_config = ConfigDict(extra="ignore")

    cpu_id: str
    descricao_cpu: str
    vetor: VetorExposuraCpu  # ponto no simplex — não-colapsado
    fator_praticabilidade: float = Field(ge=0.0, le=1.0)
    atividades_afetadas: list[str] = Field(default_factory=list)
    participacao_custo: float = Field(default=0.0, ge=0, le=1)  # soma cost_share das atividades
    recomendacao: str = ""  # ex: "CPU com alta exposição a combustível — considerar alternativa"


class RelatorioSensibilidade(BaseModel):
    """Relatório analítico de sensibilidade de margem — artefato RELATORIO_SENSIBILIDADE (ADR-026 §D4)."""

    model_config = ConfigDict(extra="ignore")

    projeto_id: str
    versao: str
    gerado_em: datetime
    status_margem: Literal["VERDE", "AMARELO", "VERMELHO"]
    margem_entrada: float
    margem_alvo_min: float
    repair_viavel: bool = False
    passos_repair: list[ItemSensibilidade] = Field(default_factory=list)
    oportunidades: list[ItemSensibilidade] = Field(default_factory=list)
    margem_pos_repair: float | None = None
    exposicao_por_cpu: list[ItemExposureCpu] = Field(default_factory=list)  # ADR-027


# ── Skill 17 — Relatório de Intervenção ──────────────────────────────────


class EixoIntervencao(BaseModel):
    """Eixo combinado de intervenção (ADR-026 §D4)."""

    model_config = ConfigDict(extra="ignore")

    nome: str  # ex: "Custo vs Prazo"
    margem_estimada: float
    prazo_delta_dias: int | None = None
    confianca: Literal["ALTA", "MEDIA", "BAIXA"] = "MEDIA"
    risco: Literal["BAIXO", "MEDIO", "ALTO"] = "MEDIO"
    levers_combinados: list[str] = Field(default_factory=list)  # tipos de lever aplicados


class RelatorioIntervencao(BaseModel):
    """Relatório analítico de espaço de intervenção — artefato RELATORIO_INTERVENCAO (ADR-026 §D4)."""

    model_config = ConfigDict(extra="ignore")

    projeto_id: str
    versao: str
    gerado_em: datetime
    status_entrada: Literal["VERDE", "AMARELO", "VERMELHO"]
    eixos_intervencao: list[EixoIntervencao] = Field(default_factory=list)
    fronteira_pareto: list[EixoIntervencao] = Field(default_factory=list)
    recomendacao_primaria: EixoIntervencao | None = None


# ── Resolução de referências circulares (ADR-027) ─────────────────────────
# VetorExposuraCpu vive em canonical.py, que importa reports.py no seu final.
# O import abaixo é tardio (E402) mas seguro: canonical.py define VetorExposuraCpu
# na linha 964, antes de importar reports.py na linha 1076, portanto o símbolo
# já existe no módulo parcial quando chegamos aqui.
from concilium.domain.models.canonical import VetorExposuraCpu  # noqa: E402

ItemExposureCpu.model_rebuild()
RelatorioSensibilidade.model_rebuild()
