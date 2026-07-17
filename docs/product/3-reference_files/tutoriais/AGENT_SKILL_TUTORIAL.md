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

1. O admin cadastra o usuário com `concilium ops auth add-user --id <id> --role <role> --email <email>`
   (ver `commands_auth.py`) — o mesmo `client_code` reutilizável ativa quantos dispositivos o
   usuário precisar, sem um comando por dispositivo.
2. Se `--email` foi informado, o usuário recebe automaticamente por email: o executável do
   proxy (link de download por SO — Windows/Linux/macOS) e os dois `claude_desktop_config.json`
   já preenchidos (`claude_desktop_config-windows.json` / `claude_desktop_config-macos-linux.json`).
   Sem `--email`, o admin entrega esses dois arquivos manualmente (impressos no terminal).
3. Baixe o executável do proxy e salve exatamente no caminho indicado no email:
   `C:\Concilium\concilium-mcp-proxy.exe` (Windows) ou `~/.concilium/bin/concilium-mcp-proxy`
   com `chmod +x` (Linux/macOS).
4. Cole o conteúdo do JSON correspondente ao seu sistema em `claude_desktop_config.json` e
   reinicie o Claude Desktop.

**Windows (Claude Desktop):**
Arquivo: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "concilium": {
      "command": "C:\\Concilium\\concilium-mcp-proxy.exe",
      "env": {
        "CONCILIUM_CLIENT_CODE": "RCODE-...",
        "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br"
      }
    }
  }
}
```

**macOS/Linux:**
Arquivo: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) ou
equivalente do seu cliente MCP (Linux).

```json
{
  "mcpServers": {
    "concilium": {
      "command": "sh",
      "args": ["-c", "$HOME/.concilium/bin/concilium-mcp-proxy"],
      "env": {
        "CONCILIUM_CLIENT_CODE": "RCODE-...",
        "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br"
      }
    }
  }
}
```

---

## Passo 0 — Verificar saúde do sistema

**Sempre faça isso primeiro.** Retorna contextos disponíveis, contagem de projetos e
saúde de cada catálogo em uma única chamada.

> **Permissão:** `ping()` requer role `admin` (escopo `system:read`). Em ambientes com
> autenticação habilitada, apenas contas admin podem chamar esta ferramenta.

```python
ping()
# → {status: "SAUDAVEL", contextos: ["mendeslobo-ce"], projetos: 3,
#    catalogos: [{contexto_id: "mendeslobo-ce", cpus: 412, erros_criticos: 0}]}
```

Se `status == "DEGRADADO"` ou `erros_criticos > 0`, investigue antes de prosseguir.

---

## Fluxo 1 — Criação de projeto

Dois caminhos disponíveis dependendo do nível de estruturação da entrada.

### Regra fundamental: falar a língua da obra

O usuário do Concilium é um engenheiro civil. Nunca exponha parâmetros técnicos do sistema na conversa. O agente é o intérprete entre a linguagem de obra e o schema interno.

| ❌ Não perguntar | ✅ Perguntar assim |
|---|---|
| "Qual o `cpu_id`?" | "Escavação 1ª categoria ou 3ª? Com carga ou só escavação?" |
| "Qual o `completion_threshold_pct`?" | (não perguntar — default 1.0) |
| "Qual o `n_max`?" | "Quantas máquinas desse tipo no pico?" |
| "Qual o `leadtime_mob_semanas`?" | "Quantas semanas para montar o canteiro antes de começar?" |
| "Quer `restricoes_mercado`?" | "Tem restrição de equipamento na região?" |
| "Informe `bdi_lucro.mao_obra`" | "Qual o lucro objetivo da obra? (um número, ex: 8%)" |

### 1A — Via QQP (forma recomendada para novos projetos)

Conduzir conversa em 7 blocos, pulando os que têm defaults aceitáveis:

**Bloco 1 — Identificação** (sempre perguntar)
```python
# Coletar na conversa: nome, tipo_obra, localizacao, data_inicio, data_termino
# Geocoding de localizacao → coordenadas (fazer internamente, não expor)
```

**Bloco 2 — Regime de trabalho** (só se diferente do padrão 6×8)
```python
# Default mendeslobo: dias_semana=6, horas_dia=8
# Perguntar: "A obra roda em regime diferente de 6 dias × 8 horas?"
```

**Bloco 3 — Serviços** (sempre)
```python
# Coletar lista em linguagem natural → criar_projeto resolve CPUs
listar_contextos()  # → confirmar contexto_id disponível

criar_projeto(
    nome="Rodovia CE-040 — Lote 09/10",
    contexto_id="mendeslobo",
    tipo_obra="terraplenagem",
    localizacao="Aracoiaba, CE",
    data_inicio="2026-09-01",
    data_termino="2027-09-01",
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
{"status": "criado", "project_id": "rodovia-ce040-lote09",
 "eap_preview": [...], "proxima_skill_sugerida": "02-produtividade-climatica"}
```

**Resposta B — itens sem CPU:**
```json
{"status": "pendente_mapeamento",
 "nao_mapeados": [{"descricao": "Carga e transporte DMT 3km", "item_id": "eap-1_4"}]}
```

Se B, pesquisar e apresentar opções ao usuário em linguagem natural:
```python
pesquisar_catalogo(contexto_id="mendeslobo", query="carga transporte terraplenagem")
# → [{cpu_id: "CPU-TERRA-CARGA-01", descricao: "Carga e transporte 1ª cat. DMT ≤ 2km"}...]

# Dizer ao usuário: "Para 'Carga e transporte DMT 3km' encontrei:
#   (1) Escavação com carga e transporte até 3km — R$ XX/m³
#   (2) Transporte puro DMT 3km — R$ XX/m³
#   Qual se encaixa melhor?"
```

Repetir `criar_projeto` com `cpu_id` preenchido.

**Bloco 4 — Custos de canteiro** (perguntar; aceita "não sei")

Perguntar: "Você tem os custos mensais do canteiro (ADM, supervisão, segurança, mobilização)?"

- Se sim: coletar valores em R$/mês por categoria
- Se não (ou "use o padrão"): usar defaults derivados dos benchmarks MendesLobo

Ao usar defaults, informar: "Usarei os padrões MendesLobo: ADM ~R$1M/mês, supervisão ~R$67k/mês, lab ~R$11k, QSMS ~R$59k. Posso ajustar depois."

**Bloco 5 — Regime e lucro** (perguntar; aceita "padrão")

Pergunta única: "Qual o regime tributário (Lucro Presumido/Simples/Lucro Real) e qual o lucro objetivo da obra?"

Tradução de "8% de lucro" → `bdi_lucro`:
```python
# Regra interna — nunca expor ao usuário:
L = 0.08
bdi_lucro = {
    "mao_obra": L, "servicos": L,
    "material": min(L, 0.04),  # isenção fiscal caps em 4%
    "diesel":   min(L, 0.04),
    "indireto": min(L, 0.05),  # convenção TCU cap em 5%
}
```

**Bloco 6 — Mobilização** (perguntar se obra > 3 meses)

"Quantas semanas para montar o canteiro antes de começar a produção?"

Tradução interna (nunca expor o nome do campo):
```python
# "3 semanas" → cronograma[*].leadtime_mob_semanas = 3
# "1 semana para devolver os equipamentos" → cronograma[*].lag_demob_semanas = 1
```

Sugestão do agente baseada no porte:
- Obra ≤ R$20M ou ≤ 6 meses → sugerir 1–2 semanas mob, 1 semana demob
- Obra > R$50M ou > 12 meses → sugerir 3–4 semanas mob, 2 semanas demob

**Bloco 7 — Equipamento na região** (só se localização remota)

"A região tem restrição de disponibilidade de equipamentos pesados?"

Tradução interna (após `disparar_pipeline("03-catalogo")` que confirma os tipos):
```python
# "Só tem 2 escavadeiras grandes disponíveis" →
# restricoes_mercado = {"EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 2}
# Default: restricoes_mercado = {} (irrestrito)
```

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

**⚠️ IMPORTANTE:** Use sempre `disparar_pipeline()` para evitar timeouts. Skills podem demorar
30-120s (especialmente cronograma com RCPSP), e chamadas síncronas bloqueiam o cliente.

#### Modo assíncrono com worker pool:

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

# Listar todos os jobs do projeto
listar_jobs_pipeline(project_id="rodovia-ce040-lote09")
# → {jobs: [{job_id: "job-abc123", status: "CONCLUIDO", progresso_percentual: 1.0, ...}]}

# Listar com estatísticas do sistema (workers, TTL, GC, health)
listar_jobs_pipeline(project_id="rodovia-ce040-lote09", incluir_estatisticas=True)
# → {jobs: [...],
#    estatisticas: {aguardando_fila: 0, em_execucao: 1, concluido: 2, erro: 0},
#    configuracao: {max_concurrent_jobs: 3, job_ttl_hours: 24, gc_interval_minutes: 60},
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

# Artefatos textuais (md, json, csv)
obter_artefato(project_id="rodovia-ce040-lote09", nome_arquivo="resumo_executivo.md", formato="texto")
# → {conteudo: "# Resumo Executivo...", tamanho_bytes: 1204}

# Binários (PNG, XLSX, PDF)
obter_artefato(project_id="rodovia-ce040-lote09", nome_arquivo="relatorio.pdf", formato="binario")
# → {base64: "...", mime_type: "application/pdf"}
```

> ⚠️ **`ler_artefato_texto()`, `baixar_artefato_binario()` e `baixar_bundle_zip()` não existem mais.**
> Use `obter_artefato(formato="texto"|"binario"|"bundle")` para todos os casos.

### Bundle completo

```python
obter_artefato(project_id="rodovia-ce040-lote09", formato="bundle")
# → {base64: "...", filename: "rodovia-ce040-lote09-bundle.zip"}
```

---

## Fluxo 5 — Benchmarks

> ⚠️ **`executar_benchmark_nep039` é uma operação longa (2–7 min).** Chamá-la via MCP stdio
> bloqueia o host Claude Code enquanto aguarda a resposta — a UI aparece travada.
> **Use sempre o CLI para executar benchmarks:**
>
> ```bash
> concilium benchmark run --slug AGIS --reset
> ```
>
> Após a execução, use `consultar_benchmark` e `download_benchmark_zip` normalmente via MCP.

```python
# Ver status de todos os benchmarks (sem argumento = listar todos)
consultar_benchmark()
# → [{slug: "AGIS", tem_referencia: true, relatorios: 3, zips_disponiveis: []}, ...]

# Ver detalhe de um benchmark específico
consultar_benchmark(benchmark_id="AGIS")
# → {slug: "AGIS", tem_referencia: true, relatorios: [...], quality_gates: {...}}

# Empacotar resultados já existentes (rápido — não re-executa)
empacotar_benchmark(slug="AGIS")

# Download do ZIP em base64
download_benchmark_zip(slug="AGIS")
```

### Interpretar resultados de benchmark

Os artefatos ficam em `benchmarks/data/<SLUG>/artifacts/`. Para ler via MCP não existe
tool direta — use `obter_artefato(formato="texto")` do projeto ou leia pelo filesystem. Os artefatos
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
auditar_catalogo(contexto_id="mendeslobo-ce", modo="saude")

# Integridade estrutural (detecta CPUs sem equipe, produtividades zeradas, etc.)
auditar_catalogo(
    contexto_id="mendeslobo-ce",
    modo="integridade",
    alpha_clt=1.777,    # encargo CLT
    alpha_pj=1.06,      # encargo PJ
    preco_diesel=6.5    # R$/litro
)

# Plausibilidade dos dados (detecta ratios P_can/P_orig fora de [0.5, 2.0])
auditar_catalogo(contexto_id="mendeslobo-ce", modo="plausibilidade")

# Comparar RFI com catálogo (dry_run=True não salva alterações)
comparar_rfi_catalogo(contexto_id="mendeslobo-ce", dry_run=True)

# Tendência histórica de preços
historico_preco_insumo(contexto_id="mendeslobo-ce", modo="tendencia")

# Preço de insumo em data específica
historico_preco_insumo(
    contexto_id="mendeslobo-ce",
    insumo_id="diesel",
    modo="pontual",
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
                               disparar_pipeline...
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
| `ping()` | Saúde do servidor, contextos, projetos e catálogos em uma chamada — requer `system:read` (admin) |
| `listar_contextos()` | Lista contextos de catálogo disponíveis |
| `listar_projetos()` | Lista todos os projetos existentes |

### Projeto — Ciclo de vida

| Tool | Descrição |
|---|---|
| `criar_projeto(nome, spec=None, ...)` | Cria projeto via QQP (linguagem natural → EAP) quando `spec=None`, ou via EAP estruturada com `cpu_id` quando `spec` fornecido; substitui `criar_projeto_formulario` e `criar_projeto_spec` |
| `iniciar_orcamento(...)` | Cria projeto com EAP estruturada e `cpu_id` já conhecidos |
| `gerir_escopo(entidade, acao, ...)` | `entidade="escopo"` cria/atualiza escopo; `entidade="plano"` gerencia planos (`criar`/`aprovar`/`arquivar`) — substitui `configurar_escopo` e `gerenciar_plano` |
| `nova_versao(...)` | Cria nova versão de planejamento a partir de versão aprovada |
| `consultar_status(project_id)` | Estado do pipeline e resultado financeiro atual |
| `consultar_estrutura_projeto(project_id)` | Árvore completa de Escopos e Planos (ADR-031) |
| `aprovar_versao(project_id)` | **Congela versão — IRREVERSÍVEL. Confirmar com o usuário.** |

### Pipeline

| Tool | Descrição |
|---|---|
| `disparar_pipeline(project_id, ...)` | **[RECOMENDADO]** Dispara skill em background via worker pool, retorna job_id |
| `consultar_job_pipeline(job_id)` | Consulta status, progresso e resultado de job assíncrono |
| `listar_jobs_pipeline(project_id, incluir_estatisticas=False)` | Lista jobs do projeto; `incluir_estatisticas=True` inclui contadores do sistema (workers, TTL, GC) |

### Catálogo

| Tool | Descrição |
|---|---|
| `pesquisar_catalogo(contexto_id, query)` | Busca CPUs/recursos por descrição ou tipo de obra |
| `auditar_catalogo(contexto_id, modo=)` | `modo="saude"` indicadores gerais; `modo="integridade"` CPUs sem equipe/PUs zerados; `modo="plausibilidade"` ratios P_can/P_orig fora do intervalo — substitui `consultar_saude_catalogo`, `verificar_integridade_catalogo`, `avaliar_plausibilidade_catalogo` |
| `comparar_rfi_catalogo(contexto_id, dry_run)` | Divergências entre RFI e catálogo |
| `historico_preco_insumo(contexto_id, insumo_id, modo=)` | `modo="pontual"` retorna preço em `data_referencia`; `modo="tendencia"` série histórica completa — substitui `consultar_preco_insumo_temporal` e `tendencia_precos_catalogo` |
| `versoes_catalogo(contexto_id, modo=)` | `modo="listar"` lista versões disponíveis; `modo="comparar"` compara duas versões — substitui `listar_versoes_catalogo` e `comparar_versoes_catalogo` |
| `atualizar_preco_insumo(...)` | Atualiza preço de insumo no contexto |
| `adicionar_variante_producao(...)` | Adiciona variante com equipe e valor horário |
| `calcular_pu_producao(...)` | Calcula PU de produção para uma composição |
| `salvar_perfil_bdi(...)` | Salva perfil BDI no contexto |
| `calcular_tributos(tipo=)` | `tipo="custo_empregador_clt"`, `"inss_empregado"` ou `"irrf"` — substitui `calcular_custo_empregador_clt`, `calcular_inss_empregado`, `calcular_irrf` |

### Análise e diagnóstico

| Tool | Descrição |
|---|---|
| `auditar_plano(project_id)` | Auditoria 360°: viabilidade, gargalos, resumo financeiro |
| `explorar_pool_recursos(project_id, face)` | Decomposição composicional-temporal do pool (7 faces) |
| `comparar_planos(project_id, plano_a, plano_b)` | Compara dois planos do mesmo escopo |
| `simular_cenario_replan(project_id, tipo, params)` | Simula impacto de alteração no plano |

### Artefatos

| Tool | Descrição |
|---|---|
| `listar_artefatos_projeto(project_id)` | Lista artefatos com nome, tipo, tamanho e audiência |
| `obter_artefato(project_id, nome_arquivo, formato=)` | `formato="texto"` para `.md`/`.json`/`.csv`; `formato="binario"` para `.png`/`.xlsx`/`.pdf` (base64); `formato="bundle"` para ZIP completo do projeto — substitui `ler_artefato_texto`, `baixar_artefato_binario`, `baixar_bundle_zip` |

### Benchmarks

| Tool | Descrição |
|---|---|
| `consultar_benchmark(benchmark_id=None)` | Sem argumento: lista todos os benchmarks com status e artefatos; com `benchmark_id`: detalha um benchmark específico — substitui `listar_benchmarks` |
| `executar_benchmark_nep039(slug, reset)` | ⚠️ **LENTO (2–7 min) — prefira o CLI** |
| `empacotar_benchmark(slug)` | Empacota resultados existentes em ZIP |
| `download_benchmark_zip(slug)` | Retorna ZIP do benchmark em base64 |

---

## Erros comuns

| Código / Mensagem | Causa | Solução |
|---|---|---|
| `Tool not found: ler_artefato_texto` | Nome antigo removido | Use `obter_artefato(formato="texto")` |
| `Tool not found: baixar_artefato_binario` | Nome antigo removido | Use `obter_artefato(formato="binario")` |
| `Tool not found: baixar_bundle_zip` | Nome antigo removido | Use `obter_artefato(formato="bundle")` |
| `Tool not found: buscar_cpu` | Nome errado | Use `pesquisar_catalogo(contexto_id, query)` |
| `Tool not found: criar_projeto_formulario` | Nome antigo removido | Use `criar_projeto(nome=..., ...)` |
| `Tool not found: configurar_escopo` | Nome antigo removido | Use `gerir_escopo(entidade="escopo", ...)` |
| `Tool not found: gerenciar_plano` | Nome antigo removido | Use `gerir_escopo(entidade="plano", ...)` |
| `Tool not found: listar_benchmarks` | Nome antigo removido | Use `consultar_benchmark()` (sem args = lista todos) |
| `Tool not found: executar_benchmark` | Nome antigo removido | Use `executar_benchmark_nep039(slug, reset)` via CLI |
| `Tool not found: avancar_pipeline` | Ferramenta removida | Use `disparar_pipeline()` + `consultar_job_pipeline()` |
| `Tool not found: obter_estatisticas_jobs` | Ferramenta removida | Use `listar_jobs_pipeline(incluir_estatisticas=True)` |
| `403 Forbidden` em `ping()` | `ping()` requer role `admin` (`system:read`) | Usar conta com permissão admin |
| `pipeline_integridade: CORROMPIDO` | Skill GATE falhou | Ver `validacoes` em `consultar_status`, corrigir inputs e re-executar |
| `status: pendente_mapeamento` | Serviço sem CPU | Usar `pesquisar_catalogo()` e repassar com `cpu_id` |
| `margem VERMELHO` | BDI ou pool de equipes fora do alvo | Revisar BDI via `salvar_perfil_bdi` e simular cenários com `simular_cenario_replan` |
| `401 Unauthorized` | Token ausente, expirado ou inválido (prod) | Renovar token JWT |
| `403 Forbidden` | Token válido mas escopo insuficiente | Usar client_id com escopo adequado |
| `429 Too Many Requests` | Rate limit atingido | Aguardar `Retry-After` segundos |
| `status: AGUARDANDO_FILA` por muito tempo | Worker pool cheio (3 jobs rodando) | Aguardar ou verificar estatísticas com `listar_jobs_pipeline(incluir_estatisticas=True)` |
| `Job 'job-xyz' não encontrado` | Job expirado após TTL (24h) ou servidor reiniciado | Jobs em memória não persistem — re-disparar pipeline se necessário |
| `progresso_percentual` não avança | Skill não reporta progresso ainda | Framework implementado mas skills precisam integração — ver ADR-102 |
| UI travada ao chamar benchmark | `executar_benchmark_nep039` bloqueia stdio | Usar `concilium benchmark run --slug X` pelo terminal |
| `ratio P_can/P_orig` nos avisos | Produtividade implícita diverge | Calibrar `precos_unitarios_sbdi` no catálogo para os CPUs afetados |
