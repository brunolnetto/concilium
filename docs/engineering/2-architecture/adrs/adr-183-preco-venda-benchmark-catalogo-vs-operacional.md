# ADR-183 — Relatório de Benchmark Reportava Preço de Catálogo Rotulado como Operacional

**Status:** Implementado ✅
**Data:** 2026-08-16
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-085 (Custo Instancial), ADR-090 (BDI Sistemático), ADR-110 (Remediação de Fallbacks Silenciosos, §P7/F7 — desatualizada por esta ADR), ADR-114 (Golden Example — fonte de verdade atual da semântica catálogo vs. operacional)

---

## Contexto

### Problema

Ao explicar a margem do benchmark `MATA_DENSA_SIMPLES` (usuário perguntou por que a margem final era menor que a soma das camadas de BDI por categoria — tributos+lucro+overhead), tracei o campo `preco_venda` do relatório de confronto (`R$3.379.141,65`) e achei que ele vinha de `Venda.total_com_bdi` — que hoje é o valor de **catálogo** (PU×Q com BDI), não o valor **operacional** (custo instancial real via pool × BDI, que seria `R$3.520.488,77` — escondido no campo `total_custo_plus`, exposto sem rótulo como `preco_venda_plus_eq`).

**Causa raiz (arqueologia de git):** o commit `07ee661c` (2026-06-06, mensagem não relacionada — "fix: remove warnings and unify presentation MCP modules") reverteu `total_com_bdi` de operacional (`venda_plus`) de volta para catálogo (`venda_catalogo_plus`) em `_resultado.py`, e reescreveu o comentário local de "PREÇO OPERACIONAL HONESTO" para "mantém contrato histórico de benchmark". `src/concilium/application/benchmarks/report/projection.py` (`_bfc_preco_venda`, `_bfc_bdi_lucro`) e `report_printer.py` **nunca foram atualizados** para acompanhar esse revert — continuaram lendo/documentando `total_com_bdi` como se fosse operacional. A **ADR-110** (escrita 12 dias depois, 2026-06-18, que criou o mecanismo `preco_venda_fonte`/homogeneidade justamente para este campo) também documenta `total_com_bdi` como "(operacional)" — ou seja, foi escrita com a premissa já desatualizada. A **ADR-114** (2026-06-19) corrigiu formalmente a confusão para o resto do sistema — `margem_pct`/`resultado_financeiro` em `_resultado.py` já usam a base operacional correta (`total_custo_plus`) — mas o relatório de benchmark ficou para trás.

**Um terceiro ponto do mesmo bug**, achado na revisão do plano: `_build_ferramenta_custo` também expunha `"preco_venda_operacional": venda.total_com_bdi` (catálogo) — mesmo erro, no mesmo arquivo, com comentário igualmente desatualizado.

### Por que isso importa

`_bfc_bdi_lucro` também preferia `Venda.bdi_lucro_impostos`, calculado em `_resultado.py` como `venda_catalogo_plus / custo_operacional_real - 1` — **mistura numerador de catálogo com denominador operacional**, gerando um "markup efetivo" que não é nem catálogo puro nem operacional puro, mascarando quanto do BDI nominal (~14-30% por categoria) realmente sobrevive depois do custo real de execução (mobilização por semana cheia via pool, ADR-086).

---

## Decisão

### D1 — `projection.py::_bfc_preco_venda`: Nível 1 passa a ler `Venda.total_custo_plus`

Em vez de `Venda.total_com_bdi` (catálogo). Fonte retornada passa de `"total_com_bdi"` para `"total_custo_plus"`. Nível 2 (fallback catálogo, `total_custo_plus_catalogo`) e Nível 3 (derivado) mantidos sem mudança — já corretamente nomeados.

### D2 — `projection.py::_bfc_bdi_lucro`: prefere `Venda.bdi_equivalente_proj`

Em vez de `Venda.bdi_lucro_impostos`. `bdi_equivalente_proj` já é calculado em `_resultado.py` como `venda_plus / custo_operacional_real - 1` — mesma base operacional dos dois lados, sem misturar catálogo com operacional. Não foi necessário calcular nada novo, só apontar para o campo que já existia com a fórmula certa.

### D3 — `_build_ferramenta_custo`: `preco_venda_operacional` corrigido para `total_custo_plus`

Mesmo fix do D1, ponto de exposição separado no dicionário de saída. `preco_venda_plus_eq` (que já lia `total_custo_plus` corretamente) fica redundante com `preco_venda_operacional` — não removido nesta correção (candidato a limpeza futura).

### D4 — `report_builder.py`: `homogeneo` passa a checar `fonte == "total_custo_plus"`

Mantém a mesma intenção conceitual ("fonte operacional confiável para comparação homogênea"), só corrige a string. Confirmado que esse campo não alimenta a decisão real do gate (S0-S3/APROVADO) — é informativo, hoje não lido por mais ninguém além do próprio JSON de saída.

### D5 — Escopo deliberadamente restrito ao relatório de benchmark

Consumidores fora do relatório de benchmark usam `Venda.total_com_bdi` **corretamente e deliberadamente** como catálogo/contratual, e não foram tocados:
- Excel (`_resultado_ml.py`, `_indiretos.py`, `_referencia.py`, `cash_flow.py`) — "Preço de Venda ao cliente"/fluxo de caixa deve refletir faturamento contratual (catálogo), não custo real.
- MCP tools (`projeto.py`, `replan.py`) e dashboards — mesma semântica catalogada.
- `Venda.total_com_bdi` em si (modelo de dados, `_financeiro_resultado.py`) — schema já documentado corretamente, não precisa mudar.

---

## Achados relacionados — mesma classe de bug, NÃO corrigidos nesta sessão

Mesma mistura de bases (catálogo × operacional) encontrada de passagem em dois lugares independentes, fora do escopo desta ADR — ficam para decisão/sessão futura:

1. **`infrastructure/adapters/excel/sheets/resultado/_resultado_ml.py`** — fórmula de "Margem bruta (%)" mistura receita de catálogo com custo operacional, divergindo do `res.margem_pct` real do modelo canônico.
2. **`runtime/deliverables/visualizations/cube/scurve_custo.py::_bdi_decomp`** — decompõe BDI em Overhead/Lucro/Tributos como `preço(catálogo) − custo(operacional)`, mesma mistura de bases do antigo `bdi_lucro_impostos`.

## ADR-110 — nota de errata

A seção P7/F7 da ADR-110 documenta `total_com_bdi` como "(operacional)" — isso ficou desatualizado frente ao revert `07ee661c` (anterior à própria ADR-110) e à correção formal da ADR-114 (posterior). Esta ADR-183 é a retificação — ADR-110 não foi reescrita, só recebe este apontamento.

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Relatório de benchmark honesto | `preco_venda (operac.)` agora reflete o custo instancial real × BDI, não o catálogo |
| Markup efetivo confiável | `bdi_lucro_impostos` deixa de misturar bases; usa `bdi_equivalente_proj`, já correto |
| Consistência com ADR-114 | Relatório de benchmark alinhado com `margem_pct`/`resultado_financeiro`, que já usavam a base certa |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Muda o que alimenta o gate de confronto (`report_builder.py` compara `preco_venda` contra referência de benchmarks reais com gabarito, ex. GOLDEN/AGIS) — deltas percentuais e severidades S0-S3 podem mudar | Rodada suíte completa + `test_golden_evaluation.py`/`test_pipeline.py`/`test_multi_escopo.py` — 0 regressão confirmada. `MATA_DENSA_SIMPLES` não tem referência ("Sem dados de referencia para confronto"), não afetado nesse aspecto específico |
| Testes com `MagicMock`/`SimpleNamespace` fixando `total_com_bdi`/`bdi_lucro_impostos` para os 3 níveis de fallback de `_bfc_preco_venda` | Atualizados: `test_benchmark_report_projection.py`, `test_viz_cube.py` — mais um teste de regressão novo que trava o bug (`test_prefere_operacional_sobre_catalogo_adr183`) |

---

## Definition of Done

- [x] `_bfc_preco_venda` lê `total_custo_plus` como Nível 1
- [x] `_bfc_bdi_lucro` prefere `bdi_equivalente_proj`
- [x] `preco_venda_operacional` corrigido em `_build_ferramenta_custo`
- [x] `report_builder.py` `homogeneo` checa `"total_custo_plus"`
- [x] Testes atualizados (`test_benchmark_report_projection.py`, `test_viz_cube.py`) + teste de regressão novo
- [x] Suíte de benchmarks (1635 testes) + integração (golden/pipeline/multi-escopo, 58 testes) verde
- [x] Excel/cash-flow/scurve confirmados intocados e verdes (consumidores catálogo-based corretos)

---

## Relacionados

ADR-085, ADR-090, ADR-110, ADR-114, ADR-086 (CuboPoolInstancial), ADR-182 (consolidação de encargos — sessão que originou esta investigação)
