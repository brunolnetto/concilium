# NEP-008: EAP deve ser cascata auditável por versão com decomposição de atividades

**Status:** Concluído  
**Prioridade:** 🟠 Alto  
**Área:** Projetos  
**Tipo:** Feature + Governança  
**Esforço:** L  
**Identificado em:** 2026-05-20  

---

## Contexto

A EAP (Estrutura Analítica do Projeto) é atualmente exibida como um dataframe plano. Não há:
- Distinção entre a EAP original do benchmark vs. ajustes feitos por versão
- Colapsável por item mostrando a composição da CPU associada
- Histórico de como a EAP evoluiu entre versões
- Auditabilidade: quem mudou o quê, quando, por que

Para um projeto de engenharia civil, a EAP é o coração do planejamento. Cada atividade precisa ser auditável desde sua origem (benchmark de referência) até a versão atual.

## Visão de Produto

### Aba "📅 Versões" no Overview

Para cada versão que tem canonical:
```
▶ v1 — 2026-05-18 (referência base)
   ▶ EAP-001: Escavação 1ª cat. — 15.000 m³
       CPU: CPU-TERRA-ESCO-CARGA-1CAT-DMT2000
       Composição: MO(2 op) + EQ(1 escavadeira) + DIESEL
       Produtividade: 42 m³/h
       Custo unitário: R$ 12,40/m³
   ▶ EAP-002: Compactação — 12.000 m³
       ...

▶ v2 — 2026-05-19 (ajuste de equipe)
   ⚡ EAP-001: n_equipes 1 → 2 (Δ custo: +R$ 45.200)
   = EAP-002: inalterado
```

### Estrutura de cada item EAP colapsável

```
📌 {item_id} — {descricao}
   CPU: {cpu_id}  |  Unidade: {unidade}  |  Qtd: {quantitativo}
   ├── Composição de equipe:
   │   ├── 👷 {funcao}: {num_pessoas} × R$ {custo}/mês
   │   └── 🚜 {equip}: {num_unidades} × R$ {custo}/mês
   ├── Insumos diretos:
   │   └── ⛽ {insumo_id}: coef={coef} [{categoria_custo}]
   └── Produtividade: {producao_horaria} {unidade}/h
```

## Critério de Aceite

1. Aba "📅 Versões" acessível no Overview
2. Cada versão com canonical tem seção colapsável
3. Cada item da EAP é `st.expander` mostrando CPU, composição completa, produtividade
4. Diff entre versões: itens novos (+), removidos (-), alterados (⚡)
5. Itens sem alteração entre versões marcados como "= inalterado"

## Notas Técnicas

- Canonical de cada versão: `project.load_canonical(version)` já disponível
- Composição da CPU: via `CatalogResolver.resolve_cpu(cpu_id, ...)` (ADR-066)
- Diff: comparar `canonical_v1.eap` vs `canonical_v2.eap` por `item_id`
- Produtividade por item: de `canonical.cronograma.scheduled_activities[item_id]`
