# ADR-105 Migration Guide: v2 → v3

**Document Version:** 1.0  
**Effective Date:** 2026-06-08  
**Deprecation Timeline:** v3.0-adr105 (current) → v4.0 (removal)

---

## Overview

ADR-105 introduces **deterministic MOB (Mobilização/Desmobilização) window inference** replacing manual `spec.rcpsp_spec` configuration. This guide explains the migration path from v2 (rcpsp_spec-based) to v3 (ADR-105 MOB phases).

---

## What Changed

### v2 Architecture (Deprecated)

```json
{
  "spec": {
    "rcpsp_spec": {
      "activities": [...],
      "precedence": [...],
      "resource_pool": {...},
      "pool_config": {...}
    }
  }
}
```

**Problem**: Manual RCPSP specification required; MOB windows not explicitly modeled.

### v3 Architecture (ADR-105)

```json
{
  "meta": {
    "data_inicio": "2026-01-01",
    "data_termino": "2027-12-31"
  },
  "spec": {
    "eap": [...],
    "cronograma": [...],
    "indiretos": [
      {
        "categoria": "MOB",
        "fase": "mobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 246900
      },
      {
        "categoria": "MOB",
        "fase": "operacao",
        "driver": "mensal",
        "custo_fixo_mensal": 35654
      },
      {
        "categoria": "MOB",
        "fase": "desmobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 123450
      }
    ]
  },
  "mob_schedule": {
    "mobilizacao": {
      "inicio": "2026-01-01",
      "fim": "2026-01-15"
    },
    "operacao": {
      "inicio": "2026-01-16",
      "fim": "2027-12-31"
    },
    "desmobilizacao": {
      "inicio": "2027-12-31",
      "fim": "2027-12-31"
    }
  }
}
```

**Benefits**: 
- ✅ Deterministic window inference (no manual input)
- ✅ Three-phase MOB structure (mobilizacao/operacao/desmobilizacao)
- ✅ Driver-aware cost distribution (projeto vs mensal)
- ✅ Automatic calculation from project dates + EAP

---

## Migration Steps

### Step 1: Verify Project Dates & EAP (Required)

**Check**: `meta.data_inicio` and `meta.data_termino` are populated.

```python
# Example
meta = {
    "data_inicio": "2026-01-01",
    "data_termino": "2027-12-31"
}
eap = [
    {"item_id": "1.1", "predecessores": []},
    {"item_id": "1.2", "predecessores": [{"item_id": "1.1"}]},
    {"item_id": "2.1", "predecessores": [{"item_id": "1.2"}]}
]
```

**Action**: Ensure EAP has `predecessores` populated for accurate window inference.

### Step 2: Update spec.indiretos (Required)

**Old Format** (v2):
```json
{
  "categoria": "MOB",
  "custo_total": 1745795
}
```

**New Format** (v3):
```json
[
  {
    "categoria": "MOB",
    "fase": "mobilizacao",
    "driver": "projeto",
    "custo_fixo_total": 246900
  },
  {
    "categoria": "MOB",
    "fase": "operacao",
    "driver": "mensal",
    "custo_fixo_mensal": 35654
  },
  {
    "categoria": "MOB",
    "fase": "desmobilizacao",
    "driver": "projeto",
    "custo_fixo_total": 123450
  }
]
```

**Migration Strategy**:
1. Identify total MOB cost from v2
2. Allocate ~15% to mobilizacao (fixed)
3. Allocate ~70% to operacao (monthly, duration inferred from project dates)
4. Allocate ~15% to desmobilizacao (fixed)

**Example**:
```python
mob_total = 1_745_795
mob_mobilizacao = mob_total * 0.15        # R$ 261,869
mob_operacao_mensal = mob_total * 0.70 / 24  # 24 months = R$ 50,836/mês
mob_desmobilizacao = mob_total * 0.15     # R$ 261,869
```

### Step 3: Remove spec.rcpsp_spec (Recommended)

**Old Code**:
```json
{
  "spec": {
    "rcpsp_spec": { "activities": [...], "precedence": [...] },
    "eap": [...],
    "cronograma": [...]
  }
}
```

**New Code**:
```json
{
  "spec": {
    "eap": [...],
    "cronograma": [...],
    "indiretos": [...]
  }
}
```

**Action**: Delete `spec.rcpsp_spec` object after verifying MOB windows are being inferred in `mob_schedule`.

### Step 4: Verify MOB Schedule Generation (Automatic)

Once Steps 1-3 are complete, Skill-04 (Cronograma) automatically generates `mob_schedule`:

```json
{
  "mob_schedule": {
    "mobilizacao": {
      "inicio": "2026-01-01",
      "fim": "2026-01-08"
    },
    "operacao": {
      "inicio": "2026-01-01",
      "fim": "2027-12-31"
    },
    "desmobilizacao": {
      "inicio": "2027-12-24",
      "fim": "2027-12-31"
    }
  }
}
```

**Verification**:
- ✅ Three phases present
- ✅ No overlaps (mobilizacao.fim ≤ desmobilizacao.inicio)
- ✅ Covers full project timeline (operacao spans data_inicio to data_termino)

### Step 5: Validate Skill-07 MOB Cost Distribution (Automatic)

Skill-07 (Custos Indiretos) now receives `mob_schedule` and distributes costs by phase:

```json
{
  "indiretos": [...],
  "resultado": {
    "breakdown": {
      "indireto": {
        "mob": {
          "mobilizacao": 246900,
          "operacao": 1232095,
          "desmobilizacao": 266800
        }
      }
    }
  }
}
```

**Verification**:
- ✅ MOB costs sum to total (±5% rounding acceptable)
- ✅ Phase distribution follows spec.indiretos allocation
- ✅ Driver semantics applied (projeto vs mensal)

---

## Automated Migration Script

Use the provided migration script to convert all benchmarks:

```bash
# Dry run (preview changes)
python3 scripts/migrate_adr105.py --dry-run

# Migrate specific benchmark
python3 scripts/migrate_adr105.py --benchmark ODFJELL

# Migrate all benchmarks
python3 scripts/migrate_adr105.py
```

The script:
1. ✅ Infers MOB windows from meta + EAP
2. ✅ Adds `mob_schedule` to referencia.json
3. ✅ Preserves existing `spec.indiretos` (MOB phase structure already in place)

---

## Backward Compatibility

### What Still Works (v2 Data)

If your project still has `spec.rcpsp_spec`:
1. **Skill-02**: May use rcpsp_spec for scheduling (legacy)
2. **Skill-04**: Infers MOB windows independently (ADR-105)
3. **Skill-07**: Accepts mob_schedule parameter (optional; falls back to legacy MOB calculation)

### When to Stop Using v2

Remove `spec.rcpsp_spec` when:
- ✅ You've verified `mob_schedule` is being generated by Skill-04
- ✅ You've updated `spec.indiretos` to use 3-phase MOB structure
- ✅ Pipeline validation shows all skills APROVADO

### Timeline

- **v3.0-adr105** (Current): rcpsp_spec fully supported but deprecated
- **v3.x (Future)**: Warning logs when rcpsp_spec is used
- **v4.0 (TBD)**: Complete removal of rcpsp_spec support

---

## Example Migration (Step-by-Step)

### Before (v2)
```json
{
  "meta": { "data_inicio": "2026-01-01", "data_termino": "2027-12-31" },
  "spec": {
    "rcpsp_spec": {
      "activities": [
        { "item_id": "1.1", "duration_weeks": 52 },
        { "item_id": "1.2", "duration_weeks": 52 }
      ],
      "precedence": [["1.1", "1.2"]],
      "resource_pool": { "team": 5 }
    },
    "eap": [
      { "item_id": "1.1", "predecessores": [] },
      { "item_id": "1.2", "predecessores": [{ "item_id": "1.1" }] }
    ],
    "indiretos": [
      { "categoria": "ADM", "custo_fixo_mensal": 100000 },
      { "categoria": "MOB", "custo_total": 1745795 }
    ]
  }
}
```

### After (v3)
```json
{
  "meta": { "data_inicio": "2026-01-01", "data_termino": "2027-12-31" },
  "spec": {
    "eap": [
      { "item_id": "1.1", "predecessores": [] },
      { "item_id": "1.2", "predecessores": [{ "item_id": "1.1" }] }
    ],
    "indiretos": [
      { "categoria": "ADM", "driver": "mensal", "custo_fixo_mensal": 100000 },
      {
        "categoria": "MOB",
        "fase": "mobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 261869
      },
      {
        "categoria": "MOB",
        "fase": "operacao",
        "driver": "mensal",
        "custo_fixo_mensal": 50836
      },
      {
        "categoria": "MOB",
        "fase": "desmobilizacao",
        "driver": "projeto",
        "custo_fixo_total": 261869
      }
    ]
  },
  "mob_schedule": {
    "mobilizacao": { "inicio": "2026-01-01", "fim": "2026-01-08" },
    "operacao": { "inicio": "2026-01-09", "fim": "2027-12-24" },
    "desmobilizacao": { "inicio": "2027-12-25", "fim": "2027-12-31" }
  }
}
```

**Changes**:
- ❌ Removed: `spec.rcpsp_spec`
- ✅ Updated: `spec.indiretos[MOB]` to 3-phase structure
- ✅ Added: `mob_schedule` (generated by Skill-04)

---

## Validation Checklist

After migration, verify:

- [ ] `meta.data_inicio` and `meta.data_termino` populated
- [ ] `spec.eap` has `predecessores` for each item
- [ ] `spec.indiretos` includes 3 MOB entries (mobilizacao, operacao, desmobilizacao)
- [ ] `spec.rcpsp_spec` removed (or ignored by pipeline)
- [ ] Run pipeline: `python3 scripts/run_benchmarks.py --benchmark YOUR_PROJECT`
- [ ] Verify status: **APROVADO** ✅
- [ ] Check `mob_schedule` in canonical output
- [ ] Verify MOB costs in breakdown match expected ranges

---

## Troubleshooting

### Problem: mob_schedule not generated

**Cause**: EAP missing or `predecessores` not populated.

**Solution**:
```python
# Ensure each EAP item has predecessores list
for item in spec["eap"]:
    if "predecessores" not in item:
        item["predecessores"] = []
```

### Problem: MOB costs don't match expected total

**Cause**: Phase allocation percentages not matching project specifics.

**Solution**: Adjust allocation from the default 15% / 70% / 15%:

```python
# Example: 20% mobilizacao, 60% operacao, 20% desmobilizacao
mob_total = 1_745_795
phases = {
    "mobilizacao": mob_total * 0.20,
    "operacao_mensal": mob_total * 0.60 / duration_months,
    "desmobilizacao": mob_total * 0.20
}
```

### Problem: Pipeline validation fails (BLOQUEADO)

**Cause**: Skill-04 or Skill-07 pre-condition not met.

**Solution**:
1. Check Skill-03 (Equipes Diretas) status
2. Verify `spec.indiretos` is properly formatted
3. Run individual skill: `python3 scripts/run_benchmarks.py --benchmark YOUR_PROJECT --skills 04`

---

## Support & Questions

For questions or issues:
1. Check [ADR-105.md](../../ADR-105.md) for detailed specification
2. Review [ADR105_IMPLEMENTATION_SUMMARY.md](../../ADR105_IMPLEMENTATION_SUMMARY.md) for technical details
3. See [ADR105_ACCURACY_VALIDATION.md](../../ADR105_ACCURACY_VALIDATION.md) for validation results

---

## References

- **ADR-105**: Mobilização e Desmobilização specification
- **Skill-04**: Cronograma (MOB window inference)
- **Skill-07**: Custos Indiretos (MOB cost distribution)
- **Script**: `scripts/migrate_adr105.py` (automated migration)
