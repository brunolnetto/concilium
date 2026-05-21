#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Operational Cost Calculation Skill for AGIS Planning

Manages:
- Direct crew costs (EQUIPE, Escavação e Carga)
- Indirect operational costs (ADM, TOP, LAB, QSMS, MOB)
- Cost reconciliation and validation (C_FIXO)

Author: AGIS Planning System
Version: 1.0.0
"""

import pandas as pd
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import json


@dataclass
class CrewCostResult:
    """Result of crew cost calculation"""
    activity: str
    monthly_labor: float
    monthly_equipment: float
    monthly_total: float
    duration_months: int
    total_cost: float
    breakdown: Dict[str, float]


@dataclass
class DeltaValidation:
    """C_FIXO Delta validation result"""
    service: str
    fixed_cost: float
    sales_cost: float
    delta: float
    delta_pct: float
    status: str  # "OK", "WARNING", "ERROR"
    message: str


class OperationalCalcSkill:
    """
    Skill for operational cost calculations
    """
    
    TABLE_DEFINITIONS = {
        "EQUIPE": {
            "description": "Equipe Direta - Mão de obra e equipamentos",
            "type": "crew_costs",
            "structure": "8 lines per activity"
        },
        "ADM": {
            "description": "Administração - Custos administrativos",
            "type": "indirect",
            "sections": ["labor", "infrastructure_monthly", "infrastructure_fixed"]
        },
        "TOP": {
            "description": "Topografia - Custos de topografia",
            "type": "crew_costs",
            "structure": "8 lines per activity"
        },
        "LAB": {
            "description": "Laboratório - Custos de laboratório",
            "type": "crew_costs",
            "structure": "8 lines per activity"
        },
        "QSMS": {
            "description": "QSMS - Custos de qualidade/segurança",
            "type": "crew_costs",
            "structure": "8 lines per activity"
        },
        "MOB": {
            "description": "Mobilização - Custos de mobilização",
            "type": "indirect",
            "sections": ["equipment_mob", "team_mob", "allowances", "benefits"]
        },
        "Escavação e Carga": {
            "description": "Equipe especializada de escavação",
            "type": "crew_costs",
            "structure": "8 lines per activity"
        },
        "C_FIXO": {
            "description": "Comparação custos fixos vs custos de venda",
            "type": "validation",
            "key_columns": ["Serviço", "Custo Fixo Total", "Custo de Venda", "DELTA"]
        }
    }
    
    def __init__(self, spreadsheet_path: str, base_skill=None):
        """
        Initialize skill
        
        Args:
            spreadsheet_path: Path to planning spreadsheet
            base_skill: Optional reference to BaseDataSkill for data loading
        """
        self.spreadsheet_path = spreadsheet_path
        self.base_skill = base_skill
        self._cache = {}
    
    def load_table(self, table_name: str) -> pd.DataFrame:
        """Load table via base_skill if available, else directly"""
        if self.base_skill:
            return self.base_skill.load_table(table_name)
        else:
            return pd.read_excel(self.spreadsheet_path, sheet_name=table_name)
    
    def calculate_crew_cost(self, 
                           activity: str,
                           labor: List[Dict[str, Any]],
                           equipment: List[Dict[str, Any]],
                           duration_months: int,
                           base_data: Optional[Dict] = None) -> CrewCostResult:
        """
        Calculate total crew cost for an activity
        
        Args:
            activity: Activity name
            labor: List of {"function": name, "qty": quantity}
            equipment: List of {"name": name, "qty": quantity}
            duration_months: Duration in months
            base_data: Optional pre-loaded base data with costs
        
        Returns:
            CrewCostResult with breakdown
        """
        if base_data is None:
            base_data = self._load_base_costs()
        
        # Calculate labor costs
        monthly_labor = 0.0
        labor_breakdown = {}
        
        for labor_item in labor:
            function = labor_item.get('function')
            qty = labor_item.get('qty', 1)
            
            if function in base_data.get('labor_costs', {}):
                cost_per_person = base_data['labor_costs'][function]
                item_cost = cost_per_person * qty
                monthly_labor += item_cost
                labor_breakdown[function] = item_cost
            else:
                labor_breakdown[f"{function} (NOT FOUND)"] = 0.0
        
        # Calculate equipment costs
        monthly_equipment = 0.0
        equipment_breakdown = {}
        
        for equip_item in equipment:
            equip_name = equip_item.get('name')
            qty = equip_item.get('qty', 1)
            
            if equip_name in base_data.get('equipment_costs', {}):
                cost_per_equip = base_data['equipment_costs'][equip_name]
                item_cost = cost_per_equip * qty
                monthly_equipment += item_cost
                equipment_breakdown[equip_name] = item_cost
            else:
                equipment_breakdown[f"{equip_name} (NOT FOUND)"] = 0.0
        
        # Calculate totals
        monthly_total = monthly_labor + monthly_equipment
        total_cost = monthly_total * duration_months
        
        breakdown = {
            "labor": labor_breakdown,
            "equipment": equipment_breakdown,
            "monthly_labor": monthly_labor,
            "monthly_equipment": monthly_equipment,
            "monthly_total": monthly_total
        }
        
        return CrewCostResult(
            activity=activity,
            monthly_labor=monthly_labor,
            monthly_equipment=monthly_equipment,
            monthly_total=monthly_total,
            duration_months=duration_months,
            total_cost=total_cost,
            breakdown=breakdown
        )
    
    def validate_cost_delta(self,
                           service: str,
                           fixed_cost: float,
                           sales_cost: float,
                           tolerance_pct: float = 0.05) -> DeltaValidation:
        """
        Validate C_FIXO delta (cost alignment)
        
        Args:
            service: Service name
            fixed_cost: Cost Fixo Total (from EQUIPE)
            sales_cost: Custo de Venda (from PLANEJAMENTO)
            tolerance_pct: Acceptable delta percentage (default 5%)
        
        Returns:
            DeltaValidation result
        """
        if fixed_cost == 0:
            delta_pct = float('inf') if sales_cost != 0 else 0
        else:
            delta = sales_cost - fixed_cost
            delta_pct = abs(delta) / fixed_cost
        
        # Determine status
        if delta_pct <= tolerance_pct:
            status = "OK"
            message = f"Custos alinhados (Delta: {delta_pct:.2%})"
        elif delta_pct <= tolerance_pct * 2:
            status = "WARNING"
            message = f"Pequena divergência (Delta: {delta_pct:.2%}) - Revisar"
        else:
            status = "ERROR"
            message = f"Grande divergência (Delta: {delta_pct:.2%}) - Corrigir"
        
        return DeltaValidation(
            service=service,
            fixed_cost=fixed_cost,
            sales_cost=sales_cost,
            delta=sales_cost - fixed_cost,
            delta_pct=delta_pct,
            status=status,
            message=message
        )
    
    def aggregate_indirect(self,
                          adm_cost: float,
                          topografia_cost: float,
                          laboratorio_cost: float,
                          qsms_cost: float,
                          mob_cost: float) -> float:
        """
        Aggregate all indirect costs
        
        Returns:
            Total indirect cost
        """
        return adm_cost + topografia_cost + laboratorio_cost + qsms_cost + mob_cost
    
    def validate_team_composition(self,
                                 activity: str,
                                 teams: int,
                                 labor_per_team: List[Dict],
                                 equipment_per_team: List[Dict]) -> Dict[str, Any]:
        """
        Validate team composition for reasonableness
        
        Args:
            activity: Activity name
            teams: Number of teams
            labor_per_team: Labor breakdown
            equipment_per_team: Equipment breakdown
        
        Returns:
            Validation report
        """
        issues = []
        
        total_people = sum(item.get('qty', 1) for item in labor_per_team) * teams
        total_equipment = sum(item.get('qty', 1) for item in equipment_per_team) * teams
        
        # Check: Not too many people per equipment
        if total_equipment > 0:
            people_per_equip = total_people / total_equipment
            if people_per_equip < 0.5:
                issues.append(f"⚠️ Few people per equipment ({people_per_equip:.1f})")
            elif people_per_equip > 5:
                issues.append(f"⚠️ Many people per equipment ({people_per_equip:.1f})")
        
        return {
            "activity": activity,
            "teams": teams,
            "total_people": total_people,
            "total_equipment": total_equipment,
            "issues": issues,
            "status": "OK" if not issues else "REVIEW"
        }
    
    def calculate_adm_infrastructure(self,
                                    items: List[Dict]) -> Dict[str, Any]:
        """
        Calculate administrative infrastructure costs
        
        Args:
            items: List of {"description": ..., "qty": ..., "unit_cost": ..., "months": ...}
        
        Returns:
            Breakdown and totals
        """
        breakdown = {}
        total_monthly = 0.0
        total_fixed = 0.0
        
        for item in items:
            key = item.get('description', 'unknown')
            qty = item.get('qty', 1)
            unit_cost = item.get('unit_cost', 0)
            months = item.get('months', 1)
            is_fixed = item.get('is_fixed', False)
            
            item_cost = qty * unit_cost
            
            if is_fixed:
                total_fixed += item_cost
            else:
                total_monthly += item_cost * months
            
            breakdown[key] = {
                "qty": qty,
                "unit_cost": unit_cost,
                "total": item_cost,
                "months": months,
                "is_fixed": is_fixed
            }
        
        return {
            "breakdown": breakdown,
            "monthly_total": total_monthly,
            "fixed_total": total_fixed,
            "grand_total": total_monthly + total_fixed
        }
    
    def calculate_mob_costs(self,
                           equipment_mob: Optional[Dict] = None,
                           team_mob: Optional[Dict] = None,
                           allowances: Optional[Dict] = None,
                           benefits: Optional[Dict] = None) -> Dict[str, float]:
        """
        Calculate mobilization costs (equipment, team, benefits)
        
        Returns:
            Breakdown by category
        """
        totals = {}
        
        if equipment_mob:
            totals['equipment_mobilization'] = equipment_mob.get('qty', 1) * equipment_mob.get('distance', 0) * equipment_mob.get('cost_per_km', 0)
            totals['equipment_demobilization'] = totals['equipment_mobilization']  # Usually same
        
        if team_mob:
            totals['team_mobilization'] = team_mob.get('people', 0) * team_mob.get('cost_per_person', 0)
        
        if allowances:
            # Housing, per diems, etc
            totals['allowances'] = allowances.get('qty', 0) * allowances.get('cost_per_person', 0) * allowances.get('months', 0)
        
        if benefits:
            # Meals, insurance, health, etc
            totals['benefits'] = benefits.get('qty', 0) * benefits.get('cost_per_person', 0) * benefits.get('months', 0)
        
        totals['total_mob'] = sum(totals.values())
        
        return totals
    
    def _load_base_costs(self) -> Dict[str, Dict]:
        """
        Load cost bases from DADOS, MÃO DE OBRA, EQUIPAMENTOS
        
        Returns:
            Dictionary with labor_costs and equipment_costs
        """
        if 'base_costs' in self._cache:
            return self._cache['base_costs']
        
        # This is simplified - in production would parse actual tables
        base_costs = {
            "labor_costs": {},
            "equipment_costs": {}
        }
        
        # Try to load if tables available
        try:
            mo_df = self.load_table("MÃO DE OBRA")
            for _, row in mo_df.iterrows():
                func_name = row.get('Função') or row.iloc[0]
                salary = row.get('Salário') or 0
                base_costs['labor_costs'][str(func_name)] = float(salary)
        except:
            pass
        
        try:
            eq_df = self.load_table("EQUIPAMENTOS")
            for _, row in eq_df.iterrows():
                eq_name = row.get('Equipamento') or row.iloc[0]
                eq_cost = row.get('Valor Mensal') or 0
                base_costs['equipment_costs'][str(eq_name)] = float(eq_cost)
        except:
            pass
        
        self._cache['base_costs'] = base_costs
        return base_costs
    
    def generate_cost_summary(self) -> Dict[str, Any]:
        """
        Generate summary of all operational costs
        
        Returns:
            Comprehensive cost summary
        """
        summary = {
            "timestamp": datetime.now().isoformat(),
            "direct_costs": {},
            "indirect_costs": {},
            "total": 0.0
        }
        
        try:
            # Load cost tables and aggregate
            for table in ["EQUIPE", "Escavação e Carga"]:
                try:
                    df = self.load_table(table)
                    # Simplified - would need to parse actual cost rows
                    summary['direct_costs'][table] = 0.0  # Placeholder
                except:
                    pass
            
            for table in ["ADM", "TOP", "LAB", "QSMS", "MOB"]:
                try:
                    df = self.load_table(table)
                    summary['indirect_costs'][table] = 0.0  # Placeholder
                except:
                    pass
        
        except Exception as e:
            summary['error'] = str(e)
        
        return summary


def main():
    """Example usage"""
    print("Operational Calculation Skill")
    print("=" * 60)
    
    # Example: Calculate crew cost
    skill = OperationalCalculationSkill(None)
    
    result = skill.calculate_crew_cost(
        activity="ESCAVAÇÃO",
        labor=[
            {"function": "OPERADOR DE ESCAVADEIRA", "qty": 1},
            {"function": "AJUDANTE", "qty": 2}
        ],
        equipment=[
            {"name": "ESCAVADEIRA", "qty": 1}
        ],
        duration_months=3,
        base_data={
            "labor_costs": {
                "OPERADOR DE ESCAVADEIRA": 6300,
                "AJUDANTE": 2500
            },
            "equipment_costs": {
                "ESCAVADEIRA": 15000
            }
        }
    )
    
    print(f"\nAtividade: {result.activity}")
    print(f"  MO Mensal: R$ {result.monthly_labor:,.0f}")
    print(f"  Equip Mensal: R$ {result.monthly_equipment:,.0f}")
    print(f"  Total Mensal: R$ {result.monthly_total:,.0f}")
    print(f"  Duração: {result.duration_months} meses")
    print(f"  TOTAL: R$ {result.total_cost:,.0f}")


if __name__ == "__main__":
    main()
