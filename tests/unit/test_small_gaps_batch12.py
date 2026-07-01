"""Coverage batch 12 — small 1-2 miss targets across many files."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

# ---------------------------------------------------------------------------
# service_support.py line 25: build_summary returns early when result is None
# ---------------------------------------------------------------------------


class TestServiceSupportBuildSummaryNoneResult:
    def test_returns_partial_dict_when_no_resultado(self):
        """Line 25: canonical has no resultado → result=None → early return dict."""
        from concilium.application.services.service_support import build_summary

        canonical = SimpleNamespace(ponto_equilibrio=[])
        result = build_summary(canonical)
        assert "pe_deficit_items" in result
        assert "pe_alerta_items" in result
        assert "custo_total" not in result  # early return, not full dict


# ---------------------------------------------------------------------------
# cubo_combustivel_builder.py line 36: continue when permanencia_meses <= 0
# ---------------------------------------------------------------------------


class TestCuboCombustivelBuilderZeroPerm:
    def test_skips_equipe_with_zero_permanencia(self):
        """Line 36: equipe.permanencia_meses=0 → if perm <= 0: continue."""
        from concilium.domain.services.analytics.cubo_combustivel_builder import build_cubo_combustivel_face

        equipe = SimpleNamespace(item_id="A1", permanencia_meses=0.0, equipamentos=[])
        canonical = SimpleNamespace(
            equipes_diretas=[equipe],
            projeto=SimpleNamespace(nome="PROJ-01", id="P-01"),
        )
        result = build_cubo_combustivel_face(canonical)
        assert result is not None
        assert result.celulas == ()


# ---------------------------------------------------------------------------
# confidence.py line 137: high semantic_similarity + low attribute_match → flag
# ---------------------------------------------------------------------------


class TestConfidenceDetectEmbeddingFailureModes:
    def test_high_similarity_low_attribute_match_flagged(self):
        """Line 137: sem_sim >= 0.8 and attr_match <= 0.3 → 'high_similarity_low_attribute_match'."""
        from concilium.application.resolution.confidence import ConfidenceAssigner

        assigner = ConfidenceAssigner()
        cand = SimpleNamespace(
            score=0.85,
            explanations=[
                {"feature": "semantic_similarity", "value": 0.9, "weight": 0.3, "contribution": 0.27},
                {"feature": "attribute_match", "value": 0.2, "weight": 0.4, "contribution": 0.08},
            ],
        )
        failures = assigner._detect_embedding_failure_modes(cand, [cand])
        assert "high_similarity_low_attribute_match" in failures


# ---------------------------------------------------------------------------
# _common.py line 70: col_label returns col_id when not found in columns
# ---------------------------------------------------------------------------


class TestColLabelFallback:
    def test_returns_col_id_when_not_found_in_columns(self):
        """Line 70: col_id not in any column → return col_id or ''."""
        from concilium.application.runtime.deliverables.visualizations.cube._common import col_label

        columns = [{"id": "tempo_natureza", "label": "Tempo × Natureza"}]
        result = col_label(columns, "NONEXISTENT_COL_ID")
        assert result == "NONEXISTENT_COL_ID"

    def test_returns_empty_when_col_id_is_none(self):
        """Coverage: col_id=None → if not col_id: return ''."""
        from concilium.application.runtime.deliverables.visualizations.cube._common import col_label

        assert col_label([], None) == ""


# ---------------------------------------------------------------------------
# executive_summary.py line 20: _get returns getattr when obj is not a dict
# ---------------------------------------------------------------------------


class TestExecutiveSummaryGetHelper:
    def test_get_uses_getattr_for_non_dict_obj(self):
        """Line 20: obj is not a dict → return getattr(obj, key, default)."""
        from concilium.application.runtime.deliverables.reports.executive_summary import _get

        obj = SimpleNamespace(custo_total=99_000.0)
        assert _get(obj, "custo_total") == 99_000.0
        assert _get(obj, "nonexistent_key", "fallback") == "fallback"


# ---------------------------------------------------------------------------
# resolution/models.py line 325: _compute_frequent_gaps returns [] when total <= 0
# ---------------------------------------------------------------------------


class TestComputeFrequentGapsZeroTotal:
    def test_returns_empty_list_when_total_zero(self):
        """Line 325: total <= 0 → return []."""
        from concilium.application.resolution.models import _compute_frequent_gaps

        result = _compute_frequent_gaps({"gap_a": 5}, total=0)
        assert result == []

    def test_returns_empty_list_when_total_negative(self):
        """Line 325: total < 0 → return []."""
        from concilium.application.resolution.models import _compute_frequent_gaps

        result = _compute_frequent_gaps({"gap_a": 1}, total=-1)
        assert result == []


# ---------------------------------------------------------------------------
# silver_normalizer.py line 114: normalize_metric_record covers return dict
# ---------------------------------------------------------------------------


class TestSilverNormalizerMetricRecord:
    def test_normalize_metric_record_returns_schema(self):
        """Line 114: normalize_metric_record called → returns normalized dict."""
        from concilium.infrastructure.observability.silver_normalizer import normalize_metric_record

        record = {
            "metric_name": "api_latency_ms",
            "ts": "2026-06-30T10:00:00Z",
            "value": 42.5,
            "labels": {"endpoint": "/api/v1/health"},
            "service": "concilium-api",
        }
        result = normalize_metric_record(record)
        assert result["metric_name"] == "api_latency_ms"
        assert result["value"] == 42.5
        assert isinstance(result["labels"], dict)

    def test_normalize_metric_record_with_empty_record(self):
        """Line 114: empty record → defaults applied."""
        from concilium.infrastructure.observability.silver_normalizer import normalize_metric_record

        result = normalize_metric_record({})
        assert result["metric_name"] == ""
        assert result["value"] == 0.0
        assert result["labels"] == {}


# ---------------------------------------------------------------------------
# client_store.py line 50: _verify_secret returns False when no hash and no plaintext
# ---------------------------------------------------------------------------


class TestVerifySecretReturnsFalse:
    def test_returns_false_when_no_secret_hash_and_no_plaintext(self):
        """Line 50: entry has neither secret_hash nor secret → return False."""
        from concilium.infrastructure.auth.client_store import _verify_secret

        entry = {"client_id": "test-client", "roles": ["read"]}  # no secret_hash, no secret
        result = _verify_secret("any-provided-secret", entry)
        assert result is False

    def test_returns_false_when_secret_is_empty_string(self):
        """Line 50: entry.secret='' → plaintext falsy → return False."""
        from concilium.infrastructure.auth.client_store import _verify_secret

        entry = {"secret": "", "roles": ["read"]}
        result = _verify_secret("any-provided-secret", entry)
        assert result is False


# ---------------------------------------------------------------------------
# resolution/storage.py line 66: continue on empty line in JSONL file
# ---------------------------------------------------------------------------


class TestResolutionDecisionStoreEmptyLines:
    def test_load_all_skips_empty_lines_in_file(self):
        """Line 66: empty line in JSONL → if not line: continue → returns []."""
        from concilium.application.resolution.storage import ResolutionDecisionStore

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            tmppath = Path(f.name)
            f.write("\n")  # blank line → stripped to "" → continue (line 66)
            f.write("   \n")  # whitespace-only → stripped to "" → continue (line 66)

        store = ResolutionDecisionStore(store_path=tmppath)
        decisions = store.load_all()
        tmppath.unlink()

        assert decisions == []
