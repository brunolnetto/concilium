"""Unit tests for resource_pool_validator.py — target 80%+ coverage.

All public functions (ResourcePoolValidator.validate_week, atribuir_custo_insumo)
are pure/self-contained; no mocks needed.
"""

import pytest

from concilium.infrastructure.catalog.resource_pool_validator import (
    ResourcePoolValidator,
    ResultadoValidacaoSemana,
    ViolacaoPool,
    atribuir_custo_insumo,
)

SEMANA = "2025-W10"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_insumo_a(preco=100.0):
    """Classe A — exclusivo_dedicado."""
    return {
        "preco_unitario": preco,
        "classe_compartilhamento": {"classe": "exclusivo_dedicado"},
    }


def _make_insumo_b(fracao=0.5, preco=100.0):
    """Classe B — exclusivo_compartilhavel."""
    return {
        "preco_unitario": preco,
        "classe_compartilhamento": {"classe": "exclusivo_compartilhavel", "fracao_uso": fracao},
    }


def _make_insumo_c(capacidade_cobertura=2, preco=200.0):
    """Classe C — concorrente_compartilhavel."""
    return {
        "preco_unitario": preco,
        "classe_compartilhamento": {
            "classe": "concorrente_compartilhavel",
            "capacidade_cobertura": capacidade_cobertura,
        },
    }


# ---------------------------------------------------------------------------
# ResultadoValidacaoSemana.ok property
# ---------------------------------------------------------------------------


class TestResultadoValidacaoSemana:
    def test_ok_when_no_violations(self):
        resultado = ResultadoValidacaoSemana()
        assert resultado.ok is True

    def test_not_ok_when_violations_present(self):
        v = ViolacaoPool(
            codigo="VAL-POOL-A-01",
            insumo_id="equip-01",
            semana=SEMANA,
            demanda=3.0,
            capacidade=2.0,
            excedente=1.0,
            classe="exclusivo_dedicado",
            recomendacao="Adquirir mais",
        )
        resultado = ResultadoValidacaoSemana(violacoes=[v])
        assert resultado.ok is False


# ---------------------------------------------------------------------------
# ResourcePoolValidator.validate_week
# ---------------------------------------------------------------------------


class TestValidateWeekNoViolations:
    """No violations when demand fits within pool for all three classes."""

    def test_class_a_demand_equals_pool_no_violation(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-a": _make_insumo_a()}
        # 2 activities each requesting 1 unit → demand = 2; pool = 2 → no violation
        alocacoes = {
            "at-1": {"eq-a": 1},
            "at-2": {"eq-a": 1},
        }
        pool = {"eq-a": 2}
        resultado = validator.validate_week(SEMANA, ["at-1", "at-2"], alocacoes, insumos, pool)
        assert resultado.ok is True
        assert resultado.violacoes == []

    def test_class_b_demand_below_pool_no_violation(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-b": _make_insumo_b(fracao=0.4)}
        # 2 activities each requesting 1 unit with fracao=0.4 → demand = 0.8; pool = 1
        alocacoes = {
            "at-1": {"eq-b": 1},
            "at-2": {"eq-b": 1},
        }
        pool = {"eq-b": 1}
        resultado = validator.validate_week(SEMANA, ["at-1", "at-2"], alocacoes, insumos, pool)
        assert resultado.ok is True

    def test_class_c_simultaneous_below_capacity_no_violation(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-c": _make_insumo_c(capacidade_cobertura=3)}
        # 3 activities → demand = 3; pool = 1 instance * cap_cobertura 3 = 3 → no violation
        alocacoes = {f"at-{i}": {"eq-c": 1} for i in range(3)}
        pool = {"eq-c": 1}
        resultado = validator.validate_week(SEMANA, list(alocacoes.keys()), alocacoes, insumos, pool)
        assert resultado.ok is True


class TestValidateWeekClassAViolation:
    """VAL-POOL-A-01: summed instances exceed pool capacity."""

    def test_class_a_violation_raised(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-a": _make_insumo_a()}
        alocacoes = {
            "at-1": {"eq-a": 2},
            "at-2": {"eq-a": 2},
        }
        pool = {"eq-a": 3}  # demand=4 > pool=3
        resultado = validator.validate_week(SEMANA, ["at-1", "at-2"], alocacoes, insumos, pool)
        assert not resultado.ok
        assert len(resultado.violacoes) == 1
        v = resultado.violacoes[0]
        assert v.codigo == "VAL-POOL-A-01"
        assert v.insumo_id == "eq-a"
        assert v.semana == SEMANA
        assert v.demanda == pytest.approx(4.0)
        assert v.capacidade == pytest.approx(3.0)
        assert v.excedente == pytest.approx(1.0)
        assert v.classe == "exclusivo_dedicado"
        assert "1" in v.recomendacao  # "1 unidade(s) adicional(is)" in message

    def test_class_a_violation_multiple_insumos(self):
        validator = ResourcePoolValidator()
        insumos = {
            "eq-a1": _make_insumo_a(),
            "eq-a2": _make_insumo_a(),
        }
        alocacoes = {
            "at-1": {"eq-a1": 5, "eq-a2": 5},
        }
        pool = {"eq-a1": 3, "eq-a2": 3}
        resultado = validator.validate_week(SEMANA, ["at-1"], alocacoes, insumos, pool)
        codigos = [v.codigo for v in resultado.violacoes]
        assert codigos.count("VAL-POOL-A-01") == 2


class TestValidateWeekClassBViolation:
    """VAL-POOL-B-01: fracao_uso-weighted demand exceeds pool."""

    def test_class_b_violation_raised(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-b": _make_insumo_b(fracao=0.6)}
        # 3 activities × 1 unit × fracao 0.6 = 1.8 > pool 1
        alocacoes = {f"at-{i}": {"eq-b": 1} for i in range(3)}
        pool = {"eq-b": 1}
        resultado = validator.validate_week(SEMANA, list(alocacoes.keys()), alocacoes, insumos, pool)
        assert not resultado.ok
        v = resultado.violacoes[0]
        assert v.codigo == "VAL-POOL-B-01"
        assert v.classe == "exclusivo_compartilhavel"
        assert v.demanda == pytest.approx(1.8)
        assert v.capacidade == pytest.approx(1.0)
        assert v.excedente == pytest.approx(0.8)

    def test_class_b_recomendacao_text(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-b": _make_insumo_b(fracao=1.0)}
        alocacoes = {"at-1": {"eq-b": 2}, "at-2": {"eq-b": 2}}
        pool = {"eq-b": 3}  # demand=4 > 3
        resultado = validator.validate_week(SEMANA, ["at-1", "at-2"], alocacoes, insumos, pool)
        assert not resultado.ok
        v = resultado.violacoes[0]
        assert "Redistribuir" in v.recomendacao or "adicionar" in v.recomendacao.lower()


class TestValidateWeekClassCViolation:
    """VAL-POOL-C-01: simultaneous activity count exceeds instancias * capacidade_cobertura."""

    def test_class_c_violation_raised(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-c": _make_insumo_c(capacidade_cobertura=2)}
        # 5 activities → n_atividades=5; pool=2 * cap=2=4 → excedente=1
        alocacoes = {f"at-{i}": {"eq-c": 1} for i in range(5)}
        pool = {"eq-c": 2}
        resultado = validator.validate_week(SEMANA, list(alocacoes.keys()), alocacoes, insumos, pool)
        assert not resultado.ok
        v = resultado.violacoes[0]
        assert v.codigo == "VAL-POOL-C-01"
        assert v.classe == "concorrente_compartilhavel"
        assert v.demanda == pytest.approx(5.0)
        assert v.capacidade == pytest.approx(4.0)
        assert v.excedente == pytest.approx(1.0)

    def test_class_c_recomendacao_mentions_capacidade_cobertura(self):
        validator = ResourcePoolValidator()
        cap = 3
        insumos = {"eq-c": _make_insumo_c(capacidade_cobertura=cap)}
        # 4 simultaneous; pool 1 * cap 3 = 3 → violation
        alocacoes = {f"at-{i}": {"eq-c": 1} for i in range(4)}
        pool = {"eq-c": 1}
        resultado = validator.validate_week(SEMANA, list(alocacoes.keys()), alocacoes, insumos, pool)
        assert not resultado.ok
        v = resultado.violacoes[0]
        assert str(cap) in v.recomendacao


class TestValidateWeekMixedClasses:
    """Mixed insumos across all three classes in one week."""

    def test_mixed_classes_only_exceeded_ones_raise(self):
        validator = ResourcePoolValidator()
        insumos = {
            "eq-a": _make_insumo_a(),
            "eq-b": _make_insumo_b(fracao=0.3),
            "eq-c": _make_insumo_c(capacidade_cobertura=5),
        }
        # eq-a: 6 activities × 1 unit = demand 6, pool=10 → OK
        # eq-b: 6 activities × 1 × fracao 0.3 = 1.8, pool=5 → OK
        # eq-c: 6 activities, pool=1 × cap=5 = 5 → VIOLATION (6>5)
        alocacoes = {f"at-{i}": {"eq-a": 1, "eq-b": 1, "eq-c": 1} for i in range(6)}
        pool = {"eq-a": 10, "eq-b": 5, "eq-c": 1}
        resultado = validator.validate_week(SEMANA, list(alocacoes.keys()), alocacoes, insumos, pool)
        assert not resultado.ok
        codigos = [v.codigo for v in resultado.violacoes]
        assert "VAL-POOL-C-01" in codigos
        assert "VAL-POOL-A-01" not in codigos
        assert "VAL-POOL-B-01" not in codigos

    def test_mixed_all_classes_can_all_violate(self):
        validator = ResourcePoolValidator()
        insumos = {
            "eq-a": _make_insumo_a(),
            "eq-b": _make_insumo_b(fracao=1.0),
            "eq-c": _make_insumo_c(capacidade_cobertura=1),
        }
        # eq-a: demand=3, pool=1 → violation
        # eq-b: demand=3, pool=1 → violation
        # eq-c: 3 simultaneous, pool=1 * cap=1 = 1 → violation
        alocacoes = {f"at-{i}": {"eq-a": 1, "eq-b": 1, "eq-c": 1} for i in range(3)}
        pool = {"eq-a": 1, "eq-b": 1, "eq-c": 1}
        resultado = validator.validate_week(SEMANA, list(alocacoes.keys()), alocacoes, insumos, pool)
        codigos = {v.codigo for v in resultado.violacoes}
        assert "VAL-POOL-A-01" in codigos
        assert "VAL-POOL-B-01" in codigos
        assert "VAL-POOL-C-01" in codigos


class TestValidateWeekEdgeCases:
    """Edge cases: zero quantity, unknown insumo_id, empty week."""

    def test_zero_quantity_skipped(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-a": _make_insumo_a()}
        # quantidade=0 → should be skipped → demand=0 → no violation
        alocacoes = {"at-1": {"eq-a": 0}}
        pool = {"eq-a": 0}  # even with zero pool, no violation since demand also zero
        resultado = validator.validate_week(SEMANA, ["at-1"], alocacoes, insumos, pool)
        assert resultado.ok

    def test_negative_quantity_skipped(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-a": _make_insumo_a()}
        alocacoes = {"at-1": {"eq-a": -5}}
        pool = {"eq-a": 0}
        resultado = validator.validate_week(SEMANA, ["at-1"], alocacoes, insumos, pool)
        assert resultado.ok

    def test_unknown_insumo_id_skipped(self):
        validator = ResourcePoolValidator()
        insumos = {}  # no insumos registered
        alocacoes = {"at-1": {"unknown-equip": 10}}
        pool = {}
        resultado = validator.validate_week(SEMANA, ["at-1"], alocacoes, insumos, pool)
        assert resultado.ok

    def test_activity_not_in_alocacoes_no_error(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-a": _make_insumo_a()}
        # activity listed as active but has no alocacoes entry
        alocacoes = {}
        pool = {"eq-a": 5}
        resultado = validator.validate_week(SEMANA, ["at-1"], alocacoes, insumos, pool)
        assert resultado.ok

    def test_empty_atividades_ativas(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-a": _make_insumo_a()}
        alocacoes = {"at-1": {"eq-a": 10}}
        pool = {"eq-a": 0}
        # No active activities → nothing accumulated → no violation
        resultado = validator.validate_week(SEMANA, [], alocacoes, insumos, pool)
        assert resultado.ok

    def test_insumo_without_classe_compartilhamento_treated_as_class_a(self):
        validator = ResourcePoolValidator()
        # No classe_compartilhamento field → defaults to exclusivo_dedicado
        insumos = {"eq-no-cls": {"preco_unitario": 50.0}}
        alocacoes = {"at-1": {"eq-no-cls": 5}}
        pool = {"eq-no-cls": 3}  # demand=5 > 3 → Class A violation
        resultado = validator.validate_week(SEMANA, ["at-1"], alocacoes, insumos, pool)
        assert not resultado.ok
        v = resultado.violacoes[0]
        assert v.codigo == "VAL-POOL-A-01"

    def test_insumo_with_none_classe_compartilhamento_treated_as_class_a(self):
        validator = ResourcePoolValidator()
        insumos = {"eq-none": {"preco_unitario": 50.0, "classe_compartilhamento": None}}
        alocacoes = {"at-1": {"eq-none": 5}}
        pool = {"eq-none": 3}
        resultado = validator.validate_week(SEMANA, ["at-1"], alocacoes, insumos, pool)
        assert not resultado.ok
        assert resultado.violacoes[0].codigo == "VAL-POOL-A-01"


# ---------------------------------------------------------------------------
# atribuir_custo_insumo
# ---------------------------------------------------------------------------


class TestAtribuirCustoInsumo:
    """Test atribuir_custo_insumo for all branches."""

    def test_no_classe_compartilhamento_returns_base_cost(self):
        insumo = {"preco_unitario": 100.0}
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=3, semanas_ativo=4)
        assert cost == pytest.approx(400.0)

    def test_classe_compartilhamento_none_returns_base_cost(self):
        insumo = {"preco_unitario": 50.0, "classe_compartilhamento": None}
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=2, semanas_ativo=3)
        assert cost == pytest.approx(150.0)

    def test_class_a_returns_full_cost(self):
        insumo = _make_insumo_a(preco=200.0)
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=5, semanas_ativo=2)
        assert cost == pytest.approx(400.0)

    def test_class_b_scales_by_fracao_uso(self):
        insumo = _make_insumo_b(fracao=0.25, preco=400.0)
        # custo_base = 400 * 4 = 1600; scaled by 0.25 → 400
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=1, semanas_ativo=4)
        assert cost == pytest.approx(400.0)

    def test_class_b_fracao_one_returns_full_base(self):
        insumo = _make_insumo_b(fracao=1.0, preco=100.0)
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=1, semanas_ativo=3)
        assert cost == pytest.approx(300.0)

    def test_class_c_divides_by_min_n_and_cap(self):
        # n_atividades_simultaneas=3, cap=5 → divisor=min(3,5)=3
        insumo = _make_insumo_c(capacidade_cobertura=5, preco=300.0)
        # custo_base = 300 * 2 = 600; / 3 = 200
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=3, semanas_ativo=2)
        assert cost == pytest.approx(200.0)

    def test_class_c_cap_limits_divisor(self):
        # n_atividades_simultaneas=10, cap=4 → divisor=min(10,4)=4
        insumo = _make_insumo_c(capacidade_cobertura=4, preco=400.0)
        # custo_base = 400 * 1 = 400; / 4 = 100
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=10, semanas_ativo=1)
        assert cost == pytest.approx(100.0)

    def test_class_c_divisor_zero_guard_returns_full_cost(self):
        # n_atividades_simultaneas=0, cap=0 (or just n=0) → divisor=0 → guard activates
        insumo = {
            "preco_unitario": 500.0,
            "classe_compartilhamento": {"classe": "concorrente_compartilhavel", "capacidade_cobertura": 0},
        }
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=0, semanas_ativo=2)
        assert cost == pytest.approx(1000.0)

    def test_class_c_n_zero_cap_positive_guard_returns_full_cost(self):
        # n_atividades_simultaneas=0 → min(0, 5)=0 → divisor=0 → guard
        insumo = _make_insumo_c(capacidade_cobertura=5, preco=100.0)
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=0, semanas_ativo=2)
        assert cost == pytest.approx(200.0)

    def test_preco_unitario_missing_defaults_to_zero(self):
        insumo = {"classe_compartilhamento": {"classe": "exclusivo_dedicado"}}
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=1, semanas_ativo=5)
        assert cost == pytest.approx(0.0)

    def test_unknown_classe_returns_base_cost(self):
        # Unknown class name → falls through to return custo_base
        insumo = {
            "preco_unitario": 100.0,
            "classe_compartilhamento": {"classe": "alguma_classe_desconhecida"},
        }
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=1, semanas_ativo=3)
        assert cost == pytest.approx(300.0)

    def test_semanas_ativo_zero(self):
        insumo = _make_insumo_a(preco=999.0)
        cost = atribuir_custo_insumo(insumo, n_atividades_simultaneas=1, semanas_ativo=0)
        assert cost == pytest.approx(0.0)


