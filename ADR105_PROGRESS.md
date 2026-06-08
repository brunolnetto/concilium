# ADR-105 Implementation Progress

**Status:** ⏳ In Progress — Phase 2 (Skills Update)  
**Date Started:** 2026-06-08  
**Last Updated:** 2026-06-08

---

## Completion Status by Phase

| Phase | Stage | Status | % Complete |
|-------|-------|--------|-----------|
| **1: Design** | ADR document | ✅ **DONE** | 100% |
| | Specification | ✅ **DONE** | 100% |
| | Test cases | ✅ **DONE** | 100% |
| **2: Skills Update** | Module creation | ✅ **DONE** | 100% |
| | Skill-04 integration | ⏳ TODO | 0% |
| | Skill-07 integration | ⏳ TODO | 0% |
| | Unit tests | ⏳ TODO | 0% |
| **3: Migration** | Migration script | ⏳ TODO | 0% |
| | 12 benchmarks conversion | ⏳ TODO | 0% |
| **4: Validation** | Pipeline tests | ⏳ TODO | 0% |
| | Accuracy validation | ⏳ TODO | 0% |
| **5: Production** | Code cleanup | ⏳ TODO | 0% |
| | Documentation | ⏳ TODO | 0% |
| | Release | ⏳ TODO | 0% |

---

## Completed Work

### Phase 1: ✅ Design Complete
- **ADR-105**: Full specification with decision rationale, alternatives, consequences
- **Pseudo-code**: MOB window inference and cost distribution algorithms documented
- **Examples**: Real data from MATEC_GUARULHOS and ODFJELL with expected outputs

### Phase 2.1: ✅ Module Created
- **File**: `src/concilium/application/scheduling/mob_scheduling.py`
- **Functions Implemented**:
  - ✅ `infer_mob_windows()`: Calculate mobilizacao/operacao/desmobilizacao windows
  - ✅ `calcular_custo_indireto_mob()`: Distribute costs by phase and driver
  - ✅ `get_mob_summary()`: Extract cost summary per phase
- **Dependencies**: date parsing, topological sort via predecessores

---

## Remaining Work (Priority Order)

### Immediate: Phase 2 (Weeks 1-2)

1. **Skill-04 Integration** (Skill-04 Cronograma)
   - [ ] Import `infer_mob_windows` from mob_scheduling
   - [ ] Calculate `mob_schedule` from project meta + EAP
   - [ ] Add `resultado.mob_schedule` to Cronograma output
   - [ ] Test: Verify windows don't overlap, cover full project timeline

2. **Skill-07 Integration** (Skill-07 Custos Indiretos)
   - [ ] Import `calcular_custo_indireto_mob` from mob_scheduling
   - [ ] Use MOB phases to calculate indirect costs
   - [ ] Integrate with existing ADM/TOP/LAB/QSMS logic
   - [ ] Test: Verify MOB distribution by driver (projeto vs mensal)

3. **Unit Tests**
   - [ ] tests/unit/test_mob_scheduling.py
     - [ ] test_infer_windows_basic
     - [ ] test_infer_windows_no_eap
     - [ ] test_infer_windows_safety_margin
     - [ ] test_calcular_mob_projeto
     - [ ] test_calcular_mob_mensal
     - [ ] test_calcular_mob_mixed

### Phase 3 (Week 3)

4. **Migration Script**
   - [ ] `scripts/migrate_adr105.py`
   - [ ] Read all 12 benchmarks from benchmarks/data/*/referencia.json
   - [ ] For each: call `infer_mob_windows()` + separate MOB phases
   - [ ] Update `spec.indiretos` with new MOB format
   - [ ] Remove `spec.rcpsp_spec` if present
   - [ ] Commit changes

5. **Benchmark Conversion**
   - [ ] AGIS: Reformat existing MOB structure
   - [ ] ODFJELL: Separate INDML5-8 into 3 phases
   - [ ] MATEC_GUARULHOS: Separate 3.5 (mobilizacao) + 3.6 (desmobilizacao)
   - [ ] CTC, LUNDIN, MARA_ROSA, ... (9 others): Desaggregate generic MOB

### Phase 4 (Week 4)

6. **Pipeline Validation**
   - [ ] Run `python scripts/run_benchmarks.py`
   - [ ] Verify 12/12 APROVADO (no BLOQUEADO or ERRO)
   - [ ] Verify `resultado.breakdown.indireto.mob` populated correctly
   - [ ] Integration test: MOB costs + diretos + BDI = total

7. **Accuracy Checks**
   - [ ] For ODFJELL: MOB total ≈ R$ 1.745.795
   - [ ] For MATEC_GUARULHOS: MOB total ≈ R$ 2.453.473
   - [ ] For AGIS: MOB total ≈ R$ 4.054.600 (estimated from current spec.indiretos)

### Phase 5 (Week 5)

8. **Production Release**
   - [ ] Mark `spec.rcpsp_spec` as @deprecated in code comments
   - [ ] Update docs/engineering/skills/04-cronograma.md
   - [ ] Update docs/engineering/skills/07-custos-indiretos.md
   - [ ] Create migration guide: v2 → v3
   - [ ] Tag release: v3.0-adr105

---

## Key Metrics

| Metric | Target | Status |
|--------|--------|--------|
| Benchmarks passing | 12/12 | ⏳ In progress |
| MOB cost accuracy | 95-105% of reference | ⏳ Pending |
| Code reduction (rcpsp_spec) | ~80% | ⏳ Pending removal |
| Skills update time | < 2 weeks | ⏳ On track |

---

## Decision Points Resolved

✅ **MOB phases approach approved** (mobilizacao + operacao + desmobilizacao)  
✅ **Driver strategy approved** (projeto=fixed, mensal=recurring)  
✅ **Window inference deterministic** (no manual input needed)  
✅ **Backwards compatible** (legacy rcpsp_spec can be ignored)

---

## Blockers / Dependencies

- None currently blocking Phase 2
- Phase 3 depends on Phase 2 completion
- Phase 4-5 depend on Phase 3

---

## Next Steps

1. **Skill-04 Integration**: Add MOB window inference to cronograma skill output
2. **Skill-07 Integration**: Add MOB cost distribution to indiretos skill
3. **Unit Tests**: Validate MOB logic with known inputs/outputs
4. **Migration**: Run script to convert all 12 benchmarks
5. **Validation**: Confirm 12/12 APROVADO with MOB phases

**Estimated Completion:** 5 weeks from 2026-06-08 = ~2026-07-13

---
