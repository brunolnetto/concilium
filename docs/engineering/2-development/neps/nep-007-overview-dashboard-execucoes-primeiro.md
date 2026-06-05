# NEP-007: Overview deve exibir dashboard de execuções antes do resumo do projeto

**Status:** Concluído  
**Prioridade:** 🟡 Médio  
**Área:** Projetos  
**Tipo:** UX  
**Esforço:** S  
**Identificado em:** 2026-05-20  

---

## Contexto

A aba "📊 Overview" de um projeto `hot_project` exibe:
1. `render_overview_tab()` — KPIs financeiros e "ℹ️ Resumo do Projeto"
2. Diagnóstico PE (se houver déficit)
3. `_render_project_config_tab()` — EAP e contexto

O engenheiro que abre um projeto normalmente quer ver **o que aconteceu** (histórico de runs, última execução, status de pipeline) antes de ver o resumo descritivo do projeto. O dashboard de execuções está enterrado no Painel de Controle.

## Visão de Produto

O Overview deve ser organizado em sub-tabs:
```
📊 Overview
├── 📈 Execuções    ← PRIMEIRO: histórico de runs, última execução, diagnóstico PE
└── 🔍 Projeto      ← DEPOIS: KPIs, EAP, contexto, configuração
```

**Aba 📈 Execuções:** mostra `render_history` compacto + pipeline monitor + diagnóstico PE + backtracking
**Aba 🔍 Projeto:** atual `render_overview_tab` + `_render_project_config_tab`

## Critério de Aceite

1. Ao abrir um projeto, a primeira coisa visível no Overview é o histórico de runs
2. A aba "📈 Execuções" mostra: últimas 10 execuções (status, versão, duração), diagnóstico PE ativo
3. A aba "🔍 Projeto" mostra: KPIs financeiros, resumo de escopo, EAP, contexto

## Notas Técnicas

- Adicionar `sub_exec, sub_proj = st.tabs(["📈 Execuções", "🔍 Projeto"])` no início de `tab_overview`
- `render_history` já existe — incluir em `sub_exec`
- Mover diagnosticos PE para `sub_exec`
- Mover `render_overview_tab` e `_render_project_config_tab` para `sub_proj`
