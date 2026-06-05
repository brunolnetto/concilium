# ADR-006: Replanning Strategy: Preventive Iteration When Constraints Become Infeasible

**Status:** Implementado  
**Date Decided:** 2026-04-30  
**Date Implemented:** 2026-05-03  
**Implementers:** scheduling/constraint_validator.py, cli/commands_replan.py, replanning/generator.py  
**Context:** **STEUERUNG ONLY** (no execution/feedback loop).

During planning phase, Skill 02B generates weekly schedule. Validation (VAL-SCHED-WEEKLY-01 to 05) may reveal:

```
Constraint violations discovered BEFORE execution:
  - Schedule misses deadline by 4 weeks (VAL-SCHED-WEEKLY-03)
  - Resource pool exceeded in weeks 8–10 (VAL-SCHED-WEEKLY-05)
  - Cumulative cost exceeds budget (VAL-INDIRETOS-04)
  - Critical path has no slack (risk assessment)
```

**The question:** If plan is infeasible, what do we do?

### The Problem (Pre-ADR-006)

1. **Multi-candidate generation (ADR-004)** already produces top-3 schedules
2. But if ALL top-3 violate constraints → what next?
3. **Need a replanning framework:** How to iteratively refine plan until constraints satisfied

---

## Decision

We adopt a **preventive replanning strategy** that runs BEFORE execution:

### D1 — Constraint Violation Triggers Replanning

```
Skill 02B generates schedule
  ↓
Validation checks constraints
  ├─ C1: All activities scheduled ✓
  ├─ C2: Deadline respected ✓
  ├─ C3: Resource pool not exceeded ✓
  ├─ C4: Precedences respected ✓
  ├─ C5: Durations respected ✓
  ├─ F1: Cost within budget ✓
  └─ F2–F5: Soft constraints (advisory)
  
If ANY hard constraint violated:
  ↓
Replan triggered (iterative refinement)
```

**NOT triggered by execution progress.** Only by planning constraints.

---

### D2 — Three Replanning Options (Preventive)

When hard constraint violated, engineer chooses from 3 strategic options:

#### Option 1: Relax Constraint (Negotiate with Client)

```
Original: Deadline week 24 (contract)
Problem: Schedule needs 26 weeks
Solution: Request 2-week extension

Cost: Indiretos increase by R$ 34k (ADR-007)
Benefit: Feasible schedule without resource stress
Decision: PM negotiates with client (cost-share? AGIS absorb?)
```

**Applies to:** Deadline, scope, budget

#### Option 2: Add Resources (Hire Contractors)

```
Original: Pool has 3 operadores (max)
Problem: Weeks 8–10 need 5 operadores
Solution: Hire 2 temporary contractors

Cost: +R$ 50k labor (weeks 8–10)
Benefit: Schedule stays on deadline
Decision: Director approves if ROI > cost (avoid penalty)
```

**Applies to:** Resource bottlenecks, team capacity

#### Option 3: Reduce Scope (Defer Activities)

```
Original: 150 activities, 24 weeks
Problem: Budget exceeded by R$ 100k
Solution: Defer finishing activities (Phase 2)

Cost: None (Phase 2 separate project)
Benefit: Phase 1 budget balanced, schedule feasible
Decision: Client approves scope reduction
```

**Applies to:** Budget constraints, schedule tightness

---

### D3 — Replanning Workflow (STEUERUNG Only)

```
Initial Schedule (Skill 02B) + Validation
  ↓
Hard constraint violated?
  ├─ NO → Approved, ready for execution
  └─ YES → Replan
      ↓
    Identify violated constraint(s)
      ↓
    Classify: Deadline? Budget? Resource?
      ↓
    Generate 3 options (Relax / Add / Reduce)
      ↓
    Impact Assessment (cost/benefit)
      ├─ Option 1: +R$ 34k (indiretos), feasible
      ├─ Option 2: +R$ 50k (labor), feasible
      └─ Option 3: -R$ 100k (scope), feasible
      ↓
    Engineer + Manager review
      ↓
    Decision: Choose option + justify
      ↓
    Recalculate plan (update 02B)
      ↓
    Validate constraints again
      └─ If still violated → loop OR escalate to director
```

**Iterative:** May need 2–3 cycles to find feasible plan.

---

### D4 — Escalation Rules

If engineer can't find feasible solution:

```
Tier 1 (Engineer): Try options 1, 2, 3 with standard parameters
  → If feasible: Done
  → If not: Escalate

Tier 2 (Senior Engineer + PM): Propose aggressive options
  → 3-week deadline extension?
  → 5 temporary contractors?
  → 20% scope reduction?
  → If feasible: Director approval needed
  → If not: Escalate

Tier 3 (Director): Strategic decision
  → Accept unbalanced budget?
  → Renegotiate entire contract?
  → Withdraw bid?
```

**Threshold:** If no option under R$ 200k cost delta, escalate to director.

---

## Interfaces / Implementation

### Replanning Workflow (CLI)

```bash
# Skill 02B generated schedule, validation found violations
concilium validate schedule --project lote09-ce
# Output:
# ❌ VAL-SCHED-WEEKLY-03: Deadline violated by 4 weeks
# ❌ VAL-SCHED-WEEKLY-05: Resource "operador" exceeded weeks 8–10

# Trigger replanning
concilium replan --project lote09-ce --reason "constraint_violation"

# Output:
# Analyzing constraint violations...
# 
# Option 1: Extend deadline 4 weeks
#   Duration: 24 → 28 weeks
#   Indiretos delta: +R$ 54k (MOB: +20k, ADM: +12k, QSMS: +22k)
#   Resource utilization: Smoothed (no peaks)
#   Recommendation: FEASIBLE, cost-effective
#   
# Option 2: Add 1 operador weeks 8–13
#   Duration: 24 weeks (unchanged)
#   Labor delta: +R$ 30k
#   Resource utilization: Still tight week 10
#   Recommendation: FEASIBLE, risky
#   
# Option 3: Defer activities 100–120 (Phase 2)
#   Duration: 22 weeks (2 weeks faster)
#   Scope reduction: 20% of activities
#   Budget delta: -R$ 100k (saves cost)
#   Recommendation: FEASIBLE, client approval needed

# Engineer chooses
concilium replan approve \
  --project lote09-ce \
  --option 1 \
  --reason "Negotiate deadline extension with client, cost-effective"

# Result: New schedule (plan v2) generated, ready for execution
```

### Constraint Violation Detection

```python
class ConstraintValidator:
    """Detect hard constraint violations in proposed schedule."""
    
    def validate(self, schedule: WeeklySchedule, canonical: CanonicalModel):
        """Return list of violations."""
        
        violations = []
        
        # C2: Deadline
        project_end = max(s.end_week for s in schedule.values())
        if project_end > canonical.deadline_week:
            violations.append(ConstraintViolation(
                code="VAL-SCHED-WEEKLY-03",
                constraint="C2-DEADLINE",
                current=project_end,
                limit=canonical.deadline_week,
                delta_weeks=project_end - canonical.deadline_week,
                remediation="Extend deadline OR add resources OR reduce scope"
            ))
        
        # C3: Resource pool
        for week in range(schedule.deadline_week):
            usage = schedule.get_resource_usage(week)
            for resource, used in usage.items():
                capacity = canonical.recursos_pool[resource]
                if used > capacity:
                    violations.append(ConstraintViolation(
                        code="VAL-SCHED-WEEKLY-05",
                        constraint="C3-RESOURCES",
                        resource=resource,
                        current=used,
                        limit=capacity,
                        weeks=[week],
                        remediation="Add resource pool OR defer activities"
                    ))
        
        # Budget (indiretos)
        if canonical.indiretos["total"] > canonical.projeto.budget_indiretos:
            violations.append(ConstraintViolation(
                code="VAL-INDIRETOS-04",
                constraint="F1-BUDGET",
                current=canonical.indiretos["total"],
                limit=canonical.projeto.budget_indiretos,
                delta=canonical.indiretos["total"] - canonical.projeto.budget_indiretos,
                remediation="Extend deadline (reduces indiretos) OR reduce scope"
            ))
        
        return violations
```

### Replanning Candidate Generation

```python
class ReplanningCandidateGenerator:
    """Generate 3 strategic options when constraints violated."""
    
    def generate(self, violations: list[ConstraintViolation]) -> list[ReplanOption]:
        """
        For each violation type, propose option:
          - Deadline miss → Option 1: Extend deadline
          - Resource peak → Option 2: Add resources
          - Budget exceed → Option 3: Reduce scope
        """
        
        options = []
        
        for violation in violations:
            if violation.constraint == "C2-DEADLINE":
                # Option 1: Extend deadline
                extension_weeks = violation.delta_weeks + 1  # +1 safety margin
                option = ReplanOption(
                    name=f"Extend deadline by {extension_weeks} weeks",
                    type="relax_constraint",
                    changes={"deadline_week": "+{extension_weeks}"},
                    cost_delta=self._estimate_indiretos_delta(extension_weeks),
                    rationale="Feasible without resource stress",
                    client_approval_required=True
                )
                options.append(option)
            
            elif violation.constraint == "C3-RESOURCES":
                # Option 2: Add resources
                shortage = violation.current - violation.limit
                option = ReplanOption(
                    name=f"Hire {shortage} temporary {violation.resource}",
                    type="add_resource",
                    changes={"pool[{violation.resource}]": f"+{shortage}"},
                    cost_delta=self._estimate_labor_cost(shortage, violation.weeks),
                    rationale="Smooth resource peaks",
                    client_approval_required=False  # AGIS cost
                )
                options.append(option)
            
            elif violation.constraint == "F1-BUDGET":
                # Option 3: Reduce scope
                scope_reduction_pct = 20  # Default: defer 20%
                option = ReplanOption(
                    name=f"Defer {scope_reduction_pct}% activities (Phase 2)",
                    type="reduce_scope",
                    changes={"activities": f"Defer {scope_reduction_pct}%"},
                    cost_delta=-violation.delta,  # Budget savings
                    rationale="Phase 1 balanced, Phase 2 separate",
                    client_approval_required=True
                )
                options.append(option)
        
        return options[:3]  # Top 3 only
```

---

## Validation Rules

```python
class ReplannValidator:
    """Validate that replan option resolves violations."""
    
    def validate_option(
        self,
        option: ReplanOption,
        violations: list[ConstraintViolation],
    ) -> bool:
        """
        After applying replan option, check:
          - All hard constraints satisfied
          - Cost delta reasonable (< R$ 200k for Tier 1)
        """
        
        # Apply option to canonical (create virtual copy)
        canonical_new = apply_replan_option(canonical, option)
        
        # Re-validate
        violations_after = validate_schedule(canonical_new)
        
        # Check resolution
        hard_violations_after = [v for v in violations_after if v.is_hard]
        
        if not hard_violations_after:
            return True  # Option solves constraint
        else:
            return False  # Option incomplete
```

---

## Related ADRs / Skills

- **ADR-004** (Scheduling Algorithm): Multi-heuristic generation (top-3 candidates)
- **ADR-007** (Indirect Costs): Cost delta calculation when deadline extended
- **Skill 02B** (Weekly Schedule): Initial schedule that may have violations
- **(NOT IN SCOPE)** Skill 02C/02D: Execution-time feedback (REGELUNG)

---

## Definition of Done

- [x] `ConstraintViolation` model with violation details (`models/constraint_violation.py`)
- [x] `ConstraintValidator` with hard constraints C2 (deadline), C3 (resources), F1 (budget) (`scheduling/constraint_validator.py`)
- [x] `ReplanningCandidateGenerator` producing 3 strategic options (`replanning/generator.py`)
- [x] Impact assessment for each option (`replanning/assessor.py`)
- [x] Escalation rules via tier system in `replanning/models.py` + `replanning/detector.py`
- [x] CLI: `concilium replan validate` and `concilium replan replan-options` (`cli/commands_replan.py`)
- [x] Iterative loop: validate → replan-options → engineer decides → rerun skill → validate again
- [x] 14 test cases in `tests/unit/test_adr006_preventive_replan.py`:
  - [x] Deadline feasible → no C2 violation
  - [x] Deadline violated → ERRO with correct magnitude
  - [x] No cronograma → C2 check skipped
  - [x] Resource peak via conflitos_pico → ERRO violation
  - [x] Multiple conflicts → multiple violations
  - [x] Budget exceeded → ERRO with correct magnitude
  - [x] Budget not provided → F1 skipped
  - [x] Multiple violation types combined → all reported
  - [x] T3 generator produces ≥ 3 strategic options

---

## Summary

**Decision:** ADR-006 is a **STEUERUNG-only (pre-execution) replanning strategy** triggered by constraint violations during planning.

```
Hard constraint violated?
  ├─ Option 1: Relax constraint (negotiate with client)
  ├─ Option 2: Add resources (hire contractors)
  └─ Option 3: Reduce scope (defer activities)

Engineer chooses option, recalculates plan, validates again.
Loop until feasible OR escalate to director.
```

**NO execution-time feedback loop** (that would be REGELUNG, out of scope).

**Consequence:**
- Plan is feasible BEFORE execution starts
- Financial and schedule risks identified early
- Client expectations aligned (deadline, scope, cost)
- Director has clear decision points (escalation rules)

This is **preventive governance**, not reactive control.
