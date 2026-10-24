"""P14-B end-to-end guard: impossible physical schedule cannot be persisted."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from concilium.application.skills import run_cronograma
from concilium.domain.models.canonical import (
    CanonicalModel,
    Coordenadas,
    EapItem,
    Meta,
    Praticabilidade,
    Projeto,
    RegimeTrabalho,
)


def _canonical(percent: float) -> CanonicalModel:
    return CanonicalModel(
        meta=Meta(gerado_em=datetime.now(UTC), contexto_id="p14b-e2e"),
        projeto=Projeto(
            id="p14b",
            nome="test physical schedule",
            tipo_obra="terraplenagem",
            localizacao="test",
            coordenadas=Coordenadas(lat=-3.0, lng=-38.0),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio=date(2026, 6, 1),
            data_termino=date(2026, 7, 31),
            snapshot_catalogo_id="test",
            snapshot_perfil_id="test",
        ),
        eap=[
            EapItem(
                item_id="i1", ordem=1, cpu_id="CPU-TEST",
                descricao="work", unidade="m3", quantitativo=300.0,
            )
        ],
        praticabilidade=Praticabilidade(
            fonte="test",
            limiar_inviabilidade_mm=0,
            calculada_em=datetime.now(UTC),
            percentual_produtivo_mensal={"06": percent, "07": percent},
        ),
    )


def test_zero_practicability_blocks_canonical_schedule_and_price() -> None:
    """A genuine Skill 04 run must fail closed, not publish partial cronograma."""
    canonical = _canonical(0.0)
    result = run_cronograma(
        canonical,
        {"num_equipes_por_item": {"i1": {"2026-W23": 1}}},
        {},
    )
    assert result.has_errors
    assert result.canonical is canonical
    assert result.canonical.cronograma is None
    assert any(
        v.codigo == "VAL-CRON-01" and v.status == "ERRO"
        for v in result.validacoes
    )


def test_incomplete_scope_reports_validation_not_fake_extra_weeks() -> None:
    """Negative physical availability is never repaired with invented weeks."""
    canonical = _canonical(0.0)
    result = run_cronograma(
        canonical,
        {"num_equipes_por_item": {"i1": {"2026-W23": 1}}},
        {},
    )
    error = next(v for v in result.validacoes if v.codigo == "VAL-CRON-01")
    assert "Itens não completados" in error.mensagem
    assert result.canonical is canonical



def test_p14c_unknown_certification_intent_fails_before_schedule() -> None:
    canonical = _canonical(1.0)
    outcome = run_cronograma(
        canonical,
        {
            "certification_intent": "AUTO_GO",
            "num_equipes_por_item": {"i1": {"2026-W23": 1}},
        },
        {},
    )
    assert outcome.has_errors
    assert outcome.canonical is canonical
    assert any(v.codigo == "VAL-CRON-CERT-INTENT" for v in outcome.validacoes)


def test_p14c_certified_missing_fm_never_publishes_price_or_schedule() -> None:
    canonical = _canonical(1.0)
    outcome = run_cronograma(
        canonical,
        {
            "certification_intent": "CERTIFIED",
            "num_equipes_por_item": {"i1": {"2026-W23": 1}},
        },
        {},
    )
    assert outcome.has_errors
    assert any(
        v.codigo == "VAL-CRON-PROD-CERT" and v.status == "ERRO"
        for v in outcome.validacoes
    )
    assert outcome.canonical.cronograma is None
    assert outcome.canonical.resultado is None
    assert outcome.canonical.resultado_reconciliado is None


def test_p14c_preview_preserves_physical_feasibility_without_granting_certificate() -> None:
    canonical = _canonical(1.0)
    outcome = run_cronograma(
        canonical,
        {
            "certification_intent": "PREVIEW",
            "num_equipes_por_item": {"i1": {"2026-W23": 1}},
        },
        {},
    )
    assert any(
        v.codigo == "VAL-CRON-PROD-PREVIEW" and v.status == "AVISO"
        for v in outcome.validacoes
    )
    assert outcome.canonical.cronograma is not None
    assert outcome.canonical.cronograma.is_feasible is True



def _catalog_productivity(rate: float, *, field: str = "producao_horaria") -> dict:
    return {
        "cpus": [{"codigo": "CPU-TEST", "producao_id_ref": "PROD"}],
        "produtividades": [{"id": "PROD", field: rate}],
    }


@pytest.mark.parametrize("field", ["producao_horaria", "valor_horario"])
def test_p14c_field_renaming_without_provenance_does_not_certify(field: str) -> None:
    outcome = run_cronograma(
        _canonical(1.0),
        {"certification_intent": "CERTIFIED",
         "num_equipes_por_item": {"i1": {"2026-W23": 1}}},
        _catalog_productivity(1000.0, field=field),
    )
    assert outcome.has_errors
    assert any(v.codigo == "VAL-CRON-PROD-CERT" for v in outcome.validacoes)
    assert outcome.canonical.cronograma is None


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf")])
def test_p14c_invalid_declared_rate_fails_before_physical_scheduler(rate: float) -> None:
    outcome = run_cronograma(
        _canonical(1.0),
        {"certification_intent": "CERTIFIED",
         "num_equipes_por_item": {"i1": {"2026-W23": 1}}},
        _catalog_productivity(rate),
    )
    assert outcome.has_errors
    assert any(
        v.codigo == "VAL-CRON-PROD-INVALID" and v.status == "ERRO"
        for v in outcome.validacoes
    )
    assert outcome.canonical.cronograma is None


def test_p14c_preview_clears_previously_cached_successful_finance() -> None:
    historical = _canonical(1.0).model_copy(
        update={
            "resultado": object(),
            "resultado_reconciliado": object(),
            "ponto_equilibrio": [object()],
            "memorial_calculo_bdi": object(),
        }
    )
    outcome = run_cronograma(
        historical,
        {"certification_intent": "PREVIEW",
         "num_equipes_por_item": {"i1": {"2026-W23": 1}}},
        {},
    )
    assert outcome.canonical.cronograma is not None
    assert outcome.canonical.cronograma.is_feasible is True
    assert outcome.canonical.resultado is None
    assert outcome.canonical.resultado_reconciliado is None
    assert outcome.canonical.ponto_equilibrio == []
    assert outcome.canonical.memorial_calculo_bdi is None



def test_p14c_certified_rejection_invalidates_cached_financial_cube() -> None:
    historical = _canonical(1.0).model_copy(
        update={
            "resultado": object(),
            "resultado_reconciliado": object(),
            "cubo_analitico": object(),
            "s_curve": object(),
            "plan_space_result": object(),
        }
    )
    outcome = run_cronograma(
        historical,
        {"certification_intent": "CERTIFIED",
         "num_equipes_por_item": {"i1": {"2026-W23": 1}}},
        {},
    )
    assert outcome.has_errors
    assert outcome.canonical.cronograma is None
    assert outcome.canonical.resultado is None
    assert outcome.canonical.resultado_reconciliado is None
    assert outcome.canonical.cubo_analitico is None
    assert outcome.canonical.s_curve is None
    assert outcome.canonical.plan_space_result is None


def test_p14c_nested_origin_and_audit_accept_real_catalog_graph() -> None:
    """Use the actual RFI catalog schema, not invented top-level aliases."""
    root = Path(__file__).resolve().parents[4]
    path = root / "config/catalogos/rfi-r02/produtividades/PROD-USINAGEM-CBUQ-RFI-001.json"
    production = json.loads(path.read_text(encoding="utf-8"))
    assert production["origem"]["fonte_id"]
    assert production["auditoria"]["versao"]
    assert production["grafo_sinergia"]
    result = run_cronograma(
        _canonical(1.0),
        {"certification_intent": "CERTIFIED",
         "num_equipes_por_item": {"i1": {"2026-W23": 1}}},
        {"cpus": [{"codigo": "CPU-TEST", "producao_id_ref": production["id"]}],
         "produtividades": [production]},
    )
    assert not any(
        v.codigo in ("VAL-CRON-PROD-CERT", "VAL-CRON-PROD-INVALID")
        for v in result.validacoes
    ), result.validacoes
