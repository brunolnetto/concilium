"""Pacote de resolução de CPU — Camada de Resolução v1.0 (ADR-002)."""

from __future__ import annotations

from concilium.application.resolution.confidence import ConfidenceAssigner
from concilium.application.resolution.constraints import ConstraintFilter, ConstraintResult
from concilium.application.resolution.models import (
    DEFAULT_SCORING_CONFIG,
    BiasReport,
    CalibrationAnalyzer,
    CandidateWithConfidence,
    ConfidenceLevel,
    ConfigSuggestion,
    CPUCanonical,
    DecisionReview,
    EliminationLog,
    ResolutionDecision,
    ResolutionOutput,
    ScoredCandidate,
    ScoringConfig,
)
from concilium.application.resolution.registry import ATTRIBUTE_REGISTRY, AttributeDefinition, resolve_alias
from concilium.application.resolution.resolver import Resolver
from concilium.application.resolution.scoring import FeatureExtractor, WeightedScorer
from concilium.application.resolution.storage import ResolutionDecisionStore

__all__ = [
    # models
    "CPUCanonical",
    "ConfidenceLevel",
    "ScoredCandidate",
    "CandidateWithConfidence",
    "EliminationLog",
    "ScoringConfig",
    "DEFAULT_SCORING_CONFIG",
    "ResolutionOutput",
    "ResolutionDecision",
    "DecisionReview",
    "BiasReport",
    "ConfigSuggestion",
    "CalibrationAnalyzer",
    # registry
    "ATTRIBUTE_REGISTRY",
    "AttributeDefinition",
    "resolve_alias",
    # constraints
    "ConstraintFilter",
    "ConstraintResult",
    # scoring
    "FeatureExtractor",
    "WeightedScorer",
    # confidence
    "ConfidenceAssigner",
    # resolver
    "Resolver",
    # storage
    "ResolutionDecisionStore",
]
