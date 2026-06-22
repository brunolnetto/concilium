# ADR-116 — Limpeza da Superfície de Tools MCP: Remoção de Legado e Governança Anti-Deriva

**Status:** Implementado ✅ _(F1-F4 2026-06-20 · F5 2026-06-22 · 55→52→40 tools)_  
**Data:** 2026-06-20  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-037 (MCP Facade Micro→Macro), ADR-099 (RBAC role↔tool), ADR-039/ADR-043 (Benchmark), ADR-102 (Pipeline Jobs async)

---

## Contexto

### Problema

P1. **Deriva contra o ADR-037.** O ADR-037 decidiu reduzir a superfície MCP de ">25 micro-ferramentas
para ~9 macro-ferramentas". Auditoria de 2026-06-20 encontrou **55 tools registradas** — 6× a meta
e 2× o estado "antes" que o ADR-037 estava corrigindo. A superfície cresceu sem governança.

P2. **Duplicação benchmark legado × NEP-039.** Coexistem dois conjuntos de tools de benchmark:
- `benchmark` (legado): `listar_benchmarks`, `executar_benchmark`, `empacotar_benchmark`, `download_benchmark_zip`
- `benchmark_nep039` (atual, store versionado + imutabilidade): `listar_benchmarks_nep039`, `executar_benchmark_nep039`, `consultar_benchmark`, `editar_benchmark`, `marcar_benchmark_imutavel`, `comparar_execucoes_benchmark`

`listar_benchmarks`/`executar_benchmark` são **duplicatas** das versões NEP-039, que oferecem
versionamento e imutabilidade que o legado não tem. O agente vê dois caminhos para a mesma intenção.

P3. **Tool deprecada ainda registrada.** `avancar_pipeline` está marcada `[DEPRECATED]` no próprio
docstring (substituída pelo fluxo assíncrono `disparar_pipeline`, ADR-102), mas continua exposta e
referenciada em prompts, app de formulário e mensagens de erro.

P4. **Sem guarda contra reincidência.** Nada impede que a superfície volte a crescer — não há teto
de tools nem detecção de verbos duplicados.

---

## Decisão

**D1 — Remover as duplicatas de benchmark legado (−2 tools).**  
`listar_benchmarks` e `executar_benchmark` são removidas do módulo `tools/benchmark.py`. Intenções
equivalentes passam por `listar_benchmarks_nep039` e `executar_benchmark_nep039` (versionados).

**D2 — Preservar empacotamento/download (sem perda de capacidade).**  
`empacotar_benchmark` e `download_benchmark_zip` **não têm equivalente** no NEP-039 (são operações de
artefato, não de execução). Permanecem registradas. O módulo `benchmark.py` deixa de ser "execução"
e passa a ser apenas "empacotamento/download de benchmark".

**D3 — Remover `avancar_pipeline` deprecada (−1 tool).**  
Removida do registro. Referências atualizadas:
- `prompts.py`: trocar exemplos `avancar_pipeline(...)` por `disparar_pipeline(...)`
- `apps/formulario-qqp/index.html`: idem na orientação ao usuário
- `analise.py`: mensagens de erro "Execute avancar_pipeline" → "Execute disparar_pipeline"
- `replan.py`, `_context.py`, `__init__.py`, `scope_guard.py`: atualizar docstrings/comentários

**D4 — Governança anti-deriva: teste de teto + sem duplicatas.**  
Novo teste `test_mcp_tool_governance.py`:
- Teto de superfície: número de tools registradas ≤ `MCP_TOOL_CEILING` (52, valor pós-limpeza).
  Subir o teto exige editar a constante conscientemente — torna o crescimento uma decisão, não acidente.
- Sem verbos duplicados: nenhum par de tools com a mesma intenção (ex: `listar_benchmarks*`,
  `executar_benchmark*`) — detecta reincidência de duplicação.
- Toda tool registrada tem entrada em `TOOL_PERMISSIONS` (ADR-099 — cobertura RBAC).

**D5 — Consolidação de micro-tools fica para fase 2 (documentada, não executada agora).**  
Candidatos identificados, deferidos para evitar mudança ampla de contrato num só passo:
- `catalogo`: 3 tools de saúde (`consultar_saude_catalogo`, `avaliar_plausibilidade_catalogo`,
  `verificar_integridade_catalogo`) → `auditar_catalogo(modo=)`
- `catalogo`: 2 de preço-histórico (`consultar_preco_insumo_temporal`, `tendencia_precos_catalogo`)
- `tributacao`: 3 (`calcular_custo_empregador_clt`, `calcular_inss_empregado`, `calcular_irrf`)
  → `calcular_tributos(tipo=)`

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Deletar o módulo `benchmark` inteiro | Perde `empacotar_benchmark`/`download_benchmark_zip` que não têm equivalente NEP-039 |
| A2 | Manter tudo e só documentar | Não resolve P1/P2; agente continua com dois caminhos para a mesma intenção |
| A3 | Consolidar tudo (catalogo+tributacao) agora | Mudança ampla de contrato num passo; risco alto. Fase 2 separada |
| A4 | Só remover deprecada, manter duplicatas benchmark | Deixa a duplicação P2 (a mais confusa para o agente) sem resolver |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Menos ambiguidade | Um caminho por intenção de benchmark (NEP-039 versionado) |
| Alinhamento ADR-037 | 55 → 52 agora; caminho para ~40 na fase 2 |
| Anti-deriva | Teto + detecção de duplicatas tornam crescimento uma decisão consciente |
| Cobertura RBAC garantida | Teste exige TOOL_PERMISSIONS para toda tool (ADR-099) |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Cliente MCP usando `listar_benchmarks`/`executar_benchmark` antigas | São duplicatas exatas — migração é trocar o nome pelo sufixo `_nep039` |
| Referências a `avancar_pipeline` quebrarem | D3 enumera e atualiza todas as referências internas |
| Teto bloquear feature legítima | Constante editável com justificativa — fricção intencional, não bloqueio |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | Remover `listar_benchmarks` + `executar_benchmark` (duplicatas) do registro | ✅ 2026-06-20 |
| F2 | Remover `avancar_pipeline` + atualizar referências (prompts, app, error msgs) | ✅ 2026-06-20 |
| F3 | Limpar `TOOL_PERMISSIONS` das tools removidas | ✅ 2026-06-20 |
| F4 | `test_mcp_tool_governance.py`: teto + sem-duplicatas + cobertura RBAC | ✅ 2026-06-20 |
| F5 | Consolidação 9 grupos micro→macro (tributação, catálogo, artefatos, pipeline, benchmark, escopo, projeto) | ✅ 2026-06-22 · 52→40 |

---

## Definition of Done

- [x] `listar_benchmarks` e `executar_benchmark` removidas; `_nep039` permanecem
- [x] `empacotar_benchmark`/`download_benchmark_zip` preservadas (sem perda de capacidade)
- [x] `avancar_pipeline` removida; nenhuma referência interna a ela em código ativo
- [x] `TOOL_PERMISSIONS` sem entradas órfãs (ADR-117 eliminou dict)
- [x] `test_mcp_tool_governance.py`: teto 40, zero duplicatas, 100% cobertura RBAC
- [x] F5: 9 consolidações → 52→40 tools (tributação, catálogo ×3, artefatos, pipeline, benchmark, escopo, projeto)
- [x] Suite verde sem regressão

---

## Relacionados

- ADR-037 — MCP Facade Micro→Macro (decisão original de superfície enxuta)
- ADR-099 — RBAC role↔tool (TOOL_PERMISSIONS)
- ADR-102 — Pipeline Jobs async (`disparar_pipeline` substitui `avancar_pipeline`)
- ADR-039/043 — Benchmark / NEP-039 (store versionado)
