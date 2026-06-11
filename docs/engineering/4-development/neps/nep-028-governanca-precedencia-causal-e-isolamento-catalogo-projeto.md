# NEP-028: Governanca de precedencia causal e isolamento de catalogo por projeto

**Status:** Implementado ✅ _(A1-A4 + D4 concluídos 2026-06-10; modo estrito de catálogo como evolução futura)_
**Prioridade:** 🔴 Crítico
**Área:** Arquitetura e Skills
**Tipo:** Governança + Refactor
**Esforço:** XL
**Identificado em:** 2026-05-23
**Dependências upstream:** ADR-035 (LifecycleCoordinator), ADR-031 (Escopos/Planos), ADR-066 (Catalog Overlay)

---

## Contexto

A plataforma evoluiu com forte capacidade de benchmark, overlays e versionamento por projeto.
Porem, a precedencia causal de entradas e a fronteira entre catalogo mestre e catalogo do projeto ainda possuem pontos de ambiguidade operacional.

Isso abre espaco para drift semantico entre execucoes historicas e novas execucoes, especialmente quando contexto/catalogo mestre muda ao longo do tempo.

## Problema observado

### A1 - Base de catalogo em run ainda depende do master corrente

O pipeline de execucao resolve catalogo via carregamento do master e aplicacao de overlays em tempo de run.
Mesmo com snapshot/catalogo embutido no projeto em alguns fluxos, esse snapshot nao e hoje a fonte primaria obrigatoria da execucao.

Efeito:

1. Mudanca no master/contexto pode alterar run de projeto antigo sem mudanca explicita no projeto.
2. Reprodutibilidade historica fica fragilizada.

### A2 - Contrato de mobilizacao nao atravessa ponta a ponta

O campo use_mobilizacao_policy existe no schema de request, mas nao e propagado de forma consistente nas rotas/servico ate a criacao do run.
Com isso, o pipeline tende a cair no default True ao montar entradas de skill.

Efeito:

1. Toggle do cliente pode ser ignorado na pratica.
2. Dificulta depuracao e auditoria de por que a policy foi aplicada.

### A3 - Pipeline strategy valida pre-condicao, mas nao governa sequencia real

Existe estrategia por tipo de projeto (hot_project vs project), porem a sequencia declarada na estrategia nao e usada como fonte unica da ordem de execucao do pipeline.

Efeito:

1. Contrato arquitetural parcial.
2. Risco de divergencia futura entre estrategia declarada e ordem efetiva.

### A4 - Caminhos auxiliares ainda podem consultar catalogos candidatos

Em alguns servicos auxiliares de resolucao/enriquecimento de CPU, ha tentativa por lista de candidatos de catalogo (base, contexto, fallback).

Efeito:

1. Respostas auxiliares podem nao refletir exatamente o mesmo baseline congelado do run.
2. Perde-se previsibilidade entre consulta de apoio e execucao oficial.

## Causa raiz

Ausencia de um contrato unico e auditavel para:

1. Precedencia de entradas de run.
2. Fonte de catalogo base por projeto/version.
3. Proveniencia de configuracoes aplicadas no run (incluindo toggles de policy).
4. Correspondencia obrigatoria entre estrategia de tipo de projeto e ordem de execucao.

## Objetivo

Garantir que dentro do projeto a execucao seja reproduzivel e governada por fonte de verdade explicita, com precedencia causal unica e auditavel.

## Decisao

Instituir contrato operacional unico de execucao por projeto, com os seguintes pilares:

### D1 - Fonte de catalogo de run com prioridade no projeto

Quando houver catalogo/snapshot resolvido no projeto (ou baseline congelado equivalente), ele deve ser a fonte primaria da execucao.
Uso de master deve ser fallback explicito, rastreado e bloqueavel por politica.

### D2 - Precedencia formal de skill_inputs

A precedencia oficial de entradas de run fica declarada e centralizada:

1. base skill_inputs do projeto;
2. overrides salvos (quando habilitado);
3. override ad hoc da requisicao;
4. injecoes de politica (somente quando contrato permitir).

### D3 - Propagacao ponta a ponta de toggles contratuais

Todo campo de controle presente no schema de API (ex.: use_mobilizacao_policy) deve atravessar rota, service e pipeline sem perda.

### D4 - Estrategia de projeto passa a governar ordem de skills

A sequencia efetiva de execucao deve ser derivada da estrategia de tipo de projeto, nao de definicoes paralelas.

### D5 - Proveniencia obrigatoria por run

Cada run deve registrar no minimo:

1. origem do catalogo base (project_snapshot, project_resolved, master_fallback);
2. hash/assinatura do baseline usado;
3. toggles aplicados;
4. versao de politica de precedencia.

## Escopo

### Incluido

1. Contrato de precedencia e proveniencia de run.
2. Correcao de propagacao de use_mobilizacao_policy.
3. Governanca de fonte de catalogo para run por projeto.
4. Alinhamento pipeline strategy com ordem efetiva de execucao.
5. Testes de regressao e nao-regressao para hot_project e project.

### Excluido

1. Mudanca de formulas de negocio de skills (fora da governanca de precedencia/fonte).
2. Reestruturacao completa de benchmarking.
3. Alteracao de UX sem impacto direto na governanca de execucao.

## Plano de implementacao

### Fase 1 - Contrato e bugfix de propagacao

1. Publicar contrato de precedencia de run.
2. Corrigir passagem de use_mobilizacao_policy da API ate run metadata.
3. Cobrir com teste unitario de rota/servico/pipeline.

### Fase 2 - Isolamento de catalogo por projeto

1. Introduzir resolvedor de baseline de run com prioridade no projeto.
2. Registrar fallback para master com codigo de auditoria.
3. Permitir modo estrito sem fallback para ambientes de validacao.

### Fase 3 - Unificacao da estrategia de execucao

1. Fazer pipeline consumir ordem de skills da PipelineStrategy.
2. Garantir paridade de comportamento por tipo de projeto.
3. Adicionar validacoes de integridade entre estrategia e execucao.

### Fase 4 - Hardening e observabilidade

1. Persistir proveniencia completa por run.
2. Expor dados de proveniencia nos endpoints de run/analysis.
3. Criar gate de regressao para bloquear drift de baseline.

## Criterio de aceite

1. Mesmo projeto + mesma versao + mesmas entradas => mesmos resultados, independente de mutacoes posteriores no master.
2. Campo use_mobilizacao_policy altera comportamento de injecao conforme solicitado pelo cliente.
3. Toda execucao possui origem de catalogo e hash de baseline auditaveis.
4. Pipeline hot_project e project executam ordem definida pela estrategia oficial.
5. Testes de regressao cobrindo AGIS e ao menos um cenario project passam sem drift.

## Riscos

1. Dependencia residual de codigo legado de resolucao em servicos auxiliares.
2. Quebra de compatibilidade em fluxos que dependiam de fallback implicito.
3. Custo inicial de migracao de testes para o novo contrato de precedencia.

## Mitigacoes

1. Rollout em modo observabilidade antes de modo estrito.
2. Feature flag para fallback controlado durante transicao.
3. Auditoria de diferencas por snapshot antes de hard cutover.

## Estado atual (2026-06-10)

### Resolvido desde a identificação

| Problema | Resolução |
|---|---|
| A3: `pipeline_strategy` não era fonte de verdade da ordem | ✅ `pipeline_strategy.py` agora usa `CANONICAL_SKILL_ORDER` derivado dos manifests TOML |
| `runtime.py` legacy com implementação duplicada | ✅ Deletado (1877 linhas removidas) — `runtime/__init__.py` é o único Runtime |
| `run_skill` com lógica duplicada vs `run_skill_on_plano` | ✅ `run_skill` delega para `run_skill_on_plano` via `FlatVersionStore` |
| `avancar_projeto` com lógica paralela | ✅ Deletado — `avancar_plano` é o caminho único |

### Pendente

| Problema | Status |
|---|---|
| A1: Snapshot de catálogo não é fonte primária obrigatória | ✅ `_load_resolved_catalogo` marca `_catalog_source` ("project_reference" vs "master"); propagado para `normalized["_catalog_source"]` — observabilidade sem modo estrito (2026-06-10) |
| A2: `use_mobilizacao_policy` não propagado end-to-end | ✅ `pipeline_service.py:215-221` lê o toggle e injeta/omite `mobilizacao_policies` em skill-04 — funcionando end-to-end |
| A4: Serviços auxiliares ainda podem consultar catálogos candidatos | ✅ Não aplicável — padrão de candidatos estava em `runtime.py` (deletado). Atual `catalog_resolver.py` não tem listas de candidatos |
| Auditoria de proveniência por run | ✅ `catalog_source` persistido em invocations.log em ambos os caminhos (`run_skill_on_plano` via `_build_log_entry`; `run_pipeline` via `_oas_log_invocation`) — 2026-06-10 |

## Evidências técnicas (estado atual)

1. `src/concilium/application/runtime/__init__.py` — Runtime canônico (único)
2. `src/concilium/application/runtime/mixins/execution.py` — `run_skill` → `run_skill_on_plano` (caminho único)
3. `src/concilium/presentation/api/routes/runs.py` — rota de execução
4. `src/concilium/presentation/api/schemas.py` — schema de request (inclui `use_mobilizacao_policy`)
5. `src/concilium/application/pipeline_strategy.py` — `CANONICAL_SKILL_ORDER` como fonte única
6. `src/concilium/infrastructure/storage/flat_version_store.py` — adaptador para projetos legados

---

## Invariantes Causais para ADR-106 (EquipeCustoEngine)

Esta seção define os contratos que o `LifecycleEngine` (ADR-106 F1) deve honrar.
São derivados da cadeia causal de skills e não podem ser violados sem regressão observável.

### IC-1 — Pré-condição de estado por fase de skill

Cada fase do engine pressupõe que as skills anteriores já popularam o canônico:

| Fase engine | Requer que skill-0X tenha rodado | Campo obrigatório no canônico |
|---|---|---|
| `DirectTeamCostStrategy` | skill-05 concluída | `equipes_diretas[*].custo_mao_obra_mensal` |
| `IndirectTeamCostStrategy` | skill-07 concluída | `indiretos[*].custo_mao_obra` |
| Decomposição instancial | ADR-085 (dentro de skill-05) | `equipes_diretas[*].custo_inst_mo is not None` |
| `fe_nec` / `gap_escala` | skill-06 concluída | `planejamento[*].subtotal.sem_bdi.total > 0` |

Violação de IC-1 resulta em divisão por zero silenciosa ou valores de `fe_nec` absurdos (> 10).

### IC-2 — Invariante de decomposição instancial

Para toda `EquipeDireta` com `custo_inst_mo is not None`:

```
|custo_inst_mo + custo_inst_eq + custo_inst_comb + custo_inst_mat + custo_inst_mob_demob
 − custo_total| < 0.05
```

Este invariante é validado em ADR-104 Checkpoint 3. O engine não pode reescrever
`custo_inst_*` sem atualizar `custo_total` correspondentemente.

### IC-3 — Monotonicidade de custo com encargos

`custo_total = custo_mao_obra_mensal + custo_encargos_mensal + custo_equipamentos_mensal
              + custo_combustivel_total_mensal + custo_material_mensal + custo_mob_desmob`

(NEP-037 D1). O engine deve preservar esta soma; qualquer redistribuição interna deve
ser neutra no total.

### IC-4 — Isolamento de catálogo por run

O engine deve receber o catálogo já resolvido pelo `_providers_factory` do runtime —
nunca carregar o catálogo master diretamente. Violação cria dependência de estado global
que compromete a reprodutibilidade (NEP-028 D1).

### IC-5 — Idempotência

`engine.calcular(equipe, catalogo) == engine.calcular(equipe, catalogo)` para o mesmo
estado de entrada. O engine não pode usar estado interno mutável entre chamadas.

### IC-6 — Não-interferência entre estratégias

`DirectTeamCostStrategy` e `IndirectTeamCostStrategy` operam sobre partições disjuntas
do canônico (`equipes_diretas` vs `indiretos`). Uma não pode alterar campos da outra.

## Resultado esperado

Ao final da NEP-028, a execução por projeto obedece um contrato causal único, com
baseline rastreável e reproduzível. O ADR-106 LifecycleEngine é a primeira implementação
que deve demonstrar conformidade com IC-1 a IC-6.
