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
docker compose -f docker-compose.dev.yml up --build
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

- `CONCILIUM_ROOT`
- `CONCILIUM_CONFIG_ROOT`
- `CONCILIUM_PROJECTS_ROOT`
- `CONCILIUM_BENCHMARK_PROJECTS_ROOT`
- `CONCILIUM_STORE_BACKEND` (opções: `local_json`, `sharepoint`, `s3`; default: `filesystem`)

Backends de store:

1. `local_json` (alias: `filesystem`) — store local por diretório/JSON
2. `sharepoint` — via Graph API (`concilium[sharepoint]`)
3. `s3` — via S3 API com `aioboto3` (`concilium[s3]`)

### Runtime config (transicao de YAML para env/file)

Precedencia do arquivo de runtime:

1. `CONCILIUM_RUNTIME_CONFIG_FILE`
2. `CONCILIUM_CONFIG_FILE` (legado)
3. `CONCILIUM_CONFIG_ROOT/concilium.yaml`

Formatos suportados: `.yaml/.yml`, `.json`, `.toml`.

Override granular por env (sem editar arquivo):

- Prefixo: `CONCILIUM_CFG__`
- Exemplo: `CONCILIUM_CFG__progress__spi__ahead_threshold=1.1`

### Mapping de benchmark (EAP -> CPU)

Precedencia:

1. `CONCILIUM_BENCHMARK_CPU_MAPPING_RULES_FILE`
2. `CONCILIUM_CPU_MAPPING_RULES_FILE` (legado, apenas transicao)
3. default interno em `config/referencias/cpu_mapping_rules.json`

### API/UI desacopladas

- Bind da API:
	- `CONCILIUM_API_HOST`
	- `CONCILIUM_API_PORT`
- URL canonica da API:
	- `CONCILIUM_API_BASE_URL`
- Bind da UI:
	- `CONCILIUM_UI_HOST`
	- `CONCILIUM_UI_PORT`
- URL da API consumida pela UI:
	- `CONCILIUM_UI_API_BASE_URL`

Precedencia da URL da API na UI:

1. `CONCILIUM_UI_API_BASE_URL`
2. `CONCILIUM_API_BASE_URL`
3. `http://{CONCILIUM_API_HOST}:{CONCILIUM_API_PORT}`

Arquivos de referencia para deploy desacoplado:

- `.env.api.example`
- `.env.ui.example`

Arquivos usados pelo `docker-compose.dev.yml`:

- `.env.api`
- `.env.ui`

Profiles de deploy:

- API: `docker compose -f docker-compose.dev.yml --profile api up --build`
- UI: `docker compose -f docker-compose.dev.yml --profile ui up --build`
- Stack completo: `docker compose -f docker-compose.dev.yml --profile deploy up --build`

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

## Documentacao tecnica

- Arquitetura e ADRs: `docs/engineering/0-architecture/`
- NEPs e backlog de produto: `docs/engineering/2-development/neps/`
- Notas tecnicas de engenharia: `docs/engineering/3-technical_notes/`

