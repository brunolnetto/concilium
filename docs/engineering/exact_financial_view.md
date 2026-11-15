# Visão financeira exata (#206, W3-A)

Custo, preço e margem exibidos ao usuário vêm **somente** dos ledgers exatos
(P16 → P18 → P20 → P21, certificados por P23). Uma única função de leitura
transforma o canônico nessa visão; resumo de execução, UI, MCP, CLI e deltas
de versão leem dela e de nenhum outro lugar.

Módulo: `src/concilium/application/scheduling/exact_financial_view.py`
Norma: `docs/product/5-specifications/formulario_longo/P23_CERTIFICACAO_E_CUSTO_EXATO.md` (N8–N10).
Nenhuma fórmula normativa muda aqui: a visão só lê o que o P21 já grava.

## Regras

1. A visão lê `resultado.pricing_diagnostics`, `resultado.pricing_gates`,
   `resultado.markup_layers`, as testemunhas P16 dos contratos de pool e o
   registro P18 (estes dois só para explicar um "não avaliado"), e o
   certificado P23 quando fornecido.
2. **Nunca** lê `resultado.venda`, `resultado.custo`, `resultado_financeiro`,
   `margem_pct` nem `status_margem`. Um canônico com campos legados absurdos
   (ou ausentes) produz a mesma visão — há teste para isso.
3. Valores são textos racionais exatos (`"159/5"`). Float só como aproximação
   de exibição (`display_float`, `format_money`, `format_percent`), derivado na
   borda de apresentação e nunca usado em decisão.
4. Não existe semáforo de margem nem "margem" `(P − C)/P`. O produto modela
   camadas de markup; o mínimo é um critério sobre a participação da camada de
   lucro no preço (`profit_layer_share` × `minimum_profit_margin`).
5. Falha fechada: evidência incompleta ou inexata (float onde deveria haver
   racional, camadas ausentes) ⇒ `NAO_AVALIADO`, sem número algum.

## Contrato — `build_exact_financial_view(canonical, certificate=None)`

Aceita o modelo canônico ou o JSON do canônico. Retorna um dict serializável
(`schema = concilium.exact-financial-view.v1`).

| chave | conteúdo |
|---|---|
| `status` | `AVALIADO` ou `NAO_AVALIADO` |
| `reasons` | lista de `{code, message, action, detail}`; vazia quando avaliado |
| `certificate` | `None` ou `{status, decision, effective_decision, recorded_decision, project_go, scope, reasons, gates[{gate_id, status, reason}]}`; `decision` só é `GO` com `project_go is True`, `status == CURRENT` e `effective_decision == GO` |

Somente quando `AVALIADO` (um "não avaliado" tem apenas as quatro chaves `schema`, `status`, `reasons`, `certificate`):

| chave | origem |
|---|---|
| `currency` | `pricing_diagnostics.currency` |
| `cost.{total,direct,indirect}` | `pricing_diagnostics.{total_cost,direct_cost,indirect_cost}` |
| `price` | `pricing_diagnostics.operational_price` |
| `layers.{cost,overhead,profit,taxes,price}` | `markup_layers.total` |
| `by_category[MO,EQ,MAT,COMB,IND].{cost,overhead,profit,taxes,price}` | `markup_layers.by_category` |
| `profit_layer_share`, `minimum_profit_margin` | `pricing_gates` |
| `catalog_benchmark`, `bdi_on_catalog` | `pricing_diagnostics.{catalog_benchmark,implied_bdi_on_catalog}` |
| `regulatory_bdi_rate`, `regulatory_bdi_floor` | `pricing_gates` (BDI sobre a base regulatória e piso agregado ponderado) |
| `bdi_rate_by_category`, `bdi_floor_by_category`, `categories_below_floor` | `pricing_diagnostics.bdi_rate_*`, `markup_layers.{bdi_floor_by_category,bdi_below_category_floor}` |
| `site_indirects.{scope_status,cost,source,reference_id}` | `pricing_diagnostics.site_indirects_*` (N10; `cost` é `null` em `NO_SITE_INDIRECTS`) |
| `gates.{status,regulatory_status,profitability_status,certification_intent,reasons[]}` | `pricing_gates` |

`pricing_diagnostics.realized_margin` e `profit_amount` (ambos `P − C`) não entram na visão.

### Motivos de "não avaliado"

Derivados apenas do que o canônico registra, em ordem determinística:

| `code` | derivado de |
|---|---|
| `SEM_CANONICO`, `RESULTADO_AUSENTE` | canônico/`resultado` ausente |
| `SEM_CONTRATOS_DE_POOL` | `contratos_recurso` vazio (N8) |
| `CONTRATO_SEM_TESTEMUNHA_P16` | contratos sem `p16_global_assignment` (N8); `detail` lista os ids |
| `CONSUMO_P18_AUSENTE` | pool testemunhado, mas `p18_consumption_preview` ausente |
| `ESCOPO_INDIRETOS_CANTEIRO` | `pricing_diagnostics.reason` cita o escopo de indiretos de canteiro (N10) |
| `BDI_PROJETO_NAO_EXATO` | `reason` cita `bdi_projeto_exato` / ponto flutuante (N9.1) |
| `CAMADAS_MARKUP_NAO_DECLARADAS` | `reason` cita as camadas de markup (N9) |
| `LEDGERS_EXATOS_DESATIVADOS` | `reason` cita `p18_consumption_preview_enabled` |
| `P21_NAO_AVALIADO` | qualquer outro `reason` registrado (mostrado literalmente em `detail`) |
| `DECLARACAO_PRECO_AUSENTE` | `reason` genérico "missing p21_pricing_evidence" quando há causa estrutural acima |
| `MOTIVO_NAO_REGISTRADO` | `reason` genérico sem causa estrutural, ou nenhum diagnóstico registrado |
| `EVIDENCIA_EXATA_INCOMPLETA` | diagnóstico presente, mas sem racionais/camadas/gates completos |

O texto registrado pelo P21 é sempre preservado em `detail`; a classificação só acrescenta a norma e a ação corretiva.

**Causa persistida.** Quando a Skill 06 não consegue montar a declaração de preço
(termos faltantes de `precificacao_exata`, perfil de BDI do projeto só em ponto
flutuante, declaração de projeto indisponível), a causa é gravada em
`pricing_diagnostics.reason` — não apenas como aviso da execução — e a vista a
mostra literalmente com a ação corretiva (`TERMOS_DE_PRECO_DO_PERFIL`,
`BDI_PROJETO_NAO_EXATO`). Quando a Skill 06 falha fechada por falta de testemunha
P16 e não registra resultado, a vista lista primeiro os contratos sem testemunha
(`CONTRATO_SEM_TESTEMUNHA_P16`) e depois o resultado ausente.

**Lacuna conhecida.** `VAL-P16-CONTRATO-DESCONHECIDO` (qual termo contratual faltou
ou estava inexato em cada tipo de recurso) não é persistido: a vista diz quais
contratos não têm testemunha e que os termos contratuais devem ser declarados
(N8), mas o campo específico só aparece nos avisos da execução.

## Resumo de execução/versão — `build_summary(canonical)`

```
{
  "financeiro_exato": <visão exata, sem certificado>,
  "pe_deficit_items": int,
  "pe_alerta_items": int
}
```

As chaves legadas `preco_venda_total`, `custo_total`, `resultado_bruto`,
`margem_pct` e `status_margem` **foram removidas** (não reapontadas: uma chave
que muda de significado é uma armadilha). Resumos gravados antes desta visão
só contêm essas chaves; `view_from_summary` os trata como "não avaliado"
(`RESUMO_ANTERIOR_AO_FINANCEIRO_EXATO`) e os números legados não são exibidos.

O certificado não é copiado para o resumo: ele é revalidado a cada leitura e
vive em `run["formalism_certificate"]`. Quem tem a run usa
`with_certificate(view, certificate)`.

## Deltas de versão — `compare_versions`

```
"deltas": {
  "pe_deficit_items": float,
  "financeiro_exato": {
    "schema": "concilium.exact-financial-deltas.v1",
    "status": "AVALIADO" | "NAO_AVALIADO",
    "reasons": [{side: "left"|"right", code, message, action, detail}],
    "deltas": {custo_total, custo_direto, custo_indireto, preco, camada_overhead,
               camada_lucro, camada_tributos, participacao_lucro_no_preco, bdi_sobre_catalogo}
  }
}
```

Cada delta é `direita − esquerda` como racional exato, ou `null` quando algum
lado não foi avaliado — nunca uma diferença contra zero.

## Consumidores nesta fatia

- UI: `presentation/ui/helpers/financeiro_exato.py` (lógica sem Streamlit),
  `organisms/layout/_version_summary_detail.py`, `_ops_audit_compare.py`.
- MCP: `consultar_status` (`resultado_atual.financeiro_exato`), `auditar_plano`
  (`financeiro_exato`), `comparar_planos` (`financeiro_exato` por plano +
  `deltas_financeiro_exato`), `consultar_estrutura_projeto`
  (`planos[].financeiro_exato`, forma compacta), `ResumoProjetoSchema`.
- CLI: `concilium audit`, `concilium validate project` (`text_lines`).
- Serviços: `build_summary` (resumo da run), `compare_versions`.

Consumidores de decisão (Skill08, campanha, cenários, aprovação de plano,
benchmarks), de documento (Skill09, entregáveis, Excel) e as análises de
ponto de equilíbrio continuam nos campos legados e são tratados nas próximas
fatias do épico #206.
