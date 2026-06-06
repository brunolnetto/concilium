# Plano de Implementacao - NEP-028 Governanca de precedencia causal e isolamento de catalogo por projeto

**Referencia:** [NEP-028](../neps/nep-028-governanca-precedencia-causal-e-isolamento-catalogo-projeto.md)  
**Data:** 2026-05-23  
**Objetivo:** tornar a referencia de execucao do projeto isolada do master, com precedencia causal explicita e auditavel.

---

## Problema que este plano resolve

1. A execucao ainda pode ser influenciada por mutacoes do master corrente.
2. Toggles contratuais como `use_mobilizacao_policy` nao atravessam a cadeia de chamada de forma uniforme.
3. A estrategia de tipo de projeto precisa governar a execucao real, nao apenas validar pre-condicoes.

## Fase 1 - Contrato de execucao e propagacao de toggles

### Entregas

1. Propagar `use_mobilizacao_policy` da API ate o run persistido.
2. Registrar o toggle no payload do run para auditoria e reproducibilidade.
3. Garantir que a montagem de inputs do pipeline respeite o toggle persistido.

### Checklist de implementacao

- [x] Atualizar `RunProjectRequest` para carregar o toggle explicitamente no fluxo.
- [x] Atualizar rotas de run e rerun para repassar o campo ao service.
- [x] Atualizar `ConciliumService` para repassar o campo ao pipeline.
- [x] Atualizar `PipelineService` para persistir e usar o toggle no run.
- [x] Adicionar teste unitario para provar que `False` desabilita a injecao.

### Critério de aceite

1. Um request com `use_mobilizacao_policy=False` nao injeta `mobilizacao_policies` no skill 04.
2. O run persistido preserva o toggle recebido.
3. O comportamento segue deterministico em sync e async.

## Fase 2 - Baseline do projeto como fonte primaria

### Entregas

1. Definir fonte primaria de catalogo por projeto/version.
2. Bloquear fallback implícito para master quando o baseline do projeto existir.
3. Registrar a proveniencia do baseline em cada run.

### Checklist de implementacao

- [x] Preferir `benchmark_reference.catalog` como baseline congelado do projeto.
- [x] Persistir `catalogo_base_origem` e `catalogo_base_hash` no `resolved_catalog.json`.
- [x] Registrar proveniencia do baseline no run.
- [x] Cobrir o baseline do projeto com teste unitario de regressao.

### Critério de aceite

1. Mesma versao de projeto produz o mesmo resultado mesmo com mutacoes posteriores no master.
2. Cada run informa a origem do catalogo usado.

## Fase 3 - Estrategia de execucao por tipo de projeto

### Entregas

1. Fazer a ordem efetiva de execucao seguir `PipelineStrategy`.
2. Endurecer os checks de integridade entre tipo de projeto e sequencia de skills.

### Checklist de implementacao

- [x] Passar a sequencia da estrategia do service para o runtime como contrato explicito.
- [x] Fazer o runtime montar o conjunto ativo de skills a partir da sequencia oficial.
- [x] Manter o bootstrap de `01-escopo-e-eap` condicionado ao estado inicial.
- [x] Cobrir a propagacao da sequencia com spy de teste.

### Critério de aceite

1. `hot_project` e `project` usam a sequencia oficial da estrategia.
2. Testes de regressao garantem que a estrategia nao diverge da execucao.

## Riscos conhecidos

1. Fallbacks residuais em servicos auxiliares podem continuar produzindo divergencia de apoio.
2. O isolamento estrito pode expor contratos historicamente dependentes do master.
3. A observabilidade precisa estar pronta antes do bloqueio definitivo.

## Validacao recomendada

1. Teste unitario de API para confirmar propagacao do toggle.
2. Teste unitario de `PipelineService` para confirmar respeito ao toggle.
3. Validacao de regressao em benchmark representativo apos o corte da Fase 1.
