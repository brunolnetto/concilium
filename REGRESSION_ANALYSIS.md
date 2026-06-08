# Regressão de Dados — Análise Técnica

**Data:** 2026-06-08  
**Status:** Identificado e documentado

---

## Problemas Identificados

### 1. **Cronograma — Concentração em Período Único**

**Symptom**: Gráfico `area_tempo_componente.png` mostra apenas 1 período (2026-06) em vez de distribuído

**Root Cause**: Cronograma não está considerando `completion_threshold_pct` de predecessores

**Expected**: 
- Atividades devem começar quando predecessor atinge `completion_threshold_pct`
- Ex: item 1.1 começa quando 1.0 atinge 35% de conclusão
- Resultado: distribuição temporal ao longo do projeto (~24 meses)

**Actual**:
- Todas as atividades concentradas em 1 período
- Cronograma não respeitando `predecessores[].completion_threshold_pct`

**Impact**:
- ❌ bar_atividade_componente.png — sem dados distribuídos
- ❌ bar_tempo_natureza.png — custo direto não aparece (concentrado em 1 período)
- ❌ fluxo_financeiro.png — agregação incorreta
- ❌ gantt_cronograma.png — Gantt incorreto (sem paralelismo)
- ❌ linha_recursos_tempo.png — valores zerados (sem distribuição)
- ❌ scurve_custo.png — sem custo direto (concentrado)

---

### 2. **Campos Opcionais EapItem**

**Status**: ✅ FIXED

**What Was**: `ordem`, `descricao`, `unidade` eram obrigatórios  
**What Is Now**: Opcionais, inferidos do catálogo se não fornecidos  
**Result**: AGIS passa sem EXCEPTION

---

## Investigação Necessária

### A. Skill-04 (Cronograma)

**Verificar**:
1. Função `_extract_dag_from_spec()` — está extraindo `completion_threshold_pct`?
2. Scheduler (heurísticas/MILP) — está usando `completion_threshold_pct` para iniciar atividades?
3. `_build_scheduled_activities()` — está aplicando as datas corretamente?

**Files to Check**:
- `src/concilium/application/skills/manifests/04-cronograma/skill.py`
- `src/concilium/application/skills/manifests/_04_cronograma_skill_helpers.py`
- `src/concilium/application/scheduling/scheduler_heuristic.py`

---

### B. Skill-08 (Consolidação Financeira)

**Verify**:
1. Custos estão sendo distribuídos por semana? 
2. Agregação por período funciona com cronograma concentrado?
3. Dados de indiretos aparecem em relatório?

**Files to Check**:
- `src/concilium/application/skills/manifests/08-consolidacao-financeira/skill.py`

---

### C. Visualizações (Skill-09)

**Verify**:
1. Dados sendo passados corretamente à geração de gráficos?
2. Agregação por período funcionando?
3. Indiretos inclusos nos gráficos?

---

## Timeline

**Ação Imediata**:
1. ✅ Tornar campos EapItem opcionais (DONE)
2. ⏳ Investigar cronograma — por que não distribui ao longo do tempo?
3. ⏳ Verificar se `completion_threshold_pct` está sendo usado
4. ⏳ Corrigir agregação de custos por período

---

## Código Exemplo — Esperado vs Atual

### Esperado (com completion_threshold_pct)

```
Atividade 1.0: 2026-06-01 → 2026-12-31 (100% execução)
Atividade 1.1: 2026-11-15 → 2027-04-30 (começa quando 1.0 atinge 35%)
Atividade 1.2: 2026-12-15 → 2027-05-31 (começa quando 1.0 atinge 35%)
...
Cronograma: Distribuído ao longo de ~24 meses
```

### Atual (sem consideration de completion_threshold_pct)

```
Atividade 1.0: 2026-06-01 → 2026-06-01 (?)
Atividade 1.1: 2026-06-01 → 2026-06-01 (?)
...
Cronograma: Concentrado em 1 período
```

---

## Próximos Passos

1. **Prioridade 1**: Verificar `_extract_dag_from_spec()` — está extraindo completion_threshold_pct?
2. **Prioridade 2**: Verificar scheduler — está aplicando completion_threshold_pct para timing?
3. **Prioridade 3**: Testar com AGIS após correção

---

## Nota

Esses problemas são **regressões da refatoração de cronograma e custos** (centralização em ADR-105). A mudança em EapItem model (tornar campos opcionais) é apenas um sintoma — o problema raiz está na **não aplicação de completion_threshold_pct no scheduling**.

**Recomendação**: Investigar commit que removeu ou mudou a lógica de `completion_threshold_pct` em Skill-04.
