# NEP-022: Adequação da variável de mapping CPU para contexto agnóstico

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Configuração  
**Tipo:** Governança + Dados  
**Esforço:** S  
**Identificado em:** 2026-05-21  
**Concluído em:** 2026-05-21

---

## Contexto

A variável `CONCILIUM_CPU_MAPPING_RULES_FILE` induzia interpretação de uso global, apesar do consumo estar concentrado em utilitário de benchmark (`cpu_mapper`).

## Causa Raiz

Nome da env var não explicitava o escopo de benchmark.

## Implementação

- Nova variável principal: `CONCILIUM_BENCHMARK_CPU_MAPPING_RULES_FILE`.
- Compatibilidade retroativa preservada com a variável legada.
- Atualização de `.env.example` com semântica explícita de escopo benchmark.

## Critério de Aceite

1. Novo nome da variável está ativo no código.
2. Variável legada continua funcional para transição.
3. `.env.example` documenta claramente escopo benchmark vs legado.

## Evidências

- `src/concilium/infrastructure/catalog/mapping/cpu_mapper.py`
- `.env.example`
