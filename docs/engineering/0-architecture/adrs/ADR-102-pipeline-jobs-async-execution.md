# ADR-102: Pipeline Jobs — Execução Assíncrona de Skills via MCP

**Status:** ✅ Implementado (v1.2 — Migrado para Application Layer)  
**Data:** 2026-06-03  
**Última atualização:** 2026-06-03 (v1.2)  
**Autor:** Sistema  
**Contexto:** MCP Tools, Developer Experience  
**Relacionado:** [ADR-103: Jobs na Camada de Aplicação](./ADR-103-jobs-application-layer.md)

> ✅ **Migração completa para ADR-103:** Implementação movida de `presentation/mcp_server/` para `application/jobs/` para permitir reuso por API REST e melhor separação de responsabilidades. Ver [ADR-103](./ADR-103-jobs-application-layer.md) para detalhes.

---

## Problema

Skills de pipeline (especialmente otimização RCPSP em `04-cronograma`) podem demorar 30-120 segundos para executar. A tool `avancar_pipeline` atual é **síncrona** — bloqueia o cliente MCP (Claude Desktop, VS Code Copilot) enquanto aguarda a resposta.

**Impactos negativos:**
- Cliente MCP aparece "travado" durante execução
- Timeouts de 60s no Claude Desktop ao inicializar conexão
- Experiência ruim de desenvolvedor — usuário não sabe se sistema está funcionando
- Impossível paralelizar execução de múltiplas skills

**Casos afetados:**
- `04-cronograma` (solver RCPSP): 20-90s dependendo da complexidade
- `05-financeiro` (BDI + pool): 5-15s
- `02-produtividade-climatica` (análise temporal): 2-8s

---

## Decisão

Implementar sistema de **jobs assíncronos em memória** para execução de pipeline via MCP, com três pilares de robustez:

### 1. Novas Tools MCP

1. **`disparar_pipeline(...)`** (recomendada)
   - Dispara skill em background via worker pool
   - Retorna `job_id` + posição na fila
   - Não bloqueia cliente

2. **`consultar_job_pipeline(job_id)`**
   - Consulta status: `AGUARDANDO_FILA` | `EM_EXECUCAO` | `CONCLUIDO` | `ERRO`
   - Retorna progresso incremental (mensagem + percentual)
   - Retorna resultado quando `CONCLUIDO`

3. **`listar_jobs_pipeline(project_id)`**
   - Lista todos os jobs (filtrado por projeto opcional)
   - Estatísticas agregadas por status

4. **`obter_estatisticas_jobs()`**
   - Configuração do sistema (max workers, TTL, GC interval)
   - Health check (worker pool ativo, GC rodando)
   - Contadores em tempo real

5. **`avancar_pipeline(...)`** [DEPRECATED]
   - Mantida para compatibilidade retroativa
   - Marcada como deprecated na documentação

### 2. Worker Pool com Limite de Concorrência

**Implementação:** `ThreadPoolExecutor` com `max_workers` configurável

```python
MAX_CONCURRENT_JOBS = int(os.getenv("CONCILIUM__MAX_CONCURRENT_JOBS", "3"))
_EXECUTOR = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS)
```

**Comportamento:**
- Jobs submetidos com `executor.submit(_executar_pipeline_async, job_id)`
- Fila FIFO gerenciada automaticamente pelo executor
- Status `AGUARDANDO_FILA` → `EM_EXECUCAO` quando worker disponível

**Vantagens:**
- Previne sobrecarga de CPU com muitos jobs simultâneos
- Fila automática sem código adicional
- Thread pool reutilizado (não cria/destrói threads)

### 3. Progresso Incremental

**Implementação:** Sistema de callbacks para skills reportarem progresso

```python
def _criar_progress_callback(job_id: str) -> Callable[[str, float | None], None]:
    """Cria callback de progresso para uma skill."""
    def callback(mensagem: str, percentual: float | None = None) -> None:
        _atualizar_job(job_id, progresso=mensagem, progresso_percentual=percentual)
    return callback
```

**Uso (futuro — quando skills suportarem callbacks):**
```python
# Dentro da skill
progress_callback("Construindo grafo RCPSP...", 0.3)
# ... solver roda ...
progress_callback("Otimizando makespan...", 0.7)
```

**Estado atual:**
- Callback criado e passível de ser injetado nas skills
- Skills atuais ainda não reportam progresso
- Framework pronto para integração futura

### 4. Garbage Collection Automático

**Implementação:** Thread daemon que remove jobs finalizados antigos

```python
JOB_TTL_HOURS = int(os.getenv("CONCILIUM__JOB_TTL_HOURS", "24"))
GC_INTERVAL_MINUTES = int(os.getenv("CONCILIUM__JOB_GC_INTERVAL_MINUTES", "60"))

def _garbage_collector_loop():
    """Loop que limpa jobs CONCLUIDO/ERRO há mais de TTL horas."""
    while not _GC_STOP_EVENT.wait(timeout=GC_INTERVAL_MINUTES * 60):
        _limpar_jobs_expirados()
```

**Lógica:**
- A cada `GC_INTERVAL_MINUTES`, verifica jobs finalizados
- Remove jobs com `finalizado_em < (agora - TTL)`
- Log de limpeza em stderr para auditoria
- Não remove jobs `EM_EXECUCAO` ou `AGUARDANDO_FILA`

**Configuração:**
- `CONCILIUM__JOB_TTL_HOURS=24` (default)
- `CONCILIUM__JOB_GC_INTERVAL_MINUTES=60` (default)

### Modelo de Dados (Job)

```python
{
    "job_id": "job-abc123",
    "status": "EM_EXECUCAO",  # AGUARDANDO_FILA | EM_EXECUCAO | CONCLUIDO | ERRO | CANCELADO
    "project_id": "rodovia-ce040-lote09",
    "skill_id": "04-cronograma",
    "inputs": {"num_equipes_por_item": {...}},
    "escopo_id": "esc-01",
    "plano_id": "plano-baseline",
    "disparado_em": "2026-06-03T19:45:00Z",
    "iniciado_em": "2026-06-03T19:45:01Z",
    "finalizado_em": "2026-06-03T19:45:45Z",
    "resultado": {...},  # resposta da skill quando CONCLUIDO
    "erro": None,  # mensagem quando ERRO
    "progresso": "Resolvendo RCPSP... 45%",  # mensagem textual
    "progresso_percentual": 0.45,  # 0.0 a 1.0
    "state_machine": <PipelineJobStateMachine>  # (v1.1+) gerencia transições
}
```

**State Machine (v1.1+):**
```python
from concilium.presentation.mcp_server.pipeline_job_state import PipelineJobStateMachine

# Transições válidas
AGUARDANDO_FILA --iniciar()--> EM_EXECUCAO --completar(resultado)--> CONCLUIDO
                                          --falhar(erro)--------> ERRO
                --cancelar()-------------> CANCELADO
```

**Hooks automáticos:**
- `on_iniciar()`: Atualiza `iniciado_em`, `progresso`, `progresso_percentual`
- `on_completar(resultado)`: Atualiza `finalizado_em`, `resultado`, `progresso`
- `on_falhar(erro)`: Atualiza `finalizado_em`, `erro`
- `on_cancelar(motivo)`: Atualiza `finalizado_em`, `erro`

### Arquitetura

```
Cliente MCP (Claude/VSCode)
    ↓
disparar_pipeline() → Job criado → ThreadPoolExecutor
    ↓                                   ↓
job_id retornado                   Fila FIFO (max 3 workers)
    ↓                                   ↓
consultar_job_pipeline()  ←────  Worker executa skill
    ↑                                   ↓
    └──────── Callback de progresso ───┘

GC Thread (daemon)
    ↓
A cada 60 min: limpa jobs finalizados > 24h
```

---

## Alternativas Consideradas

### 1. **Celery / Redis Job Queue**
❌ Complexidade excessiva para requisito atual  
❌ Requer infraestrutura adicional (Redis/RabbitMQ)  
✅ Persistência de jobs  
✅ Escalabilidade horizontal  

**Decisão:** Overhead não justificado para MVP. Considerar no futuro se houver necessidade de:
- Jobs persistentes entre reinicializações
- Fila de prioridade
- Execução distribuída

### 2. **FastAPI Background Tasks**
❌ Limitado ao lifecycle do request HTTP  
❌ Não adequado para MCP stdio transport  
✅ Integração nativa com FastAPI  

**Decisão:** Não aplicável — MCP usa stdio, não HTTP requests.

### 3. **Python asyncio**
❌ Requer refatoração massiva do código existente (síncrono)  
❌ Complexidade em coordenação de I/O  
✅ Mais "pythônico" para async  

**Decisão:** Threading simples é suficiente — skills são CPU-bound, não I/O-bound.

---

## Consequências

## Consequências

### ✅ Positivas

1. **Melhor experiência de desenvolvedor**
   - Cliente MCP não bloqueia
   - Feedback imediato ao disparar job
   - Progresso em tempo real (quando skills suportarem callbacks)
   - Fila visível com posição do job

2. **Controle de recursos**
   - Worker pool limita concorrência (máx 3 jobs simultâneos)
   - Previne sobrecarga de CPU em projetos grandes
   - GC automático previne memory leak

3. **Observabilidade**
   - Tool `obter_estatisticas_jobs()` para diagnóstico
   - Logs de GC para auditoria
   - Métricas agregadas por status

4. **Compatibilidade retroativa**
   - `avancar_pipeline` mantida (deprecated)
   - Código cliente existente continua funcionando

5. **Implementação robusta**
   - ThreadPoolExecutor padrão da stdlib
   - GC automático configúravel
   - Sistema de callbacks extensível

### ⚠️ Trade-offs

1. **Jobs não persistem**
   - Reiniciar servidor MCP perde jobs em execução
   - Aceitável: servidor raramente reinicia e usuário pode re-disparar
   - **Mitigação:** Mensagem de erro menciona TTL

2. **Concorrência limitada**
   - Máximo 3 jobs simultâneos (configurável)
   - Jobs aguardam na fila se pool cheio
   - **Mitigação:** `listar_jobs_pipeline` mostra estatísticas de fila

3. **Progresso ainda não integrado nas skills**
   - Framework de callbacks implementado
   - Skills não reportam progresso internamente ainda
   - **Mitigação:** Progresso básico (0%, 10%, 100%) já funciona
   - **Próximo passo:** Integrar callbacks nas skills (RCPSP solver, BDI)

### ❌ Limitações Conhecidas

1. **Race conditions em writes concorrentes do mesmo projeto**
   - Múltiplos jobs podem corromper estado do ProjectStore
   - **Workaround:** Documentar que usuário deve aguardar skill anterior
   - **Mitigação futura:** Implementar lock por project_id

2. **Memória cresce com jobs ativos**
   - GC só remove após finalizar + TTL
   - Projetos com centenas de jobs podem consumir RAM
   - **Mitigação:** TTL configurável, GC em 60 min

3. **Sem persistência de fila**
   - Jobs `AGUARDANDO_FILA` perdidos ao reiniciar
   - **Mitigação:** Status do job indica posição na fila

---

## Decisões de Design

### Threading vs Multiprocessing
**Escolha:** Threading com `ThreadPoolExecutor`  
**Motivo:** 
- Skills são CPU-bound mas OR-Tools libera GIL durante solver
- Threading compartilha memória (importante para ProjectStore)
- Pool reutiliza threads (mais eficiente que spawning)
- Fila FIFO automática gerenciada pelo executor

### Storage em Memória vs Persistente
**Escolha:** Memória (dict + lock)  
**Motivo:** 
- Simplicidade de implementação
- Servidor MCP reinicia raramente em desenvolvimento
- Produção usa API HTTP (onde jobs podem ser persistidos futuramente)
- GC automático previne memory leak

### Worker Pool Size
**Default:** 3 workers concorrentes  
**Motivo:**
- Skills são CPU-bound (cronograma = 30-90s de CPU intenso)
- 3 workers deixa 1 core livre para I/O e outros processos
- Configurável via `CONCILIUM__MAX_CONCURRENT_JOBS`

### Job TTL
**Default:** 24 horas após finalização  
**Motivo:**
- Tempo suficiente para usuário consultar resultado
- Previne acúmulo indefinido de jobs
- Configurável via `CONCILIUM__JOB_TTL_HOURS`

### GC Interval
**Default:** 60 minutos  
**Motivo:**
- Não precisa ser muito frequente (jobs vivem 24h)
- Reduz overhead de limpeza
- Configurável via `CONCILIUM__JOB_GC_INTERVAL_MINUTES`

### Job ID Format
**Formato:** `job-{uuid4().hex[:12]}`  
**Exemplo:** `job-a3f8b2c91d04`  
**Motivo:** Curto, único, fácil de copiar/colar em terminal.

---

## Documentação Atualizada

- ✅ Tutorial (`AGENT_SKILL_TUTORIAL.md`) — seção "Fluxo 2 — Execução do pipeline"
- ✅ Tabela de ferramentas MCP (36 → 40 tools)
- ✅ Seção "Erros comuns" — timeout e job não encontrado
- ✅ Docstrings das tools com exemplos de uso
- ✅ Variáveis de ambiente documentadas no código

---

## Próximos Passos (Futuro)

### 1. Integração de Progresso nas Skills ⏳

**Status:** Framework pronto, integração pendente

Modificar skills para receber e usar `progress_callback`:

```python
# Em concilium/application/skills/cronograma.py
def executar(ctx: SkillContext, progress_callback: Callable | None = None):
    if progress_callback:
        progress_callback("Construindo grafo RCPSP...", 0.2)
    # ... construir grafo ...
    if progress_callback:
        progress_callback("Resolvendo RCPSP...", 0.5)
    # ... solver ...
    if progress_callback:
        progress_callback("Pós-processamento...", 0.9)
```

**Impacto:** UX muito melhor — usuário vê progresso real em vez de "Executando..."

### 2. Lock por Project ID 🔒

**Problema:** Jobs concorrentes do mesmo projeto podem corromper estado

**Solução:**
```python
_PROJECT_LOCKS: dict[str, threading.Lock] = {}

def _executar_pipeline_async(job_id: str):
    project_id = job["project_id"]
    with _get_or_create_project_lock(project_id):
        # ... execução ...
```

**Impacto:** Permite múltiplos jobs de projetos diferentes sem serializar tudo

### 3. Persistência Opcional 💾

**Flag:** `CONCILIUM__JOBS_PERSIST=1`

**Storage:** SQLite local (`~/.concilium/jobs.db`)

```sql
CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY,
    status TEXT,
    project_id TEXT,
    payload JSON,
    created_at TIMESTAMP,
    ...
);
```

**Impacto:** Jobs sobrevivem reinicializações do servidor

### 4. Prioridade de Jobs 🚀

**Caso de uso:** Jobs de benchmark (lentos) com prioridade baixa

```python
disparar_pipeline(..., priority="HIGH")  # default: NORMAL
```

**Implementação:** `PriorityQueue` em vez de FIFO do executor

---

## Referências

- ADR-095: Observability (OpenTelemetry) — compatível com tracing de jobs
- ADR-099: RBAC — jobs herdam permissões de `project:run`
- ADR-101: MCP Apps — futura integração com UI de progresso real-time

---

## Configuração

Variáveis de ambiente para tunning do sistema:

```bash
# Máximo de jobs executando simultaneamente (default: 3)
export CONCILIUM__MAX_CONCURRENT_JOBS=5

# Tempo de vida de jobs finalizados em horas (default: 24)
export CONCILIUM__JOB_TTL_HOURS=48

# Intervalo de garbage collection em minutos (default: 60)
export CONCILIUM__JOB_GC_INTERVAL_MINUTES=30
```

**Recomendações:**
- **Desenvolvimento:** `MAX_CONCURRENT_JOBS=2` (máquina pessoal)
- **Servidor dedicado:** `MAX_CONCURRENT_JOBS=5` (8+ cores)
- **CI/CD:** `MAX_CONCURRENT_JOBS=1` + `JOB_TTL_HOURS=1` (execução limpa)

---

**Decisão:** ✅ Aprovado e implementado  
**Implementado:** 2026-06-03  
**Status:** ✅ Completo com extensões (worker pool, GC, progresso)  
**Revisão:** Q4 2026 após 6 meses de uso em produção

---

## Changelog

### 2026-06-03 — v1.2 (Migração para Application Layer)

**Refatoração arquitetural:**
- ✅ **ADR-103 implementada** — Lógica movida para `application/jobs/`
  - ✅ `application/jobs/models.py` — DTOs (JobDTO, JobListDTO, JobStatsDTO, SystemStatsDTO)
  - ✅ `application/jobs/state.py` — State machine (movida de presentation/)
  - ✅ `application/jobs/repository.py` — Repository pattern (JobRepository + InMemoryJobRepository)
  - ✅ `application/jobs/service.py` — JobService com casos de uso
  - ✅ `application/jobs/__init__.py` — Public API exports
- ✅ MCP tools atualizadas para usar `get_job_service()`
- ✅ Arquivos removidos de `presentation/mcp_server/`: `pipeline_jobs.py`, `pipeline_job_state.py`

**Benefícios arquiteturais:**
- ✅ **Clean Architecture:** Jobs na camada correta (application vs presentation)
- ✅ **Reusabilidade:** API REST pode usar `get_job_service()` diretamente
- ✅ **Testabilidade:** Injeção de dependências no JobService
- ✅ **Repository Pattern:** Persistência abstraída (fácil migrar para Redis/SQLite)

**Ver:** [ADR-103: Jobs na Camada de Aplicação](./ADR-103-jobs-application-layer.md) para detalhes completos da migração.

---

### 2026-06-03 — v1.1 (Refatoração com State Machine)

**Implementado:**
- ✅ Máquina de estados formal com `python-statemachine`
  - Classe `PipelineJobStateMachine` gerencia transições de estado
  - Estados: `AGUARDANDO_FILA`, `EM_EXECUCAO`, `CONCLUIDO`, `ERRO`, `CANCELADO`
  - Transições validadas: `iniciar()`, `completar()`, `falhar()`, `cancelar()`
  - Hooks automáticos em `on_*` para atualizar timestamps e campos
  - Logs de auditoria em cada transição de estado
- ✅ Configuração centralizada via `JobsSettings` (settings.py)
  - `get_jobs()` carrega `CONCILIUM__MAX_CONCURRENT_JOBS`, `JOB_TTL_HOURS`, `JOB_GC_INTERVAL_MINUTES`
  - Elimina leitura direta de `os.getenv()` espalhada pelo código
  - Padrão consistente com demais módulos (`get_api()`, `get_mcp()`, etc.)
- ✅ Documentação atualizada
  - `.env.example` com seção ADR-102 para variáveis de jobs
  - `settings.py` com tabela de referência atualizada

**Benefícios:**
- **Robustez:** Transições inválidas bloqueadas pela state machine (ex: `CONCLUIDO` → `EM_EXECUCAO` impossível)
- **Auditoria:** Logs automáticos em stderr registram todas as transições
- **Extensibilidade:** Fácil adicionar novos estados (ex: `PAUSADO`, `AGENDADO`) ou validações customizadas
- **Testabilidade:** State machine isolada e testável independentemente da lógica de jobs
- **Manutenibilidade:** Configuração centralizada elimina magic numbers e facilita testes

**Arquivos modificados:**
- `src/concilium/presentation/mcp_server/pipeline_job_state.py` (novo)
- `src/concilium/infrastructure/settings.py` (adiciona `JobsSettings` e `get_jobs()`)
- `src/concilium/presentation/mcp_server/pipeline_jobs.py` (refatorado para usar state machine)
- `cd/development/.env.example` (adiciona variáveis de jobs)

---

### 2026-06-03 — v1.0 (Implementação inicial + extensões)

**Implementado:**
- ✅ Sistema base de jobs assíncronos
- ✅ Worker pool com `ThreadPoolExecutor` (limite de concorrência)
- ✅ Garbage collection automático (TTL configurável)
- ✅ Framework de progresso incremental (callbacks)
- ✅ 4 novas tools MCP + 1 tool de estatísticas
- ✅ Documentação completa (ADR + tutorial)

**Pendente:**
- ⏳ Integração de callbacks nas skills (framework pronto)
- ⏳ Lock por project_id para concorrência segura
- ⏳ Persistência opcional em SQLite
