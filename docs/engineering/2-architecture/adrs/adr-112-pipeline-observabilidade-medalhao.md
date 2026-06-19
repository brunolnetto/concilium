# ADR-112 — Pipeline Assíncrona de Observabilidade: Arquitetura Medalhão com Backfill-Incremental

**Status:** Parcialmente Implementado _(F1–F6 ✅ 2026-06-19 · TDD · 40 testes · F7-F8 pendentes)_  
**Data:** 2026-06-18  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-095 (OTel), ADR-111 (Logging Bridge), ADR-047 (Blob Storage), ADR-096 (Deploy Azure)

---

## Contexto

### Problema

P1. **Sinais OTel são emitidos mas não processados analiticamente.**  
ADR-095 e ADR-111 produzem spans, métricas e logs estruturados. O OTLP Collector entrega esses dados
ao Azure Monitor, mas não há pipeline própria para:
- Detectar padrões de degradação ao longo do tempo (ex: taxa de `WARNING` de BDI ausente crescendo)
- Calcular SLIs (Service Level Indicators) por skill, por projeto, por semana
- Fazer backfill de dados históricos quando o pipeline esteve offline
- Cruzar logs de fallback (ADR-110) com resultados financeiros do mesmo run

P2. **Dados de observabilidade isolados de dados de negócio.**  
Logs de `logger.warning("Função X sem preco_unitario")` e spans de `concilium.skill.05` existem em
silos separados dos resultados de benchmark. Não é possível responder: "quantos warnings de dado
ausente ocorreram nos últimos 30 runs do AGIS?" ou "qual a correlação entre a taxa de fallback e o
desvio do custo direto?".

P3. **Sem mecanismo de backfill ao retomar após interrupção.**  
Se o pipeline de processamento fica offline (manutenção, deploy), os dados acumulados no OTLP
Collector/Blob não têm como ser processados retroativamente de forma idempotente e ordenada.
Reprocessar do zero (full-reload) é ineficiente; ignorar (skip) perde observabilidade.

P4. **Azure Monitor não expõe API de query adequada para análise cross-domain.**  
O Kusto Query Language (KQL) do Azure Monitor é poderoso para telemetria, mas não permite cruzar com
dados de projetos Concilium (canonical, benchmark results) sem exportar para uma camada intermediária.

---

## Decisão

### Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRODUÇÃO (ADR-095/111)                      │
│  API + MCP + CLI → OTel SDK → OTLP Collector → Azure Monitor    │
│                                        ↓                         │
│                              OTLP HTTP/gRPC export               │
└─────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA BRONZE — Ingestão Raw (ADR-047: Azure Blob Storage)      │
│  /observability/bronze/{signal_type}/{date}/{batch_id}.ndjson    │
│  Append-only, sem transformação, schema OTel bruto (OTLP JSON)   │
│  Retenção: 90 dias                                               │
└─────────────────────────────────────────────────────────────────┘
                                   ↓  async worker (Δ-incremental)
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA SILVER — Normalização e Correlação (DuckDB + Parquet)    │
│  /observability/silver/{signal_type}/{year}/{month}/part-*.parquet│
│  Schema enforced · trace_id/span_id joins · dedup por event_id   │
│  Retenção: 1 ano                                                  │
└─────────────────────────────────────────────────────────────────┘
                                   ↓  async worker (tumbling window)
┌─────────────────────────────────────────────────────────────────┐
│  CAMADA GOLD — Agregações e SLIs (DuckDB views)                  │
│  /observability/gold/sli_diario.parquet                          │
│  /observability/gold/fallback_rate_por_skill.parquet             │
│  /observability/gold/alertas_ativos.json                         │
│  Retenção: indefinida (dados pequenos, agregados)                │
└─────────────────────────────────────────────────────────────────┘
                                   ↓
┌─────────────────────────────────────────────────────────────────┐
│  CONSUMIDORES                                                    │
│  · CLI: `concilium pipeline observability report`               │
│  · API: GET /observability/sli                                   │
│  · DuckDB queries cross-domain (Gold ⋈ benchmark canonical)     │
└─────────────────────────────────────────────────────────────────┘
```

**D1 — Bronze: ingestão raw com particionamento por data e tipo de sinal.**  
O OTLP Collector (ou exporter in-process) escreve batches em NDJSON (newline-delimited JSON) no
Azure Blob Storage sob a estrutura:

```
/observability/bronze/logs/2026-06-18/batch-{uuid}.ndjson
/observability/bronze/traces/2026-06-18/batch-{uuid}.ndjson
/observability/bronze/metrics/2026-06-18/batch-{uuid}.ndjson
```

Regra: **append-only, nunca sobrescrever**. Cada arquivo é imutável. O `batch_id` é UUID v4 gerado
no momento da escrita. Isso garante idempotência no backfill: processar o mesmo arquivo duas vezes
é detectado via `event_id` (span_id ou log record id) na camada Silver.

**D2 — Silver: normalização assíncrona com `Δ-incremental` (checkpoint por arquivo).**  
Um worker Python assíncrono (`ObservabilityWorker`) processa arquivos Bronze não processados:

```python
class ObservabilityWorker:
    """Worker assíncrono Bronze → Silver."""

    async def run(self, signal_type: str, since: datetime | None = None) -> None:
        checkpoint = self._load_checkpoint(signal_type)
        blobs = await self._list_blobs_since(signal_type, checkpoint.last_processed_path)
        async for blob in blobs:
            records = await self._read_ndjson(blob)
            df = self._normalize(signal_type, records)
            await self._upsert_silver(signal_type, df)
            self._save_checkpoint(signal_type, last_processed_path=blob.path, ts=blob.modified)
```

O checkpoint (`observability/checkpoints/{signal_type}.json`) contém:
```json
{
  "signal_type": "logs",
  "last_processed_path": "bronze/logs/2026-06-18/batch-abc.ndjson",
  "last_processed_ts": "2026-06-18T14:23:00Z",
  "records_processed": 42817
}
```

**D3 — Backfill-Incremental (Fast-Forward).**  
Quando o worker é reiniciado após interrupção, ele:
1. Lê o checkpoint para saber o `last_processed_path`
2. **Fast-forward**: lista todos os blobs Bronze com path lexicograficamente > `last_processed_path`
3. Processa apenas os novos blobs (nunca re-lê blobs já checkpointados)
4. Se o checkpoint não existe (primeiro run ou `--full-reload`), processa desde o início

```
Timeline:  [B1][B2][B3][B4][B5][B6]
Checkpoint: ............^
Fast-forward:            [B4][B5][B6]  ← apenas novos
```

A idempotência na Silver é garantida por `upsert` via `event_id` como chave: se o mesmo blob for
acidentalmente processado duas vezes (checkpoint corrompido), o `event_id` deduplicará.

**D4 — Incremental: janela deslizante com lag configurável.**  
Para o processamento Silver → Gold (agregações), usa-se uma janela deslizante de processamento
com `lag_minutos` (default: 15min) para garantir que eventos atrasados ainda sejam incluídos antes
do fechamento da janela:

```
Agora: 14:30
Janela aberta: 14:00–14:15  (fechada, lag expirado — pode ser agregada)
Janela em aberto: 14:15–14:30  (ainda pode receber eventos, aguardar lag)
```

O Gold é atualizado por `INSERT OR REPLACE` particionado por `(date, hour_bucket)`.

**D5 — Schema Silver por tipo de sinal.**

**logs:**
```
event_id TEXT PK, trace_id TEXT, span_id TEXT, ts TIMESTAMP,
severity TEXT, logger TEXT, message TEXT, service TEXT,
project_id TEXT, skill_id TEXT, fallback_type TEXT
```

**traces (spans):**
```
span_id TEXT PK, trace_id TEXT, parent_span_id TEXT,
service TEXT, operation TEXT, start_ts TIMESTAMP, end_ts TIMESTAMP,
duration_ms INTEGER, status TEXT, project_id TEXT, skill_id TEXT
```

**metrics:**
```
metric_name TEXT, ts TIMESTAMP, value DOUBLE,
labels JSON, service TEXT
```

**D6 — Gold: SLIs calculados pelo pipeline.**

| Tabela Gold | Agregação | Frequência |
|---|---|---|
| `sli_diario` | p50/p95/p99 de `skill.duration_ms` por `(date, skill_id)` | Diária |
| `fallback_rate_por_skill` | COUNT(WARNING onde `fallback_type IS NOT NULL`) / COUNT(*) por `(date, skill_id)` | Diária |
| `alertas_ativos` | Skills com `p99_ms > 30000` ou `fallback_rate > 0.05` nas últimas 24h | A cada ciclo |
| `cross_domain` | JOIN com benchmark `canonical.resultado.custo_direto` por `project_id + run_date` | Semanal |

O campo `fallback_type` no schema Silver (logs) é preenchido a partir do `logger.name` e `message`
via regex de classificação: `"preco_unitario"`, `"bdi_ausente"`, `"cpu_fallback"`, etc. — tornando
rastreáveis exatamente os padrões catalogados na ADR-110.

**D7 — Implementação assíncrona: módulo `infrastructure/observability/pipeline.py`.**

```
infrastructure/
  observability/
    __init__.py
    logging_config.py      ← ADR-111
    pipeline.py            ← este ADR: ObservabilityWorker, checkpoints, Silver/Gold writers
    bronze_writer.py       ← escrita de batches OTLP em Blob Storage
    silver_normalizer.py   ← parsing OTLP JSON → schema Silver
    gold_aggregator.py     ← DuckDB queries Bronze→Silver→Gold
    checkpoint_store.py    ← leitura/escrita de checkpoints JSON
```

**D8 — CLI command: `concilium pipeline observability`.**

```bash
concilium pipeline observability run              # incremental desde último checkpoint
concilium pipeline observability run --full-reload # backfill completo (apaga checkpoints)
concilium pipeline observability run --since 2026-06-01  # fast-forward desde data
concilium pipeline observability status           # mostra último checkpoint por sinal
concilium pipeline observability report           # exibe tabelas Gold no terminal
```

**D9 — Execução como job assíncrono no ACI (ADR-102/103).**  
O pipeline de observabilidade pode ser executado como um job periódico separado no ACI, independente
do servidor principal, com schedule: a cada 15min para Bronze→Silver, a cada hora para Silver→Gold.
Isso mantém o servidor da API sem overhead de processamento de observabilidade em background.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Apache Spark / Databricks | Overhead de infra incompatível com escala atual; DuckDB local suficiente |
| A2 | Processar diretamente do Azure Monitor via KQL | Sem suporte a joins cross-domain com dados de projeto; lock-in de query language |
| A3 | Full-reload a cada execução | Ineficiente à medida que o histórico cresce; O(n) em vez de O(Δ) |
| A4 | Streaming em tempo real (Azure Event Hub) | Complexidade prematura; batch incremental com 15min lag é suficiente para alertas |
| A5 | Armazenar Silver em Azure SQL | DuckDB + Parquet é suficiente, zero-ops, compatível com análise ad-hoc local |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Correlação log-resultado | Query Gold ⋈ canonical: "benchmarks com alta taxa de BDI fallback têm desvio de custo acima de 5%?" |
| Backfill sem duplicação | Fast-forward garante processamento exatamente-uma-vez por arquivo Bronze, sem planejar reprocessamento manual |
| Alertas próprios | `alertas_ativos.json` dispensa dependência do Azure Monitor para alertas operacionais de qualidade de dados |
| DuckDB in-process | Gold queries rodam localmente sem infra adicional; exportável para qualquer ferramenta BI via Parquet |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Latência de 15min para alertas | Aceita para alertas de qualidade de dados; alertas críticos de infra continuam via Azure Monitor (ADR-095) |
| Checkpoint corrompido | Idempotência por `event_id` na Silver torna reprocessamento seguro; `--full-reload` como escape hatch |
| Crescimento do Parquet Silver | Particionamento por `(year, month)` + compressão Snappy; retenção de 1 ano configurável |
| Regex de classificação `fallback_type` frágil | Testar contra corpus real de logs antes de ativar Gold; fallback_type = NULL para logs não classificados |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `bronze_writer.py`: OTLP batch → Blob Bronze + `BronzeLogHandler` | ✅ 2026-06-19 |
| F2 | `checkpoint_store.py`: leitura/escrita/deleção de checkpoints JSON | ✅ 2026-06-19 |
| F3 | `silver_normalizer.py`: normalização + `classify_fallback_type` (padrões ADR-110) | ✅ 2026-06-19 |
| F4 | `ObservabilityWorker`: fast-forward, upsert por event_id, full-reload | ✅ 2026-06-19 |
| F5 | `gold_aggregator.py`: DuckDB → `sli_diario`, `fallback_rate_por_skill`, `alertas_ativos` | ✅ 2026-06-19 |
| F6 | CLI command `concilium observability run/status/report` | ✅ 2026-06-19 |
| F7 | Job ACI periódico: 15min Bronze→Silver, 1h Silver→Gold | ⬜ Pendente |
| F8 | Cross-domain Gold: JOIN observabilidade × canonical por `project_id + run_date` | ⬜ Pendente |

**Invariante:** cada fase tem teste de integração local (sem Azure) usando mock BlobStorage.

---

## Definition of Done

### Fase 1–4
- [ ] Bronze gravado em estrutura correta após run de pipeline
- [ ] Checkpoint criado/atualizado após processamento Silver
- [ ] Fast-forward: segunda execução processa 0 novos registros quando não há novos blobs Bronze
- [ ] `--full-reload` apaga checkpoints e reprocessa todo o Bronze sem duplicar Silver (upsert by event_id)

### Fase 5
- [ ] `sli_diario` populado com p50/p95/p99 de duration_ms por skill
- [ ] `fallback_rate_por_skill` populado com taxa de warnings de fallback (ADR-110 patterns)
- [ ] `alertas_ativos` emitido quando p99 > 30s ou fallback_rate > 5%

### Fase 6
- [ ] `concilium pipeline observability run` executa pipeline incremental
- [ ] `concilium pipeline observability status` exibe checkpoints
- [ ] `concilium pipeline observability report` exibe tabela Gold no terminal

### Fase 8
- [ ] Query cross-domain: benchmarks AGIS/RFI com fallback_rate > threshold identificáveis

---

## Relacionados

- ADR-095 — Observabilidade OpenTelemetry (fonte de sinais para o Bronze)
- ADR-111 — Logging Centralizado (garante que logs chegam ao OTel e portanto ao Bronze)
- ADR-047 — SharePoint/Blob Storage (backend de persistência Bronze + Silver + Gold)
- ADR-102 — Pipeline Jobs Assíncronos (padrão de job periódico para o worker ACI)
- ADR-103 — Jobs na Camada de Aplicação (localização do `ObservabilityWorker` na arquitetura)
- ADR-110 — Remediação de Fallbacks (origem dos `fallback_type` classificados no Gold)
