# NEP-018: Chaves de entregáveis desalinhadas entre defaults, UI e runtime

**Status:** Concluído  
**Prioridade:** 🔴 Crítico  
**Área:** Projetos  
**Tipo:** Bug + Governança  
**Esforço:** M  
**Identificado em:** 2026-05-21  
**Concluído em:** 2026-05-21

---

## Contexto

A configuração de entregáveis tinha divergências entre:

- defaults (`project_files.py`),
- painel UI (toggle de saídas),
- aplicação efetiva no runtime (`09-relatorio-e-artefatos`).

## Causa Raiz

As chaves evoluíram em camadas diferentes sem contrato único estrito.

## Implementação

- Inclusão da chave `aba_curva_abc_composicao` nos defaults.
- Runtime passou a derivar `gerar_excel` e `gerar_modelo_vivo` da `deliverables_config.json` para a skill 09.
- Runtime passou a respeitar explicitamente `modelo_vivo_xlsx` ao salvar `modelo_vivo.xlsx`.

## Critério de Aceite

1. Toggle de `modelo_vivo_xlsx` controla de fato geração/salvamento do arquivo.
2. Chave `aba_curva_abc_composicao` existe no contrato de defaults.
3. Runtime usa defaults coerentes de `resultado_xlsx`/`cronograma_xlsx`.

## Evidências

- `src/concilium/application/services/project_files.py`
- `src/concilium/application/runtime.py`
