"""Coverage batch 8 — scoring, resolver, phase_classifier, catalogo, health."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
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
# resolver.py lines 90-91: NO_VALID_CANDIDATES when confidence assigns nothing
# ---------------------------------------------------------------------------


class TestResolverNoValidCandidates:
    def _make_resolver(self):
        from concilium.application.resolution.models import CPUCanonical
        from concilium.application.resolution.resolver import Resolver

        cpu = CPUCanonical(
            cpu_id="ESCO-01",
            domain="earthwork",
            activity_type="cut_fill",
            unit="m3",
            base_productivity=200.0,
            attributes={"dmt": 2000.0},
            required_attributes=["dmt"],
            optional_attributes=[],
        )
        return Resolver(catalog=[cpu])

    def _make_intent(self):
        from concilium.application.semantic.intent import Dimension, ExtractionConfidence, SemanticIntent

        return SemanticIntent(
            raw_text="Escavação",
            scope_item_id="item-01",
            domain="earthwork",
            activity_type="cut_fill",
            unit="m3",
            dimensions=[Dimension(name="dmt", value=2000.0, unit="m")],
            extraction_confidence=ExtractionConfidence(domain=0.9, activity_type=0.9, unit=0.99, dimensions=0.85),
        )

    def test_no_valid_candidates_when_confidence_returns_empty(self):
        """Lines 90-91: eligible candidates exist but confidence assigns none → NO_VALID_CANDIDATES."""
        resolver = self._make_resolver()
        intent = self._make_intent()

        with patch.object(resolver._confidence, "assign", return_value=[]):
            output = resolver.resolve(intent)

        assert output.resolution_status == "NO_VALID_CANDIDATES"


# ---------------------------------------------------------------------------
# resolver.py line 139: resolve_and_persist calls store.persist when AUTO_SELECTED
# ---------------------------------------------------------------------------


class TestResolverPersistOnAutoSelected:
    def test_persist_called_when_auto_selected(self):
        """Line 139: store is configured and status is AUTO_SELECTED → store.persist(decision)."""
        from concilium.application.resolution.models import CandidateWithConfidence, CPUCanonical
        from concilium.application.resolution.resolver import Resolver
        from concilium.application.semantic.intent import Dimension, ExtractionConfidence, SemanticIntent

        cpu = CPUCanonical(
            cpu_id="ESCO-01",
            domain="earthwork",
            activity_type="cut_fill",
            unit="m3",
            base_productivity=200.0,
            attributes={"dmt": 2000.0},
            required_attributes=["dmt"],
            optional_attributes=[],
        )
        mock_store = MagicMock()
        resolver = Resolver(catalog=[cpu], decision_store=mock_store)

        high_candidate = CandidateWithConfidence(
            cpu_id="ESCO-01",
            score=0.95,
            confidence="HIGH",
            explanations=[],
        )
        with patch.object(resolver._confidence, "assign", return_value=[high_candidate]):
            intent = SemanticIntent(
                raw_text="Escavação",
                scope_item_id="item-01",
                domain="earthwork",
                activity_type="cut_fill",
                unit="m3",
                dimensions=[Dimension(name="dmt", value=2000.0, unit="m")],
                extraction_confidence=ExtractionConfidence(domain=0.9, activity_type=0.9, unit=0.99, dimensions=0.85),
            )
            output, decision = resolver.resolve_and_persist(intent)

        assert output.resolution_status == "AUTO_SELECTED"
        assert mock_store.persist.called
        assert decision is not None


# ---------------------------------------------------------------------------
# phase_classifier.py lines 169, 193, 198: simple function calls
# ---------------------------------------------------------------------------


class TestPhaseClassifierSimpleFunctions:
    def test_resolve_skill_id_unknown_returns_input(self):
        """Line 169: skill_id not in aliases → return skill_id unchanged."""
        from concilium.application.skills.phase_classifier import resolve_skill_id

        result = resolve_skill_id("99-nonexistent-skill")
        assert result == "99-nonexistent-skill"

    def test_resolve_skill_id_known_alias(self):
        """Line 169: skill_id in aliases → return mapped id."""
        from concilium.application.skills.phase_classifier import SKILL_ID_ALIASES, resolve_skill_id

        if SKILL_ID_ALIASES:
            alias_key = next(iter(SKILL_ID_ALIASES))
            result = resolve_skill_id(alias_key)
            assert result == SKILL_ID_ALIASES[alias_key]

    def test_get_phase_skills_returns_list(self):
        """Line 193: get_phase_skills with valid phase → returns list of skill ids."""
        from concilium.application.skills.phase_classifier import get_phase_skills

        result = get_phase_skills("Planejamento")
        assert isinstance(result, list)

    def test_get_phase_skills_unknown_phase_returns_empty(self):
        """Line 193: get_phase_skills with unknown phase → returns []."""
        from concilium.application.skills.phase_classifier import get_phase_skills

        result = get_phase_skills("NonExistentPhase")
        assert result == []

    def test_get_all_phases_returns_list_of_strings(self):
        """Line 198: get_all_phases() → list of str."""
        from concilium.application.skills.phase_classifier import get_all_phases

        result = get_all_phases()
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(p, str) for p in result)


# ---------------------------------------------------------------------------
# catalogo.py lines 38, 40, 42: _infer_tipo_combustivel branches
# ---------------------------------------------------------------------------


class TestInferTipoCombustivel:
    def _infer(self, id_):
        from concilium.domain.models.catalog.catalogo import _infer_tipo_combustivel

        return _infer_tipo_combustivel(id_)

    def test_biodiesel_b100(self):
        """Line 38: 'BIODIESEL' in upper → TipoCombustivel.BIODIESEL."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-BIODIESEL-01") == TipoCombustivel.BIODIESEL

    def test_b100_keyword(self):
        """Line 38: 'B100' in upper → TipoCombustivel.BIODIESEL."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-B100-MOTOR") == TipoCombustivel.BIODIESEL

    def test_eletrico(self):
        """Line 40: 'ELETRIC' in upper → TipoCombustivel.ELETRICO."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-ELETRICO-01") == TipoCombustivel.ELETRICO

    def test_diesel_s500(self):
        """Line 42: 'S500' in upper → TipoCombustivel.DIESEL_S500."""
        from concilium.domain.models.catalog.catalogo import TipoCombustivel

        assert self._infer("EQ-MOTOR-S500") == TipoCombustivel.DIESEL_S500


# ---------------------------------------------------------------------------
# catalogo.py lines 78-82: ClasseCompartilhamento._validate_fields_per_class
# ---------------------------------------------------------------------------


class TestClasseCompartilhamentoValidator:
    def test_valid_exclusivo_dedicado(self):
        """Lines 78, 80, 82: exclusivo_dedicado without fracao_uso → valid."""
        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        obj = ClasseCompartilhamento(classe="exclusivo_dedicado")
        assert obj.classe == "exclusivo_dedicado"

    def test_exclusivo_compartilhavel_without_fracao_raises(self):
        """Lines 78-79: exclusivo_compartilhavel without fracao_uso → ValueError."""
        import pydantic

        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        with pytest.raises((ValueError, pydantic.ValidationError)):
            ClasseCompartilhamento(classe="exclusivo_compartilhavel", fracao_uso=None)

    def test_concorrente_compartilhavel_with_fracao_raises(self):
        """Lines 80-81: concorrente_compartilhavel with fracao_uso set → ValueError."""
        import pydantic

        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        with pytest.raises((ValueError, pydantic.ValidationError)):
            ClasseCompartilhamento(classe="concorrente_compartilhavel", fracao_uso=0.5)

    def test_valid_concorrente_compartilhavel(self):
        """Lines 78, 80, 82: concorrente_compartilhavel without fracao_uso → valid."""
        from concilium.domain.models.catalog.catalogo import ClasseCompartilhamento

        obj = ClasseCompartilhamento(classe="concorrente_compartilhavel")
        assert obj.fracao_uso is None


# ---------------------------------------------------------------------------
# catalogo.py line 169: Insumo._normalizar_unidade field validator
# ---------------------------------------------------------------------------


class TestInsumoNormalizarUnidade:
    def test_create_insumo_triggers_normalizer(self):
        """Line 169: creating Insumo calls _normalizar_unidade on the unidade field."""
        from concilium.domain.models.catalog.catalogo import Insumo

        insumo = Insumo(
            codigo="MAT-001",
            tipo="MATERIAL",
            descricao="Concreto usinado",
            unidade="M3",
            preco_unitario=350.0,
            fonte_preco="catalogo_proprio",
        )
        assert insumo.unidade is not None


# ---------------------------------------------------------------------------
# catalogo.py line 336: CPU._validar_producao_e_coeficientes raises for empty ref
# ---------------------------------------------------------------------------


class TestCPUValidatorEmptyProducaoRef:
    def test_empty_producao_id_ref_raises(self):
        """Line 336: producao_id_ref is '' (falsy) → validator raises ValueError."""
        import pydantic

        from concilium.domain.models.catalog.catalogo import CPU

        with pytest.raises((ValueError, pydantic.ValidationError), match="producao_id_ref"):
            CPU(
                codigo="CPU-001",
                descricao="Test CPU",
                unidade="m3",
                origem="PROPRIA",
                producao_id_ref="",
                categoria="TERRAPLENAGEM",
            )


# ---------------------------------------------------------------------------
# health.py lines 145-149: CatalogHealthReport.compute_status_dados
# ---------------------------------------------------------------------------


class TestCatalogHealthReportComputeStatusDados:
    def test_atualizado_when_zero_desatualizadas_and_few_pendentes(self):
        """Line 145: 0 desatualizadas + <5 pendentes → 'ATUALIZADO'."""
        from concilium.domain.models.catalog.health import CatalogHealthReport

        result = CatalogHealthReport.compute_status_dados(producoes_desatualizadas=0, observacoes_pendentes=3)
        assert result == "ATUALIZADO"

    def test_critico_when_many_pendentes(self):
        """Line 147: observacoes_pendentes > 20 → 'CRITICO'."""
        from concilium.domain.models.catalog.health import CatalogHealthReport

        result = CatalogHealthReport.compute_status_dados(producoes_desatualizadas=0, observacoes_pendentes=25)
        assert result == "CRITICO"

    def test_defasado_otherwise(self):
        """Line 149: other combinations → 'DEFASADO'."""
        from concilium.domain.models.catalog.health import CatalogHealthReport

        result = CatalogHealthReport.compute_status_dados(producoes_desatualizadas=2, observacoes_pendentes=10)
        assert result == "DEFASADO"
