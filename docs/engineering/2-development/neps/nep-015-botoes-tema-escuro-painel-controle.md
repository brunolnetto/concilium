# NEP-015: Botões do Painel de Controle não respeitam tema claro/escuro

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Projetos  
**Tipo:** Estilo  
**Esforço:** M  
**Identificado em:** 2026-05-20  

---

## Contexto

Os botões dentro do "🛠️ Painel de Controle → 📊 Planejamento" aparecem com estilo fixo "modo escuro" independentemente do tema ativo. O tema claro (light mode) funciona corretamente no sidebar e nas páginas de Configuração/Catálogo, mas os componentes dentro de `st.expander` no Painel de Controle escapam do cascade CSS.

## Escopo Afetado

Componentes que precisam de auditoria:
- `atoms/elements.py` — `render_primary_button`, `render_metric`, etc.
- `molecules/components.py` — `render_download_button`, `render_mapping_table`, etc.
- `molecules/common.py` — `render_paginated_table`, `render_page_nav`
- `organisms/layout.py` — todos os `st.button` dentro de expanders

## Causa Raiz (hipótese)

O CSS do tema é injetado via `st.markdown` no topo da página. Componentes dentro de `st.expander` herdam o tema, mas o seletor CSS:
```css
.stButton > button[kind="primary"] {
    background: var(--ml-navy) !important;
}
```
...pode estar sendo sobrescrito por estilos do Streamlit para componentes dentro de containers aninhados, especialmente na área principal vs. sidebar.

## Critério de Aceite

1. Auditoria completa: mapear TODOS os `st.button(...)` sem `type=` explícito em atoms/molecules/organisms
2. Garantir que `type="primary"` e `type="secondary"` estão corretos em todos os casos (ver padrão: NEP associada ao plano de botões)
3. Em light mode, botões `primary` aparecem com fundo navy preenchido e texto branco
4. Em dark mode, botões `primary` aparecem com fundo `--ml-navy-lt` + borda laranja (padrão sidebar)
5. Nenhum componente mostra estilo "dark" quando o tema ativo é "light"

## Abordagem

1. Varredura de `grep -rn 'st.button\|st.form_submit' organisms/ atoms/ molecules/` sem `type=`
2. Para cada ocorrência: classificar em primary/secondary conforme padrão estabelecido
3. Revisar CSS em `theme.py`: garantir que seletores cubram componentes dentro de `st.expander > div`
4. Adicionar seletor específico para `[data-testid="stExpander"] .stButton > button[kind="primary"]`

## Notas Técnicas

O padrão de botões já está documentado no plano geral (botões primary = salvar/criar/executar, secondary = filtrar/navegar/cancelar). Esta NEP trata especificamente da *consistência visual* em todos os contextos de renderização.
