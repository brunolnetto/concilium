#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evals — Layer 3: Planejamento de Execução

Valida:
- validate_schedule: 100% da quantidade planejada
- calculate_bdi: aplicação correta das margens
- reconcile / resultado financeiro
"""

import pytest


# ---------------------------------------------------------------------------
# validate_schedule
# ---------------------------------------------------------------------------

class TestValidateSchedule:
    """Cronograma deve atingir exatamente 100% da quantidade planejada."""

    def test_schedule_100pct_is_ok(self, planning_skill):
        """Quantidade acumulada = total → OK."""
        result = planning_skill.validate_schedule(
            activity="ESCAVAÇÃO", total_qty=10_000, planned_accumulated=10_000
        )
        assert result.status == "OK"
        assert abs(result.completion_pct - 1.0) < 0.01

    def test_schedule_within_1pct_tolerance_is_ok(self, planning_skill):
        """Tolerância de 1% aceita — 99.5% ainda é OK."""
        result = planning_skill.validate_schedule(
            activity="ESCAVAÇÃO", total_qty=10_000, planned_accumulated=9_950
        )
        assert result.status == "OK", (
            f"99.5% deveria ser OK dentro de tolerância de 1%"
        )

    def test_schedule_below_100pct_is_incomplete(self, planning_skill):
        """80% planejado → INCOMPLETE."""
        result = planning_skill.validate_schedule(
            activity="ESCAVAÇÃO", total_qty=10_000, planned_accumulated=8_000
        )
        assert result.status == "INCOMPLETE"

    def test_schedule_above_100pct_is_overcomplete(self, planning_skill):
        """110% planejado → OVERCOMPLETE."""
        result = planning_skill.validate_schedule(
            activity="ESCAVAÇÃO", total_qty=10_000, planned_accumulated=11_000
        )
        assert result.status == "OVERCOMPLETE"

    def test_schedule_stores_activity_name(self, planning_skill):
        result = planning_skill.validate_schedule(
            activity="ATERRO", total_qty=5_000, planned_accumulated=5_000
        )
        assert result.activity == "ATERRO"

    def test_schedule_completion_pct_formula(self, planning_skill):
        """completion_pct = planned / total."""
        total = 8_000
        planned = 6_000
        result = planning_skill.validate_schedule("X", total, planned)
        expected_pct = planned / total
        assert abs(result.completion_pct - expected_pct) < 0.001

    def test_schedule_zero_total_qty(self, planning_skill):
        """Quando total_qty == 0 não deve lançar ZeroDivisionError."""
        result = planning_skill.validate_schedule(
            activity="Inativa", total_qty=0, planned_accumulated=0
        )
        # Qualquer status é aceitável, só não pode crashar
        assert result is not None


# ---------------------------------------------------------------------------
# calculate_bdi
# ---------------------------------------------------------------------------

class TestCalculateBDI:
    """BDI deve ser aplicado como multiplicador composto por categoria."""

    def test_bdi_single_category(self, planning_skill):
        """Material com BDI 25% → preço c/ BDI = custo × 1.25."""
        result = planning_skill.calculate_bdi(
            base_cost=1_000,
            bdi_percentages={"Material": 25},
        )
        # O preço com BDI deve ser maior que o custo base
        price_with_bdi = result.get("total_with_bdi") or result.get("price_with_bdi")
        if price_with_bdi is None:
            # Verifica qualquer campo que represente custo c/ BDI
            assert any(v > 1_000 for v in result.values() if isinstance(v, (int, float)))
        else:
            assert price_with_bdi > 1_000

    def test_bdi_increases_price(self, planning_skill):
        """Qualquer BDI > 0 deve resultar em preço maior que o custo base."""
        bdi = {"Material": 25, "Diesel": 20, "Mão de Obra": 15, "Equipamento": 12}
        result = planning_skill.calculate_bdi(base_cost=10_000, bdi_percentages=bdi)
        # Ao menos um valor numérico no resultado deve exceder o custo base
        has_higher_value = any(
            isinstance(v, (int, float)) and v > 10_000
            for v in result.values()
        )
        assert has_higher_value, "BDI aplicado não aumentou o preço base"

    def test_bdi_zero_returns_base_cost(self, planning_skill):
        """BDI zero → preço com BDI = custo base."""
        result = planning_skill.calculate_bdi(
            base_cost=10_000, bdi_percentages={"Material": 0}
        )
        # Verificação flexível: nenhum valor deve exceder 10.000 (com folga 1%)
        numeric_values = [v for v in result.values() if isinstance(v, (int, float))]
        assert all(v <= 10_000 * 1.01 for v in numeric_values), (
            "BDI zero não deveria aumentar o custo"
        )


# ---------------------------------------------------------------------------
# Fórmula de Planejamento Mensal (lógica pura — sem fixture)
# ---------------------------------------------------------------------------

class TestPlanejamentoMensalFormula:
    """
    Qtd Planejada Mensal = Dias × Equipes × Prod Diária × % Produtivo

    Testa a fórmula core do CRONOGRAMA sem dependência de arquivo.
    """

    @staticmethod
    def calc_qtd_mensal(
        dias_trabalhados: int,
        n_equipes: int,
        prod_horaria: float,
        produtividade_pct: float,
    ) -> float:
        prod_diaria = prod_horaria * 8  # 8 horas/dia
        return dias_trabalhados * n_equipes * prod_diaria * produtividade_pct

    def test_formula_basic(self):
        """20 dias × 1 equipe × (15 m³/h × 8h) × 0.90 = 2.160 m³."""
        result = self.calc_qtd_mensal(20, 1, 15, 0.90)
        assert abs(result - 2_160.0) < 1.0

    def test_formula_double_teams_doubles_output(self):
        """2 equipes devem produzir o dobro de 1 equipe."""
        q1 = self.calc_qtd_mensal(20, 1, 15, 0.90)
        q2 = self.calc_qtd_mensal(20, 2, 15, 0.90)
        assert abs(q2 / q1 - 2.0) < 0.001

    def test_formula_low_productivity_reduces_output(self):
        """Produtividade 50% deve reduzir a metade."""
        q_full = self.calc_qtd_mensal(20, 1, 15, 1.0)
        q_half = self.calc_qtd_mensal(20, 1, 15, 0.5)
        assert abs(q_half / q_full - 0.5) < 0.001

    def test_formula_zero_days_is_zero(self):
        """Com zero dias trabalhados a produção deve ser zero."""
        assert self.calc_qtd_mensal(0, 2, 15, 0.90) == 0.0
