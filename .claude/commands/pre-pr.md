# /pre-pr

Gate de compliance antes de abrir um Pull Request. Descobre as ferramentas configuradas no projeto e executa cada verificação, reportando status por categoria.

## Processo

### 1. Descoberta do projeto

Leia `pyproject.toml` e `Makefile` (se existirem) para identificar:
- Comando de testes (`pytest`, `make test`, etc.)
- Linter configurado (`ruff`, `flake8`, etc.)
- Type checker (`mypy`, `pyright`, etc.)
- Import-linter (`[tool.importlinter]` em pyproject.toml)
- Cobertura mínima, se definida

### 2. Verificações — execute em sequência, reporte cada uma

**Testes**
```
make test   (ou o comando descoberto)
```
- ✅ Todos passando
- ❌ N falhas — liste os nomes dos testes falhos

**Lint**
```
make lint   (ou ruff check src/ tests/)
```
- ✅ Sem violações
- ⚠️ N violações auto-corrigíveis (`make fmt`)
- ❌ N violações manuais

**Tipos**
```
make type-check   (ou ty check src/)
```
- ✅ Sem erros
- ❌ Erros — liste arquivo:linha:mensagem

**Arquitetura — camadas DDD**
Se `.importlinter` existir:
```
lint-imports
```
Se não existir, inspecione o diff e verifique se algum módulo de camada inferior importa de camada superior (ex: `domain` importando `application`). Reporte violações encontradas.

**Diff não commitado**
```
git status --short
```
- ✅ Working tree limpo
- ⚠️ Arquivos modificados não commitados — liste-os

**Branch**
```
git log main..HEAD --oneline
```
- Mostre quantos commits estão à frente de main
- ⚠️ Se 0 commits, branch não tem mudanças

### 3. Relatório final

```
┌─────────────────────────────────────┐
│  Pre-PR Gate                        │
├─────────────────┬───────────────────┤
│  Testes         │  ✅ 2128 passed   │
│  Lint           │  ✅ clean         │
│  Tipos          │  ✅ no errors     │
│  Arquitetura    │  ✅ contracts ok  │
│  Working tree   │  ✅ clean         │
│  Branch         │  3 commits ahead  │
└─────────────────┴───────────────────┘
  APROVADO — pronto para PR
```

Se qualquer item for ❌: **BLOQUEADO — corrija antes de abrir PR**. Liste as ações necessárias.

### 4. Sugestão de PR

Se aprovado, pergunte se quer gerar o título e body do PR baseado nos commits da branch.
