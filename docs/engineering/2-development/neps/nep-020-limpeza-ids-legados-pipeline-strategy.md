# NEP-020: Limpeza de IDs legados em Pipeline Strategy

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Domínio  
**Tipo:** Governança + Refactor  
**Esforço:** S  
**Identificado em:** 2026-05-21  
**Concluído em:** 2026-05-21

---

## Contexto

`pipeline_strategy.py` continha listas com IDs legados (`03-equipes-diretas`, `06-consolidar`) que não representam a malha atual de manifests.

## Causa Raiz

Sequência local duplicada em vez de fonte única derivada dos manifests.

## Implementação

- `HOT_PROJECT_PIPELINE_SKILLS` e `PROJECT_PIPELINE_SKILLS` passaram a derivar de `CANONICAL_SKILL_ORDER`.

## Critério de Aceite

1. Não há IDs legados hardcoded em `pipeline_strategy.py`.
2. Sequência acompanha automaticamente alterações futuras de manifests/fases.

## Evidências

- `src/concilium/application/pipeline_strategy.py`
