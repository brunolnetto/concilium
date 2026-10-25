"""P18-C1: real canonical Skill04 weeks -> P18 exact V -> P20 preview."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting, ExclusiveCostLedger, PostingNature,
)
from concilium.application.scheduling.physical_consumption_journal import WeeklyConsumptionEvidence
from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis, PhysicalConsumptionRate, PhysicallyPricedGood,
)
from concilium.application.scheduling.skill04_consumption_preview import (
    book_skill04_planned_consumption_preview,
)
from concilium.domain.models.canonical import (
    CanonicalModel, Coordenadas, Cronograma, DistribuicaoSemanal, EapItem,
    Meta, Projeto, RegimeTrabalho, ScheduledActivityCanonical,
)


def _canonical() -> CanonicalModel:
    activities = [
        ScheduledActivityCanonical(
            activity_id="A", start_week=0, end_week=1, duration_weeks=1,
            distribuicao_semanal={"2026-W19": DistribuicaoSemanal(
                num_equipes=1, qtd_executada=400, qtd_acumulada=400, pct=1,
            )},
        ),
        ScheduledActivityCanonical(
            activity_id="B", start_week=1, end_week=2, duration_weeks=1,
            distribuicao_semanal={"2026-W20": DistribuicaoSemanal(
                num_equipes=1, qtd_executada=100, qtd_acumulada=100, pct=1,
            )},
        ),
    ]
    return CanonicalModel(
        meta=Meta(gerado_em=datetime(2026, 5, 1, tzinfo=UTC), contexto_id="p18c"),
        projeto=Projeto(
            id="p18c", nome="physical evidence", tipo_obra="terraplenagem",
            localizacao="test", coordenadas=Coordenadas(lat=-3, lng=-38),
            regime_trabalho=RegimeTrabalho(dias_semana=5, horas_dia=8),
            data_inicio=date(2026, 5, 4), data_termino=date(2026, 6, 30),
            snapshot_catalogo_id="catalog-v1", snapshot_perfil_id="profile-v1",
        ),
        eap=[
            EapItem(item_id="A", cpu_id="CPU-A", unidade="m3", quantitativo=400),
            EapItem(item_id="B", cpu_id="CPU-B", unidade="m3", quantitativo=100),
        ],
        cronograma=Cronograma(scheduled_activities=activities, is_feasible=True),
    )


def _declared():
    # 0.5 tonnes of material per m³, R$100 per t; diesel 3 L/h, R$0.2/L.
    aggregate = PhysicallyPricedGood(
        PhysicalConsumptionRate("AGGREGATE", F(1, 2), "t",
                                ConsumptionBasis.PER_DELIVERED_UNIT, "m³"),
        F(100), "t",
    )
    diesel = PhysicallyPricedGood(
        PhysicalConsumptionRate("DIESEL", F(3), "l",
                                ConsumptionBasis.PER_OPERATING_HOUR),
        F(1, 5), "l",
    )
    declarations = {"AGGREGATE": (aggregate, "MAT"), "DIESEL": (diesel, "COMB")}
    return {"A": declarations, "B": declarations}


def _hours(a: str, week: str, hours: F = F(2)) -> WeeklyConsumptionEvidence:
    return WeeklyConsumptionEvidence(
        f"observed:{a}:{week}", a, "DIESEL", week,
        ConsumptionBasis.PER_OPERATING_HOUR, "OBSERVED_OPERATION",
        operating_hours=hours,
    )


def _pool() -> ExclusiveCostLedger:
    return ExclusiveCostLedger((
        CostPosting(("POOL", "CREW", "2026-W19"), PostingNature.ACTIVE,
                    "MO", F(10), "CREW", "2026-W19"),
    ))


def test_two_activity_partial_week_p18_p20_exact_totals_and_non_go() -> None:
    original = _canonical()
    before = original.model_dump()
    result = book_skill04_planned_consumption_preview(
        original, _pool(), _declared(),
        observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
    )
    assert len(result.consumption.evidence) == 4
    assert result.reconciliation.ledger.contractual_k == F(10)
    assert result.reconciliation.ledger.consumable_v == F(25000) + F(12, 5)
    assert result.reconciliation.ledger.indirect == F(0)
    assert result.reconciliation.total == F(25012) + F(2, 5)
    assert result.authority.endswith("NOT_PROJECT_GO")
    assert result.reconciliation.authority.endswith("NOT_PROJECT_GO")
    assert original.model_dump() == before
    assert original.resultado is None
    assert {
        (line.event_id, line.category, line.week)
        for line in result.consumption.journal.postings
        if line.nature == PostingNature.ACQUISITION
    } == {
        (("CONSUMABLE", "P18C:Q:A:AGGREGATE:2026-W19"), "MAT", "2026-W19"),
        (("CONSUMABLE", "P18C:Q:B:AGGREGATE:2026-W20"), "MAT", "2026-W20"),
        (("CONSUMABLE", "observed:A:2026-W19"), "COMB", "2026-W19"),
        (("CONSUMABLE", "observed:B:2026-W20"), "COMB", "2026-W20"),
    }


@pytest.mark.parametrize("change, error", [
    ("missing_activity", "mapping must agree"),
    ("no_hour_evidence", "operating-hour evidence"),
    ("duplicate_hours", "unique matched"),
    ("observed_wrong_week", "unique matched"),
    ("declared_hours_from_q", "unique matched"),
    ("misclosed_scope", "does not close"),
    ("fallback", "fallback"),
    ("nonfeasible", "feasible"),
    ("already_purchased", "P17 pool input cannot already"),
    ("unit_mismatch", "incompatible physical dimensions"),
    ("same_good_conflicting_price", "conflicting physical rate"),
    ("invalid_week", "invalid ISO week"),
])
def test_fail_closed_adversarial_cases(change: str, error: str) -> None:
    canonical = _canonical()
    goods = _declared()
    hours = (_hours("A", "2026-W19"), _hours("B", "2026-W20"))
    pool = _pool()
    if change == "missing_activity":
        goods.pop("B")
    elif change == "no_hour_evidence":
        hours = hours[:1]
    elif change == "duplicate_hours":
        hours = hours + (hours[0],)
    elif change == "observed_wrong_week":
        hours = (replace(hours[0], week="2026-W18"), hours[1])
    elif change == "declared_hours_from_q":
        hours = (replace(hours[0], kind="PLANNED_CLOSED_SCOPE"), hours[1])
    elif change == "misclosed_scope":
        canonical.cronograma.scheduled_activities[0].distribuicao_semanal[
            "2026-W19"
        ].qtd_executada = 399.0
    elif change == "fallback":
        canonical.cronograma.scheduled_activities[0].produtividade_fallback_aplicada = True
    elif change == "nonfeasible":
        canonical.cronograma.is_feasible = False
    elif change == "already_purchased":
        pool = ExclusiveCostLedger(pool.postings + (
            CostPosting(("CONSUMABLE", "forged"), PostingNature.ACQUISITION,
                        "MAT", F(1), "AGGREGATE", "2026-W19"),
        ))
    elif change == "unit_mismatch":
        physical, category = goods["A"]["AGGREGATE"]
        incompatible = replace(
            physical, rate=replace(physical.rate, activity_unit="t")
        )
        goods = {**goods, "A": {**goods["A"], "AGGREGATE": (incompatible, category)},
                 "B": {**goods["B"], "AGGREGATE": (incompatible, category)}}
    elif change == "same_good_conflicting_price":
        physical, category = goods["B"]["AGGREGATE"]
        goods = {**goods, "B": {**goods["B"], "AGGREGATE": (
            replace(physical, price_per_unit=F(200)), category,
        )}}
    elif change == "invalid_week":
        row = canonical.cronograma.scheduled_activities[0].distribuicao_semanal.pop("2026-W19")
        canonical.cronograma.scheduled_activities[0].distribuicao_semanal["2026-W99"] = row
    with pytest.raises(ValueError, match=error):
        book_skill04_planned_consumption_preview(
            canonical, pool, goods, observed_hours=hours,
        )


def test_zero_output_week_posts_no_material_and_requires_observed_hours() -> None:
    canonical = _canonical()
    activity = canonical.cronograma.scheduled_activities[0]
    activity.distribuicao_semanal["2026-W18"] = DistribuicaoSemanal(
        num_equipes=1, qtd_executada=0, qtd_acumulada=0, pct=0,
    )
    result = book_skill04_planned_consumption_preview(
        canonical, _pool(), _declared(),
        observed_hours=(
            _hours("A", "2026-W18", F(0)),
            _hours("A", "2026-W19"),
            _hours("B", "2026-W20"),
        ),
    )
    assert len(result.consumption.evidence) == 5
    assert not any(
        x.source_id == "P18C:Q:A:AGGREGATE:2026-W18"
        for x in result.consumption.evidence
    )
    assert result.reconciliation.ledger.consumable_v == F(25000) + F(12, 5)


def test_legacy_monetary_proxy_is_not_a_physical_catalog_declaration() -> None:
    goods = _declared()
    goods["A"] = {**goods["A"], "DIESEL": ("R$ per hour", "COMB")}
    with pytest.raises(ValueError, match="physical catalog"):
        book_skill04_planned_consumption_preview(
            _canonical(), _pool(), goods,
            observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
        )
