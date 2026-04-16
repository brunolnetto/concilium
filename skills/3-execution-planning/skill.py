#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Execution Planning Skill

Manages CRONOGRAMA, PLANEJAMENTO, and RESULTADO
"""

import pandas as pd
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ScheduleValidation:
    """Schedule validation result"""
    activity: str
    total_quantity: float
    planned_accumulated: float
    completion_pct: float
    status: str  # "OK", "INCOMPLETE", "OVERCOMPLETE"
    message: str


class ExecutionPlanningSkill:
    """
    Manages project scheduling and budget planning
    """
    
    MONTHS = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN",
              "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]
    
    def __init__(self, spreadsheet_path: str, operational_skill=None):
        self.spreadsheet_path = spreadsheet_path
        self.operational_skill = operational_skill
    
    def load_cronograma(self) -> pd.DataFrame:
        """Load CRONOGRAMA table"""
        return pd.read_excel(self.spreadsheet_path, sheet_name="CRONOGRAMA")
    
    def load_planejamento(self) -> pd.DataFrame:
        """Load PLANEJAMENTO table"""
        return pd.read_excel(self.spreadsheet_path, sheet_name="PLANEJAMENTO")
    
    def load_resultado(self) -> pd.DataFrame:
        """Load RESULTADO table"""
        return pd.read_excel(self.spreadsheet_path, sheet_name="RESULTADO")
    
    def validate_schedule(self, activity: str, 
                         total_qty: float,
                         planned_accumulated: float) -> ScheduleValidation:
        """
        Validate that scheduled quantity reaches 100%
        
        Args:
            activity: Activity name
            total_qty: Total quantity to execute
            planned_accumulated: Accumulated planned quantity
        
        Returns:
            ScheduleValidation result
        """
        if total_qty == 0:
            completion_pct = 0
        else:
            completion_pct = planned_accumulated / total_qty
        
        if abs(completion_pct - 1.0) < 0.01:  # Within 1%
            status = "OK"
            message = "✅ Cronograma 100%"
        elif completion_pct < 1.0:
            status = "INCOMPLETE"
            message = f"⚠️ Cronograma incompleto ({completion_pct:.1%})"
        else:
            status = "OVERCOMPLETE"
            message = f"⚠️ Cronograma excedido ({completion_pct:.1%})"
        
        return ScheduleValidation(
            activity=activity,
            total_quantity=total_qty,
            planned_accumulated=planned_accumulated,
            completion_pct=completion_pct,
            status=status,
            message=message
        )
    
    def calculate_bdi(self, 
                     base_cost: float,
                     bdi_percentages: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate costs with BDI applied
        
        Args:
            base_cost: Cost without BDI
            bdi_percentages: {"Material": 25, "Diesel": 20, "Labor": 15, "Equipment": 12}
        
        Returns:
            Dictionary with costs by category
        """
        average_bdi = sum(bdi_percentages.values()) / len(bdi_percentages)
        cost_with_bdi = base_cost * (1 + average_bdi / 100)
        
        return {
            "base_cost": base_cost,
            "average_bdi_pct": average_bdi,
            "cost_with_bdi": cost_with_bdi,
            "markup_amount": cost_with_bdi - base_cost
        }
    
    def reconcile_planning(self,
                          equipment_costs: float,
                          planning_costs: float,
                          tolerance_pct: float = 0.05) -> Dict[str, Any]:
        """
        Reconcile equipment costs vs planning costs
        
        Returns:
            Reconciliation report
        """
        if equipment_costs == 0:
            delta_pct = 0
        else:
            delta = planning_costs - equipment_costs
            delta_pct = abs(delta) / equipment_costs
        
        return {
            "equipment_cost": equipment_costs,
            "planning_cost": planning_costs,
            "delta": planning_costs - equipment_costs,
            "delta_pct": delta_pct,
            "status": "OK" if delta_pct <= tolerance_pct else "REVIEW",
            "message": f"Divergência: {delta_pct:.2%}"
        }
    
    def calculate_resultado(self,
                           direct_costs: float,
                           indirect_costs: float,
                           revenues: float) -> Dict[str, Any]:
        """
        Calculate financial result
        
        Args:
            direct_costs: Sum of service costs from PLANEJAMENTO
            indirect_costs: Sum of ADM, TOP, LAB, QSMS, MOB
            revenues: Total revenue (direct + indirect with BDI)
        
        Returns:
            Financial summary
        """
        total_costs = direct_costs + indirect_costs
        profit = revenues - total_costs
        
        if revenues > 0:
            margin_pct = (profit / revenues) * 100
        else:
            margin_pct = 0
        
        # Evaluate against target 8-10%
        if 8 <= margin_pct <= 10:
            viability = "VIABLE"
            recommendation = "✅ Margem dentro do target"
        elif margin_pct < 8:
            viability = "UNDERPRICED"
            recommendation = "❌ Projeto com margem baixa - Aumentar preços"
        else:
            viability = "OVERPRICED"
            recommendation = "⚠️ Preços podem estar acima do mercado"
        
        return {
            "direct_costs": direct_costs,
            "indirect_costs": indirect_costs,
            "total_costs": total_costs,
            "revenues": revenues,
            "profit": profit,
            "margin_pct": margin_pct,
            "viability": viability,
            "recommendation": recommendation,
            "timestamp": datetime.now().isoformat()
        }


def main():
    """Example usage"""
    print("=" * 60)
    print("Execution Planning Skill")
    print("=" * 60)
    
    skill = ExecutionPlanningSkill(None)
    
    # Example: Calculate resultado
    result = skill.calculate_resultado(
        direct_costs=1000000,
        indirect_costs=200000,
        revenues=1440000  # 20% higher than costs for margin
    )
    
    print(f"\nCustos Diretos: R$ {result['direct_costs']:,.0f}")
    print(f"Custos Indiretos: R$ {result['indirect_costs']:,.0f}")
    print(f"Custos Totais: R$ {result['total_costs']:,.0f}")
    print(f"\nReceita: R$ {result['revenues']:,.0f}")
    print(f"Lucro: R$ {result['profit']:,.0f}")
    print(f"Margem: {result['margin_pct']:.2f}%")
    print(f"\nStatusvabilidade: {result['viability']}")
    print(f"Recomendação: {result['recommendation']}")


if __name__ == "__main__":
    main()
