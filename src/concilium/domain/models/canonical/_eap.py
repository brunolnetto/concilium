"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from concilium.domain.models.planning.mobilizacao import WorkforcePolicy

if TYPE_CHECKING:
    from ._indiretos_insumos import ScheduledActivityCanonical


class PrecedenciaItem(BaseModel):
    """NEP-031 L4: relação de precedência tipada entre itens da EAP (§4 do enunciado).

    Tipos suportados:
      FS (Finish-to-Start, default): B começa após A terminar + lag semanas.
      SS (Start-to-Start):           B começa lag semanas após A iniciar.
      FF (Finish-to-Finish):         B termina lag semanas após A terminar (parcial).

    ADR-081: ``completion_threshold_pct`` (θ ∈ [0,1]) define a fração do quantitativo
    do predecessor concluída antes do sucessor poder iniciar (apenas FS).
    θ=1.0 (default) → FS clássico 100%.  θ=0.20 → B pode iniciar quando A está 20% feita.
    Fórmula: start_B ≥ start_A + ceil(θ × duration_A) + lag
    """

    model_config = ConfigDict(extra="ignore")

    item_id: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = Field(default=0, ge=0, description="Lag em semanas")
    # ADR-081: completion threshold ∈ [0,1]. 1.0 = FS clássico (default sem quebra retroativa).
    completion_threshold_pct: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fração do quantitativo do predecessor concluída antes do início do "
            "sucessor (apenas FS). θ=1.0 = FS estrito; θ=0.0 = equivale a SS."
        ),
    )


class EapItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_id: str
    ordem: int | None = Field(default=None, ge=1)  # Opcional — inferido do catálogo se não fornecido
    cpu_id: str
    descricao: str | None = None  # Opcional — inferido do catálogo se não fornecido
    unidade: str | None = None  # Opcional — inferido do catálogo se não fornecido
    quantitativo: float = Field(gt=0)
    # NEP-031 L4: predecessores com tipo de relação (FS/SS/FF) e lag.
    # Aceita str (legado, tratado como FS lag=0) ou PrecedenciaItem.
    predecessores: list[str | PrecedenciaItem] = Field(default_factory=list)
    # ADR-106 F5: override explícito de janela de mob/desmob (semanas), por item de EAP.
    # None = sem override (backward compat — nenhum custo de janela adicionado).
    leadtime_mob_semanas: int | None = Field(default=None, ge=0)
    lag_demob_semanas: int | None = Field(default=None, ge=0)
    # ADR-181 F1: prazo de aquisição/contratação (decisão de contratar → recurso
    # contratualmente disponível), ANTERIOR à mobilização física (leadtime_mob_semanas).
    # Sem custo direto associado (fornecedor normalmente não cobra standby nesse
    # período) — afeta só earliest_start no RCPSP, nunca custo. None = sem constraint
    # (backward compat).
    leadtime_aquisicao_semanas: int | None = Field(default=None, ge=0)

    def predecessores_tipados(self) -> list[PrecedenciaItem]:
        """Normaliza predecessores para PrecedenciaItem (converte str legados)."""
        result = []
        for p in self.predecessores:
            if isinstance(p, str):
                result.append(PrecedenciaItem(item_id=p, tipo="FS", lag=0))
            else:
                result.append(p)
        return result


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
    # ADR-054 §7.2: optional embedded mobilization policy.
    # When present, takes precedence over the project-level override file
    # (mobilizacao_policy_override.json). Enables per-Atividade policy embedded
    # in the canonical — useful for scenario branching and full auditability.
    mobilizacao_policy: WorkforcePolicy | None = None
    # ADR-106 F5: propagado de EapItem.leadtime_mob_semanas/lag_demob_semanas (skill 01).
    leadtime_mob_semanas: int | None = None
    lag_demob_semanas: int | None = None
    # ADR-181 F1: propagado de EapItem.leadtime_aquisicao_semanas (skill 01).
    leadtime_aquisicao_semanas: int | None = None


class ArestaActivityDag(BaseModel):
    """NEP-031 L4: aresta do DAG com tipo de relação, lag e threshold de conclusão.

    ADR-081: ``completion_threshold_pct`` (θ) tem a mesma semântica de PrecedenciaItem.
    """

    model_config = ConfigDict(extra="ignore")

    de: str
    para: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = Field(default=0, ge=0)
    # ADR-081: idêntico a PrecedenciaItem.completion_threshold_pct
    completion_threshold_pct: float = Field(default=1.0, ge=0.0, le=1.0)


class ActivityDag(BaseModel):
    model_config = ConfigDict(extra="ignore")

    nos: list[str]
    arestas: list[ArestaActivityDag]
    ordem_topologica: list[str]
    critical_path: list[str] | None = None
    start_offset_min: dict[str, int] | None = None


OrigemCapacidade = Literal[
    "GRAFO_FLUXO",
    "GRAFO_ELEMENTOS",
    "TAXA_POR_FRENTE_ASSUMIDA",
    "FALLBACK_ARBITRARIO",
    "NAO_DECLARADA",
]


class DistribuicaoSemanal(BaseModel):
    """Weekly materialization of effective physical capacity F_i(m_ij)*H_i.

    q_max_celula = B_nom = F_i(m_ij)*H_i for actually mobilized fronts.
    eta_p = climate * calendar * working-day availability.
    qtd_executada = min(Q_remaining, q_max_celula * eta_p).
    The final-week closure ratio phi = qtd_executada/(q_max_celula*eta_p)
    is NOT a productivity loss, and unmobilized fronts generate NO physical
    loss. perda_fisica measures only lost exogenous productive capacity
    q_max_celula*(1-eta_p), not missing front teams or scope closure.

    Transitional persisted fields: eta_s=eta_w=eficiencia=1.0 neutral,
    while fracao_fechamento stores the exact physical closure independently.
    Dependent control analytics need versioned migration (#11/#26).
    """

    model_config = ConfigDict(extra="ignore")

    num_equipes: int = Field(ge=0)
    qtd_executada: float = Field(ge=0)
    qtd_acumulada: float = Field(ge=0)
    pct: float = Field(ge=0, le=1)
    # Legacy control multiplier, neutral for an unobserved planned schedule
    eficiencia: float = Field(default=1.0, ge=0.0, le=1.0)
    # ADR-068: separacao explícita entre clima e calendario operacional.
    fator_clima: float = Field(default=1.0, ge=0.0, le=1.0)
    fator_calendario: float = Field(default=1.0, ge=0.0, le=1.0)
    # ADR-148: eta_jornada = (horas_dia - horas_improdutivas_dia) / horas_dia — determinístico,
    # estrutural (não estocástico como fator_clima; não calendarizado como fator_calendario).
    fator_jornada: float = Field(default=1.0, ge=0.0, le=1.0)
    fator_total: float = Field(default=1.0, ge=0.0, le=1.0)
    # Legacy compatibility field, permanently neutral in new schedules.
    eta_s: float = Field(default=1.0, ge=0.0, le=1.0)
    # PLANEJAMENTO: η_p = fator_clima · fator_calendario = η_clima · δ = η_plan (ADR-124).
    eta_p: float = Field(default=1.0, ge=0.0, le=1.0)
    # Legacy control multiplier: neutral until actual measured loss is available.
    eta_w: float = Field(default=1.0, ge=0.0, le=1.0)
    # Real final-week scope fraction, never a productivity loss.
    fracao_fechamento: float = Field(default=1.0, ge=0.0, le=1.0)
    q_max_celula: float = Field(default=0.0, ge=0.0)
    perda_fisica: float = Field(default=0.0, ge=0.0)
    # P10/#23: audit metadata, not alternative productivities or new multipliers.
    # None on older artifacts explicitly means not evaluated, not a zero result.
    origem_produtividade: OrigemCapacidade = "NAO_DECLARADA"
    produtividade_fisica_horaria: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    horas_contratuais_semana: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    capacidade_disponivel_semana: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    desempenho_observado: Literal["NAO_OBSERVADO"] = "NAO_OBSERVADO"
    # Graph-derived capacity is not automatically a certified source/version.
    estado_calibracao: Literal["NAO_CERTIFICADA"] = "NAO_CERTIFICADA"


# Alias retrocompatível
DistribuicaoMensal = DistribuicaoSemanal


class AtividadeIntervalo(BaseModel):
    """Unidade atômica de execução: semana ISO × atividade × composição de equipe.

    Formaliza a atividade como um intervalo particionado por semanas e composto
    por equipes. É a granularidade mínima de planejamento e controle do custo direto.

    Invariante: Σ qtd_planejada de todos os intervalos de uma atividade == quantitativo_atividade.

    Derivado de ScheduledActivityCanonical via `AtividadeIntervalo.from_scheduled_activity()`.
    """

    model_config = ConfigDict(extra="ignore")

    atividade_id: str
    semana_iso: str = Field(
        pattern=r"^\d{4}-W(0[1-9]|[1-4][0-9]|5[0-3])$",
        description="Semana ISO no formato AAAA-Www, ex: 2026-W23",
    )
    num_equipes: int = Field(ge=0)
    qtd_planejada: float = Field(ge=0)
    qtd_acumulada: float = Field(ge=0)
    eficiencia: float = Field(default=1.0, ge=0.0, le=1.0)
    pct_completude: float = Field(default=0.0, ge=0.0, le=1.0)

    @classmethod
    def from_scheduled_activity(cls, sa: "ScheduledActivityCanonical") -> "list[AtividadeIntervalo]":
        """Expande um ScheduledActivityCanonical em lista de AtividadeIntervalo (um por semana)."""
        return [
            cls(
                atividade_id=sa.activity_id,
                semana_iso=semana_iso,
                num_equipes=dist.num_equipes,
                qtd_planejada=dist.qtd_executada,
                qtd_acumulada=dist.qtd_acumulada,
                eficiencia=dist.eficiencia,
                pct_completude=dist.pct,
            )
            for semana_iso, dist in sa.distribuicao_semanal.items()
        ]


class CronogramaItem(BaseModel):
    """Per-item weekly schedule (historical format — use Cronograma for new code)."""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    dias_trabalhados_semana: int
    # Chave: ISO week "AAAA-Www" (ex. "2026-W23")
    distribuicao_semanal: dict[str, DistribuicaoSemanal] = Field(default_factory=dict)
    # Retrocompat: leitura de dados legados com distribuicao_mensal
    distribuicao_mensal: dict[str, DistribuicaoSemanal] = Field(default_factory=dict)
    pct_completude: float = Field(ge=0, le=1)
