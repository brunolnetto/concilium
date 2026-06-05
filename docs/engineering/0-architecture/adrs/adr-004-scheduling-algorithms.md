# ADR-004: Activity Scheduling Algorithm Selection Strategy

**Status:** Implementado  
**Date Decided:** 2026-04-29  
**Date Implemented:** 2026-04-29  
**Implementers:** skills/02B-cronograma-semanal, scheduling/serial_scheduler.py, scheduling/milp.py  
**Context:** Skill 02B needs to **generate a weekly schedule** given:

- Activity DAG with precedence constraints (from Skill 00B)
- Resource pool capacities (from Skill 01A)
- Activity durations in weeks (from Skill 02 monthly baseline)
- Contract deadline
- Efficiency model for progress tracking (ADR-003)

### The Problem

**Scheduling is NP-hard.** No algorithm guarantees:
1. Optimal makespan (shortest total duration)
2. Feasibility under all constraints
3. Fast execution (deterministic + sub-second)
4. Simplicity in implementation

Different works have different characteristics:

| Work Type | Size | Criticality | Complexity | Algorithm Fit |
|-----------|------|-------------|-----------|---|
| **Small paving (200 m²)** | 10–15 activities | High margin | Simple DAG | MILP (exato) |
| **Highway section (5 km)** | 50–80 activities | Medium | Moderate DAG | Serial PRB (fast) |
| **Large earthwork (100 ha)** | 200+ activities | Low | Complex DAG, resource contention | Parallel + Tabu |

**Gap:** No formal decision on:
1. **Which algorithm to use by default**
2. **How to select algorithm for a specific work**
3. **What trade-offs are acceptable** (speed vs. quality)
4. **How to handle infeasibility** (replan triggers)

---

## Decision

We adopt a **multi-algorithm strategy with intelligent selection**:

### D1 — Default Algorithm: Serial Scheduling with Priority Rules (PRB)

**Serial PRB is the MVP + standard choice** because:

| Criterion | Serial PRB | MILP | Parallel | GA/Tabu |
|-----------|-----------|------|----------|---------|
| **Implementation complexity** | Low | Medium | Low–Medium | High |
| **Determinism** | ✅ Yes | ✅ Yes | ✅ Yes | ⚠️ No (GA) |
| **Speed** | ✅ O(n²×m×w) | ❌ NP-hard | ✅ O(n²×m×w) | ⚠️ Tunable |
| **Handles hard constraints** | ✅ All (C1–C5) | ✅ All | ✅ All | ✅ Most |
| **Reproducibility** | ✅ Same input → same output | ✅ Yes (if solver deterministic) | ✅ Yes | ⚠️ Random seed dependent |
| **Practical for <150 activities** | ✅ <1s | ✅ <30s | ✅ <1s | ✅ Tunable |

**Serial PRB specifics:**

```python
class SerialScheduler:
    """
    Process activities in priority order.
    For each activity:
      1. Find earliest feasible start (respects precedence)
      2. Find first week where activity + teams fit in pool
      3. Allocate activity to that week range
    
    Supports multiple heuristics (priority rules):
      - MINSLK (Min Slack First) ← default
      - LPT (Longest Processing Time)
      - ES (Earliest Start)
      - MAXRES (Max Resource First)
    """
```

---

### D2 — Algorithm Selection Strategy (By Work Size)

```python
def select_scheduling_algorithm(
    num_activities: int,
    num_resource_types: int,
    contract_duration_weeks: int,
    deadline_margin_pct: float,  # Buffer available
    criticality: str,  # "low", "medium", "high"
) -> SchedulingStrategy:
    """
    Select algorithm based on problem characteristics.
    
    Returns: algorithm to use + expected quality
    """
    
    problem_size = num_activities * num_resource_types * contract_duration_weeks
    
    # Very small, critical works → try exact solution
    if num_activities <= 50 and criticality == "high":
        return SchedulingStrategy(
            algorithm="MILP",
            rationale="Small + critical → worth 30s to find optimal",
            fallback="SerialScheduler(MINSLK)",
            timeout_seconds=30,
        )
    
    # Medium works → fast heuristic
    if num_activities <= 150:
        return SchedulingStrategy(
            algorithm="SerialScheduler",
            heuristics=["MINSLK", "LPT", "MAXRES"],  # Try all, return top-3
            rationale="Medium size → fast iteration, good-enough quality",
            time_limit_seconds=5,
        )
    
    # Large works → scalable heuristic
    if num_activities > 150:
        return SchedulingStrategy(
            algorithm="SerialScheduler + ParallelScheduler",
            heuristics=["MINSLK"],  # Simpler for large
            rationale="Large → focus on feasibility, not optimality",
            leveling_pass=True,
            time_limit_seconds=10,
        )
    
    # Default: safest choice
    return SchedulingStrategy(
        algorithm="SerialScheduler",
        heuristics=["MINSLK"],
        rationale="Default: proven, deterministic, fast",
    )
```

---

### D3 — Multi-Heuristic Exploration (Top-3 Ranking)

Serial PRB can run with **multiple priority rules in parallel**:

```python
def explore_schedules(
    activities, dag, pool, durations, deadline, 
    heuristics=["MINSLK", "LPT", "MAXRES", "ES", "GR"]
) -> list[ScheduleOutput]:
    """
    Run Serial PRB with each heuristic.
    Rank results by quality metrics.
    Return top-3 for human review.
    """
    
    results = []
    for heuristic in heuristics:
        scheduler = SerialScheduler(priority_rule=heuristic)
        try:
            schedule = scheduler.schedule(
                activities, dag, pool, durations, deadline
            )
            metrics = compute_quality_metrics(schedule, pool)
            results.append((schedule, metrics, heuristic))
        except ScheduleError:
            pass  # This heuristic infeasible, skip
    
    # Rank by composite score
    ranked = sorted(
        results,
        key=lambda x: (
            x[1]["makespan"],              # Primary: shortest duration
            x[1]["resource_leveling_score"],  # Secondary: smoothness
            x[1]["idle_time"]              # Tertiary: minimize gaps
        )
    )
    
    return ranked[:3]  # Top 3 schedules
```

---

### D4 — Fallback Strategy for Infeasibility

If Serial PRB + all heuristics fail:

```
Feasibility Chain:
  1. Try MINSLK (default)
  2. Try LPT, MAXRES, ES (other heuristics)
  3. If all fail → try relaxations:
     a) Relax resource constraint slightly (110% pool)
     b) Try Parallel Scheduler (resource leveling)
  4. If still fail → try MILP with relaxed deadline (+1 week)
  5. If MILP fails → return INFEASIBLE + suggest replan triggers

Never silently accept infeasibility.
```

---

### D5 — Quality Metrics for Ranking

Compare schedules across multiple dimensions:

```python
class ScheduleMetrics:
    makespan: int                    # Total weeks (primary)
    resource_leveling_score: float   # Variance of weekly usage
    idle_time: int                   # Weeks with zero activity
    activity_fragmentation: int      # Count of gaps in activities
    critical_path_slack_min: float   # Minimum slack (tightness)
    resource_utilization_avg: float  # % avg usage
    
    # Composite score (weighted)
    def quality_score(
        self,
        weight_makespan=0.5,
        weight_leveling=0.2,
        weight_idle=0.15,
        weight_utilization=0.15,
    ) -> float:
        """
        score = 
            (1 - makespan/deadline_weeks) * weight_makespan +
            (1 - leveling_score / max_leveling) * weight_leveling +
            (1 - idle_time / total_weeks) * weight_idle +
            resource_utilization_avg * weight_utilization
        
        Higher is better. Range [0, 1].
        """
```

---

## Rationale

### Why Serial PRB as Default?

1. **Proven in practice:** CPM-based scheduling is industry standard
2. **Fast:** O(n²×m×w) is acceptable for 100–150 activities
3. **Deterministic:** Same inputs → same output (reproducible)
4. **Flexible:** Multiple heuristics allow exploration without reimplementation
5. **Debuggable:** Each step is transparent (priority order → allocation)
6. **Evolutionary path:** Easy to upgrade to Parallel later

### Why Not MILP/GA/Tabu by Default?

| Method | Problem |
|--------|---------|
| **MILP** | Solver dependency (CBC, Gurobi), convergence unpredictable, overkill for 100+ activities |
| **GA** | Non-deterministic, requires parameter tuning, harder to debug |
| **Tabu** | Requires careful tuning of tabu list size + iteration count |

### Why Top-3 Ranking?

Engineers must **make informed decisions**, not blind trust the algorithm:

```
Schedule A: 12 weeks, smooth resource usage
Schedule B: 11 weeks, high peaks (resource constraint?)
Schedule C: 12 weeks, low idle time

Engineer chooses based on context:
- Rush project? Pick B (accept peaks, add equipment)
- Steady work culture? Pick A (predictable)
- Cost-sensitive? Pick C (minimize overhead)
```

---

## Interfaces / Implementation

### Main Entry Point: Skill 02B

```python
class Skill02BCronogramaSemanal:
    """Generate weekly schedule using multi-algorithm strategy."""
    
    def run(
        self,
        canonical: CanonicalModel,
        inputs: dict,
        catalogo: dict,
    ) -> SkillResult:
        """
        Input: Monthly cronograma + precedence DAG + pool + durations
        Output: Weekly schedule + top-3 alternatives + metrics
        """
        
        activity_dag = canonical.activity_dag
        pool = canonical.recursos_pool
        durations_weeks = extract_durations(canonical)
        deadline_weeks = compute_deadline_weeks(canonical)
        
        # Select algorithm strategy
        strategy = select_scheduling_algorithm(
            num_activities=len(canonical.eap),
            num_resource_types=len(pool),
            contract_duration_weeks=deadline_weeks,
            deadline_margin_pct=compute_margin(canonical),
            criticality=assess_criticality(canonical),
        )
        
        # Execute primary algorithm
        schedules = []
        if strategy.algorithm == "SerialScheduler":
            schedules = self._explore_heuristics(
                canonical, activity_dag, pool, durations_weeks, deadline_weeks,
                heuristics=strategy.heuristics
            )
        elif strategy.algorithm == "MILP":
            schedule = self._milp_schedule(...)
            schedules = [schedule]
        elif strategy.algorithm == "SerialScheduler + ParallelScheduler":
            serial_schedules = self._explore_heuristics(...)
            schedules = [self._level_resources(s) for s in serial_schedules]
        
        # Fallback if infeasible
        if not schedules:
            schedules = self._fallback_infeasible(...)
        
        # Rank and select top-3
        top_3 = rank_schedules(schedules, deadline_weeks)
        
        # Store in canonical
        canonical.cronograma_semanal_candidates = top_3
        canonical.cronograma_semanal_selected = top_3[0]  # Auto-select best
        
        # Generate validations
        validacoes = self._validate_schedules(top_3, canonical)
        
        return SkillResult(
            canonical=canonical,
            validacoes=validacoes
        )
    
    def _explore_heuristics(self, ...):
        """Run Serial PRB with multiple heuristics."""
        return explore_schedules(
            activities, dag, pool, durations, deadline,
            heuristics=["MINSLK", "LPT", "MAXRES", "ES", "GR"]
        )
    
    def _milp_schedule(self, ...):
        """Fallback to MILP if time allows."""
        solver = MILPScheduler(timeout_seconds=30)
        try:
            return solver.schedule(...)
        except TimeoutError:
            return None
```

### CLI Integration

```bash
# Generate schedule (auto-selects algorithm)
concilium schedule weekly \
  --project lote09-ce \
  --show-candidates top-3 \
  --output schedules.json

# Output:
# Algorithm: SerialScheduler (MINSLK, LPT, MAXRES)
# Top-3 schedules:
#   1. MINSLK: 12 weeks, leveling_score=0.85
#   2. LPT:    11 weeks, leveling_score=0.72
#   3. MAXRES: 12 weeks, leveling_score=0.88
#
# Selected: #1 (best balance)
# Details: schedules.json

# Force specific algorithm
concilium schedule weekly \
  --project lote09-ce \
  --algorithm milp \
  --timeout 60

# Inspect alternative
concilium schedule weekly \
  --project lote09-ce \
  --select-candidate 2 \
  --save-as-alternative
```

---

## Validation Rules

```python
class ScheduleValidator:
    def validate(self, schedule: ScheduleOutput, canonical: CanonicalModel):
        """Ensure schedule meets all hard constraints."""
        
        # VAL-SCHED-01: All activities scheduled
        assert len(schedule.scheduled_activities) == len(canonical.eap), \
            "Not all activities scheduled"
        
        # VAL-SCHED-02: Precedence respected
        for (pred, succ) in canonical.activity_dag.edges:
            pred_end = schedule.get_end_week(pred)
            succ_start = schedule.get_start_week(succ)
            assert succ_start >= pred_end, \
                f"Precedence violated: {succ} starts before {pred} ends"
        
        # VAL-SCHED-03: Deadline met
        project_end = max(schedule.get_end_week(a) for a in schedule.scheduled_activities)
        assert project_end <= canonical.deadline_week, \
            f"Schedule exceeds deadline: {project_end} > {canonical.deadline_week}"
        
        # VAL-SCHED-04: Resource capacity not exceeded
        for week in range(canonical.deadline_week):
            usage = schedule.get_resource_usage(week)
            for resource_type, used in usage.items():
                capacity = canonical.recursos_pool[resource_type]
                assert used <= capacity, \
                    f"Week {week}, {resource_type}: {used} > capacity {capacity}"
        
        # VAL-SCHED-05: Durations respected
        for activity in schedule.scheduled_activities:
            actual_duration = schedule.get_duration(activity)
            planned_duration = canonical.get_planned_duration(activity)
            assert actual_duration == planned_duration, \
                f"{activity}: duration mismatch"
```

---

## Replanning Triggers

If schedule violates constraints or shows poor metrics:

| Trigger | Action |
|---------|--------|
| `resource_leveling_score < 0.5` | High peaks; suggest adding equipment |
| `idle_time > 10% of deadline` | Resource under-utilized; suggest combining activities |
| `makespan > deadline × 0.95` | Tight margin; suggest contingency buffer |
| `critical_path_slack_min < 1 week` | No slack; any delay cascades; high risk |

---

## Phase Implementation

### Phase 1 (MVP) — Serial PRB

**Sprint 1A:** Serial Scheduler + MINSLK heuristic (2 weeks)
- ✅ Minimal viable scheduling
- ✅ Handles hard constraints C1–C5
- ✅ Deterministic, fast

**Sprint 1B:** Multi-heuristic exploration + ranking (1 week)
- Add LPT, MAXRES, ES, GR
- Compare quality metrics
- Return top-3 for review

### Phase 2 (Refinement) — Parallel + Resource Leveling

**Sprint 2A:** Parallel Scheduler (2 weeks)
- Add resource leveling pass
- Reduce peaks in usage

**Sprint 2B:** Fallback chain (1 week)
- If Serial infeasible → try relaxations
- If still fail → MILP as last resort

### Phase 3 (Optimization) — MILP / Metaheuristics

**Sprint 3A:** MILP integration (3 weeks)
- PuLP + CBC solver
- For small/critical works
- 30s timeout → fallback to Serial

**Sprint 3B:** Tabu Search optional (3 weeks)
- Fast local search
- For large works where Serial struggles

---

## Trade-offs

| Choice | Pro | Con |
|--------|-----|-----|
| **Serial PRB default** | Fast, deterministic, simple | Not always optimal |
| **Top-3 ranking** | Informed decision-making | More computation |
| **Multi-heuristic** | Robust (one fails, others work) | More code to maintain |
| **Fallback chain** | Graceful degradation | Complexity hidden |
| **MILP optional** | True optimality possible | Solver dependency |

---

## Related ADRs

- **ADR-001** (Semantic Layer): ScopeItem → Activity mapping
- **ADR-002** (Resolution): CPU → produtividade (input to duration estimation)
- **ADR-003** (Progress Accumulation): Weekly progress tracking via efficiency model
- **ADR-005** (Replanning strategy): when/how to replan based on progress

---

## Definition of Done

- [x] `SerialScheduler` class with MINSLK heuristic implemented + tested
- [x] Additional heuristics (LPT, MAXRES, ES, GR) implemented
- [x] `explore_schedules()` function returns top-3 ranked
- [x] `ScheduleMetrics` computed for all schedules
- [x] `select_scheduling_algorithm()` decision function
- [x] Skill 02B refactored to use new scheduler
- [x] `ScheduleValidator` with VAL-SCHED-01 to 05
- [x] CLI commands: `schedule weekly`, `--algorithm`, `--select-candidate`
- [x] 10+ test cases (feasible, infeasible, early deadline, large DAG, resource contention)
- [x] Phase 2 fallback chain planned + dependencies clarified
- [x] MILP solver (CBC) optional dependency documented

---

## Summary

**Decision:** Activity scheduling uses **Serial PRB (Priority Rule Based) with multi-heuristic exploration** as default, with intelligent algorithm selection based on work size and criticality.

```
Problem size ≤ 50 activities + high criticality
  → MILP (exact solution, 30s timeout)

50 < activities ≤ 150
  → Serial PRB (MINSLK + 4 other heuristics, top-3)

activities > 150
  → Serial PRB + Parallel leveling (scalable, acceptable quality)

All feasible schedules
  → Rank by metrics (makespan, leveling, utilization)
  → Return top-3 for human selection
```

**Consequence:** Deterministic, transparent, auditable schedule generation that feeds directly into:
- Weekly progress tracking (ADR-003)
- Resource allocation and leveling
- Replanning triggers (ADR-005)
- Permanência calculation (indiretos)

This is the **orchestrator of weekly operations** in Concilium.
