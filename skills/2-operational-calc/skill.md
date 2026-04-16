# Operational Cost Calculation Skill

**Skill ID:** `operational-calc`  
**Version:** 1.0.0  
**Layer:** 2 - Operational Costs  
**Status:** Active

## Overview

This skill manages all operational cost calculations for the AGIS project. It handles:
- **Direct Crew Costs:** EQUIPE, Escavação e Carga  
- **Indirect Costs:** ADM, TOP, LAB, QSMS, MOB  
- **Cost Consolidation:** C_FIXO (validation & reconciliation)

**Dependency Chain:**
```
base-data  ─────────┐
                     ├──→ operational-calc ──→ execution-planning ──→ financial-validation
                     │
                     └(consumes: MÃO DE OBRA, EQUIPAMENTOS, DADOS)
```

---

## Managed Tables

### Direct Team Costs

#### EQUIPE (Equipe Direta - Direct Team)
**Purpose:** Define direct labor and equipment for each activity

**Structure (per Activity - 8 lines):**
```
Lines N to N+7:
  +0: Activity Name              (Col B)  [from PLANEJAMENTO]
  +1: Unit                       (Col C)  [from PLANEJAMENTO]
  +2: Quantity                   (Col D)  [from PLANEJAMENTO]
  +3: Hourly Production          (Col F)  [from PRODUÇÕES]
  +4: Daily Production           (Col G)  [= F × 8]
  +5: Working Days               (Col entry)
  +6: Number of Teams            (Col entry)
  +7: Planned Quantity (Calc)    (Col result)         
```

**Sections:**
1. **Labor (Linhas 17-21):**
   - Function name (EXACT match to MÃO DE OBRA)
   - Number of people = Number of teams from CRONOGRAMA
   - Salary, extras, encargos - auto-populated from MÃO DE OBRA
   - Total cost: auto-calculated

2. **Equipment (Linhas 28+):**
   - Equipment name (EXACT match to EQUIPAMENTOS)
   - Number of equipment = Number of teams from CRONOGRAMA
   - Monthly value, fuel cost - auto-populated from EQUIPAMENTOS
   - Total cost: auto-calculated

3. **Summary (Linha 10):**
   - Monthly labor cost (Col J) = Sum of labor rows
   - Monthly equipment cost (Col J) = Sum of equipment rows
   - Total monthly cost = Monthly labor + Monthly equipment
   - Duration in months (Col O) = from CRONOGRAMA
   - **Total Activity Cost (Col U) = Monthly Total × Duration**

**Key Formula:**
```
Custo Total Atividade = (Σ Salários + Σ Equipamentos) × Meses de Permanência
```

**Example:**
```
ESCAVAÇÃO, CARGA...
  Operador de Escavadeira × 1 → R$ 6.300
  Escavadeira Hidráulica × 1  → R$ 15.000
  ─────────────────────────
  Monthly Total: R$ 21.300
  Duration: 3 months
  ═════════════════════════════
  TOTAL: R$ 63.900
```

---

#### Escavação e Carga (Specialized Excavation Team)
**Purpose:** Dedicated cost table for excavation/loading activities

**Same structure as EQUIPE**, but focused on:
- Excavation equipment operators
- Loading equipment
- Specialized labor

---

### Indirect Costs

#### ADM (Administração - Administrative)
**Purpose:** Administrative team and site infrastructure

**Two Sections:**

**1. Mão de Obra (Lines 17-21 approx):**
- Same pattern as EQUIPE
- Functions: Site Manager, Supervisor, Admin Staff, etc.

**2. Infrastructure (Lines 55-94):**
- **Monthly Expenses (Lines 55-77):**
  ```
  Col E: Descrição (Barracão, Alojamento, Tensão, Diesel gen., etc)
  Col G: Unidade (m2, unidade, mês)
  Col I: Quantidade
  Col L: Preço Unitário
  Col Q: Valor Total = I × L
  ```

- **Fixed Expenses (Lines 80-94):**
  - One-time costs (permits, surveys, etc)
  - Same structure: Qty × Unit Price

**Example ADM Items:**
```
Barracão de Canteiro       | m2   | 500  | R$ 50/m2   | R$ 25.000
Alojamento Funcionários    | leito| 30   | R$ 1.200   | R$ 36.000
Gerador de Energia 40 kVA  | un   | 2    | R$ 8.000   | R$ 16.000
Seguro da Obra             | obra | 1    | R$ 15.000  | R$ 15.000 (fixed)
```

---

#### TOP (Topografia - Surveying)
**Purpose:** Surveying team costs

**Structure:** Same as EQUIPE
- Functions: Surveyor, Assistant, etc.
- Equipment: Survey instruments, vehicle
- Duration: Usually entire project

---

#### LAB (Laboratório - Testing Laboratory)
**Purpose:** Laboratory and material testing

**Structure:** Same as EQUIPE (simplified)
- Functions: Lab technician
- Equipment: Testing apparatus
- Often lower intensity than field teams

---

#### QSMS (Qualidade, Segurança, Meio Ambiente)
**Purpose:** Quality, Safety, Environmental compliance

**Structure:** Same as EQUIPE
- Functions: Safety manager, Environmental tech, Quality inspector
- Equipment: Safety gear, measurement devices
- Presence: Usually throughout project

---

#### MOB (Mobilização - Mobilization)
**Purpose:** Equipment movement and personnel logistics

**Three Main Sections:**

**1. Equipment Mobilization/Demobilization (Lines 17-18):**
```
L17:
  Col S: Number of mobilizations
  Col Z: Origin city
  Col AE: Destination city
  Col AJ: Distance (km round-trip)
  Col AP: Cost per km
  Col AV: Total Cost = S × AJ × AP
```

**2. Team Mobilization (Line 32):**
```
Col M: Number of people = SUM(C_FIXO [people column] for all activities)
      (Typically extracted from C_FIXO rows 20-21, Col C)
```

**3. Allowance/Benefits (Lines 42-62):**

**3a. Housing Allowance (Lines 42-48):**
```
Col H: Number of people
Col I: Value per person per month
Cols K-BC: Months (mark with "x")
Col BD: Total = H × I × (number of "x" months)
```

**3b. Team Benefits (Lines 51-62):**
```
Examples: 
  - Alimentação (Meals)
  - Seguro de Vida (Life Insurance)
  - Cesta Básica (Food Basket)
  - Plano de Saúde (Health Plan)

Per benefit line:
  Col B: Team Name          [from C_FIXO]
  Col H: Number of people   [from C_FIXO]
  Col K: Monthly unit cost  [from DADOS: sum of L12+L24+L25+L26]
  Col T: Duration months    [from C_FIXO]
  Col Z: Total = H × K × T  [calculated]
```

**Example:**
```
Team: Escavação
  People: 8
  Monthly benefit cost: R$ 3.500 (sum: meals + insurance + basket + health)
  Duration: 3 months
  ─────────────────────
  Total: 8 × R$ 3.500 × 3 = R$ 84.000
```

---

### Cost Reconciliation

#### C_FIXO (Custo Fixo Comparison)
**Purpose:** Validate that planned crew costs match CPU/PLANEJAMENTO costs

**Critical for Quality Control!**

**Structure (per service on Line 8):**

| Col | Field | Source | Meaning |
|-----|-------|--------|---------|
| A | Serviço | Manual | Service name |
| B | Nome da Equipe | EQUIPE L7 Col E | Team name |
| C | Nº Pessoas | EQUIPE L22 Col G | Number of people |
| D | Permanência (meses) | EQUIPE L10 Col O | Duration |
| F | Custo Fixo Mensal | EQUIPE L10 Col E | Monthly cost |
| I | **Custo Fixo Total** | = D × F | **Duration × Monthly** |
| L | Custo de Venda | PLANEJAMENTO (R+S) | Linked from planning |
| M | **DELTA** | = L - I | **Validation: should ≈ 0** |

**Interpretation:**

```
DELTA ≈ 0  ✅ Costs are aligned
DELTA > 5% ⚠️  Costs don't match - review EQUIPE or PLANEJAMENTO
DELTA < -5% ⚠️  Costs inverted - critical error
```

**Example:**
```
Service: ESCAVAÇÃO...
  Team: Escavação
  People: 8
  Duration: 3 months
  Fixed Monthly Cost: R$ 63.900
  Fixed Total: 3 × 63.900 = R$ 191.700
  
  Sales Cost (from PLANEJAMENTO): R$ 190.000
  ────────────────────────────────
  DELTA: R$ 190.000 - R$ 191.700 = -R$ 1.700 (-0.9%) ✅ OK
```

---

## Data Quality Rules

### R1: Exact Name Matching (Critical)
```
🔴 CRITICAL
When linking functions/equipment in EQUIPE, ADM, TOP, LAB, QSMS:

✅ CORRECT:
  MÃO DE OBRA: "OPERADOR DE ESCAVADEIRA"
  EQUIPE Col E: "OPERADOR DE ESCAVADEIRA"

❌ WRONG:
  "Operador de Escavadeira"        (wrong case)
  "OPERADOR DE ESCAVADEIRA "       (extra space)
  "OPERADOR DE ESCAVA"              (truncated)

💥 Result: #REF! errors, blank salary fields
```

### R2: Team Composition Integrity
```
🟡 HIGH
When defining teams:
- Number of people ≥ 1
- Equipment quantity ≥ 1
- Duration (months) ≥ 1

Multiple teams possible when needed (1, 2, 3... teams working on same activity)
```

### R3: Cost Delta Validation
```
🔴 CRITICAL
C_FIXO Column M must validate:

|DELTA| < 5% of Custo Fixo Total → OK
|DELTA| 5-10%                    → Review (minor mismatch)
|DELTA| > 10%                    → ERROR (fix EQUIPE or PLANEJAMENTO)

Non-negotiable: DELTA must be explained and approved
```

### R4: Administrative Quantities
```
🟡 HIGH
In ADM infrastructure section:
- Quantities must match actual needs
- Unit prices from market research
- Duration aligned with project schedule

Example check:
  Barracão: 500 m2 ÷ 50 people = 10 m2/person (reasonable)
```

### R5: Mobilization Distance
```
🟡 HIGH
MOB equipment mobilization:
- Distance is round-trip (ida + volta)
- Cost per km must include mobilization + demobilization
- Coordinate with equipment availability

Example:
  Origin: São Paulo Supplier
  Destination: Ceará (Aracoiaba)
  Distance: 2,500 km (round-trip)
  Cost: R$ 50/km
  Total: 2,500 × 50 = R$ 125.000
```

---

## Operations & Methods

### Operation: `calculate_crew_cost()`
**Purpose:** Calculate total team cost for an activity

```python
cost = skill.calculate_crew_cost(
    activity="ESCAVAÇÃO, CARGA...",
    labor=[
        {"function": "OPERADOR DE ESCAVADEIRA", "qty": 1}
    ],
    equipment=[
        {"name": "ESCAVADEIRA HIDRÁULICA 38T", "qty": 1}
    ],
    duration_months=3
)
# Returns: {
#   "monthly_labor": 6300,
#   "monthly_equipment": 15000,
#   "monthly_total": 21300,
#   "total_cost": 63900  # = 21300 × 3
# }
```

---

### Operation: `validate_cost_delta()`
**Purpose:** Check C_FIXO delta alignment

```python
report = skill.validate_cost_delta(
    service="ESCAVAÇÃO, CARGA...",
    fixed_cost=191700,
    sales_cost=190000
)
# Returns: {
#   "delta": -1700,
#   "delta_pct": -0.89,
#   "status": "OK",  # or "WARNING" or "ERROR"
#   "message": "Custos alinhados"
# }
```

---

### Operation: `aggregate_indirect()`
**Purpose:** Sum all indirect costs

```python
total = skill.aggregate_indirect(
    adm_cost=500000,
    topografia_cost=150000,
    laboratorio_cost=80000,
    qsms_cost=120000,
    mob_cost=200000
)
# Returns: 1,050,000
```

---

## Dependencies & Constraints

### ✅ Dependencies (Consumed from base-data)
- MÃO DE OBRA: For salary lookups in EQUIPE, ADM, etc.
- EQUIPAMENTOS: For equipment cost lookups
- DADOS: For benefit costs in MOB, unit costs in ADM
- CRONOGRAMA: For duration, number of teams, working days
- PLANEJAMENTO: For cost comparison in C_FIXO

### ⬇️ Provides to
- `execution-planning`: via CRONOGRAMA updated with team needs
- `financial-validation`: via final cost aggregates

### 🚫 Constraints
- Number of teams from CRONOGRAMA determines people/equipment qty
- Duration must match project schedule
- C_FIXO delta must be validated before proceeding to PLANEJAMENTO
- Name changes in base tables require updates here

---

## Troubleshooting

### Issue: #REF! in EQUIPE labor costs
**Cause:** Function name doesn't match MÃO DE OBRA exactly  
**Solution:**
```python
skill = OperationalCalcSkill(spreadsheet)
sync = skill.validate_references("MÃO DE OBRA", "EQUIPE")
for mismatch in sync['mismatches']:
    print(f"Fix: '{mismatch['in_target']}' → '{mismatch['suggestion']}'")
```

### Issue: C_FIXO delta > 10%
**Cause:** Mismatch between EQUIPE costs and PLANEJAMENTO costs  
**Solution:**
1. Verify team composition in EQUIPE (Linha 10 Col E)
2. Verify duration in EQUIPE (Linha 10 Col O)
3. Verify PLANEJAMENTO links correct cost data
4. Recalculate CRONOG RAMA→EQUIPE pipeline

### Issue: MOB mobilization cost too high
**Cause:** Distance or unit price incorrect  
**Solution:**
```python
# Verify in MOB:
# - Distance is round-trip
# - Cost per km includes markup
# - Number of mobilizations correct
```

---

## KPIs & Metrics

| Metric | Target | Formula | Location |
|--------|--------|---------|----------|
| Team Monthly Cost | Competitive | Sum(MO + Equip) | EQUIPE L10 E |
| C_FIXO Delta | < 5% | \|(L-I)/I\| | C_FIXO M |
| Indirect/Direct Ratio | 15-25% | Indirect ÷ Direct | Dashboard |
| Cost per Team Member | Budgeted | Monthly Cost ÷ People | Analysis |
| Mobilization Cost | < 5% of total | MOB Total ÷ Project | Dashboard |

---

## Examples

### Example 1: Calculate full EQUIPE section
```python
skill = OperationalCalcSkill(spreadsheet)

# Load activity from CRONOGRAMA
activity_teams = 2
activity_duration = 3

# Build labor groups
labor_cost = skill.calculate_crew_cost(
    activity="ESCAVAÇÃO",
    labor=[
        {"function": "OPERADOR", "qty": 1 * activity_teams},
        {"function": "AJUDANTE", "qty": 2 * activity_teams},
    ],
    equipment=[
        {"name": "ESCAVADEIRA", "qty": 1 * activity_teams}
    ],
    duration_months=activity_duration
)

print(f"Total Atividade: R$ {labor_cost['total_cost']:,.2f}")
```

### Example 2: Validate all C_FIXO entries
```python
df_cfixo = skill.load_table("C_FIXO")
errors = []

for idx, row in df_cfixo.iterrows():
    if pd.isna(row['DELTA %']) or abs(row['DELTA %']) > 0.05:
        errors.append({
            'service': row['Serviço'],
            'delta_pct': row['DELTA %'],
            'status': 'review needed'
        })

print(f"Services needing review: {len(errors)}")
for err in errors:
    print(f"  - {err['service']}: {err['delta_pct']:.1%}")
```

---

## Related Skills
- [`base-data`]: Provides MÃO DE OBRA, EQUIPAMENTOS, DADOS
- [`execution-planning`]: Consumes operational costs for scheduling
- [`financial-validation`]: Uses aggregated indirect costs

## References
- PROCEDIMENTO_PLANEJAMENTO_AGIS.md: Section 3-7
- Prompt Camila.txt: Team composition details
- Relacionamentos_Tabelas.xlsx: Relationship definitions
