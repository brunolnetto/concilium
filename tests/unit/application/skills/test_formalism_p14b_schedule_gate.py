"""P14-B end-to-end guard: impossible physical schedule cannot be persisted."""
from __future__ import annotations

from datetime import UTC, date, datetime

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
    canonical = _canonical(100.0)
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
    canonical = _canonical(100.0)
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


def test_p14c_preview_with_arbitrary_productivity_is_not_feasible() -> None:
    canonical = _canonical(100.0)
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
    assert outcome.canonical.cronograma.is_feasible is False
