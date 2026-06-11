"""Tests for ADR-063 — Project Type Discriminator.

Covers:
  F1: tipo_projeto field in meta; backward-compat with project_kind
  F2: EapItem.predecessores field; validar_dag_predecessores
  F3: PipelineStrategy dispatch; HotProjectStrategy / ProjectStrategy
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from concilium.application.pipeline_strategy import (
    HotProjectStrategy,
    ProjectStrategy,
    get_pipeline_strategy,
)
from concilium.domain.models.canonical import EapItem
from concilium.domain.services.eap_dag_validator import (
    CicloPredecessaoError,
    validar_dag_predecessores,
)

# ─── F2: EapItem.predecessores ───────────────────────────────────────────────


class TestEapItemPredecessores:
    def test_default_empty(self):
        item = EapItem(
            item_id="IT-001", ordem=1, cpu_id="CPU-A", descricao="Terraplenagem", unidade="m³", quantitativo=1000.0
        )
        assert item.predecessores == []

    def test_with_predecessores(self):
        item = EapItem(
            item_id="IT-002",
            ordem=2,
            cpu_id="CPU-B",
            descricao="Pavimentação",
            unidade="m²",
            quantitativo=500.0,
            predecessores=["IT-001"],
        )
        assert item.predecessores == ["IT-001"]

    def test_serialization_roundtrip(self):
        item = EapItem(
            item_id="IT-003",
            ordem=3,
            cpu_id="CPU-C",
            descricao="Drenagem",
            unidade="m",
            quantitativo=200.0,
            predecessores=["IT-001", "IT-002"],
        )
        dumped = item.model_dump()
        restored = EapItem.model_validate(dumped)
        assert restored.predecessores == ["IT-001", "IT-002"]

    def test_rejects_negative_quantitativo(self):
        with pytest.raises(ValidationError):
            EapItem(item_id="IT-001", ordem=1, cpu_id="CPU-A", descricao="X", unidade="m³", quantitativo=-1.0)


# ─── F2: DAG validation ───────────────────────────────────────────────────────


def _make_item(item_id: str, preds: list[str] | None = None) -> EapItem:
    return EapItem(
        item_id=item_id,
        ordem=1,
        cpu_id="CPU-A",
        descricao=item_id,
        unidade="m³",
        quantitativo=1.0,
        predecessores=preds or [],
    )


class TestValidarDagPredecessores:
    def test_empty_eap_valid(self):
        validar_dag_predecessores([])  # no raise

    def test_linear_chain_valid(self):
        eap = [
            _make_item("A"),
            _make_item("B", ["A"]),
            _make_item("C", ["B"]),
        ]
        validar_dag_predecessores(eap)  # no raise

    def test_diamond_dag_valid(self):
        eap = [
            _make_item("A"),
            _make_item("B", ["A"]),
            _make_item("C", ["A"]),
            _make_item("D", ["B", "C"]),
        ]
        validar_dag_predecessores(eap)  # no raise

    def test_simple_cycle_raises(self):
        eap = [
            _make_item("A", ["B"]),
            _make_item("B", ["A"]),
        ]
        with pytest.raises(CicloPredecessaoError):
            validar_dag_predecessores(eap)

    def test_self_loop_raises(self):
        eap = [_make_item("A", ["A"])]
        with pytest.raises(CicloPredecessaoError):
            validar_dag_predecessores(eap)

    def test_long_cycle_raises(self):
        eap = [
            _make_item("A", ["C"]),
            _make_item("B", ["A"]),
            _make_item("C", ["B"]),
        ]
        with pytest.raises(CicloPredecessaoError):
            validar_dag_predecessores(eap)

    def test_unknown_predecessor_raises(self):
        eap = [_make_item("A", ["NONEXISTENT"])]
        with pytest.raises(ValueError, match="inexistentes"):
            validar_dag_predecessores(eap)


# ─── F3: PipelineStrategy ─────────────────────────────────────────────────────


class _FakeProject:
    """Minimal ProjectHandle stub for strategy tests."""

    def __init__(self, tipo_projeto: str, status_eap: str = "ATIVO"):
        self._tipo = tipo_projeto
        self._status = status_eap

    @property
    def tipo_projeto(self) -> str:
        return self._tipo

    @property
    def status_eap(self) -> str:
        return self._status


class TestHotProjectStrategy:
    def test_validate_preconditions_always_passes(self):
        s = HotProjectStrategy()
        s.validate_preconditions(_FakeProject("hot_project", "ATIVO"))  # no raise
        s.validate_preconditions(_FakeProject("hot_project", "RASCUNHO"))  # no raise even for rascunho

    def test_skill_sequence_nonempty(self):
        skills = HotProjectStrategy().skill_sequence()
        assert len(skills) > 0
        assert "01-escopo-e-eap" in skills
        assert "06-resultado-financeiro" in skills  # NEP-041 F4


class TestProjectStrategy:
    def test_validate_rascunho_pronto_ok(self):
        s = ProjectStrategy()
        s.validate_preconditions(_FakeProject("project", "RASCUNHO_PRONTO"))  # no raise

    def test_validate_ativo_ok(self):
        s = ProjectStrategy()
        s.validate_preconditions(_FakeProject("project", "ATIVO"))  # no raise

    def test_validate_rascunho_raises(self):
        s = ProjectStrategy()
        with pytest.raises(ValueError, match="RASCUNHO_PRONTO"):
            s.validate_preconditions(_FakeProject("project", "RASCUNHO"))

    def test_skill_sequence_nonempty(self):
        skills = ProjectStrategy().skill_sequence()
        assert len(skills) > 0


class TestGetPipelineStrategy:
    def test_hot_project_returns_hot_strategy(self):
        strategy = get_pipeline_strategy(_FakeProject("hot_project"))
        assert isinstance(strategy, HotProjectStrategy)

    def test_project_returns_project_strategy(self):
        strategy = get_pipeline_strategy(_FakeProject("project"))
        assert isinstance(strategy, ProjectStrategy)

    def test_unknown_type_defaults_to_hot(self):
        strategy = get_pipeline_strategy(_FakeProject("unknown_type"))
        assert isinstance(strategy, HotProjectStrategy)
