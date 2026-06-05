# ADR-014: MCP Interaction Surface: Input/Output Contract

**Status:** Implementado  
**Date Decided:** 2026-05-02  
**Date Implemented:** 2026-05-02  
**Implementers:** mcp_server/server.py (Tools 1–7, 8–13)  
**Context:** ADR-013 established the two-layer architecture (skills internal, MCP exposes business operations). This ADR maps the **concrete interaction surface**: exactly what Claude must provide as payload for each operation, what the server returns, and where friction exists today between what Claude can infer and what must be explicitly requested from the engineer.

---

## Surface Map

### 1. `listar_contextos`

**Claude provides:**
```python
listar_contextos()  # no parameters
```

**Server returns:**
```json
{
  "contextos": [
    {
      "id": "agis",
      "nome": "AGIS — MendesLobo Construtora",
      "descricao": "Perfil rodovias/ferrovias CE, catálogo calibrado Lote 09/10",
      "perfil_id": "agis",
      "catalogo_id": "agis"
    }
  ],
  "config_root": "/path/to/config"
}
```

**Friction:** None. Read-only, no engineer input needed.

---

### 2. `listar_projetos`

**Claude provides:**
```python
listar_projetos()  # no parameters
```

**Server returns:**
```json
{
  "projetos": [
    {
      "id": "a3f2c1d0-...",
      "nome": "Lote 09 CE",
      "contexto_id": "agis",
      "current_version": "v3",
      "versoes": ["v1", "v2", "v3"]
    }
  ]
}
```

**Friction:** None. Read-only.

---

### 3. `iniciar_orcamento`

This is the most complex operation. Engineer provides **all project definition** in one call.

**Claude provides:**
```python
iniciar_orcamento(
    nome="Lote 09/10 CE",
    contexto_id="agis",                    # from listar_contextos
    tipo_obra="terraplenagem",             # enum: "terraplenagem" | "pavimentacao" | "saneamento"
    localizacao="Aracoiaba, CE",
    coordenadas_lat=-4.3622,
    coordenadas_lng=-38.7392,
    data_inicio="2026-06-01",              # ISO date
    data_termino="2026-12-31",
    eap=[
        {
            "item_id": "eap-01",           # engineer-assigned ID
            "ordem": 1,                    # sequence position
            "cpu_id": "ESCO-CARGA-1CAT-DMT2000",  # from catalog
            "descricao": "Escavação 1ª categoria",
            "unidade": "m3",
            "quantitativo": 80000.0,       # float > 0
            "origem_template": True        # True if from template suggestion
        },
        # ... more items
    ],
    dias_semana=6,                         # default: 6
    horas_dia=8,                           # default: 8
)
```

**Server returns:**
```json
{
  "project_id": "a3f2c1d0-uuid",
  "version": "v1",
  "skills_executadas": [
    {"skill": "00-escopo", "status": "OK", "validacoes": []}
  ],
  "proxima_skill_sugerida": "01-praticabilidade",
  "nota": "Projeto criado com escopo. Próximo passo: avancar_pipeline para calcular praticabilidade climática."
}
```

**Friction points — what Claude cannot infer:**

| Campo | Problema | Solução |
|-------|----------|---------|
| `eap[].cpu_id` | Claude doesn't know which CPU codes are valid | Must call `listar_contextos` first; catalog IDs must be pre-loaded or engineer provides them |
| `eap[].quantitativo` | Engineering quantity — must come from project documents | Claude asks engineer or reads uploaded quantity survey |
| `coordenadas_lat/lng` | Must be site-specific | Claude can geocode from `localizacao` string via web search |
| `tipo_obra` | Enum with only 3 values | Claude can infer from EAP description most of the time |

**Missing operation (gap):** `sugerir_eap(tipo_obra, contexto_id)` — returns template CPU list for Claude to present to engineer before calling `iniciar_orcamento`. Avoids Claude guessing CPU IDs.

---

### 4. `avancar_pipeline`

**Claude provides:**
```python
avancar_pipeline(
    project_id="a3f2c1d0-uuid",   # from iniciar_orcamento or listar_projetos
    skill_id=None,                  # None = auto-detect next pending
    inputs={}                       # skill-specific inputs (see below)
)
```

**Skill-specific inputs that may be required:**

```python
# For 01-praticabilidade:
inputs={"ano_referencia": 2024}    # optional, defaults to current year

# For 02-cronograma (monthly):
inputs={}                           # no required inputs

# For 03-equipes-diretas:
inputs={}                           # no required inputs (uses CPU catalog)

# For 02B-cronograma-semanal (via commands_schedule.py):
inputs={"algorithm": None, "top_n": 3}  # algorithm=None → auto-select
```

**Server returns:**
```json
{
  "skill_executada": "01-praticabilidade",
  "status": "OK",
  "validacoes": [],
  "version": "v1"
}
```

On precondition error:
```json
{
  "skill_executada": "03-equipes-diretas",
  "status": "ERRO_PRECONDICAO",
  "erro": "Skill '02-cronograma' deve ser executada antes de '03-equipes-diretas'",
  "version": "v1"
}
```

On pipeline complete:
```json
{
  "info": "Pipeline completo. Use aprovar_versao para congelar."
}
```

**Friction:** `skill_id=None` auto-detects from the hardcoded order in `avancar_pipeline`. This order only covers skills `00–07`. Skills `00A`, `00B`, `01A`, `02B`, `03A`, `03B`, `03C` are **not in the auto-detect list** — they must be invoked explicitly via `skill_id`. This is a gap.

---

### 5. `explorar_alternativas`

**Claude provides:**
```python
# Option A: auto-generate N variations
explorar_alternativas(
    project_id="a3f2c1d0-uuid",
    n_variations=3
)

# Option B: explicit delta multipliers
explorar_alternativas(
    project_id="a3f2c1d0-uuid",
    custo_deltas=[0.95, 1.0, 1.05],       # -5%, 0, +5%
    duracao_deltas=[0.90, 1.0, 1.10],
    equipe_deltas=[0.80, 1.0, 1.20]
)
```

**Server returns:**
```json
{
  "cenarios_executados": 3,
  "matriz": {
    "resumo": {
      "melhor_cenario": "cenario-2",
      "melhor_cenario_descricao": "...",
      "margem_max": 9.2,
      "custo_spread_pct": 12.5
    },
    "cenarios": [
      {
        "nome": "cenario-1",
        "custo_total": 4200000,
        "margem_pct": 7.1,
        "status_margem": "VERDE"
      }
    ]
  }
}
```

**Friction:** Deltas are **multipliers on the whole project** (custo × delta, duração × delta, equipe × delta). This is coarse. Engineer may want to vary **a specific activity** (e.g., "add 1 team to PAVIM-01"). The current interface doesn't support activity-level deltas — gap for `simular_impacto_replan`.

---

### 6. `consultar_status`

**Claude provides:**
```python
consultar_status(project_id="a3f2c1d0-uuid")
```

**Server returns:**
```json
{
  "project_id": "a3f2c1d0-uuid",
  "nome": "Lote 09 CE",
  "contexto_id": "agis",
  "current_version": "v3",
  "versoes": ["v1", "v2", "v3"],
  "invocations": [
    {"skill": "00-escopo", "status": "OK", "ts": "2026-05-01T10:00:00Z"},
    {"skill": "01-praticabilidade", "status": "OK", "ts": "2026-05-01T10:01:00Z"}
  ],
  "resultado_atual": {
    "preco_venda": 5200000.0,
    "custo_total": 4750000.0,
    "margem_pct": 0.0865,
    "status_margem": "VERDE"
  }
}
```

**Friction:** `resultado_atual` only appears if `06-consolidar` was run. Claude must handle `None` gracefully if pipeline is incomplete.

---

### 7. `aprovar_versao`

**Claude provides:**
```python
aprovar_versao(
    project_id="a3f2c1d0-uuid",
    version=None    # None = current version
)
```

**Server returns:**
```json
{
  "project_id": "a3f2c1d0-uuid",
  "version": "v3",
  "status": "APROVADO"
}
```

**Friction:** Operation is irreversible (files become read-only). Claude's docstring says "deve confirmar com o usuário antes de invocar" — but there is no enforcement mechanism in the protocol. Claude must implement the confirmation step in natural language before calling this tool.

---

## Gaps: What's Missing from the Surface

### Gap 1 — `sugerir_eap(tipo_obra, contexto_id)`

Without this, Claude must ask the engineer for each `cpu_id` manually, or guess from template data it may not have loaded.

```python
@server.tool()
def sugerir_eap(tipo_obra: str, contexto_id: str) -> dict:
    """
    Retorna serviços sugeridos para o tipo de obra no contexto dado.
    Claude usa para apresentar opções ao engenheiro antes de iniciar_orcamento.
    """
    # Returns template CPUs with descriptions, units, typical quantities
    return {
        "tipo_obra": tipo_obra,
        "servicos_sugeridos": [
            {
                "cpu_id": "ESCO-CARGA-1CAT-DMT2000",
                "descricao": "Escavação, carga, transporte — 1ª categoria DMT até 2000m",
                "unidade": "m3",
                "obrigatoriedade": "essencial"
            },
            ...
        ]
    }
```

---

### Gap 2 — `avancar_pipeline` doesn't cover new skills

The auto-detect order in `server.py`:
```python
order = ["00-escopo", "01-praticabilidade", "02-cronograma",
         "03-equipes-diretas", "04-planejamento-bdi", "05-indiretos",
         "06-consolidar", "07-adapter-saida"]
```

Missing from auto-detect:
- `00A-atividades`
- `00B-sequenciamento`
- `01A-declarar-recursos`
- `02B-cronograma-semanal`
- `03A-derivar-requisitos`
- `03B-alocacao-recursos`
- `03C-validar-compartilhamento`

These must be called explicitly via `skill_id=`. This is **fine for now** (they're v2.5 skills) but the auto-detect list must be updated as new skills are implemented.

---

### Gap 3 — Activity-level simulation

`explorar_alternativas` only supports whole-project multipliers. For the confirmed use case ("what if I add 1 team to activity X in week 8?") we need:

```python
@server.tool()
def simular_impacto_replan(
    project_id: str,
    tipo: str,        # "extend_deadline" | "add_teams" | "reduce_scope"
    parametros: dict  # {"semanas": 2} | {"atividade_id": "PAVIM-01", "equipes": 1, "semanas": [8,9]}
) -> dict:
    """Simula impacto sem persistir. Retorna delta_custo, delta_prazo, nova_margem."""
```

---

### Gap 4 — No read access to catalog

Claude cannot answer "which CPU IDs are valid for saneamento?" without `sugerir_eap` or a catalog query tool. Engineer is forced to know CPU codes from memory or external reference.

```python
@server.tool()
def listar_cpus(contexto_id: str, tipo_obra: str | None = None) -> dict:
    """Lista CPUs disponíveis no catálogo, opcionalmente filtradas por tipo de obra."""
```

---

## Interaction Flow: Typical Session

```
Claude Desktop — Engineer: "Inicia um orçamento de terraplenagem em Aracoiaba"

Step 1: Claude calls listar_contextos()
  → learns "agis" is available

Step 2: Claude calls sugerir_eap("terraplenagem", "agis")  [GAP — not yet implemented]
  → gets suggested CPUs with descriptions
  → presents to engineer: "Encontrei 3 serviços típicos: Escavação 1ª cat, Compactação aterro, Regularização subleito. Quais quantitativos?"

Step 3: Engineer provides quantities
  → Claude calls iniciar_orcamento(eap=[...with quantitativos...])
  → project_id = "a3f2..."

Step 4: Claude calls avancar_pipeline(project_id) × N (auto-detect)
  → Runs: 01-praticabilidade → 02-cronograma → 03-equipes-diretas
           → 04-planejamento-bdi → 05-indiretos → 06-consolidar

Step 5: Claude calls consultar_status(project_id)
  → "Margem: 8.65% (VERDE). Custo total: R$ 4.75M. Preço de venda: R$ 5.2M"

Engineer: "E se eu reduzir 10% no custo de equipe?"

Step 6: Claude calls explorar_alternativas(project_id, equipe_deltas=[0.90, 0.95, 1.0])
  → "Cenário -10% equipe: margem sobe para 9.8% (VERDE). Custo R$ 4.3M."

Engineer: "Aprovado."

Step 7: Claude confirms: "Vou aprovar a versão v1. Esta ação é irreversível. Confirma?"
  → Engineer: "Sim"
  → Claude calls aprovar_versao(project_id)
```

---

## Claude's Resolution Rules

To avoid asking the engineer for data it can resolve itself:

| Data | Claude resolves how |
|------|---------------------|
| `contexto_id` | Always call `listar_contextos` first; use first available if only one |
| `project_id` | Always call `listar_projetos` if not in conversation context |
| `coordenadas` | Geocode from `localizacao` via web search |
| `tipo_obra` | Infer from EAP description (terraplenagem/pavimentação/saneamento) |
| `cpu_id` | Call `sugerir_eap` (when implemented); never guess |
| `quantitativo` | Always ask engineer — this is engineering measurement |
| `data_inicio/termino` | Ask engineer — contract-defined |
| `skill_id` in avancar_pipeline | Leave `None`; let server auto-detect |
| Version for aprovar_versao | Leave `None`; server uses current |

---

## Definition of Done

### Immediate (gaps in current server.py)
- [x] `sugerir_eap(tipo_obra, contexto_id)` — template CPU list with descriptions
- [x] `listar_cpus(contexto_id, tipo_obra=None)` — catalog query
- [x] Update `avancar_pipeline` auto-detect order to include v2.5 skills
- [x] Explicit return of `proxima_sugerida` hint in `avancar_pipeline`

### Planned operations (ADR-013)
- [ ] `simular_impacto_replan` — activity-level simulation
- [ ] `simular_impacto_indiretos` — permanência delta
- [ ] `consultar_viabilidade_prazo` — deadline feasibility
- [ ] `identificar_gargalos_recurso` — resource peak detection
- [ ] `consultar_saude_catalogo` — catalog health (ADR-012)

---

## Summary

The interaction surface has **three types of data**:

```
1. System-resolvable (Claude calls listar_* first):
   contexto_id, project_id, version

2. Inferable (Claude resolves without asking):
   coordenadas (geocode), tipo_obra (from EAP description), skill_id (auto-detect)

3. Engineer-required (Claude must always ask):
   quantitativo, cpu_id (until sugerir_eap exists), data_inicio/termino
```

The biggest friction today is `cpu_id` in `iniciar_orcamento.eap`: Claude cannot know valid catalog codes without a catalog query tool. `sugerir_eap` is the highest-priority gap to close.