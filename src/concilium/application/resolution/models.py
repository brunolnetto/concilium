"""Modelos da camada de resolução (ADR-002)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, ClassVar, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from concilium.application.semantic.intent import DomainType, SemanticIntent


class CPUCanonical(BaseModel):
    """Representação normalizada de uma CPU para comparação estruturada.

    Gerada pelo CatalogNormalizer na ingestão.
    Armazenada junto ao snapshot do catálogo.
    Nunca normalizada em runtime de resolução.

    Atributos ausentes -> ``None`` explícito no dict ``attributes``.
    Atributo não aplicável à categoria -> ausente no dict.
    """

    model_config = ConfigDict(extra="forbid")

    cpu_id: str  # referência para CPU original no catálogo
    domain: DomainType
    activity_type: str  # vocabulary-mapped
    unit: str  # normalizado (lowercase)
    base_productivity: float  # unidades/hora

    # Atributos canônicos (chaves = ATTRIBUTE_REGISTRY.keys())
    attributes: dict[str, float | str | None] = Field(default_factory=dict)
    # None = ausente explícito. Ausente do dict = não aplicável à categoria.

    required_attributes: list[str] = Field(default_factory=list)
    optional_attributes: list[str] = Field(default_factory=list)


ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW"]


@dataclass
class ScoredCandidate:
    """CPU rankeada com score total e breakdown por feature."""

    cpu_id: str
    score: float
    explanations: list[dict]  # {"feature": str, "value": float, "weight": float, "contribution": float}


@dataclass
class CandidateWithConfidence:
    """ScoredCandidate enriquecido com nível de confiança."""

    cpu_id: str
    score: float
    confidence: ConfidenceLevel
    explanations: list[dict]


@dataclass
class EliminationLog:
    """Registro de por que uma CPU foi eliminada por hard constraint."""

    cpu_id: str
    constraint_name: str
    reason: str


class ScoringConfig(BaseModel):
    """Configuração de scoring. Tratada como modelo versionado (frozen=True).

    Pesos em ``weights`` devem somar 1.0.
    ``max_embedding_weight`` é hard cap (ADR-002): nunca ultrapassa 0.4.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = "1.0.0"

    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "semantic_similarity": 0.35,
            "attribute_match": 0.40,
            "context_fit": 0.15,
            "historical_prior": 0.10,
        }
    )
    thresholds: dict[str, float] = Field(
        default_factory=lambda: {
            "threshold_high": 0.75,
            "threshold_medium": 0.50,
            "delta_min": 0.10,
        }
    )
    feature_flags: dict[str, bool] = Field(
        default_factory=lambda: {
            "use_embeddings": False,
            "use_historical_priors": False,
        }
    )
    # Hard cap: embedding weight nunca pode superar 0.4 (ADR-002)
    max_embedding_weight: float = Field(default=0.4, le=0.4)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    lineage: str | None = None


DEFAULT_SCORING_CONFIG = ScoringConfig()


class ResolutionContext(BaseModel):
    """Contexto de resolução por camada (global -> domain -> project).

    Regra: overrides não podem modificar ``unit_compatibility``
    nem ``structural_constraints``.
    Overrides sem ``expiration`` são um risco futuro de bias.
    """

    model_config = ConfigDict(extra="forbid")

    config_version: str
    override_layer: Literal["GLOBAL", "DOMAIN", "PROJECT"]

    overrides: dict[str, Any] = Field(default_factory=dict)
    justification: str  # obrigatório para qualquer override

    expiration: date | None = None

    FORBIDDEN_OVERRIDE_KEYS: ClassVar[frozenset[str]] = frozenset(
        {
            "unit_compatibility",
            "structural_constraints",
        }
    )

    def model_post_init(self, __context: Any) -> None:
        forbidden = self.FORBIDDEN_OVERRIDE_KEYS & set(self.overrides)
        if forbidden:
            raise ValueError(f"ResolutionContext: overrides proibidos -> {forbidden}")


class ResolutionOutput(BaseModel):
    """Resultado do Resolver.resolve() para um item de escopo.

    ``resolution_status``:
    - ``AUTO_SELECTED``: confiança HIGH -> pode avançar automaticamente
    - ``NEEDS_REVIEW``:  MEDIUM/LOW -> requer validação humana
    - ``NO_VALID_CANDIDATES``: todos eliminados -> falha explícita
    """

    model_config = ConfigDict(extra="forbid")

    scope_item_id: str
    intent: SemanticIntent

    candidates: list[CandidateWithConfidence]  # ordenados por score desc
    eliminated: list[EliminationLog]  # CPUs eliminadas

    resolution_status: Literal["AUTO_SELECTED", "NEEDS_REVIEW", "NO_VALID_CANDIDATES"]
    selected_cpu_id: str | None = None  # None se NEEDS_REVIEW / NO_VALID_CANDIDATES

    ruleset_version: str = "1.0"
    scoring_config_version: str = "1.0.0"


class ResolutionDecision(BaseModel):
    """Decisão de resolução. IMUTÁVEL após criação (frozen=True).

    Regra: nunca atualizar. Somente append de novas decisões.
    Um override humano gera nova ResolutionDecision com
    ``decision_source="USER_OVERRIDE"`` e ``supersedes_decision_id`` preenchido.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    scope_item_id: str

    # O que foi decidido
    selected_cpu_id: str
    candidate_set: list[CandidateWithConfidence]
    eliminated_set: list[EliminationLog]

    # Rastreabilidade de configuração
    scoring_config_version: str
    ruleset_version: str = "1.0"

    # Confiança e explicabilidade
    confidence: ConfidenceLevel
    explanations: list[dict]  # breakdown estruturado obrigatório

    # Fonte da decisão
    decision_source: Literal["AUTO", "USER_OVERRIDE", "REVIEWED"]

    # Snapshot imutável do intent no momento da decisão
    intent_snapshot: SemanticIntent

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Referência a decisão anterior (se USER_OVERRIDE)
    supersedes_decision_id: str | None = None


class DecisionReview(BaseModel):
    """Revisão humana de uma ResolutionDecision.

    Fecha o loop de calibração:
        ResolutionDecision -> Review -> Signals -> new ScoringConfig version.
    """

    model_config = ConfigDict(extra="forbid")

    review_id: str = Field(default_factory=lambda: str(uuid4()))
    decision_id: str

    was_correct: bool
    corrected_cpu_id: str | None = None  # se was_correct=False

    reviewer_confidence: float = Field(ge=0.0, le=1.0)
    notes: str

    # Sinais para calibração
    confidence_mismatch: bool = False  # sistema disse HIGH mas estava errado
    attribute_gap: str | None = None  # qual atributo causou erro de matching

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── BiasReport e CalibrationAnalyzer ─────────────────────────────────────────


@dataclass
class ConfigSuggestion:
    """Sugestão estruturada de ajuste de ScoringConfig."""

    parameter: str
    current_value: Any
    suggested_value: Any
    rationale: str


@dataclass
class BiasReport:
    """Relatório de bias detectado nas reviews."""

    activity_type_error_rates: dict[str, float]  # activity_type -> taxa de erro
    confidence_mismatch_rate: float  # proporção de HIGH incorretos
    frequent_attribute_gaps: list[str]  # atributos que causam erros
    suggestions: list[ConfigSuggestion]
    reviewed_total: int


class CalibrationAnalyzer:
    """Detecta padrões sistemáticos nas reviews para guiar ajuste de ScoringConfig.

    Não ajusta pesos automaticamente — produz relatório para decisão humana.
    """

    ERROR_RATE_THRESHOLD = 0.30  # >30% erro por activity_type = bias sistemático
    MISMATCH_THRESHOLD = 0.20  # >20% HIGH incorreto = threshold muito baixo

    def detect_systematic_bias(self, reviews: list[DecisionReview]) -> BiasReport:
        """Detecta padrões de erro sistemático a partir de reviews.

        Args:
            reviews: Lista de DecisionReview (associadas a decisões com intent).

        Returns:
            BiasReport com taxa de erro, confidence_mismatch e sugestões.
        """
        if not reviews:
            return BiasReport(
                activity_type_error_rates={},
                confidence_mismatch_rate=0.0,
                frequent_attribute_gaps=[],
                suggestions=[],
                reviewed_total=0,
            )

        total = len(reviews)
        wrong, mismatch_rate, gap_counts = _compute_wrong_stats(reviews)
        frequent_gaps = _compute_frequent_gaps(gap_counts, total)
        suggestions = _build_bias_suggestions(mismatch_rate, self.MISMATCH_THRESHOLD, frequent_gaps, gap_counts)

        return BiasReport(
            activity_type_error_rates={},
            confidence_mismatch_rate=mismatch_rate,
            frequent_attribute_gaps=frequent_gaps,
            suggestions=suggestions,
            reviewed_total=total,
        )

    def suggest_config_changes(
        self,
        bias_report: BiasReport,
        current_config: ScoringConfig,
    ) -> list[ConfigSuggestion]:
        """Retorna sugestões de ajuste de ScoringConfig. Humano decide se aplica."""
        return bias_report.suggestions


def _compute_wrong_stats(reviews: list[DecisionReview]) -> tuple[int, float, dict[str, int]]:
    wrong = 0
    mismatch = 0
    total = len(reviews)
    gap_counts: dict[str, int] = {}
    for review in reviews:
        if review.was_correct:
            continue
        wrong += 1
        if review.confidence_mismatch:
            mismatch += 1
        if review.attribute_gap:
            gap_counts[review.attribute_gap] = gap_counts.get(review.attribute_gap, 0) + 1
    mismatch_rate = mismatch / total if total else 0.0
    return wrong, mismatch_rate, gap_counts


def _compute_frequent_gaps(gap_counts: dict[str, int], total: int) -> list[str]:
    if total <= 0:
        return []
    return [gap for gap, count in gap_counts.items() if (count / total) > 0.20]


def _build_bias_suggestions(
    mismatch_rate: float,
    mismatch_threshold: float,
    frequent_gaps: list[str],
    gap_counts: dict[str, int],
) -> list[ConfigSuggestion]:
    suggestions: list[ConfigSuggestion] = []
    if mismatch_rate > mismatch_threshold:
        suggestions.append(
            ConfigSuggestion(
                parameter="thresholds.threshold_high",
                current_value=0.75,
                suggested_value=0.80,
                rationale="Muitos casos HIGH incorretos; aumentar limiar de autoaprovação.",
            )
        )
    for gap in frequent_gaps:
        suggestions.append(
            ConfigSuggestion(
                parameter="weights.attribute_match",
                current_value=0.40,
                suggested_value=0.45,
                rationale=f"Gap frequente em '{gap}' ({gap_counts.get(gap, 0)} ocorrências).",
            )
        )
    return suggestions


__all__ = [
    "CPUCanonical",
    "ConfidenceLevel",
    "ScoredCandidate",
    "CandidateWithConfidence",
    "EliminationLog",
    "ScoringConfig",
    "DEFAULT_SCORING_CONFIG",
    "ResolutionContext",
    "ResolutionOutput",
    "ResolutionDecision",
    "DecisionReview",
    "BiasReport",
    "ConfigSuggestion",
    "CalibrationAnalyzer",
]
