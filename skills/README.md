# AGIS Planning Domain Skills

**Framework:** Skills.sh (adapted for Python)  
**Version:** 1.0.0  
**Purpose:** Modular domain skills for AGIS construction project planning spreadsheet analysis and manipulation

---

## 📋 Overview

This skills package provides a structured, layered approach to managing  the complex AGIS planning spreadsheet. The skills are organized in **4 layers** following the spreadsheet's natural workflow:

```
Layer 1: BASE DATA       (Input foundations)
    ↓
Layer 2: OPERATIONAL    (Cost calculations)
    ↓
Layer 3: EXECUTION      (Scheduling & budgeting)
    ↓
Layer 4: VALIDATION     (Financial health checks)
```

---

## 📁 Directory Structure

```
skills/
├── manifest.json                          ← Master manifest (skills registry)
├── base-data/                             ← Layer 1
│   ├── manifest.json
│   ├── skill.md                           ← Documentation
│   └── skill.py                           ← Implementation
├── operational-calc/                      ← Layer 2
│   ├── manifest.json
│   ├── skill.md
│   └── skill.py
├── execution-planning/                    ← Layer 3
│   ├── manifest.json
│   ├── skill.md
│   └── skill.py
├── financial-validation/                  ← Layer 4
│   ├── manifest.json
│   ├── skill.md
│   └── skill.py
└── README.md                              ← This file
```

---

## 🎯 Skills Summary

### Skill 1: `base-data` (Layer 1)
**Tables:** DADOS, PRODUÇÕES, PRATICABILIDADE, MÃO DE OBRA, EQUIPAMENTOS, BDI

**Purpose:** Manage foundational data tables

**Key Operations:**
- `load_table()` - Load table from spreadsheet
- `validate_data()` - Data quality checks
- `sync_references()` - Verify exact name matching
- `export_table()` - Export processed data

**Key Concern:** ⚠️ **Exact name matching** in MÃO DE OBRA and EQUIPAMENTOS

---

### Skill 2: `operational-calc` (Layer 2)
**Tables:** EQUIPE, ADM, TOP, LAB, QSMS, MOB, Escavação e Carga, C_FIXO

**Purpose:** Calculate crew and administrative costs

**Key Operations:**
- `calculate_crew_cost()` - Total team cost for activity
- `validate_cost_delta()` - Check C_FIXO alignment (< 5% delta required)
- `aggregate_indirect()` - Sum all indirect costs
- `calculate_adm_infrastructure()` - Infrastructure cost breakdown
- `calculate_mob_costs()` - Mobilization and benefits

**Key Concern:** ⚠️ **C_FIXO validation** - costs must align between EQUIPE and PLANEJAMENTO

---

### Skill 3: `execution-planning` (Layer 3)
**Tables:** CRONOGRAMA, PLANEJAMENTO, RESULTADO

**Purpose:** Schedule activities and create budget with BDI

**Key Operations:**
- `validate_schedule()` - Check CRONOGRAMA reaches 100%
- `calculate_bdi()` - Apply markup factors
- `reconcile_planning()` - Align costs across tables
- `calculate_resultado()` - Financial summary

**Key Concern:** ⚠️ **BDI application** - must result in 8-10% target margin

---

### Skill 4: `financial-validation` (Layer 4)
**Tables:** RESULTADO, PONTO DE EQUILIBRIO

**Purpose:** Validate financial viability and perform risk analysis

**Key Operations:**
- `validate_profitability()` - Check margin against 8-10% target
- `calculate_breakeven()` - Determine break-even quantity
- `sensitivity_analysis()` - Model cost/price variations
- `generate_health_report()` - Comprehensive financial assessment

**Key Concern:** ⚠️ **Viability gate** - project must pass financial validation before execution

---

## 🚀 Quick Start

### 1. Load the Master Registry
```python
import json

with open('skills/manifest.json') as f:
    registry = json.load(f)

print(f"Available skills: {[s['id'] for s in registry['skills']]}")
print(f"Groups: {list(registry['groups'].keys())}")
```

### 2. Use a Single Skill
```python
from base_data.skill import BaseDataSkill

spreadsheet = r"C:\...\2026_03_30_PLANEJAMENTO_LOTE 09 e 10_(CE).xlsx"
skill = BaseDataSkill(spreadsheet)

# Validate all base tables
report = skill.generate_health_report()
print(report)
# Output: {'timestamp': '...', 'overall_status': 'HEALTHY', ...}
```

### 3. Chain Skills for Complete Analysis
```python
from base_data.skill import BaseDataSkill
from operational_calc.skill import OperationalCalcSkill
from execution_planning.skill import ExecutionPlanningSkill
from financial_validation.skill import FinancialValidationSkill

# Initialize skills in sequence
base = BaseDataSkill(spreadsheet)
ops = OperationalCalcSkill(spreadsheet, base_skill=base)
exec = ExecutionPlanningSkill(spreadsheet, operational_skill=ops)
fin = FinancialValidationSkill(spreadsheet, execution_skill=exec)

# Run complete validation
base_health = base.generate_health_report()
print(f"Base Data: {base_health['overall_status']}")

# ... continue with operational, execution, financial
```

---

## 🔄 Data Flow (Dependencies)

```
MeteoBLUE Website
    ↓ (Climate data)
    → PRATICABILIDADE (input: days of rain)

Budget/Finance System
    ↓ (Unit costs)
    → DADOS, BDI (input: salary, equipment costs, margins)

HR System
    ↓ (Labor costs)
    → MÃO DE OBRA (input: function names, salaries)

Equipment Manager
    ↓ (Equipment inventory & costs)
    → EQUIPAMENTOS (input: equipment names, monthly costs)

Engineering Team
    ↓ (Activity definitions)
    → PRODUÇÕES (input: production hourly rates)


All Base Data Tables
    ↓ (via base-data skill)
    ↓
EQUIPE, ADM, TOP, LAB, QSMS, MOB
    ↓ (via operational-calc skill)
    ↓
CRONOGRAMA, PLANEJAMENTO
    ↓ (via execution-planning skill)
    ↓
RESULTADO, PONTO DE EQUILIBRIO
    ↓ (via financial-validation skill)
    ↓
PROJECT VIABILITY GATE
    ↓
EXECUTION or REWORK
```

---

## ✅ Quality checkpoints

**Checkpoint 1: Base Data Validation**
```
Location: base-data/skill.py::validate_all()
Checks:
  ✓ No nulls in critical columns
  ✓ No duplicates in reference tables
  ✓ Names match exactly between MÃO DE OBRA, EQUIPAMENTOS
  ✓ Monthly alignment in PRATICABILIDADE
Status: PASS if all checks pass
```

**Checkpoint 2: Cost Alignment**
```
Location: operational-calc/skill.py::validate_cost_delta()
Checks:
  ✓ EQUIPE monthly cost × months = Custo Fixo Total
  ? Custo Fixo Total ≈ Custo de Venda (delta < 5%)
Status: PASS if |delta| < 5%
```

**Checkpoint 3: Schedule Completion**
```
Location: execution-planning/skill.py::validate_schedule()
Checks:
  ✓ CRONOGRAMA accumulated = 100% of total quantity
Status: PASS if 95% ≤ accumulated ≤ 105%
```

**Checkpoint 4: Financial Viability**
```
Location: financial-validation/skill.py::validate_profitability()
Checks:
  ✓ Margin 8% ≤ % ≤ 10%
  ✓ Break-even < 30% of planned quantity
  ✓ Fixed costs < 25% of revenue
Status: PASS (GO) if all checks pass
Status: CAUTION (YELLOW) if margin 6-12%
Status: FAIL (NOGO) if margin < 6%
```

---

## 📊 Typical Workflow

### Week 1: Base Data Setup
```
1. Base-data skill
   └─ Load DADOS from finance system
   └─ Load MÃO DE OBRA from HR
   └─ Load EQUIPAMENTOS from equipment manager
   └─ Load PRATICABILIDADE from MeteoBLUE
   └─ Load PRODUÇÕES from engineering
   └─ Validate all sources
   └─ Fix any name/data mismatches
   └─ Export clean base tables
```

### Week 2: Operational Costing
```
2. Operational-calc skill
   └─ Design EQUIPE for each activity
   └─ Define ADM, TOP, LAB, QSMS teams
   └─ Calculate MOB (equipment + team mobilization + benefits)
   └─ Validate C_FIXO delta
   └─ Adjust team compositions if delta > 5%
   └─ Finalize cost breakdown
```

### Week 3: Scheduling & Budget
```
3. Execution-planning skill
   └─ Build CRONOGRAMA with monthly productivity
   └─ Distribute teams across project timeline
   └─ Link CRONOGRAMA to EQUIPE
   └─ Build PLANEJAMENTO with unit prices and BDI
   └─ Validate 100% schedule completion
   └─ Calculate RESULTADO margin
```

### Week 4: Financial Review
```
4. Financial-validation skill
   └─ Run profitability validation
   └─ Calculate break-even point
   └─ Perform sensitivity analysis (costs ±10%, price ±5%)
   └─ Generate health report
   └─ Present GO/NOGO decision
   └─ If NOGO: iterate (back to Week 2-3)
   └─ If GO: approve for execution
```

---

## 🛠️ Troubleshooting

### Issue: #REF! errors in EQUIPE
**Diagnosis:**
  ```
  base-data skill
    ↓
  skill.sync_references("MÃO DE OBRA", "EQUIPE")
  ```

**Fix:**
  - Review mismatch report
  - Correct function names in EQUIPE to match MÃO DE OBRA exactly  
  - Recheck with sync_references()

### Issue: C_FIXO delta > 5%
**Diagnosis:**
  ```
  operational-calc skill
    ↓
  skill.validate_cost_delta()
    ↓
  Compare EQUIPE L10 E vs PLANEJAMENTO link
  ```

**Fix:**
  - Verify EQUIPE permanence (duration in months, Col O)
  - Verify EQUIPE monthly cost is correct
  - Update PLANEJAMENTO links

### Issue: CRONOGRAMA incomplete
**Diagnosis:**
  ```
  execution-planning skill
    ↓
  skill.validate_schedule()
    ↓
  Accumulated < 100%
  ```

**Fix:**
  - Increase Number of Teams (L11)
  - Extend Working Days (L10)
  - Check PRATICABILIDADE % productivity

### Issue: Margin outside 8-10%
**Diagnosis:**
  ```
  financial-validation skill
    ↓
  skill.validate_profitability()
    ↓
  Margin < 8% or > 10%
  ```

**Fix if < 8%:**
  - Review BDI (may be too low)
  - Check operational costs (ADM, MOB excessive?)
  - Consider excluding low-margin activities

**Fix if > 10%:**
  - Review BDI (may be too high)
  - Reduce unit prices to match market
  - Risk of losing bids if overpriced

---

## 📝 Configuration & Customization

### Modify Target Margin
Edit `financial-validation/skill.py`:
```python
class FinancialValidationSkill:
    TARGET_MARGIN_MIN = 0.08  # Change from 8%
    TARGET_MARGIN_MAX = 0.10  # Change from 10%
```

### Add New Validation Rules
Each skill has a `validate_data()` method. Add checks in:
```python
def validate_data(self, df, table_name):
    # Add custom validations
    if custom_check_fails:
        errors.append("Custom error message")
```

### Integrate with External Systems
Skills expect standard input-output contracts:
```python
# Load from any source via load_table() method
# Export via export_table() in any format (xlsx, csv, json)
```

---

## 📚 Documentation

Each skill has three components:

1. **manifest.json** - Machine-readable metadata
   - Skill ID, version, description
   - Managed tables with relationships
   - Available operations

2. **skill.md** - Human-readable documentation
   - Detailed table descriptions
   - Business rules and constraints
   - Examples and troubleshooting
   - KPIs and success criteria

3. **skill.py** - Implementation
   - Python classes with methods
   - Data processing logic
   - Validation and calculations

---

## 🔐 Constraints & Safety

- **Read-only by default:** Base data tables not modified in normal operation
- **Reversibility:** All export operations create timestamped files
- **Traceability:** Validation reports timestamped and archived
- **Approval gates:** Each layer has go/no-go checkpoints

---

## 🎓 Learning Path

1. **Beginner (1 hour):** Read manifest.json for overall structure
2. **Intermediate (1 day):** Read skill.md for each layer
3. **Advanced (1 week):** Study skill.py implementations
4. **Expert (ongoing):** Customize and extend for specific projects

---

## 🤝 Support & Contributions

For questions or improvements:
1. Review relevant skill.md documentation
2. Check troubleshooting section
3. Examine example code in skill.py
4. Extend with custom operations as needed

---

## 📄 References

- **PROCEDIMENTO_PLANEJAMENTO_AGIS.md** - Complete procedural manual
- **Relacionamentos_Tabelas.xlsx** - Table relationship map
- **Prompt Camila.txt** - Original workflow documentation
- **skills.sh documentation** - Framework reference

---

## 📅 Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-04-15 | Initial release: 4 skills (base-data, operational-calc, execution-planning, financial-validation) |

---

**Last Updated:** 2026-04-15  
**Status:** Production Ready ✅

