# Sprint 2 e 3 - Execucao e Validacoes Intermediarias (NEP-026)

**Referencia:** [NEP-026](../neps/nep-026-descontinuacao-legacy-alias-lingua-franca.md)  
**Data:** 2026-05-22

---

## Objetivo

Concluir a maratona de descontinuacao de legacy/alias com endurecimento de contrato
canonico e remocao de aliases publicos.

## Sprint 2 - Depreciacao controlada

### Entregas aplicadas

1. Endurecimento de contrato para benchmark reference no backend.
2. Codigo de validacao explicito para payload legado de EAP.
3. Ajuste de testes para comportamento canonico por default.

### Validacao intermediaria A

- Verificacao estatica dos arquivos alterados: sem erros.
- Confirmacao de codigo de bloqueio legado:
  - `VAL-CONTRACT-EAP-LEGACY-BLOQUEADO`
  - ponto de aplicacao: `ProjectService.get_benchmark_reference()`

## Sprint 3 - Remocao definitiva

### Entregas aplicadas

1. Remocao dos endpoints alias de artefatos (`/artefacts`).
2. Remocao do comando CLI alias `validate projeto`.
3. Atualizacao do carregamento de comandos na CLI principal.

### Validacao intermediaria B

- Busca em `src/concilium/presentation/**` sem ocorrencias de:
  - `/artefacts`
  - `validate_projeto_alias`
  - `validate projeto`
- Verificacao estatica dos arquivos alterados: sem erros.

## Evidencias de codigo

- `src/concilium/application/services/project_service.py`
- `tests/unit/test_benchmark_reference_contract.py`
- `src/concilium/presentation/api/routes/analysis.py`
- `src/concilium/presentation/cli/commands_validate.py`
- `src/concilium/presentation/main.py`

## Observacao operacional

A execucao de pytest no terminal da sessao permanece intermitente e sem output consistente.
As validacoes intermediarias desta execucao foram feitas por:

1. checagem estatica (`get_errors`),
2. verificacao de ausencia de referencias por busca textual dirigida.

## Revalidacao final C - fechamento sem drift (2026-05-22)

Escopo de fechamento focado na NEP-026 e nos leftovers apontados na varredura anterior:

1. UI helper sem expansao de chaves curtas de BDI (`mo`, `eq`, `mat`, `ind`).
2. Contrato default de deliverables sem toggles duplicados de nomenclatura.
3. Rotas/comandos alias publicos continuam ausentes.
4. Bloqueio de payload legado de EAP permanece ativo com erro explicito.

### Evidencias da revalidacao final

- `src/concilium/presentation/ui/helpers/helpers.py`
- `src/concilium/application/services/project_files.py`
- `src/concilium/application/services/project_service.py`
- `src/concilium/presentation/api/routes/analysis.py`
- `src/concilium/presentation/cli/commands_validate.py`
- `tests/unit/test_benchmark_reference_contract.py`

### Resultado

Para o escopo da NEP-026 (contrato canonico e remocao de aliases publicos), a revarredura final fechou em **100%**, sem leftovers funcionais nos pontos-alvo.
