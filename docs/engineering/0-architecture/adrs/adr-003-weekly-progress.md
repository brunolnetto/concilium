# ADR-003: Weekly Progress Tracking & Efficiency Model

**Status:** IMPLEMENTED  
**Date Decided:** 2026-04-29  
**Date Implemented:** 2026-04-29  
**Implementers:** progress/models.py, progress/tracker.py, SkillResult  
**Context:** Skill 02 generates a weekly schedule (`Cronograma`) with planned quantities per ISO week (`DistribuicaoSemanal`). Once the project is under execution, each week's **actual** progress must be recorded and compared against the plan to:

1. Detect early completions and cascading delays
2. Update the project's `pct_completude` per activity
3. Compute a **Schedule Performance Index (SPI)** for trend analysis
4. Feed deviation signals into the replanning trigger layer (ADR-005)

### Core Tension

Progress tracking must be:

- **Simple to record** (foremen report quantities, not abstractions)
- **Auditable** (immutable updates, never overwrite)
- **Actionable** (produces SPI + forecast, not just raw data)
- **Aligned with the efficiency model** already used in Skill 02

### Efficiency Model (Context)

Skill 02 computes planned weekly quantity as:

```
qtd_planejada_semana = producao_horaria × horas_dia × dias_semana × num_equipes × eficiencia_semana
```

Where `eficiencia_semana` comes from `Praticabilidade.percentual_produtivo` (weather/rain reduction factor).

The same model applies to **actual** progress: if the foreman reports that fewer productive hours occurred (rain, access issues), `efficiency_observed` captures this.

---

## Decision

We adopt an **immutable append-only progress update model** with a `ProgressTracker` service that computes SPI and forecasts completion.

---

## Data Model

### `ProgressUpdate` — Atomic weekly record

```python
class ProgressUpdate(BaseModel):
    activity_id: str
    week_key: str              # ISO format "AAAA-Www" (e.g. "2026-W23")
    quantidade_realizada: float  # Actual quantity completed this week (same unit as EAP)
    efficiency_observed: float   # Fraction of productive time (0-1)
    recorded_by: str           # Engineer/foreman ID
    recorded_at: datetime      # Submission timestamp (UTC)
    notes: str | None = None
```

**Invariants:**
- `week_key` must be a valid ISO week string
- `quantidade_realizada >= 0`
- `efficiency_observed` in [0.0, 1.0]
- Once persisted, a `ProgressUpdate` is **never modified** — corrections are new records

---

### `ActivityProgress` — Derived state per activity

```python
class ActivityProgress(BaseModel):
    activity_id: str
    quantidade_planejada_total: float   # From EAP item
    quantidade_realizada_total: float   # Sum of all updates
    pct_completude: float               # realizada / planejada (0-1)
    delay_weeks: float                  # positive = behind, negative = ahead
    updates: list[ProgressUpdate]       # Chronological history
```

`delay_weeks` is computed by comparing `pct_completude` against the expected completion fraction at the current week according to the planned schedule.

---

### `WeeklyProgressReport` — Project-wide snapshot

```python
class WeeklyProgressReport(BaseModel):
    project_id: str
    week_key: str
    activities: list[ActivityProgress]
    spi: float                      # Schedule Performance Index = Σ(earned_value) / Σ(planned_value)
    forecast_completion_week: int   # Estimated project end week (linear extrapolation)
    drift_alerts: list[str]         # Human-readable warnings (e.g. "EXCAV-01 is 1.5 weeks behind")
```

---

## ProgressTracker — Service Layer

```python
class ProgressTracker:
    def record_update(
        self,
        canonical: CanonicalModel,
        update: ProgressUpdate,
    ) -> SkillResult:
        """
        Append progress update to canonical.progresso[activity_id].
        Re-compute ActivityProgress and WeeklyProgressReport.
        Emit VAL-PROG-XX validations on anomalies.
        """

    def compute_spi(
        self,
        canonical: CanonicalModel,
        week_key: str,
    ) -> float:
        """
        SPI = Σ earned_value_week / Σ planned_value_week
        earned_value_week = (qty_realizada / qty_planejada_total) × peso_atividade
        Values < 1.0 indicate schedule lag.
        """

    def forecast_completion(
        self,
        canonical: CanonicalModel,
        current_week: int,
    ) -> int:
        """
        Linear forecast: remaining_qty / avg_weekly_rate → remaining weeks.
        Returns week number of projected completion.
        """

    def detect_drift(
        self,
        canonical: CanonicalModel,
        week_key: str,
    ) -> list[str]:
        """
        Return list of alert strings for activities exceeding drift thresholds.
        Thresholds: delay_weeks >= 1 → T2-DELAY trigger candidate.
        """
```

---

## Integration with CanonicalModel

```python
# Added to CanonicalModel:
progresso: dict[str, list[ProgressUpdate]] = Field(default_factory=dict)
# Keyed by activity_id; each value is append-only list of ProgressUpdate
```

---

## Validation Codes

| Code | Condition | Status |
|------|-----------|--------|
| **VAL-PROG-01** | `quantidade_realizada > qtd_planejada_semana × 1.5` | AVISO — over-reporting suspected |
| **VAL-PROG-02** | `efficiency_observed < 0.3` for 2+ consecutive weeks | AVISO — sustained low efficiency, investigate |
| **VAL-PROG-03** | `pct_completude > 1.0` | ERRO — reported more than total planned |
| **VAL-PROG-04** | Duplicate `(activity_id, week_key)` | AVISO — possible double entry |

---

## SPI Interpretation

| SPI Range | Interpretation | Action |
|-----------|---------------|--------|
| `> 1.05` | Ahead of schedule | Offer Tier 1 acceleration (ADR-005) |
| `0.95 – 1.05` | On track | Monitor |
| `0.80 – 0.95` | Slightly behind | Tier 2 trigger if sustained ≥ 2 weeks |
| `< 0.80` | Significantly behind | Immediate Tier 2/3 replan trigger |

---

## Relationship to Replanning (ADR-005)

`ProgressTracker.detect_drift()` is the primary input to `ReplannTriggerDetector`:

```
ProgressUpdate (recorded weekly)
  ↓
ProgressTracker.record_update()
  ↓
ActivityProgress.delay_weeks computed
  ↓
WeeklyProgressReport.drift_alerts populated
  ↓
ReplannTriggerDetector.check_triggers() (ADR-005)
  ↓
Tier 1/2/3 replan candidates generated
```

---

## Consequences

### Positive

- Clear audit trail: every reported quantity is traceable to week, person, timestamp
- SPI gives a single number for project health
- Forecast completion enables early warning before deadline is missed
- Immutable model prevents silent overwrite of progress data

### Negative

- Requires weekly discipline from field engineers
- Linear SPI forecast is a simplification (doesn't account for non-linear resource plans)
- `delay_weeks` calculation depends on schedule accuracy from ADR-004

---

## Definition of Done

- [x] `ProgressUpdate` model in `progress/models.py`
- [x] `ActivityProgress` model derived from updates
- [x] `WeeklyProgressReport` model
- [x] `ProgressTracker.record_update()` with immutable append semantics
- [x] `ProgressTracker.compute_spi()` with earned-value formula
- [x] `ProgressTracker.forecast_completion()` via linear extrapolation
- [x] `ProgressTracker.detect_drift()` returning alert strings
- [x] VAL-PROG-01 to 04 validations
- [x] `progresso` field added to `CanonicalModel`
- [x] Integration with ADR-005 trigger detection documented
- [ ] Dashboard / CLI: `concilium progress report --project <id> --week <week>`
