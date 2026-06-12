# ADR-108: CampaignBundleCube Alimentado pelos Cubos de Custo e Cronograma

**Status:** Proposto → Implementado 2026-06-12  
**Relacionado:** ADR-069 (Cubo Analítico), ADR-070 (Campanha de Exploração), ADR-086 (Cubo Pool), ADR-087 (Modelo Dimensional)

---

## Problema

O `CampaignBundleCube` (ADR-070) extrai métricas flat do canonical (`resultado.margem_pct`, `cronograma.makespan_semanas`) sem passar pelos cubos existentes. Isso limita o poder analítico: o cubo do bundle compara cenários mas não explica **por que** um cenário domina o outro em custo ou prazo.

Já existem e estão populados por cenário:

| Cubo | Localização | Células AGIS | Dimensões |
|---|---|---|---|
| `cubo_analitico` | `canonical.cubo_analitico.celulas` | 3.204 | natureza, atividade_id, categoria_insumo, propriedade, semana_iso, componente_bdi |
| `cronograma.scheduled_activities` | `canonical.cronograma.scheduled_activities` | 11 ativ. | activity_id, start_week, end_week, assigned_resources, distribuicao_semanal |
| `CuboPoolFace` | `canonical.cubo_pool_face` | (stub) | item_id, semana, tipo_recurso, estado |

---

## Decisão

### D1 — Enriquecer VetorEspacoEF com composição de custo do cubo_analitico

Agregar `cubo_analitico.celulas` onde `componente_bdi = "custo_direto"`:

```
share_mo_pct    = Σ valor_rs[categoria=mao_obra]    / Σ valor_rs_total
share_eq_pct    = Σ valor_rs[categoria=equipamento] / Σ valor_rs_total
share_comb_pct  = Σ valor_rs[propriedade=combustivel] / Σ valor_rs_total
concentracao_atividade = HHI = Σ (share_i)²  (1.0 = monopólio, 1/N = uniforme)
```

Estes campos respondem: "por que a configuração A tem custo menor — é porque tem menos MO, menos equipamento, ou menos combustível?"

### D2 — Enriquecer VetorEspacoO com métricas de utilização do cronograma

A partir de `cronograma.scheduled_activities`:

```
utilizacao_recursos_pct = Σ active_weeks_por_recurso / Σ mobilized_weeks_por_recurso
paralelismo_medio       = média de atividades ativas em simultâneo por semana
```

`utilizacao_recursos_pct` mede eficiência do pool: valor baixo → recursos mobilizados mas ociosos → mob_window caro.

### D3 — Faces do CampaignBundleCube incluem dimensões do cubo_analitico

Novas métricas passam a ser variáveis de resposta nas faces e resumos marginais. Exemplo: face `n_max × share_eq_pct` mostra se aumentar frentes sobe a proporção de equipamento no custo (esperado — mais máquinas = mais aluguel relativo).

### D4 — CuboPoolFace integrado quando não for stub

`idle_pool_pct = Σ semanas_idle / Σ semanas_totais_mobilizadas` entrará em `vetor_O` quando `canonical.cubo_pool_face` for populado (ADR-106 F8 completo). Enquanto stub, fica `None`.

---

## Vetores Enriquecidos

### VetorEspacoO (adições)

| Campo | Fonte | Descrição |
|---|---|---|
| `utilizacao_recursos_pct` | `scheduled_activities.distribuicao_semanal` | Semanas produtivas / semanas mobilizadas (pool) |
| `paralelismo_medio` | `scheduled_activities` | Atividades ativas em simultâneo, média semanal |
| `idle_pool_pct` | `CuboPoolFace` (quando disponível) | Fração de semanas idle no pool mobilizado |

### VetorEspacoEF (adições)

| Campo | Fonte | Descrição |
|---|---|---|
| `share_mo_pct` | `cubo_analitico` (categoria=mao_obra) | Fração MO no custo direto |
| `share_eq_pct` | `cubo_analitico` (categoria=equipamento) | Fração equipamento no custo direto |
| `share_comb_pct` | `cubo_analitico` (propriedade=combustivel) | Fração combustível no custo direto |
| `concentracao_atividade` | `cubo_analitico` por atividade | HHI de concentração de custo por atividade |

---

## Invariantes

**IC-1:** `share_mo + share_eq + share_comb ≤ 1.0` (residual = materiais e outros)  
**IC-2:** `concentracao_atividade ∈ [1/N, 1.0]` onde N = número de atividades  
**IC-3:** `utilizacao_recursos_pct ∈ [0, 1]`  
**IC-4:** Quando `cubo_analitico` for vazio, todos os campos `share_*` são `None` (sem falha silenciosa)

---

## Exemplo de Insight Habilitado

Com as novas dimensões no CampaignBundleCube AGIS:

```
Face: n_max × share_eq_pct
  n_max×0.75: share_eq=55%   # Menos máquinas → MO domina mais
  n_max×1.0:  share_eq=59%
  n_max×1.25: share_eq=63%   # Mais máquinas → EQ domina

Resumo marginal: n_max/share_eq → crescente
Insight: "Adicionar frentes substitui MO por EQ — para obras com BDI_EQ < BDI_MO,
         n_max alto melhora a margem pela diferença de alíquotas."
```

---

## Implementação

Única mudança no serviço: `extrair_vetor_O` e `extrair_vetor_EF` passam a receber o canonical completo e consultar `cubo_analitico` e `scheduled_activities`.

Sem mudança no pipeline — os cubos já são gerados por skill-06 e skill-04.
