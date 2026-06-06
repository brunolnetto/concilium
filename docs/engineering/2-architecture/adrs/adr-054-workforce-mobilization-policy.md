# ADR-054: Workforce Mobilization Policy System for Compositional Activities

**Status:** Implementado
**Date:** 2026-05-15  
**Author:** Engenheiro Sênior  
**Supersedes:** Portions of ADR-046 (RCPSP duration assumptions)  
**Related:** ADR-005 (Replanning), ADR-030 (CPU Cost Model), ADR-039 (Bridge Analysis), ADR-046 (RCPSP), ADR-053 (CPU/Produção Separation)

## Plano de Implementação

| Fase | Entregas | Status |
|------|----------|--------|
| **Phase 0** — Foundation | `MobilizacaoPolicy`, `CurvaForca`, `WorkforcePolicySimulator`, 42 unit tests, API endpoints (policies + simulate), `curvas_forca` em `CanonicalModel` | ✅ Concluído |
| **Phase 1** — Pipeline Integration | `_expand_mobilizacao_policies` em Skill 04, injeção no `PipelineService`, deliverables config (endpoints + storage) | ✅ Concluído |
| **Phase 2** — UI | `render_mobilizacao_policy_editor` (substituiu editor de equipes), `render_deliverables_config`, `extract_eap_items_for_policy` | ✅ Concluído |
| **Phase 3** — Validation & Hardening | `VAL-WMP-POOL`, `VAL-WMP-DESMOB`, persistência de `curvas_forca` no canonical via Skill 04, endpoint `/validate`, painel de validação no UI | ✅ Concluído |
| **Conclusão** | `use_mobilizacao_policy` em `RunProjectRequest`, `Atividade.mobilizacao_policy` embedded (§7.2), prioridade embedded > file override, testes de integração Skill 04 (17 casos) | ✅ Concluído |

## Definition of Done

### Phase 0
- [x] `MobilizacaoPolicy` frozen Pydantic model com validação
- [x] `CurvaForca` / `CurvaForcaSemanal` value objects
- [x] `WorkforcePolicySimulator.simulate()` puro (sem I/O)
- [x] `CurvaForca.to_num_equipes_por_semana()` — bridge para Skill 04 MANUAL mode
- [x] 42 testes cobrindo todos os edge cases do ADR
- [x] `curvas_forca: list[CurvaForca]` em `CanonicalModel`
- [x] `GET/POST/DELETE /mobilizacao-policies` endpoints
- [x] `POST /mobilizacao-policies/simulate` endpoint (stateless)

### Phase 1
- [x] `_expand_mobilizacao_policies()` injeta WMP como `num_equipes_por_item` no Skill 04
- [x] `PipelineService._execute_run` lê `mobilizacao_policy_override.json` e injeta
- [x] `mobilizacao_policy_override.json` em `ProjectFiles`
- [x] `deliverables_config.json` em `ProjectFiles` com 7 outputs configuráveis
- [x] `GET/PUT /deliverables-config` endpoints
- [x] 91 testes passando (0 regressões)

### Phase 2
- [x] `render_mobilizacao_policy_editor` substitui `render_team_editor` no HOT template
- [x] Expander de opções avançadas (desmobilização, plateau)
- [x] Botões Salvar + Replanejar integrados ao novo fluxo
- [x] `render_deliverables_config` no final de `sub_plan`
- [x] `extract_eap_items_for_policy` em `helpers.py`

### Phase 3
- [x] `VAL-WMP-POOL` — n_max vs resource pool check
- [x] `VAL-WMP-DESMOB` — demobilização forçada antes da entrega
- [x] `curvas_forca` persistidas no canonical em cada run WMP
- [x] `POST /mobilizacao-policies/validate` endpoint
- [x] Painel de validação inline no UI (botão "🔍 Validar políticas")

### Conclusão
- [x] `RunProjectRequest.use_mobilizacao_policy: bool = True` (ADR-054 §9.1)
- [x] `PipelineService` honra o flag — `use_mobilizacao_policy=False` bypassa WMP
- [x] `Atividade.mobilizacao_policy: MobilizacaoPolicy | None` (ADR-054 §7.2)
- [x] `_expand_mobilizacao_policies` lê policies embedded nas `Atividade` com prioridade sobre arquivo
- [x] 17 testes de integração cobrindo: modo MANUAL via WMP, curvas_forca, forma da rampa, entrega completa, prioridade de overrides, `Atividade.mobilizacao_policy`, VAL-WMP-01/03/POOL/DESMOB, sem WMP, praticabilidade, correspondência distribuicao_semanal

---

## 1. Context and Problem Statement

The current system requires planners to provide explicit per-week team allocations (`num_equipes_por_item[item_id][week_key]`) or RCPSP parameters with pre-computed `duration_weeks`. Neither input can be derived automatically from a scheduling intent.

**The fundamental problem:** the system's computation direction is inverted relative to how planning engineering actually works.

| Direction | Current System | Planning Engineering Reality |
|-----------|---------------|------------------------------|
| Input | Weekly team allocation (explicit) | Quantity Q, Productivity P, Policy |
| Derived | None (allocation is the schedule) | Duration T (weeks), weekly allocation curve |
| Duration | Exogenous — must be given | Endogenous — derived from Q, P, n(t), p(t) |

A planner knows: *"I need to move Q m³, I can mobilize up to n_max teams, ramping at c_mob teams/week."* The system should answer: *"You need T weeks, here is your weekly team curve."*

Currently the planner must answer the system's question instead.

This ADR formalizes the introduction of a **Workforce Mobilization Policy** (WMP) attached to each compositional activity, replacing explicit per-week allocation with a declarative policy from which the execution timeline and weekly curve are deterministically derived.

---

## 2. Current Architecture Overview

### 2.1 Skill Pipeline Sequence

```
Skill 01: escopo-e-eap          → canonical.eap, canonical.atividades
Skill 02: (unused/deprecated)
Skill 03: alocacao-recursos     → canonical.recurso_pool, canonical.alocacoes
Skill 04: cronograma            → canonical.cronograma (weekly schedule)
Skill 05: equipes-e-alocacao    → canonical.equipes_diretas (team costs)
Skill 06: precificacao-unitaria → canonical.planejamento (PU × qty)
Skill 07: custos-indiretos      → canonical.indiretos
Skill 08: consolidacao-financeira → canonical.resultado
```

### 2.2 Data Flow for Scheduling (Skill 04)

```
Inputs (from skill_inputs + overrides):
  num_equipes_por_item: {item_id: {week_key: int}}   ← explicit weekly allocation
  OR
  rcpsp_spec: {activities: [{duration_weeks: int}]}   ← RCPSP with pre-computed durations

Catalog:
  cpus.json → producao_horaria (P)
  praticabilidade → eficiencia_semanal (p_i per week)

Computation (Skill 04):
  qtd_executada_semana = P × m × h × p_i × n_equipes_i
  qtd_acumulada = Σ qtd_executada

Output (canonical.cronograma):
  scheduled_activities[i].distribuicao_semanal: {week_key: DistribuicaoSemanal}
    num_equipes, qtd_executada, qtd_acumulada, pct, eficiencia
```

### 2.3 Key Files

| Concern | File |
|---------|------|
| Scheduling computation | `src/concilium/application/skills/manifests/04-cronograma/skill.py` |
| RCPSP solver | `src/concilium/application/scheduling/` |
| Team costing | `src/concilium/application/skills/manifests/05-equipes-e-alocacao/skill.py` |
| Domain models | `src/concilium/domain/models/canonical.py` |
| Override storage | `projetos/{uuid}/overrides/` |
| UI planning tab | `presentation/ui/organisms/layout.py` — `render_planning_tab()` |
| UI team editor | `presentation/ui/molecules/components.py` — `render_team_editor()` |

---

## 3. Current Activity/Scope Modeling

### 3.1 EapItem and Atividade

```python
class EapItem:
    item_id: str
    cpu_id: str
    quantitativo: float          # Q — delivery target
    unidade: str

class Atividade:
    atividade_id: str
    eap_item_id: str
    fracao_quantitativo: float   # Fraction of Q allocated to this activity
    quantitativo_atividade: float
    cpu_id: str
    # ← No scheduling policy. No mobilization model. No derived duration.
```

**Finding:** Activities are pure quantity declarations. They carry no execution intent beyond `cpu_id` and `quantitativo`. All scheduling information lives in Skill 04's inputs or the RCPSP spec.

### 3.2 How Duration Is Set Today

Duration flows through three paths, none of which derive it from Q, P, n:

1. **MANUAL mode:** No duration concept. Allocation is given week-by-week. Duration = span from first to last active week in `num_equipes_por_item`.

2. **AUTO (RCPSP) mode:** `rcpsp_spec["activities"][i]["duration_weeks"]` is explicitly provided in `referencia.json`. It is a **pre-computed constant**, not derived during the run.

3. **AUTO (Legacy) mode:** `canonical.atividades[i].duration_weeks` — set by Skill 01 from the benchmark reference. Also a pre-computed constant.

**Conclusion:** Duration is always an exogenous input. The formula `T = ceil(Q / (P × n × m × h))` — which every planning engineer knows — is computed nowhere in the pipeline.

---

## 4. Existing Scheduling and Productivity Assumptions

### 4.1 Fixed-Duration Assumption

**The RCPSP solver receives `duration_weeks` as a hard constraint.** SGS heuristics schedule activities with this duration and cannot extend it. If an activity genuinely needs more weeks (because praticabilidade reduces effective production), this is invisible to the solver — the schedule silently under-delivers.

Evidence: `_convert_schedule_to_distribuicao()` distributes Q uniformly over the pre-set duration. If `p_i < 1` in some weeks, `qtd_executada` is reduced, but `duration_weeks` is not extended. The quantity deficit accumulates silently.

### 4.2 Fixed Team Allocation Assumption

**The manual mode takes `{week_key: n}` literally.** There is no concept of mobilization rate, ramp-up, plateau, or demobilization. If a planner wants to start with 2 teams and grow to 5, they must manually fill every week's value.

**The RCPSP mode assigns `required_resources: {tipo: n}` per activity — a uniform demand** throughout the activity's duration. No resource curve is modeled.

### 4.3 Weekly Granularity Is Hardcoded Throughout

- `distribuicao_semanal: dict[str, DistribuicaoSemanal]` — ISO week keys
- `prat_semanal: dict[str, float]` — efficiency by ISO week
- `indiretos_semanal` — weekly overhead
- `render_team_editor()` in UI expects and produces weekly maps

**Changing granularity would require changes across domain, skills, persistence, and UI.**

### 4.4 Production Formula (Shared Invariant)

The formula is consistent across MANUAL and AUTO modes:

```
qtd_executada(t) = P × m × h × p(t) × n(t)
```

Where:
- `P` = productivity (units/hour), from CPU → producao_id_ref → valor_horario
- `m` = days/week (regime: typically 6)
- `h` = hours/day (regime: typically 8)
- `p(t)` = practicability factor for week t (from `praticabilidade.percentual_produtivo_semanal`)
- `n(t)` = number of active teams in week t

**This formula is the correct extension point for a mobilization policy.** A policy defines `n(t)` as a function rather than a lookup table.

### 4.5 Post-Hoc Pool Checking

Resource pool violations are detected after scheduling, not during. The RCPSP solver does respect pool constraints during optimization, but in MANUAL mode, any allocation is accepted — violations surface only as `VAL-POOL-01` warnings.

### 4.6 Climate/Praticabilidade Is Applied Locally

Efficiency `p(t)` reduces `qtd_executada` without extending the schedule. Under the current model:
- If `p_i = 0.7` for weeks 3–5, production is 30% lower those weeks
- But `duration_weeks` is not extended to compensate
- The activity under-delivers its Q target — silently

**This is a latent bug in the current model that the WMP must correct.**

---

## 5. Architectural Analysis — Fitness for WMP

### 5.1 Does the Architecture Support Derived Temporal Simulation?

**No.** There is no function `derive_duration(Q, P, n_policy, p_weekly, regime) → T` anywhere in the codebase. The data flow is unidirectional and inverted: duration is input, not output.

To support WMP, we need to introduce a simulation step that iterates weeks forward, accumulates production under `n(t)` and `p(t)`, and terminates when `Σ qtd_executada ≥ Q`.

### 5.2 Does It Assume Fixed-Duration Activities?

**Yes, structurally.** Both RCPSP and legacy AUTO modes receive `duration_weeks` as hard input. The RCPSP solver's `Activity.duration_weeks: int` is not nullable. Any WMP implementation must either:
- Pre-compute derived duration and feed it to the existing RCPSP, or
- Bypass the RCPSP duration constraint entirely for WMP-driven activities

**Recommendation:** Pre-compute. Introduce a `WorkforcePolicySimulator` that converts `(policy, Q, P, p_weekly) → duration_weeks + weekly_curve`, then the existing RCPSP ingests the result.

### 5.3 Does It Assume Fixed Team Allocation?

**Yes, in both modes.** MANUAL mode assumes constant allocation per week (planner-provided). RCPSP assumes constant `required_resources` throughout activity duration.

The domain model (`ScheduledActivityCanonical`) already stores `distribuicao_semanal: dict[str, DistribuicaoSemanal]` with per-week `num_equipes` — this is the right output container for variable curves. No domain schema change needed for output.

The input schema change is significant: `num_equipes_por_item` (a map) must be complemented by a `mobilization_policy_por_item` (a declarative object).

### 5.4 Does It Tightly Couple UI to Weekly Planning?

**Yes.** `render_team_editor()` renders a data editor where rows are activities and the only editable column is `num_equipes_maximo`. The state model (`build_team_adjustment_rows`) constructs rows from the `cronograma.atividades` reference. The save action (`build_num_equipes_override`) produces a flat `{week_key: n}` map.

**This coupling is surface-level and correctable.** The UI needs to shift from "edit weekly allocation" to "edit mobilization policy parameters." The underlying data_editor paradigm (tabular, per-activity rows) is preserved; only the columns change.

### 5.5 Hidden Assumptions Conflicting with WMP

| Assumption | Location | Conflict |
|-----------|----------|----------|
| `duration_weeks` is always a pre-computed integer | Skill 04, RCPSP, Skill 01 | WMP duration is derived, potentially fractional (ceil) |
| `num_equipes` is constant per week (or given explicitly) | RCPSP `required_resources`, manual mode | WMP generates a curve `n(t)` |
| Under-delivery is silent | Skill 04 MANUAL mode | WMP must guarantee Q delivery by construction |
| Pool violations are post-hoc | Skill 04 `_check_pool_violations()` | WMP must enforce `n(t) ≤ n_max ≤ pool` proactively |
| Efficiency `p(t)` reduces production but not duration | All modes | WMP must integrate `p(t)` into duration derivation |
| Activity cost = fixed_monthly × permanencia | Skill 05 | With variable n(t), monthly cost must integrate over curve, not multiply a constant |
| UI produces `{week: n}` as the canonical override | `build_num_equipes_override()` | WMP produces a policy object, not a weekly map (map is derived artifact) |

---

## 6. Feasibility Assessment

**WMP is feasible without breaking the existing pipeline.** The approach is additive:

1. Introduce a new domain object `MobilizacaoPolicy` on `Atividade`
2. Introduce a new service `WorkforcePolicySimulator` that derives `(duration_weeks, weekly_curve)` from a policy
3. Wire the simulator output into the existing Skill 04 MANUAL mode path (which already knows how to handle a `{week_key: n}` map)
4. Update Skill 05 to integrate costs over the curve rather than assuming constant n
5. Update the UI to expose policy parameters instead of (or alongside) the existing team editor
6. Persist policy as a new override dimension separate from `num_equipes_por_item`

**The existing RCPSP path remains untouched for projects that do not use WMP.** The simulator output can be expressed as a `num_equipes_por_item` map, which Skill 04 already consumes. The RCPSP can also receive derived `duration_weeks` as it does today.

**Estimated complexity:** Medium-High. Domain and simulation are straightforward. The cost model in Skill 05 requires careful adjustment (integral over variable-n curve). UI is low complexity.

---

## 7. Required Domain Model Changes

### 7.1 New Domain Object: `MobilizacaoPolicy`

```python
@dataclass(frozen=True)
class MobilizacaoPolicy:
    """Declarative workforce mobilization policy for a compositional activity."""

    n_inicial: int          # Teams at week 0 of activity (n_0 ≥ 1)
    n_maximo: int           # Peak teams (n_max ≥ n_inicial)
    taxa_mobilizacao: float # Teams added per week during ramp-up (c_mob > 0)
    taxa_desmobilizacao: float = 0.0  # Teams removed per week during wind-down (c_desmob ≥ 0)

    # Optional: explicit plateau duration before demobilization begins
    # None = demobilize only after Q delivered
    semanas_plateau: int | None = None

    # Future extension points (not yet active):
    # decay_eficiencia: Callable[[int], float] | None = None   # Learning curve / fatigue
    # stochastic_seed: int | None = None                       # Reproducible stochastic runs

    def __post_init__(self) -> None:
        if self.n_inicial < 1:
            raise ValueError("n_inicial must be ≥ 1")
        if self.n_maximo < self.n_inicial:
            raise ValueError("n_maximo must be ≥ n_inicial")
        if self.taxa_mobilizacao <= 0:
            raise ValueError("taxa_mobilizacao must be > 0")
        if self.taxa_desmobilizacao < 0:
            raise ValueError("taxa_desmobilizacao must be ≥ 0")
```

**Design rationale — frozen dataclass:** Policies are value objects. They should be immutable once defined and reproducible. Simulation is a pure function of policy + inputs.

### 7.2 Extension to `Atividade`

```python
class Atividade(BaseModel):
    atividade_id: str
    eap_item_id: str
    fracao_quantitativo: float
    quantitativo_atividade: float
    cpu_id: str
    # NEW:
    mobilizacao_policy: MobilizacaoPolicy | None = None
```

**Backward compatible:** `None` means "use existing mechanism" (explicit allocation or RCPSP).

### 7.3 New Domain Object: `CurvaForca`

The simulator outputs a curve — an ordered sequence of weekly team counts with projected production:

```python
@dataclass(frozen=True)
class CurvaForcaSemanal:
    semana_offset: int       # 0-indexed week within activity
    num_equipes: int
    eficiencia: float        # p(t) for this week
    qtd_executada: float     # P × m × h × p(t) × n(t)
    qtd_acumulada: float

@dataclass(frozen=True)
class CurvaForca:
    policy: MobilizacaoPolicy
    atividade_id: str
    quantitativo_alvo: float  # Q
    producao_horaria: float   # P
    regime: tuple[int, int]   # (dias_semana, horas_dia)
    semanas: list[CurvaForcaSemanal]  # Derived — len = T (duration in weeks)

    @property
    def duration_weeks(self) -> int:
        return len(self.semanas)

    @property
    def delivered(self) -> float:
        return self.semanas[-1].qtd_acumulada if self.semanas else 0.0

    @property
    def is_complete(self) -> bool:
        return self.delivered >= self.quantitativo_alvo
```

**This is a pure value object — no mutation after creation.** The simulator returns it; Skill 04 reads it.

### 7.4 New Service: `WorkforcePolicySimulator`

```python
class WorkforcePolicySimulator:
    """
    Derives execution horizon and weekly team curve from a mobilization policy.

    Assumptions (must be documented in each simulation call):
    - Weekly granularity
    - Production formula: qtd(t) = P × m × h × p(t) × n(t)
    - n(t) = min(n_0 + floor(t × c_mob), n_max) during mobilization
    - n(t) = n_max during plateau (if semanas_plateau given)
    - n(t) = max(n_max - floor(j × c_desmob), 0) during demobilization
    - Demobilization begins only AFTER Q delivered, unless plateau forces it
    - p(t) = 1.0 if praticabilidade not provided for week t
    - Partial production in final week: activity completes mid-week
    - Maximum guard: max_weeks = 10 × ceil(Q / (P × m × h)) to prevent infinite loop
    """

    MAX_MULTIPLIER: ClassVar[int] = 10  # Guard against infinite loops

    def simulate(
        self,
        policy: MobilizacaoPolicy,
        quantitativo: float,                  # Q
        producao_horaria: float,              # P (units/hour)
        regime: RegimeTrabalho,               # (dias_semana, horas_dia)
        prat_semanal: dict[str, float],       # {ISO_week: float}, applied by offset
        semana_inicio: str | None = None,     # "2026-W23" — anchor for prat lookup
    ) -> CurvaForca:
        """
        Core simulation loop. Terminates when:
        - Cumulative production ≥ Q (success), or
        - max_weeks exceeded (failure — returns incomplete curve)

        All parameters are explicit. No global state accessed.
        """
        ...
```

**Key design decisions:**
- Pure function of its arguments — no side effects, no database access
- `prat_semanal` is passed in, not looked up internally
- Returns complete `CurvaForca`; caller decides what to do with an incomplete one
- `max_weeks` guard prevents infinite loop for zero-productivity edge cases
- `semana_inicio` anchors the praticabilidade lookup to calendar weeks

---

## 8. Required Persistence/Schema Changes

### 8.1 New Override Dimension: `mobilizacao_policy_override.json`

```json
{
  "version": "1.0",
  "items": {
    "eap-1_0": {
      "n_inicial": 2,
      "n_maximo": 5,
      "taxa_mobilizacao": 1.0,
      "taxa_desmobilizacao": 0.0,
      "semanas_plateau": null
    },
    "eap-2_0": {
      "n_inicial": 1,
      "n_maximo": 3,
      "taxa_mobilizacao": 0.5,
      "taxa_desmobilizacao": 1.0,
      "semanas_plateau": 4
    }
  }
}
```

**Location:** `projetos/{uuid}/overrides/mobilizacao_policy_override.json`

**Not merged into `prototype_overrides.json`** — kept as a distinct file to allow independent versioning and rollback. This is consistent with `cpus_override.json`, `bdi_override.json` existing as separate files.

### 8.2 Canonical: New Field `curvas_forca`

The derived curves become a canonical artifact — reproducible from the policy + inputs, but cached for audit and downstream consumption:

```python
class CanonicalModel(BaseModel):
    # ... existing fields ...
    # NEW (optional):
    curvas_forca: list[CurvaForca] | None = None
```

**Why persist derived data?** Because:
1. Downstream skills (05, 06) need the curves to compute costs
2. Audit trail — planners need to see what curve was used in a given run
3. Report generation uses curve data

**The curve is still deterministically re-derivable** from policy + canonical inputs. Persistence is a cache, not the source of truth.

### 8.3 `ScheduledActivityCanonical` — No Schema Change Required

The existing `distribuicao_semanal: dict[str, DistribuicaoSemanal]` already accommodates variable `num_equipes` per week. The WMP simulator output maps cleanly to this structure.

### 8.4 Deliverables Configuration

New file: `projetos/{uuid}/deliverables_config.json`

```json
{
  "version": "1.0",
  "outputs": {
    "cronograma_xlsx": true,
    "curva_forca_histogram": true,
    "curva_producao_cumulativa": true,
    "relatorio_produtividade": true,
    "projecao_custo": true,
    "memoria_calculo": false,
    "relatorio_md": true
  }
}
```

**This replaces hardcoded output generation in the pipeline.** Each output has a registered `OutputGenerator` implementation. The pipeline consults `deliverables_config` and invokes only enabled generators.

---

## 9. Required API Contract Changes

### 9.1 `RunProjectRequest` Extension

```python
class RunProjectRequest(BaseModel):
    base_version: str | None = None
    fork_version: bool = False
    skill_inputs_override: dict[str, dict[str, Any]] = Field(default_factory=dict)
    use_saved_overrides: bool = True
    # NEW:
    use_mobilizacao_policy: bool = True  # Default: use saved WMP if present
```

**The existing `skill_inputs_override["04-cronograma"]["num_equipes_por_item"]` continues to work** as an explicit override that bypasses WMP. Priority chain:

```
1. skill_inputs_override["04-cronograma"]["num_equipes_por_item"]  ← highest priority (explicit)
2. Derived from mobilizacao_policy_override.json via simulator         ← WMP (new)
3. rcpsp_spec                                                          ← RCPSP
4. Legacy canonical.atividades + activity_dag                          ← lowest priority
```

### 9.2 New Endpoints

```
GET  /api/projects/{id}/mobilizacao-policies
     → {items: {item_id: MobilizacaoPolicy}}

POST /api/projects/{id}/mobilizacao-policies
     Body: {item_id: str, policy: MobilizacaoPolicy}
     → {status: "ok", item_id: str}

DELETE /api/projects/{id}/mobilizacao-policies/{item_id}
     → {status: "ok"}

POST /api/projects/{id}/mobilizacao-policies/simulate
     Body: {item_id: str, policy: MobilizacaoPolicy}
     → CurvaForca  ← preview without committing to persistence
```

The **simulate endpoint is stateless** — it runs the simulator and returns the curve without saving. This supports UI preview before the planner commits.

### 9.3 Deliverables Configuration Endpoint

```
GET  /api/projects/{id}/deliverables-config
     → {outputs: {output_id: bool}}

PUT  /api/projects/{id}/deliverables-config
     Body: {outputs: {output_id: bool}}
     → {status: "ok"}
```

---

## 10. Required UI/ViewModel/State Changes

### 10.1 Replace `render_team_editor` with `render_mobilizacao_policy_editor`

**Current:** data_editor with columns (item_id, descricao, cpu_id, Base, ✏️ Máx. equipes, Sem. início, Sem. fim, Duração)

**Target:** data_editor with columns:
- item_id, descricao, cpu_id (readonly — same)
- ✏️ Inicial (n_0), ✏️ Máximo (n_max), ✏️ Mob./semana (c_mob), ✏️ Desmob./semana (c_desmob)
- Duração est. (derived — readonly, computed server-side from simulate endpoint or local approximation)

**Progressive disclosure:** A compact row-per-activity table for the main policy parameters. An "Avançado" expander per activity for plateau configuration.

### 10.2 Curve Preview Panel

After editing a policy row, the planner can click "Visualizar curva" to call the `/simulate` endpoint and render:
- A bar chart: `num_equipes` per week
- A line chart: `qtd_acumulada` vs. week (with Q target as horizontal reference)
- Metrics: duration_weeks (derived), peak_teams, total_team_weeks

**This is progressive disclosure** — planners who just want to set "5 teams, ramp 1/week" don't need to see the chart.

### 10.3 State Management

New session state keys:
- `f"mobilizacao-policy-{project_id}"` — dict of `{item_id: MobilizacaoPolicy}` (in-memory edits before save)
- `f"mobilizacao-preview-{project_id}-{item_id}"` — cached `CurvaForca` for last simulated item

**Policy loading:** When the tab opens, load saved policies from `GET /mobilizacao-policies`. Use as `data_editor` initial values.

### 10.4 Deliverables Configuration Panel

New section at the bottom of the Planejamento tab:

```
📦 Saídas do Planejamento
[x] Cronograma XLSX
[x] Curva de força (histograma)
[x] Curva de produção acumulada
[ ] Memória de cálculo (detalhada)
[x] Relatório executivo (MD)
...
```

Backed by `GET/PUT /deliverables-config`. Changes take effect on next run.

---

## 11. Backward Compatibility Considerations

### 11.1 Projects Without WMP

Projects that do not have `mobilizacao_policy_override.json` continue to use the existing `num_equipes_por_item` mechanism unchanged. No existing project is broken.

### 11.2 `num_equipes_por_item` as Explicit Override

When a planner provides `num_equipes_por_item` directly (via the existing API or the old UI), it takes priority over any WMP. This allows escape hatch for edge cases.

### 11.3 RCPSP Compatibility

The simulator output (`CurvaForca.duration_weeks`) can be fed into RCPSP's `duration_weeks`. The RCPSP path remains valid for projects using it. WMP and RCPSP are complementary: WMP derives duration per activity, RCPSP resolves sequencing given those durations.

### 11.4 Skill 05 Cost Model

The existing cost formula in Skill 05 uses `sum(d.num_equipes for d in distribuicao_semanal.values())` to compute total team-weeks. This remains correct — `distribuicao_semanal` will now have variable `num_equipes` from the WMP curve. No formula change needed; the data shape is unchanged.

**One caveat:** The monthly cost normalization in Skill 05 assumes all weeks use the same `num_equipes`. Under WMP, team counts vary. The cost must be integrated over the actual curve:

```python
# Current (incorrect under WMP):
custo_total = fixo_semanal * n_const * duration_weeks + combustivel_semanal * ...

# Required (correct):
custo_total = Σ_t [(custo_MO + custo_EQ) / 4.348 + (custo_COMB / 4.348) × p(t)] × n(t)
```

This change is required and **not backward-breaking** — for constant `n(t)`, the integral yields the same result as the current formula.

---

## 12. Migration Strategy

### Phase 0 — Foundation (No user-facing change)

1. Add `WorkforcePolicySimulator` as a pure domain service with full test coverage
2. Add `MobilizacaoPolicy`, `CurvaForca`, `CurvaForcaSemanal` as frozen dataclasses
3. Add simulate endpoint (`POST /mobilizacao-policies/simulate`)
4. Add `CurvaForca` to `CanonicalModel` as optional field
5. Update Skill 05 cost integral (backward-compatible — same result for constant n)

**Deliverable:** Simulator tested and accessible via API. No UI change.

### Phase 1 — Policy Persistence

1. Add `mobilizacao_policy_override.json` storage
2. Add `GET/POST/DELETE /mobilizacao-policies` endpoints
3. Wire Skill 04 to read policy file and invoke simulator when `num_equipes_por_item` is absent
4. Add `deliverables_config.json` and endpoints

**Deliverable:** WMP works end-to-end for API clients. Existing UI unchanged.

### Phase 2 — UI Integration

1. Replace `render_team_editor` with `render_mobilizacao_policy_editor`
2. Add curve preview panel
3. Add deliverables configuration panel
4. Update `build_num_equipes_override` to produce policy objects instead of weekly maps
5. Deprecate `render_saved_override` (already partially removed from HOT template)

**Deliverable:** Planners use WMP in the UI. Old weekly allocation is legacy path only.

### Phase 3 — Validation and Hardening

1. Add `VAL-WMP-01`: Policy results in n(t) > n_max for some t — impossible
2. Add `VAL-WMP-02`: Simulator exceeds MAX_MULTIPLIER — under-productive
3. Add `VAL-WMP-03`: Demobilization begins before Q delivered without explicit plateau
4. Add `VAL-WMP-04`: n_max exceeds resource pool for any activity's CPU type
5. Bridge Analysis (ADR-039) updated to use WMP curve for quantization factor

**Deliverable:** Production-ready. All edge cases covered.

---

## 13. Risks and Trade-offs

### R1 — Simulator-RCPSP Impedance Mismatch (HIGH)

**Risk:** WMP computes duration independently per activity. RCPSP optimizes start times given these durations. If WMP changes `n(t)` mid-activity (ramp-up), the RCPSP's fixed-resource-demand assumption is violated — it cannot model variable demand per week.

**Mitigation:** Use the WMP simulator output to populate `num_equipes_por_item` (explicit weekly map) and bypass the RCPSP for WMP-driven activities. RCPSP remains valid for activities without WMP. Accept that WMP activities are scheduled in MANUAL mode with derived allocations.

**Trade-off:** Loses RCPSP's global resource optimization for WMP activities. Gains determinism and planner intent fidelity.

### R2 — Praticabilidade Data Availability (MEDIUM)

**Risk:** `p(t)` varies by week. The simulator needs weekly praticabilidade anchored to calendar. If the planner hasn't specified a start date for an activity, the simulator cannot map offset-t to a calendar week.

**Mitigation:** Simulator accepts `semana_inicio` as optional parameter. If absent, assumes `p(t) = 1.0` for all weeks and warns. The simulation remains valid as an upper-bound estimate.

**Alternative:** Simulate with monthly averages when weekly data is unavailable.

### R3 — Cost Model Discontinuity (MEDIUM)

**Risk:** Skill 05's current integral is `Σ_t (fixo_semanal + comb_semanal × p(t)) × n(t)`. Under WMP, `n(t)` varies. If any downstream skill or report assumes constant `n` for cost amortization, results will be incorrect.

**Mitigation:** Full audit of Skill 05 and 06 before Phase 1 deployment. Update integration test to use variable-n scenarios.

### R4 — Planner Cognitive Load (LOW-MEDIUM)

**Risk:** Four policy parameters (n_0, n_max, c_mob, c_desmob) may confuse planners accustomed to specifying teams directly.

**Mitigation:** Defaults: `n_inicial = 1`, `c_mob = 1.0`, `taxa_desmobilizacao = 0.0`, `n_maximo = current max_equipes value`. The most common case ("just set max teams") requires editing only `n_maximo`. Advanced parameters are collapsed by default (progressive disclosure).

### R5 — Partial Final Week Semantics (LOW)

**Risk:** The simulator terminates when `qtd_acumulada ≥ Q`. The final week may only partially execute (activity finishes mid-week). Duration in weeks is `ceil(...)` by construction. But cost computation treats the final week as a full week.

**Mitigation:** Introduce `fracao_semana_final` in `CurvaForcaSemanal` for the last entry. Cost model uses this fraction. Report generation shows actual delivery date within the final week.

### R6 — Serialization of Frozen Dataclasses (LOW)

**Risk:** `MobilizacaoPolicy` and `CurvaForca` are frozen dataclasses. Pydantic models and JSON serialization require explicit adapters.

**Mitigation:** Add `to_dict()` / `from_dict()` class methods. Register Pydantic validators. Keep the core types as pure Python dataclasses (not Pydantic BaseModel) to preserve immutability semantics.

---

## 14. Recommendations for Incremental Rollout

1. **Start with the simulator in isolation.** The `WorkforcePolicySimulator` is a pure function with no dependencies on the existing pipeline. Write it, test it exhaustively, and expose it via the simulate endpoint. Validate with planners before touching any existing skill.

2. **Do not change Skill 04 until the simulator is validated.** Any modification to the scheduling skill risks breaking existing projects. Phase 0 must be complete and stable before Phase 1.

3. **Use feature flag `use_mobilizacao_policy: bool` in `RunProjectRequest`.** Default to `True` only when a policy file exists. Projects without the file are unaffected.

4. **Audit Skill 05 before Phase 1.** The cost integral change is subtle. An integration test with a known scenario (variable n curve, known P, known p_t) must pass before any Phase 1 deployment.

5. **Deprecate `num_equipes_por_item` in the UI, not in the API.** The API must continue accepting explicit weekly maps indefinitely for programmatic clients and automation.

6. **The deliverables configuration is independent of WMP.** It can be shipped in Phase 1 regardless of WMP readiness. No risk coupling.

---

## 15. Open Questions and Architectural Uncertainties

### Q1 — Precedence Under WMP

When two activities are predecessor-constrained and both use WMP, the successor's start date affects its `p(t)` lookup. Should the simulator be invoked before or after RCPSP sequencing?

**Implication:** If before, the curves are correct for calendar weeks but RCPSP may shift start dates, invalidating the `p(t)` mapping. If after, we need a simulator re-run post-RCPSP.

**Proposed resolution:** Two-pass. Pass 1: simulate with `p(t) = 1.0` to derive nominal durations. Pass 2: RCPSP sequences activities. Pass 3: re-simulate with actual calendar `p(t)` from assigned start weeks. This adds complexity but preserves correctness.

### Q2 — WMP and Congestion Effects

The current formula assumes linear scaling: doubling teams doubles production. Real sites have congestion when too many teams share a work front. The `MobilizacaoPolicy` design has a comment placeholder for future `decay_eficiencia`. How should this be modeled without breaking the current formula?

**Proposed resolution:** Introduce an optional `produtividade_efetiva(n, t)` callable in the simulator, defaulting to `lambda n, t: P` (no congestion). The formula becomes `qtd(t) = produtividade_efetiva(n(t), t) × m × h × p(t)`. No current behavior is changed; the extension point is explicit.

### Q3 — Multi-Activity EAP Items

An EAP item can have multiple `Atividade` records (via `fracao_quantitativo`). Each activity has its own `cpu_id` and potentially its own WMP. How do constraints propagate between activities of the same EAP item?

**Implication:** If activity A (60% of Q) finishes early, does activity B (40% of Q) start earlier? The current model treats them as independent. WMP must clarify.

**Proposed resolution:** Each `Atividade` has an independent WMP. Sequencing between activities of the same EAP item is expressed in the DAG. WMP operates per-activity, not per-EAP-item.

### Q4 — Deliverables as Plugin vs. Configuration

The specification calls for "plugin-oriented output generation." Should deliverables be:
(a) Feature-flagged (a config object enables/disables registered generators), or
(b) True plugins (dynamically loaded generators at runtime)?

**Proposed resolution:** Option (a) for now. Registered generators are statically known; configuration only controls which execute. Option (b) is a future concern and would require a plugin registry and interface contract not yet designed.

### Q5 — Simulator Determinism Under Stochastic Productivity

The spec mentions "stochastic productivity" as a future extension. A stochastic simulator is not deterministic — it requires multiple runs or sampling. The current design assumes determinism (frozen dataclass = reproducible). How should stochastic scenarios coexist with the audit trail?

**Proposed resolution:** Stochastic runs are a separate execution mode, not a default. Deterministic simulation remains the canonical path. Stochastic results are stored as distribution summaries, not as the canonical schedule.

---

## 16. Decision

**Approved approach:** Implement the Workforce Mobilization Policy system in three phases as described in §12, using the `WorkforcePolicySimulator` as a pure domain service that produces `CurvaForca`, wired into Skill 04's MANUAL mode path via a derived `num_equipes_por_item` map.

**Rejected alternatives:**

- **Extend RCPSP to handle variable resource demand:** Too invasive. The RCPSP solver is complex and well-tested; adding time-varying resource profiles would require reformulating the MILP and all heuristics. Risk too high relative to benefit.

- **Replace Skill 04 entirely:** Would break all existing projects and require migration of every existing canonical.json. Not justified.

- **Compute duration in Skill 01 (escopo-e-eap):** Would require Skill 01 to know productivity and climate data, violating separation of concerns (Skill 01 is a scope skill, not a scheduling skill).

---

## 17. Consequences

**Positive:**
- Duration becomes derived, not manually set — eliminates the #1 source of planning errors
- Planner intent is explicitly captured in a declarative object (auditable, versionable)
- Praticabilidade is integrated into duration derivation, not just quantity reduction
- Future extensions (learning curves, congestion, stochastic) have clean extension points
- Deliverables are configurable, not hardcoded

**Negative:**
- Phase 0 adds new domain objects that planners don't yet interact with — requires testing without UI feedback
- The two-pass simulator (Q15 resolution) adds latency to pipeline execution
- Skill 05 cost integral change, while backward-compatible, requires careful testing
- `num_equipes_por_item` and WMP coexist during transition — priority chain adds cognitive overhead for API clients

**Neutral:**
- Existing projects are unaffected (backward-compatible at every layer)
- The RCPSP solver and its fallback chain remain unchanged
