"""A single installed F(m) and an independently auditable availability calendar."""
from __future__ import annotations

import sys
from importlib import import_module
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from concilium.application.skills import run_cronograma as _run_cronograma
from concilium.domain.models.canonical import DistribuicaoSemanal

assert _run_cronograma
_skill = sys.modules["_concilium_skillpkg_04_cronograma.skill"]
_costs = import_module(_skill._build_dist_cell.__module__)


def _cell(**overrides: object) -> DistribuicaoSemanal:
    data: dict[str, object] = dict(
        producao_semanal_base=200.0,
        num_eq=2,
        n_max=4,
        fator_clima=0.75,
        fator_calendario=0.8,
        fator_jornada=1.0,
        quantitativo=300.0,
        qtd_acumulada=0.0,
        capacidade_fisica_semanal=800.0,
        horas_contratuais_semana=40.0,
        origem_produtividade="GRAFO_FLUXO",
    )
    data.update(overrides)
    return _skill._build_dist_cell(**data)


def test_one_rate_calendar_and_partial_closure_auditable_without_double_penalty() -> None:
    cell = _cell()
    assert cell.produtividade_fisica_horaria == 20.0  # F(m)=800/40h
    assert cell.horas_contratuais_semana == 40.0
    assert cell.q_max_celula == 800.0  # physical installed output, before climate
    assert cell.capacidade_disponivel_semana == pytest.approx(480.0)  # 800 * 0.75 * 0.8
    assert cell.qtd_executada == 300.0
    assert cell.fracao_fechamento == pytest.approx(300.0 / 480.0)
    assert cell.perda_fisica == pytest.approx(320.0)
    assert cell.eta_s == cell.eta_w == cell.eficiencia == 1.0
    assert cell.desempenho_observado == "NAO_OBSERVADO"
    assert cell.estado_calibracao == "NAO_CERTIFICADA"
    assert cell.origem_produtividade == "GRAFO_FLUXO"


def test_zero_practicability_preserves_installed_rate_and_zero_available_capacity() -> None:
    cell = _cell(fator_clima=0.0)
    assert cell.produtividade_fisica_horaria == 20.0
    assert cell.q_max_celula == 800.0
    assert cell.capacidade_disponivel_semana == 0.0
    assert cell.qtd_executada == 0.0
    assert cell.fracao_fechamento == 0.0
    assert cell.estado_calibracao == "NAO_CERTIFICADA"


def test_fallback_is_explicitly_not_a_proven_productivity() -> None:
    classify = _costs._origem_capacidade
    assert classify(None, is_fallback=True) == "FALLBACK_ARBITRARIO"
    assert classify(None, is_fallback=False) == "TAXA_POR_FRENTE_ASSUMIDA"
    assert classify({"grafo_sinergia": {"arestas_fluxo": [{"origem": "a"}]}}) == "GRAFO_FLUXO"
    assert classify({"grafo_sinergia": {"dominio": ["a", "b"]}}) == "GRAFO_ELEMENTOS"
    cell = _cell(origem_produtividade="FALLBACK_ARBITRARIO")
    assert cell.origem_produtividade == "FALLBACK_ARBITRARIO"
    assert cell.estado_calibracao == "NAO_CERTIFICADA"


def test_old_persisted_cells_do_not_invent_calibration_or_observations() -> None:
    previous = DistribuicaoSemanal(
        num_equipes=2, qtd_executada=100, qtd_acumulada=100, pct=1,
    )
    assert previous.produtividade_fisica_horaria is None
    assert previous.capacidade_disponivel_semana is None
    assert previous.horas_contratuais_semana is None
    assert previous.origem_produtividade == "NAO_DECLARADA"
    assert previous.desempenho_observado == "NAO_OBSERVADO"
    assert previous.estado_calibracao == "NAO_CERTIFICADA"
    restored = DistribuicaoSemanal.model_validate(previous.model_dump())
    assert restored == previous


@pytest.mark.parametrize("hours", [0.0, -1.0, float("nan"), float("inf")])
def test_bad_contractual_hours_rejected_before_capacity_inference(hours: float) -> None:
    with pytest.raises(ValueError, match="contractual weekly hours"):
        _cell(horas_contratuais_semana=hours)


def test_invalid_source_or_nonfinite_rate_rejected_by_schema() -> None:
    cell = _cell()
    data = cell.model_dump()
    data["origem_produtividade"] = "PRODUTIVIDADE_AJUSTADA_PELA_CHUVA"
    with pytest.raises(ValidationError):
        DistribuicaoSemanal.model_validate(data)
    data = cell.model_dump()
    data["produtividade_fisica_horaria"] = float("inf")
    with pytest.raises(ValidationError):
        DistribuicaoSemanal.model_validate(data)



def _manual_cell(cpu: dict[str, object]) -> tuple[DistribuicaoSemanal, bool]:
    validacao = import_module(_costs.__package__ + "._validacao")
    item = SimpleNamespace(item_id="activity", quantitativo=300.0)
    regime = SimpleNamespace(horas_dia=8.0, dias_semana=5.0, eta_jornada=1.0)
    dist, errors, gaps, is_fallback = validacao._emm_process_item(
        item,
        cpu,
        {},
        regime,
        {"2026-W01": 0.75},
        {},
        {"2026-W01": 0.8},
        ["2026-W01"],
        {"activity": {"2026-W01": 2.0}},
        [],
    )
    assert not errors
    assert not gaps
    return dist["2026-W01"], is_fallback


def test_manual_schedule_persists_single_rate_and_availability_provenance() -> None:
    cell, is_fallback = _manual_cell(
        {"codigo": "CPU-1", "cpu_meta": {"producao_horaria": 10.0}}
    )
    assert is_fallback is False
    assert cell.origem_produtividade == "TAXA_POR_FRENTE_ASSUMIDA"
    assert cell.produtividade_fisica_horaria == pytest.approx(20.0)
    assert cell.horas_contratuais_semana == pytest.approx(40.0)
    assert cell.q_max_celula == pytest.approx(800.0)
    assert cell.capacidade_disponivel_semana == pytest.approx(480.0)
    assert cell.qtd_executada == pytest.approx(300.0)
    assert cell.fracao_fechamento == pytest.approx(300 / 480)


def test_manual_schedule_identifies_uncalibrated_preview_fallback() -> None:
    cell, is_fallback = _manual_cell({"codigo": "CPU-MISSING-PROD"})
    assert is_fallback is True
    assert cell.origem_produtividade == "FALLBACK_ARBITRARIO"
    assert cell.estado_calibracao == "NAO_CERTIFICADA"
    assert cell.produtividade_fisica_horaria == pytest.approx(2000.0)
    assert cell.desempenho_observado == "NAO_OBSERVADO"
