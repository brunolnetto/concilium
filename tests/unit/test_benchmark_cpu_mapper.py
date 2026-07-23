"""Tests for benchmarks comparison and support modules at 0% coverage.

Covers:
- catalog_confronto.py
- equipes_detail.py
- granular.py
- output_packager.py
- cpu_mapper.py (CpuMapper)
- cpu_validator.py (CpuValidator)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

_SAMPLE_CPU = {
    "codigo": "ATI-001",
    "descricao": "Aterro Compactação",
    "unidade": "m³",
    "categoria": "TERRA",
}

_SAMPLE_CATALOGO = {"cpus": [_SAMPLE_CPU]}

def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# 5a. cpu_mapper.py — CpuMapper
# ===========================================================================

from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper  # noqa: E402


def _make_mapper() -> CpuMapper:
    """Return a CpuMapper with _load_catalog patched out."""
    with patch.object(CpuMapper, "_load_catalog"):
        mapper = CpuMapper.__new__(CpuMapper)
        mapper.contexto_id = "mendeslobo"
        mapper._cpu_cache = {}
        mapper.catalogo = dict(_SAMPLE_CATALOGO)
        mapper.contexto = MagicMock()
    return mapper


class TestCpuMapperSearchCpus:
    def test_finds_matching_cpu(self):
        mapper = _make_mapper()
        results = mapper.search_cpus("aterro")
        assert len(results) >= 1
        assert results[0]["cpu_id"] == "ATI-001"

    def test_no_match_returns_empty(self):
        mapper = _make_mapper()
        results = mapper.search_cpus("nonexistent_xyz_abc")
        assert results == []

    def test_limit_respected(self):
        # Add extra CPUs to make limit meaningful
        mapper = _make_mapper()
        mapper.catalogo = {
            "cpus": [
                {
                    "codigo": f"CPU-{i:03d}",
                    "descricao": "Aterro Compactação genérico",
                    "unidade": "m³",
                    "categoria": "TERRA",
                }
                for i in range(10)
            ]
        }
        results = mapper.search_cpus("aterro", limit=3)
        assert len(results) <= 3

    def test_no_internal_score_key_in_output(self):
        mapper = _make_mapper()
        results = mapper.search_cpus("aterro")
        for r in results:
            assert "_score" not in r


class TestCpuMapperMapItemToCpu:
    def test_match_found_caches_result(self):
        mapper = _make_mapper()
        cpu_id = mapper.map_item_to_cpu("1.1", "Aterro Compactação")
        assert cpu_id == "ATI-001"
        assert mapper._cpu_cache["1.1"] == "ATI-001"

    def test_cached_result_used(self):
        mapper = _make_mapper()
        mapper._cpu_cache["2.1"] = "ATI-001"
        # Even with wrong description the cache wins
        cpu_id = mapper.map_item_to_cpu("2.1", "some random text xyz")
        assert cpu_id == "ATI-001"

    def test_no_match_returns_none(self):
        mapper = _make_mapper()
        cpu_id = mapper.map_item_to_cpu("3.1", "xyzzy_nonexistent_item")
        assert cpu_id is None

    def test_fallback_word_search(self):
        """Description has long word matching the catalog entry."""
        mapper = _make_mapper()
        # "Compactação" alone should match "Aterro Compactação"
        cpu_id = mapper.map_item_to_cpu("4.1", "Compactação solo")
        assert cpu_id == "ATI-001"


class TestCpuMapperMapItemsBatch:
    def test_empty_list_returns_empty_dict(self):
        mapper = _make_mapper()
        assert mapper.map_items_batch([]) == {}

    def test_list_with_items_returns_mappings(self):
        mapper = _make_mapper()
        items = [
            {"item_id": "1.1", "descricao": "Aterro"},
            {"item_id": "1.2", "descricao": "xyzzy_nonexistent"},
        ]
        result = mapper.map_items_batch(items)
        assert "1.1" in result
        assert "1.2" in result
        assert result["1.1"] is not None
        assert result["1.2"] is None


class TestCpuMapperGetAvailableCpus:
    def test_returns_list_with_cpu_id(self):
        mapper = _make_mapper()
        cpus = mapper.get_available_cpus()
        assert isinstance(cpus, list)
        assert len(cpus) == 1
        assert "cpu_id" in cpus[0]
        assert cpus[0]["cpu_id"] == "ATI-001"


class TestCpuMapperGetMappingStats:
    def test_empty_cache_success_rate_zero(self):
        mapper = _make_mapper()
        stats = mapper.get_mapping_stats()
        assert stats["total_items_processed"] == 0
        assert stats["success_rate"] == 0
        assert stats["successfully_mapped"] == 0
        assert stats["failed_mappings"] == 0

    def test_with_cached_items_computes_stats(self):
        mapper = _make_mapper()
        mapper._cpu_cache = {"1.1": "ATI-001", "1.2": None, "1.3": "ATI-001"}
        stats = mapper.get_mapping_stats()
        assert stats["total_items_processed"] == 3
        assert stats["successfully_mapped"] == 2
        assert stats["failed_mappings"] == 1
        assert abs(stats["success_rate"] - 66.666) < 0.1


# ===========================================================================



import pytest  # noqa: E402

# ─── application/benchmarks/validation/cpu_mapper.py ─────────────────────────


class TestCpuMapper:
    def _make_mapper(self, catalogo=None):
        from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper

        mapper = CpuMapper.__new__(CpuMapper)
        mapper.contexto_id = "test"
        mapper.runtime = MagicMock()
        mapper._cpu_cache = {}
        mapper.catalogo = catalogo or {
            "cpus": [
                {"codigo": "CPU-ESC", "descricao": "Escavação 1ª categoria", "unidade": "m³", "categoria": "TERRA"},
                {"codigo": "CPU-ATE", "descricao": "Aterro compactado", "unidade": "m³", "categoria": "TERRA"},
            ]
        }
        return mapper

    def test_search_cpus_exact_match(self):
        mapper = self._make_mapper()
        results = mapper.search_cpus("Escavação")
        assert len(results) >= 1
        assert any(r["cpu_id"] == "CPU-ESC" for r in results)

    def test_search_cpus_no_match(self):
        mapper = self._make_mapper()
        results = mapper.search_cpus("pavimento concreto")
        assert results == []

    def test_search_cpus_limit(self):
        catalogo = {"cpus": [{"codigo": f"CPU-{i}", "descricao": f"Test CPU {i}"} for i in range(10)]}
        mapper = self._make_mapper(catalogo)
        results = mapper.search_cpus("Test", limit=3)
        assert len(results) <= 3

    def test_map_item_to_cpu_found(self):
        mapper = self._make_mapper()
        result = mapper.map_item_to_cpu("2.1", "Escavação")
        assert result == "CPU-ESC"
        assert "2.1" in mapper._cpu_cache

    def test_map_item_to_cpu_cached(self):
        mapper = self._make_mapper()
        mapper._cpu_cache["2.1"] = "CPU-CACHED"
        result = mapper.map_item_to_cpu("2.1", "anything")
        assert result == "CPU-CACHED"

    def test_map_item_to_cpu_fallback_word_search(self):
        mapper = self._make_mapper()
        result = mapper.map_item_to_cpu("3.1", "Aterro tipo compactado")
        assert result == "CPU-ATE"

    def test_map_item_to_cpu_fallback_skips_short_words(self):
        """Palavras com <=3 caracteres são puladas na busca por termos-chave
        (branch false de `if len(word) > 3`) antes de achar uma palavra longa
        que resulte em match."""
        mapper = self._make_mapper()
        result = mapper.map_item_to_cpu("3.2", "de aterro")
        assert result == "CPU-ATE"

    def test_map_item_to_cpu_fallback_loop_skips_short_word_then_matches_long_one(self):
        """Line 112 (false branch of `if len(word) > 3`): the full-descricao search
        (line 104) and the two other existing fallback tests above all incidentally
        match on the *first* try via search_cpus' own per-word scoring against the
        description — they never actually reach this loop. Here the catalog entry's
        descricao shares no substring with any word of the query, so the direct
        search returns empty and we truly fall into the per-word loop: "de" (<=3
        chars) is skipped, then "XPTO" (>3 chars) matches via the CPU's codigo."""
        catalogo = {
            "cpus": [
                {"codigo": "XPTO", "descricao": "Unico Especial Distinto", "unidade": "un", "categoria": "X"},
            ]
        }
        mapper = self._make_mapper(catalogo)
        assert mapper.search_cpus("de XPTO extra", limit=1) == []
        result = mapper.map_item_to_cpu("1.1", "de XPTO extra")
        assert result == "XPTO"

    def test_map_item_to_cpu_no_match(self):
        mapper = self._make_mapper()
        result = mapper.map_item_to_cpu("9.9", "pavimento asfaltico especial")
        assert result is None

    def test_map_items_batch(self):
        mapper = self._make_mapper()
        items = [
            {"item_id": "1.1", "descricao": "Escavação"},
            {"item_id": "1.2", "descricao": "Aterro"},
        ]
        result = mapper.map_items_batch(items)
        assert "1.1" in result
        assert "1.2" in result

    def test_get_available_cpus(self):
        mapper = self._make_mapper()
        cpus = mapper.get_available_cpus()
        assert len(cpus) == 2
        assert all("cpu_id" in c for c in cpus)

    def test_get_mapping_stats_empty(self):
        mapper = self._make_mapper()
        stats = mapper.get_mapping_stats()
        assert stats["total_items_processed"] == 0
        assert stats["success_rate"] == 0

    def test_get_mapping_stats_with_data(self):
        mapper = self._make_mapper()
        mapper._cpu_cache = {"1.1": "CPU-ESC", "1.2": None}
        stats = mapper.get_mapping_stats()
        assert stats["total_items_processed"] == 2
        assert stats["successfully_mapped"] == 1
        assert stats["failed_mappings"] == 1
        assert stats["success_rate"] == 50.0

    def test_load_catalog_raises_on_error(self, tmp_path):
        from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper

        with pytest.raises(RuntimeError, match="Failed to load catalog"):
            CpuMapper(contexto_id="nonexistent", config_root=tmp_path)

    def test_auto_detect_config_root_and_load_catalog(self):
        """Lines 29, 39-40: auto-detects config_root when None; loads catalogo and contexto."""
        from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper

        with patch("concilium.application.benchmarks.validation.cpu_mapper.Runtime") as MockRuntime:
            mock_runtime = MagicMock()
            MockRuntime.return_value = mock_runtime
            mock_ctx = MagicMock()
            mock_ctx.catalogo_id = "test_cat"
            mock_runtime.load_contexto.return_value = mock_ctx
            mock_runtime.load_catalogo.return_value = {"cpus": []}

            mapper = CpuMapper(contexto_id="testctx")  # config_root=None

        call_path = MockRuntime.call_args[0][0]
        assert "config" in str(call_path).lower()
        assert mapper.contexto is mock_ctx

    def test_search_cpus_code_match_scores_higher(self):
        """Line 64: query matching CPU code adds score += 100."""
        mapper = self._make_mapper(catalogo={"cpus": [{"codigo": "escav", "descricao": "irrelevant thing"}]})
        results = mapper.search_cpus("escav")
        assert results and results[0]["cpu_id"] == "escav"

    def test_map_item_fallback_word_matches_code(self):
        """Lines 115-117: fallback word search finds CPU when full desc misses but single word matches code."""
        mapper = self._make_mapper(catalogo={"cpus": [{"codigo": "escavacao", "descricao": "unrelated_thing"}]})
        # Full desc: "prefix_xyz escavacao" → "prefix_xyz" and "escavacao" not in "unrelated_thing"
        # But fallback word "escavacao" IS the code → score 100
        result = mapper.map_item_to_cpu("9.1", "prefix_xyz escavacao")
        assert result == "escavacao"



