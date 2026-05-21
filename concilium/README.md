# Concilium

Framework deterministico para planejamento e orcamento de obras, com pipeline de skills, versionamento de projeto e interfaces via CLI, MCP, API e UI.

## Stack

- Python 3.11+
- Typer + Rich (CLI)
- Pydantic v2 (modelos)
- FastMCP (servidor MCP)
- Pytest (unit/integration)

## Arquitetura atual

- `src/concilium/main.py`: CLI principal (`concilium`)
- `src/concilium/runtime.py`: orquestracao do pipeline e execucao de skills
- `src/concilium/storage/`: persistencia de projetos, versoes e logs de invocacao
- `src/concilium/skills/manifests/`: skills auto-descobertas por manifesto `skill.toml`
- `src/concilium/mcp_server/`: interface MCP para operacoes de negocio
- `config/`: jurisdicoes, perfis, catalogos, referencias e contextos
- `tests/unit` e `tests/integration`: suite de validacao

Visao curta do funcionamento: `docs/architecture.md`.

## Skills atualmente presentes

As skills sao carregadas automaticamente a partir de `src/concilium/skills/manifests`:

- `00-escopo`
- `00A-atividades`
- `00B-sequenciamento`
- `02-produtividade-climatica`
- `03-catalogo-de-recursos`
- `04-cronograma`
- `03-equipes-diretas`
- `03A-derivar-requisitos`
- `03B-alocacao-recursos`
- `03C-validar-compartilhamento`
- `06-precificacao-unitaria`
- `07-custos-indiretos`
- `06-consolidar`
- `09-relatorio-e-artefatos`
- `08-criticality`
- `09-cost-criticality`
- `11-avaliacao-intervencoes`
- `12-registro-decisoes`
- `12-decision-review`

## Configuracao de ambiente

Variaveis padronizadas:

- `CONCILIUM_CONFIG_ROOT`: diretorio de configuracoes (padrao: `./config`)
- `CONCILIUM_PROJECTS_ROOT`: diretorio de projetos (padrao: `./projetos`)

Compatibilidade retroativa (legado):

- `CONCILIUM_CONFIG` (equivalente a `CONCILIUM_CONFIG_ROOT`)
- `CONCILIUM_PROJETOS` (equivalente a `CONCILIUM_PROJECTS_ROOT`)

Na inicializacao, a CLI valida se o diretorio de configuracao existe e mostra mensagem amigavel em caso de erro.

## Instalacao

### Ambiente de desenvolvimento

```bash
pip install -e ".[dev]"
pre-commit install
```

### Instalacao limpa (simulacao de maquina nova)

```bash
python -m venv .venv-clean
. .venv-clean/bin/activate  # Windows PowerShell: .venv-clean\Scripts\Activate.ps1
pip install --upgrade pip
pip install .
concilium --help
```

## Comandos CLI principais

```bash
concilium init <nome> --contexto <id>
concilium snapshot create <projeto>
concilium version new <projeto>
concilium run <skill> --project <projeto> [--version vN] [--inputs '{"...": "..."}']
concilium status <projeto>
concilium validate <projeto@vN>
concilium approve <projeto@vN> --as <papel>
concilium decision log <projeto@vN> --as <papel> --titulo ... --decisao ...
concilium decision review <projeto@vN>
concilium adapter run <projeto@vN>
concilium scenario run --project <projeto>
concilium scenario compare --project <projeto>
```

## Qualidade

### Lint e formatacao

```bash
ruff check .
ruff format .
```

### Testes

```bash
pytest tests/unit
pytest tests/integration
```

