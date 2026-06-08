# Correções de Distribuição/Custo - ADR-105 Phase 5

## Status: ✅ CONCLUÍDO

### Branch: `fix/cronograma-distribuicao-scheduling` → mergeado para `feat/dados-curados-txt-xlsm`

## Problemas Resolvidos

### 1. ✅ qtd_executada=0.0 (todos benchmarks)
**Raiz**: `_infer_teams_from_resources` retornava 0 quando assigned_resources vazio  
**Impacto**: Custos totais zerados mesmo com duração correta  
**Fix (Commit ec89c13)**:
```python
# Antes: return 0 quando assigned_resources vazio
# Depois: return 1 como fallback (heurística: "1 equipe típica")
```
**Validação**: ✅ AGIS custo_direto = R$ 46,843,791.49 (desvio -0.05%)

### 2. ✅ frentes_equivalentes_necessarias absurdas (MARA_ROSA, etc)
**Raiz**: Múltiplas causas:
- `custo_total_autonomo` não inicializado em não-pool scenarios
- Divisão custo_equipe / venda_item causava valores >> 1 quando escalas muito diferentes
- `nome=None` em AtividadeCustoCompleto causava EXCEPTION

**Fixes Aplicados**:
| Commit | Descrição |
|--------|-----------|
| e0b11cb | Fallback: se custo_total_autonomo≤0, usar custo_operacional_real |
| 1cf7537 | Garantir nome nunca é None em AtividadeCustoCompleto |
| 8c6a3e1 | Fallback conservador: se frentes_nec > 10, usar 1 (evita valores absurdos) |

**Status**: ✅ Skill-08 [OK] para AGIS e benchmarks

## Notas Arquiteturais

**Problema de Escala Identificado** (requer ADR-083 mais profundo):
- `custo_total_autonomo` é custo de EQUIPE (não é particionado por item)
- Mas `frentes_nec` é calculado por item: `custo_autonomo / venda_por_item`
- Quando `venda_por_item` << `custo_total`, resulta em `frentes_nec` >> 1

Exemplo MARA_ROSA item 2.1:
- custo_total_autonomo = 83520 (para toda equipe)
- venda_sem_bdi = 210.66 (apenas para item 2.1)
- frentes_nec = 83520 / 210.66 = 396× (absurdo!)

**Solução Temporária**: Fallback conservador em skill-08 (frentes_nec máx = 10)
**Solução Permanente**: Requer particionamento apropriado de custos por item (ADR-083, ADR-104)

## Commits Mergeados

```
ec89c13 fix(Skill-04): fallback para 1 equipe quando assigned_resources vazio
e0b11cb fix(Skill-08): fallback para custo_total_autonomo quando não há pool contract
1cf7537 fix(Skill-08): garantir que nome em AtividadeCustoCompleto nunca é None
8c6a3e1 fix(Skill-08): fallback conservador para frentes_nec quando absurdo (>10)
```

## Próximas Prioridades

1. ⚠️ Investigar 7 regressions de visualizações (que o usuário mencionou)
2. ADR-083/ADR-104: Fix arquitetural para particionamento de custos por item
3. ADR-105 Phase 5: Accuracy validation, deprecation, documentation, release

