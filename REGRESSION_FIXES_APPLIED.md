# Correções de Regressão Aplicadas

**Data:** 2026-06-08  
**Status:** Em progresso

---

## Problemas Identificados e Corrigidos

### 1. **EapItem Fields — Campos Obrigatórios** ✅ FIXED

**Problema**:
- Skill-01 exigia `ordem`, `descricao`, `unidade` como obrigatórios
- AGIS não tinha esses campos

**Causa**:
- Modelo `EapItem` em `canonical.py` definia esses campos sem default

**Correção**:
- Tornar `ordem`, `descricao`, `unidade` opcionais (`int | None`, `str | None`)
- Inferir do catálogo se não fornecidos

**Resultado**:
- ✅ AGIS passa em Skill-01 sem EXCEPTION
- ✅ Dados minimalistas preservados

### 2. **Activity Duration — Hardcoded duration_weeks=1** ⏳ IN PROGRESS

**Problema**:
- Todas as atividades criadas com `duration_weeks=1` (hardcoded)
- Cronograma concentrado em 3 semanas total
- `completion_threshold_pct` nunca aplicado (sem duração real para calcular)

**Causa-Raiz**:
- Função `_extract_activities()` ignora quantitativo e produtividade
- Deve calcular: `duration = ceil(quantitativo / (produtividade × horas_dia × dias_semana))`
- ADR-072 Direção A especifica isso, mas não foi implementado em modo MANUAL

**Correção Aplicada**:
- Modificar `_extract_activities()` para aceitar `cpu_lookup` e `producao_lookup`
- Chamar `_compute_productive_weeks()` para calcular duração real
- Default: 1 semana se catálogos não disponíveis

**Código**:
```python
# Antes (BUG):
def _extract_activities(canonical_in: CanonicalModel) -> list[Activity]:
    for item in canonical_in.eap:
        activities.append(Activity(..., duration_weeks=1, ...))  # HARDCODED!

# Depois (FIX):
def _extract_activities(
    canonical_in: CanonicalModel,
    cpu_lookup: dict | None = None,
    producao_lookup: dict | None = None,
    validacoes: list | None = None,
) -> list[Activity]:
    for item in canonical_in.eap:
        duration_weeks = 1
        if cpu_lookup and producao_lookup:
            computed = _compute_productive_weeks(
                item.item_id, 1, canonical_in, cpu_lookup, producao_lookup, validacoes
            )
            if computed:
                duration_weeks = computed
        activities.append(Activity(..., duration_weeks=duration_weeks, ...))
```

**Impacto Esperado**:
- ✅ Cronograma distribuído ao longo do tempo real (~24 meses para AGIS em vez de 3 semanas)
- ✅ `completion_threshold_pct` (0.35, 0.05) será respeitado
- ✅ Atividades em paralelo conforme predecessores permitem
- ✅ Visualizações (área_tempo_componente, gantt, etc) com dados distribuídos

---

## Próximas Investigações

Se `duration_weeks` ainda estiver 1 após essa correção:

1. **Verificar if há parâmetros de catálogo**:
   - Skill-04 está recebendo `catalogo` em inputs?
   - `cpu_lookup` está populado?

2. **Verificar if CPU está no catálogo**:
   - CPU "CPU-TERRA-ATI-003" existe no catálogo?
   - Tem `producao_id_ref`?

3. **Verificar if há problema em _compute_productive_weeks**:
   - Produtividade retorna valor > 0?
   - Q (quantitativo) é válido?

---

## Timeline de Commits

1. ✅ **b09d5dd**: refactor(EapItem): tornar campos opcionais
2. ✅ **acea2e9**: fix(Skill-04): calcular duração produtiva
3. ⏳ Teste em progresso — aguardando resultado

---

## Arquivos Modificados

- `src/concilium/domain/models/canonical.py` — campos EapItem opcionais
- `src/concilium/application/skills/manifests/04-cronograma/skill.py` — duração produtiva

---

## Validação

Esperado após correção:
- AGIS makespan: ~100+ semanas (não 3)
- Atividades distribuídas respeitando completion_threshold_pct
- Visualizações com dados ao longo do tempo

Teste: `python3 scripts/run_benchmarks.py --benchmark AGIS --skills 04`
