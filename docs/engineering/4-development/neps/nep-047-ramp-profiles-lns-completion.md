# NEP-047 — Ramp profiles (ADR-074): completar suporte no LNS

**Status:** Implementado ✅ _(2026-06-12)_  
**Prioridade:** MÉDIO — SerialScheduler já implementado; LNS ignora rampas  
**Relacionado:** ADR-074, ADR-075

---

## Problema

`Activity.ramp_profile` especifica a fração de demanda de recurso em cada semana da
atividade (ex: `[0.5, 1.0, 1.0, 0.5]` para ramp-up/down). `SerialScheduler` já consumia
esse campo via `_demand_at_offset()` em `_can_schedule()`. LNS ignorava o campo:

- `_find_start()`: testava demanda plena em todas as semanas (`for offset in range(duration_weeks)`)
- `_book_resources()`: registrava demanda plena em todas as semanas

**Consequência:** LNS schedula atividades com ramp como se demandassem `required_resources`
em toda a duração, impossibilitando paralelismo nos períodos de baixa demanda (ramp-up/down).
O pool derivado por `pool_inference` (que usa SSGS via SerialScheduler) era correto; o
schedule LNS era pessimista.

---

## Posição do CP-SAT

CP-SAT usa `AddCumulative` com demanda fixa por atividade. Modelar demanda variável exigiria
decompor cada atividade em sub-intervalos por semana — O(n×T) variáveis — custo proibitivo.
A abordagem conservadora (demanda = pico) é correta para garantir viabilidade. Ramp profiles
afetam custo de pool e cost computation, não o modelo de constraint CP-SAT.
Este comportamento está documentado em `cpsat_scheduler.py`.

---

## Correção

`_find_start()` e `_book_resources()` em `lns_scheduler.py` passaram a usar
`_demand_at_offset(activity, offset, res, qty)` — o mesmo helper de `scheduler.py`,
replicado localmente como `_lns_demand_at_offset()` para evitar dependência circular.
