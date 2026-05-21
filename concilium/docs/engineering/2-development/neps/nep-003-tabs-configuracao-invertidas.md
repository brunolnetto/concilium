# NEP-003: Tabs da página Configuração exibem conteúdo trocado

**Status:** Concluído  
**Prioridade:** 🔴 Crítico  
**Área:** Configuração  
**Tipo:** Bug  
**Esforço:** XS  
**Identificado em:** 2026-05-20  

---

## Contexto

A página de Configuração (`render_configuracao_page`) exibe quatro tabs mas o mapeamento entre o label da tab e a função renderizada está completamente invertido:

| Tab exibida | Função chamada | Deveria chamar |
|---|---|---|
| ⚖️ Jurisdições | `_render_entity_section(/api/perfis)` | `_render_jurisdicoes_section` |
| 📋 Perfis | `_render_entity_section(/api/contextos)` | `_render_entity_section(/api/perfis)` |
| 🌐 Contextos | `_render_temas_section` | `_render_entity_section(/api/contextos)` |
| 🎨 Temas | `_render_jurisdicoes_section` | `_render_temas_section` |

O usuário vê "Perfis" quando clica em "Jurisdições", "Contextos" quando clica em "Perfis", etc. Confusão total de identidade de conteúdo.

## Causa Raiz

Em `perfis_contextos_page.py`, a função `render_configuracao_page` cria as tabs na ordem `["📋 Perfis", "🌐 Contextos", "🎨 Temas", "⚖️ Jurisdições"]` mas os blocos `with tabs[N]:` foram escritos numa ordem diferente ao longo de edições successivas.

## Critério de Aceite

- Clicar em "📋 Perfis" → exibe perfis financeiros
- Clicar em "🌐 Contextos" → exibe contextos de obra
- Clicar em "🎨 Temas" → exibe temas visuais
- Clicar em "⚖️ Jurisdições" → exibe overlays de jurisdição

## Notas Técnicas

Fix de 4 linhas — reordenar os blocos `with tabs[0]:`, `with tabs[1]:`, `with tabs[2]:`, `with tabs[3]:` para corresponderem à ordem dos labels definidos em `st.tabs(...)`.
