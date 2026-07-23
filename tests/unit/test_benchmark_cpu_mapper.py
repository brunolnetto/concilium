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

