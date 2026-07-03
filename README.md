# Agente Gerente de Engenharia

Este repositório contém o **Agente Gerente de Engenharia**, um assistente de IA especializado em planejamento e gestão de obras de construção civil, construído sobre o framework `Concilium`.

O agente atua como um especialista sênior, realizando análises de viabilidade, estimativas de custo, planejamento de cronograma e otimização de recursos com base em dados técnicos e financeiros.

---

## 📋 Visão Geral do Projeto

O objetivo deste projeto é fornecer uma interface inteligente e automatizada para o planejamento de obras. O agente é capaz de:

- **Analisar e Orçar:** Calcular custos diretos e indiretos, aplicar BDI e encargos, e gerar orçamentos detalhados.
- **Planejar e Otimizar:** Criar cronogramas de execução, alocar equipes e equipamentos, e analisar a produtividade.
- **Validar e Decidir:** Avaliar a viabilidade financeira dos projetos, calcular margens de lucro, ponto de equilíbrio e analisar cenários.
- **Gerar Relatórios:** Consolidar dados e gerar artefatos como relatórios executivos e diagnósticos de criticidade.

### Arquitetura e Core

O framework **Concilium** utiliza uma arquitetura de pipeline orientada a skills:

- Pipeline manifest-driven com validações e artefatos versionados
- Catálogo tecnicamente governado (CPU, insumos, produções/produtividades)
- Persistência por projeto/versão com trilha de execução
- Operação por múltiplas interfaces: CLI, API, UI e MCP

### Stack Tecnológica

- **Python 3.11+**
- **Typer + Rich** (CLI)
- **FastAPI + Uvicorn** (API)
- **Streamlit** (UI)
- **Pydantic v2** (modelos e validação)
- **FastMCP** (MCP server)
- **Pytest + Ruff + Mypy** (qualidade e testes)

### Skills Disponíveis

As skills são auto-descobertas em `src/concilium/application/skills/manifests/`:

- `01-escopo-e-eap` — Estruturação analítica do projeto
- `02-produtividade-climatica` — Análise de fatores ambientais
- `03-catalogo-de-recursos` — Gestão de insumos e recursos
- `04-cronograma` — Planejamento temporal
- `05-equipes-e-alocacao` — Alocação de mão de obra e equipamentos
- `06-precificacao-unitaria` — Cálculo de custos unitários
- `07-custos-indiretos` — Custos administrativos e indiretos
- `08-consolidacao-financeira` — Consolidação orçamentária
- `09-relatorio-e-artefatos` — Geração de documentação
- `10-diagnostico-criticidade` — Análise de riscos
- `11-avaliacao-intervencoes` — Avaliação de mudanças
- `12-registro-decisoes` — Rastreabilidade de decisões
- `13-assessor-replanejamento` — Assistente de replanejamento
- `14-explorador-cenarios` — Análise de cenários
- `15-relatorio-executivo` — Relatórios gerenciais

---

## 🚀 Como Começar

### Instalação para Desenvolvimento

```bash
# 1. Clone o repositório
git clone https://github.com/mendes-lobo-construcao/agente-gerente-de-engenharia.git
cd agente-gerente-de-engenharia

# 2. Crie e ative um ambiente virtual
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\Activate.ps1  # Windows PowerShell

# 3. Instale as dependências em modo de desenvolvimento
pip install -e ".[dev]"

# 4. Configure os hooks de pre-commit
pre-commit install
```

### Instalação Limpa (Produção)

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install .

# Verifique a instalação
concilium --help
concilium-api --help
concilium-ui --help
```

---

## 💻 Como Usar

O agente pode ser operado através de múltiplas interfaces:

### 1. Linha de Comando (CLI)

A CLI é a principal forma de interação para automação e execução de fluxos.

```bash
# Comandos disponíveis
concilium --help
concilium project --help
concilium configuration --help
concilium catalog --help

# Fluxo básico de projeto
concilium project init "Meu Projeto" --contexto samples
concilium project status "Meu Projeto"
concilium project run 01-escopo-e-eap --project "Meu Projeto"
concilium validate project "Meu Projeto"
concilium project approve "Meu Projeto@v1" --as eng_senior
```

### 2. API (Servidor HTTP)

A API permite integração com outros sistemas.

```bash
# Iniciar o servidor
concilium-api
```

- **Endpoint:** `http://127.0.0.1:8000`
- **Documentação Swagger:** `http://127.0.0.1:8000/swagger`

### MCP Proxy Remoto

Para conectar ao servidor MCP em produção via proxy, configure (macOS/Linux):

```json
{
  "mcpServers": {
    "concilium": {
      "command": "concilium-mcp-proxy",
      "env": {
        "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br",
        "CONCILIUM_CLIENT_CODE": "RCODE-..."
      }
    }
  }
}
```

**Windows:** use `cmd /c` em vez do comando puro:

```json
{
  "mcpServers": {
    "concilium": {
      "command": "cmd",
      "args": ["/c", "concilium-mcp-proxy"],
      "env": {
        "CONCILIUM_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br",
        "CONCILIUM_CLIENT_CODE": "RCODE-..."
      }
    }
  }
}
```

Por quê: no Windows, apps GUI como o Claude Desktop podem herdar um `PATH` desatualizado ou sem o
diretório `Scripts` do Python (comum em instalações via `pip install --user` ou Microsoft Store) —
`"command": "concilium-mcp-proxy"` sozinho falha mesmo com o pacote instalado corretamente. `cmd /c`
força uma releitura do `PATH` do registro no lançamento, resolvendo isso **sem** precisar de um path
absoluto hardcoded por usuário/máquina (o que não escala — cada instalação tem um path diferente,
embutindo usuário e versão do Python).

`concilium auth add-user`, `regenerate-code` e `migrate-legacy-codes` não pedem pra escolher a
plataforma — o admin não sabe necessariamente o SO do dispositivo final no momento do cadastro.
Os dois blocos (macOS/Linux e Windows) são sempre gerados/enviados juntos (por email, em anexos
separados; no console, um após o outro), e o próprio usuário usa o que corresponde ao seu sistema.

**Notas:**
- `CONCILIUM_CLIENT_CODE`: Código fornecido pelo administrador para ativar o dispositivo
- `device_id`: Auto-detectado (hostname ou username@hostname) - não precisa configurar
- Tokens são armazenados localmente em `~/.concilium/tokens/` (chmod 600)

**Verificando a primeira ativação:**

Depois de configurar, abra o Claude Desktop e confira o log do MCP server ("View Logs" no app, ou o
arquivo em `%APPDATA%\Claude\logs\` / `~/Library/Logs/Claude/`) por uma linha `Autenticado com sucesso.`
Isso confirma que o `refresh_token` foi salvo em `~/.concilium/tokens/<device_id>.json` — a partir daí,
o proxy não depende mais do `CONCILIUM_CLIENT_CODE` no dia a dia (só reativa com ele se o token expirar
ou for revogado; validade padrão: 90 dias).

**Problema conhecido — `claude_desktop_config.json` "voltando sozinho":** em algumas instalações, o
Claude Desktop reescreve esse arquivo com um valor antigo/de outra sessão ao reiniciar (ex.: sincronização
de configuração de MCP servers atrelada à conta), revertendo edições manuais no bloco `env`. Se isso
acontecer e a ativação continuar falhando mesmo com o código correto, ative uma vez manualmente pelo
terminal para gravar o token em cache diretamente (sem depender do arquivo persistir):

```bash
CONCILIUM_CLIENT_CODE="RCODE-..." CONCILIUM_SERVER_URL="https://mcp.mendesloboconstrucao.com.br" concilium-mcp-proxy
# aguarde a linha "Autenticado com sucesso." e encerre com Ctrl+C
```

Isso é um comportamento do cliente (Claude Desktop), fora do controle deste projeto.

### 3. Interface de Usuário (UI)

Interface visual baseada em Streamlit.

```bash
# Iniciar a aplicação
concilium-ui
```

- **Endpoint:** `http://127.0.0.1:8501`

### 4. Docker Compose (Desenvolvimento)

```bash
# Subir todos os serviços
docker compose -f cd/development/docker-compose.yml up --build

# Profiles específicos
docker compose -f cd/development/docker-compose.yml --profile api up --build
docker compose -f cd/development/docker-compose.yml --profile deploy up --build
```

**Serviços disponíveis:**
- API: `http://localhost:8000`
- UI: `http://localhost:8501`

---

## 📁 Estrutura do Projeto

```
agente-gerente-de-engenharia/
├── src/concilium/           # Código-fonte principal
│   ├── application/         # Lógica de negócio e skills
│   ├── domain/              # Entidades e modelos de domínio
│   ├── presentation/        # Interfaces (CLI, API, UI)
│   └── infrastructure/      # Adapters e serviços externos
├── config/                  # Configurações e catálogos
│   ├── catalogos/          # Catálogos de insumos
│   ├── contextos/          # Contextos de projeto
│   ├── perfis/             # Perfis de cálculo
│   ├── jurisdicoes/        # Dados jurisdicionais
│   └── referencias/        # Referências (CPU, ANP, etc.)
├── tests/                   # Testes automatizados
│   ├── unit/               # Testes unitários
│   └── integration/        # Testes de integração
├── scripts/                 # Scripts de automação
│   ├── dev/                # Scripts de desenvolvimento
│   ├── catalog/            # Scripts de catálogo
│   └── benchmark/          # Scripts de benchmark
├── docs/                    # Documentação técnica
│   ├── engineering/        # Documentação de engenharia
│   └── product/            # Documentação de produto
├── projetos/               # Dados de projetos (local)
├── cd/                     # Configurações de deploy
│   ├── development/        # Docker Compose para dev
│   └── production/         # Infraestrutura (Bicep/Azure)
└── benchmarks/             # Benchmarks e validações
```

### Arquivos Principais

- `src/concilium/presentation/main.py` — Entrada da CLI
- `src/concilium/presentation/api/app.py` — Aplicação FastAPI
- `src/concilium/presentation/ui/prototype_streamlit.py` — Interface Streamlit
- `src/concilium/application/runtime.py` — Orquestração do runtime
- `src/concilium/infrastructure/settings.py` — Configurações e variáveis de ambiente

---

## ⚙️ Configuração

### Variáveis de Ambiente

Referência completa: `src/concilium/infrastructure/settings.py`.

#### Desenvolvimento Local

Arquivos de configuração (não commitados):
- `.env.api` — Variáveis da API
- `.env.ui` — Variáveis da UI

**Exemplo mínimo para desenvolvimento local:**

```bash
# .env.api
CONCILIUM__API_HOST=0.0.0.0
CONCILIUM__STORE_BACKEND=filesystem
CONCILIUM__AUTH_ENABLED=0
OTEL_SDK_DISABLED=true
```

---

## 🚢 Deploy em Produção (Azure Container Apps + SharePoint)

### Pipeline de Deploy

```
bootstrap → keys → github → configure → [image → deploy → smoke → promote]
```

### Sequência de Primeiro Deploy

```bash
# 1. Provisionar infraestrutura
cd/scripts/deploy.sh bootstrap

# 2. Gerar chaves JWT no Key Vault
cd/scripts/deploy.sh keys

# 3. Configurar GitHub Secrets/Variables
SP_CLIENT_SECRET=<secret> SMOKE_CLIENT_SECRET=<secret> \
  cd/scripts/deploy.sh github

# 4. Aplicar variáveis de ambiente nos containers
SP_TENANT_ID=<tid> SP_CLIENT_ID=<cid> SP_CLIENT_SECRET=<secret> \
SP_DRIVE_ID=<did> SMOKE_CLIENT_SECRET=<secret> \
  cd/scripts/deploy.sh configure

# 5. Build, deploy e validação
cd/scripts/deploy.sh image
cd/scripts/deploy.sh deploy <tag>
cd/scripts/deploy.sh smoke --revision <revision>
cd/scripts/deploy.sh promote --revision <revision>
```

### Variáveis de Ambiente (Produção)

**Azure Container Apps:**

| Variável | API | MCP | Descrição |
|----------|:---:|:---:|-----------|
| `CONCILIUM__CONFIG_ROOT` | ✓ | ✓ | `/app` |
| `CONCILIUM__STORE_BACKEND` | ✓ | ✓ | `sharepoint` |
| `CONCILIUM__SP_TENANT_ID` | ✓ | ✓ | Tenant do Entra ID |
| `CONCILIUM__SP_CLIENT_ID` | ✓ | ✓ | App Registration client ID |
| `CONCILIUM__SP_CLIENT_SECRET` | ✓ | ✓ | Client secret |
| `CONCILIUM__SP_DRIVE_ID` | ✓ | ✓ | Drive ID do SharePoint |
| `CONCILIUM__SP_ROOT_PATH` | ✓ | ✓ | `Concilium/prod` |
| `CONCILIUM__AUTH_ENABLED` | ✓ | ✓ | `1` |
| `CONCILIUM__JWT_KEY_VAULT_URL` | ✓ | ✓ | Key Vault URL |
| `CONCILIUM__API_HOST` | ✓ | — | `0.0.0.0` |
| `CONCILIUM__API_PORT` | ✓ | — | `8000` |
| `CONCILIUM__MCP_TRANSPORT` | — | ✓ | `streamable-http` |
| `CONCILIUM__MCP_HOST` | — | ✓ | `0.0.0.0` |
| `CONCILIUM__MCP_PORT` | — | ✓ | `8080` |

**GitHub Secrets:**

- `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
- `CONCILIUM__SP_CLIENT_SECRET`, `SMOKE_CLIENT_SECRET`
- `OTEL_EXPORTER_OTLP_ENDPOINT` (opcional)

**Azure Key Vault (`concilium-kv`):**

- `jwt-private-key` — Chave privada RS256 PEM
- `jwt-public-key` — Chave pública RS256 PEM

### Rotação de Secrets

```bash
# Gerar novo secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Re-aplicar configuração
SP_TENANT_ID=<tid> SP_CLIENT_ID=<cid> SP_CLIENT_SECRET=<secret> \
SP_DRIVE_ID=<did> SMOKE_CLIENT_SECRET=<novo-secret> \
  cd/scripts/deploy.sh configure

# Atualizar GitHub Secret
gh secret set SMOKE_CLIENT_SECRET --body "<novo-secret>" \
  --repo mendes-lobo-construcao/agente-gerente-de-engenharia
```

---

## 🤝 Como Contribuir

Agradecemos o interesse em contribuir! Seguimos diretrizes rigorosas de qualidade.

### Governança de Commits

Este repositório implementa governança automatizada de commits com **Conventional Commits**.

#### Setup Inicial

```bash
# Automático (recomendado)
python scripts/dev/setup_commit_governance.py

# Manual
pre-commit install
pre-commit install --hook-type commit-msg
git config commit.template .git-commit-template
```

#### Regras de Commits

- **Formato obrigatório:** `tipo(escopo): mensagem`
- **Tipos válidos:** `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `style`, `build`, `ci`, `chore`, `revert`
- **Limites técnicos:** ≤15 arquivos (recomendado), ≤30 arquivos (máximo)

**Exemplos:**
```bash
feat(api): adiciona endpoint de status do projeto
fix(cronograma): corrige cálculo de dias úteis
refactor(skills): reorganiza estrutura de manifests
docs(readme): atualiza instruções de instalação
```

#### Ferramentas de Validação

```bash
# Validar tamanho do commit antes de commitar
python scripts/dev/validate_commit_size.py

# Auditar histórico de commits
python scripts/dev/audit_commit_history.py

# Ver hotspots (arquivos mais modificados)
python scripts/dev/audit_commit_history.py --detailed
```

### Qualidade de Código

```bash
# Executar testes
make test

# Lint (verificação de estilo)
make lint

# Type checking (verificação de tipos)
make type-check

# Formatação automática
make fmt

# Cobertura de testes
make coverage
```

### Documentação

Consulte os seguintes recursos para mais informações:

- **[COMMIT_GOVERNANCE.md](COMMIT_GOVERNANCE.md)** — Guia completo de governança
- **[COMMIT_GOVERNANCE_QUICKSTART.md](COMMIT_GOVERNANCE_QUICKSTART.md)** — Guia rápido
- **[Conventional Commits](https://www.conventionalcommits.org/)** — Especificação oficial
- **`docs/engineering/`** — Documentação técnica e ADRs
- **`docs/product/`** — Documentação de produto e NEPs

---

## 📚 Documentação Técnica

- **Arquitetura e ADRs:** `docs/engineering/0-architecture/`
- **NEPs e Backlog de Produto:** `docs/engineering/2-development/neps/`
- **Notas Técnicas de Engenharia:** `docs/engineering/3-technical_notes/`

---

## 📄 Licença

Este projeto é propriedade de **Mendes Lobo Construção**. Todos os direitos reservados.
