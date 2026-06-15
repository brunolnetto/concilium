# NEP-044 — CP-SAT como requisito: falha explícita em vez de fallback silencioso

**Status:** Implementado ✅ _(2026-06-12)_  
**Prioridade:** ALTA — risco operacional latente  
**Relacionado:** ADR-075 (seleção de algoritmo de scheduling), ADR-004

---

## Problema

`explore_schedules()` capturava exceções do CP-SAT e do LNS com `except Exception` seguido de
`_log.warning(...)`, depois prosseguia silenciosamente para o SerialScheduler com MINSLK.

**Consequência:** falhas do solver — timeout sem solução, crash de importação, infeasibility
inesperada — produziam cronogramas de qualidade inferior (MINSLK heurístico em vez de CP-SAT
exato) sem nenhum sinal para o usuário. O pipeline terminava aparentemente normal, os contratos
de pool eram derivados sobre uma alocação subótima, e `custo_inst_*` refletia essa degradação
silenciosamente.

---

## Decisão

**CP-SAT e LNS são requisitos, não tentativas.** Se o solver falhar — por exceção ou por
retornar `feasible=False` — `explore_schedules()` lança `ScheduleError` com mensagem
explicativa. O pipeline para na skill-04 com erro claro em vez de continuar com resultado
degradado.

O SerialScheduler (MINSLK/LPT/MAXRES/ES/GR) continua disponível como **modo explícito**,
via `algorithm` override ou `heuristics` direto — não como fallback automático de falha.

---

## Mudanças (`selector.py`)

| Antes | Depois |
|---|---|
| `except Exception: _log.warning(...)` + fallthrough | `except ScheduleError: raise` + `except Exception as exc: raise ScheduleError(...) from exc` |
| `if not sched.feasible: # fall through` | `raise ScheduleError("CP-SAT solver não encontrou solução viável...")` |
| `_primary_attempted` flag para selecionar MINSLK no fallback | Removido (código morto) |
| `heuristics = ["MINSLK"] if _primary_attempted else [todos]` | `heuristics = [todos]` sempre |

---

## O que NÃO mudou

- SerialScheduler como modo primário explícito continua funcionando normalmente.
- `compare_all_algorithms()` (usado para análise comparativa) não foi alterado — mantém
  `error=str(exc)` por design (exploratório, não operacional).
- `pool_inference.py` captura `ScheduleError` intencionalmente para o seu fluxo de inferência.
