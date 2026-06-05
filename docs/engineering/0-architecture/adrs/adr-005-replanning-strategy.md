# ADR-005: Replanning Strategy: Triggers, Scope, and Governance

**Status:** Implementado  
**Date Decided:** 2026-04-29  
**Date Implemented:** 2026-04-29  
**Implementers:** scheduling/replan_trigger.py, scheduling/replan_generator.py, models/replan_decision.py  
**Context:** Weekly progress tracking (ADR-003) continuously reveals **deviations from plan**:

- Activity completes early (can accelerate successors?)
- Activity delays (will miss deadline?)
- Resource bottleneck discovered (reallocate teams?)
- Blocker appears (predecessor delayed, resource unavailable)

### The Problem

**Replanning is expensive:**
- Disrupts team continuity
- Requires new approvals
- May incur contract penalties
- Creates uncertainty

**But not replanning is also costly:**
- Cascading delays
- Resource idle time (high indirect costs)
- Missing contract deadline
- Opportunity loss (could accelerate with replan)

**Gap:** No formal framework for:
1. **When to replan** (triggers + thresholds)
2. **What to replan** (whole schedule vs. local adjustments)
3. **Scope of replan** (affected activities, resources, teams)
4. **Who decides** (engineer vs. manager vs. director)
5. **Cost/benefit analysis** (worth replanning or absorb delay?)

---

## Decision

We adopt a **tiered replanning strategy** with explicit triggers, scope definitions, and governance gates:

### D1 — Replanning Tiers (By Impact)

```
Tier 1: Local Rebalancing (No Replan)
  ├─ Scope: Single activity or adjacent pair
  ├─ Impact: <5% schedule change, no deadline risk
  ├─ Owner: Foreman / Activity Engineer
  └─ Approval: None (within contingency)

Tier 2: Tactical Replan (Quick Adjust)
  ├─ Scope: Activity chain (3–10 activities)
  ├─ Impact: 5–15% schedule change, deadline still safe
  ├─ Owner: Scheduling Engineer
  └─ Approval: Senior Engineer

Tier 3: Strategic Replan (Major Revision)
  ├─ Scope: Whole schedule or critical path
  ├─ Impact: >15% change OR deadline at risk
  ├─ Owner: Scheduling Engineer + Project Manager
  └─ Approval: Director + Client (if contract clause triggered)
```

---

### D2 — Automatic Replan Triggers

Replanning is **automatically triggered** if any condition below is detected:

#### Tier 1 Triggers (Automatic, No Approval)

| Trigger | Condition | Action |
|---------|-----------|--------|
| **T1-EARLY** | Activity completes >1 week early | Offer to accelerate successors (optional) |
| **T1-SLACK** | Activity has >2 weeks slack remaining | No action needed (acceptable variance) |
| **T1-WEATHER** | Single day lost to weather | Absorb into contingency (normal) |
| **T1-RESOURCE-PEAK** | Single week at 95–100% pool utilization | Monitor, but acceptable |

**Example:** PAVIM-01 finishes week 6 instead of week 7. COMPAC-01 can start week 6 instead of week 7 (1 week earlier). Offer to owner; no replan required.

#### Tier 2 Triggers (Auto-Escalate to Scheduling Engineer)

| Trigger | Condition | Action |
|---------|-----------|--------|
| **T2-DELAY** | Activity 1 week behind schedule | Analyze: replan local chain? Add teams? |
| **T2-BLOCKER-1W** | Activity blocked for 1+ week | Identify blocker, resolve or replan |
| **T2-RESOURCE-SUSTAINED** | Resource consistently at 100%+ for 2+ weeks | Reallocate or extend timeline |
| **T2-COST-OVERRUN** | Activity labor cost >20% over estimate | Review team composition, efficiency |
| **T2-PRODUCTIVITY-DRIFT** | Actual productivity <80% of baseline for 2 weeks | Diagnose: learning curve? Site issues? |

**Example:** EXCAV-01 is 1.5 weeks behind by end of week 7. Critical path extends 2 weeks. Trigger T2-DELAY → Scheduling Engineer analyzes: Can we add 1 team to EXCAV-01 weeks 8–9 to recover? Cost impact? Check pool availability.

#### Tier 3 Triggers (Escalate to Director)

| Trigger | Condition | Action |
|---------|-----------|--------|
| **T3-DEADLINE** | Project completion forecast > contract deadline | Critical: must replan or negotiate extension |
| **T3-CASCADE** | Delay in 1 activity cascades to 8+ successors | High-impact: replan critical path |
| **T3-RESOURCE-SHORTAGE** | Pool capacity insufficient for remainder of project | Strategic: hire more resources or reduce scope |
| **T3-COST-MILESTONE** | Cumulative cost >10% over budget | Financial impact: director decision required |

**Example:** Week 10 forecast shows project finishing week 28 instead of week 24 (4 weeks late, -R$ 400k penalty). Trigger T3-DEADLINE → Director decides: negotiate extension, add resources, reduce scope, or accept penalty.

---

### D3 — Replan Scope Definition

**What can be changed in each tier:**

#### Tier 1 Scope
- ✅ Start/end dates of individual activities (within slack)
- ✅ Activity acceleration (if predecessor done early)
- ❌ Resource reallocation across activities
- ❌ Deadline changes

#### Tier 2 Scope
- ✅ Team counts per activity-week (increase/decrease)
- ✅ Activity reordering (if no precedence violation)
- ✅ Activity consolidation (combine into fewer weeks)
- ✅ Local precedence relief (defer non-critical predecessors)
- ❌ Whole schedule restructuring
- ❌ Deadline changes (unless <1 week extension)

#### Tier 3 Scope
- ✅ Whole schedule restructuring
- ✅ Deadline negotiation (with client)
- ✅ Scope reduction (eliminate activities or reduce scope)
- ✅ Resource pool expansion (hire contractors)
- ✅ Team composition customization (override standard)
- ✅ Multiple parallel replans (explore alternatives)

---

### D4 — Replan Impact Assessment

Before implementing any replan, **cost/benefit analysis is mandatory**:

```python
class ReplannedImpactAssessment(BaseModel):
    """Quantifies impact of replanning option."""
    
    # Changes
    schedule_delta_days: int           # How many days does deadline change?
    team_count_delta: int              # How many teams added/removed total?
    cost_delta: float                  # R$ change in total cost
    resource_pool_delta: dict[str, int]  # Resource needs change
    
    # Benefits (why replan?)
    penalty_avoided: float             # R$ saved by avoiding late penalty
    expedite_revenue: float            # R$ earned by early completion (if contractual)
    efficiency_gain: float             # Hours saved, waste reduced
    
    # Costs (why not replan?)
    disruption_cost: float             # Team reassignment, learning loss
    admin_overhead: float              # Re-approval, communication
    contingency_consumed: float        # Buffer reduced
    risk_increase: float               # New dependencies, tighter margins
    
    # Decision metric
    net_benefit: float = (
        penalty_avoided + efficiency_gain
        - cost_delta - disruption_cost - risk_increase
    )
    
    recommendation: Literal["PROCEED", "ACCEPT_DELAY", "NEGOTIATE_EXTENSION"]
    
    if net_benefit > 50000:  # R$ 50k threshold
        recommendation = "PROCEED"
    elif net_benefit > 0:
        recommendation = "NEGOTIATE_EXTENSION"  # Only if net positive
    else:
        recommendation = "ACCEPT_DELAY"  # Not worth replanning cost
```

**Rule:** Replanning only proceeds if `net_benefit > threshold` for Tier 2+.

---

### D5 — Replan Execution Workflow

```
Trigger Detected (T1/T2/T3)
  ↓
Auto-Generate Replan Candidate(s)
  ├─ Tier 1: Offer 1 option (optional acceleration)
  ├─ Tier 2: Generate 3 alternatives (team add, local reorder, extend deadline)
  └─ Tier 3: Generate 5+ alternatives (full restructure options)
  ↓
Impact Assessment (Cost/Benefit)
  ├─ Compute net_benefit for each option
  ├─ Filter out negative-net options
  └─ Rank remaining by benefit
  ↓
Governance Gate
  ├─ Tier 1: Offer to foreman (accept/decline)
  ├─ Tier 2: Senior engineer reviews + approves/rejects
  └─ Tier 3: Director + client (negotiation)
  ↓
If Approved:
  ├─ Update canonical.cronograma_semanal_v[n+1]
  ├─ Update canonical.equipes_alocadas_v[n+1]
  ├─ Notify all affected teams
  ├─ Update forecast (ADR-003: forecast_completion)
  └─ Log replanning decision (audit trail)
  ↓
Rejected:
  ├─ Continue with existing schedule
  ├─ Monitor for next trigger
  └─ If deadline approaches, escalate to T3
```

---

### D6 — Replan Frequency Limits

To avoid **"replanning fatigue"** (constant schedule changes):

```python
class ReplannFrequencyPolicy:
    """Govern how often replanning can occur."""
    
    # Cannot replan more than once per N days
    min_days_between_replans: int = 7
    
    # Cannot replan same activity more than M times per project
    max_replans_per_activity: int = 3
    
    # Cannot have >N activities affected per replan
    max_activities_per_replan: int = 30  # If > 30 affected, must be Tier 3
    
    # Reason logging (audit)
    reason: str  # "resource shortage", "early completion", "blocker resolved"
    approved_by: str
    approval_date: datetime
```

**Rule:** If a second replan is proposed <7 days after the first, escalate to Tier 3 (director review). This signals instability.

---

## Interfaces / Implementation

### Replan Trigger Detection (ADR-003 Extended)

```python
class ReplannTriggerDetector:
    """Continuous monitoring for replan triggers."""
    
    def check_triggers(
        self,
        canonical: CanonicalModel,
        progress_update: ProgressUpdate,
        current_week: int,
    ) -> list[ReplannTrigger]:
        """
        After each progress update, check all triggers.
        Return list of detected triggers (empty if none).
        """
        triggers = []
        
        # Tier 1 triggers
        activity = canonical.atividades[progress_update.activity_id]
        schedule = canonical.cronograma_semanal[progress_update.activity_id]
        
        if activity.progress.is_completed and \
           activity.progress.completion_week < schedule.planned_end_week:
            weeks_early = schedule.planned_end_week - activity.progress.completion_week
            if weeks_early >= 1:
                triggers.append(ReplannTrigger(
                    tier=1,
                    code="T1-EARLY",
                    activity_id=activity.id,
                    weeks_early=weeks_early,
                    auto_action="offer_acceleration"
                ))
        
        # Tier 2 triggers
        if activity.progress.delay_weeks >= 1:
            triggers.append(ReplannTrigger(
                tier=2,
                code="T2-DELAY",
                activity_id=activity.id,
                delay_weeks=activity.progress.delay_weeks,
                escalate_to="scheduling_engineer"
            ))
        
        # Check resource pool sustainability
        weekly_usage = self._compute_weekly_usage(canonical, current_week)
        for resource_type, usage in weekly_usage.items():
            capacity = canonical.recursos_pool[resource_type]
            if usage >= capacity * 0.95:
                triggers.append(ReplannTrigger(
                    tier=1 if usage < capacity else 2,
                    code="T1/T2-RESOURCE-PEAK",
                    resource_type=resource_type,
                    usage_pct=usage / capacity * 100
                ))
        
        # Tier 3 triggers
        deadline_forecast = self._forecast_completion(canonical)
        if deadline_forecast > canonical.deadline_week:
            days_late = (deadline_forecast - canonical.deadline_week) * 7
            triggers.append(ReplannTrigger(
                tier=3,
                code="T3-DEADLINE",
                forecast_week=deadline_forecast,
                days_late=days_late,
                escalate_to="director"
            ))
        
        return triggers
```

### Replan Generation (Skill 02B Extended)

```python
class ReplannGenerator:
    """Generate replan candidates based on trigger."""
    
    def generate_candidates(
        self,
        canonical: CanonicalModel,
        trigger: ReplannTrigger,
        tier: int,
    ) -> list[ReplannCandidate]:
        """
        Generate 1 (Tier 1) to 5+ (Tier 3) replan options.
        Each candidate is a complete alternative schedule.
        """
        
        candidates = []
        
        if tier == 1:
            # Single option: accelerate successors
            if trigger.code == "T1-EARLY":
                candidate = self._accelerate_successors(
                    canonical, trigger.activity_id, trigger.weeks_early
                )
                candidates.append(candidate)
        
        elif tier == 2:
            # Multiple local options
            if trigger.code == "T2-DELAY":
                # Option 1: Add teams to delayed activity
                cand1 = self._add_teams_to_activity(
                    canonical, trigger.activity_id, num_teams_add=1
                )
                candidates.append(cand1)
                
                # Option 2: Reorder non-critical activities to free resources
                cand2 = self._reorder_slack_activities(
                    canonical, trigger.activity_id
                )
                candidates.append(cand2)
                
                # Option 3: Consolidate downstream, accept slight timeline shift
                cand3 = self._consolidate_downstream(
                    canonical, trigger.activity_id
                )
                candidates.append(cand3)
        
        elif tier == 3:
            # Full strategic options
            # Option 1: Add resources (hire more teams)
            cand1 = self._expand_resource_pool(canonical, expansion_pct=20)
            candidates.append(cand1)
            
            # Option 2: Reduce scope (defer non-critical activities)
            cand2 = self._reduce_scope(canonical, priority="cost")
            candidates.append(cand2)
            
            # Option 3: Negotiate deadline extension
            cand3 = self._extend_deadline(canonical, extension_weeks=2)
            candidates.append(cand3)
            
            # Option 4: Full restructure (restart schedule from scratch)
            cand4 = self._full_restructure(canonical)
            candidates.append(cand4)
        
        return candidates
    
    def _accelerate_successors(self, canonical, activity_id, weeks_early):
        """Move successor start dates earlier."""
        new_schedule = deepcopy(canonical.cronograma_semanal)
        
        for succ_id in canonical.activity_dag.successors(activity_id):
            current_start = new_schedule[succ_id]["start_week"]
            new_schedule[succ_id]["start_week"] = max(0, current_start - weeks_early)
        
        return ReplannCandidate(
            name=f"Accelerate successors of {activity_id}",
            schedule=new_schedule,
            # ... other fields
        )
```

### Impact Assessment

```python
class ImpactAssessor:
    """Quantify cost/benefit of replan candidate."""
    
    def assess(
        self,
        canonical_current: CanonicalModel,
        candidate: ReplannCandidate,
    ) -> ReplannImpactAssessment:
        """
        Compute all deltas and recommendation.
        """
        
        # Current state metrics
        current_metrics = self._compute_metrics(canonical_current)
        
        # Apply candidate, recompute
        canonical_new = deepcopy(canonical_current)
        canonical_new.cronograma_semanal = candidate.schedule
        canonical_new.equipes_alocadas = candidate.team_allocations
        
        new_metrics = self._compute_metrics(canonical_new)
        
        # Deltas
        schedule_delta = new_metrics["project_duration"] - current_metrics["project_duration"]
        cost_delta = new_metrics["total_cost"] - current_metrics["total_cost"]
        
        # Benefits
        penalty_avoided = 0
        if current_metrics["days_late"] > 0:
            # Contract penalty for late completion
            penalty_rate = canonical_current.projeto.multa_atraso_per_day  # R$/day
            days_saved = min(current_metrics["days_late"], schedule_delta * 7)
            penalty_avoided = days_saved * penalty_rate
        
        disruption_cost = self._estimate_disruption(canonical_current, candidate)
        
        # Net benefit
        net_benefit = penalty_avoided - cost_delta - disruption_cost
        
        # Recommendation
        if net_benefit > 50_000:
            recommendation = "PROCEED"
        elif net_benefit > 0:
            recommendation = "NEGOTIATE_EXTENSION"
        else:
            recommendation = "ACCEPT_DELAY"
        
        return ReplannImpactAssessment(
            schedule_delta_days=schedule_delta * 7,
            cost_delta=cost_delta,
            penalty_avoided=penalty_avoided,
            disruption_cost=disruption_cost,
            net_benefit=net_benefit,
            recommendation=recommendation,
        )
```

### Governance Gate (CLI)

```bash
# Trigger detected automatically
# Engineer receives notification
concilium replan status --project lote09-ce --week 10

# Output:
# ⚠️ TRIGGER DETECTED: T2-DELAY
# Activity: EXCAV-01
# Delay: 1.5 weeks
# Forecast impact: Project +2 weeks
# 
# Generated 3 candidates:
# 1. Add 1 team to EXCAV-01 (weeks 8–9)
#    Cost delta: +R$ 15k
#    Penalty avoided: +R$ 50k
#    Net benefit: +R$ 35k ✅ PROCEED
# 
# 2. Reorder slack activities (defer non-critical)
#    Cost delta: -R$ 5k (overhead saved)
#    Penalty avoided: +R$ 35k
#    Net benefit: +R$ 40k ✅ PROCEED
# 
# 3. Accept delay
#    Cost delta: 0
#    Penalty: -R$ 75k
#    Net benefit: -R$ 75k ❌ NOT WORTH IT

# Engineer approves option 1
concilium replan approve \
  --project lote09-ce \
  --trigger T2-DELAY \
  --option 1 \
  --reason "Add teams to recover delay" \
  --approval-signature "engineer_001"

# Output:
# ✅ Replan approved
# Schedule v11 created
# Teams notified: EXCAV-01 adding 1 team week 8
# Updated deadline: Week 26 (was 28)
# Financial impact: +R$ 35k net benefit
```

---

## Validation Rules

```python
class ReplannValidator:
    """Validate replan candidate before execution."""
    
    def validate(
        self,
        candidate: ReplannCandidate,
        canonical: CanonicalModel,
    ) -> list[ValidacaoItem]:
        """Check replan doesn't violate constraints."""
        
        validacoes = []
        
        # VAL-REPLAN-01: Precedence still respected
        for (pred, succ) in canonical.activity_dag.edges:
            pred_end = candidate.schedule[pred]["end_week"]
            succ_start = candidate.schedule[succ]["start_week"]
            if succ_start < pred_end:
                validacoes.append(ValidacaoItem(
                    codigo="VAL-REPLAN-01",
                    status="ERRO",
                    mensagem=f"Precedence violated: {succ} starts before {pred} ends"
                ))
        
        # VAL-REPLAN-02: Deadline still met (or intentionally extended)
        project_end = max(
            schedule[a]["end_week"] for a in candidate.schedule
        )
        if project_end > canonical.deadline_week + 2:  # Allow 2-week extension
            validacoes.append(ValidacaoItem(
                codigo="VAL-REPLAN-02",
                status="AVISO",
                mensagem=f"Deadline extends {project_end - canonical.deadline_week} weeks"
            ))
        
        # VAL-REPLAN-03: Resource pool still feasible
        pool_violations = ResourcePoolValidator().validate_schedule(
            candidate.schedule,
            candidate.team_allocations,
            canonical.recursos_pool
        )
        if pool_violations:
            validacoes.extend(pool_violations)
        
        # VAL-REPLAN-04: Activity durations unchanged
        for activity_id in canonical.eap:
            old_duration = canonical.cronograma_semanal[activity_id]["duration_weeks"]
            new_duration = candidate.schedule[activity_id]["duration_weeks"]
            if old_duration != new_duration:
                validacoes.append(ValidacaoItem(
                    codigo="VAL-REPLAN-04",
                    status="ERRO",
                    mensagem=f"{activity_id} duration changed {old_duration} → {new_duration}"
                ))
        
        # VAL-REPLAN-05: Replanning frequency respected
        last_replan = canonical.replanning_history[-1].approval_date if canonical.replanning_history else None
        if last_replan and (datetime.now() - last_replan).days < 7:
            validacoes.append(ValidacaoItem(
                codigo="VAL-REPLAN-05",
                status="AVISO",
                mensagem="Replanning within 7 days of previous replan. Schedule instability risk."
            ))
        
        return validacoes
```

---

## Audit Trail

Every replan decision is **permanently recorded**:

```python
class ReplannDecision(BaseModel):
    """Immutable record of replanning decision."""
    
    replan_id: str                      # UUID
    trigger: ReplannTrigger
    tier: int
    
    candidates_generated: list[ReplannCandidate]
    assessments: list[ReplannImpactAssessment]
    
    selected_candidate_id: str
    selected_recommendation: str
    
    approval_chain: list[dict]          # {approver, role, date, signature}
    # Tier 1: foreman (optional)
    # Tier 2: senior_engineer
    # Tier 3: director + client (if applicable)
    
    schedule_version_before: str        # v10
    schedule_version_after: str         # v11
    
    rationale: str
    created_at: datetime
    approved_at: datetime
```

---

## Related ADRs

- **ADR-003** (Progress Accumulation): Detects deviations that trigger replanning
- **ADR-004** (Scheduling Algorithm): Used to re-generate schedule in replan
- **ADR-006** (Team Composition): May need to adjust team allocations in replan


---

## Definition of Done

- [ ] `ReplannTrigger` and `ReplannCandidate` models
- [ ] `ReplannTriggerDetector` implemented (all T1/T2/T3 triggers)
- [ ] `ReplannGenerator` with Tier 1/2/3 logic
- [ ] `ImpactAssessor` with cost/benefit calculation
- [ ] `ReplannValidator` with VAL-REPLAN-01 to 05
- [ ] `ReplannFrequencyPolicy` enforced
- [ ] CLI commands: `replan status`, `replan approve`
- [ ] Governance workflow tested (Tier 1/2/3 approvals)
- [ ] Audit trail (ReplannDecision) logged to canonical
- [ ] Integration with ADR-003 (trigger detection post-progress-update)
- [ ] 8+ test cases:
  - [ ] T1-EARLY: accelerate successors
  - [ ] T2-DELAY: add teams
  - [ ] T2-BLOCKER: unblock resource
  - [ ] T3-DEADLINE: full restructure
  - [ ] Negative net-benefit: reject replan
  - [ ] Replanning too frequent: escalate
  - [ ] Precedence violated in candidate: reject
  - [ ] Director approval workflow

---

## Phase Implementation

### Phase 1 (MVP) — Tier 1 Triggers + Offer

**Sprint 1A:** Trigger detection (1.5 weeks)
- T1-EARLY, T1-SLACK, T1-WEATHER, T1-RESOURCE-PEAK
- Simple notifications to foreman

**Sprint 1B:** Optional acceleration (1.5 weeks)
- Generate 1 candidate (accelerate successors)
- Foreman can accept/decline

### Phase 2 (Post-MVP) — Tier 2 Triggers + Tactical Replan

**Sprint 2A:** Tier 2 detection + generation (2 weeks)
- T2-DELAY, T2-BLOCKER, T2-RESOURCE-SUSTAINED, T2-COST-OVERRUN
- Generate 3 candidates per trigger

**Sprint 2B:** Impact assessment + approval (2 weeks)
- Cost/benefit analysis
- Senior engineer approval workflow

### Phase 3 — Tier 3 Triggers + Strategic Replan

**Sprint 3A:** Tier 3 detection (1 week)
- T3-DEADLINE, T3-CASCADE, T3-RESOURCE-SHORTAGE, T3-COST-MILESTONE

**Sprint 3B:** Strategic candidate generation (3 weeks)
- Full restructure, scope reduction, resource expansion
- Director + client negotiation workflow

---

## Summary

**Decision:** Replanning follows a **tiered strategy** with explicit triggers, automatic candidate generation, impact assessment, and governance gates.

```
T1 (Local Adjustment)
  Trigger: 1 week early / weather day / resource peak
  Owner: Foreman (optional accept)
  Approval: None

T2 (Tactical Replan)
  Trigger: 1 week delay / blocker / sustained high resource
  Owner: Scheduling Engineer (generates 3 options)
  Approval: Senior Engineer

T3 (Strategic Replan)
  Trigger: Deadline at risk / cascading delays / resource shortage
  Owner: Scheduling Engineer + Project Manager (generates 5+ options)
  Approval: Director + Client
```

**Consequence:**
- Replanning is **data-driven** (triggers based on facts)
- Decisions are **cost-justified** (net benefit calculated)
- Governance is **clear** (who decides at each tier)
- Audit trail is **complete** (all replanning decisions recorded)
- Frequency is **limited** (prevent instability)

This is the **control loop** that closes the planning cycle: Progress → Trigger → Replan → New Schedule → Progress tracking continues.
