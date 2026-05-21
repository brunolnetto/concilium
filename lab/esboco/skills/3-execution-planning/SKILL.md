---
name: execution-planning
description: >
  Use esta skill para orquestrar a conversão de custos operacionais em um
  orçamento completo com cronograma e previsão financeira. Ative para
  distribuição de atividades (CRONOGRAMA), elaboração de orçamento
  (PLANEJAMENTO), ou cálculo de BDI e resultado financeiro.
compatibility: "Python 3.10+, openpyxl, pandas"
---

# Execution Planning Skill

**Skill ID:** `execution-planning`  
**Version:** 1.0.0  
**Layer:** 3 - Execution & Scheduling  
**Status:** Active

## Overview

This skill orchestrates the conversion of operational costs into a complete project budget with timeline and financial forecasting.

**Key Tables:**
- **CRONOGRAMA**: Monthly schedule with productivity factors and team allocation
- **PLANEJAMENTO**: Line-item budget with BDI markups
- **RESULTADO**: Financial summary and project viability

---

## CRONOGRAMA (Project Schedule)

**Purpose:** Distribute activities over project duration with monthly productivity tracking

**Structure (per Activity - 8 lines):**

```
Lines N to N+7:
  +0: Activity Name
  +1: Unit
  +2: Total Quantity
  +3: Hourly Production
  +4: Daily Production (= Hourly × 8)
  +5: Working Days
  +6: Number of Teams
  +7: Planned Quantity (calculated)
```

**Monthly Section (Columns for each month Jan-Dec):**

```
L5: Month Names (JAN, FEV, MAR, ...)
L8: % Produtivo (from PRATICABILIDADE)
L10: Dias Trabalhados (working days input)
L11: Nº de Equipes (team count input)
L12-17: Daily calculations
```

**Critical Formula:**
```
Qtd Planejada Mensal = Dias Trabalhados × Nº Equipes × Prod Diária × % Produtivo

Goal: Qtd Plan. Acumulada (L17) = 100% of Quantidade Total (L2)
```

---

## PLANEJAMENTO (Budget)

**Purpose:** Line-item bud with unit prices, costs by category, and BDI markups

**Starting from Line 11,per service:**

| Col | Field | Source | Input |
|-----|-------|--------|-------|
| C | Service | Text | Manual |
| D | Unit | Text | Manual |
| E | Quantity | Number | Manual |
| F | Material Price | R$ | Linked to CPU or Manual |
| G | Diesel Price | R$ | Linked to CPU or Manual |
| H | Labor Price | R$ | Linked to CPU or Manual |
| I | Equipment Price | R$ | Linked to CPU or Manual |
| K-N | BDI % | % | Auto from BDI table |

**Automatic Calculations:**

| Col | Field | Formula |
|-----|-------|---------|
| O | Price without BDI | = F + G + H + I |
| P-S | Subtotal without BDI | = E × (each cost category) |
| T | Price with BDI | = O × (1 + sum(BDI %)) |
| U-X | Subtotal with BDI | = E × (each category with BDI) |
| Y | Total Project | = Sum all subtotals |

**Validation (L12 example):**
```
PLANEJAMENTO L12 Col O (Unit Price no BDI)
MUST = CPU L52 Col J (Unit Cost)

If not equal → Check material, diesel, labor, equipment links in CPU
```

---

## RESULTADO (Financial Summary)

**Purpose:** Consolidate all costs and calculate project profitability

**Key Rows:**

```
Custo Direto (from PLANEJAMENTO Y)        = Costs of services
  + Custo Indireto (from ADM, TOP, LAB, QSMS, MOB)
  ════════════════════════════════════════════════════
  = Custo Total

Receita (from PLANEJAMENTO with BDI)
  - Custo Total
  ════════════════════════════════════════════════════
L28 Col C: Resultado Financeiro (Profit/Loss)
L28 Col D: % Margem (Margin %)
```

**Success Criteria:**
```
✅ Margem 8% ≤ % ≤ 10%

❌ < 8%  → Project underpriced
❌ > 10% → Not competitive in market
```

---

## Key Operations

### `schedule_activities()`
Distributes tasks across timeline:
- Reads CRONOGRAMA structure
- Applies PRATICABILIDADE monthly factors
- Calculates team requirements
- Validates 100% completion

### `reconcile_costs()`
Ensures cost consistency:
- EQUIPE (fixed) ↔ CPU (composition) ↔ PLANEJAMENTO (final)
- Validates C_FIXO delta < 5%
- Flags mismatches for review

### `calculate_bdi()`
Applies markup factors:
- Reads BDI percentages per cost type
- Calculates compound BDI
- Updates PLANEJAMENTO costs

### `aggregate_results()`
Final consolidation:
- Sums direct costs from PLANEJAMENTO
- Adds indirect costs from ADM, TOP, LAB, QSMS, MOB
- Calculates profit and margin%

---

## Data Dependencies

**Inputs from base-data & operational-calc:**
- PRATICABILIDADE → % Produtivo monthly
- PRODUÇÕES → Hourly rates
- EQUIPE → Team composition & costs
- CPU → Unit cost basis
- BDI → Markup factors
- ADM, TOP, LAB, QSMS, MOB → Indirect costs

**Validation Points:**
1. CRONOGRAMA distribution reaches 100%
2. PLANEJAMENTO unit prices match CPU
3. C_FIXO delta < acceptable threshold
4. RESULTADO margin 8-10%

---

## KPIs

| Metric | Target | Location |
|--------|--------|----------|
| Schedule Completion | 100% | CRONOGRAMA L17 |
| Cost Alignment | Delta < 5% | C_FIXO Col M |
| Margin % | 8-10% | RESULTADO L28 D |
| Revenue vs Budget | ≥ 95% | Analysis |

---

## Examples & Procedures

See PROCEDIMENTO_PLANEJAMENTO_AGIS.md Sections 2-3 for detailed step-by-step examples.

## Related Skills
- [`base-data`]: Provides PRODUÇÃO, PRATICABILIDADE, BDI
- [`operational-calc`]: Provides EQUIPE, ADM costs
- [`financial-validation`]: Consumes final results
