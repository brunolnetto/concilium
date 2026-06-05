"""Scoring da camada de resolução — ADR-002.

Features:
    semantic_similarity — jaccard sobre tokens normalizados (embedding opcional)
    attribute_match     — compatibilidade de atributos canônicos
    context_fit         — compatibilidade de contexto de execução
    historical_prior    — frequência histórica (com anti-self-reinforcement cap)

Invariante: embedding weight nunca ultrapassa ScoringConfig.max_embedding_weight (0.4).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from concilium.application.resolution.models import (
    CPUCanonical,
    ResolutionDecision,
    ScoredCandidate,
    ScoringConfig,
)
from concilium.application.resolution.registry import ATTRIBUTE_REGISTRY
from concilium.application.semantic.intent import SemanticIntent

if TYPE_CHECKING:
    pass

_RE_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Tokeniza texto para Jaccard: lowercase, alphanumeric only."""
    return set(_RE_TOKEN.findall(text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Coeficiente de Jaccard entre dois conjuntos de tokens."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _am_collect_unique_attrs(required: object, optional: object) -> list:
    """Returns deduplicated list of required+optional attribute names."""
    seen: set = set()
    result: list = []
    for a in list(required) + list(optional):
        if a not in seen:
            seen.add(a)
            result.append(a)
    return result


def _am_build_intent_dims(intent: object) -> dict:
    """Builds flat {attr_name: value} dict from intent dimensions + context."""
    dims = {d.name: d.value for d in intent.dimensions}
    dims.update({k: v for k, v in intent.context.items() if isinstance(v, (int, float, str))})
    return dims


def _am_score_numeric(cpu_f: float, intent_f: float, tol: float) -> float:
    """Numeric attribute compatibility score within tolerance band."""
    if cpu_f == 0.0:
        return 1.0 if intent_f == 0.0 else 0.0
    diff_pct = abs(cpu_f - intent_f) / abs(cpu_f)
    if diff_pct <= tol:
        return 1.0
    if diff_pct <= tol * 2:
        return 0.5
    return 0.0


def _am_score_attr_value(attr: str, cpu_val: object, intent_val: object) -> float:
    """Returns compatibility score [0.0-1.0] for a single attribute pair."""
    attr_def = ATTRIBUTE_REGISTRY.get(attr)
    tol = attr_def.tolerance_pct if attr_def else 0.0
    if isinstance(cpu_val, (int, float)) and isinstance(intent_val, (int, float)):
        return _am_score_numeric(float(cpu_val), float(intent_val), tol)
    if isinstance(cpu_val, str) and isinstance(intent_val, str):
        return 1.0 if cpu_val.upper() == str(intent_val).upper() else 0.0
    return 0.0


class FeatureExtractor:
    """Extrai features estruturadas para scoring.

    Embeddings = ferramenta de recall, nunca de decisão (ADR-002).
    """

    def semantic_similarity(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> float:
        """Similaridade semântica entre intent.activity_type e cpu.activity_type.

        Usa Jaccard sobre tokens normalizados.
        Peso máximo: 0.4 (ADR hard cap — enforçado no WeightedScorer).
        """
        tokens_intent = _tokenize(intent.activity_type)
        tokens_cpu = _tokenize(cpu.activity_type)

        # Match exato = 1.0
        if intent.activity_type == cpu.activity_type:
            return 1.0

        return _jaccard(tokens_intent, tokens_cpu)

    def attribute_match(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> float:
        """Score de compatibilidade de atributos.

        Lógica:
        - atributo presente em cpu.optional_attributes:
            - presente no intent dentro da tolerância -> +1.0 por atributo
            - presente mas fora da tolerância -> +0.2
            - ausente no intent -> 0.0 (não penalidade)
        - cpu.attributes[attr] == None -> atributo ausente na CPU -> ignorar
        - Score final: média sobre optional_attributes (ou 0.5 se nenhum)
        """
        attrs_to_score = _am_collect_unique_attrs(cpu.required_attributes, cpu.optional_attributes)
        if not attrs_to_score:
            return 0.5
        scores: list[float] = []
        intent_dims = _am_build_intent_dims(intent)
        for attr in attrs_to_score:
            cpu_val = cpu.attributes.get(attr)
            intent_val = intent_dims.get(attr)
            if cpu_val is None:
                continue
            if intent_val is None:
                continue
            scores.append(_am_score_attr_value(attr, cpu_val, intent_val))
        return sum(scores) / len(scores) if scores else 0.5

    def context_fit(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
    ) -> float:
        """Compatibilidade de contexto de execução.

        Lógica básica: método mecanizado -> preferir CPUs com equipamentos.
        Sem contexto -> retorna 0.5 (neutro).
        """
        if not intent.context:
            return 0.5

        score = 0.5
        method = intent.context.get("method") or intent.method

        if method == "manual":
            # CPUs com equipamentos pesados não são ótimas para execução manual
            if cpu.activity_type in ("cut_fill",):
                score = 0.3
        elif method == "mechanized":
            if cpu.activity_type in ("cut_fill", "embankment_compaction"):
                score = 0.8

        return min(1.0, max(0.0, score))

    def historical_prior(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
        history: list[ResolutionDecision],
    ) -> float:
        """Frequência histórica de seleção desta CPU para activity_types similares.

        Anti-self-reinforcement: cap em 0.8 mesmo com dominância histórica total.
        """
        if not history:
            return 0.5

        relevant = [d for d in history if d.intent_snapshot.activity_type == intent.activity_type]
        if not relevant:
            return 0.5

        count_this = sum(1 for d in relevant if d.selected_cpu_id == cpu.cpu_id)
        raw_rate = count_this / len(relevant)

        # Cap anti-self-reinforcement: nunca mais de 0.8
        return min(0.80, raw_rate)


class WeightedScorer:
    """Aplica pesos configuráveis às features.

    Pesos vêm de ScoringConfig (versionado).
    Embedding nunca ultrapassa weight <= max_embedding_weight.
    """

    def score(
        self,
        intent: SemanticIntent,
        cpu: CPUCanonical,
        config: ScoringConfig,
        history: list[ResolutionDecision] | None = None,
        extractor: FeatureExtractor | None = None,
    ) -> ScoredCandidate:
        """Calcula score total com breakdown por feature.

        Returns:
            ScoredCandidate com score e explanations estruturadas.
        """
        fx = extractor or FeatureExtractor()
        weights = config.weights

        features = {
            "semantic_similarity": fx.semantic_similarity(intent, cpu),
            "attribute_match": fx.attribute_match(intent, cpu),
            "context_fit": fx.context_fit(intent, cpu),
        }

        if config.feature_flags.get("use_historical_priors") and history:
            features["historical_prior"] = fx.historical_prior(intent, cpu, history)
        else:
            features["historical_prior"] = 0.5  # neutro

        # Enforça cap de embedding (ADR-002)
        sem_weight = min(
            weights.get("semantic_similarity", 0.35),
            config.max_embedding_weight,
        )
        effective_weights = {**weights, "semantic_similarity": sem_weight}

        total_weight = sum(effective_weights.get(k, 0.0) for k in features)
        total_score = 0.0
        explanations = []

        for feat_name, feat_value in features.items():
            w = effective_weights.get(feat_name, 0.0)
            contribution = feat_value * w
            total_score += contribution
            explanations.append(
                {
                    "feature": feat_name,
                    "value": round(feat_value, 4),
                    "weight": round(w, 4),
                    "contribution": round(contribution, 4),
                }
            )

        # Normalizar se pesos não somam 1.0
        if total_weight > 0 and abs(total_weight - 1.0) > 0.01:
            total_score = total_score / total_weight

        return ScoredCandidate(
            cpu_id=cpu.cpu_id,
            score=round(min(1.0, max(0.0, total_score)), 4),
            explanations=explanations,
        )

    def score_all(
        self,
        intent: SemanticIntent,
        candidates: list[CPUCanonical],
        config: ScoringConfig,
        history: list[ResolutionDecision] | None = None,
    ) -> list[ScoredCandidate]:
        """Pontua todos os candidatos e ordena por score desc."""
        fx = FeatureExtractor()
        scored = [self.score(intent, cpu, config, history, extractor=fx) for cpu in candidates]
        return sorted(scored, key=lambda s: s.score, reverse=True)


__all__ = ["FeatureExtractor", "WeightedScorer", "ScoredCandidate"]
