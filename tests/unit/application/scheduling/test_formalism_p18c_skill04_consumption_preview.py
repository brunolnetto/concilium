"""P18-C1: real canonical Skill04 weeks -> P18 exact V -> P20 preview."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from fractions import Fraction as F

import pytest

from concilium.application.scheduling.contractual_cost_ledger import (
    CostPosting,
    ExclusiveCostLedger,
    PostingNature,
)
from concilium.application.scheduling.physical_consumption_journal import WeeklyConsumptionEvidence
from concilium.application.scheduling.physical_consumption_rates import (
    ConsumptionBasis,
    PhysicalConsumptionRate,
    PhysicallyPricedGood,
)
from concilium.application.scheduling.skill04_consumption_preview import (
    book_skill04_planned_consumption_preview,
)
from concilium.domain.models.canonical import (
    Atividade,
    CanonicalModel,
    Coordenadas,
    Cronograma,
    DistribuicaoSemanal,
    EapItem,
    Meta,
    Projeto,
    RegimeTrabalho,
    ScheduledActivityCanonical,
)


def _canonical() -> CanonicalModel:
    activities = [
        ScheduledActivityCanonical(
            activity_id="A", start_week=0, end_week=0, duration_weeks=1,
            distribuicao_semanal={"2026-W19": DistribuicaoSemanal(
                num_equipes=1, qtd_executada=400, qtd_acumulada=400, pct=1,
            )},
        ),
        ScheduledActivityCanonical(
            activity_id="B", start_week=1, end_week=1, duration_weeks=1,
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


def test_shared_good_uses_activity_specific_consumption_rate() -> None:
    canonical = _canonical()
    goods = _declared()
    diesel_b, category = goods["B"]["DIESEL"]
    goods["B"] = {
        **goods["B"],
        "DIESEL": (
            replace(
                diesel_b,
                rate=replace(diesel_b.rate, physical_rate=F(5)),
            ),
            category,
        ),
    }

    result = book_skill04_planned_consumption_preview(
        canonical,
        _pool(),
        goods,
        observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
    )

    # Shared MA-DIESEL-S10 has one unit price, but the CPUs declare different
    # rates: A consumes 3 L/h and B consumes 5 L/h. Two operation-hours each
    # produce 6 L + 10 L at R$0.20/L = R$3.20, without aliasing the rates.
    diesel = {
        line.activity_id: line.measure
        for line in result.consumption.evidence
        if line.measure.good_id == "DIESEL"
    }
    assert diesel["A"].physical_quantity == F(6)
    assert diesel["B"].physical_quantity == F(10)
    assert diesel["A"].exact_cost == F(6, 5)
    assert diesel["B"].exact_cost == F(2)
    assert result.consumption.variable_cost == F(25000) + F(16, 5)




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
    ("same_good_conflicting_price", "conflicting physical price/category"),
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


def test_zero_output_middle_week_posts_no_material_but_requires_observed_hours() -> None:
    canonical = _canonical()
    activity = canonical.cronograma.scheduled_activities[0]
    activity.end_week = 2
    activity.duration_weeks = 3
    activity.distribuicao_semanal["2026-W19"].qtd_executada = 200
    activity.distribuicao_semanal["2026-W20"] = DistribuicaoSemanal(
        num_equipes=1, qtd_executada=0, qtd_acumulada=200, pct=0.5,
    )
    activity.distribuicao_semanal["2026-W21"] = DistribuicaoSemanal(
        num_equipes=1, qtd_executada=200, qtd_acumulada=400, pct=1,
    )
    observed = (
        _hours("A", "2026-W19"),
        _hours("A", "2026-W20", F(0)),
        _hours("A", "2026-W21", F(0)),
        _hours("B", "2026-W20"),
    )
    result = book_skill04_planned_consumption_preview(
        canonical, _pool(), _declared(), observed_hours=observed,
    )
    assert len(result.consumption.evidence) == 7
    assert not any(
        x.source_id == "P18C:Q:A:AGGREGATE:2026-W20"
        for x in result.consumption.evidence
    )
    assert result.reconciliation.ledger.consumable_v == F(25000) + F(12, 5)

    # Removing the zero-Q intermediate week also removes its hourly requirement
    # in the former implementation. Both source loss and hour loss must fail.
    activity.distribuicao_semanal.pop("2026-W20")
    with pytest.raises(ValueError, match="does not cover scheduled interval"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=tuple(x for x in observed if x.week != "2026-W20" or x.activity_id == "B"),
        )


def test_hourly_evidence_missing_for_zero_q_interior_week_fails_closed() -> None:
    canonical = _canonical()
    activity = canonical.cronograma.scheduled_activities[0]
    activity.end_week = 2
    activity.duration_weeks = 3
    activity.distribuicao_semanal["2026-W19"].qtd_executada = 200
    activity.distribuicao_semanal["2026-W20"] = DistribuicaoSemanal(
        num_equipes=1, qtd_executada=0, qtd_acumulada=200, pct=0.5,
    )
    activity.distribuicao_semanal["2026-W21"] = DistribuicaoSemanal(
        num_equipes=1, qtd_executada=200, qtd_acumulada=400, pct=1,
    )
    with pytest.raises(ValueError, match="explicit operating-hour evidence"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=(
                _hours("A", "2026-W19"),
                _hours("A", "2026-W21"),
                _hours("B", "2026-W20"),
            ),
        )


def test_legacy_monetary_proxy_is_not_a_physical_catalog_declaration() -> None:
    goods = _declared()
    goods["A"] = {**goods["A"], "DIESEL": ("R$ per hour", "COMB")}
    with pytest.raises(ValueError, match="physical catalog"):
        book_skill04_planned_consumption_preview(
            _canonical(), _pool(), goods,
            observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
        )


def test_micro_scope_cannot_disappear_under_absolute_rounding_tolerance() -> None:
    canonical = _canonical()
    canonical.eap[0].quantitativo = 0.00000001
    week = canonical.cronograma.scheduled_activities[0].distribuicao_semanal["2026-W19"]
    week.qtd_executada = 0.0
    with pytest.raises(ValueError, match="does not close"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
        )


def _subdivided() -> CanonicalModel:
    """Real Skill01 identities: subactivities A-atv-1/B-atv-1, final Skill04 A/B."""
    canonical = _canonical()
    canonical.atividades = [
        Atividade(
            atividade_id="A-atv-1", eap_item_id="A", descricao="activity A",
            fracao_quantitativo=1, quantitativo_atividade=400, cpu_id="CPU-A",
        ),
        Atividade(
            atividade_id="B-atv-1", eap_item_id="B", descricao="activity B",
            fracao_quantitativo=1, quantitativo_atividade=100, cpu_id="CPU-B",
        ),
    ]
    return canonical


def test_real_skill01_subactivity_ids_resolve_to_final_skill04_eap_ids() -> None:
    canonical = _subdivided()
    assert {a.atividade_id for a in canonical.atividades} == {"A-atv-1", "B-atv-1"}
    assert {sa.activity_id for sa in canonical.cronograma.scheduled_activities} == {"A", "B"}
    result = book_skill04_planned_consumption_preview(
        canonical, _pool(), _declared(),
        observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
    )
    assert result.consumption.variable_cost == F(25000) + F(12, 5)


def test_two_subactivities_reconcile_one_eap_schedule_scope() -> None:
    canonical = _subdivided()
    canonical.atividades = [
        Atividade(
            atividade_id="A-atv-1", eap_item_id="A", descricao="first half",
            fracao_quantitativo=0.5, quantitativo_atividade=200, cpu_id="CPU-A",
        ),
        Atividade(
            atividade_id="A-atv-2", eap_item_id="A", descricao="second half",
            fracao_quantitativo=0.5, quantitativo_atividade=200, cpu_id="CPU-A",
        ),
        canonical.atividades[1],
    ]
    result = book_skill04_planned_consumption_preview(
        canonical, _pool(), _declared(),
        observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
    )
    assert result.consumption.variable_cost == F(25000) + F(12, 5)


@pytest.mark.parametrize("kind", [
    "missing_eap", "incomplete_q", "incomplete_fraction", "duplicate_subactivity",
    "orphan_parent", "cpu_mismatch",
])
def test_incomplete_or_forged_subactivity_decomposition_rejected(kind: str) -> None:
    canonical = _subdivided()
    if kind == "missing_eap":
        canonical.atividades = canonical.atividades[:1]
    elif kind == "incomplete_q":
        canonical.atividades[0].quantitativo_atividade = 200
    elif kind == "incomplete_fraction":
        canonical.atividades[0].fracao_quantitativo = 0.5
    elif kind == "duplicate_subactivity":
        canonical.atividades = canonical.atividades + [canonical.atividades[0]]
    elif kind == "orphan_parent":
        canonical.atividades[0].eap_item_id = "MISSING"
    elif kind == "cpu_mismatch":
        canonical.atividades[0].cpu_id = "WRONG"
    with pytest.raises(ValueError, match="EAP|subactivity|CPU"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
        )


def test_week_calendar_iso_rollover_and_gaps() -> None:
    canonical = _canonical()
    canonical.projeto.data_inicio = date(2026, 12, 21)  # ISO W52
    canonical.cronograma.scheduled_activities[0].distribuicao_semanal = {
        "2026-W52": DistribuicaoSemanal(
            num_equipes=1, qtd_executada=400, qtd_acumulada=400, pct=1,
        ),
    }
    canonical.cronograma.scheduled_activities[1].distribuicao_semanal = {
        "2026-W53": DistribuicaoSemanal(
            num_equipes=1, qtd_executada=100, qtd_acumulada=100, pct=1,
        ),
    }
    # ISO 2026 has 53 weeks: B must be in W53, not 2027-W01.
    # Do not reuse a contractual pool line from W19 on a W52-only project.
    result = book_skill04_planned_consumption_preview(
        canonical, ExclusiveCostLedger(()), _declared(),
        observed_hours=(_hours("A", "2026-W52"), _hours("B", "2026-W53")),
    )
    assert result.consumption.variable_cost == F(25000) + F(12, 5)


def test_nonfinite_weekly_scope_never_enters_financial_ledger() -> None:
    canonical = _canonical()
    row = canonical.cronograma.scheduled_activities[0].distribuicao_semanal["2026-W19"]
    row.qtd_executada = float("nan")
    with pytest.raises(ValueError, match="finite nonnegative"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
        )



def test_skill01_explicit_six_decimal_rounding_is_not_missing_parent_scope() -> None:
    canonical = _subdivided()
    # Explicit Skill01 splits use round(frac * parent_Q, 6); two 0.5 child
    # rows may sum to 1.0 despite their parent declaring 1.000001 units.
    canonical.eap[0].quantitativo = 1.000001
    canonical.atividades = [
        Atividade(
            atividade_id="A-atv-1", eap_item_id="A", descricao="half one",
            fracao_quantitativo=0.5,
            quantitativo_atividade=round(0.5 * 1.000001, 6), cpu_id="CPU-A",
        ),
        Atividade(
            atividade_id="A-atv-2", eap_item_id="A", descricao="half two",
            fracao_quantitativo=0.5,
            quantitativo_atividade=round(0.5 * 1.000001, 6), cpu_id="CPU-A",
        ),
        canonical.atividades[1],
    ]
    row = canonical.cronograma.scheduled_activities[0].distribuicao_semanal["2026-W19"]
    row.qtd_executada = 1.000001
    result = book_skill04_planned_consumption_preview(
        canonical, _pool(), _declared(),
        observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
    )
    assert result.consumption.variable_cost == F("1.000001") * F(50) + F(5000) + F(12, 5)


def test_skill01_unrelated_six_decimal_forgery_is_not_tolerated() -> None:
    canonical = _subdivided()
    canonical.atividades[0].quantitativo_atividade = 399.999999
    with pytest.raises(ValueError, match="rounding"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=(_hours("A", "2026-W19"), _hours("B", "2026-W20")),
        )


def test_skill04_retained_outer_zero_weeks_require_hourly_evidence() -> None:
    canonical = _canonical()
    activity = canonical.cronograma.scheduled_activities[0]
    activity.start_week = 1
    activity.end_week = 1
    activity.duration_weeks = 1
    activity.distribuicao_semanal = {
        "2026-W19": DistribuicaoSemanal(
            num_equipes=0, qtd_executada=0, qtd_acumulada=0, pct=0,
        ),
        "2026-W20": DistribuicaoSemanal(
            num_equipes=1, qtd_executada=400, qtd_acumulada=400, pct=1,
        ),
        "2026-W21": DistribuicaoSemanal(
            num_equipes=0, qtd_executada=0, qtd_acumulada=400, pct=1,
        ),
    }
    hours = (
        _hours("A", "2026-W19", F(0)),
        _hours("A", "2026-W20"),
        _hours("A", "2026-W21", F(0)),
        _hours("B", "2026-W20"),
    )
    result = book_skill04_planned_consumption_preview(
        canonical, _pool(), _declared(), observed_hours=hours,
    )
    assert result.consumption.variable_cost == F(25000) + F(12, 5)
    assert {("A", x.week) for x in result.consumption.evidence
            if x.activity_id == "A" and x.measure.good_id == "DIESEL"} == {
        ("A", "2026-W19"), ("A", "2026-W20"), ("A", "2026-W21"),
    }
    with pytest.raises(ValueError, match="explicit operating-hour evidence"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=tuple(x for x in hours if x.week != "2026-W19"),
        )


def test_extra_production_outside_declared_skill04_bounds_is_rejected() -> None:
    canonical = _canonical()
    activity = canonical.cronograma.scheduled_activities[0]
    activity.start_week = 1
    activity.end_week = 1
    activity.distribuicao_semanal = {
        "2026-W19": DistribuicaoSemanal(
            num_equipes=1, qtd_executada=1, qtd_acumulada=1, pct=0.0025,
        ),
        "2026-W20": DistribuicaoSemanal(
            num_equipes=1, qtd_executada=399, qtd_acumulada=400, pct=1,
        ),
    }
    with pytest.raises(ValueError, match="productive bounds"):
        book_skill04_planned_consumption_preview(
            canonical, _pool(), _declared(),
            observed_hours=(
                _hours("A", "2026-W19"), _hours("A", "2026-W20"),
                _hours("B", "2026-W20"),
            ),
        )


def test_exact_quantity_rejects_integer_overflow_as_domain_validation() -> None:
    from concilium.application.scheduling.skill04_consumption_preview import _exact_q

    with pytest.raises(ValueError, match="finite nonnegative"):
        _exact_q(10 ** 400)
