# ADR-050 - CLI Unificada para Projeto e Benchmark com Data Source Versionado

**Status:** Implementado  
**Data:** 2026-05-14  
**Contexto:** MendesLobo Construtora - Concilium

---

## Contexto

### Problema

A operacao de validacao e benchmark ainda apresenta friccao de uso e assimetria de interfaces:

- P1 - A CLI possui comandos separados para projeto e benchmark, com semantica de parametros e saida diferentes.
- P2 - Nao existe contrato unico para saida de validacao de PU em modos projeto e benchmark.
- P3 - O benchmark usa dados em `benchmarks/data`, mas isso nao esta explicitamente modelado como data source de projeto, dificultando comparacao direta e rastreio.
- P4 - Ha debito de sincronia documental: decisoes de pipeline e benchmark evoluem mais rapido que a taxonomia da CLI.

---

## Decisao

### D1 - Introduzir superficie unificada de comando para validacao

Padronizar uma familia unica de comandos de validacao, com namespace comum:

- `concilium validate project`
- `concilium validate benchmark`
- Alias de compatibilidade em PT-BR: `concilium validate projeto`

Todos os modos devem expor o mesmo contrato de saida minima:

- identificador de alvo (project_id ou benchmark_slug)
- resumo de convergencia (verde, amarelo, vermelho)
- lista de validacoes com codigo, status e mensagem
- metadados de origem (contexto, versao, timestamp)

### D2 - Definir BenchmarkDataSource como conceito explicito

Formalizar `benchmarks/data/<slug>` como data source versionado de benchmark, com metadados:

- slug
- contexto
- referencia utilizada
- hash de entrada
- data de extracao

### D3 - Compatibilidade progressiva

Manter comandos antigos por uma janela de transicao e emitir aviso de deprecacao orientando para o namespace `validate`.

### D4 - Escopo separado para benchmark aninhado em projeto

A ideia de executar benchmark aninhado em projeto (projeto como agregador de benchmark data source) e valida, mas altera modelo de ciclo de vida e governanca de artefatos. Essa mudanca deve ser tratada em ADR proprio (fora do escopo deste ADR).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| X1 | Manter CLIs distintas sem contrato comum | Mantem friccao e aumenta custo de automacao/observabilidade. |
| X2 | Unificar apenas output, sem unificar comandos | Ajuda parcialmente, mas preserva descoberta ruim e semantica fragmentada. |
| X3 | Implementar benchmark aninhado agora | Eleva risco de regressao sem discutir governanca e versionamento em detalhe. |

---

## Consequencias

### Positivas

| ID | Consequencia |
|---|---|
| C1 | UX previsivel: mesmos argumentos e mesmo formato de saida por modo. |
| C2 | Menor custo de integracao com CI/CD e dashboards. |
| C3 | Melhor rastreabilidade de benchmark por data source versionado. |
| C4 | Reduz debito de sincronia entre operacao real e documentacao de arquitetura. |

### Negativas / Riscos

| ID | Risco | Mitigacao |
|---|---|---|
| R1 | Quebra de scripts antigos | Alias de compatibilidade e aviso de deprecacao por ciclo definido. |
| R2 | Crescimento de complexidade no parser CLI | Introduzir por fases com contrato minimo obrigatorio e testes de regressao. |
| R3 | Ambiguidade entre benchmark e projeto em casos hibridos | Tratar hibrido em ADR posterior com semantica explicita. |

---

## Plano de Implementacao

| Fase | Entregas | Status |
|---|---|---|
| F1 | Contrato comum de saida para validate project/benchmark | Implementado |
| F2 | Namespace `validate` + alias `projeto` + mensagens de deprecacao | Implementado |
| F3 | Metadados de BenchmarkDataSource e serializacao em relatorio | Implementado |
| F4 | Testes de integracao CLI para project/benchmark | Parcialmente Implementado |
| F5 | ADR sucessor para benchmark aninhado em projeto | Aceito |

---

## Definition of Done

### Fase 1
- [x] Comandos `validate project` e `validate benchmark` ativos.
- [x] Alias `validate projeto` ativo.
- [x] Mesmo schema de saida JSON para os dois modos.

### Fase 2
- [x] Metadados de BenchmarkDataSource incluidos na saida.
- [x] Comandos legados com aviso de deprecacao.
- [ ] Testes de regressao passando em ambiente local e CI.

### Fase 3
- [x] Novo ADR aberto para benchmark aninhado em projeto.

---

## Dependencias

- ADR-036 (reorganizacao da CLI)
- ADR-043 (benchmark application layer)
- ADR-048 (API/UI para iteracao rapida)
- ADR-049 (validacao convergente de PU como caso de uso principal da unificacao)

---

## Evidencias de Implementacao

- Namespace de CLI criado: `concilium validate project|benchmark|projeto`.
- Contrato de resposta unificado com campos `target_type`, `target_id`, `source`, `resumo_convergencia`, `validacoes`.
- Compatibilidade progressiva: comando legado `concilium benchmark validate` mantido com aviso de deprecacao para `concilium validate benchmark`.
