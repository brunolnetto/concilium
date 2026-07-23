"""Coverage batch 19 — replanning/validator, completeness small gaps."""

from __future__ import annotations

# completeness.py line 118: _find_cpu_by_description returns None when not found
# ---------------------------------------------------------------------------


class TestFindCpuByDescriptionReturnsNone:
    def _make_checker(self):
        from concilium.infrastructure.catalog.completeness import CatalogGapDetector

        return CatalogGapDetector()

    def test_returns_none_when_no_match(self):
        """Line 118: no CPU matches description → loop exhausted → return None."""
        checker = self._make_checker()
        cpus = [
            {"codigo": "ESCO-01", "descricao": "Escavação de primeira categoria"},
        ]
        result = checker._find_cpu_by_description("pavimentação asfáltica CBUQ", cpus)
        assert result is None

    def test_returns_none_from_empty_cpu_list(self):
        """Line 118: empty cpus → for loop never executes → return None."""
        checker = self._make_checker()
        result = checker._find_cpu_by_description("any description", [])
        assert result is None

    def test_returns_cpu_when_description_matches(self):
        """Normal path: description found → returns the matching cpu dict."""
        checker = self._make_checker()
        cpu = {"codigo": "ESCO-01", "descricao": "Escavação de primeira categoria"}
        result = checker._find_cpu_by_description("escavação de primeira categoria", [cpu])
        assert result == cpu

