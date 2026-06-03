# NEP-010: Coluna "Base [un/h]" de produtividade exibe zeros por join incompleto

**Status:** Concluído  
**Prioridade:** 🔴 Crítico  
**Área:** Projetos  
**Tipo:** Bug  
**Esforço:** S  
**Identificado em:** 2026-05-20  

---

## Contexto

No Painel de Controle → Planejamento → Custos Diretos → "💪🏽 Produtividade das CPUs", a coluna "Base [un/h]" exibe `0.0` para todas as CPUs, mesmo que o catálogo contenha fichas de produtividade com `valor_horario` preenchido.

## Causa Raiz

A função `render_cpu_productivity_override` (layout.py) tenta resolver `producao_horaria` a partir do snapshot do benchmark reference. Quando a referência não existe (projeto do tipo `project`) ou quando o snapshot não contém o campo, o fallback retorna `0.0`.

O sistema já possui (ADR-066) um join `producao_id_ref → valor_horario` implementado em `CatalogResolver._enrich_cpus_with_producao()`, mas `render_cpu_productivity_override` não usa esse caminho — ainda faz lookup manual pela referência.

## Gap Técnico

```python
# Atual (busca no snapshot da referência — falha quando ausente):
producao_horaria = _catalog_cpus_prod.get(cpu_id, {}).get("valor_horario", 0.0)

# Correto (via API que usa CatalogResolver com join ADR-066):
GET /api/catalogs/{catalog_id}/cpus?limit=500
# Já retorna producao_horaria enriquecida
```

## Critério de Aceite

- Coluna "Base [un/h]" mostra o `valor_horario` da ficha de produtividade para cada CPU
- CPUs sem ficha de produtividade registrada mostram "—" (não "0")
- Funciona tanto para `hot_project` (com referência) quanto para `project` (sem referência)

## Notas Técnicas

Substituir o lookup manual pelo endpoint `/api/catalogs/{catalog_id}/cpus` que já usa `_enrich_cpus_with_producao`. O `catalog_id` é obtido via contexto do projeto (`contexto.catalogo_id`).
</content>
</invoke>