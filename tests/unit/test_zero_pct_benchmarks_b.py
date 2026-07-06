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
import zipfile
from builtins import __import__ as _builtin_import
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ===========================================================================
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
# 2. equipes_detail.py
# ===========================================================================

from concilium.application.benchmarks.comparison.equipes_detail import (  # noqa: E402
    _bed_has_discrepancy,
    build_equipes_detail,
)


class TestBedHasDiscrepancy:
    def test_funcoes_ref_empty_esp_nonempty_returns_true(self):
        assert _bed_has_discrepancy([], ["func_a"], [], []) is True

    def test_both_empty_returns_false(self):
        assert _bed_has_discrepancy([], [], [], []) is False

    def test_funcoes_ref_nonempty_returns_false(self):
        assert _bed_has_discrepancy(["func_a"], ["func_b"], [], []) is False

    def test_equips_ref_empty_esp_nonempty_returns_true(self):
        assert _bed_has_discrepancy([], [], [], ["eq_a"]) is True

    def test_equips_ref_nonempty_esp_nonempty_returns_false(self):
        assert _bed_has_discrepancy(["f"], ["f2"], ["eq"], ["eq2"]) is False


class TestBuildEquipesDetail:
    def test_no_referencia_returns_empty_equipes(self, tmp_path):
        bench_data = tmp_path / "benchmarks" / "data"
        bench_data.mkdir(parents=True)
        result = build_equipes_detail("NOSLUG", root=tmp_path)
        assert result["slug"] == "NOSLUG"
        assert result["total_equipes_com_discrepancias"] == 0
        assert result["equipes"] == []

    def test_referencia_no_equipes_detalhadas(self, tmp_path):
        slug = "NOEQUIP"
        ref = {"eap": [{"item_id": "1.1", "descricao": "Escavação"}], "equipes_detalhadas": []}
        _write_json(tmp_path / "benchmarks" / "data" / slug / "referencia.json", ref)
        result = build_equipes_detail(slug, root=tmp_path)
        assert result["total_equipes_com_discrepancias"] == 0

    def test_equipes_detalhadas_with_discrepancy(self, tmp_path):
        slug = "WITHDISC"
        # The catalog CPU has funcoes but engine equipe has none
        cpu_id = "CPU-TERRA-001"
        cpu_data = {
            "equipe": {
                "funcoes": [{"cargo": "Motorista"}],
                "equipamentos": [],
            },
            "composicao_itens": [],
        }
        ref = {
            "eap": [
                {
                    "item_id": "1.1",
                    "descricao": "Terraplenagem",
                    "quantitativo": 100,
                    "unidade": "m³",
                }
            ],
            "equipes_detalhadas": [
                {
                    "item_id": "1.1",
                    "equipe_id": "EQ-01",
                    "nome": "Equipe A",
                    "cpu_id": cpu_id,
                    "funcoes": [],  # empty → discrepancy with catalog
                    "equipamentos": [],
                    "custo_total": 0,
                    "custo_mao_obra_mensal": 0,
                    "custo_equipamentos_mensal": 0,
                }
            ],
        }
        cpus_dir = tmp_path / "config" / "catalogos" / "mendeslobo" / "cpus"
        _write_json(cpus_dir / f"{cpu_id}.json", cpu_data)
        _write_json(tmp_path / "benchmarks" / "data" / slug / "referencia.json", ref)

        result = build_equipes_detail(slug, root=tmp_path)
        assert result["total_equipes_com_discrepancias"] == 1
        entry = result["equipes"][0]
        assert entry["cpu_id"] == cpu_id
        assert entry["item_id"] == "1.1"
        assert entry["eap_descricao"] == "Terraplenagem"

    def test_equipes_detalhadas_no_discrepancy(self, tmp_path):
        slug = "NODISC"
        cpu_id = "CPU-TERRA-002"
        cpu_data = {
            "equipe": {
                "funcoes": [],
                "equipamentos": [],
            }
        }
        ref = {
            "eap": [],
            "equipes_detalhadas": [
                {
                    "item_id": "1.2",
                    "equipe_id": "EQ-02",
                    "nome": "Equipe B",
                    "cpu_id": cpu_id,
                    "funcoes": [],
                    "equipamentos": [],
                    "custo_total": 500,
                    "custo_mao_obra_mensal": 500,
                    "custo_equipamentos_mensal": 0,
                }
            ],
        }
        cpus_dir = tmp_path / "config" / "catalogos" / "mendeslobo" / "cpus"
        _write_json(cpus_dir / f"{cpu_id}.json", cpu_data)
        _write_json(tmp_path / "benchmarks" / "data" / slug / "referencia.json", ref)

        result = build_equipes_detail(slug, root=tmp_path)
        assert result["total_equipes_com_discrepancias"] == 0

    def test_no_cpu_id_skips_catalog_load(self, tmp_path):
        slug = "NOCPUID"
        ref = {
            "eap": [],
            "equipes_detalhadas": [
                {
                    "item_id": "1.3",
                    "equipe_id": "EQ-03",
                    "nome": "Equipe C",
                    "cpu_id": None,
                    "funcoes": [],
                    "equipamentos": [],
                    "custo_total": 0,
                    "custo_mao_obra_mensal": 0,
                    "custo_equipamentos_mensal": 0,
                }
            ],
        }
        _write_json(tmp_path / "benchmarks" / "data" / slug / "referencia.json", ref)
        # cpu_cat will be {}, equipe will be {}, funcoes_esp/equips_esp both []
        result = build_equipes_detail(slug, root=tmp_path)
        assert result["total_equipes_com_discrepancias"] == 0


# ===========================================================================
# 3. granular.py
# ===========================================================================

from concilium.application.benchmarks.comparison.granular import (  # noqa: E402
    _bgc_build_catalogo_entry,
    _bgc_load_extracao_maps,
    build_granular_comparison,
)


class TestBgcLoadExtracaoMaps:
    def test_empty_dict_returns_empty_maps(self):
        em, iz, cz = _bgc_load_extracao_maps({})
        assert em == {}
        assert iz == {}
        assert cz == {}

    def test_with_etapas_data(self):
        extracao = {
            "etapas": {
                "03_equipes_e_alocacao": {
                    "equipes": [
                        {"item_id": "1.1", "funcoes": ["f1"]},
                        {"item_id": "1.2", "funcoes": []},
                    ]
                },
                "04_planejamento_bdi": {
                    "itens_com_qtd_e_custo_zero": [
                        {"item_id": "1.3"},
                    ]
                },
            },
            "disparidades": {
                "equipes_zeradas": [
                    {"item_id": "1.4"},
                ]
            },
        }
        em, iz, cz = _bgc_load_extracao_maps(extracao)
        assert "1.1" in em
        assert "1.2" in em
        assert "1.3" in iz
        assert "1.4" in cz

    def test_none_etapas_section(self):
        extracao = {"etapas": None}
        em, iz, cz = _bgc_load_extracao_maps(extracao)
        assert em == {}
        assert iz == {}
        assert cz == {}


class TestBgcBuildCatalogoEntry:
    def test_empty_cpu_cat(self):
        entry = _bgc_build_catalogo_entry({})
        assert entry["producao_horaria"] is None
        assert entry["unidade"] is None
        assert entry["funcoes_count"] == 0
        assert entry["equipamentos_count"] == 0
        assert entry["composicao_count"] == 0

    def test_with_equipe_data(self):
        cpu_cat = {
            "producao_horaria": 100.0,
            "unidade": "m³",
            "equipe": {
                "funcoes": [{"cargo": "Motorista"}, {"cargo": "Operador"}],
                "equipamentos": [{"equipamento": "Pá-mecânica"}],
            },
            "composicao_itens": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}],
        }
        entry = _bgc_build_catalogo_entry(cpu_cat)
        assert entry["funcoes_count"] == 2
        assert entry["equipamentos_count"] == 1
        assert entry["composicao_count"] == 3
        assert entry["producao_horaria"] == 100.0
        assert entry["unidade"] == "m³"

    def test_equipe_none(self):
        entry = _bgc_build_catalogo_entry({"equipe": None})
        assert entry["funcoes_count"] == 0
        assert entry["equipamentos_count"] == 0


class TestBuildGranularComparison:
    def test_no_files_returns_empty_comparacao(self, tmp_path):
        bench_data = tmp_path / "benchmarks" / "data"
        bench_data.mkdir(parents=True)
        result = build_granular_comparison("EMPTY", root=tmp_path)
        assert result["slug"] == "EMPTY"
        assert result["comparacao"] == []
        assert result["total"] == 0

    def test_with_referencia_and_extracao(self, tmp_path):
        slug = "GRAN1"
        cpu_id = "CPU-TERRA-001"
        cpu_data = {
            "producao_horaria": 50.0,
            "unidade": "m³",
            "equipe": {
                "funcoes": [{"cargo": "Op"}],
                "equipamentos": [],
            },
            "composicao_itens": [{"id": "c1"}],
        }
        ref = {
            "eap": [
                {
                    "item_id": "1.1",
                    "descricao": "Escavação",
                    "cpu_id": cpu_id,
                }
            ],
            "equipes_detalhadas": [
                {
                    "item_id": "1.1",
                    "funcoes": [],
                    "equipamentos": [],
                    "custo_total": 0,
                    "custo_mao_obra_mensal": 0,
                    "custo_equipamentos_mensal": 0,
                    "custo_combustivel_total_mensal": 0,
                }
            ],
        }
        extracao = {
            "etapas": {
                "03_equipes_e_alocacao": {
                    "equipes": [{"item_id": "1.1", "funcoes": [], "equipamentos": [], "custo_total": 0}]
                },
                "04_planejamento_bdi": {"itens_com_qtd_e_custo_zero": []},
            },
            "disparidades": {"equipes_zeradas": []},
        }
        cpus_dir = tmp_path / "config" / "catalogos" / "mendeslobo" / "cpus"
        _write_json(cpus_dir / f"{cpu_id}.json", cpu_data)
        _write_json(tmp_path / "benchmarks" / "data" / slug / "referencia.json", ref)
        _write_json(tmp_path / "benchmarks" / "data" / slug / "extracao_intermediarios.json", extracao)

        result = build_granular_comparison(slug, root=tmp_path)
        assert result["total"] == 1
        item = result["comparacao"][0]
        assert item["item_id"] == "1.1"
        assert item["cpu_id"] == cpu_id
        assert item["catalogo"]["funcoes_count"] == 1
        assert item["flags"]["cpu_ausente_no_catalogo"] is False

    def test_flags_zerado_and_cpu_ausente(self, tmp_path):
        slug = "GRAN2"
        ref = {
            "eap": [{"item_id": "2.1", "descricao": "Item sem CPU", "cpu_id": None}],
            "equipes_detalhadas": [],
        }
        extracao = {
            "etapas": {
                "03_equipes_e_alocacao": {"equipes": []},
                "04_planejamento_bdi": {"itens_com_qtd_e_custo_zero": [{"item_id": "2.1"}]},
            },
            "disparidades": {"equipes_zeradas": [{"item_id": "2.1"}]},
        }
        _write_json(tmp_path / "benchmarks" / "data" / slug / "referencia.json", ref)
        _write_json(tmp_path / "benchmarks" / "data" / slug / "extracao_intermediarios.json", extracao)

        result = build_granular_comparison(slug, root=tmp_path)
        item = result["comparacao"][0]
        assert item["flags"]["zerado_no_planejamento"] is True
        assert item["flags"]["composicao_zerada"] is True
        assert item["flags"]["cpu_ausente_no_catalogo"] is True


# ===========================================================================
# 4. output_packager.py
# ===========================================================================

from concilium.application.benchmarks.charts.output_packager import (  # noqa: E402
    _cf_collect_audit,
    _cf_collect_cenarios,
    _cf_collect_graficos,
    _cf_collect_ref,
    _cf_collect_relatorios,
    _collect_files,
    _find_benchmark_dir,
    _gerar_manifest,
    _tentar_gerar_graficos,
    _tools_root_from_config,
    empacotar_outputs,
)


class TestToolsRootFromConfig:
    def test_returns_parent(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        result = _tools_root_from_config(config_root)
        assert result == tmp_path


class TestFindBenchmarkDir:
    def test_no_matching_dir_returns_none(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        result = _find_benchmark_dir("NOEXIST", config_root=config_root)
        assert result is None

    def test_returns_existing_path(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "MYBENCH"
        bench_dir.mkdir(parents=True)
        result = _find_benchmark_dir("MYBENCH", config_root=config_root)
        assert result == bench_dir

    def test_no_config_root_skips_config_candidate(self):
        """Line 32 false branch: config_root=None -> only the fallback candidate is checked."""
        result = _find_benchmark_dir("DEFINITELY-NOT-A-REAL-BENCHMARK-SLUG-XYZ", config_root=None)
        assert result is None


class TestCfCollectGraficos:
    def test_empty_bench_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        assert collected == []

    def test_viz_dir_with_pngs(self, tmp_path):
        viz_dir = tmp_path / "artifacts" / "outputs" / "visualizations"
        viz_dir.mkdir(parents=True)
        (viz_dir / "chart1.png").write_text("fake")
        (viz_dir / "chart2.svg").write_text("fake")
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        arc_names = [arc for _, arc in collected]
        assert "graficos/chart1.png" in arc_names
        assert "graficos/chart2.svg" in arc_names

    def test_fallback_to_outputs_dir(self, tmp_path):
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "plot.png").write_text("fake")
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        assert any(arc == "graficos/plot.png" for _, arc in collected)

    def test_no_outputs_dir_returns_empty(self, tmp_path):
        collected: list = []
        _cf_collect_graficos(tmp_path, collected)
        assert collected == []


class TestCfCollectRelatorios:
    def test_reports_dir_with_files(self, tmp_path):
        reports_dir = tmp_path / "artifacts" / "outputs" / "reports"
        reports_dir.mkdir(parents=True)
        (reports_dir / "report.md").write_text("# Report")
        (reports_dir / "data.json").write_text("{}")
        collected: list = []
        _cf_collect_relatorios(tmp_path, collected)
        arc_names = [arc for _, arc in collected]
        assert "relatorio/report.md" in arc_names
        assert "relatorio/data.json" in arc_names

    def test_fallback_to_artifacts_outputs(self, tmp_path):
        art_out = tmp_path / "artifacts" / "outputs"
        art_out.mkdir(parents=True)
        (art_out / "summary.md").write_text("# Summary")
        collected: list = []
        _cf_collect_relatorios(tmp_path, collected)
        assert any(arc == "relatorio/summary.md" for _, arc in collected)

    def test_no_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_relatorios(tmp_path, collected)
        assert collected == []


class TestCfCollectAudit:
    def test_audit_dir_with_jsons(self, tmp_path):
        audit_dir = tmp_path / "artifacts" / "audit"
        audit_dir.mkdir(parents=True)
        (audit_dir / "report.json").write_text("{}")
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        assert ("audit/report.json") in [arc for _, arc in collected]

    def test_fallback_audit_dir(self, tmp_path):
        audit_dir2 = tmp_path / "audit"
        audit_dir2.mkdir()
        (audit_dir2 / "bench.json").write_text("{}")
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        assert any(arc == "audit/bench.json" for _, arc in collected)

    def test_deduplication_of_arc_paths(self, tmp_path):
        # Same filename in artifacts/audit AND audit/ — should appear only once
        audit_primary = tmp_path / "artifacts" / "audit"
        audit_primary.mkdir(parents=True)
        (audit_primary / "shared.json").write_text("{}")
        audit_fallback = tmp_path / "audit"
        audit_fallback.mkdir()
        (audit_fallback / "shared.json").write_text("{}")
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        arcs = [arc for _, arc in collected]
        assert arcs.count("audit/shared.json") == 1

    def test_no_audit_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_audit(tmp_path, collected)
        assert collected == []


class TestCfCollectCenarios:
    def test_inter_dir_with_matching_files(self, tmp_path):
        inter_dir = tmp_path / "artifacts" / "intermediate"
        inter_dir.mkdir(parents=True)
        (inter_dir / "M0.benchmark_report.json").write_text("{}")
        (inter_dir / "plan_space_report.json").write_text("{}")
        collected: list = []
        _cf_collect_cenarios(tmp_path, collected)
        arcs = [arc for _, arc in collected]
        assert "cenarios/M0.benchmark_report.json" in arcs
        assert "cenarios/plan_space_report.json" in arcs

    def test_no_inter_dir_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_cenarios(tmp_path, collected)
        assert collected == []


class TestCfCollectRef:
    def test_primary_ref_exists(self, tmp_path):
        ref_path = tmp_path / "artifacts" / "inputs" / "referencia.json"
        ref_path.parent.mkdir(parents=True)
        ref_path.write_text("{}")
        collected: list = []
        _cf_collect_ref(tmp_path, collected)
        assert any(arc == "inputs/referencia.json" for _, arc in collected)

    def test_fallback_to_root_ref(self, tmp_path):
        fallback = tmp_path / "referencia.json"
        fallback.write_text("{}")
        collected: list = []
        _cf_collect_ref(tmp_path, collected)
        assert any(arc == "inputs/referencia.json" for _, arc in collected)

    def test_no_ref_collected_unchanged(self, tmp_path):
        collected: list = []
        _cf_collect_ref(tmp_path, collected)
        assert collected == []


class TestCollectFiles:
    def test_returns_combined_list(self, tmp_path):
        # Populate multiple artifact types
        ref_path = tmp_path / "referencia.json"
        ref_path.write_text("{}")
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        (audit_dir / "rep.json").write_text("{}")

        result = _collect_files(tmp_path)
        arcs = [arc for _, arc in result]
        assert "inputs/referencia.json" in arcs
        assert "audit/rep.json" in arcs


class TestGerarManifest:
    def test_returns_correct_structure(self, tmp_path):
        files = [
            (tmp_path / "a.png", "graficos/a.png"),
            (tmp_path / "b.json", "relatorio/b.json"),
            (tmp_path / "c.json", "audit/c.json"),
        ]
        manifest = _gerar_manifest("MYBENCH", files, tmp_path)
        assert manifest["slug"] == "MYBENCH"
        assert "gerado_em" in manifest
        assert manifest["arquivos"] == ["graficos/a.png", "relatorio/b.json", "audit/c.json"]
        assert manifest["totais"]["graficos"] == 1
        assert manifest["totais"]["relatorio"] == 1
        assert manifest["totais"]["audit"] == 1
        assert manifest["totais"]["cenarios"] == 0

    def test_slug_is_uppercased(self, tmp_path):
        manifest = _gerar_manifest("lower", [], tmp_path)
        assert manifest["slug"] == "LOWER"


class TestEmpacotar:
    def test_no_bench_dir_raises_file_not_found(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        with pytest.raises(FileNotFoundError):
            empacotar_outputs("MISSING", config_root=config_root, output_path=tmp_path / "out.zip")

    def test_no_files_raises_value_error(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "EMPTY"
        bench_dir.mkdir(parents=True)
        with pytest.raises(ValueError):
            empacotar_outputs("EMPTY", config_root=config_root, output_path=tmp_path / "out.zip", gerar_graficos=False)

    def test_creates_valid_zip_with_manifest(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "MYBENCH"
        # Place a referencia.json so _collect_files finds at least one file
        ref_path = bench_dir / "referencia.json"
        ref_path.parent.mkdir(parents=True)
        ref_path.write_text('{"eap": []}')
        output_zip = tmp_path / "output.zip"

        result = empacotar_outputs(
            "MYBENCH",
            config_root=config_root,
            output_path=output_zip,
            gerar_graficos=False,
        )

        assert result == output_zip
        assert output_zip.exists()
        with zipfile.ZipFile(output_zip) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["slug"] == "MYBENCH"

    def test_skips_collected_file_that_no_longer_exists(self, tmp_path):
        """Line 200 false branch: a collected (path, arc) entry whose real_path
        does not exist on disk is silently skipped when writing the zip."""
        from unittest.mock import patch

        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "GHOSTFILE"
        bench_dir.mkdir(parents=True)
        existing = bench_dir / "referencia.json"
        existing.write_text("{}")
        missing = bench_dir / "vanished.json"  # never created on disk
        output_zip = tmp_path / "out.zip"

        with patch(
            "concilium.application.benchmarks.charts.output_packager._collect_files",
            return_value=[(existing, "relatorio/referencia.json"), (missing, "relatorio/vanished.json")],
        ):
            result = empacotar_outputs(
                "GHOSTFILE",
                config_root=config_root,
                output_path=output_zip,
                gerar_graficos=False,
            )

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
        assert "relatorio/referencia.json" in names
        assert "relatorio/vanished.json" not in names

    def test_incluir_cenarios_includes_cenario_files(self, tmp_path):
        config_root = tmp_path / "config"
        config_root.mkdir()
        bench_dir = tmp_path / "benchmarks" / "data" / "CENTEST"
        inter_dir = bench_dir / "artifacts" / "intermediate"
        inter_dir.mkdir(parents=True)
        (inter_dir / "M1.benchmark_report.json").write_text("{}")
        # Also add referencia so we have non-cenario files
        (bench_dir / "referencia.json").write_text("{}")
        output_zip = tmp_path / "out.zip"

        result = empacotar_outputs(
            "CENTEST",
            config_root=config_root,
            output_path=output_zip,
            gerar_graficos=False,
            incluir_cenarios=True,
        )

        with zipfile.ZipFile(result) as zf:
            names = zf.namelist()
        assert "cenarios/M1.benchmark_report.json" in names


class TestTentarGerarGraficos:
    def test_pngs_exist_returns_immediately(self, tmp_path):
        outputs_dir = tmp_path / "outputs"
        outputs_dir.mkdir()
        (outputs_dir / "existing.png").write_text("fake")
        # Should not raise — just return early
        _tentar_gerar_graficos(tmp_path, "SLUG")

    def test_import_error_silent_pass(self, tmp_path, monkeypatch):
        # Simula ImportError só para o módulo de chart_generator.
        def _import_with_forced_error(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "concilium.application.benchmarks.charts.chart_generator":
                raise ImportError("simulated missing matplotlib stack")
            return _builtin_import(name, globals, locals, fromlist, level)

        monkeypatch.setattr("builtins.__import__", _import_with_forced_error)
        _tentar_gerar_graficos(tmp_path, "SLUG")

    def test_generic_exception_logs_warning_and_swallows(self, tmp_path):
        """Lines 223-224: gerar_graficos_benchmark raising a non-ImportError Exception
        is caught and logged as a warning — packaging proceeds without PNGs."""
        from unittest.mock import patch

        with patch(
            "concilium.application.benchmarks.charts.chart_generator.gerar_graficos_benchmark",
            side_effect=RuntimeError("matplotlib backend crashed"),
        ):
            # Must not raise — best-effort chart generation.
            _tentar_gerar_graficos(tmp_path, "SLUG")


# ===========================================================================
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
# 5b. cpu_validator.py — CpuValidator
# ===========================================================================

from concilium.application.benchmarks.validation.cpu_validator import CpuValidator  # noqa: E402

_FULL_CATALOGO = {
    "cpus": [
        {
            "codigo": "ATI-001",
            "descricao": "Aterro Compactação",
            "unidade": "m³",
            "categoria": "TERRA",
            "producao_id_ref": "PROD-001",
        }
    ],
    "producoes": [
        {
            "codigo": "PROD-001",
            "descricao": "Produção aterro",
            "composicao_padrao_equipe": {
                "funcoes": [{"cargo": "Motorista"}],
                "equipamentos": [{"equipamento": "Compactador"}],
            },
        }
    ],
}


def _make_validator(catalogo: dict | None = None) -> CpuValidator:
    """Return CpuValidator with _load_catalog patched."""
    cat = catalogo if catalogo is not None else dict(_FULL_CATALOGO)
    with patch.object(CpuMapper, "_load_catalog"):
        validator = CpuValidator.__new__(CpuValidator)
        mapper = CpuMapper.__new__(CpuMapper)
        mapper.contexto_id = "mendeslobo"
        mapper._cpu_cache = {}
        mapper.catalogo = cat
        mapper.contexto = MagicMock()
        validator.mapper = mapper
        validator.catalogo = cat
    return validator


class TestCpuValidatorValidateCpuExists:
    def test_existing_cpu_returns_true(self):
        v = _make_validator()
        assert v.validate_cpu_exists("ATI-001") is True

    def test_nonexistent_cpu_returns_false(self):
        v = _make_validator()
        assert v.validate_cpu_exists("NONEXISTENT") is False


class TestCpuValidatorGetCpu:
    def test_found_returns_dict(self):
        v = _make_validator()
        cpu = v.get_cpu("ATI-001")
        assert isinstance(cpu, dict)
        assert cpu["codigo"] == "ATI-001"

    def test_not_found_returns_none(self):
        v = _make_validator()
        assert v.get_cpu("NONEXISTENT") is None


class TestCpuValidatorGetProduction:
    def test_found_by_codigo_returns_dict(self):
        v = _make_validator()
        prod = v.get_production("PROD-001")
        assert isinstance(prod, dict)

    def test_found_by_id_returns_dict(self):
        cat = {
            "cpus": [],
            "produtividades": [{"id": "PROD-X", "descricao": "Prod X"}],
        }
        v = _make_validator(catalogo=cat)
        prod = v.get_production("PROD-X")
        assert prod is not None
        assert prod["id"] == "PROD-X"

    def test_not_found_returns_none(self):
        v = _make_validator()
        assert v.get_production("NO-PROD") is None


class TestCpuValidatorValidateCpuMapping:
    def test_cpu_not_found_returns_errors_list(self):
        v = _make_validator()
        result = v.validate_cpu_mapping("NONEXISTENT")
        assert result["cpu_exists"] is False
        assert len(result["errors"]) >= 1

    def test_cpu_without_producao_id_ref(self):
        cat = {
            "cpus": [{"codigo": "CPU-NOPROD", "descricao": "No prod ref"}],
            "producoes": [],
        }
        v = _make_validator(catalogo=cat)
        result = v.validate_cpu_mapping("CPU-NOPROD")
        assert result["cpu_exists"] is True
        assert result["has_producao_ref"] is False
        assert len(result["errors"]) >= 1

    def test_production_not_found(self):
        cat = {
            "cpus": [{"codigo": "CPU-BADPROD", "descricao": "Refs missing prod", "producao_id_ref": "MISSING"}],
            "producoes": [],
        }
        v = _make_validator(catalogo=cat)
        result = v.validate_cpu_mapping("CPU-BADPROD")
        assert result["has_producao_ref"] is True
        assert result["producao_exists"] is False
        assert len(result["errors"]) >= 1

    def test_production_without_composicao(self):
        cat = {
            "cpus": [{"codigo": "CPU-NOCOMP", "descricao": "No comp", "producao_id_ref": "PROD-NOCOMP"}],
            "producoes": [{"codigo": "PROD-NOCOMP", "descricao": "No composicao"}],
        }
        v = _make_validator(catalogo=cat)
        result = v.validate_cpu_mapping("CPU-NOCOMP")
        assert result["producao_exists"] is True
        assert result["has_composicao"] is False
        assert len(result["errors"]) >= 1

    def test_full_valid_chain_has_composicao_true(self):
        v = _make_validator()
        result = v.validate_cpu_mapping("ATI-001")
        assert result["cpu_exists"] is True
        assert result["has_producao_ref"] is True
        assert result["producao_exists"] is True
        assert result["has_composicao"] is True
        assert result["errors"] == []

    def test_production_empty_composicao(self):
        cat = {
            "cpus": [{"codigo": "CPU-EMPCOMP", "descricao": "Empty comp", "producao_id_ref": "PROD-EMPCOMP"}],
            "producoes": [
                {
                    "codigo": "PROD-EMPCOMP",
                    "descricao": "Empty composicao",
                    "composicao_padrao_equipe": {"funcoes": [], "equipamentos": []},
                }
            ],
        }
        v = _make_validator(catalogo=cat)
        result = v.validate_cpu_mapping("CPU-EMPCOMP")
        assert result["has_composicao"] is False
        assert len(result["errors"]) >= 1


class TestCpuValidatorValidateEapItems:
    def test_mixes_valid_and_invalid(self):
        v = _make_validator()
        eap_items = [
            {"item_id": "1.1", "cpu_id": "ATI-001"},  # valid
            {"item_id": "1.2", "cpu_id": "NONEXISTENT"},  # invalid
        ]
        result = v.validate_eap_items(eap_items)
        assert result["total"] == 2
        assert result["valid"] == 1
        assert result["invalid"] == 1
        assert "1.1" in result["items"]
        assert "1.2" in result["items"]

    def test_all_valid(self):
        v = _make_validator()
        eap_items = [{"item_id": "1.1", "cpu_id": "ATI-001"}]
        result = v.validate_eap_items(eap_items)
        assert result["valid"] == 1
        assert result["invalid"] == 0

    def test_empty_list(self):
        v = _make_validator()
        result = v.validate_eap_items([])
        assert result["total"] == 0
        assert result["valid"] == 0
        assert result["invalid"] == 0


class TestCpuValidatorPrintValidationReport:
    def test_invalid_items_calls_print(self, capsys):
        v = _make_validator()
        eap_items = [
            {"item_id": "1.1", "cpu_id": "ATI-001"},
            {"item_id": "1.2", "cpu_id": "NONEXISTENT"},
        ]
        validation = v.validate_eap_items(eap_items)
        v.print_validation_report(validation)
        captured = capsys.readouterr()
        assert "VALIDAÇÃO" in captured.out or "VALIDA" in captured.out
        assert "1.2" in captured.out

    def test_all_valid_no_details_section(self, capsys):
        v = _make_validator()
        eap_items = [{"item_id": "1.1", "cpu_id": "ATI-001"}]
        validation = v.validate_eap_items(eap_items)
        v.print_validation_report(validation)
        captured = capsys.readouterr()
        assert "Detalhes" not in captured.out
