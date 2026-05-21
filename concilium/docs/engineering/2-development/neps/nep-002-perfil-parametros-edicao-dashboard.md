# NEP-002: Parâmetros financeiros do perfil não editáveis nem visíveis no dashboard

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Configuração  
**Tipo:** Feature + UX  
**Esforço:** M  
**Identificado em:** 2026-05-20  

---

## Contexto

O perfil versioned (`config/perfis/mendeslobo/versions/v1.json`) contém parâmetros financeiros estruturados que governam toda a lógica de precificação:

```json
{
  "faixa_margem_alvo": { "min": 0.15, "max": 0.25 },
  "faixa_margem_aceitavel": { "min": 0.08, "max": 0.30 },
  "razao_indireto_direto_alvo": { "min": 0.20, "max": 0.40 },
  "categorias_indireto": [
    { "codigo": "ADM", "descricao": "Administração Central", "driver": "permanencia" },
    { "codigo": "TOP", "descricao": "Topografia", "driver": "permanencia" },
    ...
  ]
}
```

**Problemas:**
1. A aba "📋 Perfis" → "➕ Nova versão" exibe apenas campos genéricos (`catalogo_id`, `jurisdicao_id`, `nome`) — os campos financeiros não aparecem
2. O Overview do projeto não mostra os parâmetros do perfil ativo (margem alvo, razão ind/dir) como referência
3. Engenheiro precisa editar o JSON manualmente para ajustar targets de margem

## Critério de Aceite

**Na aba Perfis:**
- Formulário de nova versão substituído por editor tipado (ADR-064) com campos:
  - Margem alvo: `min`/`max` em % (`number_input` 0–100%)
  - Margem aceitável: `min`/`max` em %
  - Razão indireto/direto: `min`/`max` em %
  - Categorias de indireto: `data_editor` com colunas (código, descrição, driver selectbox)
  
**No Overview do projeto:**
- Bloco de métricas "Parâmetros do Perfil":
  - `Margem alvo`: intervalo formatado (ex: "15% – 25%")
  - `Margem aceitável`: intervalo
  - `Razão ind/dir`: intervalo
  - Badge de saúde: 🟢 se resultado atual dentro da faixa, 🟡 se na aceitável, 🔴 se fora

## Notas Técnicas

- A função `_render_perfil_detail` já lê `faixa_margem_alvo` e exibe métricas (parcialmente) — ampliar para incluir edição
- O formulário de nova versão (`_render_new_version_form`) é genérico — criar `_render_perfil_version_form` específico
- Os dados de resultado (margem atual) vêm de `canonical.resultado.margem_pct` via API
