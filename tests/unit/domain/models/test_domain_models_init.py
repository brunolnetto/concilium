"""Tests for tiny-gap files: validador_cobertura_item, scope_guard, inputs mixin,
conversor_unidades, report_calibration_sections, domain/models/__init__,
analitica, cube __init__, artifact_transport, 04-cronograma/_skill_helpers/_dag."""

from __future__ import annotations

import pytest

# ─── domain/models/__init__.py (1 missing: line 95) ───────────────────────────


class TestDomainModelsInit:
    def test_can_import_domain_models(self):
        import concilium.domain.models

        # The __init__.py has a re-export — just importing it covers the file
        assert hasattr(concilium.domain.models, "__file__")

    def test_canonical_importable(self):
        from concilium.domain.models.canonical import CanonicalModel

        assert CanonicalModel is not None

    def test_unknown_attribute_raises_attribute_error(self):
        """Line 95: __getattr__ raises AttributeError for unknown names."""
        import concilium.domain.models

        with pytest.raises(AttributeError, match="has no attribute"):
            _ = concilium.domain.models.NonExistentModel  # type: ignore[attr-defined]

    def test_lazy_load_known_model(self):
        """__getattr__ successfully resolves and caches a lazy-loaded model."""
        import concilium.domain.models

        # Access via __getattr__ — should return the real class
        cls = concilium.domain.models.Projeto
        assert cls is not None



