# Onda 1 / #25 — runbook de desbloqueio de CI e branch protection

**Status observado em 2026-10-27:** #25 aberta (quatro de cinco critérios registrados). Repositório **privado**. `main` no SHA `8f7c3f386ad01e7fdec3b02f16b383db3c51a7dd`. Os workflows do PR #120 concluem `startup_failure` antes de executar jobs; isso **não** é aprovação de testes.

## Limites atuais da integração GitHub

- `GET /repos/brunolnetto/concilium/rulesets` retorna 403: **"Upgrade to GitHub Pro or make this repository public to enable this feature."**
- `GET /repos/brunolnetto/concilium/branches/main/protection` retorna 403: **"Resource not accessible by integration"**.
- Não há permissão de escrita de regras administrativas nesta integração. Não é correto afirmar que a proteção foi configurada nem executar um merge enquanto `startup_failure` e o requisito de proteção persistirem.
- **Não tornar o repositório público automaticamente.** Qualquer alteração de visibilidade é decisão independente do proprietário e exige auditoria de segredos, código e propriedade intelectual.

## Ações exclusivas do proprietário

1. Em **Settings → Billing and licensing**, investigar cobrança/limites de GitHub Actions; restabelecer a capacidade de inicializar runners (não apenas repetir workflows). Verificar se o plano habilita a proteção exigida em **repositório privado**. Atualizar plano elegível (ex.: GitHub Pro/Team) apenas com decisão explícita.
2. Em **Settings → Branches** ou **Settings → Rules → Rulesets**, definir proteção sobre `main`. Exigir PR, revisão e status checks em SHA atual; não permitir push direto/bypass administrativo ou force-push. Habilitar atualização de branch com `main` antes do merge.
3. Verificar no workflow [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) os nomes de **jobs existentes** que devem tornar-se status checks obrigatórios:
   - `Economic Contract Evidence (required)`
   - `Formalism Reference (independent)`
   - `Dependency Lock (Docker parity)`
   - `Lint`
   - `Type Check`
   - `Tests`

   O job `MCP Proxy (standalone)` é condicional a mudanças; não exigir indiscriminadamente um job que pode ficar `skipped`. Avaliar a matriz `Formalism Reference Py...` e jobs adicionais conforme política efetiva. Selecionar os status **existentes e publicados** pelo GitHub depois de um workflow real.
4. Criar PR de teste **deliberadamente inválido** em branch isolado, alterando custo/economia sem atualizar especificação/golden obrigatórios, para demonstrar que `Economic Contract Evidence (required)` falha **e a proteção impede merge**. Reverter/descartar a mutação e provar PR válido com todos os checks exigidos verdes. Não confundir o teste unitário do gate com esta prova de branch protection.
5. Registrar na issue #25: screenshots/configuração versionada da proteção, SHA da branch protegida, IDs de workflow, status checks obrigatórios, PR bloqueado do teste negativo, e evidência do CI positivo. Só então avaliar fechamento de #25, sempre com aceite manual.

## Preflight local de DAG de PRs

O PR #120 acrescenta [`formalism_planonly_pr_preflight.py`](../../scripts/formalism_planonly_pr_preflight.py) e testes de falsificação independentes.

```bash
cd ~/github/concilium
git fetch origin
git switch docs/formalism-planonly-pr-topological-registry
git pull --ff-only

uv run pytest -q \
  tests/reference_formalism/test_formalism_execution_dag.py \
  tests/reference_formalism/test_formalism_planonly_pr_registry.py \
  tests/reference_formalism/test_formalism_planonly_pr_preflight.py

uv run ruff check \
  scripts/formalism_planonly_pr_preflight.py \
  tests/reference_formalism/test_formalism_planonly_pr_registry.py \
  tests/reference_formalism/test_formalism_planonly_pr_preflight.py

uv run python scripts/formalism_planonly_pr_preflight.py
GH_TOKEN="$(gh auth token)" uv run python scripts/formalism_planonly_pr_preflight.py --live
```

O relatório `--live` verifica os 12 PRs de planejamento por número/base/head/draft e os bloqueios de **todas** as issues predecessoras. Por segurança, `--require-merge-ready` deve retornar saída **1** enquanto os PRs continuarem `PLAN_ONLY`, mesmo que #25 venha a fechar: os documentos precisam primeiro virar código implementado e comprovado. Falha de credenciais/snapshot parcial retorna **2** (FAIL CLOSED).

## Separação de aceites

A correção de #25 habilita início de ondas seguintes, **não** certifica as issues #14–#26. Cada pacote ainda exige implementação, oráculo independente, revisão de HEAD, CI obrigatório e fechamento individual em ordem topológica. PRs de planejamento #108–#119 e o PR de governança #120 não são provas econômicas ou GO de projeto.
