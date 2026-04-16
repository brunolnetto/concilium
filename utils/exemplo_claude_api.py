#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exemplo Prático: Como usar a integração com Claude API (Anthropic)

Este arquivo mostra como:
1. Enviar tools + system prompt para Claude
2. Processar resposta do Claude
3. Executar skills baseado em tool_use blocks
4. Validar sequência e gates
5. Retornar resposta sem alucinações
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import json
from datetime import datetime

# Você precisará instalar: pip install anthropic
# from anthropic import Anthropic

from skills_integration_framework import (
    SkillsIntegrationFramework,
    ToolCallResult
)
from claude_agis_client import ClaudeAGISClient


@dataclass
class AnalysisRequest:
    """Request para análise de um plano AGIS"""
    project_name: str
    sheet_path: str
    query: str
    required_gates: List[str] = None


class AGISClaudeIntegration:
    """
    Integração completa com Claude API
    
    Fluxo:
    1. Usuário faz pergunta
    2. Sistema envia system prompt + tools para Claude
    3. Claude chama tools (não halucina)
    4. Sistema executa skills
    5. Sistema valida resultado
    6. Sistema retorna resposta verificada
    """
    
    def __init__(self):
        """Inicializa integração"""
        self.client = ClaudeAGISClient()
        self.framework = SkillsIntegrationFramework()
        self.conversations = {}  # Track conversations
    
    def prepare_api_request(self) -> Dict[str, Any]:
        """
        Prepara estrutura para enviar para Claude API
        
        Retorna:
            Dict com system, tools, e instruções para Claude
        """
        return {
            "system": self.client.create_system_message(),
            "tools": self.client.get_available_tools(),
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 4096,
            "instructions": {
                "enforce_tools": True,
                "validate_sequence": True,
                "require_all_gates": True
            }
        }
    
    def process_claude_response(
        self,
        response: Dict[str, Any],
        execution_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Processa resposta do Claude, valida e executa tools
        
        Args:
            response: Resposta completa do Claude (content blocks)
            execution_context: Contexto com dados de entrada
        
        Retorna:
            Dict com resultado validado ou erro
        """
        
        # Extrair tool_use blocks
        tool_calls = []
        final_response = None
        
        for block in response.get("content", []):
            if block.get("type") == "tool_use":
                tool_calls.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {})
                })
            elif block.get("type") == "text":
                final_response = block.get("text")
        
        # 1. Validar sequência de tools
        tool_sequence = [t["name"] for t in tool_calls]
        validation = self.client.validate_tool_call_sequence(tool_sequence)
        
        if not validation["valid"]:
            return {
                "success": False,
                "error": "Tool sequence invalid",
                "details": validation["errors"],
                "recovery": "Claude must reorganize tool calls"
            }
        
        # 2. Executar cada tool
        tool_results = []
        
        for tool_call in tool_calls:
            tool_name = tool_call["name"]
            tool_input = tool_call["input"]
            
            # Verificar se tool existe
            if tool_name not in self.framework.tools:
                return {
                    "success": False,
                    "error": f"Unknown tool: {tool_name}",
                    "recovery": "Claude referenced invalid tool"
                }
            
            # Executar skill correspondente
            try:
                result = self._execute_skill(
                    tool_name,
                    tool_input,
                    execution_context
                )
                
                tool_result = ToolCallResult(
                    tool_id=tool_name,
                    success=result["success"],
                    data=result.get("data"),
                    error=result.get("error")
                )
                
                # Log na framework
                self.client.process_tool_call(
                    tool_name,
                    tool_input,
                    tool_result
                )
                
                tool_results.append({
                    "tool": tool_name,
                    "input": tool_input,
                    "output": result
                })
                
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Tool execution failed: {tool_name}",
                    "details": str(e),
                    "recovery": "Check skill implementation"
                }
        
        # 3. Validar gates (camadas de validação)
        gates_result = self._validate_gates(tool_sequence, tool_results)
        
        if not gates_result["passed"]:
            return {
                "success": False,
                "error": "Validation gates failed",
                "gates": gates_result["gates"],
                "failed_gates": gates_result["failed"],
                "recovery": gates_result["recovery"]
            }
        
        # 4. Se tudo passou, retornar resposta
        return {
            "success": True,
            "tool_calls": len(tool_calls),
            "response": final_response,
            "validation": {
                "sequence_valid": validation["valid"],
                "all_gates_passed": gates_result["passed"],
                "gates_status": gates_result["gates"]
            },
            "audit_trail": self.client.generate_audit_trail_report()
        }
    
    def _execute_skill(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Executa o skill correspondente ao tool
        
        Em produção, isto chamaria as funções reais dos skills:
        - skills/1-base-data/skill.py
        - skills/2-operational-calc/skill.py
        - etc.
        """
        
        # Mapeamento de tools para skill functions
        skill_executors = {
            # Layer 1: Base Data
            "load_base_data": self._skill_load_base_data,
            "validate_base_data": self._skill_validate_base_data,
            
            # Layer 2: Operational Calc
            "calculate_crew_cost": self._skill_calculate_crew_cost,
            "validate_cost_delta": self._skill_validate_cost_delta,
            
            # Layer 3: Execution Planning
            "validate_schedule": self._skill_validate_schedule,
            "calculate_resultado": self._skill_calculate_resultado,
            
            # Layer 4: Financial Validation
            "validate_profitability": self._skill_validate_profitability,
            "generate_health_report": self._skill_generate_health_report,
        }
        
        if tool_name not in skill_executors:
            return {
                "success": False,
                "error": f"No executor for tool: {tool_name}"
            }
        
        # Executar o skill
        executor = skill_executors[tool_name]
        return executor(tool_input, context)
    
    # Skill Executors (Mock implementations)
    # Em produção, estas chamariam as funções reais dos arquivos skill.py
    
    def _skill_load_base_data(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Carrega tabela base"""
        table_name = input_params.get("table_name")
        
        # Em produção: from skills.base_data.skill import BaseDataSkill
        # skill = BaseDataSkill(context["sheet_path"])
        # return skill.load_table(table_name)
        
        return {
            "success": True,
            "data": {
                "table": table_name,
                "rows": 150,
                "columns": 8,
                "sample": "MÃO DE OBRA data loaded"
            }
        }
    
    def _skill_validate_base_data(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Valida integridade de dados"""
        table_name = input_params.get("table_name")
        
        return {
            "success": True,
            "data": {
                "table": table_name,
                "valid": True,
                "warnings": 0,
                "errors": 0
            }
        }
    
    def _skill_calculate_crew_cost(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Calcula custo de mão de obra com ENCARGOS"""
        activity = input_params.get("activity")
        labor = input_params.get("labor")
        duration = input_params.get("duration_months")
        apply_encargos = input_params.get("apply_encargos", True)
        
        # Mock: Base salary * number of people
        base_salary = 4000 * 2 * 3  # 2 people, 3 months
        
        if apply_encargos:
            # CRUCIAL: Apply 66% multiplier
            total = base_salary * (1 + 0.66)
        else:
            total = base_salary
        
        return {
            "success": True,
            "data": {
                "activity": activity,
                "base_salary": base_salary,
                "encargos_applied": apply_encargos,
                "encargos_multiplier": 0.66 if apply_encargos else 0,
                "total_cost": total
            }
        }
    
    def _skill_validate_cost_delta(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Valida convergência de custos"""
        fixed = input_params.get("fixed_cost", 0)
        sales = input_params.get("sales_cost", 0)
        tolerance = input_params.get("tolerance_pct", 5.0)
        
        delta_pct = abs((sales - fixed) / fixed * 100) if fixed else 0
        passed = delta_pct <= tolerance
        
        return {
            "success": passed,
            "data": {
                "fixed_cost": fixed,
                "sales_cost": sales,
                "delta_pct": delta_pct,
                "tolerance": tolerance,
                "passed": passed,
                "status": "PASS" if passed else f"FAIL - delta {delta_pct:.1f}% > {tolerance}%"
            }
        }
    
    def _skill_validate_schedule(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Valida cronograma"""
        activity = input_params.get("activity")
        total = input_params.get("total_qty", 0)
        accumulated = input_params.get("planned_accumulated", 0)
        
        completion_pct = (accumulated / total * 100) if total else 0
        passed = completion_pct >= 100
        
        return {
            "success": passed,
            "data": {
                "activity": activity,
                "total_qty": total,
                "accumulated": accumulated,
                "completion_pct": completion_pct,
                "passed": passed,
                "status": "ON_SCHEDULE" if passed else f"BEHIND - {completion_pct:.1f}%"
            }
        }
    
    def _skill_calculate_resultado(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Calcula RESULTADO financeiro"""
        direct = input_params.get("direct_costs", 0)
        indirect = input_params.get("indirect_costs", 0)
        revenue = input_params.get("revenues", 0)
        
        total_cost = direct + indirect
        profit = revenue - total_cost
        margin_pct = (profit / revenue * 100) if revenue else 0
        
        return {
            "success": True,
            "data": {
                "direct_costs": direct,
                "indirect_costs": indirect,
                "total_costs": total_cost,
                "revenues": revenue,
                "profit": profit,
                "margin_pct": margin_pct
            }
        }
    
    def _skill_validate_profitability(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Valida margem de lucro"""
        margin = input_params.get("margin_pct", 0) * 100
        
        low_target = 8.0
        high_target = 10.0
        
        passed = low_target <= margin <= high_target
        
        return {
            "success": passed,
            "data": {
                "margin_pct": margin,
                "target_range": f"{low_target}% - {high_target}%",
                "passed": passed,
                "status": "IN_RANGE ✅" if passed else f"OUT_OF_RANGE - {margin:.1f}%"
            }
        }
    
    def _skill_generate_health_report(self, input_params: Dict, context: Dict) -> Dict:
        """Mock: Gera relatório de saúde financeira"""
        margin = input_params.get("margin_pct", 0) * 100
        breakeven = input_params.get("breakeven_pct", 0) * 100
        direct = input_params.get("direct_costs", 0)
        indirect = input_params.get("indirect_costs", 0)
        revenue = input_params.get("revenue", 0)
        
        # Decisão: GO se margem dentro de range
        decision = "GO" if 8 <= margin <= 10 else "NOGO"
        confidence = 95 if 8 <= margin <= 10 else 60
        
        return {
            "success": True,
            "data": {
                "overall_status": decision,
                "confidence": confidence,
                "margin_pct": margin,
                "breakeven_pct": breakeven,
                "risks": [] if decision == "GO" else ["Profitability out of range"],
                "recommendation": f"Project is {decision}"
            }
        }
    
    def _validate_gates(
        self,
        tool_sequence: List[str],
        tool_results: List[Dict]
    ) -> Dict[str, Any]:
        """
        Valida todos os portões (gates) de validação
        
        Retorna True APENAS se TODAS as camadas passarem
        """
        
        gates = {
            "Gate 1 - Base Data": {
                "required": ["load_base_data", "validate_base_data"],
                "passed": False
            },
            "Gate 2 - Cost Convergence": {
                "required": ["calculate_crew_cost", "validate_cost_delta"],
                "passed": False
            },
            "Gate 3 - Schedule": {
                "required": ["validate_schedule"],
                "passed": False
            },
            "Gate 4 - Profitability": {
                "required": ["validate_profitability"],
                "passed": False
            }
        }
        
        # Check cada gate
        for gate_name, gate_info in gates.items():
            required = set(gate_info["required"])
            called = set(tool_sequence)
            
            if required.issubset(called):
                # Verificar se todos os tools retornaram success
                gate_info["passed"] = all(
                    result["output"]["success"]
                    for result in tool_results
                    if result["tool"] in required
                )
        
        all_passed = all(g["passed"] for g in gates.values())
        failed_gates = [name for name, g in gates.items() if not g["passed"]]
        
        return {
            "passed": all_passed,
            "gates": {name: g["passed"] for name, g in gates.items()},
            "failed": failed_gates,
            "recovery": "Fix failed gates before proceeding" if not all_passed else "All gates passed ✅"
        }


def example_usage():
    """
    Exemplo de como usar a integração na prática
    """
    
    integration = AGISClaudeIntegration()
    
    # 1. Preparar API request (enviado para Claude)
    print("\n" + "="*80)
    print("1. PREPARANDO API REQUEST")
    print("="*80)
    
    api_request = integration.prepare_api_request()
    print(f"\nSistema será enviado com:")
    print(f"  - Model: {api_request['model']}")
    print(f"  - Max tokens: {api_request['max_tokens']}")
    print(f"  - Tools: {len(api_request['tools'])} disponíveis")
    print(f"  - System prompt length: {len(api_request['system'])} chars")
    
    # 2. Simular resposta do Claude
    print("\n" + "="*80)
    print("2. SIMULANDO RESPOSTA DO CLAUDE")
    print("="*80)
    
    claude_response = {
        "content": [
            {
                "type": "tool_use",
                "id": "1",
                "name": "load_base_data",
                "input": {"table_name": "MÃO DE OBRA"}
            },
            {
                "type": "tool_use",
                "id": "2",
                "name": "validate_base_data",
                "input": {"table_name": "MÃO DE OBRA", "strict": True}
            },
            {
                "type": "tool_use",
                "id": "3",
                "name": "calculate_crew_cost",
                "input": {
                    "activity": "Escavação",
                    "labor": [{"role": "Operador", "qty": 2}],
                    "equipment": [{"name": "CAT-320", "qty": 1}],
                    "duration_months": 3,
                    "apply_encargos": True
                }
            },
            {
                "type": "tool_use",
                "id": "4",
                "name": "validate_cost_delta",
                "input": {
                    "service": "Escavação",
                    "fixed_cost": 24000,
                    "sales_cost": 24552,
                    "tolerance_pct": 5.0
                }
            },
            {
                "type": "tool_use",
                "id": "5",
                "name": "validate_schedule",
                "input": {
                    "activity": "Escavação",
                    "total_qty": 1500,
                    "planned_accumulated": 1500
                }
            },
            {
                "type": "tool_use",
                "id": "6",
                "name": "calculate_resultado",
                "input": {
                    "direct_costs": 24000,
                    "indirect_costs": 3000,
                    "revenues": 35000
                }
            },
            {
                "type": "tool_use",
                "id": "7",
                "name": "validate_profitability",
                "input": {"margin_pct": 0.086}
            },
            {
                "type": "tool_use",
                "id": "8",
                "name": "generate_health_report",
                "input": {
                    "margin_pct": 0.086,
                    "breakeven_pct": 0.054,
                    "direct_costs": 24000,
                    "indirect_costs": 3000,
                    "revenue": 35000
                }
            },
            {
                "type": "text",
                "text": "Based on the AGIS planning analysis, the project LOTE 09 is **GO**. All validation gates passed with a margin of 8.6%, which is within the target range of 8-10%."
            }
        ]
    }
    
    print("\nClaude called 8 tools in sequence:")
    for i, block in enumerate(claude_response["content"][:8], 1):
        print(f"  {i}. {block['name']}")
    
    # 3. Processar resposta do Claude
    print("\n" + "="*80)
    print("3. PROCESSANDO RESPOSTA DO CLAUDE")
    print("="*80)
    
    context = {"sheet_path": "/path/to/PLANEJAMENTO.xlsm"}
    
    result = integration.process_claude_response(claude_response, context)
    
    if result["success"]:
        print("\n✅ ANÁLISE VALIDADA COM SUCESSO")
        print(f"\nResposta do Claude:")
        print(result["response"])
        
        print(f"\nValidação:")
        print(f"  - Sequência de tools: ✅ VÁLIDA")
        print(f"  - Portões de validação: ✅ TODOS PASSARAM")
        print(f"  - Gate 1 (Base Data): ✅ PASS")
        print(f"  - Gate 2 (Cost Delta): ✅ PASS (2.3% < 5%)")
        print(f"  - Gate 3 (Schedule): ✅ PASS (100% completion)")
        print(f"  - Gate 4 (Profitability): ✅ PASS (8.6% in range 8-10%)")
    else:
        print(f"\n❌ ANÁLISE REJEITADA")
        print(f"Erro: {result['error']}")
        print(f"Detalhes: {result.get('details')}")
    
    # 4. Relatório de auditoria
    print("\n" + "="*80)
    print("4. RELATÓRIO DE AUDITORIA")
    print("="*80)
    
    if result["success"]:
        print(result["audit_trail"][:500] + "...")


if __name__ == "__main__":
    example_usage()
