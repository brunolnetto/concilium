# NEP-027: Centralização das inferências de benchmark em camada única

**Status:** Concluída  
**Prioridade:** 🔴 Crítico  
**Área:** Arquitetura e Skills  
**Tipo:** Governança + Refactor  
**Esforço:** XL  
**Identificado em:** 2026-05-23

---

## Contexto

A execução de benchmark está funcional, mas as inferências de baseline (BDI, confrontos de referência, overrides e sinalizadores de modo benchmark) estão distribuídas entre loader, runner, report builder e skills.

Esse acoplamento distribuído aumenta o risco de drift semântico entre:

1. inferência de entrada,
2. cálculo de skill,
3. projeção de relatório,
4. auditoria de discrepância.

O custo é conhecido: cada ajuste pontual tende a produzir novo efeito colateral em outro estágio.

## Problema Observado

Atualmente há inferência de benchmark em múltiplos pontos:

1. `src/concilium/application/benchmarks/runner.py`
- Injeta `benchmark_mode` para skills (06 e 08).

2. `src/concilium/application/benchmarks/spec_loader.py`
- Monta `extra_inputs` com regras específicas de benchmark.

3. `src/concilium/application/benchmarks/_spec_loader_helpers_b.py`
- Deriva `tabela_bdi` para skill 06.
- Deriva `bdi_indireto_efetivo` para skill 08 a partir da referência.

4. `src/concilium/application/benchmarks/report_builder.py`
- Reinterpreta referência para confronto e aplica fallback/normalização.

5. `src/concilium/application/skills/manifests/06-precificacao-unitaria/skill.py`
- Regras internas condicionadas por `benchmark_mode`.

6. `src/concilium/application/skills/manifests/08-consolidacao-financeira/_skill_helpers_a.py`
- Consome override de benchmark (`bdi_indireto_efetivo`) em cálculo financeiro.

## Causa Raiz

Ausência de um contrato único e explícito de "inferências de benchmark", com:

1. schema tipado,
2. origem por campo,
3. precedência formal,
4. consumo uniforme por skill.

Hoje, a precedência está implícita em código espalhado.

## Objetivo

Criar uma camada central única para inferências de benchmark, removendo lógica inferencial distribuída em helpers de skills e adaptadores de relatório.

## Decisão

Instituir o artefato canônico `BenchmarkInferencePack` no domínio de benchmark, com responsabilidade exclusiva por derivar e publicar inferências.

### D1 — Contrato canônico

Criar modelo tipado com no mínimo:

1. `benchmark_mode: bool`
2. `pricing_baseline`: regras de skill 06 (ex.: uso de `precos_unitarios_sbdi`, `planejamento_item_overrides`)
3. `bdi_inference`: tabela/rates/fonte/regime/overrides derivados
4. `consolidacao_inference`: campos efetivos para skill 08 (ex.: `bdi_indireto_efetivo`)
5. `reference_projection`: campos canônicos de confronto (direto, indireto, total, venda)
6. `trace`: evidências de origem por campo (`source_path`, `rule_id`, `fallback_applied`)

### D2 — Fonte única de derivação

Toda inferência sai de um único serviço:

`BenchmarkInferenceService.derive(reference, canonical_context, policy)`

Nenhum outro módulo poderá inferir benchmark ad hoc.

### D3 — Skills consomem contrato pronto

Skills 06/08 não devem "adivinhar" comportamento de benchmark.
Devem apenas consumir campos explícitos do pack.

### D4 — Report builder sem reinterpretação ad hoc

`report_builder` deve usar `reference_projection` já normalizada pelo pack, removendo múltiplos fallbacks internos.

### D5 — Política versionada

A precedência de inferência deve ficar em política versionada (`benchmark_inference_policy_version`), permitindo auditoria reprodutível entre execuções históricas.

## Escopo

### Incluído

1. Contrato tipado do pack.
2. Serviço central de derivação.
3. Adaptação de runner/spec_loader/report_builder para consumir pack.
4. Remoção progressiva de inferências distribuídas.
5. Testes de regressão por benchmark (AGIS, CTC, VALE, ROSH, ODFJELL, PRIVATE_LOG).

### Excluído

1. Mudança de fórmula de negócio em skills (fora do que já está aprovado por ADR).
2. Mudança de formato de referência de planilha.
3. Reescrita completa de análise/auditoria fora da fronteira de inferência.

## Plano de Implementação

### Fase 1 — Contrato e serviço

1. Criar `BenchmarkInferencePack` e `BenchmarkInferenceService`.
2. Portar inferências de `_spec_loader_helpers_b.py` e `report_builder.py` para o serviço.
3. Emitir `trace` por campo inferido.

#### Progresso da Fase 1 (2026-05-23)

- [x] `BenchmarkInferencePack` criado com policy version e `trace` de inferência.
- [x] `BenchmarkInferenceService` criado com derivação central de:
	- projeção canônica da referência para confronto,
	- `bdi_indireto_efetivo` para skill 08,
	- injeção padrão de `benchmark_mode` para skills 06/08.
- [x] Runner integrado ao serviço central de inferência.
- [x] Report Builder integrado ao serviço central de inferência.
- [x] `spec_loader` deixou de carregar inferência residual de benchmark.
- [x] Testes unitários TDD iniciais adicionados para serviço de inferência.
- [x] Validação end-to-end AGIS executada com flag V2 ativa (status APROVADO, deltas estáveis).

### Fase 2 — Integração com pipeline

1. Runner passa a derivar pack no início.
2. Spec loader injeta somente dados brutos; sem inferência de negócio.
3. Skills 06/08 recebem campos prontos do pack.

#### Progresso da Fase 2 (2026-05-23)

- [x] Runner passou a derivar `BenchmarkInferencePack` uma única vez por execução.
- [x] Runner aplica inferências nas entradas de skill via `apply_to_skill_inputs`.
- [x] Report Builder passou a consumir `reference_projection` do pack (sem re-derivar quando já disponível).
- [x] Fluxo unificado centralizado aplicado como caminho único.
- [x] Execução AGIS validada com flag V2 ativa (status APROVADO e deltas estáveis).
- [x] Evidência multi-cenário coletada (12 benchmarks): paridade `legacy` vs `v2` no `BENCHMARK_SUMMARY` (`diff_count = 0`).

### Fase 3 — Strangler e limpeza

1. Desligar inferências legadas e manter apenas o fluxo centralizado.
2. Rodar side-by-side (v1 vs v2) em benchmarks críticos.
3. Remover código legado após estabilidade.

#### Progresso da Fase 3 (2026-05-23)

- [x] Iniciada remoção controlada de duplicação no `BenchmarkReportBuilder`.
- [x] `BenchmarkReportBuilder` passou a priorizar `BenchmarkInferenceService` como fonte primária de `reference_projection`, mantendo fallback local como contingência.
- [x] Fallback local remanescente removido no `BenchmarkReportBuilder`.
- [x] Gate final de paridade por snapshot (legado vs v2) concluído em 12/12 projetos (`diff_count = 0`).
- [x] Evidência registrada em `artifacts/audit/benchmark_snapshot_parity.json`.
- [x] Feature flag removida; implementação nova centralizada tornou-se caminho único.
- [x] Regressão completa executada com task `run-all-benchmarks` em todos os 12 cenários.
- [x] Evidência consolidada em `BENCHMARK_SUMMARY.json` com contagem final: `{'APROVADO': 1, 'INVIAVEL/AVISO': 11}`.

### Encerramento Oficial (hard cutover)

Em 2026-05-23, a migração foi oficialmente encerrada com hard cutover concluído.

Condições de encerramento atendidas:

1. Caminho legado removido e fluxo centralizado estabelecido como implementação única.
2. Paridade legado vs novo comprovada por snapshot em 12/12 projetos (`diff_count = 0`).
3. Regressão completa executada para todos os cenários com geração de sumário consolidado.
4. Cenário AGIS permaneceu `APROVADO` com deltas estáveis no confronto.

## Critério de Aceite

1. Existe exatamente um ponto de derivação inferencial de benchmark.
2. `runner`, `spec_loader`, `report_builder` não contêm fallback inferencial duplicado.
3. Skills 06/08 consomem inferências explícitas, sem heurística local de benchmark.
4. Resultado AGIS mantém delta <= 0.01% em custo direto, indireto e preço de venda.
5. Cada campo crítico de inferência possui `trace` auditável.

## Riscos

1. Regressão silenciosa por mudança de precedência implícita atual.
2. Falsa sensação de neutralidade se policy não for versionada.
3. Aumento inicial de complexidade durante período de dual-run.

## Mitigações

1. Testes de snapshot em `benchmark_report.json` e `pipeline_integrity.json` por slug.
2. Reexecução de regressão completa (`run-all-benchmarks`) como gate obrigatório para mudanças futuras na inferência central.
3. Mapa de precedência formal em documentação versionada.

## Evidências Técnicas (estado atual)

1. `src/concilium/application/benchmarks/runner.py`
2. `src/concilium/application/benchmarks/spec_loader.py`
3. `src/concilium/application/benchmarks/_spec_loader_helpers_b.py`
4. `src/concilium/application/benchmarks/report_builder.py`
5. `src/concilium/application/skills/manifests/06-precificacao-unitaria/skill.py`
6. `src/concilium/application/skills/manifests/08-consolidacao-financeira/_skill_helpers_a.py`
7. `docs/engineering/2-development/implementation_plan/benchmark_runner_strangler_fig_plan.md`

## Resultado esperado

Ao final da NEP-027, inferência de benchmark deixa de ser um comportamento emergente do código distribuído e passa a ser um contrato explícito, auditável e versionado.