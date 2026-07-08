# ADR-001: Semantic Layer for Client Scope Interpretation

**Status:** Implementado  
**Date Decided:** 2026-04-29  
**Date Implemented:** 2026-04-29  
**Implementers:** models/semantic_layer.py, skills/00-escopo  
**Context:** The system must translate unstructured or semi-structured client scope items into structured entities that can be deterministically mapped to internal catalog elements (CPUs) and subsequently used for planning.

Key challenges:

* Client descriptions are inconsistent, ambiguous, and lossy
* CPU catalog requires strict compatibility (unit, dimensions, method, etc.)
* Downstream planning depends on correctness, not similarity
* Retrieval techniques (e.g., embeddings) are insufficient as a source of truth

There is a need for a **controlled semantic layer** that:

1. Normalizes client input into a canonical representation
2. Preserves enough structure for deterministic validation
3. Avoids overfitting to specific catalog implementations
4. Enables traceability and auditability of decisions

---

## Decision

We introduce a **Semantic Layer** based on a canonical, typed model called `SemanticIntent`.

This layer acts as a **contract boundary** between:

* Upstream: unstructured client input
* Downstream: deterministic resolution (CPU mapping, productivity, planning)

---

## Semantic Model

The core entity is defined as:

```python
class SemanticIntent(BaseModel):
    raw_text: str

    category: Literal[
        "earthwork", "pavement", "drainage", "structure"
    ]

    activity: str
    material: Optional[str]
    method: Optional[str]

    unit: str

    dimensions: List[Dimension]
    qualifiers: List[str]
```

### Design Principles

1. **Canonical, not exhaustive**

   * The model captures only what is required for resolution
   * It is not a full ontology of construction activities

2. **Normalized fields**

   * `activity`, `material`, and `method` must be mapped to controlled vocabularies where possible

3. **Explicit dimensions**

   * Quantitative attributes (e.g., thickness) are first-class citizens
   * Avoid encoding dimensions in free text

4. **Unit as a contract**

   * Unit must be explicit and normalized
   * Unit mismatch is a hard failure in downstream processing

---

## Responsibilities

The Semantic Layer is responsible for:

* Parsing raw input into `SemanticIntent`
* Normalizing units, activities, and dimensions
* Rejecting inputs that cannot be interpreted with sufficient structure

The Semantic Layer is **not responsible for**:

* Selecting CPUs
* Applying productivity
* Performing planning calculations
* Inferring missing critical attributes beyond safe defaults

---

## Parsing Strategy

The parsing approach follows a **deterministic-first strategy**:

1. Rule-based extraction (regex, keyword dictionaries)
2. Controlled normalization (mapping tables)
3. Optional LLM fallback for edge cases (must be logged and flagged)

If parsing fails to produce a valid `SemanticIntent`, the process must stop with an explicit failure.

---

## Invariants

The following invariants must hold:

* `unit` is always present and normalized
* All dimensions are structured (`name`, `value`, `unit`)
* No critical attribute is inferred silently
* Every `SemanticIntent` is traceable back to `raw_text`

---

## Failure Modes

The Semantic Layer must explicitly handle:

* Missing unit → reject
* Ambiguous activity → reject or flag for review
* Conflicting dimensions → reject
* Unsupported category → reject

Failure is a valid and expected outcome.

---

## Consequences

### Positive

* Enables deterministic validation in resolution layer
* Reduces ambiguity propagation into planning
* Provides a stable contract for future extensions (rules, DSL, calibration)
* Improves auditability of decisions

### Negative

* Higher upfront rejection rate of inputs
* Requires curation of vocabularies and parsing rules
* May require human intervention for ambiguous cases
* Limits flexibility in early stages

---

## Trade-offs

| Aspect           | Decision                 | Alternative (Rejected)      |
| ---------------- | ------------------------ | --------------------------- |
| Flexibility      | Controlled schema        | Free-form text + embeddings |
| Parsing approach | Deterministic-first      | LLM-first                   |
| Error handling   | Explicit failure         | Silent fallback             |
| Model scope      | Minimal canonical schema | Full domain ontology        |

---

## Future Considerations

The Semantic Layer is designed to support:

* Rule Engine DSL for constraint evaluation
* Scoring calibration based on historical mappings
* Versioning of semantic interpretations
* Decision logging (ADR-style runtime traceability)

However, these are **explicitly out of scope for the initial implementation (MVP)**.

---

## Open Questions

* What is the minimal viable controlled vocabulary for `activity`?
* How should tolerance (e.g., thickness variance) be represented?
* When should LLM parsing be allowed vs rejected?
* How to version semantic interpretations over time?

---

## Definition of Done

- [x] `SemanticIntent` model defined as frozen Pydantic model (no mutation after construction)
- [x] All EAP scope items pass through `SemanticIntent` parsing before CPU resolution
- [x] `unit` is always present and normalized — no implicit defaults
- [x] `dimensions` are structured `(name, value, unit)` — no free-text encoding of quantitative attributes
- [x] Inputs without a valid unit → explicit `VAL-SCOPE-UNIT-MISSING` error (hard failure, not silent fallback)
- [x] Ambiguous activity → `VAL-SCOPE-AMBIGUOUS` error or flagged for review (not resolved silently)
- [x] Conflicting or unsupported attributes → explicit rejection
- [x] Every parsed `SemanticIntent` carries original `raw_text` (full traceability back to client input)
- [x] LLM fallback (if used) is logged and flagged — never silent
- [x] Unit tests cover: happy path, missing unit rejection, ambiguous activity rejection, conflicting dimensions rejection

---

## Decision Summary

We adopt a **strict, minimal, and deterministic semantic layer** that prioritizes:

> correctness, traceability, and rejection over flexibility and coverage.

This layer becomes the foundation for all downstream decisions and must remain stable, auditable, and intentionally constrained.
