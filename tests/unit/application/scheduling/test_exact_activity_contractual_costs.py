"""Exact MO/EQ activity cost from P16 witnesses, and its use by Skill05."""

from __future__ import annotations

import json
import sys
from fractions import Fraction

import pytest

from concilium.application.scheduling.skill06_p17_cost_reconciliation import exact_activity_contractual_costs
from concilium.application.skills import run_equipes_e_alocacao
from concilium.domain.models.canonical import (
    EquipamentoEquipeDireta,
    EquipeDireta,
    FuncaoEquipeDireta,
    RecursoContrato,
)


def _contract(tipo_id: str, category: str, demand: dict, owners: dict, partitions: list, *, active="5",
              standby="2", mobility="60") -> RecursoContrato:
    weeks = ["2026-W01", "2026-W02", "2026-W03"]
    active_idx = [weeks.index(w) for w in owners]
    total = Fraction(active) * len(active_idx) + Fraction(standby) + Fraction(mobility)
    witness = {
        "resource_type": tipo_id, "contract_id": f"C-{tipo_id}", "currency": "BRL", "category": category,
        "calendar_weeks": weeks,
        "tariff": {"active_week": active},
        "demand_by_activity": demand,
        "chains": [{"active_week_indices": active_idx, "activity_by_week": owners}],
        "costs": {"active": str(Fraction(active) * len(active_idx)), "standby": standby, "mobility": mobility,
                  "pool_total": str(total)},
    }
    return RecursoContrato(
        contrato_id=f"C-{tipo_id}", tipo_id=tipo_id, quantidade_contratada=1,
        semana_inicio="2026-W01", semana_fim="2026-W03", semanas_contrato=3,
        custo_unit_semanal=float(active), custo_total_contrato=float(total),
        p16_global_assignment=witness, particao_por_item=partitions,
    )


def _shared_crane() -> RecursoContrato:
    # A owns W01, B owns W03; standby 2 + mobility 60 split 50/50 by partitions.
    return _contract(
        "CRANE", "EQ", {"A": [1, 0, 0], "B": [0, 0, 1]}, {"2026-W01": "A", "2026-W03": "B"},
        [{"item_id": "A", "custo_total_particionado": 36.0}, {"item_id": "B", "custo_total_particionado": 36.0}],
    )


def _operator() -> RecursoContrato:
    return _contract(
        "OPER", "MO", {"A": [1, 0, 0]}, {"2026-W01": "A"},
        [{"item_id": "A", "custo_total_particionado": 7.0}], active="7", standby="0", mobility="0",
    )


def test_exact_costs_split_by_category_with_lifecycle_allocation() -> None:
    costs = exact_activity_contractual_costs([_shared_crane(), _operator()])
    assert costs == {
        "A": {"EQ": Fraction(5) + Fraction(31), "MO": Fraction(7)},
        "B": {"EQ": Fraction(5) + Fraction(31), "MO": Fraction(0)},
    }


def test_missing_witness_or_category_fails_closed() -> None:
    crane = _shared_crane()
    no_category = crane.model_copy(
        update={"p16_global_assignment": {k: v for k, v in crane.p16_global_assignment.items() if k != "category"}}
    )
    with pytest.raises(ValueError, match="MO or EQ"):
        exact_activity_contractual_costs([no_category])
    with pytest.raises(ValueError, match="missing exact P16 witness"):
        exact_activity_contractual_costs([crane.model_copy(update={"p16_global_assignment": None})])


def _skill05_helper():
    module = sys.modules[run_equipes_e_alocacao.__module__]
    return module.__dict__["aplicar_custo_exato_p16"]


def _team(item: str, equipment: list[str], functions: list[str]) -> EquipeDireta:
    return EquipeDireta(
        item_id=item,
        equipamentos=[EquipamentoEquipeDireta(equip_id=e) for e in equipment],
        funcoes=[FuncaoEquipeDireta(funcao_id=f) for f in functions],
        custo_inst_mo=999.0, custo_inst_eq=999.0, custo_inst_comb=3.0, custo_inst_mat=4.0, custo_total=2005.0,
    )


def test_skill05_uses_exact_p16_cost_only_when_the_whole_team_is_covered() -> None:
    aplicar = _skill05_helper()
    covered = _team("A", ["CRANE"], ["OPER"])
    partial = _team("B", ["CRANE"], ["HELPER"])  # HELPER labor has no P16 contract
    validations: list = []
    aplicar([covered, partial], [_shared_crane(), _operator()], validations)

    assert (covered.custo_inst_mo, covered.custo_inst_eq) == (7.0, 36.0)
    assert covered.custo_total == 7.0 + 36.0 + 3.0 + 4.0
    assert (partial.custo_inst_mo, partial.custo_inst_eq, partial.custo_total) == (999.0, 999.0, 2005.0)
    codes = {(v.codigo, v.status) for v in validations}
    assert ("VAL-P16-CUSTO-EXATO", "OK") in codes
    partial_msgs = [v.mensagem for v in validations if v.codigo == "VAL-P16-COBERTURA-PARCIAL"]
    assert partial_msgs and "HELPER" in partial_msgs[0]


def test_skill05_without_witnesses_keeps_legacy_costs() -> None:
    aplicar = _skill05_helper()
    team = _team("A", ["CRANE"], [])
    validations: list = []
    aplicar([team], [_shared_crane().model_copy(update={"p16_global_assignment": None})], validations)
    assert (team.custo_inst_mo, team.custo_inst_eq) == (999.0, 999.0)
    assert validations == []


def test_utilization_summary_standby_follows_the_p16_witness() -> None:
    """V3 audits the Skill05 summary against the witness. When P16 hires the 4th
    worker only when demand needs it, the legacy summary (all contracted units
    present for the whole contract) must not report standby the witness lacks."""
    from concilium.domain.models.canonical import ResumoUtilizacaoContrato

    module = sys.modules[run_equipes_e_alocacao.__module__]
    align = module.__dict__["resumo_alinhado_a_testemunha_p16"]
    legacy = ResumoUtilizacaoContrato(
        contrato_id="C-OPER", tipo_id="OPER", quantidade_contratada=4, semanas_contrato=3,
        machine_weeks_disponiveis=12, machine_weeks_usados=10, machine_weeks_standby=2,
        taxa_utilizacao_pct=83.3, custo_standby_total=14.0,
    )
    witness = {"demand": [3, 3, 4], "standby": [0, 0, 0], "costs": {"standby": "0"}}
    aligned = align(legacy, witness)
    assert (aligned.machine_weeks_usados, aligned.machine_weeks_standby, aligned.custo_standby_total) == (10, 0, 0.0)
    assert aligned.taxa_utilizacao_pct == round(10 / 12 * 100, 1)
    assert legacy.machine_weeks_standby == 2  # input not mutated

    with_idle = align(legacy, {"demand": [3, 3, 4], "standby": [1, 0, 0], "costs": {"standby": "1469.76"}})
    assert (with_idle.machine_weeks_standby, with_idle.custo_standby_total) == (1, 1469.76)


def _pe(*, frentes: float):
    from concilium.domain.models.canonical import PontoEquilibrio

    return PontoEquilibrio(
        item_id="A", custo_fixo_equipe=1.0, custo_venda_cpu=1.0, delta=0.0, delta_pct=0.0,
        status_validacao="OK", frentes_equivalentes_necessarias=frentes,
    )


def _frentes_validator():
    from concilium.application.skills import _load

    _load("06-resultado-financeiro", "run_resultado_financeiro")
    for name, module in sys.modules.items():
        if name.endswith("_consolidacao._skill_helpers._ponto_equilibrio"):
            return module._validate_frentes_necessarias
    raise AssertionError("PE helper module not loaded")


@pytest.mark.parametrize(
    ("exact", "expected"),
    [(Fraction(11, 10), None), (Fraction(14, 10), "AVISO"), (Fraction(16, 10), "ERRO")],
)
def test_frentes_check_uses_exact_ratio_when_available(exact, expected) -> None:
    """The legacy estimate says 4.72x (would be ERRO); the exact R_i governs."""
    validate = _frentes_validator()
    pe = _pe(frentes=4.72)
    validations: list = []
    validate(pe, validations, exact)
    statuses = [v.status for v in validations if v.codigo == "VAL-FRENTES-NECESSARIAS-ALTA"]
    assert statuses == ([] if expected is None else [expected])
    if expected:
        assert "R_i" in validations[0].mensagem


def test_frentes_check_without_exact_ratio_keeps_legacy_estimate() -> None:
    validate = _frentes_validator()
    pe = _pe(frentes=4.72)
    validations: list = []
    validate(pe, validations, None)
    assert [v.status for v in validations] == ["ERRO"]


def test_exact_ratio_only_for_fully_covered_activities_with_p18_evidence() -> None:
    from concilium.application.scheduling.skill06_p17_cost_reconciliation import exact_operational_to_catalog_ratio
    from concilium.domain.models.canonical import CanonicalModel

    canonical = CanonicalModel.model_construct(
        contratos_recurso=[_shared_crane(), _operator()],
        equipes_diretas=[_team("A", ["CRANE"], ["OPER"]), _team("B", ["CRANE"], ["HELPER"])],
        p18_consumption_preview={
            "evidence": [
                {"activity_id": "A", "exact_cost": "57"},
                {"activity_id": "B", "exact_cost": "10"},
            ]
        },
    )
    ratios = exact_operational_to_catalog_ratio(canonical, {"A": Fraction(100), "B": Fraction(50)})
    # A: (EQ 36 + MO 7 + V 57) / 100 = 1; B lacks HELPER coverage -> legacy.
    assert ratios == {"A": Fraction(1)}


def test_production_activity_cost_matches_the_oracle_vector() -> None:
    """exact_activity_contractual_costs reproduces activity_cost_reconciliation_v1 exactly."""
    from pathlib import Path

    vector = json.loads(
        (
            Path(__file__).resolve().parents[3] / "reference_formalism/vectors/activity_cost_reconciliation_v1.json"
        ).read_text()
    )["vectors"][0]
    weeks = ["2026-W01", "2026-W02", "2026-W03"]
    contracts = []
    for spec in vector["inputs"]["contracts"]:
        owners = spec["active_week_owner"]
        demand = {aid: [1 if owners.get(w) == aid else 0 for w in weeks] for aid in sorted(set(owners.values()))}
        contracts.append(
            _contract(
                spec["tipo_id"], spec["category"], demand, owners,
                [{"item_id": k, "custo_total_particionado": float(Fraction(v))} for k, v in spec["partitions"].items()],
                active=spec["active_week"], standby=spec["standby"], mobility=spec["mobility"],
            )
        )
    observed = {
        aid: {c: str(v) for c, v in sorted(row.items())}
        for aid, row in sorted(exact_activity_contractual_costs(contracts).items())
    }
    assert observed == vector["expected"]


def test_exact_ratio_uses_zero_v_only_for_declared_no_consumables() -> None:
    from concilium.application.scheduling.skill06_p17_cost_reconciliation import exact_operational_to_catalog_ratio
    from concilium.domain.models.canonical import CanonicalModel

    def ratios(preview: dict) -> dict:
        canonical = CanonicalModel.model_construct(
            contratos_recurso=[_shared_crane(), _operator()],
            equipes_diretas=[_team("A", ["CRANE"], ["OPER"]), _team("B", ["CRANE"], [])],
            p18_consumption_preview=preview,
        )
        return exact_operational_to_catalog_ratio(canonical, {"A": Fraction(100), "B": Fraction(72)})

    evidence = [{"activity_id": "A", "exact_cost": "57"}]
    # B has no evidence rows: without a declaration its R_i is unknown (legacy stays).
    assert ratios({"evidence": evidence}) == {"A": Fraction(1)}
    # With the explicit declaration, V_B = 0 and R_B = K_B / C_B^cat = 36 / 72.
    assert ratios({"evidence": evidence, "declared_no_consumables": ["B"]}) == {"A": Fraction(1), "B": Fraction(1, 2)}
