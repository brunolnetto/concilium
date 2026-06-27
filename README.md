# Concilium

Framework deterministico para planejamento temporal e financeiro de obras, com
pipeline manifest-driven de skills, versionamento de projeto e interfaces via
CLI, API, UI e MCP.

## Visao geral

- Core de execucao em pipeline por skills, com validacoes e artefatos versionados.
- Catalogo tecnicamente governado (CPU, insumos, producoes/produtividades).
- Persistencia por projeto/versao com trilha de execucao.
- Operacao por multiplas superficies:
	- CLI (`concilium`)
	- API HTTP (`concilium-api`)
	- UI Streamlit (`concilium-ui`)
	- MCP server (ferramentas para agentes)

## Stack

- Python 3.11+
- Typer + Rich (CLI)
- FastAPI + Uvicorn (API)
- Streamlit (UI)
- Pydantic v2 (modelos)
- FastMCP (MCP server)
- Pytest + Ruff + Mypy (qualidade)

## Estrutura principal

- `src/concilium/presentation/main.py`: entrada da CLI
- `src/concilium/presentation/api/app.py`: app FastAPI
- `src/concilium/presentation/ui/prototype_streamlit.py`: UI Streamlit
- `src/concilium/application/runtime.py`: orquestracao do runtime
- `src/concilium/application/skills/manifests/`: skills por manifesto `skill.toml`
- `src/concilium/infrastructure/storage/`: armazenamento de projeto e versao
- `config/`: contextos, perfis, catalogos, referencias e jurisdicoes
- `tests/unit` e `tests/integration`: testes automatizados

## Skills atualmente presentes

As skills sao auto-descobertas em
`src/concilium/application/skills/manifests`:

- `01-escopo-e-eap`
- `02-produtividade-climatica`
- `03-catalogo-de-recursos`
- `04-cronograma`
- `05-equipes-e-alocacao`
- `06-precificacao-unitaria`
- `07-custos-indiretos`
- `08-consolidacao-financeira`
- `09-relatorio-e-artefatos`
- `10-diagnostico-criticidade`
- `11-avaliacao-intervencoes`
- `12-registro-decisoes`
- `13-assessor-replanejamento`
- `14-explorador-cenarios`
- `15-relatorio-executivo`

## Instalacao

### Desenvolvimento

```bash
pip install -e ".[dev]"
pre-commit install
```

### Instalacao limpa

```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install .

concilium --help
concilium-api --help
concilium-ui --help
```

## Execucao local

### CLI

```bash
concilium --help
concilium project --help
concilium configuration --help
concilium catalog --help
```

### API

```bash
concilium-api
```

Default local: `127.0.0.1:8000`.
Swagger: `http://127.0.0.1:8000/swagger`.

### UI

```bash
concilium-ui
```

Default local: `127.0.0.1:8501`.

## Execucao com Docker Compose

```bash
docker compose -f cd/development/docker-compose.yml up --build
```

Servicos:

- API em `http://localhost:8000`
- UI em `http://localhost:8501`

## Fluxo rapido de projeto (CLI)

```bash
# Criar projeto
concilium project init "Projeto Exemplo" --contexto samples

# Ver status
concilium project status "Projeto Exemplo"

# Rodar skill
concilium project run 01-escopo-e-eap --project "Projeto Exemplo" --inputs '{}'

# Validar projeto
concilium validate project "Projeto Exemplo"

# Aprovar versao
concilium project approve "Projeto Exemplo@v1" --as eng_senior
```

## Variaveis de ambiente

Referencia completa: `src/concilium/infrastructure/settings.py`.

### Desenvolvimento local

Arquivos usados pelo `cd/development/docker-compose.yml` (nao commitados):

- `.env.api` — vars da API (HOST, PORT, STORE_BACKEND, AUTH)
- `.env.ui` — vars da UI (UI_HOST, UI_PORT, UI_API_BASE_URL)

```bash
# Exemplo minimo .env.api para dev local com filesystem
CONCILIUM__API_HOST=0.0.0.0
CONCILIUM__STORE_BACKEND=filesystem
CONCILIUM__AUTH_ENABLED=0
OTEL_SDK_DISABLED=true
```

Profiles de compose:

```bash
docker compose -f cd/development/docker-compose.yml --profile api up --build
docker compose -f cd/development/docker-compose.yml --profile deploy up --build
```

## Deploy em producao (ACA + SharePoint)

### Visao geral do pipeline

```
bootstrap -> keys -> github -> configure -> [image -> deploy -> smoke -> promote]
```

### Variaveis por escopo

#### Azure Container Apps — env vars dos containers

Aplicadas via `deploy.sh configure` (idempotente). Necessitam das variaveis de ambiente
`SP_*` e `SMOKE_CLIENT_SECRET` definidas antes de executar.

| Variavel | API | MCP | Valor |
|---|:---:|:---:|---|
| `CONCILIUM__CONFIG_ROOT` | ✓ | ✓ | `/app` |
| `CONCILIUM__STORE_BACKEND` | ✓ | ✓ | `sharepoint` |
| `CONCILIUM__SP_TENANT_ID` | ✓ | ✓ | tenant do Entra ID |
| `CONCILIUM__SP_CLIENT_ID` | ✓ | ✓ | App Registration client ID |
| `CONCILIUM__SP_CLIENT_SECRET` | ✓ | ✓ | client secret do App Registration |
| `CONCILIUM__SP_DRIVE_ID` | ✓ | ✓ | Drive ID do SharePoint |
| `CONCILIUM__SP_ROOT_PATH` | ✓ | ✓ | `Concilium/prod` |
| `CONCILIUM__AUTH_ENABLED` | ✓ | ✓ | `1` |
| `CONCILIUM__AUTH_CLIENTS` | ✓ | ✓ | JSON gerado por `configure` a partir de `SMOKE_CLIENT_SECRET` |
| `CONCILIUM__JWT_KEY_VAULT_URL` | ✓ | ✓ | `https://concilium-kv.vault.azure.net` |
| `CONCILIUM__API_HOST` | ✓ | — | `0.0.0.0` |
| `CONCILIUM__API_PORT` | ✓ | — | `8000` |
| `CONCILIUM__MCP_TRANSPORT` | — | ✓ | `streamable-http` |
| `CONCILIUM__MCP_HOST` | — | ✓ | `0.0.0.0` |
| `CONCILIUM__MCP_PORT` | — | ✓ | `8080` |
| `OTEL_SERVICE_NAME` | ✓ | ✓ | `concilium-api` / `concilium-mcp` |

#### GitHub Secrets

Configurados via `deploy.sh github`. Mascarados nos logs do Actions.

| Secret | Descricao |
|---|---|
| `AZURE_CLIENT_ID` | App Registration OIDC para o GitHub Actions |
| `AZURE_TENANT_ID` | Tenant ID do Entra ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID do Azure |
| `CONCILIUM__SP_CLIENT_SECRET` | Client secret do App Registration SharePoint |
| `SMOKE_CLIENT_SECRET` | Secret do cliente `smoke-test` para smoke tests |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Endpoint OTLP para telemetria (opcional) |

#### GitHub Variables

| Variable | Valor |
|---|---|
| `RESOURCE_GROUP` | `concilium-rg` |
| `ACA_API_APP` | `concilium-api` |
| `ACA_MCP_APP` | `concilium-mcp` |
| `ACR_NAME` | `conciliumacr` |
| `IMAGE_NAME` | `concilium` |
| `SMOKE_CLIENT_ID` | `smoke-test` |

#### Azure Key Vault (`concilium-kv`)

Secrets buscados em runtime pela Managed Identity (`CONCILIUM__JWT_KEY_VAULT_URL`).

| Secret | Conteudo |
|---|---|
| `jwt-private-key` | Chave privada RS256 PEM (gerada por `deploy.sh keys`) |
| `jwt-public-key` | Chave publica RS256 PEM |

### Sequencia de primeiro deploy

```bash
# 1. Provisionar infra (idempotente)
deploy.sh bootstrap

# 2. Gerar JWT keys no Key Vault
deploy.sh keys

# 3. Configurar GitHub Secrets/Vars
SP_CLIENT_SECRET=<secret> SMOKE_CLIENT_SECRET=<secret> deploy.sh github

# 4. Aplicar env vars nos containers ACA
SP_TENANT_ID=<tid> SP_CLIENT_ID=<cid> SP_CLIENT_SECRET=<secret> \
SP_DRIVE_ID=<did> SMOKE_CLIENT_SECRET=<secret> \
deploy.sh configure

# 5. Build e deploy da imagem
deploy.sh image
deploy.sh deploy <tag>
deploy.sh smoke --revision <revision>
deploy.sh promote --revision <revision>
```

### Rotacao do SMOKE_CLIENT_SECRET

```bash
# Gerar novo secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Re-aplicar configuracao com o novo secret
SP_TENANT_ID=<tid> SP_CLIENT_ID=<cid> SP_CLIENT_SECRET=<secret> \
SP_DRIVE_ID=<did> SMOKE_CLIENT_SECRET=<novo-secret> \
deploy.sh configure

# Atualizar GitHub Secret
gh secret set SMOKE_CLIENT_SECRET --body "<novo-secret>" --repo mendeslobo/concilium
```

## Qualidade e manutencao

```bash
# Testes rapidos
make test

# Lint
make lint

# Type check
make type-check

# Formatacao
make fmt

# Cobertura
make coverage
```

## Governanca de commits

Este repositorio implementa governanca automatizada de commits para manter qualidade e rastreabilidade do historico.

### Setup inicial

```bash
# Automatico (recomendado)
python scripts/dev/setup_commit_governance.py

# Manual
pre-commit install
pre-commit install --hook-type commit-msg
git config commit.template .git-commit-template
```

### Regras principais

- **Limites tecnicos**: ≤15 arquivos (recomendado), ≤30 arquivos (maximo)
- **Formato obrigatorio**: `tipo(escopo): mensagem` (Conventional Commits)
- **Tipos validos**: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `style`, `build`, `ci`, `chore`, `revert`

### Ferramentas

```bash
# Validar tamanho antes de commitar
python scripts/dev/validate_commit_size.py

# Auditar historico
python scripts/dev/audit_commit_history.py

# Ver hotspots (arquivos mais modificados)
python scripts/dev/audit_commit_history.py --detailed
```

### Documentacao

- **Guia completo**: [COMMIT_GOVERNANCE.md](COMMIT_GOVERNANCE.md)
- **Guia rapido**: [COMMIT_GOVERNANCE_QUICKSTART.md](COMMIT_GOVERNANCE_QUICKSTART.md)
- **Conventional Commits**: https://www.conventionalcommits.org/

## Documentacao tecnica

- Arquitetura e ADRs: `docs/engineering/0-architecture/`
- NEPs e backlog de produto: `docs/engineering/2-development/neps/`
- Notas tecnicas de engenharia: `docs/engineering/3-technical_notes/`

