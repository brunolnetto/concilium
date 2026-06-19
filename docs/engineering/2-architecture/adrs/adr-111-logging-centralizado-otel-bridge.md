# ADR-111 — Logging Centralizado e Ponte Python → OTel

**Status:** Implementado ✅ _(F1–F5 2026-06-18 · TDD · 28 testes)_  
**Data:** 2026-06-18  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-095 (Observabilidade OTel), ADR-096 (Deploy Azure), ADR-110 (Remediação de Fallbacks — logging adicionado)

---

## Contexto

### Problema

P1. **Dimensão de logs da ADR-095 não implementada.**  
ADR-095 D2 declara logs estruturados com `trace_id`, `span_id`, `project_id`, `severity` como campos
obrigatórios, emitidos via OTEL Logs API. A função `setup_telemetry()` em
`infrastructure/telemetry/__init__.py` chama `_setup_tracing()` e `_setup_metrics()`, mas não existe
`_setup_logging()`. Toda a dimensão de logs está pendente.

P2. **Logging descentralizado e sem estrutura.**  
Após ADR-110, dezenas de módulos emitem `logger.warning/error` via `logging.getLogger(__name__)`.
Não há `basicConfig`, `dictConfig` nem JSON formatter configurado. Logs vão para stderr sem
`trace_id`, sem `span_id` e sem formato previsível — impossível correlacionar com spans do OTel.

P3. **Logs não chegam ao sink OTel (Azure Monitor / Datadog).**  
Sem `SdkLoggerProvider` configurado, os registros de `logger.warning("Função %s sem preco_unitario")`,
`logger.error("Falha ao resolver CPU %s")` etc. são invisíveis para o pipeline de observabilidade.
O operador não consegue alertar sobre degradação de dados de catálogo nem sobre falhas silenciosas
que antes eram engolidas.

P4. **Ausência de configuração de nível e formato por ambiente.**  
Dev precisa de output legível; produção precisa de JSON estruturado para ingestão; CI/testes precisam
de silêncio (ou WARNING mínimo). Hoje tudo usa o default do Python (WARNING, stderr, sem formato).

---

## Decisão

**D1 — Adicionar `_setup_logging()` a `infrastructure/telemetry/__init__.py`.**  
A função cria um `SdkLoggerProvider` com `OTLPLogExporter` (quando `OTEL_EXPORTER_OTLP_ENDPOINT`
está configurado) ou `ConsoleLogExporter` (quando `CONCILIUM__OTEL_CONSOLE=true`).
A chamada é adicionada a `setup_telemetry()` após `_setup_metrics()`.

```python
def _setup_logging() -> None:
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.sdk._logs import LoggerProvider
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor

    telemetry = get_telemetry()
    resource = _build_resource()
    log_provider = LoggerProvider(resource=resource)

    otlp_endpoint = telemetry.otlp_endpoint
    if otlp_endpoint:
        from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
        log_provider.add_log_record_processor(
            BatchLogRecordProcessor(OTLPLogExporter(endpoint=f"{otlp_endpoint}/v1/logs"))
        )
    elif _otel_console():
        from opentelemetry.sdk._logs.export import ConsoleLogExporter
        log_provider.add_log_record_processor(BatchLogRecordProcessor(ConsoleLogExporter()))

    set_logger_provider(log_provider)
```

**D2 — Ponte automática Python `logging` → OTel via `LoggingHandler` (SDK nativo).**  
`opentelemetry-instrumentation-logging` não está no conjunto de dependências do projeto.
Usa-se `LoggingHandler` do próprio `opentelemetry-sdk`, que é a alternativa oficial e já disponível:

```python
from opentelemetry.sdk._logs import LoggingHandler
handler = LoggingHandler(level=logging.WARNING, logger_provider=log_provider)
logging.getLogger().addHandler(handler)
```

`LoggingHandler` recebe `LogRecord` do root Python logger, converte para `OTel LogRecord`
(com `trace_id`/`span_id` do span ativo) e emite ao `LoggerProvider`.

A extração de `trace_id`/`span_id` para o `_JsonFormatter` (output JSON local) é feita diretamente
via `opentelemetry.trace.get_current_span()` — sem dependência de bibliotecas externas adicionais.

**D3 — Criar `infrastructure/observability/logging_config.py` com `configure_logging()`.**  
Função de configuração centralizada chamada no startup de cada entry point (API, CLI, MCP):

```python
def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configura o sistema de logging do Concilium.

    Em produção: JSON estruturado com campos OTel (trace_id, span_id, service).
    Em dev: formato humano colorido.
    Em CI/testes: WARNING mínimo, sem propagação ruído.
    """
    root = logging.getLogger()
    root.setLevel(level)

    if json_format:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        root.addHandler(handler)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
            datefmt="%H:%M:%S",
        )

    # Silenciar bibliotecas ruidosas
    for noisy in ("httpx", "httpcore", "urllib3", "azure", "opentelemetry.sdk"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
```

**D4 — `_JsonFormatter`: campos obrigatórios por ADR-095 D2.**

```python
class _JsonFormatter(logging.Formatter):
    """Emite JSON-lines com campos OTel mandatórios (trace_id, span_id, severity)."""

    FIELDS = ("trace_id", "span_id", "otelServiceName")

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "otelTraceID", ""),
            "span_id": getattr(record, "otelSpanID", ""),
            "service": getattr(record, "otelServiceName", "concilium"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
```

**D5 — Integração nos três entry points.**

| Entry point | Arquivo | Chamada |
|---|---|---|
| API | `presentation/api/app.py` (startup lifespan) | `configure_logging(json_format=not settings.debug)` |
| MCP | `presentation/mcp/server.py` | idem |
| CLI | `presentation/main.py` | `configure_logging(json_format=False)` |
| Testes | `conftest.py` | `configure_logging(level="WARNING", json_format=False)` |

**D6 — Hierarquia de namespaces `concilium.*`.**  
Todos os loggers do pacote seguem o padrão `logging.getLogger(__name__)`, que já produz a hierarquia
`concilium.application.benchmarks.analysis`, `concilium.domain.services.simulation`, etc.
Nenhuma alteração necessária nos módulos — a hierarquia já está correta por convenção.

**D7 — Convenção de severidade para os padrões da ADR-110.**

| Padrão | Severidade | Justificativa |
|---|---|---|
| Exceção engolida em operação estrutural | `ERROR` com `exc_info=True` | Impacto imediato no resultado; requer triagem |
| Dado ausente mascarando zero (insumo, BDI) | `WARNING` | Degradação de qualidade; não bloqueia |
| Fallback de fonte (produção, catálogo) | `DEBUG` | Esperado em casos de dados parciais |
| Conversão float falhou | `WARNING` | Dado malformado; pode inflar erro |

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | `python-json-logger` como dependência | Adiciona dependência para algo implementável em ~30 linhas internas |
| A2 | Manter logging sem configuração central | Logs da ADR-110 permanecem invisíveis para OTel; viola ADR-095 D2 |
| A3 | Instrumentar cada módulo com OTel SDK diretamente | Acoplamento; D2 se aplica a toda a pilha via bridge automática |
| A4 | Usar `structlog` | Quebra compatibilidade com `logging.getLogger(__name__)` já adotado em todo o codebase |
| A5 | `LoggingInstrumentor` (opentelemetry-instrumentation-logging) | Não está nas dependências do projeto; `LoggingHandler` do SDK nativo cobre o mesmo caso de uso sem dependência adicional |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| ADR-095 D2 completa | Logs estruturados com `trace_id`/`span_id` chegam ao Azure Monitor junto com spans/métricas |
| Correlação automática | `logger.error("Falha ao resolver CPU X")` aparece no mesmo trace da tool MCP que o chamou |
| Observabilidade dos fallbacks ADR-110 | `WARNING` de BDI ausente ou preco_unitario ausente gera alerta configurável |
| Zero mudança em módulos existentes | `logging.getLogger(__name__)` é o padrão; `LoggingInstrumentor` enriquece sem alterar chamadas |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `BatchLogRecordProcessor` pode atrasar shutdown em caso de erro de rede | Configurar `max_export_batch_size=512, export_timeout_millis=5000` |
| `otelTraceID` como string `"0000...0000"` quando não há span ativo | Filtrar no formatter: `if trace_id != "0" * 32: payload["trace_id"] = trace_id` |
| Logs de bibliotecas externas (httpx, azure) sobrecarregando sink | D3 já silencia ao nível WARNING |
| Custo de ingestão de logs no Azure Monitor | Filtrar severidade < WARNING antes do exporter; logs DEBUG apenas em console |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `_setup_logging()` em `infrastructure/telemetry/__init__.py` + `SdkLoggerProvider` | ⬜ Pendente |
| F2 | `infrastructure/observability/logging_config.py` com `configure_logging()` + `_JsonFormatter` | ⬜ Pendente |
| F3 | `LoggingHandler` adicionado ao root logger em `_setup_logging()` (via SDK nativo) | ✅ 2026-06-18 |
| F4 | Integração nos 3 entry points (API, MCP, CLI) + `conftest.py` | ✅ 2026-06-18 |
| F5 | Testes TDD: 28 testes cobrindo _JsonFormatter, configure_logging, _setup_logging, entry points | ✅ 2026-06-18 |

**Invariante de cada fase:** `pytest tests/` deve passar sem regressão.

---

## Definition of Done

### Fase 1–3
- [x] `setup_telemetry()` chama `_setup_logging()` quando OTel disponível
- [x] `SdkLoggerProvider` com `OTLPLogExporter` configurado quando `OTEL_EXPORTER_OTLP_ENDPOINT` presente
- [x] `LoggingHandler` (SDK nativo) adicionado ao root logger — `trace_id`/`span_id` extraídos via `get_current_span()` no `_JsonFormatter`

### Fase 4
- [x] `configure_logging()` chamado no startup da API (`create_app`), MCP (`build_server`) e CLI (`main.py`)
- [x] `conftest.py` chama `configure_logging(level="WARNING", json_format=False)` — testes silenciosos

### Fase 5
- [x] 28 testes TDD cobrindo todos os comportamentos: `_JsonFormatter`, `configure_logging`, `_setup_logging`, entry points
- [x] `test_trace_id_injected_when_span_active`: span ativo → `trace_id != ""` no JSON output
- [x] `pytest tests/` verde

---

## Relacionados

- ADR-095 — Observabilidade OpenTelemetry (spans + métricas — este ADR completa a dimensão logs)
- ADR-110 — Remediação de Fallbacks Silenciosos (origem dos logger.warning/error a serem capturados)
- ADR-096 — Deploy Azure (sink de destino: Azure Monitor Application Insights)
- ADR-112 — Pipeline Assíncrona de Observabilidade Medalhão (consumidor downstream dos logs OTel)
