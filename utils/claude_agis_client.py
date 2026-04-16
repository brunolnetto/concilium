#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude AGIS Skills Client - Example Integration

Shows how to:
1. Use the framework to validate Claude's tool calls
2. Enforce tool execution in correct order
3. Prevent hallucinations through validation gates
4. Generate audit trails
"""

import json
from typing import List, Dict, Any, Optional
from skills_integration_framework import (
    SkillsIntegrationFramework,
    ToolCallResult
)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ClaudeAGISClient:
    """
    Wrapper client that enforces tool usage when communicating with Claude
    """
    
    def __init__(self):
        """Initialize client with skills framework"""
        self.framework = SkillsIntegrationFramework()
        self.conversation_history = []
        self.tool_sequence = []
    
    def create_system_message(self) -> str:
        """
        Create system message that FORCES tool usage
        
        Returns:
            System prompt with tool definitions and enforcement rules
        """
        return self.framework.get_system_prompt()
    
    def get_available_tools(self) -> List[Dict]:
        """
        Get tool definitions for Claude API
        
        Returns:
            List of tool definitions in OpenAI/Claude format
        """
        return self.framework.get_tools_for_claude()
    
    def validate_tool_call_sequence(self, tool_calls: List[str]) -> Dict[str, Any]:
        """
        Validate that Claude called tools in correct dependency order
        
        Args:
            tool_calls: List of tool IDs Claude used
        
        Returns:
            Validation report with errors and warnings
        """
        validation = self.framework.validate_tool_sequence(tool_calls)
        
        logger.info(f"\n[VALIDATION] Checking tool sequence...")
        logger.info(f"Tools called: {tool_calls}")
        
        if validation["valid"]:
            logger.info("✅ Tool sequence is VALID")
        else:
            logger.error("❌ Tool sequence is INVALID:")
            for error in validation["errors"]:
                logger.error(f"   - {error}")
        
        for warning in validation["warnings"]:
            logger.warning(f"   ⚠️  {warning}")
        
        return validation
    
    def process_tool_call(
        self,
        tool_id: str,
        input_params: Dict[str, Any],
        tool_result: ToolCallResult
    ) -> bool:
        """
        Process and log a tool call from Claude
        
        Args:
            tool_id: ID of tool Claude called
            input_params: Parameters Claude provided
            tool_result: Result from tool execution
        
        Returns:
            True if tool call valid, False otherwise
        """
        # Verify tool exists
        if tool_id not in self.framework.tools:
            logger.error(f"❌ Unknown tool: {tool_id}")
            return False
        
        tool = self.framework.tools[tool_id]
        
        # Check required parameters
        missing_params = [
            p for p in tool.required_params
            if p not in input_params
        ]
        
        if missing_params:
            logger.error(f"❌ Missing required parameters for {tool_id}:")
            for param in missing_params:
                logger.error(f"   - {param}")
            return False
        
        # Log the tool call
        self.framework.log_tool_call(tool_id, input_params, tool_result)
        self.tool_sequence.append(tool_id)
        
        # Check for success
        if not tool_result.success:
            logger.error(f"❌ Tool {tool_id} failed: {tool_result.error}")
            return False
        
        logger.info(f"✅ Tool {tool_id} succeeded")
        return True
    
    def create_validation_gate(
        self,
        gate_name: str,
        required_tools: List[str],
        validation_func: callable
    ) -> Dict[str, Any]:
        """
        Create a validation gate that checks if tools were called
        
        Args:
            gate_name: Name of gate (e.g., "Base Data Validation")
            required_tools: Tools that must have been called
            validation_func: Function to validate gate conditions
        
        Returns:
            Gate validation result
        """
        result = {
            "gate": gate_name,
            "status": "PASS",
            "required_tools": required_tools,
            "missing_tools": [],
            "validation_passed": False
        }
        
        # Check if all required tools were called
        missing = [t for t in required_tools if t not in self.tool_sequence]
        if missing:
            result["status"] = "FAIL"
            result["missing_tools"] = missing
            return result
        
        # Run validation function
        try:
            result["validation_passed"] = validation_func()
            if not result["validation_passed"]:
                result["status"] = "FAIL"
        except Exception as e:
            result["status"] = "FAIL"
            result["error"] = str(e)
        
        return result
    
    def generate_audit_trail_report(self) -> str:
        """Generate human-readable audit trail"""
        trail = self.framework.get_audit_trail()
        
        report = "\n" + "="*80 + "\n"
        report += "AUDIT TRAIL - Tool Execution History\n"
        report += "="*80 + "\n\n"
        
        report += f"Total Tool Calls: {trail['total_calls']}\n\n"
        
        report += "By Tool:\n"
        for tool_id in sorted(trail['by_tool'].keys()):
            count = trail['by_tool'][tool_id]
            report += f"  {tool_id:30s}: {count:3d} call(s)\n"
        
        report += "\nCall Sequence:\n"
        for i, call in enumerate(trail['all_calls'], 1):
            status = "✅" if call['success'] else "❌"
            report += f"\n  {i}. {status} {call['tool_id']}\n"
            report += f"     Tool: {call['tool_name']}\n"
            report += f"     Time: {call['timestamp']}\n"
        
        return report


class ConversationSimulator:
    """Simulates a conversation with Claude to demonstrate enforcement"""
    
    def __init__(self):
        self.client = ClaudeAGISClient()
    
    def simulate_good_flow(self):
        """Simulate Claude following the correct tool sequence"""
        logger.info("\n" + "="*80)
        logger.info("SCENARIO 1: Claude FOLLOWS RULES (Correct Sequence)")
        logger.info("="*80)
        
        # Layer 1: Load base data
        logger.info("\n[LAYER 1] Loading base data...")
        result = ToolCallResult(
            tool_id="load_base_data",
            success=True,
            data={"rows": 150, "columns": 8}
        )
        self.client.process_tool_call(
            "load_base_data",
            {"table_name": "MÃO DE OBRA"},
            result
        )
        
        # Layer 1: Validate base data
        logger.info("[LAYER 1] Validating data...")
        result = ToolCallResult(
            tool_id="validate_base_data",
            success=True,
            data={"valid": True, "warnings": 0}
        )
        self.client.process_tool_call(
            "validate_base_data",
            {"table_name": "MÃO DE OBRA", "strict": True},
            result
        )
        
        # Layer 2: Calculate costs
        logger.info("[LAYER 2] Calculating crew cost...")
        result = ToolCallResult(
            tool_id="calculate_crew_cost",
            success=True,
            data={"total_cost": 450000.00, "base_salary": 271084.34, "with_encargos": 450000.00}
        )
        self.client.process_tool_call(
            "calculate_crew_cost",
            {
                "activity": "Escavação",
                "labor": [{"role": "Operador", "qty": 2}],
                "equipment": [{"name": "CAT-320", "qty": 1}],
                "duration_months": 3,
                "apply_encargos": True
            },
            result
        )
        
        # Layer 2: Validate convergence
        logger.info("[LAYER 2] Validating cost convergence...")
        result = ToolCallResult(
            tool_id="validate_cost_delta",
            success=True,
            data={"delta_pct": 2.3, "status": "PASS", "convergence": "Good"}
        )
        self.client.process_tool_call(
            "validate_cost_delta",
            {
                "service": "Escavação",
                "fixed_cost": 450000.00,
                "sales_cost": 460345.00,
                "tolerance_pct": 5.0
            },
            result
        )
        
        # Layer 3: Validate schedule
        logger.info("[LAYER 3] Validating schedule...")
        result = ToolCallResult(
            tool_id="validate_schedule",
            success=True,
            data={"completion": 100, "status": "ON_SCHEDULE"}
        )
        self.client.process_tool_call(
            "validate_schedule",
            {"activity": "Escavação", "total_qty": 1500, "planned_accumulated": 1500},
            result
        )
        
        # Layer 4: Validate profitability
        logger.info("[LAYER 4] Validating profitability...")
        result = ToolCallResult(
            tool_id="validate_profitability",
            success=True,
            data={"margin_pct": 9.2, "status": "IN_RANGE"}
        )
        self.client.process_tool_call(
            "validate_profitability",
            {"margin_pct": 0.092},
            result
        )
        
        # Layer 4: Generate health report
        logger.info("[LAYER 4] Generating financial health report...")
        result = ToolCallResult(
            tool_id="generate_health_report",
            success=True,
            data={
                "overall_status": "GO",
                "margin": 9.2,
                "confidence": 95,
                "risks": []
            }
        )
        self.client.process_tool_call(
            "generate_health_report",
            {
                "margin_pct": 0.092,
                "breakeven_pct": 0.045,
                "direct_costs": 450000,
                "indirect_costs": 50000,
                "revenue": 545000
            },
            result
        )
        
        # Validate sequence
        logger.info("\n[VALIDATION] Checking tool sequence...")
        validation = self.client.validate_tool_call_sequence(self.client.tool_sequence)
        
        if validation["valid"]:
            logger.info("✅ ALL GATES PASSED - Project is GO")
        
        print(self.client.generate_audit_trail_report())
    
    def simulate_bad_flow(self):
        """Simulate Claude trying to skip tools (hallucination attempt)"""
        logger.info("\n" + "="*80)
        logger.info("SCENARIO 2: Claude BREAKS RULES (Skips Tools)")
        logger.info("="*80)
        
        # Claude tries to skip Layer 1 and go directly to Layer 4
        logger.warning("\n❌ Claude attempts to skip base data validation and jump to profitability")
        
        # Try to call validate_profitability without prerequisite tools
        result = ToolCallResult(
            tool_id="validate_profitability",
            success=True,
            data={"margin_pct": 0.105}
        )
        
        success = self.client.process_tool_call(
            "validate_profitability",
            {"margin_pct": 0.105},
            result
        )
        
        # Validate sequence - this will fail
        logger.info("\n[VALIDATION] Checking tool sequence...")
        validation = self.client.validate_tool_call_sequence(self.client.tool_sequence)
        
        if not validation["valid"]:
            logger.error("\n❌ SEQUENCE VALIDATION FAILED")
            logger.error("Claude cannot proceed - must follow dependency chain")
        
        print("\nThis would be blocked by the framework!")


def main():
    """Run demonstration"""
    
    # Create client and show system setup
    client = ClaudeAGISClient()
    
    print("\n" + "="*80)
    print("AGIS SKILLS - CLAUDE INTEGRATION FRAMEWORK")
    print("="*80)
    
    print("\n📋 System Message (sent to Claude):")
    print("-" * 80)
    print(client.create_system_message()[:1000] + "\n... [truncated] ...\n")
    
    print("\n🔧 Available Tools (sent to Claude):")
    print("-" * 80)
    tools = client.get_available_tools()
    for tool in tools[:3]:
        print(f"\n{json.dumps(tool, indent=2, ensure_ascii=False)}")
    print(f"\n... and {len(tools)-3} more tools\n")
    
    # Run simulations
    simulator = ConversationSimulator()
    simulator.simulate_good_flow()
    simulator.simulate_bad_flow()


if __name__ == "__main__":
    main()
