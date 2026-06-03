"""Modelo de confiança — anti-bullshit mechanism (ADR-002).

Alta confiança requer DOIS critérios:
1. Score acima de threshold_high
2. Margem para o segundo candidato acima de delta_min

Sem margem -> MEDIUM, independente do score absoluto.
"0.83 com segundo em 0.82 = MEDIUM" — não é HIGH.
"""

from __future__ import annotations

from concilium.application.resolution.models import (
    CandidateWithConfidence,
    ConfidenceLevel,
    ScoredCandidate,
    ScoringConfig,
)


class ConfidenceAssigner:
    """Atribui nível de confiança com base em score absoluto E margem relativa.

    Regras:
        HIGH:   score[0] > threshold_high  AND  (score[0] - score[1]) > delta_min
        MEDIUM: score[0] > threshold_medium (mas não HIGH)
        LOW:    abaixo de threshold_medium, ou sem candidatos válidos

    Edge cases:
        - Apenas 1 candidato -> MEDIUM (margem não calculável)
        - Top-2 empatados -> MEDIUM
        - Score alto com atributos ausentes -> rebaixar para MEDIUM
          (detectado via feature attribute_match < 0.3 no breakdown)
        - Embedding failure modes -> rebaixar para MEDIUM
    """

    def assign(
        self,
        candidates: list[ScoredCandidate],
        config: ScoringConfig,
    ) -> list[CandidateWithConfidence]:
        """Atribui confiança a cada candidato.

        Args:
            candidates: Ordenados por score desc.
            config:     ScoringConfig com thresholds.

        Returns:
            Lista de CandidateWithConfidence na mesma ordem.
        """
        if not candidates:
            return []

        t_high = config.thresholds.get("threshold_high", 0.75)
        t_med = config.thresholds.get("threshold_medium", 0.50)
        delta_min = config.thresholds.get("delta_min", 0.10)

        result: list[CandidateWithConfidence] = []

        for i, cand in enumerate(candidates):
            confidence = self._compute_confidence(
                cand=cand,
                rank=i,
                all_candidates=candidates,
                t_high=t_high,
                t_med=t_med,
                delta_min=delta_min,
            )
            result.append(
                CandidateWithConfidence(
                    cpu_id=cand.cpu_id,
                    score=cand.score,
                    confidence=confidence,
                    explanations=cand.explanations,
                )
            )

        return result

    def _compute_confidence(
        self,
        cand: ScoredCandidate,
        rank: int,
        all_candidates: list[ScoredCandidate],
        t_high: float,
        t_med: float,
        delta_min: float,
    ) -> ConfidenceLevel:
        score = cand.score

        # Score abaixo de threshold_medium -> LOW sempre
        if score < t_med:
            return "LOW"

        # Verificar falha de embedding (attribute_match baixo apesar de score alto)
        failure_modes = self._detect_embedding_failure_modes(cand, all_candidates)
        if failure_modes:
            return "MEDIUM"

        # Edge case: apenas 1 candidato -> MEDIUM (sem margem calculável)
        if len(all_candidates) == 1:
            return "MEDIUM" if score >= t_med else "LOW"

        # Edge case: não é o top candidato -> MEDIUM ou LOW
        if rank > 0:
            return "MEDIUM" if score >= t_med else "LOW"

        # É o top candidato — checar margem
        second_score = all_candidates[1].score if len(all_candidates) > 1 else 0.0
        margin = score - second_score

        # Alta confiança requer score alto E margem adequada
        if score >= t_high and margin >= delta_min:
            return "HIGH"

        return "MEDIUM"

    def _detect_embedding_failure_modes(
        self,
        cand: ScoredCandidate,
        all_candidates: list[ScoredCandidate],
    ) -> list[str]:
        """Detecta falhas de embedding que devem rebaixar confiança.

        1. Alta similarity (>=0.8), baixo attribute_match (<=0.3) -> likely false positive
        2. Muitos candidatos com similarity alta -> baixo poder discriminativo
        """
        failures: list[str] = []

        explanations_by_feature = {e["feature"]: e for e in cand.explanations}

        sem_sim = explanations_by_feature.get("semantic_similarity", {}).get("value", 0.0)
        attr_match = explanations_by_feature.get("attribute_match", {}).get("value", 1.0)

        # False positive: alta similarity + baixo attribute_match
        if sem_sim >= 0.8 and attr_match <= 0.3:
            failures.append("high_similarity_low_attribute_match")

        # Baixo poder discriminativo: 3+ candidatos com score próximo ao top
        if len(all_candidates) >= 3:
            top_score = all_candidates[0].score
            close = sum(1 for c in all_candidates[1:] if top_score - c.score < 0.05)
            if close >= 2:
                failures.append("low_discriminative_power")

        return failures


__all__ = ["ConfidenceAssigner"]
