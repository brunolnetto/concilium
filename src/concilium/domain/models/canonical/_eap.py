"""Camada 4 — Modelo canônico do orçamento (parte extraída de canonical.py)."""

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field

from concilium.domain.models.planning.mobilizacao import MobilizacaoPolicy

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
    mobilizacao_policy: MobilizacaoPolicy | None = None


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


class DistribuicaoSemanal(BaseModel):
    """Distribuição de execução por semana ISO ("AAAA-Www").

    NEP-035 — Decomposição causal da eficiência η = η_s · η_p · η_w:
      η_s  = n_j / n_max          (alocação: fração da força máxima fielded)
      η_p  = fator_clima × fator_calendario  (praticabilidade)
      η_w  = m_ij / M_max = eficiencia      (gestão; M_max=1.0 até calibração histórica)
      η    = fator_total = η_s · η_p · η_w  (eficiência total observada)

    q_max_celula = P_i · h · n_max · M_max  (capacidade teórica da semana)
    perda_fisica = q_max_celula · η_s - q_executada  (produção perdida na semana, unidades físicas)

    Agregação multi-semanal correta (Seção 5 do modelo):
      η_agg = Σ_j(η_j · q_max_celula_j) / Σ_j(q_max_celula_j)  [ponderado por capacidade]
      ≠ produto de médias por fator (os fatores acoplam via pesos de capacidade).
    """

    model_config = ConfigDict(extra="ignore")

    num_equipes: int = Field(ge=0)
    qtd_executada: float = Field(ge=0)
    qtd_acumulada: float = Field(ge=0)
    pct: float = Field(ge=0, le=1)
    # ADR-082-cons: eficiencia = utilização m_ij (≠ praticabilidade; ver fator_total)
    eficiencia: float = Field(default=1.0, ge=0.0, le=1.0)
    # ADR-068: separacao explícita entre clima e calendario operacional.
    fator_clima: float = Field(default=1.0, ge=0.0, le=1.0)
    fator_calendario: float = Field(default=1.0, ge=0.0, le=1.0)
    fator_total: float = Field(default=1.0, ge=0.0, le=1.0)
    # NEP-035: decomposição causal η_s · η_p · η_w
    eta_s: float = Field(default=1.0, ge=0.0, le=1.0)
    eta_p: float = Field(default=1.0, ge=0.0, le=1.0)
    eta_w: float = Field(default=1.0, ge=0.0, le=1.0)
    q_max_celula: float = Field(default=0.0, ge=0.0)
    perda_fisica: float = Field(default=0.0, ge=0.0)


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


