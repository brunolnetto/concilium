# Sistema de Jobs Assíncronos — Guia de Testes

Este documento descreve como testar as três extensões implementadas no ADR-102.

## 🚀 Inicialização

O sistema de jobs é **auto-inicializante**. Na primeira chamada de `disparar_pipeline()`, o servidor:
1. Cria `ThreadPoolExecutor` com 3 workers (configurável)
2. Inicia thread daemon de garbage collection
3. Ambos rodam até o servidor MCP ser encerrado

## ✅ Teste 1: Worker Pool com Limite de Concorrência

```python
# Disparar múltiplos jobs em sequência
job1 = disparar_pipeline(project_id="proj-A", skill_id="02-produtividade-climatica")
job2 = disparar_pipeline(project_id="proj-B", skill_id="02-produtividade-climatica")
job3 = disparar_pipeline(project_id="proj-C", skill_id="02-produtividade-climatica")
job4 = disparar_pipeline(project_id="proj-D", skill_id="02-produtividade-climatica")

# Esperado:
# - job1, job2, job3: status="EM_EXECUCAO" (workers ocupados)
# - job4: status="AGUARDANDO_FILA", posicao_fila=1

# Verificar estatísticas
stats = obter_estatisticas_jobs()
# → contadores: {jobs_por_status: {EM_EXECUCAO: 3, AGUARDANDO_FILA: 1}}
```

**Configurar limite:**
```bash
export CONCILIUM__MAX_CONCURRENT_JOBS=5
# Reiniciar servidor MCP
```

## ✅ Teste 2: Progresso Incremental

```python
job = disparar_pipeline(project_id="X", skill_id="04-cronograma")

# Consultar periodicamente
consultar_job_pipeline(job_id=job["job_id"])
# → {status: "EM_EXECUCAO", progresso: "Preparando execução...", progresso_percentual: 0.0}

# Aguardar 5s
# → {status: "EM_EXECUCAO", progresso: "Executando skill...", progresso_percentual: 0.1}

# Aguardar até finalizar
# → {status: "CONCLUIDO", progresso: "Concluído", progresso_percentual: 1.0}
```

**Nota:** Progresso atual é básico (0% → 10% → 100%). Para progresso detalhado, integrar callbacks nas skills (ver ADR-102 § Próximos Passos).

## ✅ Teste 3: Garbage Collection Automático

```python
# Disparar job e aguardar conclusão
job = disparar_pipeline(project_id="X", skill_id="02-produtividade-climatica")
# Aguardar finalizar...

# Job permanece disponível por 24h (default)
consultar_job_pipeline(job_id=job["job_id"])
# → {status: "CONCLUIDO", ...}

# Verificar configuração de TTL
stats = obter_estatisticas_jobs()
# → configuracao: {job_ttl_hours: 24, gc_interval_minutes: 60}

# GC roda a cada 60 min e remove jobs finalizados > 24h atrás
# Logs aparecem em stderr:
# [pipeline-gc] Removidos 5 jobs expirados (TTL: 24h)
```

**Ajustar TTL:**
```bash
export CONCILIUM__JOB_TTL_HOURS=1        # Jobs expiram após 1h
export CONCILIUM__JOB_GC_INTERVAL_MINUTES=5  # GC roda a cada 5 min
# Reiniciar servidor MCP
```

**Testar GC manualmente:**
```python
# Após configurar TTL=1h e GC_INTERVAL=5min:
# 1. Disparar e finalizar job
# 2. Aguardar 1h + 5 min
# 3. Consultar job — deve retornar "não encontrado (pode ter expirado após 1h)"
```

## 📊 Monitoramento

### Listar todos os jobs

```python
listar_jobs_pipeline()
# → {
#     jobs: [{job_id, status, skill_id, progresso_percentual, ...}, ...],
#     estatisticas: {
#         aguardando_fila: 2,
#         em_execucao: 3,
#         concluido: 15,
#         erro: 1
#     },
#     max_concurrent_jobs: 3
# }
```

### Health check do sistema

```python
obter_estatisticas_jobs()
# → {
#     configuracao: {
#         max_concurrent_jobs: 3,
#         job_ttl_hours: 24,
#         gc_interval_minutes: 60
#     },
#     contadores: {
#         total_jobs_ativos: 21,
#         jobs_por_status: {CONCLUIDO: 15, EM_EXECUCAO: 3, ...}
#     },
#     sistema: {
#         worker_pool_ativo: true,
#         gc_ativo: true
#     }
# }
```

## 🔧 Troubleshooting

### Worker pool não está ativo

**Sintoma:** `sistema.worker_pool_ativo: false`

**Solução:** Chamar `disparar_pipeline()` uma vez para inicializar

### GC não está rodando

**Sintoma:** `sistema.gc_ativo: false`

**Causa:** Thread GC morreu por exceção

**Solução:** Reiniciar servidor MCP (GC é daemon thread)

### Jobs não expiram

**Verificar:**
1. TTL configurado: `obter_estatisticas_jobs().configuracao.job_ttl_hours`
2. Jobs finalizados: `listar_jobs_pipeline()` — verificar `finalizado_em`
3. Logs stderr: procurar por `[pipeline-gc] Removidos N jobs expirados`

**Debug:**
```bash
# Configurar TTL agressivo para testar
export CONCILIUM__JOB_TTL_HOURS=0  # Expira imediatamente após finalizar
export CONCILIUM__JOB_GC_INTERVAL_MINUTES=1  # GC roda a cada 1 min
```

### Fila muito longa

**Sintoma:** Muitos jobs com `status: AGUARDANDO_FILA`

**Solução:**
```bash
# Aumentar workers
export CONCILIUM__MAX_CONCURRENT_JOBS=5
# Reiniciar servidor MCP
```

## 📈 Métricas de Performance

| Métrica | Valor Esperado | Como Medir |
|---|---|---|
| Tempo de disparo | < 50ms | `disparar_pipeline()` retorna imediato |
| Latência de consulta | < 10ms | `consultar_job_pipeline()` (apenas lock + dict lookup) |
| Overhead de GC | < 100ms a cada 60 min | Log stderr |
| Memória por job | ~2-5 KB | `total_jobs_ativos * 5KB` |

## 🎯 Casos de Uso

### CI/CD (execução limpa)

```bash
export CONCILIUM__MAX_CONCURRENT_JOBS=1      # Serializa execução
export CONCILIUM__JOB_TTL_HOURS=1            # Limpa após 1h
export CONCILIUM__JOB_GC_INTERVAL_MINUTES=5  # GC frequente
```

### Desenvolvimento local

```bash
export CONCILIUM__MAX_CONCURRENT_JOBS=2      # 2 jobs simultâneos
export CONCILIUM__JOB_TTL_HOURS=8            # 1 dia de trabalho
export CONCILIUM__JOB_GC_INTERVAL_MINUTES=30 # GC moderado
```

### Servidor dedicado (8+ cores)

```bash
export CONCILIUM__MAX_CONCURRENT_JOBS=5      # 5 jobs simultâneos
export CONCILIUM__JOB_TTL_HOURS=72           # 3 dias
export CONCILIUM__JOB_GC_INTERVAL_MINUTES=120 # GC a cada 2h
```
