"""Testes — ConstraintFilter: unit, domain, required_attributes, structural."""

from concilium.application.resolution.constraints import ConstraintFilter
from concilium.application.resolution.models import CPUCanonical
from concilium.application.semantic.intent import Dimension, ExtractionConfidence, SemanticIntent


def _make_intent(**kwargs) -> SemanticIntent:
    defaults = {
        "raw_text": "texto de teste",
        "scope_item_id": "item-test",
        "domain": "earthwork",
        "activity_type": "cut_fill",
        "unit": "m3",
        "dimensions": [],
        "extraction_confidence": ExtractionConfidence(domain=0.9, activity_type=0.9, unit=0.9, dimensions=0.5),
    }
    defaults.update(kwargs)
    return SemanticIntent(**defaults)


def _make_cpu(**kwargs) -> CPUCanonical:
    defaults = {
        "cpu_id": "CPU-TEST",
        "domain": "earthwork",
        "activity_type": "cut_fill",
        "unit": "m3",
        "base_productivity": 100.0,
        "attributes": {},
        "required_attributes": [],
        "optional_attributes": [],
    }
    defaults.update(kwargs)
    return CPUCanonical(**defaults)


class TestConstraintFilter:
    def setup_method(self):
        self.f = ConstraintFilter()

    def test_unit_compativel_passa(self):
        intent = _make_intent(unit="m3")
        cpu = _make_cpu(unit="m3")
        result = self.f.check_unit_compatibility(intent, cpu)
        assert result.passed

    def test_unit_incompativel_elimina(self):
        """m2 ≠ m3 → eliminado."""
        intent = _make_intent(unit="m2")
        cpu = _make_cpu(unit="m3")
        result = self.f.check_unit_compatibility(intent, cpu)
        assert not result.passed
        assert "m2" in result.reason or "m3" in result.reason

    def test_domain_compativel_passa(self):
        intent = _make_intent(domain="earthwork")
        cpu = _make_cpu(domain="earthwork")
        result = self.f.check_domain_compatibility(intent, cpu)
        assert result.passed

    def test_domain_incompativel_elimina(self):
        """pavement ≠ drainage → eliminado."""
        intent = _make_intent(domain="pavement")
        cpu = _make_cpu(domain="drainage")
        result = self.f.check_domain_compatibility(intent, cpu)
        assert not result.passed

    def test_domain_other_nao_elimina_por_domain(self):
        """Intent com domain='other' não deve ser eliminado por domain."""
        intent = _make_intent(domain="other")
        cpu = _make_cpu(domain="earthwork")
        result = self.f.check_domain_compatibility(intent, cpu)
        assert result.passed

    def test_required_attributes_presentes_passa(self):
        """CPU exige 'dmt'; intent tem dmt → passa."""
        intent = _make_intent(dimensions=[Dimension(name="dmt", value=2000.0, unit="m")])
        cpu = _make_cpu(required_attributes=["dmt"])
        result = self.f.check_required_attributes(intent, cpu)
        assert result.passed

    def test_required_attributes_ausentes_elimina(self):
        """CPU exige 'pipe_diameter'; intent não tem → eliminado."""
        intent = _make_intent(dimensions=[])
        cpu = _make_cpu(required_attributes=["pipe_diameter"])
        result = self.f.check_required_attributes(intent, cpu)
        assert not result.passed
        assert "pipe_diameter" in result.reason

    def test_structural_cut_fill_dmt_compativel(self):
        """Intent DMT 2000m, CPU max 2000m → elegível."""
        intent = _make_intent(
            activity_type="cut_fill",
            dimensions=[Dimension(name="dmt", value=2000.0, unit="m")],
        )
        cpu = _make_cpu(
            activity_type="cut_fill",
            attributes={"dmt": 2000.0},
        )
        result = self.f.check_structural_compatibility(intent, cpu)
        assert result.passed

    def test_structural_cut_fill_dmt_excede_elimina(self):
        """Intent DMT 3500m, CPU max 2000m → eliminado (excede tolerância)."""
        intent = _make_intent(
            activity_type="cut_fill",
            dimensions=[Dimension(name="dmt", value=3500.0, unit="m")],
        )
        cpu = _make_cpu(
            activity_type="cut_fill",
            attributes={"dmt": 2000.0},
        )
        result = self.f.check_structural_compatibility(intent, cpu)
        assert not result.passed

    def test_is_eligible_cpu_valido(self):
        """CPU totalmente compatível com intent deve ser marcado elegível."""
        intent = _make_intent(unit="m3", domain="earthwork")
        cpu = _make_cpu(unit="m3", domain="earthwork")
        ok, results = self.f.is_eligible(intent, cpu)
        assert ok
        assert all(r.passed for r in results)

    def test_is_eligible_cpu_invalido_retorna_falso(self):
        """CPU com domain errado deve ser inelegível."""
        intent = _make_intent(unit="m3", domain="pavement")
        cpu = _make_cpu(unit="m3", domain="drainage")
        ok, results = self.f.is_eligible(intent, cpu)
        assert not ok
        failed = [r for r in results if not r.passed]
        assert failed, "Deve haver ao menos 1 constraint falhada"
