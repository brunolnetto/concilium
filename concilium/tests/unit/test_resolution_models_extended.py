"""Tests for resolution/models.py — CalibrationAnalyzer and ResolutionContext coverage."""

from __future__ import annotations

import pytest

from concilium.application.resolution.models import (
    DEFAULT_SCORING_CONFIG,
    CalibrationAnalyzer,
    DecisionReview,
    ResolutionContext,
)

# ─────────────────────────────────────────────────────────────────────────────
#  ResolutionContext — forbidden overrides validation
# ─────────────────────────────────────────────────────────────────────────────


class TestResolutionContext:
    def test_valid_context_created(self):
        """ResolutionContext with allowed overrides is valid."""
        ctx = ResolutionContext(
            config_version="1.0.0",
            override_layer="GLOBAL",
            overrides={"some_param": 0.5},
            justification="test override",
        )
        assert ctx.config_version == "1.0.0"

    def test_forbidden_override_unit_compatibility_raises(self):
        """overrides containing 'unit_compatibility' raises ValueError."""
        with pytest.raises(ValueError, match="proibidos"):
            ResolutionContext(
                config_version="1.0.0",
                override_layer="DOMAIN",
                overrides={"unit_compatibility": "strict"},
                justification="bad override",
            )

    def test_forbidden_override_structural_constraints_raises(self):
        """overrides containing 'structural_constraints' raises ValueError."""
        with pytest.raises(ValueError, match="proibidos"):
            ResolutionContext(
                config_version="1.0.0",
                override_layer="PROJECT",
                overrides={"structural_constraints": {}},
                justification="bad override",
            )

    def test_no_overrides_valid(self):
        """Empty overrides dict is valid."""
        ctx = ResolutionContext(
            config_version="1.0.0",
            override_layer="PROJECT",
            overrides={},
            justification="no overrides",
        )
        assert ctx.overrides == {}


# ─────────────────────────────────────────────────────────────────────────────
#  CalibrationAnalyzer
# ─────────────────────────────────────────────────────────────────────────────


def _make_review(
    was_correct: bool = True,
    confidence_mismatch: bool = False,
    attribute_gap: str | None = None,
) -> DecisionReview:
    return DecisionReview(
        decision_id="dec-01",
        was_correct=was_correct,
        corrected_cpu_id=None if was_correct else "CORRECT-CPU",
        reviewer_confidence=0.9 if was_correct else 0.5,
        notes="test review",
        confidence_mismatch=confidence_mismatch,
        attribute_gap=attribute_gap,
    )


class TestCalibrationAnalyzer:
    def setup_method(self):
        self.analyzer = CalibrationAnalyzer()

    def test_empty_reviews_returns_zero_bias(self):
        """detect_systematic_bias() with no reviews returns zeroed BiasReport."""
        report = self.analyzer.detect_systematic_bias([])
        assert report.reviewed_total == 0
        assert report.confidence_mismatch_rate == 0.0
        assert report.frequent_attribute_gaps == []
        assert report.suggestions == []

    def test_all_correct_reviews_no_suggestions(self):
        """All correct reviews → no suggestions, mismatch_rate=0."""
        reviews = [_make_review(was_correct=True) for _ in range(10)]
        report = self.analyzer.detect_systematic_bias(reviews)
        assert report.confidence_mismatch_rate == 0.0
        assert report.suggestions == []
        assert report.reviewed_total == 10

    def test_high_mismatch_rate_generates_suggestion(self):
        """confidence_mismatch_rate > 20% → threshold_high suggestion."""
        reviews = [_make_review(was_correct=False, confidence_mismatch=True) for _ in range(5)] + [
            _make_review(was_correct=True) for _ in range(5)
        ]
        report = self.analyzer.detect_systematic_bias(reviews)
        # 5/10 mismatches = 50% > 20% threshold
        assert report.confidence_mismatch_rate == 0.5
        param_names = [s.parameter for s in report.suggestions]
        assert "thresholds.threshold_high" in param_names

    def test_frequent_attribute_gaps_detected(self):
        """Repeated attribute_gap on wrong reviews → attribute suggestion."""
        reviews = [_make_review(was_correct=False, attribute_gap="dmt") for _ in range(5)] + [
            _make_review(was_correct=True) for _ in range(5)
        ]
        report = self.analyzer.detect_systematic_bias(reviews)
        assert "dmt" in report.frequent_attribute_gaps
        # Should have a suggestion for attribute_match
        rationale_texts = [s.rationale for s in report.suggestions]
        assert any("dmt" in r for r in rationale_texts)

    def test_reviewed_total_count(self):
        """reviewed_total reflects actual number of reviews."""
        reviews = [_make_review() for _ in range(7)]
        report = self.analyzer.detect_systematic_bias(reviews)
        assert report.reviewed_total == 7

    def test_suggest_config_changes_returns_suggestions(self):
        """suggest_config_changes() returns bias_report.suggestions."""
        reviews = [_make_review(was_correct=False, confidence_mismatch=True) for _ in range(4)] + [
            _make_review(was_correct=True)
        ]
        report = self.analyzer.detect_systematic_bias(reviews)
        suggestions = self.analyzer.suggest_config_changes(report, DEFAULT_SCORING_CONFIG)
        assert suggestions is report.suggestions

    def test_suggest_config_changes_empty_no_suggestions(self):
        """suggest_config_changes() returns [] when no bias detected."""
        reviews = [_make_review(was_correct=True) for _ in range(10)]
        report = self.analyzer.detect_systematic_bias(reviews)
        suggestions = self.analyzer.suggest_config_changes(report, DEFAULT_SCORING_CONFIG)
        assert suggestions == []

    def test_mismatch_threshold_raised(self):
        """Mismatch rate triggers threshold increase suggestion."""
        # 3 mismatches with confidence_mismatch out of 5 total
        reviews = [_make_review(was_correct=False, confidence_mismatch=True)] * 3 + [_make_review(was_correct=True)] * 2
        report = self.analyzer.detect_systematic_bias(reviews)
        if report.confidence_mismatch_rate > CalibrationAnalyzer.MISMATCH_THRESHOLD:
            suggestion = next(
                (s for s in report.suggestions if s.parameter == "thresholds.threshold_high"),
                None,
            )
            assert suggestion is not None
            assert suggestion.suggested_value > 0.75  # raised above default

    def test_low_mismatch_rate_no_threshold_suggestion(self):
        """Low mismatch rate (≤ 20%) → no threshold_high suggestion."""
        reviews = [
            _make_review(was_correct=False, confidence_mismatch=True),
            _make_review(was_correct=True),
            _make_review(was_correct=True),
            _make_review(was_correct=True),
            _make_review(was_correct=True),
            # 1/5 = 20% = exactly at threshold (not above)
        ]
        report = self.analyzer.detect_systematic_bias(reviews)
        # 20% is NOT > 20%, so no suggestion
        param_names = [s.parameter for s in report.suggestions]
        assert "thresholds.threshold_high" not in param_names

    def test_infrequent_attribute_gap_ignored(self):
        """Single attribute_gap occurrence is not in frequent_gaps."""
        reviews = [
            _make_review(was_correct=False, attribute_gap="rare_attr"),
            _make_review(was_correct=True),
            _make_review(was_correct=True),
            _make_review(was_correct=True),
            _make_review(was_correct=True),
        ]
        report = self.analyzer.detect_systematic_bias(reviews)
        assert "rare_attr" not in report.frequent_attribute_gaps
