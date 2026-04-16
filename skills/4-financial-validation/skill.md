# Financial Validation Skill

**Skill ID:** `financial-validation`  
**Version:** 1.0.0  
**Layer:** 4 - Validation & Analysis  
**Status:** Active

## Overview

This skill provides final validation of project financial viability and performs sensitivity analysis for risk management.

**Key Tables:**
- **RESULTADO**: Financial summary with margin calculation
- **PONTO DE EQUILIBRIO**: Break-even analysis and cost structure

---

## RESULTADO (Financial Result)

**Purpose:** Final consolidation of all project economics

**Key Rows:**

```
Row L28 Col C: Resultado Financeiro    = Revenue - Total Costs
Row L28 Col D: % Margem                = (Profit / Revenue) × 100
```

**Success Criteria:**

```
✅ VIABLE:        8% ≤ Margem ≤ 10%
❌ UNDERPRICED:   Margem < 8%  → Increase prices or reduce costs
❌ OVERPRICED:    Margem > 10% → May lose bids, reduce BDI
```

**Components:**

```
Direct Costs      = PLANEJAMENTO Y (service costs with BDI)
Indirect Costs    = SUM(ADM, TOP, LAB, QSMS, MOB total costs)
─────────────────────────────────────────────────
TOTAL COSTS

Revenue           = PLANEJAMENTO with full BDI markup
─────────────────────────────────────────────────
PROFIT = Revenue - Total Costs
MARGIN = (Profit / Revenue) × 100
```

---

## PONTO DE EQUILIBRIO (Break-Even Analysis)

**Purpose:** Understand cost structure and pricing strategy

**Components:**

```
Fixed Costs       = ADM, TOP, LAB, QSMS (infrastructure)
Variable Costs    = MO + Equipment per activity unit
Contribution Margin = Price - Variable Cost per unit

Break-Even Point  = Fixed Costs / Contribution Margin
                  = Qty of units needed to break even
```

**Use Cases:**
- If project is halted halfway, can company still pay fixed costs?
- How sensitive is profit to price changes?
- What's the minimum volume needed?

---

## Financial Validation Operations

### `validate_profitability()`
Checks if margin meets target:
```
Input:
  - Margin % from RESULTADO
  
Output:
  - Status: VIABLE / UNDERPRICED / OVERPRICED
  - Actions: Recommendations for adjustment
```

### `calculate_breakeven()`
Determines break-even quantity:
```
Input:
  - Fixed costs (ADM, etc)
  - Contribution margin per unit
  
Output:
  - Break-even quantity
  - Break-even revenue
  - Safety margin %
```

### `sensitivity_analysis()`
Models impact of cost variations:
```
Input:
  - Base scenario (costs, prices)
  - Variations: ±5%, ±10%, ±15% on key costs
  
Output:
  - Profit under each scenario
  - Risk zones (where profit becomes negative)
```

### `generate_health_report()`
Comprehensive financial health check:
```
Output:
  - Overall viability
  - Margin trend
  - Risk factors
  - Recommendations
  - Traffic light: 🟢 OK / 🟡 CAUTION / 🔴 RISK
```

---

## Risk Indicators

### 🟢 GREEN (Low Risk)
```
- Margin 8-10%
- Fixed cost < 20% of revenue
- Break-even < 30% of planned quantity
- No critical suppliers
```

### 🟡 YELLOW (Medium Risk)
```
- Margin 6-8% or 10-12%
- Fixed cost 20-30% of revenue
- Break-even 30-50% of planned quantity
- Dependency on 1-2 suppliers
```

### 🔴 RED (High Risk)
```
- Margin < 6% or > 12%
- Fixed cost > 30% of revenue
- Break-even > 50% of planned quantity
- Weather/schedule risks realized
```

---

## Sensitivity Scenarios

**Base Case (Planned):**
- All costs as budgeted
- Schedule as planned
- No weather delays

**Scenario 1: Cost Increase (±10%)**
- Material prices ↑ 10%
- Labor ↑ 10%
- Impact on margin

**Scenario 2: Schedule Delay (±20%)**
- Extended duration
- Higher fixed costs
- Partial completion penalties

**Scenario 3: Price Pressure (-5%)**
- Market competition forces price cut
- Impact on profitability

**Scenario 4: Combined Stress**
- Costs ↑ 10% + Price ↓ 5%
- Worst-case analysis

---

## Success / Failure Thresholds

| Metric | Target | Allow | Critical |
|--------|--------|-------|----------|
| Margin % | 8-10% | 7-11% | <6% or >12% |
| Break-Even | <30% | <40% | >50% |
| Cost/Revenue | 80-90% | 70-95% | >95% |
| Fixed Cost % | <20% | <25% | >30% |

---

## Key Metrics

**Profitability Index**
```
= (Revenue - Total Costs) / Revenue
Target: 8-10%
```

**Cost Structure**
```
Direct %:      60-70% of revenue
Indirect %:    10-20% of revenue
Profit %:      8-10% of revenue
```

**Break-Even Coverage**
```
= (Planned Qty / Break-Even Qty) - 1
Target: > 2x (200% - only need 50% of planned work)
```

---

## Validation Checklist

- [ ] RESULTADO margin is 8-10%
- [ ] All costs accounted for (direct + indirect)
- [ ] BDI markup reasonable and competitive
- [ ] Break-even < 40% of planned output
- [ ] Fixed costs properly classified
- [ ] No major cost items missing
- [ ] Team costs validated (C_FIXO delta OK)
- [ ] Equipment mobilization included
- [ ] Administrative overhead reasonable
- [ ] Benefits and allowances complete

---

## Pass / Fail Criteria

**PASS (Ready for Execution):**
```
✅ Margin 8-10%
✅ All validations pass
✅ Risk indicators green or yellow
✅ No critical warnings
✅ Stakeholder approval obtained
```

**FAIL (Rework Required):**
```
❌ Margin <6% or >12%
❌ Major cost validation failure
❌ Break-even > 50%
❌ Critical data missing
❌ High-risk factors unmitigated
```

---

## Output & Reporting

### Executive Summary
- Overall viability (GO/NOGO)
- Margin %
- Key risks
- Recommendations

### Detailed Financial Report
- Detailed cost breakdown
- Scenario analysis
- Break-even calculation
- Monthly cash flow projection

### Risk Register
- Identified risks
- Impact if realized
- Mitigation strategies
- Contingency allocation

---

## Related Skills
- [`execution-planning`]: Provides RESULTADO financial data
- [`operational-calc`]: Provides indirect cost details
- [`base-data`]: Provides fundamental cost rates

## References
- PROCEDIMENTO_PLANEJAMENTO_AGIS.md: Section 8 (RESULTADO)
- Relacionamentos_Tabelas.xlsx: Financial table relationships

