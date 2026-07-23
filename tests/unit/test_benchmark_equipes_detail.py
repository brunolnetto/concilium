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




# equipes_detail.py lines 17-18: _load_json with invalid JSON → return {}
# ---------------------------------------------------------------------------


class TestEquipesDetailLoadJsonBadJson:
    def test_bad_json_returns_empty_dict(self, tmp_path):
        """Lines 17-18: invalid JSON → except branch → return {}."""
        from concilium.application.benchmarks.comparison.equipes_detail import _load_json

        bad_file = tmp_path / "cpu_bad.json"
        bad_file.write_text("{{invalid", encoding="utf-8")
        result = _load_json(bad_file)
        assert result == {}


# ---------------------------------------------------------------------------

