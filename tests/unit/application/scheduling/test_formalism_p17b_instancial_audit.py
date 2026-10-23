"""P17-B: legacy Skill 05 accounting ownership and non-certified variable costs."""
from fractions import Fraction

from concilium.application.scheduling.instance_accounting_audit import audit_skill05_cost_ownership
from concilium.domain.models.canonical import InstanciaRecurso, RecursoContrato


def _contract(total: float = 130.0) -> RecursoContrato:
    return RecursoContrato(
        contrato_id="C1", tipo_id="CRANE", quantidade_contratada=1,
        semana_inicio="2026-W01", semana_fim="2026-W02", semanas_contrato=2,
        custo_unit_semanal=50.0, custo_total_contrato=total,
    )


def _instance(**updates: object) -> InstanciaRecurso:
    fields = {
        "instancia_id": "CRANE-1", "contrato_id": "C1", "tipo_id": "CRANE",
        "numero": 1, "semana_entrada": "2026-W01", "semana_saida": "2026-W02",
        "custo_ativo_mo": 20.0, "custo_ativo_eq": 50.0,
        "custo_idle_mo": 10.0, "custo_idle_eq": 5.0,
        "custo_ativo_mat": 5.0, "custo_ativo_comb": 10.0,
        "custo_mob_instancia": 20.0, "custo_demob_instancia": 10.0,
        "custo_instancia_total": 130.0,
    }
    fields.update(updates)
    return InstanciaRecurso.model_validate(fields)


def _codes(audit) -> set[str]:
    return {item.codigo for item in audit.validations}


def test_separate_contractual_k_unverified_v_and_indirect_mobility() -> None:
    audit = audit_skill05_cost_ownership((_contract(),), (_instance(),))
    assert audit.contractual_k == Fraction(85)
    assert audit.legacy_consumption_unverified == Fraction(15)
    assert audit.indirect_mobility == Fraction(30)
    assert audit.reconstructed == Fraction(130)
    assert audit.authority == "PREVIEW_ONLY_LEGACY_MONETARY_COMPONENTS"
    assert "VAL-P17-CONSUMO-LEGADO" in _codes(audit)
    assert not any(x.status == "ERRO" for x in audit.validations)


def test_duplicate_instance_does_not_double_charge() -> None:
    instance = _instance()
    audit = audit_skill05_cost_ownership((_contract(),), (instance, instance))
    assert len(audit.slices) == 1
    assert "VAL-P17-INSTANCIA-DUPLICADA" in _codes(audit)


def test_wrong_legacy_total_and_contract_total_fail_closed() -> None:
    wrong = audit_skill05_cost_ownership((_contract(),), (
        _instance(custo_instancia_total=120.0),
    ))
    assert "VAL-P17-INSTANCIA-NAO-CONCILIADA" in _codes(wrong)
    assert "VAL-P17-CONTRATO-NAO-CONCILIADO" in _codes(wrong)


def test_negative_float_and_nan_values_never_become_a_proof() -> None:
    for bad in (-1.0, float("nan")):
        audit = audit_skill05_cost_ownership((_contract(),), (
            _instance(custo_ativo_eq=bad),
        ))
        assert "VAL-P17-VALOR-INVALIDO" in _codes(audit)
        assert audit.slices == ()


def test_missing_contract_and_missing_instances_are_not_valid_zero_cost() -> None:
    none = audit_skill05_cost_ownership((), ())
    assert "VAL-P17-SEM-EVIDENCIA" in _codes(none)
    missing = audit_skill05_cost_ownership((), (_instance(),))
    assert "VAL-P17-CONTRATO-AUSENTE" in _codes(missing)
    empty = audit_skill05_cost_ownership((_contract(),), ())
    assert "VAL-P17-CUSTO-INSTANCIAL-AUSENTE" in _codes(empty)
