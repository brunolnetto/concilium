# Operational Gnomes Architecture (Black Box Model)

**Document ID:** ARCH-2026-05-12-GNOMOS  
**Status:** DRAFT - Reference Implementation  
**Author:** Engineering Team  
**Date:** 2026-05-12

## Overview

The **Operational Gnomes** are the internal machinery of the framework that transforms canonical project information (scope, catalog references, logistics) into detailed execution plans, resource schedules, and financial projections.

The gnomes operate as a **black box** — they do not have knowledge of real-world constraints beyond what is explicitly provided. This design enforces clear separation between:
- **Canonical Input:** User-supplied metadata (project info, scope, precedence rules)
- **Gnome Processing:** System-driven transformations (scheduling, costing, consolidation)
- **Consumable Output:** Detailed breakdown for execution

## The Six-Step Gnome Workflow

### Phase 1: Effort Calculation (Cálculo de Esforço)
**Input:**
- Catalog references (CPU IDs) with associated scope items
- Productivity reference (default from SICRO/SINAPI or override)
- Composition rules (how CPUs decompose into labor + equipment)

**Gnome Operation:**
- Traverse each CPU composition → extract labor hours per unit quantity
- Apply quantity multiplier from scope item
- **Output:** Total effort in hours per activity type

**Data Flow:**
```
Escopo Item (CPU-ID, qty) 
  → CPU Composition (mão_obra: [horas/un], equipamentos: [...])
  → Effort = qty * sum(horas/un)
  → {cpu_id, tipo_atividade, horas_totais}
```

**Related Skills:**
- `02-cronograma` (initial phase) — transforms scope into effort vector

---

### Phase 2: Weekly Distribution (Distribuição em Semanas)
**Input:**
- Effort per activity (from Phase 1)
- Productivity constraints: `praticabilidade` (%)  `produtividade` (hours/week/team)
- Precedence graph (which activities must complete before others start)
- Project duration or execution window

**Gnome Operation:**
- Respect precedence: topological sort of activity DAG
- For each activity, calculate `weeks_needed = effort_hours / (produtividade * praticabilidade)`
- Assign activities to weeks respecting dependencies (critical path considerations)
- **Output:** Week-by-week activity schedule

**Data Flow:**
```
Effort {cpu_id, horas} + Productivity {produtividade, praticabilidade} + Precedence DAG
  → Calculate critical path per activity thread
  → Allocate to weeks with precedence constraints
  → {cpu_id, semana_inicio, semana_fim, horas_por_semana}
```

**Critical Note on Precedence:**
- Gnomes **do not infer** precedence from technical knowledge
- Precedence **must be provided** by external input (user, project rules, contract)
- Gnomes enforce it strictly (fail if circular, warn if infeasible duration)

**Related Skills:**
- `02-cronograma` (primary) — builds weekly schedule
- Pre-input: `precedencia.json` or contract-derived rules

---

### Phase 3: Team Quantity Adjustment (Ajuste de Quantitativo de Equipes)
**Input:**
- Weekly schedule (from Phase 2)
- Per-week breakdown of activities with hours assigned
- Team capacity model (min/max team members per activity type)
- Budget constraints (if applicable)

**Gnome Operation:**
- For each week partition:
  - Calculate required FTE (full-time equivalents) to complete all activities
  - Apply team composition rules (e.g., mason team = 1 master + 2 assistants)
  - Adjust team size up/down based on critical path pressure
- **Output:** Week-by-week team roster with member counts per role

**Data Flow:**
```
Weekly Schedule {cpu_id, semana, horas_semana}
  → Group by semana and activity type
  → FTE_needed = horas_semana / (40h/week standard)
  → Apply team_model ratios
  → {semana, equipe_tipo, quantidade_pessoas}
```

**Related Skills:**
- `03-equipes` (primary) — determines team composition per week
- Depends on output from Phase 2

---

### Phase 4: Resource Merging & Indirect Allocation (Merge de Recursos + Indiretos)
**Input:**
- Weekly team roster (from Phase 3)
- Activity-level resource specifications (labor types, equipment, materials)
- Indirect resource requirements (site supervision, safety, admin overhead)
- Temporal conflict resolution rules

**Gnome Operation:**
1. **Direct Resource Consolidation:**
   - For activities running in same week without temporal conflict:
     - Merge equipment pools (combine overlapping equipment usage)
     - Consolidate labor by role (sum mason hours, electrician hours, etc.)
   - Flag temporal conflicts → escalate to Phase 3 for team adjustment

2. **Indirect Resource Allocation:**
   - Calculate overhead needs based on project complexity and duration
   - Allocate site supervision (supervisor FTE per activity cluster)
   - Allocate safety and administrative resources proportionally
   - **Output:** Consolidated resource list (direct + indirect per week)

**Data Flow:**
```
Team Roster + Activity Resources
  → Identify non-conflicting activity clusters per week
  → Merge: equipment, labor by role, materials
  → Calculate Indirect Pool (supervision, safety, admin)
  → {semana, recurso_tipo, quantidade, custo_unitario}
```

**Related Skills:**
- `05-indiretos` (primary) — allocates overhead resources
- Depends on output from Phase 3
- Cross-references CPU composition for equipment/material lists

---

### Phase 5: Cost Calculation (Cálculo de Custos)
**Input:**
- Consolidated resource list (from Phase 4)
- Pricing cascade (project overrides → regional → master catalog)
- Permanency model (which resources remain for entire project vs temporary)
- BDI parameters (overhead, profit margin)

**Gnome Operation:**
1. **Direct Costs:**
   - For each resource in each week: `cost_week = quantity × unit_price`
   - **Permanency Calculation:** Distinguish between:
     - **Occasional:** Used intermittently (e.g., specialized equipment week 3-5 only)
     - **Permanent:** Present entire project duration (e.g., site supervisor)
   - Direct Cost Total = Σ(weekly costs, adjusted for permanency)

2. **Indirect Costs:**
   - Allocate indirect resource costs proportionally to permanent duration
   - Calculate overhead burden (% of direct labor typically)

3. **Financial Metrics:**
   - Sale Total = (Direct + Indirect) × BDI multiplier
   - Break-even per team = Total Cost / Team Count
   - Operational Cost (direct + indirect per week, for cash flow)

**Data Flow:**
```
Resources {qty, unit_price, permanency} 
  → Weekly costs with permanency factors
  → Direct = Σ(costs_direct), Indirect = Σ(costs_indirect)
  → Sale Total = (Direct + Indirect) × BDI
  → Break-even per team = Total / team_qty
  → {semana, custo_direto, custo_indireto, custo_venda}
```

**Related Skills:**
- `06-consolidacao` (partial) — drives consolidation inputs
- Pricing sourced from catalog governance module
- BDI parameters from project profile (perfil)

---

### Phase 6: Consolidation (Consolidação Final)
**Input:**
- Weekly costs (from Phase 5)
- Permanent vs. occasional resource split
- BDI breakdown
- Margin and contingency policies

**Gnome Operation:**
- **Consolidate Financials:**
  - Direct Costs (total for project)
  - Indirect Costs (total for project)
  - Costs with BDI (direct + indirect × BDI multiplier)
  - Sale Price (costs with BDI + margin)
  - Profit = Sale Price - Costs
  - Margin % = Profit / Sale Price

- **Consolidate Schedule:**
  - Critical Path Duration (project end date)
  - Resource utilization by role (total person-weeks per role)
  - Weekly cash flow (costs per week)
  - Revenue schedule (if phased delivery)

- **Output:** Consolidated project financials and schedule for executive reporting

**Data Flow:**
```
Phase 5 Outputs (weekly costs, direct/indirect)
  → Sum by category (direct, indirect, BDI)
  → Apply margin policy
  → Calculate profitability metrics
  → Generate consolidation table
  → {categoria, valor_total, percentual, margem}
```

**Related Skills:**
- `06-consolidacao` (primary) — final aggregation and reporting
- Feeds into executive dashboards and contract pricing

---

## Gnome Architecture Constraints & Assumptions

### What Gnomes Know:
✅ Catalog compositions (CPU → labor, equipment breakdown)  
✅ Productivity and practicability metrics (provided inputs)  
✅ Precedence rules (provided explicitly)  
✅ Team capacity models (standard industry rules)  
✅ Pricing hierarchies (project override → regional → master)  
✅ Temporal scheduling algorithms (critical path, resource leveling)  

### What Gnomes DON'T Know:
❌ Real-world contract clauses or hidden constraints  
❌ Site-specific particularities (terrain, weather, local labor market)  
❌ Political or stakeholder preferences  
❌ Non-linear cost relationships (e.g., "efficiency improves after week 3")  
❌ External force majeure or delays  

**Design Principle:** If something is not provided as **canonical input**, gnomes assume default/neutral behavior.

---

## Mapping to Existing Skills

| Phase | Gnome Role | Primary Skill | Secondary Skills | Output Artifact |
|-------|-----------|---|---|---|
| 1 | Effort Calculation | `02-cronograma` | N/A | `esforco_por_atividade.json` |
| 2 | Weekly Distribution | `02-cronograma` | `precedencia.json` input | `cronograma_semanas.json` |
| 3 | Team Adjustment | `03-equipes` | Capacity model config | `equipes_por_semana.json` |
| 4 | Resource Merge + Indirect | `05-indiretos` | Equipment/material specs | `recursos_consolidados.json` |
| 5 | Cost Calculation | `06-consolidacao` | Pricing cascade | `custos_por_semana.json` |
| 6 | Consolidation | `06-consolidacao` | BDI config, margin policy | `consolidacao_financeira.json` |

---

## Critical Implementation Notes

### 1. Precedence Input Format
```json
{
  "precedencia": [
    {"atividade_id": "CPU-001", "predecessoras": []},
    {"atividade_id": "CPU-002", "predecessoras": ["CPU-001"]},
    {"atividade_id": "CPU-003", "predecessoras": ["CPU-001", "CPU-002"]}
  ]
}
```

### 2. Permanency Model
Not all resources have the same duration:
- **Permanent:** Site supervisor (weeks 1-52 for 1-year project)
- **Occasional:** Concrete pump (weeks 5-10 during foundation pour)
- **Multiplicative:** Labor per activity (scales with activity duration only)

Gnomes allocate costs accordingly: permanent resources amortized across full project, occasional resources charged only to their active weeks.

### 3. BDI Multiplier
BDI (Benefícios e Despesas Indiretas) typically ranges 20-40% of direct costs. Applied as:
```
Sale_Total = (Direct_Costs + Indirect_Costs) × (1 + BDI_%)
```

### 4. Catalog Complexity Handling (8000+ CPUs)
- Gnomes do NOT require knowledge of all 8000 CPUs upfront
- Gnomes process only the **subset referenced in project scope** (typically 50-200 CPUs)
- Scope item = `{cpu_id, quantidade, unidade}`
- Missing CPU composition → error (caught by Phase 1, fail-fast)

---

## Data Flow Diagram (Conceptual)

```
┌─────────────────────────────────────────────────────────────┐
│                 CANONICAL INPUTS                            │
│ • Project Metadata (nome, localização)                     │
│ • Scope (cpu_id, qty, unit) per EAP item                   │
│ • Productivity & Practicability (praticabilidade%)         │
│ • Precedence Graph (dependencies)                          │
│ • Budget / Duration Constraints                            │
└────────────┬────────────────────────────────────────────────┘
             │
       ┌─────▼──────────────────────────────────┐
       │  PHASE 1: Effort Calculation           │
       │  02-cronograma: Initial Pass           │
       │  Output: Horas totais per atividade    │
       └─────┬──────────────────────────────────┘
             │
       ┌─────▼──────────────────────────────────┐
       │  PHASE 2: Weekly Distribution          │
       │  02-cronograma: Schedule w/ Precedence │
       │  Output: Cronograma (semana, horas)    │
       └─────┬──────────────────────────────────┘
             │
       ┌─────▼──────────────────────────────────┐
       │  PHASE 3: Team Adjustment              │
       │  03-equipes: Roster & FTE              │
       │  Output: Equipes per semana            │
       └─────┬──────────────────────────────────┘
             │
       ┌─────▼──────────────────────────────────┐
       │  PHASE 4: Resource Merge + Indirect    │
       │  05-indiretos: Consolidate & Allocate  │
       │  Output: Recursos (direto + indireto)  │
       └─────┬──────────────────────────────────┘
             │
       ┌─────▼──────────────────────────────────┐
       │  PHASE 5: Cost Calculation             │
       │  06-consolidacao: Pricing & Metrics    │
       │  Output: Custos (direto/indireto/BDI)  │
       └─────┬──────────────────────────────────┘
             │
       ┌─────▼──────────────────────────────────┐
       │  PHASE 6: Consolidation (Final)        │
       │  06-consolidacao: Aggregation & Report │
       │  Output: Executive Summary & Analytics │
       └─────────────────────────────────────────┘
```

---

## Next Steps

1. **Define MendesLobo Catalog** — Create reference project with canonical scope
2. **Implement Phase Interfaces** — Formalize input/output contracts for each skill
3. **Test Gnome Pipeline** — End-to-end execution with sample data
4. **Document Precedence Rules** — Clarify which precedence constraints are system vs. user-driven
5. **Catalog Complexity Strategy** — Define how to handle 8000+ CPU references (lazy loading, caching, etc.)

