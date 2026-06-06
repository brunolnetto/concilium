# Tutorial — Criar e Executar Projetos via MCP

Este tutorial cobre o fluxo completo do Concilium MCP: desde a verificação do sistema
até a entrega de artefatos e diagnóstico de resultados. Destinado a agentes LLM
(Claude Code, Claude Desktop, Copilot) e a humanos que utilizam o sistema via API.

---

## Pré-requisitos

### Desenvolvimento local (`.mcp.json`)

Adicione ao `.mcp.json` na raiz do projeto:

```json
{
  "mcpServers": {
    "concilium": {
      "command": "wsl",
      "args": [
        "-e", "bash", "-c",
        "cd /home/pingu/github/agente_engenheiro_senior/concilium && source .venv/bin/activate && python -m concilium.presentation.mcp.server"
      ],
      "env": {
        "CONCILIUM__CONFIG_ROOT": "/home/pingu/github/agente_engenheiro_senior/concilium/config",
        "CONCILIUM__PROJECTS_ROOT": "/home/pingu/github/agente_engenheiro_senior/concilium/projetos",
        "CONCILIUM__AUTH_ENABLED": "0"
      }
    }
  }
}
```

**Importante:** Substitua os caminhos pelos valores do seu ambiente. Use paths **Linux** (não Windows) nas variáveis de ambiente, pois o servidor roda dentro do WSL.

> ⚠️ **Primeira inicialização pode demorar 30-60s** enquanto o catálogo é carregado. Claude Desktop/VS Code podem mostrar timeout — aguarde a mensagem de "Server online" no log stderr.

Reinicie o VS Code após criar o arquivo. O `.mcp.json` deve ser adicionado ao `.gitignore` (contém caminhos específicos da máquina).

**Troubleshooting:**

Se o servidor não responder após 60s:
1. Verifique os logs stderr para erros de configuração
2. Teste manualmente no WSL: `wsl -e bash -c "cd /seu/path && source .venv/bin/activate && python -m concilium.presentation.mcp.server"`
3. Confirme que `CONCILIUM__CONFIG_ROOT` aponta para um diretório válido com `concilium.yaml`
4. Se usar contexto com muitos CPUs (>500), considere otimizar o cache do catálogo

### Autenticação JWT (Produção)

Para ambientes com autenticação habilitada (Azure deploy — ADR-094):

#### 1. Obter um token

```bash
curl -s -X POST https://api.mendesloboconstrucao.com.br/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "SEU_CLIENT_ID", "client_secret": "SEU_CLIENT_SECRET"}' \
  | jq -r .access_token
```

O token expira em **8 horas** por padrão. Service accounts CI/CD podem solicitar até 90 dias com `"ttl_days": 90`.

#### 2. Usar o token na API REST

```bash
TOKEN="eyJ..."

# Listar projetos
curl -H "Authorization: Bearer $TOKEN" \
  https://api.mendesloboconstrucao.com.br/api/projects

# Executar pipeline
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"base_version": null}' \
  https://api.mendesloboconstrucao.com.br/api/projects/PROJETO_ID/runs
```

#### 3. Escopos disponíveis

> **📋 Roles e Workflows:** Para entender o mapeamento completo entre roles, permissões, tools e workflows, consulte [ROLES-WORKFLOWS-MAPPING.md](./ROLES-WORKFLOWS-MAPPING.md).

| Scope | Operações permitidas |
|---|---|
| `mcp:read` | Listar projetos, consultar status, baixar artefatos |
| `mcp:write` | Criar projetos, aplicar overrides |
| `pipeline:run` | Executar pipeline, avançar skills |

Os escopos são configurados por `client_id` em `CONCILIUM__AUTH_CLIENTS` (env var do servidor).

> **Nota:** O sistema RBAC atual (ADR-099) usa **roles** em vez de escopos planos. O mapeamento acima é legado e será descontinuado. Novos clientes devem usar roles: `viewer`, `operator`, `engineer`, `admin`, `service-ci`, `auditor`.

#### 4. Renovação automática (script)

```bash
#!/usr/bin/env bash
# renew-token.sh — salva token renovado em ~/.concilium-token
curl -sf -X POST https://api.mendesloboconstrucao.com.br/auth/token \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"${CONCILIUM_CLIENT_ID}\", \
       \"client_secret\": \"${CONCILIUM_CLIENT_SECRET}\"}" \
  | jq -r .access_token > ~/.concilium-token && echo "Token renovado."
```

Agende via `cron` a cada 7 horas:
```
0 */7 * * * /path/to/renew-token.sh
```

### Produção (`concilium-mcp-proxy`)

Para ambientes com autenticação JWT (Azure deploy — ADR-096):

1. `concilium-mcp-proxy` instalado e configurado no `claude_desktop_config.json`
   → Ver `cd/development/claude_desktop_config.json.template` (perfil `concilium-prod`)
2. Device code fornecido pelo admin via `concilium auth new-device`

**Windows (Claude Desktop):**
Arquivo: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "concilium-local": {
      "command": "wsl",
      "args": [
        "-e", "bash", "-c",
        "cd /home/pingu/github/agente_engenheiro_senior/concilium && source .venv/bin/activate && python -m concilium.presentation.mcp.server"
      ],
      "env": {
        "CONCILIUM__CONFIG_ROOT": "/home/pingu/github/agente_engenheiro_senior/concilium/config",
        "CONCILIUM__PROJECTS_ROOT": "/home/pingu/github/agente_engenheiro_senior/concilium/projetos"
      }
    }
  }
}
```

---

## Passo 0 — Verificar saúde do sistema

**Sempre faça isso primeiro.** Retorna contextos disponíveis, contagem de projetos e
saúde de cada catálogo em uma única chamada.

```python
ping()
# → {status: "SAUDAVEL", contextos: ["mendeslobo-ce"], projetos: 3,
#    catalogos: [{contexto_id: "mendeslobo-ce", cpus: 412, erros_criticos: 0}]}
```

Se `status == "DEGRADADO"` ou `erros_criticos > 0`, investigue antes de prosseguir.

---

## Fluxo 1 — Criação de projeto

Dois caminhos disponíveis dependendo do nível de estruturação da entrada.

### 1A — Via QQP (forma recomendada para novos projetos)

Quando o usuário tem uma lista de serviços em linguagem natural:

```python
# Passo 1: confirmar contextos disponíveis
listar_contextos()
# → [{id: "mendeslobo-ce", perfil_id: "...", catalogo_id: "..."}]

# Passo 2: criar a partir da QQP
criar_projeto_formulario(
    nome="Rodovia CE-040 — Lote 09/10",
    contexto_id="mendeslobo-ce",
    tipo_obra="terraplenagem",
    localizacao="Aracoiaba, CE",
    data_inicio="2026-09-01",
    servicos=[
        {"descricao": "Supressão vegetal",            "quantidade": 8,      "unidade": "ha"},
        {"descricao": "Escavação de material 3ª cat", "quantidade": 450000, "unidade": "m³"},
        {"descricao": "Aterro compactado",            "quantidade": 120000, "unidade": "m³"},
        {"descricao": "Carga e transporte DMT 3km",   "quantidade": 450000, "unidade": "m³"},
    ]
)
```

**Resposta A — todos mapeados:**
```json
{"status": "criado", "project_id": "rodovia-ce040-lote09", "version": "v1",
 "eap_preview": [...], "proxima_skill_sugerida": "02-produtividade-climatica"}
```

**Resposta B — itens sem CPU:**
```json
{"status": "pendente_mapeamento",
 "nao_mapeados": [{"descricao": "Carga e transporte DMT 3km", "item_id": "eap-1_4"}],
 "instrucoes": "Use pesquisar_catalogo() para encontrar o cpu_id correto..."}
```

Se B, pesquise o CPU — o tool correto é `pesquisar_catalogo`, não `buscar_cpu`:

```python
pesquisar_catalogo(contexto_id="mendeslobo-ce", query="carga transporte terraplenagem")
# → [{cpu_id: "CPU-TERRA-CARGA-01", descricao: "Carga e transporte..."}, ...]
```

Repita `criar_projeto_formulario` com `cpu_id` preenchido nos itens pendentes.

### 1B — Via EAP estruturada (`iniciar_orcamento`)

Quando já se conhece os `cpu_id` de cada item:

```python
iniciar_orcamento(
    nome="Rodovia CE-040 — Lote 09/10",
    contexto_id="mendeslobo-ce",
    tipo_obra="terraplenagem",
    localizacao="Aracoiaba, CE",
    coordenadas_lat=-4.37,
    coordenadas_lng=-38.77,
    data_inicio="2026-09-01",
    data_termino="2027-09-01",
    horas_dia=8,
    dias_semana=6,
    eap=[
        {"item_id": "eap-1_1", "ordem": 1, "cpu_id": "CPU-TERRA-SUPVEG",
         "descricao": "Supressão vegetal", "unidade": "ha", "quantitativo": 8},
        {"item_id": "eap-1_2", "ordem": 2, "cpu_id": "CPU-TERRA-COMPAC-PN",
         "descricao": "Escavação 3ª cat",  "unidade": "m³", "quantitativo": 450000},
    ]
)
```

---

## Fluxo 2 — Execução do pipeline

### Passo 3 — Avançar skill a skill

**⚠️ IMPORTANTE:** Use `disparar_pipeline()` em vez de `avancar_pipeline()` para evitar timeouts.
Skills podem demorar 30-120s (especialmente cronograma com RCPSP), e chamadas síncronas bloqueiam o cliente.

#### Modo recomendado (assíncrono com worker pool):

```python
# Dispara a próxima skill pendente em background
job = disparar_pipeline(project_id="rodovia-ce040-lote09")
# → {job_id: "job-abc123", status: "AGUARDANDO_FILA", posicao_fila: 0, workers_disponiveis: 3}

# Sistema gerencia fila automaticamente — máx 3 jobs simultâneos
# Se fila cheia: status="AGUARDANDO_FILA", senão: status="EM_EXECUCAO"

# Aguardar 5-10 segundos (ou perguntar ao usuário antes de consultar)
# ...

# Consultar resultado
resultado = consultar_job_pipeline(job_id="job-abc123")
# → {status: "EM_EXECUCAO", progresso: "Resolvendo RCPSP...", progresso_percentual: 0.45}

# Quando finalizado:
# → {status: "CONCLUIDO", skill_executada: "02-produtividade-climatica", 
#    proxima_sugerida: "03-catalogo-de-recursos", validacoes: [...]}

# Skill de cronograma requer num_equipes_por_item
job = disparar_pipeline(
    project_id="rodovia-ce040-lote09",
    skill_id="04-cronograma",
    inputs={"num_equipes_por_item": {"eap-1_1": 2, "eap-1_2": 3}}
)
# Aguardar e consultar novamente...

# Listar todos os jobs do projeto (com estatísticas)
listar_jobs_pipeline(project_id="rodovia-ce040-lote09")
# → {jobs: [{job_id: "job-abc123", status: "CONCLUIDO", progresso_percentual: 1.0, ...}],
#    estatisticas: {aguardando_fila: 0, em_execucao: 1, concluido: 2, erro: 0},
#    max_concurrent_jobs: 3}

# Estatísticas do sistema (diagnóstico)
obter_estatisticas_jobs()
# → {configuracao: {max_concurrent_jobs: 3, job_ttl_hours: 24, gc_interval_minutes: 60},
#    contadores: {total_jobs_ativos: 5, jobs_por_status: {...}},
#    sistema: {worker_pool_ativo: true, gc_ativo: true}}
```

**Configuração do sistema:**
```bash
# Ajustar concorrência (default: 3)
export CONCILIUM__MAX_CONCURRENT_JOBS=5

# TTL de jobs finalizados (default: 24h)
export CONCILIUM__JOB_TTL_HOURS=48

# Intervalo de garbage collection (default: 60min)
export CONCILIUM__JOB_GC_INTERVAL_MINUTES=30
```

#### Modo legado (síncrono — não recomendado):

```python
# ⚠️ BLOQUEANTE — cliente MCP pode dar timeout em skills lentas (cronograma, otimização)
avancar_pipeline(project_id="rodovia-ce040-lote09")
# → {skill_executada: "02-produtividade-climatica", status: "OK",
#    proxima_sugerida: "03-catalogo-de-recursos", validacoes: [...]}
```

### Passo 4 — Verificar status

```python
consultar_status(project_id="rodovia-ce040-lote09")
# → {pipeline_integridade: "COMPLETO",
#    resultado_atual: {preco_venda: 85_639_774.05, margem: 0.204}, ...}
```

> ⚠️ Se `pipeline_integridade == "CORROMPIDO"`, os valores financeiros **não devem ser usados**.
> Corrija os erros em `validacoes` e re-execute a partir do checkpoint falho.

> ⚠️ **Margem VERMELHO** (< 20%) é um sinal financeiro real — não é bug. Significa que
> o BDI e/ou a configuração de equipes precisa ser revisada antes de submeter proposta.

---

## Fluxo 3 — Diagnóstico e replanejamento

Use este fluxo após obter um resultado VERMELHO/AMARELO ou quando quiser explorar
cenários alternativos.

### Auditoria completa

```python
auditar_plano(project_id="rodovia-ce040-lote09")
# → {viabilidade: {...}, gargalos: [...], resumo_financeiro: {...}}
```

### Explorar pool de recursos

```python
# Ver ciclo de vida de cada instância (padrão)
explorar_pool_recursos(project_id="rodovia-ce040-lote09", face="instancia_ciclo_vida")

# Decompor custo por estado (prod/idle/mob/demob)
explorar_pool_recursos(project_id="rodovia-ce040-lote09", face="custo_estado_componente")

# Faces disponíveis:
# instancia_ciclo_vida | custo_estado_componente | utilizacao_temporal
# atividade_instancia  | causa_custo             | economia_pool
# cadeia_perpetuacao
```

### Simular cenário de replanejamento

```python
# Impacto de estender o prazo 4 semanas
simular_cenario_replan(
    project_id="rodovia-ce040-lote09",
    tipo="extend_deadline",
    parametros={"semanas": 4},
    incluir_indiretos=True
)

# Impacto de adicionar equipes em itens críticos
simular_cenario_replan(
    project_id="rodovia-ce040-lote09",
    tipo="add_teams",
    parametros={"eap_item_id": "eap-1_6", "delta_equipes": 2}
)
```

### Aplicar sugestão (cria nova versão)

```python
aplicar_sugestao_replan(
    project_id="rodovia-ce040-lote09",
    sugestao_id="sug-001",
    justificativa="Paralelismo eap-1_6: +2 frentes para atingir margem alvo"
)
```

### Comparar dois planos

```python
comparar_planos(
    project_id="rodovia-ce040-lote09",
    escopo_id="esc-01",
    plano_a="plano-baseline",
    plano_b="plano-paralelo"
)
```

---

## Fluxo 4 — Artefatos

### Listar e ler

```python
listar_artefatos_projeto(project_id="rodovia-ce040-lote09")
# → [{kind: "relatorio_md", filename: "relatorio.md", audiencia: "agente"},
#    {kind: "planilha_excel", filename: "resultado_planejamento.xlsx", audiencia: "humano"},
#    ...]

# Artefatos textuais (md, json, csv) — use ler_artefato_TEXTO, não ler_artefato
ler_artefato_texto(project_id="rodovia-ce040-lote09", nome_arquivo="resumo_executivo.md")
# → {conteudo: "# Resumo Executivo...", tamanho_bytes: 1204}

# Binários (PNG, XLSX, PDF) — use baixar_artefato_binario
baixar_artefato_binario(project_id="rodovia-ce040-lote09", nome_arquivo="relatorio.pdf")
# → {base64: "...", mime_type: "application/pdf"}
```

> ⚠️ **`ler_artefato()` não existe.** O nome correto é `ler_artefato_texto()` para
> arquivos de texto e `baixar_artefato_binario()` para binários. Confundir os dois
> resulta em erro de chamada.

### Bundle completo

```python
baixar_bundle_zip(project_id="rodovia-ce040-lote09")
# → {base64: "...", filename: "rodovia-ce040-lote09-bundle.zip"}
```

---

## Fluxo 5 — Benchmarks

> ⚠️ **`executar_benchmark` é uma operação longa (2–7 min).** Chamá-la via MCP stdio
> bloqueia o host Claude Code enquanto aguarda a resposta — a UI aparece travada.
> **Use sempre o CLI para executar benchmarks:**
>
> ```bash
> concilium benchmark run --slug AGIS --reset
> ```
>
> Após a execução, use `listar_benchmarks` e `download_benchmark_zip` normalmente via MCP.

```python
# Ver status de todos os benchmarks
listar_benchmarks()
# → [{slug: "AGIS", tem_referencia: true, relatorios: 3, zips_disponiveis: []}, ...]

# Empacotar resultados já existentes (rápido — não re-executa)
empacotar_benchmark(slug="AGIS")

# Download do ZIP em base64
download_benchmark_zip(slug="AGIS")
```

### Interpretar resultados de benchmark

Os artefatos ficam em `benchmarks/data/<SLUG>/artifacts/`. Para ler via MCP não existe
tool direta — use `ler_artefato_texto` do projeto ou leia pelo filesystem. Os artefatos
chave são:

| Arquivo | Conteúdo | Audiência |
|---|---|---|
| `audit/benchmark_report.json` | Confronto calculado vs. referência, quality gates, RCPSP | agente |
| `outputs/resumo_executivo.md` | Resultado financeiro, criticidade, alavancas PE | ambos |
| `outputs/relatorio.md` | Relatório completo do planejamento | humano |
| `outputs/memorial_bdi.md` | Composição detalhada do BDI | agente/humano |

**Exemplo AGIS (benchmark de referência — Ferrovia Nova Transnordestina):**

| Métrica | Referência | Calculado | Delta |
|---|---|---|---|
| Custo direto | R$ 46.867.333 | R$ 46.843.791 | **-0,05%** ✅ |
| Custo indireto | R$ 19.584.539 | R$ 19.584.539 | **-0,00%** ✅ |
| Preço de venda | R$ 76.961.262 | R$ 85.639.774 | **+11,28%** ⚠️ |

O delta no preço de venda é **divergência de BDI**, não de custo. O motor calculou
`bdi_lucro_impostos = 25,7%` enquanto a referência AGIS implica ~15,5%. Isso é escolha
de negócio, não erro — o quality gate `BLOQUEADO_COM_INVESTIGACAO` está correto.

Avisos de produtividade nos `CPU-DREN-*` (ratio P_can/P_orig ≈ 3,4–3,6×) indicam
calibração pendente das produtividades implícitas no catálogo `mendeslobo` para itens
de drenagem de baixo volume.

---

## Fluxo 6 — Catálogo (operações avançadas)

```python
# Saúde geral do catálogo
consultar_saude_catalogo(contexto_id="mendeslobo-ce")

# Integridade estrutural (detecta CPUs sem equipe, produtividades zeradas, etc.)
verificar_integridade_catalogo(
    contexto_id="mendeslobo-ce",
    alpha_clt=1.777,    # encargo CLT
    alpha_pj=1.06,      # encargo PJ
    preco_diesel=6.5    # R$/litro
)

# Plausibilidade dos dados (detecta ratios P_can/P_orig fora de [0.5, 2.0])
avaliar_plausibilidade_catalogo(contexto_id="mendeslobo-ce")

# Comparar RFI com catálogo (dry_run=True não salva alterações)
comparar_rfi_catalogo(contexto_id="mendeslobo-ce", dry_run=True)

# Tendência histórica de preços
tendencia_precos_catalogo(contexto_id="mendeslobo-ce")

# Preço de insumo em data específica
consultar_preco_insumo_temporal(
    contexto_id="mendeslobo-ce",
    insumo_id="diesel",
    data_referencia="2026-06-01"
)

# Atualizar preço de insumo
atualizar_preco_insumo(
    contexto_id="mendeslobo-ce",
    insumo_id="diesel",
    novo_preco=6.80,
    nota="Reajuste Petrobras jun/2026"
)
```

---

## Ciclo de vida de versões

```
v1 (RASCUNHO) → aprovar_versao → v1 (APROVADO)
                                      ↓
                               nova_versao() → v2 (RASCUNHO)
                                      ↓
                               avancar_pipeline...
```

```python
# Aprovar versão atual (IRREVERSÍVEL — confirmar com o usuário antes)
aprovar_versao(project_id="rodovia-ce040-lote09")

# Criar v2 para replanejamento
nova_versao(project_id="rodovia-ce040-lote09")
# → {nova_versao: "v2", proxima_skill_sugerida: "04-cronograma"}

# Estrutura completa de escopos/planos
consultar_estrutura_projeto(project_id="rodovia-ce040-lote09")
```

---

## Referência completa das 40 ferramentas

### Sistema

| Tool | Descrição |
|---|---|
| `ping()` | Saúde do servidor, contextos, projetos e catálogos em uma chamada |
| `listar_contextos()` | Lista contextos de catálogo disponíveis |
| `listar_projetos()` | Lista todos os projetos existentes |

### Projeto — Ciclo de vida

| Tool | Descrição |
|---|---|
| `criar_projeto_formulario(...)` | Cria projeto a partir de QQP (linguagem natural → EAP) |
| `iniciar_orcamento(...)` | Cria projeto com EAP estruturada e `cpu_id` já conhecidos |
| `configurar_escopo(...)` | Cria ou atualiza um escopo de obra no projeto |
| `gerenciar_plano(acao, ...)` | Gerencia planos dentro de um escopo (`criar`/`aprovar`/`arquivar`) |
| `nova_versao(...)` | Cria nova versão de planejamento a partir de versão aprovada |
| `consultar_status(project_id)` | Estado do pipeline e resultado financeiro atual |
| `consultar_estrutura_projeto(project_id)` | Árvore completa de Escopos e Planos (ADR-031) |
| `aprovar_versao(project_id)` | **Congela versão — IRREVERSÍVEL. Confirmar com o usuário.** |

### Pipeline

| Tool | Descrição |
|---|---|
| `disparar_pipeline(project_id, ...)` | **[RECOMENDADO]** Dispara skill em background via worker pool, retorna job_id |
| `consultar_job_pipeline(job_id)` | Consulta status, progresso e resultado de job assíncrono |
| `listar_jobs_pipeline(project_id)` | Lista todos os jobs de pipeline do projeto com estatísticas |
| `obter_estatisticas_jobs()` | Estatísticas do sistema (workers, TTL, GC, health check) |
| `avancar_pipeline(project_id, ...)` | **[DEPRECATED]** Executa skill de forma síncrona (bloqueante — evite usar) |

### Catálogo

| Tool | Descrição |
|---|---|
| `pesquisar_catalogo(contexto_id, query)` | Busca CPUs/recursos por descrição ou tipo de obra |
| `verificar_integridade_catalogo(contexto_id)` | Integridade estrutural (CPUs sem equipe, PUs zerados) |
| `consultar_saude_catalogo(contexto_id)` | Indicadores de saúde e cobertura |
| `avaliar_plausibilidade_catalogo(contexto_id)` | Detecta ratios P_can/P_orig fora do intervalo aceitável |
| `comparar_rfi_catalogo(contexto_id, dry_run)` | Divergências entre RFI e catálogo |
| `tendencia_precos_catalogo(contexto_id)` | Tendência histórica de preços por insumo |
| `consultar_preco_insumo_temporal(...)` | Preço de insumo em data específica |
| `atualizar_preco_insumo(...)` | Atualiza preço de insumo no contexto |
| `adicionar_variante_producao(...)` | Adiciona variante com equipe e valor horário |
| `calcular_pu_producao(...)` | Calcula PU de produção para uma composição |
| `salvar_perfil_bdi(...)` | Salva perfil BDI no contexto |

### Análise e diagnóstico

| Tool | Descrição |
|---|---|
| `auditar_plano(project_id)` | Auditoria 360°: viabilidade, gargalos, resumo financeiro |
| `explorar_pool_recursos(project_id, face)` | Decomposição composicional-temporal do pool (7 faces) |
| `comparar_planos(project_id, plano_a, plano_b)` | Compara dois planos do mesmo escopo |
| `simular_cenario_replan(project_id, tipo, params)` | Simula impacto de alteração no plano |
| `aplicar_sugestao_replan(project_id, sugestao_id)` | Aplica sugestão criando nova versão |

### Artefatos

| Tool | Descrição |
|---|---|
| `listar_artefatos_projeto(project_id)` | Lista artefatos com nome, tipo, tamanho e audiência |
| `ler_artefato_texto(project_id, nome_arquivo)` | Lê artefato textual: `.md`, `.json`, `.csv`, `.txt` |
| `baixar_artefato_binario(project_id, nome_arquivo)` | Retorna binário em base64: `.png`, `.xlsx`, `.pdf` |
| `baixar_bundle_zip(project_id)` | ZIP com todos os artefatos do projeto |

### Benchmarks

| Tool | Descrição |
|---|---|
| `listar_benchmarks()` | Lista benchmarks disponíveis com status e artefatos |
| `executar_benchmark(slug, reset)` | ⚠️ **LENTO (2–7 min) — prefira o CLI** |
| `empacotar_benchmark(slug)` | Empacota resultados existentes em ZIP |
| `download_benchmark_zip(slug)` | Retorna ZIP do benchmark em base64 |

---

## Erros comuns

| Código / Mensagem | Causa | Solução |
|---|---|---|
| `Tool not found: ler_artefato` | Nome errado | Use `ler_artefato_texto` (texto) ou `baixar_artefato_binario` (binário) |
| `Tool not found: buscar_cpu` | Nome errado | Use `pesquisar_catalogo(contexto_id, query)` |
| `pipeline_integridade: CORROMPIDO` | Skill GATE falhou | Ver `validacoes` em `consultar_status`, corrigir inputs e re-executar |
| `status: pendente_mapeamento` | Serviço sem CPU | Usar `pesquisar_catalogo()` e repassar com `cpu_id` |
| `margem VERMELHO` | BDI ou pool de equipes fora do alvo | Revisar BDI via `salvar_perfil_bdi` e simular cenários com `simular_cenario_replan` |
| `401 Unauthorized` | Token ausente, expirado ou inválido (prod) | Renovar token JWT |
| `403 Forbidden` | Token válido mas escopo insuficiente | Usar client_id com escopo adequado |
| `429 Too Many Requests` | Rate limit atingido | Aguardar `Retry-After` segundos |
| Timeout ao chamar `avancar_pipeline` | Skill demorada bloqueou cliente | Use `disparar_pipeline()` + `consultar_job_pipeline()` para execução assíncrona |
| `status: AGUARDANDO_FILA` por muito tempo | Worker pool cheio (3 jobs rodando) | Aguardar ou verificar estatísticas com `obter_estatisticas_jobs()` |
| `Job 'job-xyz' não encontrado` | Job expirado após TTL (24h) ou servidor reiniciado | Jobs em memória não persistem — re-disparar pipeline se necessário |
| `progresso_percentual` não avança | Skill não reporta progresso ainda | Framework implementado mas skills precisam integração — ver ADR-102 |
| UI travada ao chamar benchmark | `executar_benchmark` bloqueia stdio | Usar `concilium benchmark run --slug X` pelo terminal |
| `ratio P_can/P_orig` nos avisos | Produtividade implícita diverge | Calibrar `precos_unitarios_sbdi` no catálogo para os CPUs afetados |
