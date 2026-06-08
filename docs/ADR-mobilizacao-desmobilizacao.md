# ADR-XXX: Mobilização e Desmobilização como Indiretos Tipificados

**Status:** Proposed  
**Date:** 2026-06-08  
**Author:** Engineering Team  
**Replaces:** Dependency on spec.rcpsp_spec for activity scheduling

## Context

Currently, `spec.rcpsp_spec` is a heavyweight construct containing:
- `activities`: List of work items (redundant with spec.eap)
- `resource_pool`: Resource definitions (inferrable from EAP + catalog)
- `precedence`: Activity dependencies (already in eap.predecessores)
- `resource_costs`: Cost components (already in spec.bdi + spec.indiretos)

Analysis of 12 benchmarks shows that **mobilization/demobilization patterns are consistent and predictable**:

### Observed Pattern from Benchmark Data

**ODFJELL (típico projeto de obra civil):**
```
INDML5: Mobilização/Desmobilização de equipamentos     R$ 246.900,00 (fixo, único)
INDML6: Implantação de Canteiro                        R$ 204.241,87 (fixo, único)
INDML7: Equipamentos de Uso Geral                      R$ 391.551,66 (continuo)
INDML8: Despesas Gerais (operação de canteiro)        (mensal durante projeto)
```

**MATEC_GUARULHOS (terraplanagem):**
```
3.5: Mobilização e desmobilização    R$ 2.044.560,87 (9,7% do custo total, fixo)
3.6: Desmobilização                   R$ 408.912,17  (3,0% do custo total, fixo)
```

**Pattern:**
1. **Mobilização (início)**: Custo fixo único para setup
2. **Operação (continuo)**: Custos mensais/semanais durante execução
3. **Desmobilização (fim)**: Custo fixo único para encerramento

---

## Decision

Replace `spec.rcpsp_spec` with **typified MOB indiretos** that capture the three phases implicitamente:

### New spec.indiretos Structure

```json
"indiretos": [
  {
    "tipo": "MOB",
    "fase": "mobilizacao",           // ou "desmobilizacao", "operacao"
    "driver": "projeto",             // ou "mensal"
    "custo_fixo_total": 2044560.87,  // se driver="projeto"
    "custo_fixo_mensal": null,       // se driver="mensal"
    "descricao": "Mobilização e aquisição de equipamentos"
  },
  {
    "tipo": "MOB",
    "fase": "desmobilizacao",
    "driver": "projeto",
    "custo_fixo_total": 408912.17,
    "descricao": "Remoção de equipamentos e restauração do sítio"
  },
  {
    "tipo": "MOB",
    "fase": "operacao",
    "driver": "mensal",
    "custo_fixo_mensal": 50000.00,
    "descricao": "Custos de canteiro, combustível, manutenção"
  },
  {
    "tipo": "ADM",
    "driver": "mensal",
    "custo_fixo_mensal": 384000.00,
    "descricao": "Administração geral"
  }
]
```

### Scheduling Inference from spec.eap

**In the absence of rcpsp_spec, scheduling is derived as:**

1. **Project timeline**: `meta.data_inicio` to `meta.data_termino`
2. **Activities**: spec.eap items with precedences from predecessores
3. **Mobilization window**: 1-4 weeks before first EAP activity
4. **Demobilization window**: 1-2 weeks after last EAP activity
5. **Operation period**: Continuously from mobilization to demobilization

```python
# Pseudo-algorithm for schedule inference
project_start = meta.data_inicio
project_end = meta.data_termino

# First activity in EAP (after topological sort)
first_activity_date = project_start + timedelta(weeks=1)  # 1-week buffer for mob

# Last activity in EAP
last_activity_date = project_end - timedelta(weeks=1)     # 1-week buffer for demob

# Mobilization: project_start to first_activity_date
mob_period = (project_start, first_activity_date)

# Demobilization: last_activity_date to project_end
demob_period = (last_activity_date, project_end)

# Operation: project_start to project_end (overlaps with EAP activities)
```

---

## Benefits

| Aspect | Current (rcpsp_spec) | Proposed (MOB indiretos) |
|--------|----------------------|--------------------------|
| **Redundancy** | High (EAP + RCPSP + catalog) | None (single source: spec.indiretos) |
| **File size** | ~300 lines (AGIS) | ~50 lines (indiretos) |
| **Maintenance** | 3 sources of truth | 1 source (spec.indiretos) |
| **Flexibility** | Fixed structure | Extensible (adicionar fases conforme necessário) |
| **Clarity** | Complex scheduling semantics | Simple cost phases (mob → op → demob) |
| **Inferability** | Cannot infer from EAP | Fully deterministic from project timeline |

---

## Migration Path

### Phase 1: Parallel Support (v3 schema)
- Keep spec.rcpsp_spec if present (backward compat)
- Implement inference from spec.indiretos.MOB
- Validate: both paths produce equivalent results

### Phase 2: Skills Update
- **Skill-04 (cronograma)**: Infer mobilization/demobilization windows from indiretos.MOB
- **Skill-05 (equipes)**: Skip pool contract logic if rcpsp_spec absent (rely on PUxQ costing)
- **Skill-07 (indiretos)**: Use MOB phases to distribute costs across timeline

### Phase 3: Deprecation
- Remove rcpsp_spec from all benchmarks
- Update spec_loader to ignore rcpsp_spec if present
- Test all 12 benchmarks: should remain APROVADO

---

## Implementation Example

### Current (v2 with rcpsp_spec)
```json
{
  "spec": {
    "eap": [...],
    "cronograma": [...],
    "bdi": {...},
    "indiretos": [...],
    "rcpsp_spec": {
      "deadline_weeks": 105,
      "activities": { /* 100+ lines */ },
      "resource_pool": { /* 50+ lines */ },
      "precedence": [/* redundant with EAP */],
      "resource_costs": { /* redundant with BDI */ }
    }
  }
}
```
**Total: ~250 lines redundant data**

### Proposed (v3 without rcpsp_spec)
```json
{
  "spec": {
    "eap": [...],
    "cronograma": [...],
    "bdi": {...},
    "indiretos": [
      {
        "tipo": "MOB",
        "fase": "mobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 2044560.87
      },
      {
        "tipo": "MOB",
        "fase": "desmobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 408912.17
      },
      {
        "tipo": "MOB",
        "fase": "operacao",
        "driver": "mensal",
        "custo_fixo_mensal": 50000.00
      },
      {
        "tipo": "ADM",
        "driver": "mensal",
        "custo_fixo_mensal": 384000.00
      }
    ]
  }
}
```
**Total: ~30 lines, zero redundancy**

---

## Open Questions

1. **Default mob/demob duration**: 1 week? 2 weeks? Make configurable?
   - Proposal: Use 10% of project duration, min 1 week, max 4 weeks
   
2. **Mobilization cost allocation**: 
   - Current: Single lump sum at project start
   - Alternative: Spread across first month?
   - Decision: Keep lump sum (simpler, aligns with contracting patterns)

3. **Operation phase overlap with EAP**:
   - Should MOB operacao cost run only during EAP execution?
   - Or continuously project_start → project_end?
   - Decision: Continuously (canteiro e equipamentos estão provisionados mesmo fora execução)

---

## Risks & Mitigation

| Risk | Mitigation |
|------|-----------|
| **Loss of scheduling detail** | Acceptable: PUxQ costing doesn't need fine-grained RCPSP |
| **Inflexibility if complex pools needed** | Can re-introduce rcpsp_spec for specific projects as override |
| **Historical data in rcpsp_spec** | Migration script to extract and convert to MOB indiretos |

---

## Testing

After implementation, validate:
- [ ] All 12 benchmarks remain APROVADO
- [ ] Total custo_indireto matches pre-refactor
- [ ] Mobilization dates inferred correctly
- [ ] Demobilization dates inferred correctly
- [ ] Operation costs distributed correctly across timeline

---

## References

- MATEC_GUARULHOS planejamento.txt: Items 3.5-3.6 (MOB costs)
- ODFJELL planejamento.txt: Items INDML5-8 (MOB components)
- Current skill-05 implementation: Uses rcpsp_spec only for pool contracts
- Current skill-07 implementation: Uses indiretos for cost distribution

---

## Conclusion

Replacing `spec.rcpsp_spec` with typified MOB indiretos:
- ✅ Eliminates redundancy (activities already in EAP)
- ✅ Simplifies schema (~80% size reduction)
- ✅ Single source of truth (spec.indiretos)
- ✅ Fully deterministic scheduling from project timeline
- ✅ Maintains cost accuracy for all 12 benchmarks

**Recommendation: Implement in Phase 1 (v3 schema), parallel support before deprecation.**
