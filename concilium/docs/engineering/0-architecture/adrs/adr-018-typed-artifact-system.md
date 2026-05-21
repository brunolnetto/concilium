# ADR-018 — Typed Artifact System and MCP Anti-Corruption Layer

**Title:** Unified Artifact Envelope for Concilium's Domain Objects + MCP Server as Gateway  
**Status:** Implementado  
**Date:** 2026-05-02  
**Date Implemented:** 2026-05-02  
**Implementers:** models/artifact.py (ArtifactKind, ArtifactEnvelope, ArtifactMeta, ArtifactState), storage/artifact_store.py (FileSystemArtifactStore)  
**Decision Maker:** Engineering Lead (Concilium Architecture)

**Source:** Informed by architectural discussion on typed artifact systems and gateway design.

---

## Context

Concilium already has artifact-like structures, but they are not unified:

```
SnapshotStore     → content-addressed (SHA-256), immutable ✅
ProjectStore      → canonical.json per version, chmod 444 on approve ✅
Producao          → versioned (PROD-001 → PROD-002), audit trail ✅ (ADR-007)
Observacao        → typed, timestamped (ADR-017) ✅
PropostaAtualizacao → typed with governance (ADR-017) ✅
CanonicalModel    → large aggregate, no envelope ❌
Insumo            → no version, no content hash ❌
CPU               → no envelope, referenced by string ID ❌
```

Three problems emerge:

**Problem 1 — No uniform lineage.** When `Resultado` (Skill 06) is computed, there is no machine-readable record that it derives from `Cronograma` (Skill 02) → `EquipeDireta` (Skill 03) → `Indireto` (Skill 05). The `invocations.log` captures skill execution order but not artifact parentage.

**Problem 2 — No trace correlation.** A Claude Desktop session calling `avancar_pipeline` three times produces three skill executions with no shared identifier. Debugging "why did Skill 05 produce R$X?" requires manual reconstruction.

**Problem 3 — MCP schema leakage risk.** As `server.py` grows, there is pressure to return rich internal objects directly. Without a formal contract at the MCP boundary, internal model changes silently break Claude's behavior.

---

## Decisions

### D1 — Typed Artifact Envelope for Concilium Domain Objects

We adopt the `ArtifactEnvelope` pattern for the artifact types that need lineage, replay, and audit. This is **not applied to everything** — only to artifacts that flow between layers or are subject to governance.

```python
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
from typing import Any, Generic, Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T", bound=BaseModel)


class ArtifactState(str, Enum):
    DRAFT      = "draft"       # Created, not yet committed
    COMMITTED  = "committed"   # Valid, immutable
    SUPERSEDED = "superseded"  # Replaced by newer version
    DEPRECATED = "deprecated"  # Readable, not to be produced
    REJECTED   = "rejected"    # Failed validation or governance


class ArtifactKind(str, Enum):
    # Concilium-specific kinds (not generic)
    CANONICAL     = "canonical"      # CanonicalModel snapshot per version
    PRODUCAO      = "producao"       # Productivity artifact (ADR-007)
    OBSERVACAO    = "observacao"     # Catalog observation (ADR-017)
    PROPOSTA      = "proposta"       # Catalog update proposal (ADR-017)
    DECISAO       = "decisao"        # Technical decision (Skill 11)
    RESULTADO     = "resultado"      # Financial result (Skill 06)
    RELATORIO     = "relatorio"      # Output adapter (Skill 07)


class ArtifactRef(BaseModel):
    """Stable, immutable reference to a specific artifact version."""
    model_config = ConfigDict(frozen=True)

    artifact_id: str
    version: str
    kind: ArtifactKind
    schema_name: str
    schema_version: str
    content_hash: str


class ArtifactMeta(BaseModel):
    """Envelope metadata — separate from payload, searchable."""
    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    version: str = "1.0.0"
    kind: ArtifactKind
    schema_name: str
    schema_version: str

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str                 # Skill ID or MCP operation name
    trace_id: Optional[str] = None  # Shared across one Claude session (D3)

    parent_refs: list[ArtifactRef] = Field(default_factory=list)
    # ↑ explicit lineage: Resultado derives from Canonical v3

    state: ArtifactState = ArtifactState.DRAFT
    content_hash: str               # SHA-256 of payload JSON


class ArtifactEnvelope(Generic[T], BaseModel):
    """Immutable artifact: metadata + typed payload."""
    model_config = ConfigDict(frozen=True)

    meta: ArtifactMeta
    payload: T

    def ref(self) -> ArtifactRef:
        return ArtifactRef(
            artifact_id=self.meta.artifact_id,
            version=self.meta.version,
            kind=self.meta.kind,
            schema_name=self.meta.schema_name,
            schema_version=self.meta.schema_version,
            content_hash=self.meta.content_hash,
        )
```

---

### D2 — Which Artifacts Get Envelopes

Not everything needs an envelope. The rule:

> An artifact gets an envelope if it crosses a layer boundary, is subject to governance, or needs lineage tracing.

```
GETS ENVELOPE:                      DOES NOT GET ENVELOPE:
─────────────────────────────────   ──────────────────────────────────
Producao        (ADR-007)           ValidacaoItem  (inline, ephemeral)
Observacao      (ADR-017)           DistribuicaoMensal (internal calc)
PropostaAtualiz (ADR-017)           Coordenadas    (input scalar)
CanonicalModel  (per version)       RegimeTrabalho (config, not output)
Resultado       (Skill 06 output)   Praticabilidade (intermediate)
DecisionLog     (Skill 11)
RelatorioSaida  (Skill 07)
```

**Boundary rule for CanonicalModel:**
The current `canonical.json` file IS the artifact. ADR-018 adds an `ArtifactMeta` sidecar file (`canonical.meta.json`) alongside it, without changing the canonical model shape. This avoids a breaking migration.

```
projetos/lote09/v3/
  canonical.json         ← unchanged (payload)
  canonical.meta.json    ← NEW (ArtifactMeta sidecar)
  invocations.log        ← unchanged
```

---

### D3 — Trace ID Propagation

A `trace_id` is created once per Claude Desktop session and propagated to all artifacts produced in that session:

```
Claude Desktop session begins
  ↓
MCP operation: iniciar_orcamento(...)
  trace_id = "01JX4NM..."   ← generated at MCP boundary
  ↓
Skill 00-escopo runs
  canonical.meta.json: trace_id = "01JX4NM..."
  ↓
avancar_pipeline × N
  Each canonical version: trace_id = "01JX4NM..."
  ↓
Resultado committed
  resultado.artifact.json: trace_id = "01JX4NM...",
                            parent_refs = [canonical_v3_ref]
```

**Implementation:** `trace_id` is generated in the MCP server at session start and passed to `Runtime.run_skill()` via context. Skills do not generate trace IDs — they inherit them.

```python
# In server.py — trace_id generation
import uuid

def _get_or_create_trace_id(session_context: dict) -> str:
    if "trace_id" not in session_context:
        session_context["trace_id"] = str(uuid.uuid4())
    return session_context["trace_id"]
```

**Minimal tracing — no OpenTelemetry required.** `trace_id` is stored in artifact metadata and `invocations.log`. This enables:
- "Show me everything produced in this planning session"
- "Which canonical version led to this Resultado?"
- Debugging without log archaeology

---

### D4 — Artifact Lineage for Concilium's Chain

The production chain maps to explicit `parent_refs`:

```
Skill 00-escopo:
  Produces: CanonicalModel v1
  parents:  [] (root — derived from user inputs)

Skill 06-consolidar:
  Produces: Resultado
  parents:  [CanonicalModel_v1_ref]
             ↑ "this result was computed from this canonical version"

Skill 07-adapter-saida:
  Produces: RelatorioSaida (.xlsm)
  parents:  [Resultado_ref, CanonicalModel_v1_ref]

Producao PROD-002 (ADR-017 update):
  parents:  [PROD-001_ref, Observacao_lote12_ref]
             ↑ "this productivity version was created from this observation"

PropostaAtualizacao:
  parents:  [Observacao_ref_1, Observacao_ref_2]
             ↑ "this proposal is supported by these observations"
```

---

### D5 — MCP Server as Anti-Corruption Layer (No Separate Gateway)

The ChatGPT discussion proposed a FastAPI gateway between Claude and the MCP server. **This is not needed for Concilium** at current scale, and would add latency and operational overhead for a tool running over stdio.

However, the anti-corruption principle IS correct and already partially implemented. Formalizing it:

```
Claude Desktop
      ↓  (MCP stdio protocol)
MCP Server (server.py)        ← THIS IS THE GATEWAY
      ↓  (Python function calls)
Runtime / Skills / Storage
```

The MCP server is already the anti-corruption layer. Its contract:

```python
# WHAT MCP OPERATIONS MUST RETURN (contract):
# Business-readable summaries — never internal model dumps

# ❌ Wrong (leaks internals):
return canonical.model_dump()

# ✅ Correct (business contract):
return {
    "margem_pct": resultado.margem_pct,
    "status_margem": resultado.status_margem,
    "custo_total": resultado.custo_total.total,
    "proxima_acao": _suggest_next(canonical),
    "trace_id": trace_id,          # ← NEW: propagated for debugging
    "artifact_ref": resultado_ref,  # ← NEW: stable reference for replay
}
```

**Two additions to the existing MCP contract (ADR-013/ADR-014):**
1. All responses include `trace_id` (D3)
2. Committed outputs include `artifact_ref` (stable reference for future queries)

**Schema versioning at MCP boundary:**

```python
# In server.py — every tool response carries schema version
RESPONSE_SCHEMA_VERSION = "2026-05-02"

def _wrap_response(data: dict, trace_id: str) -> dict:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "trace_id": trace_id,
        **data,
    }
```

When `RESPONSE_SCHEMA_VERSION` changes, Claude's project instructions must be updated. This is the explicit contract boundary — no silent drift.

---

### D6 — Artifact Registry (Minimal)

A registry maps `schema_name` to payload class, enabling validation without hardcoded types:

```python
class ConciliumArtifactRegistry:
    """Maps schema names to Pydantic payload classes."""

    _schemas: dict[str, type[BaseModel]] = {
        "CanonicalModel":       CanonicalModel,
        "Producao":             Producao,
        "ObservacaoProdutiv":   ObservacaoProdutividade,
        "PropostaAtualizacao":  PropostaAtualizacao,
        "Resultado":            Resultado,
        "DecisionLogEntry":     DecisionLogEntry,
    }

    @classmethod
    def validate(cls, schema_name: str, data: dict) -> BaseModel:
        model = cls._schemas.get(schema_name)
        if not model:
            raise ValueError(f"Unknown artifact schema: {schema_name}")
        return model.model_validate(data)

    @classmethod
    def register(cls, name: str, model: type[BaseModel]) -> None:
        """Extension point for new artifact types (e.g. from ADR-016 class annotations)."""
        cls._schemas[name] = model
```

---

## What This ADR Does NOT Adopt

From the ChatGPT discussion, these were deliberately omitted:

| Proposed | Decision | Reason |
|---|---|---|
| FastAPI HTTP gateway | ❌ Not adopted | Concilium uses stdio MCP; HTTP adds latency + ops overhead without benefit at current scale |
| OpenTelemetry | ❌ Not adopted | `trace_id` in artifact metadata achieves debuggability without OTel infrastructure dependency |
| Relational DB for artifact storage | ❌ Not adopted | File-based storage (JSON + content-addressed) is sufficient; migration path preserved via `ArtifactStore` interface |
| Tool version registry in gateway | ❌ Not adopted | MCP operation versioning via `RESPONSE_SCHEMA_VERSION` string is sufficient |
| Auth/JWT mapping | ❌ Not adopted | Internal tool; auth not in scope |
| Separate `ArtifactStore` interface | ✅ Adopted (interface only) | Preserves migration path to DB without requiring it now |

---

## Artifact Store Interface

```python
class ArtifactStore:
    """Storage backend — today: file system. Future: DB if needed."""

    def save(self, artifact: ArtifactEnvelope[Any]) -> None:
        raise NotImplementedError

    def get(self, ref: ArtifactRef) -> ArtifactEnvelope[Any]:
        raise NotImplementedError

    def list_by_trace(self, trace_id: str) -> list[ArtifactRef]:
        """All artifacts from one Claude Desktop session."""
        raise NotImplementedError

    def list_by_kind(self, kind: ArtifactKind) -> list[ArtifactRef]:
        raise NotImplementedError


class FileSystemArtifactStore(ArtifactStore):
    """
    Current implementation: sidecar .meta.json files alongside payloads.
    canonical.json + canonical.meta.json in version directory.
    producoes/PROD-001.json + producoes/PROD-001.meta.json.
    """
    ...
```

---

## Impact on Existing Code

| Component | Change | Size |
|---|---|---|
| `ProjectStore.save_canonical` | Write `canonical.meta.json` sidecar | Small |
| `ProjectStore.load_canonical` | Optionally load sidecar for trace queries | Small |
| `Producao` (ADR-007) | Already has `auditoria` → map to `ArtifactMeta` | Medium |
| `server.py` | Add `trace_id` generation + `_wrap_response` | Small |
| `Runtime.run_skill` | Accept + propagate `trace_id` | Small |
| New: `ArtifactEnvelope`, `ArtifactMeta`, `ArtifactRef` | New models | Medium |
| New: `ConciliumArtifactRegistry` | New class | Small |
| New: `FileSystemArtifactStore` | New class | Medium |

---

## Related ADRs

- **ADR-007** (Productivity): `Producao` becomes first artifact to adopt envelope fully
- **ADR-013** (MCP Facade): MCP server is confirmed as the anti-corruption layer
- **ADR-014** (MCP Surface): All operations gain `trace_id` + `artifact_ref` in response
- **ADR-017** (Catalog Lifecycle): `Observacao` + `PropostaAtualizacao` get envelopes

---

## Definition of Done

- [x] `ArtifactEnvelope`, `ArtifactMeta`, `ArtifactRef`, `ArtifactState`, `ArtifactKind` models
- [x] `ConciliumArtifactRegistry` with initial schema map
- [x] `ArtifactStore` interface + `FileSystemArtifactStore` implementation
- [x] `canonical.meta.json` sidecar written by `ProjectStore.save_canonical`
- [x] `trace_id` generated in `server.py`, propagated through `Runtime`
- [x] `_wrap_response` helper in `server.py` with `schema_version`
- [x] `Producao` model mapped to `ArtifactEnvelope[ProducaoPayload]`
- [x] `list_by_trace(trace_id)` returns all artifacts from one session
- [ ] 5+ test cases:
  - [ ] Envelope immutability (frozen=True, modification raises)
  - [ ] Content hash matches payload JSON
  - [ ] `parent_refs` chain: Resultado → CanonicalModel
  - [ ] `list_by_trace` returns all artifacts with same trace_id
  - [ ] Registry validates known schema, raises on unknown

---

## Summary

**Decision:** Adopt typed `ArtifactEnvelope` for Concilium's domain objects that cross layer boundaries or require governance. Add `trace_id` propagation from MCP session through Runtime to all committed artifacts. Confirm MCP server as the anti-corruption layer — no separate HTTP gateway.

```
WHAT WE ADOPT:
  ArtifactEnvelope (immutable, hashed, lineage via parent_refs)
  trace_id (one per Claude Desktop session, propagated everywhere)
  ArtifactStore interface (file-system today, DB-ready tomorrow)
  MCP schema_version in all responses (explicit contract boundary)

WHAT WE DEFER:
  OpenTelemetry (trace_id in metadata is sufficient for now)
  HTTP gateway (stdio MCP is adequate; revisit at multi-user scale)
  Relational DB (file-system store preserved behind interface)
```

The real value, per the source material: artifacts become **first-class evidence of work**, not anonymous JSON files. The chain `intent → plan → result → report` becomes machine-readable and replayable — without reconstructing it from timestamps and hope.