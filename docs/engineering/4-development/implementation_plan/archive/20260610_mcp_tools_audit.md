# MCP Tools Audit — Plano de Correção

**Data:** 2026-06-10  
**Origem:** Auditoria de 9 achados confirmados que introduzem confusão para o agente

---

## Achados e Status

| # | Severidade | Descrição | Status |
|---|---|---|---|
| 1 | 🔴 Crítico | `criar_projeto_formulario` usa modelo flat — `disparar_pipeline` falha depois | ✅ Corrigido |
| 2 | 🔴 Crítico | `prazo_ok` tautologia (`data_termino <= data_termino`) — sempre True | ✅ Corrigido |
| 3 | 🟠 Alto | `avancar_pipeline` deprecated visível ao agente | ✅ Corrigido |
| 4 | 🟠 Alto | `benchmark_nep039` registra `listar_benchmarks`/`executar_benchmark` duplicados (mortos) | ✅ Corrigido |
| 5 | 🟠 Alto | `replan` stubs com dados fictícios (`"R$ +45.000,00"` hardcoded) | ✅ Corrigido |
| 6 | 🟠 Alto | `consultar_status` cego para ADR-031 (retorna `current_version: null`) | ✅ Corrigido |
| 7 | 🟡 Médio | 3 tools de criação de projeto sem guia de decisão nas docstrings | ✅ Corrigido |
| 8 | 🟡 Médio | 11 tools de catálogo sem diferenciação clara nas docstrings | ✅ Corrigido |

---

## Detalhes técnicos por achado

### #1 — `criar_projeto_formulario` flat model
**Causa:** `formulario.py` nunca foi migrado após o refactor ADR-031. Usava `store.new_version()` + `coord.avancar_projeto()` em vez de `create_escopo + avancar_plano`. Após a criação, `disparar_pipeline` falhava com "Use configurar_escopo", que por sua vez falhava com FileExistsError.  
**Fix:** Migrado para `create_escopo("esc-principal") + create_plan() + coord.avancar_plano()` — exatamente o mesmo padrão de `iniciar_orcamento`.

### #2 — `prazo_ok` tautologia
**Causa:** `canonical.projeto.data_termino <= canonical.projeto.data_termino` — comparação de objeto com si mesmo.  
**Fix:** Comparado com `date.today()` (prazo futuro = OK).

### #3 — `avancar_pipeline` visível
**Causa:** Tool deprecated registrada sem `hidden=True` no FastMCP. Aparecia ao lado de `disparar_pipeline` com parâmetros idênticos.  
**Fix:** Removido `@server.tool()` do decorator — mantida a função para retrocompat de código interno.

### #4 — `benchmark_nep039` duplicatas
**Causa:** `server.py` registra `benchmark.register()` na linha 82 e `benchmark_nep039.register()` na 91. FastMCP mantém o primeiro registro por nome — as funções NEP-039 eram código morto.  
**Fix:** `benchmark_nep039.register()` movido para comentário no server; suas tools únicas (`consultar_benchmark`, `editar_benchmark`, `marcar_benchmark_imutavel`, `comparar_execucoes_benchmark`) preservadas com prefix diferente.

### #5 — Replan stubs
**Causa:** `simular_cenario_replan` retornava `"delta_custo": "R$ +45.000,00"` hardcoded. `aplicar_sugestao_replan` exigia `sugestao_id` que nenhuma tool gerava.  
**Fix:** Ambas ocultadas (`hidden=True`) até implementação real. Mensagem de erro clara se chamadas diretamente.

### #6 — `consultar_status` cego para ADR-031
**Causa:** Toda a lógica de skills/resultado era gated por `if v:` onde `v = meta.get("current_version")`. Projetos ADR-031 não têm `current_version` no meta.json raiz.  
**Fix:** Quando `current_version` é None, consulta escopos ativos e seus planos. Retorna `escopos_ativos`, `plano_ativo`, e skills executadas do invocations.log do plano.

### #7 — Docstrings das 3 tools de criação
**Fix:** Cada docstring agora inicia com quando usar ("Use quando X") e menciona as alternativas.

### #8 — Docstrings das 11 tools de catálogo
**Fix:** Reescritas com caso de uso concreto na primeira linha. Grupos diferenciados: lookup/pesquisa, diagnóstico/saúde, mutação/atualização, análise temporal.
