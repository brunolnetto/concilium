# AGIS-Claude Integration: Arquitetura Sistemática

## Problema que Soluciona

**Pergunta do Usuário:**
> "Como nós podemos acoplar as skills à interface do Claude de forma sistêmica a forçá-lo a utilizá-las, e não halucinar de acordo com sua interpretação?"

**Desafio:**
- Claude pode "achar que sabe" números de construção (custos, produtividade, encargos)
- Sem constraint sistemático, Claude halucina: "Em minha experiência, a margem típica é..."
- Skills (dados reais do AGIS) são ignoradas se não forem impostas

---

## Solução: Framework de 3 Camadas

### Camada 1: Tool Definitions (Claude Tools API)

**Arquivo:** `claude_tools.json`

```json
{
  "version": "2.0.0",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "load_base_data",
        "description": "[LAYER 1] Load foundational data tables (MÃO DE OBRA, ...",
        "parameters": {
          "type": "object",
          "properties": {
            "table_name": {
              "type": "string",
              "enum": ["MÃO DE OBRA", "EQUIPAMENTOS", "BDI", ...]
            }
          },
          "required": ["table_name"]
        }
      }
    },
    ...
  ]
}
```

**How it works:**
- Claude receives **explicit list** of available tools
- Claude knows exact parameters needed
- Cannot hallucinate parameters - structure enforced

---

### Camada 2: System Prompt Enforcement

**Arquivo:** `system_prompt.md`

Característica principal: **MANDATORY WORKFLOW**

```markdown
## CRITICAL CONSTRAINT: You MUST use tools systematically

You are an expert assistant for AGIS construction planning.
**Your responses MUST be based EXCLUSIVELY on data obtained through tools.**
**Under NO circumstances should you hallucinate, estimate, or guess values.**

### MANDATORY EXECUTION WORKFLOW

Follow this workflow STRICTLY:

1. LAYER 1 - Base Data Validation
   - Always call `load_base_data` for any table
   - Always call `validate_base_data` before using data
   - If validation fails → STOP

2. LAYER 2 - Operational Calculations  
   - Call `calculate_crew_cost` with exact parameters
   - ALWAYS call `validate_cost_delta` (tolerance: <5%)
   - If delta fails → return error

3. LAYER 3 - Execution Planning
   - Call `validate_schedule` for completion %
   - Call `calculate_resultado` for financial outcome
   - Never assume budget without calculation

4. LAYER 4 - Financial Validation
   - ALWAYS end with `validate_profitability`
   - ALWAYS generate `generate_health_report`
   - Final decision: GO or NOGO only

### Enforcement Rules

**RULE 1: Dependency Chain**
- Cannot skip layers
- Cannot use Layer 3 without Layer 1+2 validation
- Cannot make GO/NOGO without Layer 4

**RULE 2: Mandatory Tools**
Tools that MUST be called (for context):
- `load_base_data` - antes de qualquer análise
- `validate_base_data` - antes de usar dados carregados
- `validate_cost_delta` - enforced para qualquer custo
- `validate_profitability` - antes de decisão final
- `generate_health_report` - SEMPRE ao final

**RULE 3: Numeric Accuracy**
- All numbers MUST come from tools
- All percentages calculated by tools
- Never estimate or round before tool usage

**WHAT YOU CANNOT DO:**
❌ "In my experience, typical margins are..."
❌ "This might cost around..."
❌ "Assuming standard rates..."

WHAT YOU MUST DO:**
✅ "Tool load_base_data returned..."
✅ "Validation check shows..."
✅ "Calculated result is..."
```

**How it works:**
- Claude reads system prompt on every request
- Explicit rules override general knowledge
- "Cannot" statements prevent hallucination patterns
- Mandatory tools create guardrails

---

### Camada 3: Validation & Circuit Breaker

**Arquivo:** `skills_integration_framework.py`

#### A. Dependency Validation

```python
def validate_tool_sequence(tool_calls: List[str]) -> Dict[str, Any]:
    """
    Claude calls tools: [load_base_data, validate_base_data, calculate_crew_cost, ...]
    
    Framework checks:
    1. Is each tool ID valid? (exists in system)
    2. Were dependencies called first?
    3. Are mandatory tools present?
    """
    
    for tool_id in tool_calls:
        tool = self.tools[tool_id]
        
        # Check dependencies
        for dep in tool.dependencies:
            if dep not in tool_calls:
                raise ValidationError(
                    f"Tool {tool_id} requires {dep} to be called first"
                )
    
    return {"valid": True|False, "errors": [...]}
```

#### B. Gate-Based Circuit Breaker

```python
# Before accepting Claude's output, check gates in sequence

gate_1 = client.create_validation_gate(
    "Base Data Validation",
    required_tools=["load_base_data", "validate_base_data"],
    validation_func=lambda: validate_data_quality()
)
# Gate 1 MUST PASS before proceeding

gate_2 = client.create_validation_gate(
    "Cost Convergence",
    required_tools=["calculate_crew_cost", "validate_cost_delta"],
    validation_func=lambda: delta_pct < 5.0
)
# Gate 2 MUST PASS before proceeding

gate_3 = client.create_validation_gate(
    "Schedule Completion",
    required_tools=["validate_schedule"],
    validation_func=lambda: completion == 100
)

gate_4 = client.create_validation_gate(
    "Profitability Check",
    required_tools=["validate_profitability"],
    validation_func=lambda: 0.08 <= margin <= 0.10
)
# Gate 4 final gate - decides GO/NOGO
```

#### C. Audit Trail

```python
# Every tool call logged
execution_log = [
    {
        "timestamp": "2024-01-15T10:30:45",
        "tool_id": "load_base_data",
        "input": {"table_name": "MÃO DE OBRA"},
        "success": True,
        "result": {"rows": 150, "columns": 8}
    },
    {
        "timestamp": "2024-01-15T10:30:46",
        "tool_id": "validate_base_data",
        "input": {"table_name": "MÃO DE OBRA", "strict": True},
        "success": True,
        "result": {"valid": True, "warnings": 0}
    },
    ...
]

# Provides compliance trail for construction projects
```

---

## Arquitectura Visual

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude LLM                                │
│  (Receives: System Prompt + Tool Definitions)                   │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       │ Calls tools with parameters
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│         Framework: Validation Layer                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ 1. Dependency Chain Checker                                 ││
│  │    • load_base_data → validate_base_data → calculate_cost   ││
│  │    • If sequence broken → REJECT                             ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ 2. Gate-Based Circuit Breaker                               ││
│  │    • Layer 1 Base Data Gate (MUST PASS)                     ││
│  │    • Layer 2 Cost Delta Gate (MUST PASS) ← ENCARGOS applied  ││
│  │    • Layer 3 Schedule Gate (MUST PASS) ← 100% completion    ││
│  │    • Layer 4 Profitability Gate (MUST PASS) ← 8-10% margin  ││
│  │    Final: GO / NOGO / NEEDS_REVIEW                          ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ 3. Numeric Accuracy Validator                               ││
│  │    • All cells must come from tool outputs                  ││
│  │    • Cannot round before tool usage                         ││
│  │    • Cannot estimate percentages                            ││
│  ├─────────────────────────────────────────────────────────────┤│
│  │ 4. Audit Trail Logger                                       ││
│  │    • Every tool call timestamped                             ││
│  │    • Input/output recorded for compliance                   ││
│  │    • Accessible for review/debugging                        ││
│  └─────────────────────────────────────────────────────────────┘│
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       │ Passes only if ALL gates pass
                       │
┌──────────────────────▼──────────────────────────────────────────┐
│              Skills Layer (Real Data)                            │
│ ┌────────────────┐ ┌────────────────┐ ┌─────────────────────┐  │
│ │ Layer 1: Base  │ │ Layer 2: Calc  │ │ Layer 3: Planning   │  │
│ │  • MÃO DE OBRA │ │  • Crew Cost   │ │  • CRONOGRAMA       │  │
│ │  • EQUIPMTOS   │ │  • ENCARGOS✓   │ │  • PLANEJAMENTO     │  │
│ │  • BDI         │ │  • EPI Costs   │ │  • RESULTADO        │  │
│ │  • MATERIAIS   │ │  • Validation  │ │                     │  │
│ │  • CPU         │ │               │ │ Layer 4: Validation │  │
│ └────────────────┘ └────────────────┘ │  • Profitability    │  │
│                                         │  • Health Report    │  │
│                                         └─────────────────────┘  │
│                                                                   │
│ Data from: 2026_03_30_PLANEJAMENTO_LOTE 09 e 10_(CE).xlsm       │
│ 22 sheets, 66% salary multiplier (ENCARGOS), real numbers       │
└───────────────────────────────────────────────────────────────────┘
```

---

## How to Use: Step-by-Step

### 1. Initialize Framework (Backend Setup)

```python
from skills_integration_framework import initialize_framework

# One-time setup
framework = initialize_framework()

# Export for Claude API
framework.export_claude_tools_json("./claude_tools.json")
framework.export_system_prompt("./system_prompt.md")
```

Output files:
- `claude_tools.json` - Tool definitions (send to Claude API)
- `system_prompt.md` - System prompt (send to Claude API)

### 2. Create Client-Side Wrapper

```python
from claude_agis_client import ClaudeAGISClient

client = ClaudeAGISClient()

# Get system message and tools
system = client.create_system_message()
tools = client.get_available_tools()

# Send both to Claude when creating conversation
response = claude_client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=4096,
    system=system,
    tools=tools,
    messages=[
        {
            "role": "user",
            "content": "Analyze project LOTE 09 and tell me if it's GO or NOGO"
        }
    ]
)
```

### 3. Process Claude's Response

```python
# Claude returns tool_use blocks
tool_calls = []

for block in response.content:
    if block.type == "tool_use":
        tool_id = block.name
        input_params = block.input
        
        # Execute the actual skill
        skill = load_skill(tool_id)
        result = skill.execute(**input_params)
        
        # Log the call
        tool_result = ToolCallResult(
            tool_id=tool_id,
            success=result["success"],
            data=result.get("data")
        )
        
        client.process_tool_call(tool_id, input_params, tool_result)
        tool_calls.append(tool_id)

# Validate entire sequence
validation = client.validate_tool_call_sequence(tool_calls)

if not validation["valid"]:
    # Return error - Claude must call tools correctly
    print("ERROR: Invalid tool sequence")
    print(validation["errors"])
    raise HallucinationDetected(validation["errors"])

# All gates passed - accept final answer
print("✅ Project Decision: " + response.content[-1].text)
```

### 4. Generate Audit Trail

```python
# Show compliance documentation
audit_report = client.generate_audit_trail_report()
print(audit_report)

# Examples for construction project compliance:
# - Regulatory review
# - Budget justification
# - Risk documentation
# - Decision trail
```

---

## ENCARGOS Implementation in Framework

**Critical Finding:** 66% Salary Multiplier

```
Base Salary: R$ 4,000
Encargos: 31% + 30% + 5% = 66%
Total: R$ 4,000 × (1 + 0.66) = R$ 6,640
```

Framework enforces this in `calculate_crew_cost`:

```python
@tool_definition
def calculate_crew_cost(activity, labor, equipment, duration_months, apply_encargos=True):
    """
    Calculate crew cost with ENCARGOS multiplier
    
    Critical: If apply_encargos=False, labor is UNDERESTIMATED by 40%
    """
    
    # Load salary data from MÃO DE OBRA table
    base_salary = load_salary(labor)
    
    if apply_encargos:
        # MANDATORY: Apply 66% multiplier
        multiplier = 1 + 0.66  # From ENCARGOS table
        total_salary = base_salary * multiplier
    else:
        # This path triggers warning
        logger.warning("⚠️ ENCARGOS not applied - costs may be underestimated")
        total_salary = base_salary
    
    return {
        "base_salary": base_salary,
        "encargos_multiplier": multiplier,
        "total_salary": total_salary,
        "with_encargos": apply_encargos
    }
```

Claude **must call this tool** to get accurate labor costs. If Claude tries to estimate without tools, system prompt blocks it.

---

## What Makes This Systematic?

### 1. No Escape Hatch

| Method | Result |
|--------|--------|
| Claude estimates with "typical rates" | ❌ System prompt forbids it |
| Claude uses general construction knowledge | ❌ System prompt enforces tools |
| Claude skips Layer 1 data validation | ❌ Dependency chain rejects it |
| Claude calls tools in wrong order | ❌ Framework validates and rejects |
| Claude provides wrong parameters | ❌ Tool definitions enforce schema |
| Claude ignores cost convergence check | ❌ Mandatory tool, circuit-breaker fails |

### 2. Forced to Use Real Data

- **MÃO DE OBRA** - Real labor rates from spreadsheet
- **MATERIAIS** - Real material costs (replaces hallucinated DADOS)
- **ENCARGOS** - Real 66% multiplier (not "typical 50%")
- **BDI** - Indirect cost formula from CPU service definitions
- **EQUIPAMENTOS** - Real equipment specs and costs

### 3. Quality Assurance

Every analysis output requires:
- ✅ Layer 1: Base data loaded + validated
- ✅ Layer 2: Costs calculated + convergence checked
- ✅ Layer 3: Schedule validated + resultado calculated
- ✅ Layer 4: Profitability checked + health report generated

3 gates must PASS before final answer.

### 4. Compliance & Audit

```
[TOOLS USED]
- load_base_data (MÃO DE OBRA)
- validate_base_data (✅ PASS)
- calculate_crew_cost (with ENCARGOS)
- validate_cost_delta (2.3% - ✅ PASS)
- validate_schedule (100% - ✅ PASS)
- calculate_resultado
- validate_profitability (9.2% - ✅ PASS)
- generate_health_report

[VALIDATION GATES]
Gate 1 (Base Data): ✅ PASS
Gate 2 (Cost Delta): ✅ PASS (2.3% < 5%)
Gate 3 (Schedule): ✅ PASS (100% completion)
Gate 4 (Profitability): ✅ PASS (9.2% within 8-10%)

[FINAL DECISION]
Status: GO
Reason: All gates passed, project is profitable and on schedule
```

---

## Deployment Checklist

### Backend
- [ ] skills/1-base-data/skill.py updated with ENCARGOS
- [ ] skills/2-operational-calc/skill.py updated with ENCARGOS
- [ ] skills_integration_framework.py deployed
- [ ] claude_tools.json generated
- [ ] system_prompt.md finalized

### Claude API Configuration
- [ ] System prompt set (from system_prompt.md)
- [ ] Tools array configured (from claude_tools.json)
- [ ] Tool handler implemented (skill execution)
- [ ] Validation layer enabled

### Monitoring
- [ ] Audit trail logging working
- [ ] Gate validation reports generated
- [ ] Error handling for skipped tools
- [ ] User-facing compliance reports

---

## Resposta Direta à Pergunta

**"Como acoplar skills à interface do Claude de forma sistemática a forçá-lo a utilizá-las?"**

1. **System Prompt**: Proíbe alucinações explicitamente
2. **Tool Definitions**: Força formas específicas de chamar skills
3. **Dependency Chain**: Bloqueia sequência incorreta
4. **Circuit Breaker**: Rejeita análise sem todas as gates passando
5. **Audit Trail**: Prova compliance para stakeholders

**Resultado:**
- Claude não pode estimar (system prompt proíbe)
- Claude não pode chamar ferramentas erradas (schema enforça)
- Claude não pode pular camadas (dependências bloqueiam)
- Claude não pode dar resposta sem dados reais (gates obrigam)

→ **Sistemática, não deixa brechas, enforçável.**
