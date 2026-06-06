# Governança de Commits — Concilium

Este documento estabelece as regras e práticas para commits neste repositório, garantindo qualidade, rastreabilidade e integração contínua eficiente.

## Índice

1. [Princípios](#princípios)
2. [Limites Técnicos](#limites-técnicos)
3. [Estrutura de Mensagem](#estrutura-de-mensagem)
4. [Tipos de Commit](#tipos-de-commit)
5. [Validações Automáticas](#validações-automáticas)
6. [Fluxo de Trabalho](#fluxo-de-trabalho)
7. [Exceções e Overrides](#exceções-e-overrides)

---

## Princípios

### 1. Atomicidade
Cada commit deve representar **uma única mudança lógica** que pode ser:
- Revertida independentemente
- Revisada de forma isolada
- Testada individualmente

### 2. Rastreabilidade
Todo commit deve ter mensagem clara que explica:
- **O quê** mudou (resumo)
- **Por quê** mudou (contexto/motivação)
- **Como** afeta o sistema (impacto)

### 3. Integração Contínua
Commits devem:
- Passar em todos os testes automatizados
- Manter o projeto em estado "sempre deployável"
- Não quebrar funcionalidades existentes

---

## Limites Técnicos

Para manter commits gerenciáveis e revisáveis:

| Métrica | Limite Recomendado | Limite Máximo | Ação se Exceder |
|---------|-------------------|---------------|-----------------|
| **Arquivos modificados** | ≤ 15 arquivos | 30 arquivos | Dividir em commits temáticos |
| **Linhas adicionadas** | ≤ 500 linhas | 1.000 linhas | Dividir por módulo/feature |
| **Linhas removidas** | ≤ 300 linhas | Sem limite* | Documentar refatoração |
| **Tamanho total do diff** | ≤ 50 KB | 100 KB | Dividir por escopo |

\* Remoções grandes são permitidas (ex: deletar módulo obsoleto), mas exigem justificativa.

### Exceções Permitidas

Commits que podem exceder limites **com justificativa obrigatória**:

- 🔄 **Refatorações estruturais** (ex: renomear módulos, mover arquivos)
- 📦 **Atualizações de dependências** (lock files, requirements)
- 📊 **Dados de benchmark ou fixtures** (arquivos JSON/CSV grandes)
- 🧪 **Snapshots de teste** (outputs esperados)
- 📚 **Documentação massiva** (ex: migração de docs, ADRs)
- 🎨 **Assets binários** (imagens, fontes) — preferir Git LFS

**Formato de justificativa:**
```
tipo(escopo): mensagem breve

[EXCEÇÃO: motivo]
- Refatoração estrutural de módulo X
- Impacta Y arquivos, mas mudança atômica
- Alternativa seria N commits interdependentes
```

---

## Estrutura de Mensagem

### Formato Obrigatório

```
<tipo>(<escopo>): <resumo em português, ≤72 caracteres>

[corpo opcional: contexto, motivação, impacto]

[footer opcional: refs, breaking changes, co-autores]
```

### Exemplos

#### Commit Simples
```
fix(catalog): corrigir cálculo de BDI em CPU tipo 3

O multiplicador estava usando valor fixo 1.3 ao invés de
ler do perfil de contexto. Agora lê corretamente de
config/perfis/{contexto}.json no campo bdi.tipo_3.

Refs: #234
```

#### Commit com Breaking Change
```
feat(api): adicionar versionamento de endpoints v2

BREAKING CHANGE: endpoints /project/* movidos para /v1/project/*

Adiciona versionamento explícito na API para permitir
evolução sem quebrar clientes antigos. V1 mantida por
compatibilidade até 2026-12-31.

Refs: ADR-089
```

#### Commit de Refatoração Grande
```
refactor(skills): reorganizar manifests por domínio funcional

[EXCEÇÃO: refatoração estrutural]
- Move 15 skills para estrutura skill/<dominio>/<nome>/
- Preserva compatibilidade via aliases em __init__.py
- Mudança atômica para evitar estado inconsistente

Impacta 43 arquivos mas sem mudança de comportamento.
Testes de regressão passam 100%.

Refs: NEP-042
```

---

## Tipos de Commit

Baseado em [Conventional Commits](https://www.conventionalcommits.org/):

| Tipo | Descrição | Exemplos |
|------|-----------|----------|
| `feat` | Nova funcionalidade | Adicionar skill, endpoint, comando CLI |
| `fix` | Correção de bug | Corrigir cálculo, validação, crash |
| `refactor` | Mudança de código sem alterar comportamento | Extrair função, renomear, reorganizar |
| `perf` | Melhoria de performance | Otimizar query, cachear resultado |
| `test` | Adicionar ou corrigir testes | Novo teste unitário, fixture |
| `docs` | Documentação | README, ADR, docstrings, comentários |
| `style` | Formatação (não afeta lógica) | Ruff auto-fix, ajuste de espaços |
| `build` | Build system, dependências | Atualizar pyproject.toml, Dockerfile |
| `ci` | CI/CD, automação | GitHub Actions, pre-commit |
| `chore` | Tarefas de manutenção | Atualizar .gitignore, limpar arquivos |
| `revert` | Reverter commit anterior | `revert: feat(api): ...` |

### Escopos Comuns

- `api`, `cli`, `ui`, `mcp` — superfícies de interação
- `skills`, `catalog`, `runtime` — core do sistema
- `storage`, `config`, `validation` — infraestrutura
- `benchmark`, `audit`, `migration` — utilitários
- `docs`, `tests`, `ci` — suporte

---

## Validações Automáticas

### Pre-commit Hooks (Executam Antes do Commit)

1. **Formatação Automática** (Ruff)
   - Corrige estilo automaticamente
   - Falha se houver violações não auto-fixáveis

2. **Validação de Tamanho** (Custom Hook)
   - Alerta se > 15 arquivos
   - Bloqueia se > 30 arquivos (sem justificativa)
   - Bloqueia se diff > 100 KB

3. **Validação de Mensagem** (Custom Hook)
   - Verifica formato `tipo(escopo): mensagem`
   - Valida tamanho da linha de resumo (≤72 chars)
   - Exige corpo se commit > 10 arquivos

4. **Verificação de Secrets** (detect-secrets)
   - Bloqueia commits com chaves API, tokens, senhas

### Testes Contínuos (CI/CD)

Executam em pull requests e merges:
- ✅ Testes unitários (pytest)
- ✅ Checagem de tipos (mypy)
- ✅ Lint (ruff check)
- ✅ Cobertura mínima (80%)

---

## Fluxo de Trabalho

### 1. Preparação

```bash
# Ver arquivos modificados
git status

# Se > 15 arquivos, planejar divisão
git status --short | wc -l
```

### 2. Stage Seletivo

```bash
# Adicionar por tema
git add src/concilium/application/skills/manifests/04-cronograma/
git commit -m "feat(skills): adicionar validação de feriados em cronograma"

# Adicionar testes relacionados
git add tests/unit/skills/test_04_cronograma.py
git commit -m "test(skills): cobertura de validação de feriados"

# Adicionar documentação
git add docs/engineering/3-technical_notes/cronograma-feriados.md
git commit -m "docs(skills): documentar lógica de feriados em cronograma"
```

### 3. Validação Pré-commit

```bash
# Rodar hooks manualmente (recomendado)
pre-commit run --all-files

# Verificar tamanho do commit
python scripts/dev/validate_commit_size.py
```

### 4. Commit

```bash
# Commit com mensagem descritiva
git commit -m "tipo(escopo): resumo" -m "
Corpo com contexto adicional:
- Detalhe 1
- Detalhe 2

Refs: #123
"
```

### 5. Revisão Antes do Push

```bash
# Ver últimos commits
git log --oneline -5

# Ver diff completo do que será enviado
git diff origin/main..HEAD --stat

# Se houver commit muito grande, considerar squash ou split
git rebase -i origin/main
```

---

## Exceções e Overrides

### Bypass de Validações (Uso Restrito)

```bash
# Pular pre-commit hooks (NÃO RECOMENDADO)
git commit --no-verify -m "..."

# Justificativa obrigatória:
# - Emergência de produção (hotfix crítico)
# - Commit de merge automático
# - Conflito conhecido temporário
```

### Commits de Merge/Rebase

```bash
# Merge commits são isentos de limites
git merge feature-branch
# Mensagem automática é aceitável

# Squash em PRs é encorajado
git merge --squash feature-branch
git commit -m "feat(escopo): resumo de toda a feature"
```

### Commits de Dados de Benchmark

Benchmarks podem ser grandes, mas devem:
- Ir em commits isolados
- Ter mensagem explicando origem dos dados
- Referenciar issue/ADR que justifica inclusão

```bash
git add benchmarks/data/NOVO_PROJETO/
git commit -m "chore(benchmark): adicionar baseline NOVO_PROJETO

[EXCEÇÃO: dados de benchmark]
- Dataset de validação para ADR-XYZ
- 23 arquivos JSON (12 MB) com traces de execução
- Necessário para testes de regressão

Refs: ADR-XYZ, #456
"
```

---

## Ferramentas de Apoio

### Scripts Disponíveis

- `scripts/dev/validate_commit_size.py` — Validar tamanho antes de commitar
- `scripts/dev/audit_commit_history.py` — Analisar histórico (commits grandes)
- `scripts/dev/split_commit_interactive.py` — Assistente para dividir commits

### Comandos Úteis

```bash
# Ver commits ordenados por tamanho
git log --stat --oneline | sort -k2 -nr | head -20

# Ver commits por autor (para auditoria)
git shortlog -sn --since="2026-01-01"

# Ver arquivos mais modificados (hotspots)
git log --format=format: --name-only | sort | uniq -c | sort -nr | head -20
```

---

## Responsabilidades

### Desenvolvedores
- ✅ Seguir limites técnicos
- ✅ Escrever mensagens claras
- ✅ Dividir commits grandes
- ✅ Rodar pre-commit antes de push

### Revisores (Code Review)
- ✅ Verificar atomicidade
- ✅ Exigir justificativa para exceções
- ✅ Validar que testes cobrem mudanças
- ✅ Rejeitar commits "carona" (mudanças não relacionadas)

### Mantenedores
- ✅ Auditar histórico periodicamente
- ✅ Atualizar governança conforme projeto evolui
- ✅ Treinar time em boas práticas
- ✅ Documentar casos excepcionais

---

## Revisões Periódicas

Este documento deve ser revisado:
- 📅 Trimestralmente (ou quando houver padrão recorrente de violações)
- 🔄 Após retrospectivas de sprint
- 📊 Com base em métricas de CI/CD (tempo de build, falhas)

**Última revisão:** 2026-06-05  
**Próxima revisão:** 2026-09-05  
**Responsável:** Gerente de Engenharia
