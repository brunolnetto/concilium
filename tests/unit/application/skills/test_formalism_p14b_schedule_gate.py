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
    assert result.canonical is not canonical
    assert result.canonical.cronograma is None
    assert result.canonical.resultado is None
    assert result.canonical.resultado_reconciliado is None
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
    assert "Fechamento físico de escopo não comprovado" in error.mensagem
    assert "Q=300.0" in error.mensagem
    assert "Σq=0.0" in error.mensagem
    assert "resíduo=300.0" in error.mensagem
    assert "tolerância=" in error.mensagem
    assert "horizonte_semanas=" in error.mensagem
    assert "CALENDAR_OR_CAPACITY_EXHAUSTED" in error.mensagem
    assert result.canonical is not canonical
    assert result.canonical.cronograma is None
    assert result.canonical.resultado is None
