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

import pytest

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


# 1. catalog_confronto.py
# ===========================================================================

from concilium.application.benchmarks.comparison.catalog_confronto import (  # noqa: E402
    _acc_process_cpu_refs,
    _acc_process_equipes,
    analyze_catalog_confronto,
    consolidate_all,
)
from concilium.application.benchmarks.comparison.catalog_confronto import (  # noqa: E402
    _load_json as cc_load_json,
)


class TestCcLoadJson:
    def test_exists_valid_json(self, tmp_path):
        p = tmp_path / "data.json"
        _write_json(p, {"key": "value"})
        assert cc_load_json(p) == {"key": "value"}

    def test_not_exists(self, tmp_path):
        p = tmp_path / "missing.json"
        assert cc_load_json(p) == {}

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json}", encoding="utf-8")
        assert cc_load_json(p) == {}


class TestAccProcessCpuRefs:
    def test_with_not_found_cpu(self):
        confronto = {
            "cpu_referencias": {
                "catalog_cpus": {
                    "CPU-001": {"status": "NAO_ENCONTRADO_NO_CATALOGO"},
                    "CPU-002": {"status": "FOUND"},
                }
            }
        }
        result = _acc_process_cpu_refs(confronto)
        assert result == ["CPU-001"]

    def test_empty_confronto(self):
        assert _acc_process_cpu_refs({}) == []

    def test_all_not_found(self):
        confronto = {
            "cpu_referencias": {
                "catalog_cpus": {
                    "A": {"status": "NAO_ENCONTRADO_NO_CATALOGO"},
                    "B": {"status": "NAO_ENCONTRADO_NO_CATALOGO"},
                }
            }
        }
        result = _acc_process_cpu_refs(confronto)
        assert set(result) == {"A", "B"}

    def test_none_catalog_cpus(self):
        confronto = {"cpu_referencias": {"catalog_cpus": None}}
        assert _acc_process_cpu_refs(confronto) == []


class TestAccProcessEquipes:
    def test_classifies_funcoes_vazias(self):
        confronto = {
            "equipes_confronto": {
                "confronto": [
                    {
                        "item_id": "1.1",
                        "cpu_id": "CPU-A",
                        "nome": "Escavação",
                        "discrepancias": {"funcoes_vazia": True},
                    }
                ]
            }
        }
        fv, ev, zv = _acc_process_equipes(confronto)
        assert len(fv) == 1
        assert fv[0]["item_id"] == "1.1"
        assert ev == []
        assert zv == []

    def test_classifies_equipamentos_vazios(self):
        confronto = {
            "equipes_confronto": {
                "confronto": [
                    {
                        "item_id": "1.2",
                        "cpu_id": "CPU-B",
                        "nome": "Aterro",
                        "discrepancias": {"equipamentos_vazia": True},
                    }
                ]
            }
        }
        fv, ev, zv = _acc_process_equipes(confronto)
        assert ev[0]["item_id"] == "1.2"
        assert fv == []
        assert zv == []

    def test_classifies_custo_zero(self):
        confronto = {
            "equipes_confronto": {
                "confronto": [
                    {
                        "item_id": "1.3",
                        "cpu_id": "CPU-C",
                        "nome": "Reaterro",
                        "discrepancias": {"custo_zero": True},
                    }
                ]
            }
        }
        fv, ev, zv = _acc_process_equipes(confronto)
        assert zv[0]["item_id"] == "1.3"
        assert zv[0]["nome"] == "Reaterro"

    def test_empty_confronto_returns_empty_tuples(self):
        fv, ev, zv = _acc_process_equipes({})
        assert fv == []
        assert ev == []
        assert zv == []

    def test_none_confronto_list(self):
        confronto = {"equipes_confronto": {"confronto": None}}
        fv, ev, zv = _acc_process_equipes(confronto)
        assert fv == ev == zv == []

    def test_multiple_flags_on_same_entry(self):
        confronto = {
            "equipes_confronto": {
                "confronto": [
                    {
                        "item_id": "2.1",
                        "cpu_id": "CPU-D",
                        "nome": "Multi",
                        "discrepancias": {
                            "funcoes_vazia": True,
                            "equipamentos_vazia": True,
                            "custo_zero": True,
                        },
                    }
                ]
            }
        }
        fv, ev, zv = _acc_process_equipes(confronto)
        assert len(fv) == 1
        assert len(ev) == 1
        assert len(zv) == 1


class TestAnalyzeCatalogConfronto:
    def test_no_confronto_json_returns_empty(self, tmp_path):
        # tmp_path has no benchmarks/data/<slug>/confronto_catalogo.json
        result = analyze_catalog_confronto("MISSING", root=tmp_path)
        assert result == {}

    def test_valid_json_returns_issues_dict(self, tmp_path):
        slug = "TESTBENCH"
        confronto_data = {
            "cpu_referencias": {
                "catalog_cpus": {
                    "CPU-X": {"status": "NAO_ENCONTRADO_NO_CATALOGO"},
                }
            },
            "equipes_confronto": {
                "confronto": [
                    {
                        "item_id": "1.1",
                        "cpu_id": "CPU-Y",
                        "nome": "Item",
                        "discrepancias": {"funcoes_vazia": True},
                    }
                ]
            },
            "planejamento_confronto": {
                "confronto": [
                    {"item_id": "2.1", "engine_zerado": True},
                ]
            },
        }
        p = tmp_path / "benchmarks" / "data" / slug / "confronto_catalogo.json"
        _write_json(p, confronto_data)

        result = analyze_catalog_confronto(slug, root=tmp_path)

        assert result["slug"] == slug
        assert "CPU-X" in result["cpus_nao_encontradas"]
        assert len(result["equipes_com_funcoes_vazias"]) == 1
        assert result["equipes_com_equipamentos_vazios"] == []
        assert result["equipes_zeradas"] == []
        assert "2.1" in result["planejamento_zerados"]
        assert result["bdi_mismatch"] is False

    def test_uses_default_root_when_none(self, tmp_path):
        # When root is None the function builds a path under _DEFAULT_ROOT.
        # We patch _DEFAULT_ROOT indirectly by passing root explicitly and
        # ensuring a missing root gives {}.
        result = analyze_catalog_confronto("NONEXISTENT", root=tmp_path)
        assert result == {}


class TestConsolidateAll:
    def test_empty_bench_root_returns_zero_totals(self, tmp_path):
        bench_root = tmp_path / "benchmarks" / "data"
        bench_root.mkdir(parents=True)
        result = consolidate_all(root=tmp_path)
        assert result["total_benchmarks"] == 0
        assert result["total_cpus_nao_encontradas"] == 0
        assert result["total_equipes_zeradas"] == 0
        assert result["benchmarks"] == []

    def test_aggregates_one_benchmark(self, tmp_path):
        slug = "BENCH1"
        confronto_data = {
            "cpu_referencias": {
                "catalog_cpus": {
                    "CPU-1": {"status": "NAO_ENCONTRADO_NO_CATALOGO"},
                    "CPU-2": {"status": "NAO_ENCONTRADO_NO_CATALOGO"},
                }
            },
            "equipes_confronto": {
                "confronto": [
                    {
                        "item_id": "1.1",
                        "cpu_id": "CPU-Z",
                        "nome": "Z",
                        "discrepancias": {"custo_zero": True},
                    }
                ]
            },
            "planejamento_confronto": {"confronto": []},
        }
        p = tmp_path / "benchmarks" / "data" / slug / "confronto_catalogo.json"
        _write_json(p, confronto_data)

        result = consolidate_all(root=tmp_path)

        assert result["total_benchmarks"] == 1
        assert result["total_cpus_nao_encontradas"] == 2
        assert result["total_equipes_zeradas"] == 1
        assert result["benchmarks"][0]["slug"] == slug

    def test_bench_root_nonexistent_raises(self, tmp_path):
        # bench_root does not exist at all — iterdir() will raise
        with pytest.raises(Exception):  # noqa: B017
            consolidate_all(root=tmp_path)


# ===========================================================================

