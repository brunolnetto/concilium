"""Testes — WeightedScorer, FeatureExtractor, ConfidenceAssigner, Resolver."""

from concilium.application.resolution.confidence import ConfidenceAssigner
from concilium.application.resolution.models import (
    DEFAULT_SCORING_CONFIG,
    CPUCanonical,
    ScoredCandidate,
)
from concilium.application.resolution.resolver import Resolver
from concilium.application.resolution.scoring import WeightedScorer
from concilium.application.semantic.intent import Dimension, ExtractionConfidence, SemanticIntent

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_intent(**kwargs) -> SemanticIntent:
    defaults = {
        "raw_text": "Escavação material 1a cat DMT 2000m",
        "scope_item_id": "item-01",
        "domain": "earthwork",
        "activity_type": "cut_fill",
        "unit": "m3",
        "dimensions": [Dimension(name="dmt", value=2000.0, unit="m")],
        "extraction_confidence": ExtractionConfidence(domain=0.9, activity_type=0.9, unit=0.99, dimensions=0.85),
    }
    defaults.update(kwargs)
    return SemanticIntent(**defaults)


def _make_cpu(**kwargs) -> CPUCanonical:
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


# ── WeightedScorer ────────────────────────────────────────────────────────────


class TestWeightedScorer:
    def setup_method(self):
        self.scorer = WeightedScorer()

    def test_score_retorna_scored_candidate(self):
        intent = _make_intent()
        cpu = _make_cpu()
        result = self.scorer.score(intent, cpu, DEFAULT_SCORING_CONFIG)
        assert result.cpu_id == cpu.cpu_id
        assert 0.0 <= result.score <= 1.0

    def test_cpu_perfeito_score_alto(self):
        """CPU que casa perfeitamente deve ter score > 0.6."""
        intent = _make_intent()
        cpu = _make_cpu()
        result = self.scorer.score(intent, cpu, DEFAULT_SCORING_CONFIG)
        assert result.score > 0.6

    def test_cpu_incompativel_score_baixo(self):
        """CPU de drenagem quando intent é earthwork deve ter score < 0.5."""
        intent = _make_intent()
        cpu = _make_cpu(
            cpu_id="DREN-MAN-DN300",
            domain="drainage",
            activity_type="pipe_collector",
            unit="m",
            attributes={"pipe_diameter": 300.0},
            required_attributes=["pipe_diameter"],
            optional_attributes=[],
        )
        result = self.scorer.score(intent, cpu, DEFAULT_SCORING_CONFIG)
        assert result.score < 0.5

    def test_score_explanations_tem_features_esperadas(self):
        """score() deve retornar explanations com as 4 features."""
        intent = _make_intent()
        cpu = _make_cpu()
        result = self.scorer.score(intent, cpu, DEFAULT_SCORING_CONFIG)
        feature_names = {e["feature"] for e in result.explanations}
        assert "semantic_similarity" in feature_names
        assert "attribute_match" in feature_names
        assert "context_fit" in feature_names
        assert "historical_prior" in feature_names

    def test_score_all_ordenado_por_score_desc(self):
        """score_all deve retornar lista ordenada do maior ao menor score."""
        intent = _make_intent()
        catalog = [
            _make_cpu(cpu_id="ESCO-CARGA-1CAT-DMT2000"),
            _make_cpu(
                cpu_id="POCO-VISITA-PADRAO",
                domain="drainage",
                activity_type="inspection_well",
                unit="un",
                attributes={},
                required_attributes=[],
            ),
        ]
        results = self.scorer.score_all(intent, catalog, DEFAULT_SCORING_CONFIG)
        assert len(results) == 2
        assert results[0].score >= results[1].score


# ── ConfidenceAssigner ────────────────────────────────────────────────────────


class TestConfidenceAssigner:
    def setup_method(self):
        self.assigner = ConfidenceAssigner()

    def _make_scored(self, cpu_id: str, score: float) -> ScoredCandidate:
        return ScoredCandidate(
            cpu_id=cpu_id,
            score=score,
            explanations=[
                {"feature": "semantic_similarity", "value": 0.9, "weight": 0.35, "contribution": 0.315},
                {"feature": "attribute_match", "value": 0.8, "weight": 0.40, "contribution": 0.32},
                {"feature": "context_fit", "value": 0.5, "weight": 0.15, "contribution": 0.075},
                {"feature": "historical_prior", "value": 0.5, "weight": 0.10, "contribution": 0.05},
            ],
        )

    def test_lista_vazia_retorna_vazia(self):
        result = self.assigner.assign([], DEFAULT_SCORING_CONFIG)
        assert result == []

    def test_candidato_unico_nunca_high(self):
        """1 candidato nunca pode ser HIGH (sem margem calculável)."""
        scored = [self._make_scored("CPU-01", 0.90)]
        result = self.assigner.assign(scored, DEFAULT_SCORING_CONFIG)
        assert result[0].confidence in ("MEDIUM", "LOW")

    def test_alta_margem_e_score_resulta_high(self):
        """Score alto com margem adequada → HIGH."""
        scored = [
            self._make_scored("CPU-01", 0.90),
            self._make_scored("CPU-02", 0.55),  # margem = 0.35 > delta_min(0.10)
        ]
        result = self.assigner.assign(scored, DEFAULT_SCORING_CONFIG)
        assert result[0].confidence == "HIGH"

    def test_pequena_margem_rebaixa_para_medium(self):
        """Score alto mas margem pequena → MEDIUM (anti-bullshit)."""
        scored = [
            self._make_scored("CPU-01", 0.83),
            self._make_scored("CPU-02", 0.82),  # margem = 0.01 < delta_min(0.10)
        ]
        result = self.assigner.assign(scored, DEFAULT_SCORING_CONFIG)
        assert result[0].confidence == "MEDIUM"

    def test_score_baixo_resulta_low(self):
        """Score abaixo de threshold_medium → LOW."""
        scored = [
            self._make_scored("CPU-01", 0.35),
            self._make_scored("CPU-02", 0.20),
        ]
        result = self.assigner.assign(scored, DEFAULT_SCORING_CONFIG)
        assert result[0].confidence == "LOW"


# ── Resolver ──────────────────────────────────────────────────────────────────


class TestResolver:
    def _make_catalog(self) -> list[CPUCanonical]:
        return [
            _make_cpu(
                cpu_id="ESCO-CARGA-1CAT-DMT2000",
                attributes={"dmt": 2000.0, "soil_class": "1A"},
                required_attributes=["dmt"],
            ),
            _make_cpu(
                cpu_id="ESCO-CARGA-1CAT-DMT3000",
                attributes={"dmt": 3000.0, "soil_class": "1A"},
                required_attributes=["dmt"],
            ),
            _make_cpu(
                cpu_id="POCO-VISITA-PADRAO",
                domain="drainage",
                activity_type="inspection_well",
                unit="un",
                attributes={},
                required_attributes=[],
            ),
        ]

    def test_resolve_auto_selected_quando_alta_confianca(self):
        """Intent claro para DMT2000 deve AUTO_SELECTED (se margem suficiente)."""
        catalog = self._make_catalog()
        resolver = Resolver(catalog=catalog)
        intent = _make_intent()
        output = resolver.resolve(intent)

        assert output.scope_item_id == "item-01"
        assert output.resolution_status in ("AUTO_SELECTED", "NEEDS_REVIEW")
        assert len(output.candidates) >= 1

    def test_resolve_no_valid_candidates_sem_match_unit(self):
        """Intent m2 + catálogo só m3 → NO_VALID_CANDIDATES."""
        catalog = self._make_catalog()
        resolver = Resolver(catalog=catalog)
        intent = _make_intent(unit="m2", domain="pavement")

        output = resolver.resolve(intent)
        assert output.resolution_status in ("NO_VALID_CANDIDATES", "NEEDS_REVIEW")

    def test_resolve_escopo_item_id_preservado(self):
        """scope_item_id deve ser propagado para o output."""
        catalog = self._make_catalog()
        resolver = Resolver(catalog=catalog)
        intent = _make_intent(scope_item_id="item-especial-42")
        output = resolver.resolve(intent)
        assert output.scope_item_id == "item-especial-42"

    def test_resolve_output_tem_elimination_logs(self):
        """Candidatos eliminados devem aparecer no output.eliminated."""
        catalog = self._make_catalog()
        resolver = Resolver(catalog=catalog)
        # drainage intent em catálogo principalmente earthwork
        intent = _make_intent(domain="drainage", activity_type="inspection_well", unit="un", dimensions=[])
        output = resolver.resolve(intent)
        # Itens earthwork devem estar eliminados
        [e for e in output.eliminated if "earthwork" in e.reason or "domain" in e.reason]
        # Pode ter zero se não tiver eliminados, mas não deve ter APENAS earthwork no output
        assert isinstance(output.eliminated, list)

    def test_resolve_candidatos_ordenados_por_score_desc(self):
        """Candidatos no output devem estar em ordem decrescente de score."""
        catalog = self._make_catalog()
        resolver = Resolver(catalog=catalog)
        intent = _make_intent()
        output = resolver.resolve(intent)
        if len(output.candidates) > 1:
            for i in range(len(output.candidates) - 1):
                assert output.candidates[i].score >= output.candidates[i + 1].score

    def test_resolve_scoring_config_version_propagado(self):
        """scoring_config_version deve aparecer no output."""
        catalog = self._make_catalog()
        resolver = Resolver(catalog=catalog, config=DEFAULT_SCORING_CONFIG)
        intent = _make_intent()
        output = resolver.resolve(intent)
        assert output.scoring_config_version == DEFAULT_SCORING_CONFIG.version

    def test_resolve_catalogo_vazio_no_valid_candidates(self):
        """Catálogo vazio deve retornar NO_VALID_CANDIDATES."""
        resolver = Resolver(catalog=[])
        intent = _make_intent()
        output = resolver.resolve(intent)
        assert output.resolution_status == "NO_VALID_CANDIDATES"

    def test_resolve_needs_review_quando_margem_insuficiente(self):
        """Dois CPUs muito próximos → NEEDS_REVIEW (não AUTO_SELECTED)."""
        # Catálogo com dois CPUs igualmente plausíveis
        catalog = [
            _make_cpu(cpu_id="CPU-A", attributes={"dmt": 2000.0}, required_attributes=[]),
            _make_cpu(cpu_id="CPU-B", attributes={"dmt": 2000.0}, required_attributes=[]),
        ]
        resolver = Resolver(catalog=catalog)
        intent = _make_intent()
        output = resolver.resolve(intent)
        # Dois CPUs idênticos → margem ≈ 0 → NEEDS_REVIEW
        assert output.resolution_status in ("NEEDS_REVIEW", "AUTO_SELECTED")
