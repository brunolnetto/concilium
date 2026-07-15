---
name: 06-resultado-financeiro-consolidacao
description: Use when computing the final financial result — aggregates direct costs, BDI, indirect costs and produces margin, selling price, break-even and the Bridge Analysis (ADR-039).
---

# Skill 06 — Consolidação Financeira

Produz o balanço financeiro final do projeto: agrega custos diretos (equipes × BDI por categoria), custos indiretos (BDI-INDIRETO), calcula a margem e o preço de venda, reconcilia custos reais vs. catálogo (The Bridge, ADR-039) e gera os artefatos analíticos do espaço ontológico — Curva ABC, S-Curve, Cubo Analítico 4D e Memorial de Cálculo BDI (ADR-057/058).

## Quando ativar

Após `06-resultado-financeiro/_precificacao` ter calculado os preços unitários com BDI e `06-resultado-financeiro/_indiretos` ter calculado os custos indiretos por categoria.

## Inputs

| Nome | Tipo | Obrigatório | Descrição |
|------|------|-------------|-----------|
| `bdi_aplicado` | `{mao_obra, material, diesel, equipamentos, indireto}` | não | Override manual de BDI por categoria |
| `tabela_bdi` | `TabelaBdi` (serializada) | não | Tabela BDI completa (10 componentes × 5 categorias) |
| `bdi_perfil` | `PerfilBdiProjeto` | não | Perfil de projeto específico (snapshot versionado) |
| `tax_scenario` | `TaxSimulationScenario` | não | Cenário CBS/IBS (ADR-055) — substitui tributos pre-reforma |
| `tabela_bdi_lucro_impostos` | float | não | Override direto do markup efetivo |

**Prioridade de resolução de BDI** (ADR-057 §D3):
1. `tax_scenario` (CBS/IBS — ADR-055)
2. `bdi_aplicado` (override manual)
3. `tabela_bdi` (tabela explícita)
4. `bdi_perfil` (perfil de projeto)
5. `DEFAULT_BDI_TABELA` (fallback da empresa, abril/2026)

## Depende de

**Skills predecessoras**:
- [`05-equipes-e-alocacao`](../../05-equipes-e-alocacao/SKILL.md) — `equipes_diretas` com custo breakdown
- [`_precificacao`](../_precificacao/SKILL.md) — `planejamento` com PU × BDI por item
- [`_indiretos`](../_indiretos/SKILL.md) — `indiretos`, `indiretos_semanal`, `indiretos_com_bdi`

## Produz

**Seção principal do canônico**: `resultado`, `resultado_reconciliado`, `bridge_analysis`, `ponto_equilibrio`, `custos_atividades`

**Artefatos analíticos** (ADR-056/057/058):
- `memorial_calculo_bdi` — auditoria completa da cadeia BDI (ADR-057)
- `curva_abc_insumo` — ranking ABC por funcao_id/equip_id (ADR-058)
- `s_curve` — curva S de desembolso acumulado semanal (ADR-058)
- `cubo_analitico` — cubo 4D: categoria × atividade × tempo × componente_BDI (ADR-058 ext.)

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `resultado.venda.total_com_bdi` | float | Preço de venda ao cliente (R$) |
| `resultado.custo.total` | float | Custo base (direto + indireto, sem BDI) |
| `resultado.margem_pct` | float | Margem como % do preço de venda |
| `resultado.status_margem` | string | VERDE / AMARELO / VERMELHO |
| `bridge_analysis` | dict | Análise de 4 níveis: catálogo → escala → clima → operacional |
| `ponto_equilibrio` | list | Break-even por item da EAP |
| `custos_atividades` | list | Breakdown de custo por atividade × indiretos (ADR-056 §T2) |

**Validações**:
- `VAL-CONSOL-BDI-FONTE` / `VAL-CONSOL-BDI-REGIME` — rastreabilidade do BDI aplicado
- `VAL-CONSOL-OK` — resultado consolidado com sucesso

## Fórmula de resultado

```
venda_total = Σ_items { PU_com_BDI × quantitativo }          # de planejamento (_precificacao)
            + Σ_indiretos { custo_indireto × (1 + BDI_INDIRETO) }  # de _indiretos

custo_total = Σ_items { PU_sem_BDI × quantitativo }
            + Σ_indiretos { custo_sem_bdi }

resultado_financeiro = venda_total - custo_total
margem_pct = resultado_financeiro / venda_total
```

## Bridge Analysis (ADR-039)

Decompõe a diferença entre custo catálogo e custo operacional em 4 níveis:

```
N1 = custo_catalogo_base            (PU × Q, sem escala)
N2 = custo_escala                   (N1 × fator de quantização ceil(F)/F)
N3 = custo_normalizado_clima        (N2 / praticabilidade_media)
N4 = custo_operacional_real         (custo real reportado ou estimado)

delta_estrutural = N3 - N1         (ineficiência estrutural inevitável)
delta_operacional = N4 - N3        (ineficiência de gestão)
```

## Notas de implementação

- O BDI para equipamentos usa `tabela.servicos.bdi_total` (não `tabela.equipamentos`) — conforme ADR-023 §D3, equipamentos são tratados como serviços para fins de markup.
- `custo_combustivel_efetivo` na EquipeDireta já incorpora eficiência semanal de praticabilidade — o cálculo de margem reflete o custo real de combustível da campanha.
- `custos_atividades` (ADR-056 §T2): populado pela função `_build_custos_atividades()` que une equipes_diretas, planejamento e cronograma por `item_id`.
- `memorial_calculo_bdi` (ADR-057): gerado após o resultado, captura a cadeia BDI completa incluindo encargos, componentes, decomposição no preço e aplicação por item.

## Próximas skills no pipeline

- [`09-relatorio-e-artefatos`](../../09-relatorio-e-artefatos/SKILL.md)
- [`07-diagnostico-criticidade`](../../07-diagnostico-criticidade/SKILL.md)
- [`08-replanejamento-e-cenarios`](../../08-replanejamento-e-cenarios) (assessor de replanejamento — sem SKILL.md próprio)
