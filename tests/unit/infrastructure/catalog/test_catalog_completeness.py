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





# completeness.py line 46:
# producao with confianca_pct < 60 → prods_baixa += 1
# completeness.py line 118:
# _find_cpu_by_description: cpu descricao is substring of input → return cpu
# ---------------------------------------------------------------------------


class TestCompletenessAnalyzeProducoes:
    def test_low_confianca_increments_prods_baixa(self):
        """Line 46: producao with confianca_pct=50 < 60 → prods_baixa=1."""
        from concilium.infrastructure.catalog.completeness import _analyze_producoes_quality

        producoes = [
            {"origem": {"tipo": "calibrado_contra_obra_real"}, "qualidade": {"confianca_pct": 50}},
        ]
        prods_reais, prods_tabela, prods_baixa, confianca_media = _analyze_producoes_quality(producoes)
        assert prods_reais == 1
        assert prods_baixa == 1
        assert confianca_media == 50.0

    def test_high_confianca_does_not_increment_prods_baixa(self):
        """Validate that confianca_pct >= 60 is not counted as baixa."""
        from concilium.infrastructure.catalog.completeness import _analyze_producoes_quality

        producoes = [
            {"origem": {}, "qualidade": {"confianca_pct": 80}},
        ]
        _, _, prods_baixa, _ = _analyze_producoes_quality(producoes)
        assert prods_baixa == 0


class TestCompletenessFinCpuByDescription:
    def test_cpu_descricao_substring_of_input_returns_cpu(self):
        """Line 118: cpu.descricao.lower() in descricao_lower → return cpu."""
        from concilium.infrastructure.catalog.completeness import CatalogGapDetector

        detector = CatalogGapDetector()
        cpu_a = {"descricao": "escavação hidráulica"}
        # input is a longer string that contains cpu_a's descricao as substring
        result = detector._find_cpu_by_description("escavação hidráulica de rocha", [cpu_a])
        assert result is cpu_a

    def test_no_match_returns_none(self):
        """Return None when no CPU description matches."""
        from concilium.infrastructure.catalog.completeness import CatalogGapDetector

        detector = CatalogGapDetector()
        cpu_a = {"descricao": "compactação de aterro"}
        result = detector._find_cpu_by_description("escavação hidráulica", [cpu_a])
        assert result is None


# ---------------------------------------------------------------------------


# completeness.py lines 30-38: _as_health_status full branch coverage
# ---------------------------------------------------------------------------


class TestCompletenessAsHealthStatus:
    def test_adequado(self):
        from concilium.infrastructure.catalog.completeness import _as_health_status

        assert _as_health_status("ADEQUADO") == "ADEQUADO"

    def test_parcial(self):
        from concilium.infrastructure.catalog.completeness import _as_health_status

        assert _as_health_status("PARCIAL") == "PARCIAL"

    def test_insuficiente(self):
        from concilium.infrastructure.catalog.completeness import _as_health_status

        assert _as_health_status("INSUFICIENTE") == "INSUFICIENTE"

    def test_unexpected_value_raises_value_error(self):
        import pytest

        from concilium.infrastructure.catalog.completeness import _as_health_status

        with pytest.raises(ValueError, match="Status de saúde do catálogo inesperado"):
            _as_health_status("BOGUS")

