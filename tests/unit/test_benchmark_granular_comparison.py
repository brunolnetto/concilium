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

