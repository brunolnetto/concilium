# NEP-013: "Saídas do Planejamento" deve preceder botão "Iniciar Pipeline"

**Status:** Concluído  
**Prioridade:** 🔴 Crítico  
**Área:** Projetos  
**Tipo:** UX  
**Esforço:** XS  
**Identificado em:** 2026-05-20  

---

## Contexto

No Painel de Controle → Planejamento, o botão "Iniciar Pipeline" aparece **antes** do expander "📦 Saídas do Planejamento". Isso cria um fluxo ilógico: o usuário configura o que quer gerar *depois* de já ter iniciado a execução.

O fluxo correto é:
1. Configurar o que será gerado (Saídas)
2. Então iniciar a execução (Pipeline)

## Comportamento Atual

```
[Custos Diretos]
[Custos Indiretos]
[BDI e Regime]
──────────────────
[Iniciar Pipeline]  ← botão de ação
[Saídas do Planejamento]  ← configuração que deveria vir antes
```

## Comportamento Esperado

```
[Custos Diretos]
[Custos Indiretos]
[BDI e Regime]
[Saídas do Planejamento]  ← configuração primeiro
──────────────────
[Iniciar Pipeline]  ← ação por último
```

## Critério de Aceite

- "📦 Saídas do Planejamento" renderiza imediatamente antes do botão/bloco de execução
- O botão "Iniciar Pipeline" é o último elemento visível da seção de planejamento

## Notas Técnicas

Em `project_page.py`, trocar a ordem de chamada entre `render_deliverables_config` e `render_run`. Fix de 2–4 linhas.
