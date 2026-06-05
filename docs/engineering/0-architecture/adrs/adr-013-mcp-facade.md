# ADR-013: MCP Server as Business-Operation Facade over Skill Pipeline

**Status:** Implementado  
**Date Decided:** 2026-05-02  
**Date Implemented:** 2026-05-02  
**Implementers:** mcp_server/server.py, mcp_server/__init__.py  
**Context:** Concilium has two distinct interfaces:

```
CLI (concilium run, concilium schedule weekly, ...)
  → Used by: software engineer, debugging, CI
  → Granularity: skill-level (explicit skill IDs)
  → Audience: technical

MCP Server (FastMCP over stdio, Claude Desktop)
  → Used by: AGIS engineer exploring project scenarios
  → Granularity: business operation level
  → Audience: domain expert, not software engineer
```

The question raised: **are skills the right abstraction for the MCP interface, or does MCP require a different level of abstraction?**

### The Answered Question

The answer is already in `concilium/mcp_server/__init__.py`:

```python
"""
Expõe operações de negócio de alto nível ao Claude Desktop, em vez de
expor skills granulares. Skills permanecem implementação interna,
orquestradas via Runtime.
"""
```

This ADR formalizes **why** this is correct, **what** the boundary means in practice, and **how** future operations must be designed.

### Primary Use Case (Confirmed)

The dominant usage pattern is:

> **Engineer via Claude Desktop exploring scenarios** — not batch pipeline execution.

Typical interactions:
```
"Qual o impacto de usar 3 equipes na pavimentação?"
"Qual cenário tem melhor margem dentro do orçamento X?"
"O cronograma respeita o prazo contratual?"
"Onde estão os gargalos de recurso nas semanas 8–10?"
"Se estender 2 semanas, quanto aumentam os indiretos?"
```

None of these map 1:1 to a skill. They are **business queries** that may internally invoke one or several skills.

---

## Decision

### D1 — Two-Layer Architecture (Confirmed)

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: MCP FACADE (business operations)                  │
│                                                             │
│  iniciar_orcamento    → business intent: "start project"    │
│  avancar_pipeline     → business intent: "progress"         │
│  explorar_alternativas → business intent: "what-if"         │
│  consultar_status     → business intent: "where am I?"      │
│  aprovar_versao       → business intent: "commit"           │
│  [future operations]  → always at business intent level     │
│                                                             │
└──────────────────────┬──────────────────────────────────────┘
                       │ invokes internally
┌──────────────────────▼──────────────────────────────────────┐
│  LAYER 1: SKILL PIPELINE (implementation)                   │
│                                                             │
│  00-escopo → 00A → 00B → 01 → 01A → 02 → 02B →            │
│  03 → 03A → 03B → 03C → 04 → 05 → 06 → 07                  │
│                                                             │
│  Skills: pure functions on canonical model                  │
│  Runtime: DAG execution, validation, persistence            │
│  CLI: direct skill access (developer/debug only)            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Rule:** MCP tools NEVER expose skill IDs to Claude. Claude doesn't know `02B-cronograma-semanal` exists — it knows `explorar_alternativas` exists.

---

### D2 — What Makes a Good MCP Operation

An MCP operation is correct if it satisfies:

```
1. Business-complete: Returns a meaningful answer to a business question
   ✅ "iniciar_orcamento" → returns project created + first results
   ❌ "run_skill_00_escopo" → returns canonical JSON (meaningless to engineer)

2. Idempotent or explicitly destructive:
   ✅ "consultar_status" → safe to call anytime, always returns current state
   ✅ "aprovar_versao" → explicit, documented as irreversible, requires confirmation
   ❌ Silently modifying state without clear signal to Claude

3. Self-describing for Claude:
   ✅ Docstring explains WHEN to use the tool, not HOW it works internally
   ✅ Returns human-readable next steps ("nota": "Próximo passo: avancar_pipeline")
   ❌ Returns raw canonical model dump

4. Absorbs implementation complexity:
   ✅ "avancar_pipeline" detects next pending skill automatically
   ✅ "iniciar_orcamento" runs 00-escopo internally without exposing it
   ❌ Requiring Claude to track which skills were run and in what order
```

---

### D3 — Current Operations and Their Business Intent

| MCP Tool | Business Intent | Skills Invoked Internally |
|---|---|---|
| `listar_contextos` | "What postures are available?" | None (config read) |
| `listar_projetos` | "What projects exist?" | None (storage read) |
| `iniciar_orcamento` | "Start a new project from scope" | 00-escopo |
| `avancar_pipeline` | "Progress to next planning step" | Next pending in DAG |
| `explorar_alternativas` | "What if I change parameters?" | ScenarioRunner (multiple skills) |
| `consultar_status` | "Where am I in the process?" | None (log + canonical read) |
| `aprovar_versao` | "Commit this version as final" | approve() (storage lock) |

---

### D4 — Planned Operations (Future, Same Principle)

These operations are needed for the confirmed use case (scenario exploration) and must follow the same rule: business intent, not skill exposure.

#### Exploração de Restrições

```python
@server.tool()
def consultar_viabilidade_prazo(project_id: str) -> dict:
    """
    Responde: "O cronograma atual respeita o prazo contratual?"

    Internally:
      - Loads canonical.cronograma_semanal
      - Runs constraint validation (VAL-SCHED-WEEKLY-03)
      - Returns: feasible?, delay_weeks, critical_path_slack
    """
```

```python
@server.tool()
def identificar_gargalos_recurso(project_id: str, semana_inicio: int, semana_fim: int) -> dict:
    """
    Responde: "Onde estão os gargalos de recurso no período X–Y?"

    Internally:
      - Loads canonical.equipes_alocadas + pool
      - Runs ResourcePoolValidator for given range
      - Returns: weeks with >90% utilization, specific resource types
    """
```

#### Simulação de Impacto

```python
@server.tool()
def simular_impacto_replan(
    project_id: str,
    tipo: str,           # "extend_deadline" | "add_teams" | "reduce_scope"
    parametros: dict,    # tipo-specific: {"semanas": 2} or {"equipes": 1, "atividade": "PAVIM-01"}
) -> dict:
    """
    Responde: "Se eu fizer X, qual é o impacto financeiro e de prazo?"

    Internally:
      - Creates virtual copy of canonical
      - Applies parametros to cronograma_semanal (ADR-006 replan candidate)
      - Recalculates Skills 03 + 05 on virtual copy
      - Returns: delta_custo, delta_prazo, nova_margem, feasible?
      - Does NOT persist (simulation only)
    """
```

```python
@server.tool()
def simular_impacto_indiretos(project_id: str, delta_semanas: int) -> dict:
    """
    Responde: "Se estender N semanas, quanto aumentam os indiretos?"

    Internally:
      - Reads canonical.indiretos (ADR-009)
      - Recalculates permanência-based categories with new duration
      - Returns: delta per category (TOP, ADM, LAB, QSMS), total delta, MOB unchanged
    """
```

#### Catálogo e Saúde

```python
@server.tool()
def consultar_saude_catalogo(dominio: str, jurisdicao: str = "BR") -> dict:
    """
    Responde: "O catálogo cobre o domínio deste projeto?"

    Internally:
      - Runs CatalogHealthReport (ADR-012)
      - Returns: cobertura_pct, gaps_criticos, status (COMPLETO/ADEQUADO/PARCIAL)
    """
```

---

### D5 — What MCP Operations Must NOT Do

```
❌ Expose skill IDs in parameters or return values
   # Wrong:
   def avancar_pipeline(skill_id="02B-cronograma-semanal"):  # skill ID visible to Claude

   # Correct:
   def avancar_pipeline(skill_id=None):  # auto-detect; skill_id is implementation detail

❌ Return raw canonical JSON
   # Wrong:
   return canonical.model_dump()  # Claude gets 500-line JSON, can't summarize it

   # Correct:
   return {
       "margem_pct": resultado.margem_pct,
       "status": resultado.status_margem,
       "proxima_acao": "aprovar_versao" if resultado.status_margem == "VERDE" else "explorar_alternativas"
   }

❌ Require Claude to manage state between calls
   # Wrong: Claude must remember which skills ran and pass that to next call

   # Correct: avancar_pipeline auto-detects from invocations.log (already implemented)

❌ Silently persist irreversible changes
   # Wrong: Silently approve + lock files without confirmation signal

   # Correct (already implemented): aprovar_versao docstring says
   # "Claude Desktop deve confirmar com o usuário antes de invocar"
```

---

### D6 — CLI Remains for Developer Use

CLI retains full skill-level granularity. This is correct and necessary:

```bash
# Developer debugging: run specific skill with explicit inputs
concilium run 02B-cronograma-semanal --project lote09 --inputs '{"algorithm": "MILP"}'

# Developer inspection: skill graph
concilium skills export --format mermaid --group-by-phase

# Developer testing: run single skill in isolation
concilium run 03C-validar-compartilhamento --project lote09
```

**Rule:** The CLI is the developer interface. The MCP server is the business user interface. They serve different audiences and must not converge.

---

### D7 — Exploration vs. Batch: Both Supported

The two regimes coexist without conflict:

```
Regime 1: BATCH (complete planning)
  Engineer: "Execute o planejamento completo do Lote 09"
  Claude: calls iniciar_orcamento → avancar_pipeline × N → consultar_status
  Result: complete canonical, ready for aprovar_versao

Regime 2: EXPLORATION (scenario what-if)
  Engineer: "E se eu usar 3 equipes na pavimentação semana 8?"
  Claude: calls simular_impacto_replan(tipo="add_teams", parametros={...})
  Result: delta cost + new margin, WITHOUT persisting
```

Key: `simular_*` operations work on **virtual copy of canonical**, never persisting. Only `avancar_pipeline` and `aprovar_versao` write to storage.

This maps exactly to the Steuerung (planning) vs Regelung (execution) separation: all current operations are Steuerung — no execution feedback loop in scope.

---

## Interfaces / Implementation

### Operation Design Template

Every new MCP operation must follow this template:

```python
@server.tool()
def nome_operacao(
    project_id: str,
    # Business-level parameters only (not skill IDs, not canonical fields)
) -> dict[str, Any]:
    """
    [One sentence: what business question does this answer?]

    Use when: [when should Claude invoke this?]

    Args:
        project_id: [description]
        [param]: [business-level description, not implementation detail]

    Returns:
        [Business-readable fields with clear names]
        [Always include: "proxima_acao" hint for Claude]
    """
    # 1. Load project + canonical
    store = _project(project_id)
    rt = _runtime()

    # 2. Run internal computation (skills, validators, calculators)
    # Skills NEVER mentioned in docstring or return value
    result = rt.run_skill("XX-internal-skill", store, ...)

    # 3. Return business summary, NOT canonical dump
    return {
        "resultado_chave": ...,
        "interpretacao": "VERDE / AMARELO / VERMELHO",
        "proxima_acao": "nome_da_proxima_operacao ou None se concluido",
        "nota": "Texto legível para Claude resumir ao usuário",
    }
```

---

## Validation

**How to test that an MCP operation is at the right level:**

Give the operation signature to a civil engineer (not software engineer) unfamiliar with Concilium internals. Ask: "Does this make sense to you?"

```
✅ iniciar_orcamento(nome, contexto_id, tipo_obra, localizacao, eap)
   → Engineer: "Yes, I'm starting a budget for a project"

✅ simular_impacto_replan(tipo="extend_deadline", parametros={"semanas": 2})
   → Engineer: "Yes, I want to know what happens if I extend by 2 weeks"

❌ run_skill(skill_id="02B-cronograma-semanal", inputs={"algorithm": "MILP"})
   → Engineer: "What is a skill? What is MILP?"
```

---

## Related ADRs / Code

- **ADR-006** (Replanning): `simular_impacto_replan` implements Steuerung-only replan
- **ADR-009** (Indirect Costs): `simular_impacto_indiretos` uses permanência model
- **ADR-012** (Catalog Completeness): `consultar_saude_catalogo` exposes health report
- **`server.py`**: Current implementation (7 operations, all correct by this ADR)
- **`commands_run.py`**: CLI skill-level access (correct for developer use)
- **`ScenarioRunner`**: Internal implementation of `explorar_alternativas`

---

## Definition of Done

### Already implemented (server.py) ✅
- [x] `listar_contextos`
- [x] `listar_projetos`
- [x] `iniciar_orcamento`
- [x] `avancar_pipeline` (auto-detects next skill)
- [x] `explorar_alternativas` (wraps ScenarioRunner)
- [x] `consultar_status`
- [x] `aprovar_versao` (with irreversibility warning)

### To implement (future sprints)
- [x] `consultar_viabilidade_prazo` (deadline feasibility check)
- [x] `identificar_gargalos_recurso` (resource peak detection)
- [x] `simular_impacto_replan` (virtual replan, no persistence)
- [x] `simular_impacto_indiretos` (permanência delta calculator)
- [ ] `consultar_saude_catalogo` (ADR-012 health report)

### Architectural invariants (never break)
- [ ] No skill IDs in MCP operation signatures or return values
- [ ] No raw canonical JSON in return values
- [ ] Simulation operations never persist
- [ ] `aprovar_versao` always documents irreversibility in docstring
- [ ] CLI retains full skill-level access (separate audience)

---

## Summary

**Decision:** MCP server exposes **business operations** to Claude Desktop. Skills remain **internal implementation** orchestrated by Runtime.

```
Engineer asks: "What if I extend the deadline 2 weeks?"
Claude calls:  simular_impacto_replan(tipo="extend_deadline", parametros={"semanas": 2})
               ↓ internally
               Virtual canonical copy
               + recalc 02B (schedule)
               + recalc 05 (indiretos, ADR-009)
               + constraint validation (ADR-006)
Claude answers: "Extending 2 weeks increases indirect costs by R$ 34k
                and resolves the resource bottleneck in weeks 8–10.
                New margin: 8.2% (VERDE). Recommend proceeding."
```

The engineer never sees `02B-cronograma-semanal`. Claude never needs to understand the DAG. Skills remain free to change internally without affecting the MCP contract.

**This is the correct architecture for the confirmed use case: engineer via Claude Desktop exploring scenarios.**