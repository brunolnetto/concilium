# ADR-002: Resolution & Matching Strategy

**Status:** IMPLEMENTED  
**Date Decided:** 2026-04-29  
**Date Implemented:** 2026-04-29  
**Implementers:** skills/02-resolver-cpus, models/resolution_decision.py  
**Context:** We must resolve **client-side scope items (unstructured / semi-structured)** into:

* Catalog **CPU (Composição de Preço Unitário)**
* Associated **productivity references**
* Inputs required for **planning (WorkPackages)**

This resolution sits between:

* **Translation Layer** (semantic interpretation)
* **Planning Layer** (deterministic scheduling and allocation)

### Core tension

We have two competing forces:

1. **Determinism (auditability, reproducibility)**
2. **Flexibility (real-world messy inputs)**

Naively choosing one breaks the system:

* Fully deterministic → brittle, high manual effort
* Fully fuzzy → non-auditable, impossible to trust

---

## Decision

We adopt a **hybrid resolution model**:

### 1. Deterministic Core (Hard Constraints)

A candidate CPU is **eligible only if all hard constraints pass**:

* Unit compatibility (e.g., m² ≠ m³)
* Domain/category compatibility
* Required attributes present
* Structural compatibility (e.g., requires formwork? excavation type?)

This acts as a **strict filter**, not a scoring factor.

---

### 2. Scoring Edge (Soft Ranking)

Among valid candidates, we apply **weighted scoring**:

| Dimension           | Description                                     |
| ------------------- | ----------------------------------------------- |
| Semantic similarity | Text/embedding similarity                       |
| Attribute match     | Parameter alignment (thickness, material, etc.) |
| Contextual fit      | Project context (urban/rural, constraints)      |
| Historical priors   | Previously selected mappings                    |

Final score:

```
score = Σ(weight_i * feature_i)
```

---

### 3. Resolution Output Contract

Resolution does NOT return “the answer”.

It returns a **ranked decision set**:

```json
{
  "scope_item_id": "SI-001",
  "candidates": [
    {
      "cpu_id": "CPU-123",
      "score": 0.87,
      "confidence": "HIGH",
      "explanations": [
        "unit_match",
        "semantic_similarity=0.91",
        "attribute_match=partial(thickness missing)"
      ]
    },
    {
      "cpu_id": "CPU-456",
      "score": 0.72,
      "confidence": "MEDIUM",
      "explanations": [...]
    }
  ],
  "resolution_status": "AUTO_SELECTED | NEEDS_REVIEW"
}
```

---

## Confidence Model (Anti-Bullshit Mechanism)

Confidence is **not the score**.

We explicitly prevent “confidence inflation”:

### Rules:

* HIGH → only if:

  * score > threshold_high
  * AND margin to next candidate > delta_min
* MEDIUM → score acceptable but ambiguous
* LOW → weak match or constraint degradation

Example:

```
if score > 0.85 and (score - next_score) > 0.15:
    HIGH
elif score > 0.70:
    MEDIUM
else:
    LOW
```

This avoids the classic trap:

> “0.83 looks high” — yeah, until you notice second place is 0.82.

---

## Rule Engine DSL

We define a minimal DSL for constraints + scoring:

### Hard constraints

```yaml
constraints:
  - type: unit_match
  - type: domain_match
  - type: required_attributes
```

### Scoring

```yaml
scoring:
  - feature: semantic_similarity
    weight: 0.4

  - feature: attribute_match
    weight: 0.3

  - feature: context_fit
    weight: 0.2

  - feature: historical_prior
    weight: 0.1
```

---

## Resolution Pipeline

```
ScopeItem
   ↓
[1] Candidate Retrieval (broad, recall-oriented)
   ↓
[2] Constraint Filtering (deterministic gate)
   ↓
[3] Feature Extraction
   ↓
[4] Scoring
   ↓
[5] Confidence Assignment
   ↓
Resolution Output
```

---

## Integration with Productivity & Planning

Once a CPU is selected:

```
CPU → Productivity Table → efficiency_factor → WorkPackage
```

Key constraint:

> The resolution layer must output **all attributes required by productivity lookup**, not just CPU ID.

Otherwise you create a silent coupling bug where planning “guesses” missing inputs.

---

## Consequences

### Positive

* Auditability preserved (hard constraints)
* Flexibility where it matters (ranking)
* Explainability by design
* Supports human-in-the-loop

### Negative / Risks

* Requires **careful feature engineering** (garbage scoring = garbage decisions)
* DSL can become a hidden programming language if not controlled
* Historical priors can introduce bias loops
* Threshold tuning is non-trivial

---

## Non-Goals

* Fully autonomous resolution
* Zero human validation
* Perfect semantic understanding

If someone promises that, they’re either selling a demo or lying.

---

# 🔧 ADR Remediations — Make It Operational (Not Aspirational)

## 1. Persist Resolution Decisions as First-Class Entities

**Decision: YES — mandatory, not optional**

If you don’t persist decisions, you’ve built a stateless guesser, not a system.

### Why this matters (beyond the obvious)

* You need **traceability** (why did we choose CPU X?)
* You need **replayability** (would we choose the same today?)
* You need **drift detection** (are decisions changing unintentionally?)

### Model it explicitly

```python
class ResolutionDecision(BaseModel):
    decision_id: str
    scope_item_id: str

    selected_cpu_id: str
    candidate_set: list[Candidate]

    scoring_config_version: str
    ruleset_version: str

    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    explanations: list[str]

    decision_source: Literal[
        "AUTO",
        "USER_OVERRIDE",
        "REVIEWED"
    ]

    created_at: datetime
```

### Non-negotiable properties

* **Immutable** (never update, only append new decisions)
* **Linked to inputs** (ScopeItem snapshot, not reference)
* **Linked to config version**

If you skip immutability, congrats — you just destroyed auditability.

---

## 2. Version Scoring Configurations (Treat It Like a Model)

**Decision: Explicit versioning with reproducibility guarantees**

Stop thinking of this as “config”. This *is* your model.

### Minimal viable versioning

```python
class ScoringConfig(BaseModel):
    version: str  # e.g. "v1.3.2"

    weights: dict[str, float]
    thresholds: dict[str, float]

    feature_flags: dict[str, bool]

    created_at: datetime
```

### But versioning alone is not enough

You need:

#### a) Deterministic execution guarantee

Given:

* same input
* same config version
* same ruleset

→ output MUST be identical

If not, your system is non-reproducible.

---

#### b) Config lineage

```text
v1.2 → v1.3 → v1.4
        ↑
    “fixed attribute bias”
```

Otherwise, debugging becomes archaeology.

---

#### c) Shadow evaluation (this is where people get lazy)

Before promoting a new version:

* Run it against historical decisions
* Compare:

  * selection changes
  * confidence shifts

If you don’t do this, you're effectively deploying blind.

---

## 3. Project-Specific Overrides vs Global Consistency

This is where systems usually collapse into chaos.

**Decision: Controlled overrides with explicit scoping**

### The naive approaches (both wrong)

* ❌ “Everything global” → doesn’t fit reality
* ❌ “Everything customizable” → fragmentation nightmare

---

### The correct approach: layered resolution context

```text
Global Config
   ↓
Domain Config (optional)
   ↓
Project Overrides (restricted)
```

---

### Hard rule: overrides cannot break constraints

You can tweak:

* weights
* thresholds
* priors

You cannot override:

* unit compatibility
* structural constraints

If a project can map m² → m³, your system is decorative.

---

### Override model

```python
class ResolutionContext(BaseModel):
    config_version: str
    override_layer: Literal["GLOBAL", "DOMAIN", "PROJECT"]

    overrides: dict[str, Any]
    justification: str
```

---

### Governance constraint

Every override must have:

* justification
* scope
* expiration (yes, expiration — otherwise overrides become permanent bugs)

---

# 🧠 Now the “Practical Take” — Turn It Into Enforcement

Your previous note is correct but still too soft. Let’s weaponize it.

---

## 1. “Log every decision” → Enforced via architecture

Not a guideline. A constraint:

* Resolution API **must fail** if persistence fails
* No “best effort logging”

---

## 2. “Version every rule” → No implicit defaults

* No “latest config”
* No “fallback config”
* Every call must specify:

  * `ruleset_version`
  * `scoring_config_version`

---

## 3. “Expose explanations” → Structured, not text blobs

Bad:

```json
"explanations": ["good match"]
```

Good:

```json
"explanations": [
  {
    "feature": "semantic_similarity",
    "value": 0.91,
    "weight": 0.4,
    "contribution": 0.364
  }
]
```

If you can’t decompose the score, you can’t debug it.

---

# 🔁 Feedback Loop (Where Most Systems Pretend to Have One)

Let’s make it real.

## Decision Review Loop

```text
ResolutionDecision
   ↓
Human Review (optional but critical)
   ↓
DecisionReview
   ↓
Signals:
   - correct / incorrect
   - confidence mismatch
   ↓
Calibration Inputs
   ↓
New ScoringConfig Version
```

---

### Review model

```python
class DecisionReview(BaseModel):
    decision_id: str

    was_correct: bool
    corrected_cpu_id: str | None

    reviewer_confidence: float  # human judgment
    notes: str

    created_at: datetime
```

---

### What you do with this (this is the hard part)

* Detect **systematic bias**:

  * “always wrong for excavation”
* Adjust:

  * weights
  * thresholds
  * feature engineering

If you’re not closing this loop, your system is static — and will decay.

---

# ⚠️ Final Reality Check

You are not building:

> “a matching system”

You are building:

> **a decision system with legal, financial, and planning consequences**

That means:

* reproducibility > cleverness
* explainability > accuracy (to a point)
* governance > flexibility

# 1) Representing `ScopeItem` Semantically

If your `ScopeItem` is just:

```json
"description": "Concrete slab 10cm thick"
```

you’ve already lost.

You need a **multi-layer semantic representation**, not a string.

---

## The correct mental model: decomposition, not embedding

A `ScopeItem` should be a **structured hypothesis about intent**:

```python
class ScopeItemSemantic(BaseModel):
    # Raw
    original_text: str

    # Core classification
    domain: Literal["earthwork", "concrete", "finishing", ...]
    activity_type: str  # "slab_execution", "excavation", etc.

    # Measurable dimensions
    quantity: float
    unit: str  # m2, m3, etc.

    # Physical attributes
    attributes: dict[str, Any]
    # e.g. {"thickness_cm": 10, "strength_mpa": 25}

    # Material / composition hints
    materials: list[str]  # ["concrete", "rebar"]

    # Execution context
    context: dict[str, Any]
    # e.g. {"location_type": "urban", "access": "restricted"}

    # Confidence per extracted field
    extraction_confidence: dict[str, float]
```

---

## Key idea: **partial structure is fine — implicit structure is not**

Bad system:

> “We’ll infer thickness from embeddings”

Good system:

> “Thickness is missing → attribute_match gets penalized explicitly”

---

## Extraction pipeline (don’t overcomplicate it)

```text
Text
 ↓
Rule-based extraction (units, numbers)
 ↓
Dictionary / ontology mapping (activities, materials)
 ↓
LLM assist (ONLY for filling gaps, not primary logic)
 ↓
Structured ScopeItemSemantic
```

---

## Critical constraint

Every field must answer:

> “Will this affect CPU selection or productivity?”

If not, it’s noise. Drop it.

---

# 2) Normalizing CPU Attributes

Your CPU catalog is probably “structured”… in the same way spreadsheets are “databases”.

Meaning:

* inconsistent naming
* missing attributes
* implicit assumptions

If you don’t normalize this, your scoring is comparing garbage to garbage.

---

## Target: canonical CPU representation

```python
class CPUCanonical(BaseModel):
    cpu_id: str

    domain: str
    activity_type: str

    unit: str

    base_productivity: float  # e.g. m2/day

    attributes: dict[str, Any]
    # same schema as ScopeItem

    required_attributes: set[str]

    optional_attributes: set[str]
```

---

## The real work: attribute normalization

You need a **controlled vocabulary**.

### Example problem

Catalog A:

```json
"espessura": 0.10
```

Catalog B:

```json
"thickness_mm": 100
```

If you don’t normalize:

→ your “attribute_match” becomes random

---

## Solution: canonical attribute registry

```python
ATTRIBUTE_REGISTRY = {
    "thickness": {
        "type": "float",
        "unit": "cm",
        "aliases": ["espessura", "thickness_mm"],
        "normalizer": lambda x: x / 10 if x > 20 else x
    }
}
```

---

## Normalize at ingestion, not at runtime

Bad:

> normalize during scoring

Good:

> CPUCanonical is already normalized

Otherwise:

* performance degrades
* bugs become non-deterministic

---

## Missing attributes are first-class citizens

```python
attributes = {
    "thickness": None  # explicit missing
}
```

This enables:

* deterministic penalties
* explainability

---

# 3) Avoiding Embedding Over-Reliance

This is where most teams shoot themselves in the foot while feeling sophisticated.

---

## The trap

> “We’ll just embed everything and do similarity search”

What happens in practice:

* “Concrete slab” ≈ “Concrete wall” (high similarity)
* Completely different execution logic
* System confidently picks the wrong CPU

---

## Principle: embeddings are **recall tools**, not decision tools

Use them for:

* candidate retrieval (broad set)
* synonym handling

Never for:

* final selection
* constraint validation

---

## Correct usage in your pipeline

```text
ScopeItem
 ↓
[Embedding search]
 ↓
Top 20 candidates
 ↓
[Hard constraints]
 ↓
Filtered candidates
 ↓
[Structured scoring]
 ↓
Final decision
```

---

## Feature hierarchy (this is your safety net)

Order matters:

1. **Hard constraints** (unit, domain)
2. **Explicit attributes** (thickness, material)
3. **Context**
4. **Embeddings**

If embeddings dominate your score, you’ve already lost control.

---

## Cap embedding influence

```python
embedding_weight <= 0.4  # hard cap
```

And even that is generous.

---

## Detect embedding failure modes

You *must* explicitly detect:

### 1. High similarity, low attribute match

→ likely false positive

### 2. High similarity across many candidates

→ low discriminative power

### 3. Semantic ambiguity

→ force MEDIUM confidence

---

## Optional but powerful: semantic guards

Example:

```python
if activity_type_mismatch:
    score *= 0.5
```

This prevents embeddings from “hallucinating equivalence”.

---

# Wrap-up (No fluff, just reality)

You’re building three layers of truth:

---

## 1. ScopeItem = **intent hypothesis**

* structured
* partially uncertain
* explicit gaps

---

## 2. CPU = **execution truth**

* normalized
* canonical
* comparable

---

## 3. Matching = **controlled comparison**

* constraints eliminate nonsense
* attributes drive correctness
* embeddings assist, never decide

---

## The uncomfortable truth

If you skip:

* attribute normalization → your scoring is noise
* structured ScopeItem → your inputs are guesses
* embedding constraints → your system will look smart and be wrong

And worse:

> it will be wrong *confidently*

—which is exactly what kills trust in planning systems.

---

That’s the foundation. Everything else (rules, scoring, feedback loop) only works if this layer is solid.
---

## Definition of Done

- [x] `ResolutionDecision` model persisted as immutable record per scope item resolution (never updated, only appended)
- [x] `ResolutionDecision` carries: `decision_id`, `scope_item_id`, `selected_cpu_id`, `candidate_set`, `scoring_config_version`, `confidence`, `explanations`, `decision_source`, `created_at`
- [x] Hard constraints (unit compatibility, domain match, required attributes) gate candidate eligibility before scoring
- [x] Confidence `HIGH` only when score > `threshold_high` AND margin to next candidate > `delta_min` (anti-inflation guard)
- [x] `decision_source` correctly set: `AUTO` / `USER_OVERRIDE` / `REVIEWED`
- [x] `resolution_status: "AUTO_SELECTED" | "NEEDS_REVIEW"` correctly populated
- [x] `ScoringConfig` carries explicit `version` field; every `ResolutionDecision` references config version
- [x] Resolution output includes all CPU attributes required by productivity lookup (no silent coupling gaps)
- [x] `DecisionReview` model accepts human correction signals (`was_correct`, `corrected_cpu_id`, `reviewer_confidence`)
- [x] Integration tests: clear single candidate → HIGH confidence AUTO_SELECTED; close-score tie → MEDIUM / NEEDS_REVIEW
