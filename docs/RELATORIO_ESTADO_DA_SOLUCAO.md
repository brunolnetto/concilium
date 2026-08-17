# Relatório de Estado da Solução — Concilium / AGIS

**Data de referência:** 2026-08-14  
**Branch:** `main` — `mendes-lobo-construcao/agente-gerente-de-engenharia`  
**Audiência:** Engenheiros e times que continuarão o desenvolvimento

---

## 1. Propósito e Escopo

O **Concilium** é o framework central do **Agente Gerente de Engenharia** — um sistema de planejamento e orçamento de obras de construção civil, com foco inicial em terraplenagem (supressão vegetal, escavação, carga, transporte). O sistema:

- Recebe uma EAP (Estrutura Analítica do Projeto) com quantitativos e cronograma;
- Aplica um pipeline de 9 skills sequenciais para calcular custo operacional, preço de venda, margem e viabilidade;
- Persiste um artefato canônico (JSON estruturado) por projeto/versão;
- Exporta planilha Excel auditável (`.xlsm`) como saída final.

O estado atual cobre o ciclo completo de **planejamento de obra de campo**, da EAP ao relatório executivo, com modelo financeiro rigoroso baseado em custo de pool de recursos.

---

## 2. Arquitetura

### 2.1 Camadas (Clean Architecture + DDD)

```
src/concilium/
├── domain/          ← Entidades, regras de negócio, repositórios (interfaces)
│   ├── models/      ← Catalog (CPU, Insumo, Producao), Canonical, Financial, Project
│   ├── services/    ← Lógica de domínio pura (analytics, financial, planning)
│   └── validations/ ← Validadores de invariantes de negócio
│
├── application/     ← Orquestração, skills, serviços de aplicação
│   ├── skills/      ← Pipeline de 9 skills (ver §3)
│   ├── runtime/     ← Executor de pipeline, deliverables (PDF, Excel, charts)
│   ├── services/    ← ConciliumService, ProjectService, CampaignService, etc.
│   ├── benchmarks/  ← Suite de benchmarks com dados reais de projetos
│   ├── scheduling/  ← RCPSP solver (OR-Tools / PuLP)
│   └── optimizer/   ← Otimização de alocação de recursos e pool
│
├── infrastructure/  ← Adaptadores externos (storage, catálogo, auth, telemetria)
│   ├── catalog/     ← DuckDB query engine + JSON loader + SICRO mapping
│   ├── adapters/    ← Blob storage (Azure/S3/GDrive), Excel sheets
│   ├── auth/        ← JWT (PyJWT + Azure Key Vault)
│   └── observability/ ← OpenTelemetry (OTEL exporter)
│
└── presentation/    ← Entradas e saídas do sistema
    ├── cli/         ← Typer + Rich (interface de linha de comando)
    ├── api/         ← FastAPI + Uvicorn (REST API com rate limiting)
    ├── mcp/         ← FastMCP server (protocolo MCP para agentes LLM)
    └── ui/          ← Streamlit (interface web)
```

**Restrições de importação** são impostas via `import-linter` (ver `pyproject.toml`):
- `domain` nunca importa de `application`, `infrastructure` ou `presentation`;
- `application` nunca importa de `presentation`;
- `presentation.api` nunca importa diretamente de `domain` (apenas via `application`).

Violações bloqueiam o CI.

### 2.2 Interfaces de Entrada

| Interface | Comando/Rota | Uso principal |
|-----------|-------------|---------------|
| CLI | `concilium run <projeto>` | Desenvolvimento, scripts, CI |
| API REST | `POST /projects/{id}/run` | Integração com outros sistemas |
| MCP Server | Tools expostos via protocolo MCP | Agentes LLM (Claude Desktop, etc.) |
| Streamlit UI | `concilium-ui` | Visualização interativa de resultados |

---

## 3. Pipeline de 9 Skills

As skills são **auto-descobertas** no diretório `src/concilium/application/skills/manifests/` e executadas em sequência numerada. Cada skill lê o artefato canônico, processa sua camada e escreve de volta.

```
01-escopo-e-eap
    ↓  EAP validada + precedências (DAG)
02-produtividade-climatica
    ↓  Fator β (praticabilidade) por semana e jurisdição
03-catalogo-de-recursos
    ↓  CPU, Producao e Insumos resolvidos
04-cronograma
    ↓  Cronograma semanal: qtd = ρ × β × h × n_equipes
05-equipes-e-alocacao
    ↓  Custo horário de equipes (MO + EQ + COMB + MAT) + pool de recursos
06-resultado-financeiro
    ↓  PU, BDI, custo direto/indireto, margem, ponto de equilíbrio
07-diagnostico-criticidade
    ↓  Análise de sensibilidade, caminho crítico, τ_i por atividade
08-replanejamento-e-cenarios
    ↓  Espaço de planos alternativos (cenários ±5/10/15%)
09-relatorio-e-artefatos
    ↓  Planilha Excel (.xlsm) + JSON canônico final
```

### 3.1 Contrato entre Skills

Cada skill recebe e retorna um objeto **`ConciliumCanonical`** — modelo Pydantic v2 que funciona como o "estado compartilhado" do pipeline. O canônico nunca é apagado entre skills; ele é **enriquecido** em cada passo.

---

## 4. Modelo Financeiro — Hipóteses Construtivas

Esta seção documenta as hipóteses que fundamentam os cálculos do pipeline. São verdades verificadas em obra e formalizadas como axiomas do sistema.

### 4.1 Decomposição de Custos em Dois Pools

O custo operacional real de uma atividade $i$ é:

$$OC_{\text{total}} = C_{\text{pool}}^c + C_{\text{pool}}^v$$

**Pool Contratual** ($C_{\text{pool}}^c$): pago por tempo de permanência, independente da produção.  
Composto por: Mão de Obra + Equipamentos (aluguel) + Mobilização/Desmobilização + Overhead (ADM, TOP, QSMS, LAB).

**Pool Consumível** ($C_{\text{pool}}^v$): pago apenas pelas horas efetivamente produtivas.  
Composto por: Diesel/combustível + materiais consumíveis.

**Consequência crítica:** O custo contratual é pago **mesmo em dias ociosos** (chuva, feriado, falta de frente). O consumível não.

### 4.2 Produtividade Efetiva = ρ × β

| Símbolo | Significado | Fonte |
|---------|-------------|-------|
| $\rho$ | Produtividade base de catálogo (m²/h, m³/h, etc.) em condições ideais | `Producao.producao_horaria` |
| $\beta$ | Fator climático/calendário $\in [0.4, 1.0]$ | Skill 02 (INMET/calendário) |
| $\rho \times \beta$ | Produtividade efetivamente realizada | Aplicado em Skill 04 |

### 4.3 Razão de Ineficiência τ_i

O ratio entre custo operacional real e custo de catálogo:

$$\tau_i = \frac{OC_i}{CC_i} \geq 1$$

**τ_i = 1** é impossível quando $\beta < 1$ ou há permanência mínima não-amortizada.  
Para projetos grandes: $\tau_i \approx 1/\bar{\varepsilon}$ (onde $\bar{\varepsilon}$ = eficiência média ponderada).  
Para projetos pequenos: τ_i cresce porque o overhead fixo (mob/demob, permanência mínima) não se dilui sobre volume suficiente.

A decomposição analítica exata é:

$$\tau_i = 1 + \frac{(1-\delta_i^*)(1-\bar\varepsilon_i)}{\bar\varepsilon_i}$$

onde $\delta_i^* = \frac{\gamma_i^{consumo}}{\gamma_i^{total}}$ é a fração de custos consumíveis.

**No código:** `frentes_equivalentes_necessarias` em `_ponto_equilibrio.py`.

### 4.4 Pool com Múltiplas Atividades — Compartilhamento de Recursos

Quando um recurso serve múltiplas atividades sequencialmente (cadeia de perpetuação), o custo contratual é calculado sobre o **envelope temporal do pool** — não a soma de cada atividade isolada:

$$C_{\text{pool}}^c = qt \cdot c_{\text{sem}} \cdot (T_{\max} - T_{\min}) + \sum_k (c_{\text{mob}} + c_{\text{demob}}) + \sum c_{\text{standby}} \cdot \text{gap}$$

**Critério de perpetuação (ADR-073):** mantém recurso em standby se:

$$c_{\text{standby}} \cdot |\text{gap}| < c_{\text{mob}} + c_{\text{demob}}$$

O custo do pool é **particionado entre atividades** via diagrama de Euler:
- Regiões exclusivas → 100% para a atividade
- Regiões de sobreposição → divisão Shapley uniforme ($c_r / n$)
- Gaps → imputados ao sucessor causal mais próximo

**Invariante garantida:** $\sum_i \phi_i = C_{\text{pool}}$ (sem resíduos).

### 4.5 BDI — Estrutura Multiplicativa por Categoria (TCU Acórdão 2622/2013)

$$\text{BDI}^{(c)} = \frac{(1+AC)(1+DF)(1+R)(1+CR)(1+L)}{1 - T} - 1$$

Taxas default calibradas contra a planilha AGIS / Ferrovia Nova Transnordestina:

| Categoria | BDI default |
|-----------|-------------|
| Mão de Obra | ≈ 29,97% |
| Equipamentos (aluguel + manutenção) | ≈ 29,97% |
| Material | 4,00% |
| Combustível/Diesel | **4,00%** (ADR-090: mercadoria, não serviço) |

**Cadeia de resolução de BDI** (prioridade decrescente):
1. `inputs.tax_scenario` (reforma fiscal CBS/IBS)
2. `inputs.bdi_aplicado` (override manual)
3. `inputs.tabela_bdi` + `inputs.perfil_bdi` + alíquotas de jurisdição
4. `DEFAULT_BDI_TABELA` (fallback)

### 4.6 Encargos de Mão de Obra

Todo custo de MO é multiplicado por **1,66×**:

$$1{,}00 \text{ (base)} + 0{,}30 \text{ (CLT)} + 0{,}31 \text{ (13°+férias)} + 0{,}05 \text{ (admin)} = 1{,}66$$

Não há exceção. Aplicado a equipes diretas e a todos os indiretos (ADM, TOP, LAB, QSMS).

### 4.7 Viabilidade

O projeto é viável se e somente se:

$$\text{BDI}_{\text{aplicado}} > \tau_i - 1$$

Ou equivalentemente: **Margem ∈ [8%, 10%]** para status VERDE.

---

## 5. Qualidade de Código

### 5.1 Ferramentas

| Ferramenta | Papel | Configuração |
|-----------|-------|-------------|
| **Ruff** | Lint + formatação (substitui flake8 + black + isort) | `pyproject.toml [tool.ruff]`, linha máxima 120 |
| **ty** (Astral) | Type checking estático, pinado em `ty==0.0.56` | Bloqueante no CI, cobre toda `src/` |
| **import-linter** | Restrições de importação entre camadas | Contratos declarados em `pyproject.toml` |
| **pytest** | 15.237 testes coletados, modo `asyncio_mode=auto` | `pytest.ini` + `pyproject.toml` |
| **pre-commit** | Gatilho local antes do commit | `.pre-commit-config.yaml` |

### 5.2 Pirâmide de Testes

```
tests/
├── unit/               ← A base: isolados, sem I/O externo
│   ├── application/    ← Skills, services, scheduler, optimizer
│   ├── domain/         ← Modelos, validadores, serviços de domínio
│   ├── infrastructure/ ← Adaptadores, catálogo, auth, storage
│   └── presentation/   ← CLI, API, MCP, UI helpers
│
├── integration/        ← Com infraestrutura real (benchmarks, pipeline E2E)
│   ├── benchmark/
│   ├── pipeline/
│   └── cost/
│
├── fixtures/           ← Dados de entrada para testes
└── samples/            ← Projetos reais de referência
```

**Marcadores de pytest:**
- `slow` — testes > 1s, excluídos do `make test` padrão
- `flaky` — sensíveis a timing/carga, tolerados em CI lento
- `integration` — requerem infraestrutura (storage, catálogo completo)

### 5.3 Variáveis de Ambiente para Testes

```bash
PYDANTIC_DISABLE_PLUGINS=__all__  # elimina ~10-15s de boot do logfire plugin
OTEL_SDK_DISABLED=true            # desativa exporters OpenTelemetry em testes
```

Ambas estão encapsuladas em `TEST_ENV` no Makefile.

### 5.4 Pre-commit Local

Além dos hooks padrão (trailing-whitespace, check-yaml, detect-private-key), há dois hooks customizados:
- **validate-commit-size** — rejeita commits excessivamente grandes
- **validate-commit-msg** — impõe formato Conventional Commits

---

## 6. Esteira CI/CD

### 6.1 CI (Pull Requests e Push para `main`)

Pipeline em `.github/workflows/ci.yml` com 4 jobs independentes:

```
┌─────────────────────────────────────────────────────────┐
│  changes  (detecta mudanças em tools/mcp-proxy/)        │
└──────────────────┬──────────────────────────────────────┘
                   │
    ┌──────────────┼───────────────┬────────────────────┐
    ▼              ▼               ▼                    ▼
  lint           type-check      test              mcp-proxy
  (ruff)         (ty==0.0.56)    (pytest -m        (isolado,
                                  "not slow         só se proxy
                                  and not flaky")   mudou)
```

O job `test` sobe todos os 720 arquivos de teste mas exclui `slow` e `flaky`, sendo rápido o suficiente para não bloquear PRs. O relatório pytest (`.pytest-report.json`) é uploadado como artefato GitHub Actions.

### 6.2 Deploy (Push para `main` com mudanças em `src/`)

Pipeline em `.github/workflows/deploy.yml`:

```
build
  └─ docker build + push → Azure Container Registry (ACR)
       │
       ├─ deploy-revision
       │    └─ az containerapp update → nova revision sem promover tráfego
       │         └─ smoke (validação automática da nova revision)
       │              └─ promote → 100% tráfego para nova revision
       │
       └─ update-observability-job
            └─ atualiza Container Apps Job de coleta de métricas
```

**Estratégia blue/green:** nova revision recebe 0% de tráfego até o smoke passar. Se o promote falhar, o rollback é manual (`make rollback`).

**Serialização:** `concurrency: group: deploy-production, cancel-in-progress: false` — deploys em fila, nunca cancelados no meio.

### 6.3 Infraestrutura (Azure)

| Recurso | Finalidade |
|---------|-----------|
| Azure Container Apps (ACA) | Runtime da API e MCP Server |
| Azure Container Registry (ACR) | Registry de imagens Docker |
| Azure Key Vault | JWT keys, secrets de infraestrutura |
| Azure Blob Storage | Persistência de projetos e artefatos |

Provisionamento é idempotente via `cd/scripts/provision.sh` (chamado por `make bootstrap`).

---

## 7. Configuração

### 7.1 Arquivo Central

`config/concilium.yaml` centraliza todos os parâmetros tuneáveis:
- Backend de catálogo: `local_json` | `google_sheets` | `sharepoint`
- TTL de cache remoto
- Parâmetros de BDI default
- Thresholds de margem (VERDE/AMARELO/VERMELHO)
- Configuração de scheduling (RCPSP solver)

### 7.2 Catálogo de Recursos

Estrutura em `config/catalogos/{contexto}/`:
```
config/catalogos/mendeslobo/
├── insumos/         ← Preços de MO, EQ, materiais
├── cpus/            ← Composições de Preço Unitário
├── produtividades/  ← ρ por serviço (versioned, First-Class)
└── perfis/          ← Configurações de BDI por contexto
```

O contexto `mendeslobo` é o catálogo primário calibrado. `rfi-r02`, `samples` e `test` são contextos alternativos.

### 7.3 Contextos e Jurisdições

- **Contextos** (`config/contextos/`): combinam catálogo + regime de trabalho + jurisdição
- **Jurisdições** (`config/jurisdicoes/BR-*.json`): calendários de feriados por estado
- **Calendários** (`config/calendarios/`): base global + sobreposições regionais

---

## 8. Benchmarks e Dados de Referência

O diretório `benchmarks/` contém dados reais de projetos para validação:

| Projeto | Localização | Uso |
|---------|-------------|-----|
| MATA_DENSA_SIMPLES | GO | Caso base de calibração (τ_i = 4.31) |
| MATA_DENSA | GO | Variação com múltiplas frentes |
| AGIS | — | Projeto primário de referência |
| LUNDIN, MARA_ROSA, VALE, etc. | Vários | Casos de validação cross-projeto |

Os benchmarks são executados via `benchmarks/campaign_runner.py` e produzem artefatos em `benchmarks/data/{PROJETO}/`. O script `scripts/audit_fallback_usage.py` audita qual fração dos projetos usa fallback de composição vs. bottom-up.

---

## 9. MCP Proxy (Ferramenta Standalone)

`tools/mcp-proxy/` é um pacote Python **completamente isolado** do restante do monorepo:
- Nunca importa `concilium`
- Tem seu próprio `pyproject.toml` com dependências mínimas (`httpx` only)
- CI job `mcp-proxy` instala apenas suas dependências (sem `pip install -e .` da raiz)
- Qualquer importação acidental de `concilium` falha o CI por ImportError

---

## 10. Observabilidade

O sistema usa OpenTelemetry para traces e métricas:
- `OTEL_SDK_DISABLED=true` desativa em dev/testes
- Em produção: `opentelemetry-exporter-otlp-proto-http` exporta para collector configurado
- Instrumentações ativas: FastAPI, logging
- Container Apps Job separado coleta métricas de observabilidade

---

## 11. Pontos de Atenção e Trabalho Pendente

### 11.1 Limitação Conhecida (ADR-148)

O **gap climático é diagnosticado em N3 mas nunca cobrado em N4**: a duração do cronograma não é estendida por clima. As equipes compensam clima reduzindo horas produtivas por dia, não estendendo datas. Isso mantém o RCPSP computável mas significa que `gap_praticabilidade` em `_bridge.py` é indicativo, não operacional.

### 11.2 Fórmula de τ_i — Gap Residual

A fórmula analítica $\tau_i = 1 + (1-\delta_i^*)(1-\bar\varepsilon_i)/\bar\varepsilon_i$ captura ~85% da estrutura observada. O gap residual de ~15% se deve a overhead "semi-contratado" (QSMS, LAB) que tem sensibilidade parcial a $\varepsilon_j$ mas é tratado como totalmente fixo no modelo. Documentado em `MAPEAMENTO_TEORIA_CODIGO.md §2.F`.

### 11.3 Degradação de Produtividade com Múltiplas Frentes

O modelo atual assume que $\varepsilon_j$ é independente do número de frentes paralelas ($m_{ij}$). Na prática, múltiplas equipes disputando o mesmo espaço de trabalho degradam produtividade. O modelo de degradação $\varepsilon_j = \varepsilon_0 - k(n-1)$ está proposto mas não calibrado nem implementado.

### 11.4 Reforma Fiscal CBS/IBS

O campo `tax_scenario` na cadeia de resolução de BDI (Prioridade 1) suporta o cenário pós-reforma fiscal CBS/IBS. A implementação existe como placeholder — as alíquotas reais precisam ser atualizadas quando a legislação for consolidada.

---

## 12. Como Continuar

### Para Rodar Localmente

```bash
git clone https://github.com/mendes-lobo-construcao/agente-gerente-de-engenharia
cd agente-gerente-de-engenharia
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# Rodar testes (rápidos)
make test

# Rodar verificações de qualidade
make check

# Rodar benchmark de referência
python benchmarks/run_mata_densa_simples.py
```

### Para Entender o Modelo Financeiro

Ler nesta ordem:
1. `docs/AXIOMAS_INVARIANTES_CONFORMIDADE.md` — axiomas e invariantes de negócio
2. `docs/product/5-specifications/FORMULARIO_RIGOROSO_DERIVACAO.md` — derivação matemática completa (30 seções, auditada contra código em 2026-08-17)
3. `docs/MAPEAMENTO_TEORIA_CODIGO.md` — como cada símbolo mapeia para o código
4. `docs/ALGEBRA_POOL_IMPLEMENTACAO.md` — teoria de conjuntos do pool de recursos

### Para Entender o Pipeline

1. `docs/FLUXO_DADOS_SKILLS.md` — rastreamento de variáveis entre skills
2. `docs/MAPEAMENTO_FORMULARIO_SKILLS.md` — estrutura de dados e fórmulas por skill
3. `src/concilium/application/skills/manifests/` — código das skills

### Para Fazer Deploy

```bash
make bootstrap   # provisiona infra Azure (idempotente)
make keys        # gera JWT keys no Key Vault
make github-secrets  # configura GitHub Secrets
# A partir daí, push para main com mudanças em src/ dispara deploy automático
```

---

## 13. Mapa de Documentação

| Documento | Conteúdo | Status |
|-----------|---------|--------|
| `docs/product/5-specifications/FORMULARIO_RIGOROSO_DERIVACAO.md` | Derivação matemática: Schedule → Quantitativo Semanal → Pool/Material → BDI → Indireto Semanal → Margem (θ/λ/τ) → Resultado | ✅ Completo e auditado contra código (v5.7) |
| `docs/MAPEAMENTO_TEORIA_CODIGO.md` | Símbolos teóricos ↔ variáveis de código | ✅ Completo |
| `docs/AXIOMAS_INVARIANTES_CONFORMIDADE.md` | 11 axiomas + invariantes + matriz de conformidade | ✅ Completo |
| `docs/MAPEAMENTO_FORMULARIO_SKILLS.md` | Estrutura de dados, fórmulas e rastreamento por skill | ✅ Completo |
| `docs/FLUXO_DADOS_SKILLS.md` | Fluxo de variáveis N1→N4 com exemplos numéricos | ✅ Completo |
| `docs/ALGEBRA_POOL_IMPLEMENTACAO.md` | Teoria de conjuntos do pool (Euler diagrams, perpetuação) | ✅ Completo |
| `docs/EFICIENCIA_PRODUTIVA_CONSOLIDADA.md` | Como ρ e β fluem pelo pipeline | ✅ Completo |
| `README.md` | Getting started, stack, skills disponíveis | ✅ Atualizado |

---

*Documento gerado em 2026-08-14 a partir do estado do branch `main`.*
