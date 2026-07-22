# ADR-146 — Contrato de Labels de Métricas para Conformação Dimensional

**Status:** Implementado
**Data:** 2026-07-21
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-095 (Telemetria OTel), ADR-112 (Pipeline Medallion), ADR-118 (Audit de Tools), ADR-087 (CuboAnalitico — precedente do padrão de cubo que a Gold de observabilidade vai seguir)

---

## Contexto

### Problema

P1. **Cada instrumento de métrica tagueia um subconjunto próprio de labels, sem contrato.** `record_skill_duration` emite `{"skill", "status"}`; `record_tool_call` emite `{"tool", "status"}`; `record_project_margin` emite `{"project.id", "pipeline.mode"}`; `record_rate_limit_exceeded` emite `{"route"}` (`infrastructure/telemetry/__init__.py`). Nenhum documento define quais chaves são canônicas — um instrumento futuro poderia emitir `skill_id` ou `toolName` e nada acusaria a divergência.

P2. **A Silver de metrics não projeta nenhuma dimensão.** `normalize_metric_record` gravava só `{metric_name, ts, value, labels, service}` — `DIM_SKILL`/`DIM_TOOL`/`DIM_PROJECT` (ERD Gold, sessão de 2026-07-20/21) eram inalcançáveis a partir de `FACT_METRIC_DATAPOINT` sem parsear o dict `labels` em cada consulta.

P3. **`record_tool_call` descarta contexto que já tem em mãos.** `_with_tracing` extrai `project_id = kwargs.get("project_id")` e o grava no span (`attrs["project.id"]`), mas a métrica `concilium.mcp.tool.calls` era emitida sem ele — chamadas de tool não eram fatiáveis por projeto em nenhuma camada de metrics.

### Restrição central

Este é o único gap do ERD cuja correção muda instrumentação já em produção. O desenho abaixo minimiza esse risco: **nenhuma chave de label existente é renomeada** (renomear quebraria continuidade de séries e a projeção retroativa sobre Bronze antigo) e a única adição é opcional e omitida quando ausente (sem série espúria `project.id=None`).

## Decisão

D1. **Chaves canônicas como constantes de módulo** em `infrastructure/telemetry/__init__.py`: `METRIC_LABEL_SKILL = "skill"`, `METRIC_LABEL_TOOL = "tool"`, `METRIC_LABEL_PROJECT = "project.id"`, `METRIC_LABEL_STATUS = "status"`. Os valores são exatamente os já emitidos historicamente. Todos os `record_*` passam a referenciá-las. Labels fora do contrato (`route`, `pipeline.mode`) continuam válidas — só não ganham coluna própria na Silver.

D2. **`record_tool_call(tool_name, status, project_id=None)`** — única mudança de comportamento. `_with_tracing` repassa o `project_id` que já extraía para o span. Quando ausente, o label dict é byte-idêntico ao histórico. Cardinalidade: tools × status × projetos efetivamente usados — limitada.

D3. **Projeção dimensional read-side em `normalize_metric_record`**: promove `labels["skill"]` → `skill_id`, `labels["tool"]` → `tool_name`, `labels["project.id"]` → `project_id` como colunas de primeira classe (None quando ausentes), mantendo `labels` íntegro. Retroativa sobre todo Bronze existente, já que as chaves canônicas são o que sempre foi emitido.

D4. **`silver_normalizer` permanece módulo puro** (zero imports do concilium): usa os literais com comentário apontando para o dono do contrato (telemetry), e um teste de conformidade (`test_telemetry_metric_label_contract.py::TestContractConformanceWithSilver`) solda os dois lados — se alguém mudar uma constante sem mudar a projeção (ou vice-versa), o teste quebra.

D5. **Fora de escopo, deliberadamente:**
- `project.id` em `concilium.pipeline.skill.duration_ms` — `SkillExecutor` é domain-agnostic por design ("all domain knowledge is injected through callbacks"); encanar projeto ali violaria essa arquitetura, e skill×projeto já é respondível por `FACT_SPAN` (spans de skill carregam `project.id` via `set_current_span_attrs`).
- `user.id` em qualquer métrica — cardinalidade cresce com a base de usuários, e a célula de `CuboMetricas` no ERD não o inclui; análise por usuário pertence a `FACT_SPAN`/`FACT_TOOL_INVOCATION`.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Renomear chaves para as colunas-alvo (`skill` → `skill_id` etc.) | Quebra continuidade de séries em qualquer consumidor OTLP e inutiliza a projeção retroativa sobre Bronze antigo — custo alto, ganho zero |
| A2 | Todo instrumento emite todas as dimensões (skill+tool+project em tudo) | Skill-duration não tem projeto em escopo sem violar o design do executor; labels vazias/None criariam séries espúrias |
| A3 | `silver_normalizer` importar as constantes de `telemetry` | Acoplaria um módulo hoje puro (zero imports) à máquina de settings/OTel; teste de conformidade dá a mesma garantia sem o acoplamento |
| A4 | Enriquecer via contextvar (projeto corrente) em vez de parâmetro explícito | Mágica implícita para resolver um caso que um parâmetro opcional resolve; contextvar de projeto não existe hoje |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Gap 2 do ERD Gold fechado | `DIM_SKILL`/`DIM_TOOL`/`DIM_PROJECT` alcançáveis de `FACT_METRIC_DATAPOINT` — último pré-requisito dos 4 cubos (CuboMetricas) resolvido |
| Retroativo | A projeção vale para dados já em Bronze/Silver, sem reprocessamento especial (próximo ciclo com `--full-reload` ou upsert natural reescreve o Silver com as colunas novas) |
| Contrato executável | Divergência futura entre write-side e read-side quebra teste, não aparece como coluna silenciosamente NULL em produção |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Séries existentes de `concilium.mcp.tool.calls` com projeto passam a ter um label a mais (split de série no ponto do deploy) | Gold agrega do zero a cada ciclo a partir dos data points; não há consumidor OTLP externo configurado em produção (Bronze é o consumidor) — sem dashboard a quebrar |
| Registros Silver antigos de metrics não têm as colunas novas até serem reescritos | `read_silver`/consultas devem usar `.get()` (já é o padrão); um `run --signal metrics --full-reload` normaliza tudo se necessário |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | Constantes canônicas + refactor dos `record_*` (comportamento idêntico) | ✅ Implementado |
| F2 | `record_tool_call` com `project_id` opcional + repasse em `_with_tracing` | ✅ Implementado |
| F3 | Projeção dimensional em `normalize_metric_record` + teste de conformidade | ✅ Implementado |

## Definition of Done

- [x] Constantes com os valores exatos de produção, testadas
- [x] `record_tool_call` sem `project_id` emite label dict byte-idêntico ao histórico (teste)
- [x] `_with_tracing` repassa `project_id` nos caminhos OK e ERROR (testes)
- [x] Projeção Silver promove as 3 chaves canônicas e só elas; `labels` preservado; `labels=None` seguro (testes)
- [x] Teste de conformidade soldando telemetry ↔ silver_normalizer sem import em runtime

---

## Relacionados

- ADR-095 — Telemetria OTel (instrumentos originais e política de privacidade D5 — apenas metadados operacionais)
- ADR-112 — Pipeline Medallion (Silver que recebe a projeção)
- ADR-087 — CuboAnalitico (padrão de cubo que a Gold de observabilidade seguirá; este contrato é o último pré-requisito do CuboMetricas)
- ERD Gold de observabilidade (artifact da sessão 2026-07-20/21) — gaps 1, 3, 4 fechados anteriormente; este ADR fecha o gap 2
