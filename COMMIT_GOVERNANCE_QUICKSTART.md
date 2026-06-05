# Guia Rápido — Governança de Commits

Este guia fornece comandos práticos para usar as ferramentas de governança de commits no dia a dia.

## 🚀 Configuração Inicial (Uma Vez)

### 1. Instalar Pre-commit Hooks

```bash
# Instalar pre-commit (se ainda não tiver)
pip install pre-commit

# Instalar hooks no repositório
pre-commit install
pre-commit install --hook-type commit-msg
```

### 2. Configurar Template de Commit

```bash
# Configurar git para usar o template
git config commit.template .git-commit-template

# Agora ao executar `git commit` sem -m, o template será aberto no editor
```

### 3. Verificar Instalação

```bash
# Testar hooks manualmente
pre-commit run --all-files

# Ver configuração do git
git config --list | grep commit
```

---

## 📝 Fluxo de Trabalho Diário

### Antes de Commitar

```bash
# 1. Ver arquivos modificados
git status

# 2. Se houver muitos arquivos (>15), planejar divisão por tema
git status --short | wc -l

# 3. Validar tamanho antes de adicionar
python scripts/dev/validate_commit_size.py
```

### Commitando por Etapas

```bash
# Cenário: 25 arquivos modificados (muitos para 1 commit)

# 1. Adicionar por tema/módulo
git add src/concilium/application/skills/manifests/04-cronograma/
git commit -m "feat(skills): adicionar validação de feriados em cronograma"

# 2. Adicionar testes relacionados
git add tests/unit/skills/test_04_cronograma.py
git commit -m "test(skills): cobertura de validação de feriados"

# 3. Adicionar documentação
git add docs/engineering/3-technical_notes/cronograma-feriados.md
git commit -m "docs(skills): documentar lógica de feriados"
```

### Stage Interativo (Recomendado)

```bash
# Adicionar arquivos interativamente (escolhe o que entra no commit)
git add -i

# Ou adicionar partes de arquivos (patch mode)
git add -p src/concilium/application/skills/manifests/04-cronograma/skill.py

# Revisar o que foi staged
git diff --cached
```

### Commit com Mensagem Descritiva

```bash
# Commit simples
git commit -m "feat(api): adicionar endpoint de validação de CPU"

# Commit com corpo (recomendado para mudanças não triviais)
git commit -m "feat(catalog): adicionar validação de CPU duplicados" -m "
Implementa validação que detecta entradas duplicadas no
catálogo CPU durante o carregamento. Previne inconsistências
em precificação quando há códigos repetidos.

Refs: #234
"

# Commit com editor (usa template)
git commit
```

---

## 🔍 Auditoria e Análise

### Auditar Commits Recentes

```bash
# Analisar últimos 100 commits (padrão)
python scripts/dev/audit_commit_history.py

# Analisar últimos 50 commits
python scripts/dev/audit_commit_history.py -n 50

# Analisar commits desde janeiro
python scripts/dev/audit_commit_history.py --since 2026-01-01

# Analisar branch específica
python scripts/dev/audit_commit_history.py --range main..feature-branch

# Modo detalhado
python scripts/dev/audit_commit_history.py --detailed -v

# Gerar relatório JSON para análise
python scripts/dev/audit_commit_history.py --output audit.json
```

### Ver Histórico Local

```bash
# Ver últimos commits com estatísticas
git log --oneline --stat -10

# Ver commits por autor
git shortlog -sn --since="2026-01-01"

# Ver arquivos mais modificados (hotspots)
git log --format=format: --name-only | sort | uniq -c | sort -nr | head -20

# Ver tamanho de commits
git log --oneline --numstat | head -50
```

---

## 🛠️ Ferramentas de Correção

### Dividir Commit Staged Muito Grande

```bash
# Remover tudo do stage
git reset HEAD

# Adicionar novamente por partes
git add src/modulo1/
git commit -m "tipo(escopo): mudança 1"

git add src/modulo2/
git commit -m "tipo(escopo): mudança 2"
```

### Corrigir Mensagem do Último Commit

```bash
# Alterar mensagem do último commit
git commit --amend

# Alterar mensagem sem abrir editor
git commit --amend -m "nova mensagem corrigida"
```

### Dividir Último Commit em Vários

```bash
# Desfazer último commit mas manter mudanças staged
git reset --soft HEAD~1

# Ou desfazer e remover do stage (mais comum)
git reset HEAD~1

# Agora commitar em partes
git add arquivo1.py
git commit -m "tipo(escopo): mudança 1"

git add arquivo2.py
git commit -m "tipo(escopo): mudança 2"
```

### Squash de Múltiplos Commits

```bash
# Combinar últimos 3 commits em 1
git rebase -i HEAD~3

# No editor:
# - Deixar 'pick' no primeiro commit
# - Trocar 'pick' por 'squash' (ou 's') nos outros
# - Salvar e sair
# - Editar mensagem combinada na próxima tela
```

---

## 🚨 Troubleshooting

### Pre-commit Está Bloqueando Commit

```bash
# Ver qual hook está falhando
pre-commit run --all-files

# Rodar hook específico
pre-commit run validate-commit-size

# Ver detalhes do erro
pre-commit run --verbose
```

### Bypass de Hooks (Uso Excepcional)

```bash
# ⚠️ NÃO RECOMENDADO - Usar apenas em emergências
git commit --no-verify -m "hotfix crítico"

# Preferir: corrigir o problema e commitar normalmente
```

### Validação Manual Sem Commit

```bash
# Testar validação de tamanho
python scripts/dev/validate_commit_size.py

# Testar validação de mensagem (criar arquivo teste)
echo "feat(api): teste" > /tmp/test-msg.txt
python scripts/dev/validate_commit_msg.py /tmp/test-msg.txt
```

### Pre-commit Hooks Não Estão Rodando

```bash
# Reinstalar hooks
pre-commit uninstall
pre-commit install
pre-commit install --hook-type commit-msg

# Verificar se hooks foram instalados
ls -la .git/hooks/

# Testar manualmente
pre-commit run --all-files
```

---

## 📊 Exemplos Práticos

### Exemplo 1: Feature Nova

```bash
# Implementação
git add src/concilium/application/skills/manifests/16-nova-skill/
git commit -m "feat(skills): adicionar skill 16 para análise de risco"

# Testes
git add tests/unit/skills/test_16_analise_risco.py
git commit -m "test(skills): cobertura para skill 16"

# Documentação
git add docs/engineering/skills/16-analise-risco.md
git commit -m "docs(skills): documentar skill 16 análise de risco"
```

### Exemplo 2: Bug Fix

```bash
# Correção
git add src/concilium/infrastructure/catalog/loader.py
git commit -m "fix(catalog): corrigir parsing de CPU com preços zerados" -m "
CPU com preço 0 estava sendo ignorada no carregamento,
causando erro em projetos que usam serviços sem custo.
Agora permite preço zero explicitamente.

Refs: #456
Fixes: #789
"

# Teste de regressão
git add tests/unit/infrastructure/catalog/test_loader_zero_price.py
git commit -m "test(catalog): adicionar caso de teste para CPU preço zero"
```

### Exemplo 3: Refatoração

```bash
# Se mudança é muito grande (>30 arquivos), justificar
git add src/concilium/domain/
git commit -m "refactor(domain): reorganizar modelos por subdomínio" -m "
[EXCEÇÃO: refatoração estrutural]
- Move modelos de domain/ para domain/{projeto,catalogo,executivo}/
- Preserva imports via __init__.py para compatibilidade
- Mudança atômica necessária para evitar estado inconsistente

Impacta 42 arquivos mas sem alteração de comportamento.
Testes de regressão passam 100%.

Refs: ADR-091
"
```

---

## 📚 Referências

- **Documentação Completa**: [COMMIT_GOVERNANCE.md](COMMIT_GOVERNANCE.md)
- **Conventional Commits**: https://www.conventionalcommits.org/
- **Pre-commit Framework**: https://pre-commit.com/

---

## 🎯 Checklist Antes de Push

```bash
# ✅ 1. Todos os commits seguem Conventional Commits?
git log --oneline -10

# ✅ 2. Nenhum commit muito grande?
python scripts/dev/audit_commit_history.py -n 10

# ✅ 3. Pre-commit hooks passando?
pre-commit run --all-files

# ✅ 4. Testes passando?
make test

# ✅ 5. Lint limpo?
make lint

# Se tudo OK, fazer push
git push origin feature-branch
```

---

**Última atualização**: 2026-06-05
