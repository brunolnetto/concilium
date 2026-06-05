# ADR-016 — Resource Sharing Taxonomy: Exclusive, Shared, and Concurrent Insumos

**Title:** Three-Class Resource Model for Accurate Pool Constraints and Cost Attribution  
**Status:** Implementado  
**Date:** 2026-05-02  
**Date Implemented:** 2026-05-02  
**Implementers:** models/catalogo.py (ClasseInsumo, ClasseCompartilhamento), skills/03B-alocacao-recursos, skills/03C-validar-compartilhamento  
**Decision Maker:** Engineering Lead + Operations (Concilium Scheduling & Costing)

---

## Context

ADR-005 (Team Composition) treats all pool resources uniformly:

```
pool["operador_maquina"] = 3
pool["topografo"] = 2

constraint: sum(demand_week) ≤ pool[resource]
```

This is correct for `operador_maquina` (one operator = one machine = one activity) but wrong for `topografo` (one surveyor can cover multiple simultaneous fronts). The uniform model causes two errors:

**Error 1 — Overconstrained scheduling:** A project with 3 simultaneous activities is blocked because `topografo_demand = 3 > pool["topografo"] = 2`, even though 2 surveyors can physically cover 3 fronts.

**Error 2 — Overcounted cost:** When two activities share an encarregado de frente, the cost model bills the encarregado twice — once per CPU — instead of once shared across both.

**Root cause:** The CPU model embeds insumos at full-dedication rates, but some insumos are structurally shared across activities. The direct/indirect split (ADR-009) partially captures this at project level, but does not model it at the insumo-within-CPU level.

---

## Decision

We formalize a **three-class resource taxonomy** applied to every insumo in the catalog:

### D1 — Three Classes

#### Class A — Exclusive-Dedicated (`exclusivo_dedicado`)

```
Definition: One instance serves exactly one activity for the full period it is active.
            Cannot be shared without interrupting the activity.

Examples:
  Escavadeira hidráulica 38T
  Rolo compactador
  Motoniveladora
  Operador de máquina
  Motorista de caminhão basculante (while truck is on haul cycle)

Pool constraint:
  demand_week = sum(instances allocated to active activities this week)
  constraint:  demand_week ≤ pool[resource]

Cost attribution:
  Full cost to the activity for every week it is active.
  No pro-rating.
```

#### Class B — Exclusive-Shareable (`exclusivo_compartilhavel`)

```
Definition: One instance serves one activity at a time, but can alternate
            between activities within the same period (week).
            Scheduling determines which fraction of the period each activity gets.

Examples:
  Caminhão-pipa (serves escavação OR compactação, not both simultaneously)
  Equipamento de ensaio móvel
  Motosserra (serves desmatamento A OR desmatamento B)
  Ajudante geral (can shift between two adjacent activities)

Pool constraint:
  demand_week = sum(fração_uso × instances per activity)
  constraint:  demand_week ≤ pool[resource]

  Where fração_uso ∈ (0, 1]: the proportion of the week this activity
  needs this resource. Defined in CPU composition.

Cost attribution:
  fração_uso × custo_unitario attributed to each activity.
  Total across activities ≤ 1.0 × custo_unitario per instance.
```

#### Class C — Concurrent-Shareable (`concorrente_compartilhavel`)

```
Definition: One instance can serve N activities simultaneously up to a
            coverage capacity. Presence at the site provides value to all
            active activities at once.

Examples:
  Topógrafo (covers up to 3 simultaneous fronts)
  Técnico de segurança do trabalho (covers all active fronts)
  Laboratorista (runs tests for all active activities)
  Encarregado de frente (covers 2 adjacent activities)
  Mecânico de frota (available to all equipment on site)
  Gerente de contrato (overhead presence for all activities)

Pool constraint:
  effective_capacity = pool[resource] × capacidade_cobertura
  demand_week = count(activities needing this resource this week)
  constraint:  demand_week ≤ effective_capacity

  Where capacidade_cobertura: max simultaneous activities per instance.
  Defined in the insumo catalog entry.

Cost attribution:
  custo_unitario / min(n_atividades_simultaneas, capacidade_cobertura)
  attributed to each activity sharing the resource.
  Total cost remains custo_unitario (no duplication).
```

---

### D2 — Catalog Annotation

Each insumo entry in the catalog gains a `classe_compartilhamento` field:

```yaml
# config/catalogos/agis/insumos.json (extended)

insumos:

  ESCAV-HID-38T:
    descricao: "Escavadeira hidráulica 38T"
    tipo: "equipamento"
    unidade: "h"
    custo_unitario: 278.40
    classe_compartilhamento:
      classe: "exclusivo_dedicado"
      fracao_uso: 1.0        # always 1.0 for Class A
      capacidade_cobertura: 1

  MOTORISTA-CAM-BASC:
    descricao: "Motorista de caminhão basculante"
    tipo: "mao_de_obra"
    unidade: "h"
    custo_unitario: 28.82
    classe_compartilhamento:
      classe: "exclusivo_dedicado"
      fracao_uso: 1.0
      capacidade_cobertura: 1

  CAMINHAO-PIPA:
    descricao: "Caminhão-pipa 10.000L"
    tipo: "equipamento"
    unidade: "h"
    custo_unitario: 95.00
    classe_compartilhamento:
      classe: "exclusivo_compartilhavel"
      fracao_uso: 0.5        # serves 2 activities in alternation
      capacidade_cobertura: 1

  TOPOGRAFO:
    descricao: "Topógrafo"
    tipo: "mao_de_obra"
    unidade: "h"
    custo_unitario: 18000.0  # monthly rate
    classe_compartilhamento:
      classe: "concorrente_compartilhavel"
      fracao_uso: null       # not applicable for Class C
      capacidade_cobertura: 3  # covers up to 3 simultaneous fronts

  TEC-SEGURANCA:
    descricao: "Técnico de segurança do trabalho"
    tipo: "mao_de_obra"
    unidade: "h"
    custo_unitario: 9450.0
    classe_compartilhamento:
      classe: "concorrente_compartilhavel"
      fracao_uso: null
      capacidade_cobertura: 5  # covers all fronts on a typical site

  ENCARREGADO-FRENTE:
    descricao: "Encarregado de frente"
    tipo: "mao_de_obra"
    unidade: "h"
    custo_unitario: 19950.0
    classe_compartilhamento:
      classe: "concorrente_compartilhavel"
      fracao_uso: null
      capacidade_cobertura: 2  # supervises 2 adjacent activities
```

---

### D3 — Revised Pool Constraint (Skill 03B and 03C)

```python
class ResourcePoolValidator:
    """
    Validates team allocations against pool using class-aware constraints.
    Replaces uniform demand summation from ADR-005.
    """

    def validate_week(
        self,
        week: int,
        active_activities: list[str],
        allocations: dict[str, TeamAllocation],
        insumos: dict[str, Insumo],
        pool: dict[str, int],
    ) -> list[ConstraintViolation]:

        violations = []

        # Aggregate demand by class
        demand_A = defaultdict(float)  # Class A: direct sum
        demand_B = defaultdict(float)  # Class B: weighted sum by fração_uso
        demand_C = defaultdict(int)    # Class C: count of activities needing

        for activity_id in active_activities:
            allocation = allocations[activity_id]
            for insumo_id, quantity in allocation.insumos_alocados.items():
                insumo = insumos[insumo_id]
                cls = insumo.classe_compartilhamento

                if cls.classe == "exclusivo_dedicado":
                    demand_A[insumo_id] += quantity

                elif cls.classe == "exclusivo_compartilhavel":
                    demand_B[insumo_id] += quantity * cls.fracao_uso

                elif cls.classe == "concorrente_compartilhavel":
                    # Count activities needing this resource (not instances)
                    if quantity > 0:
                        demand_C[insumo_id] += 1

        # Check Class A: demand ≤ pool
        for insumo_id, demand in demand_A.items():
            capacity = pool.get(insumo_id, 0)
            if demand > capacity:
                violations.append(ConstraintViolation(
                    codigo="VAL-POOL-A-01",
                    insumo_id=insumo_id,
                    semana=week,
                    demanda=demand,
                    capacidade=capacity,
                    excedente=demand - capacity,
                    classe="exclusivo_dedicado",
                    recomendacao=f"BUY {demand - capacity} more or SHIFT activity"
                ))

        # Check Class B: weighted demand ≤ pool
        for insumo_id, weighted_demand in demand_B.items():
            capacity = pool.get(insumo_id, 0)
            if weighted_demand > capacity:
                violations.append(ConstraintViolation(
                    codigo="VAL-POOL-B-01",
                    insumo_id=insumo_id,
                    semana=week,
                    demanda=weighted_demand,
                    capacidade=capacity,
                    excedente=weighted_demand - capacity,
                    classe="exclusivo_compartilhavel",
                    recomendacao=f"Reschedule to avoid overlap or add instance"
                ))

        # Check Class C: activity count ≤ effective capacity
        for insumo_id, n_activities in demand_C.items():
            insumo = insumos[insumo_id]
            instances = pool.get(insumo_id, 0)
            effective_capacity = instances * insumo.classe_compartilhamento.capacidade_cobertura
            if n_activities > effective_capacity:
                violations.append(ConstraintViolation(
                    codigo="VAL-POOL-C-01",
                    insumo_id=insumo_id,
                    semana=week,
                    demanda=n_activities,
                    capacidade=effective_capacity,
                    excedente=n_activities - effective_capacity,
                    classe="concorrente_compartilhavel",
                    recomendacao=f"Add 1 instance covers {insumo.classe_compartilhamento.capacidade_cobertura} more fronts"
                ))

        return violations
```

---

### D4 — Cost Attribution by Class

Direct cost attribution changes for shared resources:

```python
def atribuir_custo_insumo(
    insumo: Insumo,
    n_atividades_simultaneas: int,
    semanas_ativo: int,
) -> float:
    """
    Calculate cost attributed to one activity for a shared insumo.
    """
    cls = insumo.classe_compartilhamento
    custo_base = insumo.custo_unitario * semanas_ativo

    if cls.classe == "exclusivo_dedicado":
        # Full cost to this activity
        return custo_base

    elif cls.classe == "exclusivo_compartilhavel":
        # Pro-rated by fraction of time used
        return custo_base * cls.fracao_uso

    elif cls.classe == "concorrente_compartilhavel":
        # Divided across simultaneous activities, capped at coverage capacity
        effective_share = min(n_atividades_simultaneas, cls.capacidade_cobertura)
        return custo_base / effective_share
```

**Example — Topógrafo serving 3 simultaneous activities:**
```
custo_topografo_mensal = R$ 18.000
n_atividades_simultaneas = 3 (≤ capacidade_cobertura = 3)

custo_atribuido_por_atividade = 18.000 / 3 = R$ 6.000 / atividade
total_cobrado = 3 × 6.000 = R$ 18.000 ✅ (no duplication)

vs. ADR-005 (wrong):
custo_atribuido_por_atividade = 18.000 (full, per CPU)
total_cobrado = 3 × 18.000 = R$ 54.000 ❌ (3× overcount)
```

---

### D5 — Relationship to Direct vs. Indirect Split

This taxonomy resolves a structural ambiguity in ADR-009:

```
PREVIOUS UNDERSTANDING:
  Direct insumos → belong to CPU → charged per activity
  Indirect insumos → permanência → charged once to project

REVISED UNDERSTANDING (ADR-016):
  Direct insumos, Class A → charged fully per activity (unchanged)
  Direct insumos, Class B → charged pro-rata per activity (new)
  Direct insumos, Class C → charged divided per activity (new)
  Indirect insumos (TOP/ADM/LAB/QSMS) → Class C at project level (already correct)
  Indirect insumos (MOB) → one-time (no class applies)
```

Class C direct insumos (encarregado de frente, mecânico, ajudante geral) sit on the boundary between direct and indirect — they appear in CPUs but behave like indirect resources. This is not a classification error: they are legitimately direct (tied to activities) but shared in their consumption pattern.

---

### D6 — Impact on `identificar_gargalos_recurso` (ADR-015)

The MCP operation must distinguish real bottlenecks from false ones:

```python
def classificar_gargalo(violacao: ConstraintViolation) -> dict:
    """
    Translate constraint violation to business-level diagnosis.
    """
    if violacao.classe == "exclusivo_dedicado":
        return {
            "tipo": "gargalo_real",
            "acao": f"Adicionar {violacao.excedente} unidade(s) ao pool ou deslocar atividade",
            "custo_estimado": violacao.excedente * custo_diario_recurso(violacao.insumo_id)
        }

    elif violacao.classe == "exclusivo_compartilhavel":
        return {
            "tipo": "gargalo_sobreposicao",
            "acao": "Redistribuir atividades para evitar sobreposição no mesmo período",
            "custo_estimado": 0  # Free: just reschedule
        }

    elif violacao.classe == "concorrente_compartilhavel":
        return {
            "tipo": "gargalo_cobertura",
            "acao": f"Adicionar 1 instância cobre até {capacidade_cobertura} frentes adicionais",
            "custo_estimado": custo_mensal_recurso(violacao.insumo_id)
        }
```

---

## Validation Rules

| Code | Condition | Severity |
|------|-----------|----------|
| **VAL-POOL-A-01** | Class A demand exceeds pool | ERRO |
| **VAL-POOL-B-01** | Class B weighted demand exceeds pool | ERRO |
| **VAL-POOL-C-01** | Class C activity count exceeds effective capacity | ERRO |
| **VAL-INS-CLASS-01** | Insumo has no `classe_compartilhamento` annotation | AVISO |
| **VAL-INS-CLASS-02** | Class B `fracao_uso` not in (0, 1] | ERRO |
| **VAL-INS-CLASS-03** | Class C `capacidade_cobertura` < 1 | ERRO |
| **VAL-COST-SHARE-01** | Sum of shared cost attributions > 100% of instance cost | ERRO |

---

## Related ADRs

- **ADR-005** (Team Composition): Pool constraint replaces uniform demand sum
- **ADR-009** (Insumos Matrix): Direct/indirect split gains Class dimension
- **ADR-012** (Catalog Completeness): Class annotation is part of catalog completeness
- **ADR-015** (MCP Surface): `identificar_gargalos_recurso` uses class to distinguish bottleneck types
- **ADR-017** (Catalog Lifecycle): Class annotations subject to validation and enrichment

---

## Definition of Done

- [x] `ClasseCompartilhamento` enum + model on `Insumo`
- [x] `ResourcePoolValidator` rewritten with three-class constraint
- [x] `atribuir_custo_insumo()` function with class-aware attribution
- [x] Skill 03B updated to use new pool validator
- [x] 6+ test cases (test_derivar_alocacao_compartilhamento.py)
- [ ] All AGIS catalog insumos annotated with class
- [ ] Skill 03C updated to classify violations by class
- [ ] `identificar_gargalos_recurso` MCP operation translates class to action
- [ ] VAL-POOL-A/B/C-01 validation codes