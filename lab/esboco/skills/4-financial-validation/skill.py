#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Financial Validation Skill

Validates financial viability and performs sensitivity analysis
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class HealthStatus(Enum):
    """Project health status"""
    GREEN = "🟢 OK"
    YELLOW = "🟡 CAUTION"
    RED = "🔴 RISK"


@dataclass
class FinancialValidation:
    """Financial validation result"""
    margin_pct: float
    margin_status: HealthStatus
    breakeven_pct: float
    breakeven_status: HealthStatus
    cost_structure_status: HealthStatus
    overall_status: HealthStatus
    message: str
    recommendations: List[str]


@dataclass
class SensitivityScenario:
    """Sensitivity analysis scenario"""
    name: str
    cost_change_pct: float
    price_change_pct: float
    resulting_margin: float
    resulting_status: str
    risk_level: str


class FinancialValidationSkill:
    """
    Validates project financial health and viability
    """
    
    # Target ranges
    TARGET_MARGIN_MIN = 0.08
    TARGET_MARGIN_MAX = 0.10
    TARGET_MARGIN_IDEAL = 0.09
    
    FIXED_COST_MAX_PCT = 0.25
    BREAKEVEN_MAX_PCT = 0.40
    
    MARGIN_THRESHOLDS = {
        "GREEN": (0.08, 0.10),
        "YELLOW": (0.06, 0.12),
        "RED": (0.0, 0.06) or (0.12, float('inf'))
    }
    
    def __init__(self, spreadsheet_path: str, execution_skill=None):
        self.spreadsheet_path = spreadsheet_path
        self.execution_skill = execution_skill
    
    def validate_profitability(self, margin_pct: float) -> Dict[str, Any]:
        """
        Validate if margin meets target
        
        Args:
            margin_pct: Margin percentage (e.g., 0.095 for 9.5%)
        
        Returns:
            Validation result
        """
        margin_pct_display = margin_pct * 100
        
        if self.TARGET_MARGIN_MIN <= margin_pct <= self.TARGET_MARGIN_MAX:
            status = "VIABLE"
            health = HealthStatus.GREEN
            message = f"✅ Margem dentro do target: {margin_pct_display:.2f}%"
        elif 0.06 <= margin_pct < 0.08:
            status = "UNDERPRICED"
            health = HealthStatus.YELLOW
            message = f"⚠️ Margem baixa ({margin_pct_display:.2f}%) - Considerar aumentar preços"
        elif margin_pct < 0.06:
            status = "CRITICAL"
            health = HealthStatus.RED
            message = f"🔴 Margem crítica ({margin_pct_display:.2f}%) - REWORK NECESSÁRIO"
        elif 0.10 < margin_pct <= 0.12:
            status = "OVERPRICED"
            health = HealthStatus.YELLOW
            message = f"⚠️ Margem alta ({margin_pct_display:.2f}%) - Risco competitivo"
        else:  # > 0.12
            status = "OVERPRICED_CRITICAL"
            health = HealthStatus.RED
            message = f"🔴 Margem muito alta ({margin_pct_display:.2f}%) - Preço não competitivo"
        
        return {
            "margin_pct": margin_pct_display,
            "status": status,
            "health": health.value,
            "message": message,
            "target_min": self.TARGET_MARGIN_MIN * 100,
            "target_max": self.TARGET_MARGIN_MAX * 100
        }
    
    def calculate_breakeven(self,
                           fixed_costs: float,
                           variable_cost_per_unit: float,
                           unit_price: float,
                           planned_quantity: float) -> Dict[str, Any]:
        """
        Calculate break-even point
        
        Args:
            fixed_costs: ADM, TOP, LAB, QSMS total
            variable_cost_per_unit: (Material + Diesel + MO + Eq) per unit
            unit_price: Selling price per unit
            planned_quantity: Planned output quantity
        
        Returns:
            Break-even analysis
        """
        contribution_margin = unit_price - variable_cost_per_unit
        
        if contribution_margin <= 0:
            return {
                "status": "ERROR",
                "message": "Contribution margin <= 0 (price must exceed variable cost)"
            }
        
        breakeven_qty = fixed_costs / contribution_margin
        breakeven_revenue = breakeven_qty * unit_price
        breakeven_pct = breakeven_qty / planned_quantity if planned_quantity > 0 else 0
        
        # Determine health
        if breakeven_pct <= 0.30:
            health = HealthStatus.GREEN
            message = "✅ Break-even confortável"
        elif breakeven_pct <= 0.40:
            health = HealthStatus.YELLOW
            message = "⚠️ Break-even moderado"
        else:
            health = HealthStatus.RED
            message = "🔴 Break-even crítico"
        
        # Safety margin
        safety_margin = planned_quantity - breakeven_qty
        safety_margin_pct = (safety_margin / planned_quantity * 100) if planned_quantity > 0 else 0
        
        return {
            "fixed_costs": fixed_costs,
            "variable_cost_per_unit": variable_cost_per_unit,
            "unit_price": unit_price,
            "contribution_margin": contribution_margin,
            "breakeven_quantity": breakeven_qty,
            "breakeven_revenue": breakeven_revenue,
            "breakeven_pct_of_planned": breakeven_pct * 100,
            "safety_margin_quantity": safety_margin,
            "safety_margin_pct": safety_margin_pct,
            "health": health.value,
            "message": message
        }
    
    def sensitivity_analysis(self,
                            base_revenue: float,
                            base_costs: float,
                            cost_variations: List[float] = None,
                            price_variations: List[float] = None) -> List[SensitivityScenario]:
        """
        Perform sensitivity analysis
        
        Args:
            base_revenue: Base revenue
            base_costs: Base total costs
            cost_variations: Cost change percentages (e.g., [-0.10, 0.10])
            price_variations: Price change percentages (e.g., [-0.05, 0.05])
        
        Returns:
            List of scenarios with resulting margins
        """
        if cost_variations is None:
            cost_variations = [-0.10, -0.05, 0.0, 0.05, 0.10]
        if price_variations is None:
            price_variations = [-0.05, 0.0, 0.05]
        
        base_margin = (base_revenue - base_costs) / base_revenue
        scenarios = []
        
        for cost_change in cost_variations:
            for price_change in price_variations:
                new_costs = base_costs * (1 + cost_change)
                new_revenue = base_revenue * (1 + price_change)
                new_margin = (new_revenue - new_costs) / new_revenue if new_revenue > 0 else 0
                
                if new_margin >= 0.08:
                    scenario_status = "VIABLE"
                elif new_margin >= 0.06:
                    scenario_status = "MARGINAL"
                else:
                    scenario_status = "CRITICAL"
                
                if cost_change > 0.10 or price_change < -0.05:
                    risk_level = "HIGH"
                elif cost_change > 0.05 or price_change < 0:
                    risk_level = "MEDIUM"
                else:
                    risk_level = "LOW"
                
                scenarios.append(SensitivityScenario(
                    name=f"Custos {cost_change:+.0%} / Preço {price_change:+.0%}",
                    cost_change_pct=cost_change * 100,
                    price_change_pct=price_change * 100,
                    resulting_margin=new_margin * 100,
                    resulting_status=scenario_status,
                    risk_level=risk_level
                ))
        
        return scenarios
    
    def validate_cost_structure(self,
                               direct_costs: float,
                               indirect_costs: float,
                               revenue: float) -> Dict[str, Any]:
        """
        Validate cost structure proportions
        
        Returns:
            Validation of percentages
        """
        total_costs = direct_costs + indirect_costs
        
        direct_pct = direct_costs / revenue if revenue > 0 else 0
        indirect_pct = indirect_costs / revenue if revenue > 0 else 0
        profit_pct = (revenue - total_costs) / revenue if revenue > 0 else 0
        
        issues = []
        
        if indirect_pct > 0.25:
            issues.append(f"⚠️ Custos indiretos altos ({indirect_pct:.1%} > 25%)")
        
        if direct_pct > 0.85:
            issues.append(f"⚠️ Custos diretos muito altos ({direct_pct:.1%} > 85%)")
        
        if profit_pct < 0.06:
            issues.append(f"⚠️ Margem baixa ({profit_pct:.1%})")
        
        status = HealthStatus.RED if len(issues) >= 2 else HealthStatus.YELLOW if issues else HealthStatus.GREEN
        
        return {
            "direct_cost_pct": direct_pct * 100,
            "indirect_cost_pct": indirect_pct * 100,
            "profit_pct": profit_pct * 100,
            "issues": issues,
            "status": status.value
        }
    
    def generate_health_report(self,
                              margin_pct: float,
                              breakeven_pct: float,
                              direct_costs: float,
                              indirect_costs: float,
                              revenue: float) -> Dict[str, Any]:
        """
        Generate comprehensive financial health report
        
        Returns:
            Complete health assessment
        """
        profitability = self.validate_profitability(margin_pct)
        breakeven = {
            "pct_of_planned": breakeven_pct * 100,
            "status": HealthStatus.GREEN if breakeven_pct <= 0.30 else HealthStatus.YELLOW if breakeven_pct <= 0.40 else HealthStatus.RED
        }
        cost_structure = self.validate_cost_structure(direct_costs, indirect_costs, revenue)
        
        # Determine overall health
        statuses = [profitability['health'], breakeven['status'].value, cost_structure['status']]
        if all('🔴' in s for s in statuses):
            overall = HealthStatus.RED
        elif any('🔴' in s for s in statuses):
            overall = HealthStatus.YELLOW
        else:
            overall = HealthStatus.GREEN
        
        return {
            "timestamp": pd.Timestamp.now().isoformat(),
            "overall_status": overall.value,
            "profitability": profitability,
            "breakeven": breakeven,
            "cost_structure": cost_structure,
            "recommendation": self._generate_recommendation(overall, profitability, breakeven),
            "go_nogo": "GO" if overall == HealthStatus.GREEN else "CAUTION" if overall == HealthStatus.YELLOW else "NOGO"
        }
    
    def _generate_recommendation(self, overall: HealthStatus,
                                 profitability: Dict,
                                 breakeven: Dict) -> str:
        """Generate recommendation based on analysis"""
        if overall == HealthStatus.GREEN:
            return "✅ Projeto aprovado - Viável economicamente"
        elif overall == HealthStatus.YELLOW:
            recs = []
            if profitability['status'] == "UNDERPRICED":
                recs.append("Aumentar preços ou reduzir custos")
            if breakeven['pct_of_planned'] > 0.40:
                recs.append("Avaliar riscos de produção reduzida")
            return "⚠️ Projeto com recomendações: " + "; ".join(recs)
        else:
            return "🔴 NOGO - Projeto requer rework completo antes de execução"


def main():
    """Example usage"""
    print("=" * 60)
    print("Financial Validation Skill")
    print("=" * 60)
    
    skill = FinancialValidationSkill(None)
    
    # Example: Complete validation
    health = skill.generate_health_report(
        margin_pct=0.092,  # 9.2%
        breakeven_pct=0.25,  # 25% of planned
        direct_costs=1000000,
        indirect_costs=200000,
        revenue=1440000
    )
    
    print(f"\n{health['overall_status']} {health['go_nogo']}")
    print(f"\nMargem: {health['profitability']['margin_pct']:.2f}%")
    print(f"Break-even: {breakeven['pct_of_planned']:.1f}% of planned")
    print(f"\n{health['recommendation']}")


if __name__ == "__main__":
    main()
