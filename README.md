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

## Variaveis de ambiente (resumo)

Arquivo de referencia: `.env.example`.

### Diretorios

- `CONCILIUM__ROOT`
- `CONCILIUM__CONFIG_ROOT`
- `CONCILIUM__PROJECTS_ROOT`
- `CONCILIUM__BENCHMARK_PROJECTS_ROOT`
- `CONCILIUM__STORE_BACKEND` (opções: `local_json`, `sharepoint`, `s3`; default: `filesystem`)

Backends de store:

1. `local_json` (alias: `filesystem`) — store local por diretório/JSON
2. `sharepoint` — via Graph API (`concilium[sharepoint]`)
3. `s3` — via S3 API com `aioboto3` (`concilium[s3]`)

### Runtime config (transicao de YAML para env/file)

Precedencia do arquivo de runtime:

1. `CONCILIUM__RUNTIME_CONFIG_FILE`
2. `CONCILIUM__CONFIG_FILE` (legado)
3. `CONCILIUM__CONFIG_ROOT/concilium.yaml`

Formatos suportados: `.yaml/.yml`, `.json`, `.toml`.

Override granular por env (sem editar arquivo):

- Prefixo: `CONCILIUM__CFG__`
- Exemplo: `CONCILIUM__CFG__progress__spi__ahead_threshold=1.1`

### Mapping de benchmark (EAP -> CPU)

Precedencia:

1. `CONCILIUM__BENCHMARK_CPU_MAPPING_RULES_FILE`
2. `CONCILIUM__CPU_MAPPING_RULES_FILE` (legado, apenas transicao)
3. default interno em `config/referencias/cpu_mapping_rules.json`

### API/UI desacopladas

- Bind da API:
	- `CONCILIUM__API_HOST`
	- `CONCILIUM__API_PORT`
- URL canonica da API:
	- `CONCILIUM__API_BASE_URL`
- Bind da UI:
	- `CONCILIUM__UI_HOST`
	- `CONCILIUM__UI_PORT`
- URL da API consumida pela UI:
	- `CONCILIUM__UI_API_BASE_URL`

Precedencia da URL da API na UI:

1. `CONCILIUM__UI_API_BASE_URL`
2. `CONCILIUM__API_BASE_URL`
3. `http://{CONCILIUM__API_HOST}:{CONCILIUM__API_PORT}`

Arquivos de referencia para deploy desacoplado:

- `.env.api.example`
- `.env.ui.example`

Arquivos usados pelo `cd/development/docker-compose.yml`:

- `.env.api`
- `.env.ui`

Profiles de deploy:

- API: `docker compose -f cd/development/docker-compose.yml --profile api up --build`
- UI: `docker compose -f cd/development/docker-compose.yml --profile ui up --build`
- Stack completo: `docker compose -f cd/development/docker-compose.yml --profile deploy up --build`

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

