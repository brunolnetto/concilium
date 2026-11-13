"""EAP DAG validation accepts typed predecessors (NEP-031), not only ids."""

from __future__ import annotations

import pytest

from concilium.domain.models.canonical import EapItem
from concilium.domain.services.eap_dag_validator import CicloPredecessaoError, validar_dag_predecessores


def _item(item_id: str, predecessores: list) -> EapItem:
    return EapItem(item_id=item_id, cpu_id="CPU-X", quantitativo=1.0, predecessores=predecessores)


def test_typed_q_fs_predecessor_is_accepted() -> None:
    """Upserting an EAP with a typed FS theta=0.5 predecessor crashed with
    `unhashable type: 'PrecedenciaItem'` before."""
    validar_dag_predecessores([
        _item("A", []),
        _item("B", [{"item_id": "A", "tipo": "FS", "lag": 0, "completion_threshold_pct": 0.5}]),
        _item("C", ["B"]),
    ])


def test_typed_unknown_predecessor_is_named() -> None:
    with pytest.raises(ValueError, match="inexistentes.*ZZ"):
        validar_dag_predecessores([_item("A", [{"item_id": "ZZ", "tipo": "SS", "lag": 1}])])


def test_cycle_through_typed_predecessors_is_detected() -> None:
    with pytest.raises(CicloPredecessaoError):
        validar_dag_predecessores([
            _item("A", [{"item_id": "B", "tipo": "FS"}]),
            _item("B", ["A"]),
        ])
