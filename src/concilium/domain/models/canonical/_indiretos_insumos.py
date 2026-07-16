"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ._eap import DistribuicaoSemanal


class IndirectoCostComponent(BaseModel):
    """Componente de custo indireto: MÃO_DE_OBRA, EQUIPAMENTOS ou VERBAS."""

    model_config = ConfigDict(extra="ignore")

    nome: str
    custo_fixo_mensal: float = Field(ge=0)
    itens: list[dict] = Field(default_factory=list)


class IndirectoCategoria(BaseModel):
    """Categoria de custo indireto com driver de escalonamento (ADR-009)."""

    model_config = ConfigDict(extra="ignore")

    categoria: Literal["TOP", "ADM", "LAB", "QSMS", "MOB"]
    driver: Literal["permanencia", "one_time"]
    mao_de_obra: IndirectoCostComponent | None = None
    equipamentos: IndirectoCostComponent | None = None
    verbas: IndirectoCostComponent | None = None
    custo_fixo_mensal: float = Field(default=0.0, ge=0)
    custo_fixo_total: float = Field(default=0.0, ge=0)  # apenas para driver="one_time"

    @property
    def custo_semanal(self) -> float:
        """Custo por semana para categorias permanencia. MOB retorna 0 (one_time)."""
        if self.driver == "one_time":
            return 0.0
        from concilium.domain.constants import SEMANAS_POR_MES

        return round(self.custo_fixo_mensal / SEMANAS_POR_MES, 2)

    def custo_total_para_semanas(self, n_semanas: int) -> float:
        """Custo total para uma duração em semanas."""
        if self.driver == "one_time":
            return self.custo_fixo_total
        return round(self.custo_semanal * n_semanas, 2)


class IndiretoSemanal(BaseModel):
    """Breakdown semanal de custo indireto por categoria (ADR-009 §D2)."""

    model_config = ConfigDict(extra="ignore")

    semana: int = Field(ge=0)
    categoria: str
    custo_mao_de_obra: float = Field(default=0.0, ge=0)
    custo_equipamentos: float = Field(default=0.0, ge=0)
    custo_verbas: float = Field(default=0.0, ge=0)
    custo_semanal: float = Field(default=0.0, ge=0)
    ativa: bool = True


# ── ADR-010: Activity Cost Breakdown Models ────────────────────────────────────


class InsumoComponenteAtividade(BaseModel):
    """Componente de custo direto de uma atividade: MO, EQUIPAMENTOS ou MATERIAL."""

    model_config = ConfigDict(extra="ignore")

    nome: str
    itens: list[dict] = Field(default_factory=list)  # legado — sem schema
    # ADR-058 D1: itens tipados com rastreabilidade de insumo individual
    itens_detalhados: list["InsumoDetalheAtvCanonical"] = Field(default_factory=list)
    custo_total: float = Field(ge=0)


class InsumoDetalheAtvCanonical(BaseModel):
    """ADR-058 D1: insumo individual rastreável dentro de uma atividade (versão Pydantic).

    Versão serializável do dataclass InsumoDetalheAtividade em domain/models/analitica.py.
    """

    model_config = ConfigDict(extra="ignore")

    insumo_id: str
    descricao: str
    categoria: str  # "MAO_OBRA" | "EQUIPAMENTO" | "DIESEL" | "MATERIAL"
    num_unidades: float = 0.0
    custo_unitario_mensal: float = 0.0
    permanencia_meses: float = 0.0
    custo_total: float = 0.0


class AtividadeInsumo(BaseModel):
    """Insumo de custo direto de uma atividade (ADR-010 §D1)."""

    model_config = ConfigDict(extra="ignore")

    categoria: str
    mao_de_obra: InsumoComponenteAtividade | None = None
    equipamentos: InsumoComponenteAtividade | None = None
    material: InsumoComponenteAtividade | None = None

    @property
    def custo_total_direto(self) -> float:
        return round(
            (self.mao_de_obra.custo_total if self.mao_de_obra else 0.0)
            + (self.equipamentos.custo_total if self.equipamentos else 0.0)
            + (self.material.custo_total if self.material else 0.0),
            2,
        )


class IndiretoAlocacao(BaseModel):
    """Como uma atividade compartilha os pools de custo indireto (ADR-010 §D2)."""

    model_config = ConfigDict(extra="ignore")

    estrategia: Literal["esforco_mo", "duracao", "fator_explicito"]
    percentual_horas_mo: float | None = Field(default=None, ge=0, le=1)
    semanas_atividade: int | None = Field(default=None, ge=0)
    semanas_projeto: int | None = Field(default=None, ge=0)
    fator_top: float = Field(default=0.0, ge=0, le=1)
    fator_adm: float = Field(default=0.0, ge=0, le=1)
    fator_lab: float = Field(default=0.0, ge=0, le=1)
    fator_qsms: float = Field(default=0.0, ge=0, le=1)


class CustoIndiretoAtividade(BaseModel):
    """Parcela de custo indireto atribuída a uma atividade (ADR-010 §D2)."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    alocacao: IndiretoAlocacao
    custo_top_atribuido: float = Field(default=0.0, ge=0)
    custo_adm_atribuido: float = Field(default=0.0, ge=0)
    custo_lab_atribuido: float = Field(default=0.0, ge=0)
    custo_qsms_atribuido: float = Field(default=0.0, ge=0)

    @property
    def custo_total_indireto(self) -> float:
        return round(
            self.custo_top_atribuido + self.custo_adm_atribuido + self.custo_lab_atribuido + self.custo_qsms_atribuido,
            2,
        )


class MobilizacaoAtividade(BaseModel):
    """Custo de setup/teardown específico de uma atividade (ADR-010 §D3)."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    fase: Literal["setup", "teardown", "both"]
    mao_de_obra: InsumoComponenteAtividade | None = None
    equipamentos: InsumoComponenteAtividade | None = None
    material: InsumoComponenteAtividade | None = None
    alocacao: Literal["semana_inicio", "semana_fim", "ambas"] = "semana_inicio"

    @property
    def custo_total(self) -> float:
        return round(
            (self.mao_de_obra.custo_total if self.mao_de_obra else 0.0)
            + (self.equipamentos.custo_total if self.equipamentos else 0.0)
            + (self.material.custo_total if self.material else 0.0),
            2,
        )

    def alocacao_por_semana(self, semana_inicio: int, semana_fim: int) -> dict[int, float]:
        if self.alocacao == "semana_inicio":
            return {semana_inicio: self.custo_total}
        if self.alocacao == "semana_fim":
            return {semana_fim: self.custo_total}
        metade = round(self.custo_total / 2, 2)
        return {semana_inicio: metade, semana_fim: metade}


class AtividadeCustoCompleto(BaseModel):
    """Breakdown completo de custo de uma atividade (ADR-010 §D4)."""

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    nome: str = ""
    semana_inicio: int = Field(ge=0)
    semana_fim: int = Field(ge=0)
    custos_diretos: list[AtividadeInsumo] = Field(default_factory=list)
    indireto_alocacao: IndiretoAlocacao | None = None
    custo_indireto_atribuido: float = Field(default=0.0, ge=0)
    mobilizacao: MobilizacaoAtividade | None = None

    @property
    def duracao_semanas(self) -> int:
        return max(1, self.semana_fim - self.semana_inicio + 1)

    @property
    def custo_direto_total(self) -> float:
        return round(sum(i.custo_total_direto for i in self.custos_diretos), 2)

    @property
    def custo_mobilizacao_atividade(self) -> float:
        return self.mobilizacao.custo_total if self.mobilizacao else 0.0

    @property
    def custo_total_atividade(self) -> float:
        return round(
            self.custo_direto_total + self.custo_indireto_atribuido + self.custo_mobilizacao_atividade,
            2,
        )


# ── ADR-004: Weekly schedule canonical models ─────────────────────────────


class ScheduledActivityCanonical(BaseModel):
    """Atividade agendada (semanal) — com detalhe de distribuição de execução.

    Unifica scheduling (semana início/fim, datas) com distribuição de execução (qtd por semana).
    """

    model_config = ConfigDict(extra="ignore")

    activity_id: str
    start_week: int
    end_week: int
    duration_weeks: int
    data_inicio: date | None = None
    data_fim: date | None = None
    assigned_resources: dict[str, int] = Field(default_factory=dict)
    # ADR-074: normalized ramp profile propagated from Activity; None = flat demand
    ramp_profile: list[float] | None = None

    # Distribuição semanal: chave "AAAA-Www" -> {num_equipes, qtd_executada, qtd_acumulada, pct, eficiencia}
    distribuicao_semanal: dict[str, DistribuicaoSemanal] = Field(default_factory=dict)


class EstoqueDelayCanonical(BaseModel):
    """ADR-128 F5: causa de atraso por recurso consumível (diesel/material) — espelho
    canônico de ``EstoqueDelayCause`` (application/scheduling/models.py)."""

    model_config = ConfigDict(extra="ignore")

    resource_id: str
    activity_id: str
    delay_weeks: int


class ScheduleCandidateCanonical(BaseModel):
    """Candidato de cronograma semanal gerado por uma heurística (v1 — deprecated)."""

    model_config = ConfigDict(extra="ignore")

    heuristic: str
    scheduled_activities: list[ScheduledActivityCanonical] = Field(default_factory=list)
    makespan: int
    quality_score: float
    metrics: dict[str, float] = Field(default_factory=dict)
    relaxed: bool = False
    # ADR-128 F5: vazio quando nenhum ReplenishableResource foi passado ao scheduler.
    estoque_delays: list[EstoqueDelayCanonical] = Field(default_factory=list)


class Cronograma(BaseModel):
    """Cronograma unificado (semanal com agregação mensal).

    Single source of truth para o schedule do projeto (semanal + agregação mensal).
    """

    model_config = ConfigDict(extra="ignore")

    # Scheduling metadata (from AUTO optimization or MANUAL_ALLOCATION)
    algorithm: Literal["manual_allocation", "MINSLK", "LPT", "MAXRES", "ES", "GR", "MILP", "CP-SAT", "LNS"] = (
        "manual_allocation"
    )
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    makespan_weeks: int = Field(default=1, ge=1)
    is_feasible: bool = True
    was_relaxed: bool = False

    # Scheduled activities with weekly detail
    scheduled_activities: list[ScheduledActivityCanonical] = Field(default_factory=list)

    # Monthly aggregation (for reporting, backward compatibility)
    # Chave: "2026-03" -> {qtd_total, pct, atividades: [activity_ids]}
    distribuicao_mensal: dict[str, dict] = Field(default_factory=dict)

    # Legacy field (retrocompat if needed)
    pct_completude: float = Field(default=1.0, ge=0.0, le=1.0)

    # ADR-128 F5: causas de atraso por recurso consumível (diesel/material) do candidato
    # selecionado. Vazio quando nenhum ReplenishableResource foi construído para o projeto.
    estoque_delays: list[EstoqueDelayCanonical] = Field(default_factory=list)


def _migrate_cron_item_to_dict(item) -> dict | None:
    if isinstance(item, dict):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return None


def _extract_weeks_from_dist(dist_semanal: dict) -> list:
    weeks = []
    for k in dist_semanal:
        if "-W" in str(k):
            try:
                weeks.append(int(str(k).split("-W")[1]))
            except (ValueError, IndexError):
                pass
    return weeks


def _migrate_cron_list_to_cronograma(cron: list) -> dict:
    scheduled = []
    for item in cron:
        item_data = _migrate_cron_item_to_dict(item)
        if item_data is None:
            continue
        item_id = item_data.get("item_id", "")
        dist_semanal = item_data.get("distribuicao_semanal") or {}
        if not dist_semanal:
            dist_semanal = item_data.get("distribuicao_mensal") or {}
        weeks = _extract_weeks_from_dist(dist_semanal)
        start = min(weeks) if weeks else 1
        end = max(weeks) if weeks else 1
        scheduled.append(
            {
                "activity_id": item_id,
                "start_week": start,
                "end_week": end,
                "duration_weeks": max(end - start + 1, 1),
                "distribuicao_semanal": dist_semanal,
            }
        )
    return {"algorithm": "manual_allocation", "scheduled_activities": scheduled}
