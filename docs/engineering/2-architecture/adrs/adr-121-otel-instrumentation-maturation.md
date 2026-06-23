# ADR-121 — Maturação da Instrumentação OpenTelemetry: Logs, Propagação e Baggage

**Status:** Implementado ✅  
**Data:** 2026-06-23  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-095 (OTel), ADR-111 (structured logging), ADR-112 (Medallion pipeline), ADR-099 (RBAC/JWT middleware)

---

## Contexto

### Auditoria de sinais OTel (junho 2026)

Uma auditoria sistemática dos quatro primitivos OTel — Traces, Metrics, Logs, Baggage — revelou
as seguintes lacunas de cobertura:

**Logs (Partial — gap crítico de nível)**

P1. `LoggingHandler` configurado em `logging.WARNING`. INFO e DEBUG, que carregam a maioria dos
eventos operacionais (decisões de scheduling, progresso da pipeline, queries de catálogo), são
silenciosamente descartados do sink OTel. O APM recebe apenas exceções e alertas.

P2. `BronzeLogHandler` foi implementado em `bronze_writer.py` (ADR-112 F1), mas nunca conectado
ao sistema de logging Python. O pipeline Medallion Bronze→Silver→Gold não recebe eventos ao vivo —
só processa blobs já gravados.

P3. `_JsonFormatter` não captura o campo `fallback_type` (ADR-110) mesmo quando presente no
`extra` do registro. Fallbacks de CP-SAT → MINSLK e relaxamentos de pool são invisíveis
no Silver normalizado.

**Traces (Partial — propagação ausente)**

P4. `McpAuthMiddleware` extrai JWT e seta contextvars de identidade, mas não lê os headers
W3C `traceparent`/`tracestate`. Cada request MCP inicia um novo root span desconectado
de qualquer trace upstream, impedindo visibilidade end-to-end em APM.

P5. Transições de estado dentro de skills — algoritmo selecionado, CP-SAT resolvido, fallback
ativado — não emitem `span.add_event()`. O trace mostra "skill executou em X ms" mas não "o que
aconteceu durante esses X ms".

**Baggage (Absent)**

P6. Zero uso de `opentelemetry.baggage`. `tenant_id` e `user_id` são contextvars task-local
hoje: evaporam em fronteiras de task e não cruzam chamadas de serviço. Downstream, cada serviço
precisa re-autenticar ou re-extrair esses valores independentemente.

---

## Decisão

Três fases ordenadas por relação impacto/esforço, cada uma com entregas testadas via TDD.

### Fase 1 — Cobertura de Logs

**D1 — LoggingHandler em DEBUG**

O bridge `LoggingHandler` (Python logging → OTel LogRecords) passa de `logging.WARNING` para
`logging.DEBUG`. Permite que INFO e DEBUG atravessem até o OTLP sink.

Justificativa: a maioria dos eventos operacionais está em INFO. O custo de volume é gerenciado
pelo `BatchLogRecordProcessor` (já configurado) e pelo sampling do coletor OTel no ambiente
de produção — não na fonte.

**D2 — `fallback_type` no `_JsonFormatter`**

Quando um `logging.LogRecord` carregar `fallback_type` no dict de extras, `_JsonFormatter.format()`
inclui o campo no JSON emitido. Nenhum outro campo de `extra` é incluído automaticamente —
apenas `fallback_type`, pois faz parte do vocabulário ADR-110 e alimenta o Silver normalizado.

**D3 — `BronzeLogHandler` conectado ao `configure_logging()`**

`configure_logging()` aceita um parâmetro opcional `bronze_storage: BlobStoragePort | None`.
Quando fornecido, instancia `BronzeLogHandler(BronzeWriter(storage, "logs"))` e o adiciona
ao root logger. A adição é idempotente: remove instâncias prévias antes de adicionar.

### Fase 2 — Propagação de Contexto de Trace

**D4 — Extração de `traceparent`/`tracestate` no `McpAuthMiddleware`**

Antes de despachar para o app interno, o middleware extrai o contexto OTel dos headers HTTP via
`opentelemetry.propagate.extract()` e chama `context.attach()`. O token é preservado e
`context.detach()` é chamado no `finally`. Falhas de extração são silenciosas (best-effort):
se o header estiver ausente ou malformado, o span continua como root span normal.

**D5 — `span.add_event()` nas decisões de scheduling**

Em `explore_schedules()`, três eventos de span são emitidos no span ativo:
- `scheduling.algorithm.selected` com atributos `algorithm`, `n_activities`, `deadline_weeks`
- `scheduling.solution.found` com atributos `algorithm`, `makespan_weeks`, `quality_score`
- `scheduling.solution.failed` com atributos `algorithm`, `error` (quando ScheduleError é levantada)

Esses eventos são emitidos com `trace.get_current_span().add_event()`. Se não houver span ativo
(OTEL_SDK_DISABLED ou fora de um contexto instrumentado), a chamada é no-op — sem impacto
em testes ou desenvolvimento.

### Fase 3 — Baggage

**D6 — Injeção de `tenant_id` e `user_id` como membros W3C Baggage**

Imediatamente após decodificar o JWT e antes de despachar para o app interno,
`McpAuthMiddleware` injeta:

```
Baggage: tenant.id=<tid>, user.id=<sub>
```

via `opentelemetry.baggage.set_baggage()`. O contexto com baggage é `attach()`-ado e
`detach()`-ado no `finally`. Valores ausentes no token (None) são omitidos do baggage.

Benefício imediato: qualquer serviço downstream que propague `traceparent` + `Baggage`
pode ler `tenant.id` sem re-autenticar. O pipeline de observabilidade cross-domain
pode filtrar logs Silver por tenant sem depender do campo `user_id` injetado por contextvar.

---

## Consequências

**Positivas:**
- Pipeline Medallion Bronze recebe eventos ao vivo após D3
- INFO-level operacional visível no APM após D1 (scheduling, catálogo, pipeline)
- `fallback_type` alimenta Gold fallback-rate por skill após D2
- Traces MCP conectados ao trace upstream do cliente após D4
- Decisões de scheduling rastreáveis dentro de um span após D5
- `tenant_id`/`user_id` disponíveis em qualquer span filho após D6

**Restrições mantidas:**
- Nenhum valor de parâmetro de tool ou dado de projeto entra em qualquer sinal OTel (ADR-095 D5)
- Todos os patches são best-effort: falha OTel nunca bloqueia fluxo principal
- `OTEL_SDK_DISABLED=true` em CI/testes — sem efeito colateral de telemetria nos testes

**Fora de escopo (backlog):**
- Injeção de `traceparent` em chamadas HTTP outbound (SharePoint, S3, Azure) — requer
  instrumentação de cada cliente HTTP; planejado como ADR-122
- Views e exemplares OTel (histogramas com samples ligados a traces) — planejado como ADR-123
- RED metrics por endpoint de API — planejado junto com ADR-122
