# NEP-017: Inventário de Skills no README desatualizado

**Status:** Concluído  
**Prioridade:** 🔴 Crítico  
**Área:** Projetos  
**Tipo:** Governança + Documentação  
**Esforço:** S  
**Identificado em:** 2026-05-21  
**Concluído em:** 2026-05-21

---

## Contexto

O README listava IDs legados de skills (ex.: `00-escopo`, `03A-*`, `06-consolidar`) que não refletem mais os manifests ativos.

## Causa Raiz

Ausência de sincronização sistemática entre `README.md` e `src/concilium/application/skills/manifests/*/skill.toml`.

## Implementação

- Atualização da seção de arquitetura para paths reais (`application/runtime.py`, `presentation/main.py`, etc.).
- Atualização da lista de skills para o inventário atual (01 a 15).

## Critério de Aceite

1. README lista exclusivamente skills existentes nos manifests atuais.
2. Paths de arquitetura no README apontam para diretórios vigentes.

## Evidências

- `README.md` atualizado com lista real de skills e paths atuais.
