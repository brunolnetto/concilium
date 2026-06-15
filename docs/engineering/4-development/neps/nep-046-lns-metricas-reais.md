# NEP-046 — Métricas reais no LNS (remover _simple_metrics trivial)

**Status:** Implementado ✅ _(2026-06-12)_  
**Prioridade:** MÉDIO — distorce `compare_all_algorithms()` e quality_score  
**Relacionado:** ADR-075, NEP-038

---

## Problema

`_simple_metrics()` em `lns_scheduler.py` retornava valores triviais fixos:
- `resource_leveling_score = 1.0` (melhor possível)
- `idle_time = 0`
- `resource_utilization_avg = 0.0`

O `quality_score` composto (makespan 50%, leveling 20%, idle 15%, util 15%) ficava inflado
artificialmente para resultados LNS. Em `compare_all_algorithms()`, LNS ganhava de CP-SAT
e MINSLK nas componentes de leveling/idle mesmo quando seu cronograma era pior.

## Causa

`_ssgs()` já computava `resource_usage: dict[int, dict[str, int]]` internamente mas não
passava para `_simple_metrics()`. As métricas reais precisam desse dict.

## Correção

`_simple_metrics()` passou a aceitar `resource_usage` e `deadline_weeks`, computando
leveling score (coeficiente de variação), idle time e utilização média — idêntico ao
algoritmo de `SerialScheduler._compute_metrics()`.

A chamada em `_ssgs()` foi atualizada para passar `resource_usage` e `deadline`.
