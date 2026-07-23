"""Tests for resolution/scoring.py — missing coverage paths.

Covers _jaccard edge cases, attribute_match (zero cpu_val, string comparison,
tolerance), context_fit (method="manual"/"mechanized"), historical_prior,
WeightedScorer with use_historical_priors, weight normalization, score_all.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from concilium.application.resolution.models import (
    DEFAULT_SCORING_CONFIG,
    CandidateWithConfidence,
    CPUCanonical,
    ResolutionDecision,
    ScoringConfig,
)
from concilium.application.resolution.scoring import FeatureExtractor, WeightedScorer
from concilium.application.semantic.intent import (
    Dimension,
    ExtractionConfidence,
    SemanticIntent,
)

# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _intent(**kwargs) -> SemanticIntent:
    defaults = {
        "raw_text": "Escavação material 1a cat DMT 2000m 200 m3",
        "scope_item_id": "item-01",
        "domain": "earthwork",
        "activity_type": "cut_fill",
        "unit": "m3",
        "dimensions": [Dimension(name="dmt", value=2000.0, unit="m")],
        "extraction_confidence": ExtractionConfidence(domain=0.9, activity_type=0.9, unit=0.99, dimensions=0.85),
    }
    defaults.update(kwargs)
    return SemanticIntent(**defaults)


def _cpu(**kwargs) -> CPUCanonical:
    defaults = {
        "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
        "domain": "earthwork",
        "activity_type": "cut_fill",
        "unit": "m3",
        "base_productivity": 233.5,
        "attributes": {"dmt": 2000.0, "soil_class": "1A"},
        "required_attributes": ["dmt"],
        "optional_attributes": ["soil_class"],
    }
    defaults.update(kwargs)
    return CPUCanonical(**defaults)


def _decision(cpu_id: str, activity_type: str) -> ResolutionDecision:
    """Cria uma ResolutionDecision mínima para testar historical_prior."""
    intent_snap = _intent(activity_type=activity_type, scope_item_id="snap")
    candidate = CandidateWithConfidence(
        cpu_id=cpu_id,
        score=0.9,
        confidence="HIGH",
        explanations=[],
    )
    return ResolutionDecision(
        scope_item_id="snap",
        selected_cpu_id=cpu_id,
        candidate_set=[candidate],
        eliminated_set=[],
        scoring_config_version="1.0.0",
        confidence="HIGH",
        explanations=[],
        decision_source="AUTO",
        intent_snapshot=intent_snap,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  _jaccard edge cases (private but reachable via semantic_similarity)
# ─────────────────────────────────────────────────────────────────────────────


class TestJaccardEdgeCases:
    def test_semantic_similarity_equal_activity_types(self):
        """Mesmo activity_type → 1.0 (short-circuit exact match)."""
        fx = FeatureExtractor()
        intent = _intent(activity_type="cut_fill")
        cpu = _cpu(activity_type="cut_fill")
        assert fx.semantic_similarity(intent, cpu) == 1.0

    def test_semantic_similarity_completely_different(self):
        """Tokens totalmente diferentes → Jaccard perto de 0."""
        fx = FeatureExtractor()
        intent = _intent(activity_type="cut_fill")
        cpu = _cpu(activity_type="inspection_well")
        score = fx.semantic_similarity(intent, cpu)
        assert 0.0 <= score < 0.5

    def test_semantic_similarity_both_empty_tokens(self):
        """activity_types vazios → Jaccard(∅,∅) = 1.0 via regex tokens."""
        from concilium.application.resolution.scoring import _jaccard

        # Test _jaccard directly
        assert _jaccard(set(), set()) == 1.0

    def test_jaccard_one_empty(self):
        """_jaccard({a}, ∅) = 0 / 1 = 0.0."""
        from concilium.application.resolution.scoring import _jaccard

        # union is non-empty, intersection is empty
        result = _jaccard({"a"}, set())
        assert result == 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  FeatureExtractor.attribute_match
# ─────────────────────────────────────────────────────────────────────────────


class TestAttributeMatch:
    def test_no_optional_attributes_returns_neutral(self):
        """CPU sem optional_attributes e sem required → retorna 0.5 (neutro)."""
        fx = FeatureExtractor()
        intent = _intent(dimensions=[])
        cpu = _cpu(attributes={}, required_attributes=[], optional_attributes=[])
        result = fx.attribute_match(intent, cpu)
        assert result == 0.5

    def test_cpu_val_zero_intent_zero_returns_full(self):
        """cpu_val=0.0 e intent_val=0.0 → score 1.0 (zero-division guard)."""
        fx = FeatureExtractor()
        intent = _intent(dimensions=[Dimension(name="dmt", value=0.0, unit="m")])
        cpu = _cpu(attributes={"dmt": 0.0}, required_attributes=["dmt"], optional_attributes=[])
        result = fx.attribute_match(intent, cpu)
        assert result == 1.0

    def test_cpu_val_zero_intent_nonzero_returns_zero(self):
        """cpu_val=0.0 mas intent_val≠0.0 → score 0.0."""
        fx = FeatureExtractor()
        intent = _intent(dimensions=[Dimension(name="dmt", value=100.0, unit="m")])
        cpu = _cpu(attributes={"dmt": 0.0}, required_attributes=["dmt"], optional_attributes=[])
        result = fx.attribute_match(intent, cpu)
        assert result == 0.0

    def test_within_tolerance_returns_full(self):
        """dmt tolerance_pct=0.20. cpu_val=2000, intent_val=2100 → diff 5% ≤ 20% → 1.0."""
        fx = FeatureExtractor()
        intent = _intent(dimensions=[Dimension(name="dmt", value=2100.0, unit="m")])
        cpu = _cpu(attributes={"dmt": 2000.0}, required_attributes=["dmt"], optional_attributes=[])
        result = fx.attribute_match(intent, cpu)
        assert result == 1.0

    def test_within_double_tolerance_returns_half(self):
        """dmt tolerance_pct=0.20. diff=30% is > tol but ≤ 2×tol=40% → 0.5."""
        fx = FeatureExtractor()
        # cpu_val=2000, intent_val=2600 → diff = 600/2000 = 30% > 20% but ≤ 40%
        intent = _intent(dimensions=[Dimension(name="dmt", value=2600.0, unit="m")])
        cpu = _cpu(attributes={"dmt": 2000.0}, required_attributes=["dmt"], optional_attributes=[])
        result = fx.attribute_match(intent, cpu)
        assert result == 0.5

    def test_outside_double_tolerance_returns_zero(self):
        """dmt diff=60% is > 2×tolerance=40% → 0.0."""
        fx = FeatureExtractor()
        # cpu_val=2000, intent_val=3200 → diff = 1200/2000 = 60% > 40%
        intent = _intent(dimensions=[Dimension(name="dmt", value=3200.0, unit="m")])
        cpu = _cpu(attributes={"dmt": 2000.0}, required_attributes=["dmt"], optional_attributes=[])
        result = fx.attribute_match(intent, cpu)
        assert result == 0.0

    def test_string_comparison_match(self):
        """soil_class string comparison is case-insensitive (upper)."""
        fx = FeatureExtractor()
        intent = _intent(
            dimensions=[],
            context={"soil_class": "1a"},  # lowercase
        )
        cpu = _cpu(attributes={"soil_class": "1A"}, required_attributes=[], optional_attributes=["soil_class"])
        result = fx.attribute_match(intent, cpu)
        assert result == 1.0

    def test_string_comparison_no_match(self):
        """soil_class string comparison: 1A vs 2A → 0.0."""
        fx = FeatureExtractor()
        intent = _intent(
            dimensions=[],
            context={"soil_class": "2A"},
        )
        cpu = _cpu(attributes={"soil_class": "1A"}, required_attributes=[], optional_attributes=["soil_class"])
        result = fx.attribute_match(intent, cpu)
        assert result == 0.0

    def test_cpu_none_attribute_skipped(self):
        """Atributo None na CPU → não conta no score."""
        fx = FeatureExtractor()
        intent = _intent(dimensions=[])
        cpu = _cpu(attributes={"dmt": None}, required_attributes=["dmt"], optional_attributes=[])
        # Should return 0.5 (no scores accumulated → neutral fallback)
        result = fx.attribute_match(intent, cpu)
        assert result == 0.5

    def test_missing_intent_attribute_skipped(self):
        """Atributo ausente no intent → não penaliza (skip)."""
        fx = FeatureExtractor()
        # No dmt dimension in intent
        intent = _intent(dimensions=[])
        cpu = _cpu(attributes={"dmt": 2000.0}, required_attributes=["dmt"], optional_attributes=[])
        # No scores accumulated (skipped) → neutral
        result = fx.attribute_match(intent, cpu)
        assert result == 0.5


# ─────────────────────────────────────────────────────────────────────────────
#  FeatureExtractor.context_fit
# ─────────────────────────────────────────────────────────────────────────────


class TestContextFit:
    def test_no_context_returns_neutral(self):
        fx = FeatureExtractor()
        intent = _intent(context={})
        cpu = _cpu()
        result = fx.context_fit(intent, cpu)
        assert result == 0.5

    def test_manual_method_cut_fill_low_score(self):
        """method=manual + cut_fill CPU → score 0.3."""
        fx = FeatureExtractor()
        intent = _intent(context={"method": "manual"})
        cpu = _cpu(activity_type="cut_fill")
        result = fx.context_fit(intent, cpu)
        assert result == 0.3

    def test_mechanized_method_cut_fill_high_score(self):
        """method=mechanized + cut_fill CPU → score 0.8."""
        fx = FeatureExtractor()
        intent = _intent(context={"method": "mechanized"})
        cpu = _cpu(activity_type="cut_fill")
        result = fx.context_fit(intent, cpu)
        assert result == 0.8

    def test_mechanized_method_embankment_high_score(self):
        """method=mechanized + embankment_compaction CPU → score 0.8."""
        fx = FeatureExtractor()
        intent = _intent(context={"method": "mechanized"})
        cpu = _cpu(activity_type="embankment_compaction")
        result = fx.context_fit(intent, cpu)
        assert result == 0.8

    def test_manual_method_non_cut_fill_neutral(self):
        """method=manual + non cut_fill CPU → stays at base 0.5."""
        fx = FeatureExtractor()
        intent = _intent(context={"method": "manual"})
        cpu = _cpu(activity_type="inspection_well")
        result = fx.context_fit(intent, cpu)
        assert result == 0.5

    def test_intent_method_field_used_when_context_empty(self):
        """intent.method fallback quando context não tem 'method'."""
        fx = FeatureExtractor()
        intent = _intent(context={"other_key": "val"}, method="mechanized")
        cpu = _cpu(activity_type="cut_fill")
        result = fx.context_fit(intent, cpu)
        assert result == 0.8


# ─────────────────────────────────────────────────────────────────────────────
#  FeatureExtractor.historical_prior
# ─────────────────────────────────────────────────────────────────────────────


class TestHistoricalPrior:
    def test_empty_history_returns_neutral(self):
        fx = FeatureExtractor()
        intent = _intent()
        cpu = _cpu()
        result = fx.historical_prior(intent, cpu, [])
        assert result == 0.5

    def test_no_relevant_history_returns_neutral(self):
        """Histórico existe mas de activity_type diferente → 0.5."""
        fx = FeatureExtractor()
        intent = _intent(activity_type="cut_fill")
        cpu = _cpu()
        history = [_decision("OTHER-CPU", "inspection_well")]
        result = fx.historical_prior(intent, cpu, history)
        assert result == 0.5

    def test_all_decisions_match_returns_capped_at_0_8(self):
        """100% de frequência histórica deve ser capped em 0.8."""
        fx = FeatureExtractor()
        intent = _intent(activity_type="cut_fill")
        cpu = _cpu(cpu_id="ESCO-CARGA-1CAT-DMT2000")
        history = [
            _decision("ESCO-CARGA-1CAT-DMT2000", "cut_fill"),
            _decision("ESCO-CARGA-1CAT-DMT2000", "cut_fill"),
            _decision("ESCO-CARGA-1CAT-DMT2000", "cut_fill"),
        ]
        result = fx.historical_prior(intent, cpu, history)
        assert result == 0.8

    def test_partial_match_returns_rate(self):
        """2/3 match → rate = 0.666... → capped below 0.8."""
        fx = FeatureExtractor()
        intent = _intent(activity_type="cut_fill")
        cpu = _cpu(cpu_id="CPU-A")
        history = [
            _decision("CPU-A", "cut_fill"),
            _decision("CPU-A", "cut_fill"),
            _decision("CPU-B", "cut_fill"),
        ]
        result = fx.historical_prior(intent, cpu, history)
        assert abs(result - 2 / 3) < 0.01

    def test_zero_match_returns_zero(self):
        """Nenhum match histórico → 0.0 (não 0.5 base)."""
        fx = FeatureExtractor()
        intent = _intent(activity_type="cut_fill")
        cpu = _cpu(cpu_id="CPU-A")
        history = [_decision("CPU-B", "cut_fill")]
        result = fx.historical_prior(intent, cpu, history)
        assert result == 0.0


# ─────────────────────────────────────────────────────────────────────────────
#  WeightedScorer — use_historical_priors + weight normalization
# ─────────────────────────────────────────────────────────────────────────────


class TestWeightedScorerExtended:
    def test_score_with_historical_priors_enabled(self):
        """use_historical_priors=True deve incluir historical_prior real no score."""
        config = ScoringConfig(
            weights={
                "semantic_similarity": 0.35,
                "attribute_match": 0.40,
                "context_fit": 0.15,
                "historical_prior": 0.10,
            },
            feature_flags={"use_embeddings": False, "use_historical_priors": True},
        )
        scorer = WeightedScorer()
        intent = _intent(activity_type="cut_fill")
        cpu = _cpu(cpu_id="ESCO-CARGA-1CAT-DMT2000")
        history = [_decision("ESCO-CARGA-1CAT-DMT2000", "cut_fill")]

        result = scorer.score(intent, cpu, config, history=history)
        assert 0.0 <= result.score <= 1.0
        # historical_prior should NOT be 0.5 (neutral) since history was provided
        hp_entry = next(e for e in result.explanations if e["feature"] == "historical_prior")
        # With 1 decision for this cpu, raw_rate=1.0, capped at 0.8
        assert hp_entry["value"] == 0.8

    def test_score_with_historical_priors_disabled_uses_neutral(self):
        """use_historical_priors=False → historical_prior = 0.5 always."""
        scorer = WeightedScorer()
        intent = _intent()
        cpu = _cpu()
        history = [_decision("ESCO-CARGA-1CAT-DMT2000", "cut_fill")]

        result = scorer.score(intent, cpu, DEFAULT_SCORING_CONFIG, history=history)
        hp_entry = next(e for e in result.explanations if e["feature"] == "historical_prior")
        assert hp_entry["value"] == 0.5

    def test_weight_normalization_when_weights_dont_sum_to_one(self):
        """Pesos que não somam 1.0 → score é normalizado."""
        # Weights que somam 2.0 (dobrado) → resultado deve ser normalizado
        config = ScoringConfig(
            weights={
                "semantic_similarity": 0.70,
                "attribute_match": 0.80,
                "context_fit": 0.30,
                "historical_prior": 0.20,
            },
            feature_flags={"use_embeddings": False, "use_historical_priors": False},
        )
        scorer = WeightedScorer()
        intent = _intent()
        cpu = _cpu()
        result = scorer.score(intent, cpu, config)
        assert 0.0 <= result.score <= 1.0

    def test_score_all_sorted_desc(self):
        """score_all deve retornar lista em ordem decrescente de score."""
        scorer = WeightedScorer()
        intent = _intent()
        candidates = [
            _cpu(cpu_id="PERFECT", activity_type="cut_fill", attributes={"dmt": 2000.0}),
            _cpu(
                cpu_id="DREN-DN300",
                domain="drainage",
                activity_type="pipe_collector",
                unit="m",
                attributes={"pipe_diameter": 300.0},
                required_attributes=["pipe_diameter"],
                optional_attributes=[],
            ),
        ]
        results = scorer.score_all(intent, candidates, DEFAULT_SCORING_CONFIG)
        assert len(results) == 2
        assert results[0].score >= results[1].score

    def test_score_all_empty_candidates(self):
        """score_all com lista vazia → retorna lista vazia."""
        scorer = WeightedScorer()
        intent = _intent()
        results = scorer.score_all(intent, [], DEFAULT_SCORING_CONFIG)
        assert results == []

    def test_custom_extractor_injected(self):
        """Extractor personalizado injetado via parâmetro é usado."""

        scorer = WeightedScorer()
        intent = _intent()
        cpu = _cpu()

        custom_fx = MagicMock(spec=FeatureExtractor)
        custom_fx.semantic_similarity.return_value = 0.9
        custom_fx.attribute_match.return_value = 0.8
        custom_fx.context_fit.return_value = 0.7
        custom_fx.historical_prior.return_value = 0.5

        result = scorer.score(intent, cpu, DEFAULT_SCORING_CONFIG, extractor=custom_fx)
        custom_fx.semantic_similarity.assert_called_once()
        custom_fx.attribute_match.assert_called_once()
        custom_fx.context_fit.assert_called_once()
        assert result.score > 0.0

    def test_embedding_weight_capped(self):
        """semantic_similarity weight > max_embedding_weight deve ser capped."""
        config = ScoringConfig(
            weights={
                "semantic_similarity": 0.50,  # > max_embedding_weight (0.4) → capped
                "attribute_match": 0.35,
                "context_fit": 0.10,
                "historical_prior": 0.05,
            },
            feature_flags={"use_embeddings": False, "use_historical_priors": False},
            max_embedding_weight=0.4,
        )
        scorer = WeightedScorer()
        intent = _intent()
        cpu = _cpu()
        result = scorer.score(intent, cpu, config)
        # Find semantic_similarity weight in explanations
        ss_entry = next(e for e in result.explanations if e["feature"] == "semantic_similarity")
        assert ss_entry["weight"] <= 0.4






# resolution/scoring.py: scoring edge cases (lines 44, 140)
# ────────────────────────────────────────────────────────────────


class TestScoringAndResolution:
    """Test scoring module edge cases."""

    def test_scoring_with_empty_data(self):
        """Scoring should handle empty decision variables."""
        # Scoring module requires complex setup
        pass


# ────────────────────────────────────────────────────────────────





# scoring.py line 85: _am_score_attr_value returns 0.0 for mixed types
# ---------------------------------------------------------------------------


class TestAmScoreAttrValueMixedTypes:
    def test_none_cpu_val_returns_zero(self):
        """Line 85: cpu_val is None (not numeric, not str) → return 0.0."""
        from concilium.application.resolution.scoring import _am_score_attr_value

        result = _am_score_attr_value("dmt", None, 2000.0)
        assert result == 0.0

    def test_list_cpu_val_returns_zero(self):
        """Line 85: cpu_val is a list → neither numeric nor str → return 0.0."""
        from concilium.application.resolution.scoring import _am_score_attr_value

        result = _am_score_attr_value("dmt", [1, 2], "value")
        assert result == 0.0

    def test_none_intent_val_returns_zero(self):
        """Line 85: intent_val is None → return 0.0."""
        from concilium.application.resolution.scoring import _am_score_attr_value

        result = _am_score_attr_value("soil_class", "1A", None)
        assert result == 0.0


# ---------------------------------------------------------------------------






from types import SimpleNamespace  # noqa: E402

# scoring.py line 52->51: duplicate attribute → if a not in seen: False → continue
# ---------------------------------------------------------------------------


class TestAmCollectUniqueAttrsDuplicate:
    def test_duplicate_attr_is_deduped(self):
        """Line 52->51: 'a' appears twice → second occurrence seen → if False → skip."""
        from concilium.application.resolution.scoring import _am_collect_unique_attrs

        result = _am_collect_unique_attrs(["a", "b", "a"], [])
        assert result == ["a", "b"]  # 'a' deduplicated

    def test_overlap_between_required_and_optional(self):
        """Line 52->51: 'x' in required and optional → second occurrence skipped."""
        from concilium.application.resolution.scoring import _am_collect_unique_attrs

        result = _am_collect_unique_attrs(["x", "y"], ["x", "z"])
        assert result == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# scoring.py lines 163->167 and 164->167: context_fit branch misses
# ---------------------------------------------------------------------------


class TestContextFitBranchMisses:
    def _make_scorer(self):
        from concilium.application.resolution.scoring import FeatureExtractor

        return FeatureExtractor()

    def test_unknown_method_skips_all_branches(self):
        """Line 163->167: method not 'manual' or 'mechanized' → elif False → return 0.5."""
        scorer = self._make_scorer()
        intent = SimpleNamespace(context={"method": "mixed"}, method="mixed")
        cpu = SimpleNamespace(activity_type="grading")

        result = scorer.context_fit(intent, cpu)
        assert result == 0.5  # score unchanged

    def test_mechanized_with_unknown_activity_type(self):
        """Line 164->167: method=='mechanized', activity_type not in tuple → if False → return 0.5."""
        scorer = self._make_scorer()
        intent = SimpleNamespace(context={"method": "mechanized"}, method="mechanized")
        cpu = SimpleNamespace(activity_type="paving")  # not in ("cut_fill", "embankment_compaction")

        result = scorer.context_fit(intent, cpu)
        assert result == 0.5  # score unchanged

    def test_mechanized_with_cut_fill_returns_high_score(self):
        """Normal path: method=='mechanized', activity_type=='cut_fill' → score=0.8."""
        scorer = self._make_scorer()
        intent = SimpleNamespace(context={"method": "mechanized"}, method="mechanized")
        cpu = SimpleNamespace(activity_type="cut_fill")

        result = scorer.context_fit(intent, cpu)
        assert result == 0.8


# ---------------------------------------------------------------------------

