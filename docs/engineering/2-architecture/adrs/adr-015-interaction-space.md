# ADR-015: MCP Use Case Space and Replan Interaction Surface

**Status:** Implementado  
**Date Decided:** 2026-05-02  
**Date Implemented:** 2026-05-02  
**Implementers:** mcp_server/server.py (explorar_alternativas fix, Tools 10–13)  
**Context:** Complete coverage map: (Project State × Engineer Intent) → Operation.

---

## Decision: Use Case Space

The MCP facade use case space is the product of two dimensions:

```
USE_CASE_SPACE = PROJECT_STATE × ENGINEER_INTENT
```

### Dimension 1: Project Lifecycle States

```
S0  NO_PROJECT       No project exists yet
S1  SCOPED           00-escopo ran; EAP defined, no schedule
S2  PLANNED          Pipeline partial: through 06-consolidar (resultado exists)
S3  CONFLICT         Pipeline ran but has resource conflicts or deadline violations
S4  APPROVED         Version locked (read-only, chmod 444)
```

Note: S2 and S3 are the same pipeline stage — distinguished only by validation outcome.

### Dimension 2: Engineer Intent

```
I1  INITIALIZE       "Start a new project from scope"
I2  ORIENT           "Where am I? What's the current state?"
I3  PROGRESS         "Run the next planning step"
I4  DIAGNOSE         "What's wrong? What constraints are violated?"
I5  SIMULATE         "What if I change X? Show me alternatives"
I6  COMMIT           "This is final. Freeze it."
```

---

### Coverage Matrix

```
           I1          I2             I3              I4               I5                I6
        INITIALIZE   ORIENT         PROGRESS        DIAGNOSE         SIMULATE          COMMIT
       ─────────────────────────────────────────────────────────────────────────────────────────
S0  │  iniciar_     listar_        ─ (nothing      ─ (nothing       ─ (nothing         ─
NO  │  orcamento    projetos       to progress)    to diagnose)     to simulate)
    │  ✅ EXISTS    ✅ EXISTS
    ├─────────────────────────────────────────────────────────────────────────────────────────
S1  │  ─            consultar_     avancar_        ─ (no resultado  ─ (no resultado    ─
SCOPED│            status          pipeline        to query)        to vary)
    │               ✅ EXISTS      ✅ EXISTS
    ├─────────────────────────────────────────────────────────────────────────────────────────
S2  │  ─            consultar_     avancar_        consultar_       explorar_          aprovar_
PLANNED│            status         pipeline        viabilidade_     alternativas       versao
    │               ✅ EXISTS      ✅ EXISTS        prazo            ✅ EXISTS*         ✅ EXISTS
    │                                              ❌ GAP           simular_impacto_
    │                                                               replan
    │                                                               ❌ GAP
    ├─────────────────────────────────────────────────────────────────────────────────────────
S3  │  ─            consultar_     ─ (pipeline     identificar_     explorar_          ─ (must
CONFLICT│           status         ran, has        gargalos_        alternativas       resolve
    │               ✅ EXISTS      errors; must    recurso          ✅ EXISTS*         first)
    │                              resolve)        ❌ GAP           simular_impacto_
    │                                              consultar_       replan
    │                                              viabilidade_     ❌ GAP
    │                                              prazo
    │                                              ❌ GAP
    ├─────────────────────────────────────────────────────────────────────────────────────────
S4  │  ─            consultar_     ─ (locked)      ─ (locked)       ─ (locked;         ─ (already
APPROVED│           status                                          read new version   done)
    │               ✅ EXISTS                                        from v_new)
    └─────────────────────────────────────────────────────────────────────────────────────────

✅ EXISTS   = implemented in server.py
❌ GAP      = needed, not implemented
* = partially correct (see Part II — replan surface analysis)
```

### Missing Operations (Gaps Summary)

| Gap | State(s) | Intent | Priority |
|-----|----------|--------|----------|
| `sugerir_eap` | S0 | I1 | HIGH — Claude can't know cpu_ids |
| `consultar_viabilidade_prazo` | S2, S3 | I4 | HIGH — core planning question |
| `identificar_gargalos_recurso` | S3 | I4 | HIGH — explains why S3 exists |
| `simular_impacto_replan` | S2, S3 | I5 | HIGH — activity-level what-if |
| `simular_impacto_indiretos` | S2, S3 | I5 | MEDIUM — permanência cost delta |
| `nova_versao` | S4 | I3 | MEDIUM — fork approved version for revision |
| `listar_cpus` | S0, S1 | I1 | MEDIUM — catalog query without full eap |

### State Transitions

```
S0 ──[iniciar_orcamento]──→ S1
S1 ──[avancar_pipeline × N]──→ S2 or S3
S2 ──[aprovar_versao]──→ S4
S3 ──[simular_impacto_replan + avancar_pipeline]──→ S2 or S3
S4 ──[nova_versao (gap)]──→ S1 (new version forked from S4)
```

### One Structural Problem: `explorar_alternativas` PERSISTS

Reading `ScenarioRunner.run_scenario()`:

```python
versao = self.project.new_version()  # ← creates a real version in storage
for skill_id in pipeline:
    result = self.runtime.run_skill(skill_id, self.project, version=versao, ...)
```

**Every scenario call creates a new persisted version.** Three scenarios = three new versions (v2, v3, v4). This is:

- ✅ Correct for "run full pipeline variations and compare" (batch analysis)
- ❌ Wrong for "engineer asks what-if and wants a quick answer" (interactive simulation)

The existing `explorar_alternativas` is **batch analysis that happens to be exposed via MCP**, not an interactive simulation tool. It satisfies I5 only partially: good for coarse sensitivity, wrong for targeted replan exploration.

The distinction must be explicit in the facade:

```
explorar_alternativas    → batch, persists N new versions, project-wide multipliers
simular_impacto_replan   → virtual, no persistence, activity-level or typed replan
```

---

## Part II — Replan Interaction Surface

### What "Replan" Means at MCP Level

From ADR-006 (Steuerung only): replan is triggered when **planning constraints are violated** during the planning phase — not during execution. Three replan types:

```
TYPE 1: extend_deadline    Schedule needs more time than contract allows
TYPE 2: add_resource       Resource pool exhausted (peak conflict)
TYPE 3: reduce_scope       Budget exceeded; defer activities
```

Each type has a different **input surface**, **impact calculation**, and **feasibility check**.

---

### Replan Operations: Full Input/Output Contract

#### `consultar_viabilidade_prazo`

**When to call:** Engineer asks "Does the schedule fit the contract deadline?"

**Claude provides:**
```python
consultar_viabilidade_prazo(project_id="a3f2c1d0")
# No extra parameters: reads canonical.cronograma + canonical.projeto.data_termino
```

**Server returns:**
```json
{
  "project_id": "a3f2c1d0",
  "version": "v2",
  "viavel": false,
  "data_termino_contrato": "2026-12-31",
  "data_termino_prevista": "2027-02-14",
  "semanas_excedentes": 7,
  "atividades_no_caminho_critico": ["PAVIM-01", "COMPAC-03", "REMAT-01"],
  "folga_minima_semanas": -7,
  "nota": "Cronograma excede prazo contratual em 7 semanas. Opções: extend_deadline, add_resource, ou reduce_scope."
}
```

**Implementation:** reads `canonical.cronograma_semanal` if exists, else `canonical.cronograma`; compares final week against `canonical.projeto.data_termino`.

---

#### `identificar_gargalos_recurso`

**When to call:** Engineer asks "Where are resource bottlenecks?" or S3 (pipeline ran with conflicts).

**Claude provides:**
```python
identificar_gargalos_recurso(
    project_id="a3f2c1d0",
    semana_inicio=0,    # optional, default: 0
    semana_fim=None     # optional, default: end of schedule
)
```

**Server returns:**
```json
{
  "project_id": "a3f2c1d0",
  "conflitos": [
    {
      "recurso": "operador_maquina",
      "semanas_conflito": [8, 9, 10],
      "demanda_max": 5,
      "capacidade_pool": 3,
      "excedente": 2,
      "atividades_conflitantes": ["EXCAV-01", "COMPAC-02"],
      "recomendacao": "BUY (adicionar 2 ao pool) ou SHIFT (atrasar COMPAC-02 para semana 11)"
    }
  ],
  "semanas_com_pico": [8, 9, 10],
  "taxa_utilizacao_media_pct": 87.3,
  "nota": "2 conflitos detectados. Semanas 8–10 são críticas para operadores."
}
```

**Implementation:** reads `canonical.conflitos_pico` (already populated by Skill 03C). If `conflitos_pico` is empty but S3, re-runs 03C on current canonical.

---

#### `simular_impacto_replan`

**When to call:** Engineer wants to test a specific replan option BEFORE committing.

**Claude provides:**
```python
# Type 1: extend deadline
simular_impacto_replan(
    project_id="a3f2c1d0",
    tipo="extend_deadline",
    parametros={"semanas": 4}
)

# Type 2: add resource to pool
simular_impacto_replan(
    project_id="a3f2c1d0",
    tipo="add_resource",
    parametros={
        "recurso": "operador_maquina",
        "quantidade": 2,
        "semanas": [8, 9, 10]   # temporary addition, not permanent
    }
)

# Type 3: change team allocation on specific activity
simular_impacto_replan(
    project_id="a3f2c1d0",
    tipo="add_teams",
    parametros={
        "atividade_id": "PAVIM-01",
        "equipes_adicionar": 1,
        "semanas": [6, 7, 8]
    }
)

# Type 4: defer activities (scope reduction)
simular_impacto_replan(
    project_id="a3f2c1d0",
    tipo="reduce_scope",
    parametros={
        "atividades_diferir": ["ACABAMENTO-01", "PAISAG-01"],
        "justificativa": "Non-critical; defer to Phase 2"
    }
)
```

**Server returns (all types):**
```json
{
  "project_id": "a3f2c1d0",
  "tipo": "extend_deadline",
  "parametros_aplicados": {"semanas": 4},
  "persisted": false,

  "baseline": {
    "data_termino": "2027-02-14",
    "custo_total": 4750000,
    "margem_pct": 8.65,
    "conflitos_pico": 2,
    "viavel": false
  },

  "simulado": {
    "data_termino": "2027-03-14",
    "custo_total": 5100000,
    "margem_pct": 6.10,
    "conflitos_pico": 0,
    "viavel": true
  },

  "delta": {
    "custo": "+R$ 350.000",
    "custo_pct": "+7.4%",
    "margem_pct": "-2.55pp",
    "semanas": "+4",
    "conflitos_resolvidos": 2,
    "status_margem_novo": "AMARELO"
  },

  "componentes_custo_delta": {
    "indiretos_permanencia": "+R$ 280.000",
    "mob": "+R$ 0 (one-time, unchanged)",
    "diretos": "+R$ 70.000 (additional labor weeks)"
  },

  "nota": "Extensão de 4 semanas resolve todos os conflitos mas reduz margem para 6.1% (AMARELO). Requer aprovação de diretor se aceito."
}
```

**Critical design rule:** `persisted: false` — this operation MUST work on a **virtual copy** of canonical, never calling `project.new_version()`. It computes impact in memory and discards.

**Implementation path:**
```python
def simular_impacto_replan(project_id, tipo, parametros):
    store = _project(project_id)
    rt = _runtime()
    v = store.current_version()

    # Load current canonical (read-only)
    canonical_base = store.load_canonical(v)

    # Apply parametros to virtual copy (in memory only)
    canonical_sim = _apply_replan_virtual(canonical_base, tipo, parametros)

    # Recalculate affected sections (03, 05) on virtual copy
    canonical_sim = _recalc_equipes(canonical_sim, rt)
    canonical_sim = _recalc_indiretos(canonical_sim, rt)
    canonical_sim = _recalc_resultado(canonical_sim, rt)

    # Compute delta
    return _build_delta_response(canonical_base, canonical_sim, persisted=False)
    # canonical_sim is discarded after this call
```

---

#### `simular_impacto_indiretos`

**When to call:** Engineer asks specifically about indirect cost impact of a timeline change.

**Claude provides:**
```python
simular_impacto_indiretos(
    project_id="a3f2c1d0",
    delta_semanas=4    # positive = extend, negative = compress
)
```

**Server returns:**
```json
{
  "project_id": "a3f2c1d0",
  "duracao_atual_semanas": 28,
  "duracao_simulada_semanas": 32,
  "delta_semanas": 4,

  "indiretos_atuais": {
    "TOP":  663975.60,
    "ADM": 6754361.28,
    "LAB":  481552.80,
    "QSMS": 449674.00,
    "MOB": 6265184.86,
    "total": 14614748.54
  },

  "indiretos_simulados": {
    "TOP":  758257.60,
    "ADM": 7719270.72,
    "LAB":  550203.20,
    "QSMS": 513913.60,
    "MOB": 6265184.86,
    "total": 15806829.98
  },

  "delta": {
    "TOP":   "+R$ 94.282,00",
    "ADM":  "+R$ 964.909,44",
    "LAB":   "+R$ 68.650,40",
    "QSMS":  "+R$ 64.239,60",
    "MOB":   "R$ 0 (one-time)",
    "total": "+R$ 1.192.081,44"
  },

  "formula": "CUSTO_CAT = (custo_fixo_mensal / 4.33) × semanas",
  "nota": "4 semanas adicionais aumentam indiretos em R$ 1.19M (+8.1%). ADM é o maior componente."
}
```

**Implementation:** Pure arithmetic from ADR-009 model. No skill invocation needed. Reads `canonical.indiretos` for current values, applies formula directly.

---

### Replan Decision Flow (Full)

```
Engineer: "O plano está viável?"
  → Claude calls: consultar_viabilidade_prazo(project_id)
  → Returns: viavel=false, 7 semanas excedentes

Engineer: "Por quê? Onde está o problema?"
  → Claude calls: identificar_gargalos_recurso(project_id)
  → Returns: operador_maquina overloaded weeks 8–10

Engineer: "O que acontece se eu adicionar 2 operadores nas semanas 8–10?"
  → Claude calls: simular_impacto_replan(tipo="add_resource",
                    parametros={"recurso": "operador_maquina", "quantidade": 2, "semanas": [8,9,10]})
  → Returns: viavel=true, delta_custo=+R$50k, margem=9.1% (VERDE), persisted=false

Engineer: "E se eu estender 2 semanas em vez disso?"
  → Claude calls: simular_impacto_replan(tipo="extend_deadline", parametros={"semanas": 2})
  → Returns: viavel=true, delta_custo=+R$596k (indiretos), margem=7.8% (VERDE), persisted=false

Engineer: "Quanto dos R$596k são indiretos?"
  → Claude calls: simular_impacto_indiretos(project_id, delta_semanas=2)
  → Returns: indiretos delta breakdown by category

Engineer: "Prefiro adicionar os operadores. Aplica."
  → [This is where replan goes from simulation → commitment]
  → Claude calls: avancar_pipeline(project_id, skill_id="01A-declarar-recursos",
                    inputs={"pool_overrides": {"operador_maquina": 5}})
  → Then: avancar_pipeline(project_id, skill_id="03B-alocacao-recursos")
  → Then: avancar_pipeline(project_id, skill_id="06-consolidar")
  → consultar_status → confirms viavel=true, margem VERDE

Engineer: "Aprovado."
  → Claude confirms irreversibility → aprovar_versao(project_id)
```

---

## Part III — Gap Closure Priority

### P0 — Fixes Required Before MCP is Usable

**`explorar_alternativas` persistence mismatch:**

Current behavior: creates N new versions per call. An engineer asking "show me 3 scenarios" creates 3 permanent versions in storage, polluting the version history.

Proposed fix: add `persist=False` parameter (default). When False, uses a temp directory and discards after comparison.

```python
def explorar_alternativas(
    project_id: str,
    n_variations: int = 3,
    persist: bool = False,   # NEW: default False = simulation only
    ...
)
```

---

### P1 — Required for Core Use Case (I4+I5)

| Operation | Implements | Effort |
|-----------|-----------|--------|
| `consultar_viabilidade_prazo` | I4 at S2/S3 | Low — reads canonical |
| `identificar_gargalos_recurso` | I4 at S3 | Low — reads `conflitos_pico` |
| `simular_impacto_replan` | I5 at S2/S3 | Medium — virtual copy + recalc |
| `simular_impacto_indiretos` | I5 at S2/S3 | Low — pure arithmetic |

---

### P2 — Required for Complete Coverage

| Operation | Implements | Effort |
|-----------|-----------|--------|
| `sugerir_eap` | I1 at S0 | Low — reads templates |
| `listar_cpus` | I1 at S0 | Low — reads catalog |
| `nova_versao` | I3 at S4 | Low — wraps `project.new_version()` |

---

## Summary

**Two findings with immediate consequence:**

1. **`explorar_alternativas` silently persists.** It creates real versioned copies per scenario. This must be fixed (add `persist=False` default) before the tool is safe to use interactively.

2. **The I4 intent (Diagnose) has zero implemented operations.** An engineer asking "what's wrong with my plan?" has no MCP operation to call. `consultar_viabilidade_prazo` and `identificar_gargalos_recurso` are the minimum to make S3 actionable.

**The replan surface requires three new operations** (`consultar_viabilidade_prazo`, `identificar_gargalos_recurso`, `simular_impacto_replan`) plus one arithmetic helper (`simular_impacto_indiretos`). Together they cover the full (S2/S3 × I4/I5) quadrant which is the confirmed primary use case.

## Definition of Done

- [x] Use case space fully mapped: `PROJECT_STATE (S0–S4) × ENGINEER_INTENT (I1–I6)` coverage matrix documented
- [x] `explorar_alternativas` persistence fixed: `persist=False` default — no phantom versions created on interactive what-if calls
- [x] `consultar_viabilidade_prazo` (S2/S3 × I4): reads `cronograma` vs. `data_termino`; returns `viavel`, `semanas_excedentes`, critical-path activities
- [x] `identificar_gargalos_recurso` (S3 × I4): reads `conflitos_pico`; returns peak-week conflicts with resource-level recommendation (BUY or SHIFT)
- [x] `simular_impacto_replan` (S2/S3 × I5): operates on virtual canonical copy (`persisted=False`); supports `extend_deadline`, `add_resource`, `add_teams`, `reduce_scope`; returns baseline vs. simulated delta
- [x] `simular_impacto_indiretos` (S2/S3 × I5): pure arithmetic from ADR-009 model; returns per-category indirect cost delta by week range
- [x] `sugerir_eap` (S0 × I1): reads templates catalog; returns EAP draft without requiring cpu_ids from caller
- [x] `listar_cpus` (S0/S1 × I1): reads catalog; returns matching CPUs by filter
- [x] State transitions documented: `S0→S1→S2/S3→S4` and replan cycle `S3→(simulate)→S2/S3`
- [x] `nova_versao` (S4 × I3): fork approved version into new S1 for revision
- [x] `consultar_saude_catalogo`: catalog health MCP tool