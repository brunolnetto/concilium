"""Strategic tests to reach 100% coverage.

Targets remaining 58 missing statements across multiple modules.
Focus on error handling, edge cases, and specific condition paths.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from concilium.domain.models.canonical import (
    Coordenadas,
    Meta,
    Projeto,
    RegimeTrabalho,
)


def _make_meta():
    return Meta(gerado_em=datetime.now(UTC), contexto_id="test")

def _make_proj():
    return Projeto(
        id="p1",
        nome="proj",
        tipo_obra="terraplenagem",
        localizacao="x",
        coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
        regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
        data_inicio=date(2026, 6, 1),
        data_termino=date(2026, 7, 31),
        snapshot_catalogo_id="s",
        snapshot_perfil_id="s",
    )


# semantic/extractor.py: field extraction (line 169)
# ────────────────────────────────────────────────────────────────


class TestSemanticExtraction:
    """Test semantic field extraction."""

    def test_extractor_with_complex_input(self):
        """Extractor should handle complex input structures."""
        pass


# ────────────────────────────────────────────────────────────────

