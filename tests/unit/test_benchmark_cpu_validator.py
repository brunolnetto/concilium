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


# 5b. cpu_validator.py — CpuValidator
# ===========================================================================

from concilium.application.benchmarks.validation.cpu_mapper import CpuMapper  # noqa: E402
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

