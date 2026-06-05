# /commit

Gera e executa um commit convencional a partir do diff atual.

## Processo

1. Leia `git diff --staged`. Se vazio, leia `git diff HEAD` e pergunte se quer stagear tudo.

2. Inspecione os últimos 10 commits (`git log --oneline -10`) para confirmar a convenção em uso no projeto.

3. **Determine o tipo** a partir da natureza das mudanças:
   - `feat` — nova capacidade observável pelo usuário ou agente
   - `fix` — corrige comportamento incorreto
   - `refactor` — reestrutura sem mudar comportamento externo
   - `test` — adiciona ou corrige testes
   - `docs` — documentação, ADRs, NEPs
   - `chore` — infra, deps, CI/CD, config
   - `data` — atualiza dados de referência (catálogos, benchmarks, fixtures)
   - `perf` — melhora de performance

4. **Infira o escopo** a partir dos caminhos dos arquivos alterados, usando a camada DDD mais específica:
   - `domain/<módulo>` → escopo é o módulo (ex: `scheduling`, `catalog`)
   - `application/<feature>` → escopo é a feature
   - `infrastructure/<adapter>` → escopo é o adapter (ex: `azure`, `storage`)
   - `presentation/<entry>` → entry point (ex: `api`, `mcp`, `cli`, `ui`)
   - `tests/` → escopo do que está sendo testado
   - `.github/`, `cd/`, `Dockerfile` → `ci` ou `cd`
   - `docs/`, `adrs/` → `adr` + número se aplicável (ex: `adr099`)
   - Múltiplas camadas → use a camada de maior impacto ou omita o escopo

5. **Escreva o subject** em inglês ou português conforme o histórico do projeto:
   - Modo imperativo, minúsculas, sem ponto final
   - Máximo 72 caracteres incluindo `type(scope): `
   - Descreve O QUÊ muda, não o porquê (o porquê vai no body se necessário)

6. Adicione **breaking change** no footer se a interface pública mudou: `BREAKING CHANGE: <descrição>`.

7. Mostre a mensagem gerada e peça confirmação antes de executar o commit.

8. Execute: `git commit -m "<mensagem>"` (nunca use `--no-verify`).

## Formato esperado

```
type(scope): subject imperativo em ≤72 chars

Body opcional explicando o porquê, contexto ou trade-offs.
Múltiplos parágrafos permitidos.

BREAKING CHANGE: descrição se aplicável
```
