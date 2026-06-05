# NEP-023: Estratégia de variáveis de ambiente para separação API/UI e legado de mapping

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Configuração  
**Tipo:** Governança + Deploy  
**Esforço:** S  
**Identificado em:** 2026-05-22  
**Concluído em:** 2026-05-22

---

## Contexto

O `.env.example` já refletia a migração para `CONCILIUM__BENCHMARK_CPU_MAPPING_RULES_FILE`,
mas ainda precisava:

1. reforçar que `CONCILIUM__CPU_MAPPING_RULES_FILE` é legado apenas para transição,
2. preparar variáveis de rede para cenário de API e UI desacopladas.

## Decisão

- Manter `CONCILIUM__BENCHMARK_CPU_MAPPING_RULES_FILE` como variável principal para mapeamento de benchmark.
- Preservar `CONCILIUM__CPU_MAPPING_RULES_FILE` somente como compatibilidade temporária.
- Introduzir bloco de variáveis API/UI no `.env.example` para deployments com serviços separados:
  - `CONCILIUM__API_HOST`
  - `CONCILIUM__API_PORT`
  - `CONCILIUM__API_BASE_URL`
  - `CONCILIUM__UI_HOST`
  - `CONCILIUM__UI_PORT`
  - `CONCILIUM__UI_API_BASE_URL`

## Critério de Aceite

1. `.env.example` diferencia claramente variável principal vs legada no mapping CPU.
2. `.env.example` contém variáveis de host/porta/base URL para API e UI.
3. Documentação deixa explícito que o bloco API/UI é preparação para arquitetura desacoplada.

## Evidências

- `.env.example`
- `src/concilium/infrastructure/catalog/mapping/cpu_mapper.py`
- `src/concilium/presentation/ui/config.py`
