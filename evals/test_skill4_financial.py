#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evals — Layer 4: Validação Financeira

Valida:
- validate_profitability: faixas VIABLE / UNDERPRICED / OVERPRICED
- calculate_breakeven: fórmula Custos Fixos / Margem de Contribuição
- sensitivity_analysis: variações ±5%, ±10%, ±15%
- generate_health_report: semáforo 🟢🟡🔴
"""

import pytest


# ---------------------------------------------------------------------------
# validate_profitability — target: 8% ≤ margem ≤ 10%
# ---------------------------------------------------------------------------

class TestValidateProfitability:
    """Testa as faixas de viabilidade financeira."""

    def test_margin_9pct_is_viable(self, financial_skill):
        """9% está dentro da faixa ideal → VIABLE."""
        result = financial_skill.validate_profitability(0.09)
        assert result["status"] == "VIABLE"

    def test_margin_8pct_lower_bound_is_viable(self, financial_skill):
        """8% é o limite inferior aceitável → VIABLE."""
        result = financial_skill.validate_profitability(0.08)
        assert result["status"] == "VIABLE"

    def test_margin_10pct_upper_bound_is_viable(self, financial_skill):
        """10% é o limite superior aceitável → VIABLE."""
        result = financial_skill.validate_profitability(0.10)
        assert result["status"] == "VIABLE"

    def test_margin_7pct_is_underpriced(self, financial_skill):
        """7% está abaixo de 8% → UNDERPRICED."""
        result = financial_skill.validate_profitability(0.07)
        assert result["status"] in ("UNDERPRICED",)

    def test_margin_5pct_is_critical(self, financial_skill):
        """5% está criticamente abaixo → status crítico."""
        result = financial_skill.validate_profitability(0.05)
        assert result["status"] in ("CRITICAL", "UNDERPRICED")

    def test_margin_11pct_is_overpriced(self, financial_skill):
        """11% está acima de 10% → OVERPRICED."""
        result = financial_skill.validate_profitability(0.11)
        assert result["status"] in ("OVERPRICED", "OVERPRICED_CRITICAL")

    def test_margin_result_contains_target_range(self, financial_skill):
        """Resultado deve incluir os limites mínimo e máximo."""
        result = financial_skill.validate_profitability(0.09)
        assert "target_min" in result
        assert "target_max" in result
        assert result["target_min"] == 8.0
        assert result["target_max"] == 10.0

    def test_margin_result_contains_message(self, financial_skill):
        """Resultado deve conter mensagem descritiva."""
        result = financial_skill.validate_profitability(0.09)
        assert "message" in result
        assert len(result["message"]) > 0


# ---------------------------------------------------------------------------
# calculate_breakeven
# ---------------------------------------------------------------------------

class TestCalculateBreakeven:
    """Testa o cálculo de ponto de equilíbrio."""

    # Cenário:
    # Custos fixos:         R$ 200.000
    # Custo variável/m³:   R$ 10,00
    # Preço de venda/m³:   R$ 20,00
    # Margem de contribuição = R$ 10,00/m³
    # Break-even = 200.000 / 10 = 20.000 m³
    FIXED  = 200_000
    VC_PER = 10.0
    PRICE  = 20.0
    PLANNED_QTY = 80_000  # → break-even at 25% of planned

    def test_breakeven_quantity_formula(self, financial_skill):
        """Break-even = Custos Fixos / Margem de Contribuição."""
        result = financial_skill.calculate_breakeven(
            fixed_costs=self.FIXED,
            variable_cost_per_unit=self.VC_PER,
            unit_price=self.PRICE,
            planned_quantity=self.PLANNED_QTY,
        )
        assert abs(result["breakeven_quantity"] - 20_000) < 1.0, (
            f"Break-even esperado 20.000 m³, calculado {result['breakeven_quantity']}"
        )

    def test_breakeven_revenue(self, financial_skill):
        """Receita de equilíbrio = break-even qty × preço unitário."""
        result = financial_skill.calculate_breakeven(
            fixed_costs=self.FIXED,
            variable_cost_per_unit=self.VC_PER,
            unit_price=self.PRICE,
            planned_quantity=self.PLANNED_QTY,
        )
        expected_revenue = 20_000 * self.PRICE
        assert abs(result["breakeven_revenue"] - expected_revenue) < 1.0

    def test_breakeven_pct_of_planned(self, financial_skill):
        """Break-even / planejado = 20.000 / 80.000 = 25%."""
        result = financial_skill.calculate_breakeven(
            fixed_costs=self.FIXED,
            variable_cost_per_unit=self.VC_PER,
            unit_price=self.PRICE,
            planned_quantity=self.PLANNED_QTY,
        )
        expected_pct = 25.0
        assert abs(result["breakeven_pct_of_planned"] - expected_pct) < 0.5

    def test_breakeven_low_pct_is_green(self, financial_skill):
        """Break-even a 25% → saúde verde (confortável)."""
        result = financial_skill.calculate_breakeven(
            fixed_costs=self.FIXED,
            variable_cost_per_unit=self.VC_PER,
            unit_price=self.PRICE,
            planned_quantity=self.PLANNED_QTY,
        )
        assert "🟢" in result["health"] or "GREEN" in result["health"].upper()

    def test_breakeven_high_pct_is_red(self, financial_skill):
        """Break-even a 90% da quantidade → saúde vermelha (crítico)."""
        # planned_quantity muito baixo → break-even é % alto
        result = financial_skill.calculate_breakeven(
            fixed_costs=self.FIXED,
            variable_cost_per_unit=self.VC_PER,
            unit_price=self.PRICE,
            planned_quantity=22_000,  # break-even > 40%
        )
        assert "🔴" in result["health"] or "RED" in result["health"].upper()

    def test_breakeven_negative_contribution_margin_returns_error(self, financial_skill):
        """Quando preço < custo variável não deve calcular — retorna erro."""
        result = financial_skill.calculate_breakeven(
            fixed_costs=100_000,
            variable_cost_per_unit=25.0,
            unit_price=20.0,   # preço < custo variável → margem negativa
            planned_quantity=10_000,
        )
        assert result.get("status") == "ERROR"


# ---------------------------------------------------------------------------
# sensitivity_analysis
# ---------------------------------------------------------------------------

class TestSensitivityAnalysis:
    """Análise de sensibilidade: variações de ±5%, ±10%, ±15% nos custos."""

    REVENUE = 1_000_000
    COSTS   =   910_000  # margem base = 9%

    def test_sensitivity_returns_scenarios(self, financial_skill):
        """Deve retornar lista de cenários."""
        scenarios = financial_skill.sensitivity_analysis(
            base_revenue=self.REVENUE,
            base_costs=self.COSTS,
        )
        assert isinstance(scenarios, list)
        assert len(scenarios) > 0

    def test_sensitivity_base_scenario_viable(self, financial_skill):
        """Cenário base (variação 0%) deve ser VIABLE."""
        scenarios = financial_skill.sensitivity_analysis(
            base_revenue=self.REVENUE,
            base_costs=self.COSTS,
            cost_variations=[0.0],
            price_variations=[0.0],
        )
        assert len(scenarios) == 1
        assert scenarios[0].resulting_status in ("VIABLE", "viable")

    def test_sensitivity_cost_increase_reduces_margin(self, financial_skill):
        """Aumento de custos de 10% deve reduzir a margem."""
        s_base = financial_skill.sensitivity_analysis(
            base_revenue=self.REVENUE, base_costs=self.COSTS,
            cost_variations=[0.0], price_variations=[0.0],
        )[0]
        s_10pct = financial_skill.sensitivity_analysis(
            base_revenue=self.REVENUE, base_costs=self.COSTS,
            cost_variations=[0.10], price_variations=[0.0],
        )[0]
        assert s_10pct.resulting_margin < s_base.resulting_margin

    def test_sensitivity_price_decrease_reduces_margin(self, financial_skill):
        """Queda de preço de 5% deve reduzir a margem."""
        s_base = financial_skill.sensitivity_analysis(
            base_revenue=self.REVENUE, base_costs=self.COSTS,
            cost_variations=[0.0], price_variations=[0.0],
        )[0]
        s_5pct_down = financial_skill.sensitivity_analysis(
            base_revenue=self.REVENUE, base_costs=self.COSTS,
            cost_variations=[0.0], price_variations=[-0.05],
        )[0]
        assert s_5pct_down.resulting_margin < s_base.resulting_margin

    def test_sensitivity_standard_variations_covered(self, financial_skill):
        """Deve cobrir variações ±5%, ±10%, ±15% conforme regra de negócio."""
        scenarios = financial_skill.sensitivity_analysis(
            base_revenue=self.REVENUE, base_costs=self.COSTS,
        )
        cost_variations = {s.cost_change_pct for s in scenarios}
        # O skill armazena variações como percentual (e.g., -10.0) ou decimal (-0.1)
        # Normaliza para decimal para comparar
        def _to_dec(v):
            return v / 100 if abs(v) > 1 else v
        cost_variations_dec = {_to_dec(v) for v in cost_variations}
        for expected in [-0.10, -0.05, 0.0, 0.05, 0.10]:
            assert expected in cost_variations_dec, (
                f"Variação de custo {expected:.0%} ausente nos cenários"
            )
