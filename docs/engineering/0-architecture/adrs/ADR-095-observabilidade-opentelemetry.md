# ADR-095 — Observabilidade Agnóstica de Sink: OpenTelemetry para API e MCP

**Status:** APROVADO
**Data:** 2026-05-30
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-096 (Deploy Azure), ADR-094 (JWT Auth)

---

## Contexto

### Problema

P1. Com o deploy em produção (ADR-096), erros de pipeline, latência elevada e uso
indevido são invisíveis até que um usuário reclame. Não há como diagnosticar problemas
proativamente.

P2. A instrumentação acoplada a um vendor específico (ex: `azure-monitor-sdk` direto)
cria lock-in. Se a empresa migrar para Datadog ou Grafana Cloud, é necessário reescrever
toda a instrumentação.

P3. Não há métricas de uso por skill, por tool MCP ou por usuário. Sem isso, é
impossível priorizar otimizações ou identificar padrões de uso.

---

## Decisão

D1. **OpenTelemetry SDK como camada única.** Toda telemetria (traces, métricas, logs)
é emitida via OTEL SDK. O destino é configurado por variável de ambiente:

```
App → OTEL SDK → OTEL Collector → {Azure Monitor | Datadog | Grafana | ...}
```

Trocar de Azure Monitor para Datadog = trocar `OTEL_EXPORTER_OTLP_ENDPOINT`.

D2. **Três dimensões de telemetria.**

**Traces** — cada invocação de tool MCP gera um span:
```python
span.set_attribute("tool.name", tool_fn.__name__)
span.set_attribute("project.id", kwargs.get("project_id", "?"))
span.set_attribute("user.id", current_user.sub)
```

**Métricas**
```python
concilium.pipeline.skill.duration_ms{skill, status}
concilium.mcp.tool.calls{tool, status, scope}
concilium.pipeline.n_celulas_cubo{project_id}
concilium.artifacts.bundle_size_bytes{project_id}
```

**Logs estruturados** — campos obrigatórios: `trace_id`, `span_id`, `project_id`,
`user_id`, `severity`. Emitidos via OTEL Logs API (não `print`).

D3. **Decorator de tracing para tools MCP.**

```python
def _with_tracing(tool_fn):
    @wraps(tool_fn)
    def wrapper(*args, **kwargs):
        with tracer.start_as_current_span(tool_fn.__name__) as span:
            span.set_attribute("tool.name", tool_fn.__name__)
            try:
                result = tool_fn(*args, **kwargs)
                span.set_status(StatusCode.OK)
                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(StatusCode.ERROR, str(e))
                raise
    return wrapper
```

D4. **Alertas mínimos para produção.**
- Pipeline failure rate > 5% em 5min → **P1**
- Latência de tool call p99 > 30s → **P2**
- ACI CPU > 80% por > 2min → **P2** (warning de provisionamento)

D5. **Privacy by design.** Nenhum dado de projeto (quantitativos, preços, nomes
de atividades) entra em traces. Apenas metadados operacionais: IDs, durações,
status, contagens.

D6. **Sink inicial: Azure Monitor (Application Insights).** Configurável via
`OTEL_EXPORTER_OTLP_ENDPOINT` — pode ser substituído sem alterar código.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Azure Monitor SDK direto | Lock-in; trocar de sink exige reescrita |
| R2 | Logs apenas (sem traces/métricas) | Insuficiente para diagnosticar latência de skills individuais |
| R3 | Sem observabilidade no MVP | Inaceitável — produção sem visibilidade é operacionalmente cega |
| R4 | Sentry apenas | Cobre erros mas não latência nem métricas de uso |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Vendor-agnostic | Migrar destino de telemetria = trocar 1 variável de ambiente |
| Diagnóstico proativo | Alertas P1/P2 antes de usuário reportar problema |
| Visibilidade por skill | Identifica qual skill tem maior latência e onde otimizar |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Overhead de instrumentação (~1–3ms por span) | Sampling configurável para reduzir overhead em produção |
| Custo de armazenamento de telemetria | Retention de 30 dias por default; ajustável por tier de custo |
| OTEL Collector como dependência adicional | Usar in-process exporter como fallback simplificado |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | OTEL SDK instalado + in-process exporter configurado | 🟢 Implementado |
| 2 | Instrumentação automática FastAPI + decorator para tools MCP | 🟢 Implementado |
| 3 | Métricas de pipeline por skill | 🟢 Implementado |
| 4 | Sink Azure Monitor (Application Insights) configurado | 🔴 Pendente (ADR-096) |
| 5 | Dashboard + alertas P1/P2 no Azure Monitor | 🔴 Pendente (ADR-096) |

## Definition of Done

### Fase 1
- [ ] OTEL SDK inicializado no startup do container
- [ ] Spans gerados e visíveis no exporter local (dev mode)

### Fase 2
- [ ] Toda invocação de tool MCP gera span com `tool.name`, `project.id`, `user.id`
- [ ] FastAPI requests instrumentados automaticamente
- [ ] Logs estruturados com `trace_id` e `span_id`

### Fase 3
- [ ] Métricas `skill.duration_ms` e `mcp.tool.calls` exportadas
- [ ] Métricas verificadas em dev via Prometheus scrape ou OTEL local

### Fase 4
- [ ] Telemetria visível no Azure Application Insights em produção
- [ ] Dados de trace de uma execução de pipeline rastreáveis end-to-end

### Fase 5
- [ ] Dashboard com latência por skill, failure rate e uso por tool
- [ ] Alertas P1 e P2 configurados e testados (simulação de falha)

---

## Relacionados

[[adr096-deploy-azure-acr-aci-dns]] [[adr094-jwt-auth-layer]]
