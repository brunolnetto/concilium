# NEP-045 — Remoção do MILPScheduler (código morto)

**Status:** Implementado ✅ _(2026-06-12)_  
**Prioridade:** BAIXO — limpeza de código morto  
**Relacionado:** ADR-004, ADR-075, NEP-044

---

## Problema

`MILPScheduler` (via PuLP/CBC) nunca é selecionado por `select_scheduling_algorithm()` nem
por `explore_schedules()`. Os únicos pontos de chamada eram:

- CLI `commands_schedule.py` — branch `algorithm == "MILP"` (modo de desenvolvimento)
- skill-04 `_try_milp()` — fallback após heurísticas falharem
- skill-13 `_build_sugestao_milp()` — sugestão de replanejamento com MILP

Com NEP-044 (CP-SAT como requisito), o caminho `explore_schedules → fallback MILP` foi
encerrado. O MILP nunca chegará a ser invocado em produção.

Manter código morto cria ruído de leitura, mantém dependência opcional de PuLP e confunde
a lista `AVAILABLE_SCHEDULE_ALGORITHMS`.

---

## Mudanças

| Arquivo | Ação |
|---|---|
| `scheduling/milp.py` | Removido |
| `scheduling/__init__.py` | Removida referência a `MILPScheduler` |
| `commands_schedule.py` | Removido branch `algorithm == "MILP"` |
| `skill-04/skill.py` | Removidos `_try_milp()`, fallback MILP em `_run_auto_schedule_fallback_chain`, `"MILP"` de `AVAILABLE_SCHEDULE_ALGORITHMS` |
| `skill-13/_assessor.py` | Removidos `_build_sugestao_milp()` e sua chamada |
| `test_milp_scheduler.py` | Removido |
| `test_coverage_boost_misc.py` | Removida classe `TestMILPMissingLines` |
| `test_skill_02_cronograma_auto_mode.py` | Removido teste `test_02_auto_milp_fallback_quando_heuristicas_falham` |
