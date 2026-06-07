from __future__ import annotations

import pytest

from concilium.application.services.project_service import ProjectService
from concilium.presentation.ui.helpers.helpers import extract_bdi_dict, extract_eap_items_for_policy, safe_count_eap


def _svc() -> ProjectService:
    return object.__new__(ProjectService)


def test_validate_benchmark_reference_contract_accepts_canonical_block() -> None:
    payload = {
        "cpus": {
            "itens_eap": [
                {
                    "item_id": "A1",
                    "cpu_id": "CPU-001",
                    "descricao": "Escavacao",
                    "unidade": "m3",
                    "quantitativo": 120.0,
                }
            ]
        }
    }

    _svc()._validate_benchmark_reference_contract(payload)

    itens = (payload.get("cpus") or {}).get("itens_eap")
    assert isinstance(itens, list)
    assert len(itens) == 1
    assert itens[0]["item_id"] == "A1"
    assert itens[0]["cpu_id"] == "CPU-001"
    assert itens[0]["ordem"] == 1


def test_validate_benchmark_reference_contract_filters_invalid_and_duplicate_rows() -> None:
    payload = {
        "cpus": {
            "itens_eap": [
                {"item_id": "A1", "cpu_id": "CPU-001", "quantitativo": 10},
                {"item_id": "A1", "cpu_id": "CPU-002", "quantitativo": 20},
                {"item_id": "A2", "quantitativo": 30},
                {"cpu_id": "CPU-003", "quantitativo": 40},
                {"item_id": "A3", "cpu_id": "CPU-003", "quantitativo": 50},
            ]
        }
    }

    _svc()._validate_benchmark_reference_contract(payload)

    itens = (payload.get("cpus") or {}).get("itens_eap")
    assert isinstance(itens, list)
    assert [row["item_id"] for row in itens] == ["A1", "A3"]
    assert [row["cpu_id"] for row in itens] == ["CPU-001", "CPU-003"]


@pytest.mark.parametrize(
    "historical_payload",
    [
        {"eap": [{"item_id": "L1", "cpu_id": "CPU-999"}]},
        {"skill_inputs": {"01-escopo-e-eap": {"eap": [{"item_id": "L2", "cpu_id": "CPU-998"}]}}},
        {"skill_inputs": {"01-escopo-e-eap": {"inputs_escopo": {"eap": [{"item_id": "L3", "cpu_id": "CPU-997"}]}}}},
    ],
)
def test_validate_benchmark_reference_contract_rejects_historical_eap_sources(
    historical_payload: dict,
) -> None:
    with pytest.raises(ValueError, match="VAL-CONTRACT-EAP-HISTORICO-BLOQUEADO"):
        _svc()._validate_benchmark_reference_contract(historical_payload)


def test_ui_helpers_read_only_canonical_eap_contract() -> None:
    canonical_ref = {
        "cpus": {
            "itens_eap": [
                {"item_id": "A1", "cpu_id": "CPU-001", "descricao": "Item 1", "quantitativo": 10},
                {"item_id": "A2", "cpu_id": "CPU-002", "descricao": "Item 2", "quantitativo": 20},
            ]
        }
    }

    historical_ref = {
        "eap": [{"item_id": "L1", "cpu_id": "CPU-999"}],
        "skill_inputs": {"01-escopo-e-eap": {"eap": [{"item_id": "L2", "cpu_id": "CPU-998"}]}},
    }

    assert safe_count_eap(canonical_ref) == 2
    assert len(extract_eap_items_for_policy(canonical_ref)) == 2

    assert safe_count_eap(historical_ref) == 0
    assert extract_eap_items_for_policy(historical_ref) == []


def test_extract_bdi_dict_keeps_only_canonical_keys() -> None:
    bdi_payload = {
        "bdi": {
            "mo": 0.15,
            "eq": 0.07,
            "mao_obra": 0.21,
            "equipamentos": 0.11,
        }
    }

    extracted = extract_bdi_dict(bdi_payload)

    assert extracted.get("mao_obra") == 0.21
    assert extracted.get("equipamentos") == 0.11
    assert "mo" not in extracted
    assert "eq" not in extracted
    assert extracted.get("material") is None
    assert extracted.get("indireto") is None
