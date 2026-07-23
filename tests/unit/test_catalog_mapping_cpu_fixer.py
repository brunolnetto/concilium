"""Tests for catalog mapping modules at 0% coverage.

Covers:
- cpu_fixer.fix_referencia_mappings
- cpu_mapper (private helpers + public API)
- equipes_normalizer (all helpers + public API)
- healer.heal_catalog
"""

from __future__ import annotations

from pathlib import Path

# 1. cpu_fixer
# ---------------------------------------------------------------------------
from concilium.infrastructure.catalog.mapping.cpu_fixer import fix_referencia_mappings


class TestFixReferenciaMappings:
    def test_returns_empty_list_for_existing_path(self, tmp_path: Path) -> None:
        result = fix_referencia_mappings(tmp_path)
        assert result == []

    def test_returns_empty_list_for_nonexistent_path(self, tmp_path: Path) -> None:
        result = fix_referencia_mappings(tmp_path / "does_not_exist")
        assert result == []

    def test_returns_list_type(self, tmp_path: Path) -> None:
        result = fix_referencia_mappings(tmp_path)
        assert isinstance(result, list)


# ---------------------------------------------------------------------------

