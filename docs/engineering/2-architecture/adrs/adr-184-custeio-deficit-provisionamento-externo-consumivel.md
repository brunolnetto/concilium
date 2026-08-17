# ADR-184 — Custeio do Déficit de Estoque Provisionado Externamente + Cubo de Estoque Consumível no Relatório

**Status:** ✅ Implementado
**Data:** 2026-08-17
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-151 (provisionamento externo de déficit, D4 deixou o custeio fora de escopo), ADR-139 (origem de material, `preco_unitario=0.0` para `GERACAO_INTERNA`), ADR-128 (disponibilidade de recursos consumíveis, `Escopo.logistica_consumiveis`, cubo canônico F6)

---

## Contexto

### Problema

P1. A ADR-151 introduziu `DisponibilidadeConsumivel.deficit_provisionado_externamente` para resolver a **viabilidade de cronograma** de materiais `GERACAO_INTERNA` com demanda estrutural maior que a produção interna pareada — e explicitamente adiou o custeio dessa quantidade (D4: "problema genuíno mas distinto, deixado para uma ADR de continuação"). Hoje esse déficit existe, afeta o cronograma, gera o aviso `VAL-ESTOQUE-PROVISIONAMENTO-01` — e nunca vira R$ em lugar nenhum do resultado financeiro. Um material que precisou ser comprado fora do processo produtor-consumidor está sendo contabilizado como se tivesse custo zero (convenção de `GERACAO_INTERNA`, ADR-139 D1), o que subestima o custo real do projeto sempre que há provisionamento externo declarado.

P2. Investigação paralela (nesta sessão) confirmou que o **delay** de estoque (atividade atrasada por falta de material, ADR-128 D2) já impacta custo corretamente — via `makespan_weeks` pós-reparo, que alimenta custos indiretos por permanência em skill-06 (`_indiretos/skill.py`). Não há gap aí. O gap é estritamente o custo *direto* da quantidade provisionada externamente.

P3. O cubo canônico `CuboEstoqueConsumivel` (ADR-128 F6) — builder, projeção (`resolve_cubo_estoque_consumivel_projection`), endpoints MCP (`explorar_estoque_consumiveis`) e REST (`/cubo-estoque-consumivel/projecao`) — está pronto desde a implementação da F6, mas **nenhum entregável o consome**: zero call-sites em `application/runtime/deliverables/` ou em `application/skills/manifests/09-relatorio-e-artefatos/`. O relatório final do projeto não menciona estoque de consumíveis, mesmo quando há atrasos ou déficits relevantes. Outro cubo do mesmo tipo (`CuboRosterReal`) está no mesmo estado — não é bug isolado, é um padrão de "cubo pronto, nunca cabeado" que se repetiu.

---

## Decisão

### D1 — Preço do déficit é campo de projeto, simétrico a `deficit_provisionado_externamente`

Novo campo `preco_provisionamento_externo: float | None = None`, na mesma estrutura de override que já carrega `deficit_provisionado_externamente` (`Escopo.logistica_consumiveis[insumo_id]` → `_CAMPOS_DISPONIBILIDADE` em `replenishable_builder.py`). Não é campo de catálogo: o preço de um provisionamento emergencial/pontual é decisão de mercado e momento de compra, não um fato do insumo mestre — mesma lógica que levou a ADR-151 D2 a colocar o déficit em si no projeto.

### D2 — Custo bruto: `deficit_provisionado_externamente × (preco_provisionamento_externo ou 0.0)`, por recurso

Calculado uma vez por `resource_id` (o déficit da ADR-151 já é um escalar por recurso, não distribuído por semana/atividade — D2 não muda essa granularidade). Sem preço informado, custo é `0.0` — não trava nada, preserva o comportamento atual (ADR-151 já é `✅ Implementado`; esta ADR não pode regredir viabilidade de cronograma existente).

### D3 — Visibilidade: novo aviso `VAL-ESTOQUE-PROVISIONAMENTO-02`

Quando `deficit_provisionado_externamente > 0` e `preco_provisionamento_externo` está ausente, emite `AVISO` (ao lado do `VAL-ESTOQUE-PROVISIONAMENTO-01` existente) informando que o déficit está sendo contabilizado a custo zero por falta de preço declarado. Transparência em vez de assunção silenciosa — o mesmo princípio de D3 da ADR-151, agora aplicado ao custo em vez de à quantidade.

### D4 — BDI reaproveitado: alíquota de material, sem categoria nova

O custo do déficit entra na categoria de custo `deficit_estoque_externo`, mas usa a mesma alíquota de BDI já calculada para `material` (`_bdi("material")` em `_venda_custo.py`) — é custo de material por natureza (uma compra externa), não justifica uma sub-categoria de BDI própria.

### D5 — Cubo de estoque conectado ao relatório de skill-09, seguindo o padrão do `CuboPoolInstancial`

Nova seção `render_estoque_consumivel()` em `report_markdown_sections.py`, cabeada em `financial_report_markdown.py` logo após `render_pool_economia_origem`, chamando `resolve_cubo_estoque_consumivel_projection(canonical, face="resumo_por_recurso")` dentro de `try/except` (degrada graciosamente, mesmo padrão do pool). Novo builder de gráfico `visualizations/cube/estoque_temporal.py`, registrado em `_FACE_BUILDERS`. A face `resumo_por_recurso` ganha a coluna `custo_deficit_externo` (D2), fechando o laço entre o custo (D1-D4) e a visibilidade (D5) — o relatório passa a mostrar, por recurso, quanto custou o provisionamento externo.

Não é uma decisão nova de arquitetura de cubo — é aplicar a um cubo já pronto e isolado o mesmo mecanismo de conexão que `CuboPoolInstancial` já usa.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Preço vindo de um "material gêmeo `AQUISICAO_EXTERNA`" do mesmo insumo | Não existe convenção nem campo formalizado para essa relação (ADR-139/151 não a definem); exigiria heurística de nome/categoria frágil, e nem todo material `GERACAO_INTERNA` tem um gêmeo comprável cadastrado |
| A2 | Auto-inferir o preço de um índice de mercado externo (SICRO/referência) | Adiciona dependência de dado externo não solicitada; o preço de um provisionamento emergencial real tende a divergir de tabela de referência, e a ADR-151 já rejeitou automatismo equivalente (A3 daquela ADR) por mascarar julgamento humano |
| A3 | Bloquear o cronograma (gate) se déficit > 0 sem preço | Regrediria a viabilidade que a ADR-151 já resolve — o preço é dado financeiro adicional, não pré-requisito de exequibilidade física |
| A4 | Nova categoria de BDI dedicada para custo de déficit externo | Complexidade desproporcional ao caso — é custo de material adquirido, a alíquota de material já existe e se aplica |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Custo real do projeto deixa de omitir provisionamento externo | Fecha o gap deixado explicitamente em aberto pela ADR-151 D4 |
| Reaproveita infraestrutura já testada | `_CAMPOS_DISPONIBILIDADE`/`Escopo.logistica_consumiveis` (ADR-128 F5) e `_bdi("material")` (skill-06) já existem — nenhuma API nova |
| Cubo de estoque deixa de ser código morto para o usuário final | Primeiro cubo canônico "isolado" (ao lado de `CuboRosterReal`) a ser conectado a um entregável real |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Preço pode ser chute/estimativa do engenheiro, não valor de compra real | Mesma classe de risco que qualquer dado de entrada de projeto (mesmo argumento da ADR-151 para a quantidade); `VAL-ESTOQUE-PROVISIONAMENTO-02` só cobre ausência total, não qualidade do valor informado |
| `CuboRosterReal` continua isolado após esta ADR | Fora de escopo — mencionado só como precedente do padrão, não resolvido aqui |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `preco_provisionamento_externo` em `_CAMPOS_DISPONIBILIDADE`/override de projeto | ✅ |
| F2 | Cálculo de `custo_deficit_externo` por recurso + `VAL-ESTOQUE-PROVISIONAMENTO-02` | ✅ |
| F3 | `_build_custo_categorial_bottom_up` (skill-06) com nova chave `deficit_estoque_externo`, propagada por `_calc_venda_com_bdi` e exposta em `CustoTotal.deficit_estoque_externo` | ✅ |
| F4 | `render_estoque_consumivel()` no relatório de skill-09 + builder de gráfico `estoque_temporal.py`, face `resumo_por_recurso` com coluna `custo_deficit_externo` | ✅ |

## Definition of Done

### Fase 1-3
- [x] `preco_provisionamento_externo` aceita `None`/`float >= 0`; override via `logistica_consumiveis` funciona fim a fim
- [x] Custo do déficit calculado corretamente com/sem preço informado (0.0 quando ausente)
- [x] `VAL-ESTOQUE-PROVISIONAMENTO-02` emitido só quando déficit > 0 e preço ausente; ausente em qualquer outro caso (regressão zero sobre `VAL-ESTOQUE-PROVISIONAMENTO-01`)
- [x] `_build_custo_categorial_bottom_up` inclui `deficit_estoque_externo`; `_calc_venda_com_bdi` aplica `_bdi("material")` sobre essa chave; `CustoTotal.deficit_estoque_externo` exposto no resultado final
- [x] Baseline de custo dos benchmarks/golden existentes sem provisionamento externo declarado permanece bit-a-bit igual (déficit=0 → custo=0, sem efeito colateral) — suíte completa sem regressão

### Fase 4
- [x] `render_estoque_consumivel()` produz Markdown não-vazio quando há `ReplenishableResource`s no cronograma; seção omitida (sem exceção) quando não há
- [x] Face `resumo_por_recurso` do cubo expõe `custo_deficit_externo`
- [x] `estoque_temporal.py` registrado em `_FACE_BUILDERS`, com `try/except` interno (falha isolada não quebra os demais builders)
- [x] Suíte completa sem regressão; `uv run ty` e `uv run ruff` limpos

## Achado de implementação (fora do escopo original, corrigido junto)

Ao implementar F1-F4, dois gaps pré-existentes foram descobertos e corrigidos por estarem
na trajetória direta do trabalho (não são regressão desta ADR):

1. **`LogisticaConsumivelConfig` (Pydantic, `Escopo`) nunca espelhava `deficit_provisionado_externamente`**
   desde a implementação original da ADR-151 — `model_config = extra="ignore"` descartava
   silenciosamente o campo sempre que um escopo era lido de volta via `Escopo.model_validate()`.
   O caminho de agendamento em si não era afetado (lê o JSON cru de `inputs`, sem passar por
   este modelo), mas a leitura tipada do escopo (ex. auditoria/API) perdia o dado. Corrigido
   junto por ser o mesmo espelho que esta ADR já precisava estender.
2. **`DisponibilidadeConsumivelCanonical`/`CuboEstoqueConsumivelBuilder` (ADR-128 F6) não
   preservavam `deficit_provisionado_externamente`** no snapshot canônico — o builder do
   cubo reconstruía a projeção semanal (faces `estoque_temporal`/`fluxo_componente`) SEM o
   déficit, podendo mostrar estoque negativo para um recurso que o cronograma real já havia
   reparado via provisionamento externo. Corrigido porque afeta diretamente o cubo que esta
   ADR conecta ao relatório (Parte A) — sem o fix, a nova seção do relatório mostraria dado
   inconsistente com o cronograma real.

---

## Relacionados

- ADR-151 — Provisionamento Externo de Déficit em Materiais de Geração Interna (D4 abriu esta continuação)
- ADR-139 — Origem de Materiais Consumíveis e Produtor-Consumidor entre Atividades
- ADR-128 — Disponibilidade de Recursos Consumíveis (F6 cubo canônico, F5 `Escopo.logistica_consumiveis`)
