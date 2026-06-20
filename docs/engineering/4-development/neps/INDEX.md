# NEPs — Notas de Evolução de Produto

**Projeto:** Concilium — MendesLobo Construtora  
**Última atualização:** 2026-06-12  
**Total:** 47 NEPs | ✅ 35 Concluídas · ⚠️ 4 Parcial/Em Andamento · 💡 3 Proposta

---

## Legenda de Status

| Ícone | Status |
|---|---|
| ✅ | Concluído / Implementado — código em produção |
| ⚠️ | Parcialmente Implementado — trabalho em curso |
| 🔵 | Em Andamento — iniciado, sem entrega ainda |
| 💡 | Proposta — identificado, não iniciado |

---

## NEPs 001–027 — Concluídas

| NEP | Título | Status |
|---|---|---|
| [001](nep-001-jurisdicoes-artefatos-sinapi-sicro.md) | Jurisdições não expõem provedores SINAPI/SICRO | ✅ |
| [002](nep-002-perfil-parametros-edicao-dashboard.md) | Parâmetros financeiros do perfil não editáveis | ✅ |
| [003](nep-003-tabs-configuracao-invertidas.md) | Tabs da Configuração exibem conteúdo trocado | ✅ |
| [004](nep-004-tema-layout-editor.md) | Layout do editor de tema desorganizado | ✅ |
| [005](nep-005-categoria-diversos-reclassificacao.md) | Categoria "DIVERSOS" é genérica demais | ✅ |
| [006](nep-006-composicao-coluna-dados-incompletos.md) | Coluna Composição ignora equipe no catálogo | ✅ |
| [007](nep-007-overview-dashboard-execucoes-primeiro.md) | Overview deve exibir dashboard antes do resumo | ✅ |
| [008](nep-008-eap-cascata-auditavel-por-versao.md) | EAP deve ser cascata auditável por versão | ✅ |
| [009](nep-009-cpus-composicao-equipe-incompleta.md) | CPUs de terraplenagem sem composição de equipe | ✅ |
| [010](nep-010-produtividade-base-zeros.md) | Coluna "Base [un/h]" de produtividade exibe zeros | ✅ |
| [011](nep-011-custos-indiretos-equipe-editavel.md) | Equipe de apoio nos custos indiretos sem edição completa | ✅ |
| [012](nep-012-bdi-decomposicao-completa-tcu.md) | BDI pré-reforma não expõe componentes TCU | ✅ |
| [013](nep-013-saidas-antes-pipeline.md) | "Saídas" deve preceder botão "Iniciar Pipeline" | ✅ |
| [014](nep-014-abas-excel-fundamentais-complementares.md) | Abas Excel sem distinção semântica + Curva ABC ausente | ✅ |
| [015](nep-015-botoes-tema-escuro-painel-controle.md) | Botões do Painel não respeitam tema claro/escuro | ✅ |
| [016](nep-016-eap-vazia-pipeline-feedback.md) | Pipeline falha com "EAP vazia" sem diagnóstico | ✅ |
| [017](nep-017-inventario-skills-readme-desatualizado.md) | Inventário de Skills no README desatualizado | ✅ |
| [018](nep-018-entregaveis-keys-desalinhadas-runtime-ui.md) | Chaves de entregáveis desalinhadas runtime/UI | ✅ |
| [019](nep-019-persistencia-artefatos-tipados.md) | Persistência e exposição de artefatos tipados | ✅ |
| [020](nep-020-limpeza-ids-legados-pipeline-strategy.md) | Limpeza de IDs legados em Pipeline Strategy | ✅ |
| [021](nep-021-documentacao-plano-v2-5-obsoleta.md) | Documento de plano v2.4→v2.5 obsoleto | ✅ |
| [022](nep-022-variavel-cpu-mapping-benchmark-agnostico.md) | Variável de mapping CPU para contexto agnóstico | ✅ |
| [023](nep-023-env-separacao-api-ui-e-legacy-mapping.md) | Variáveis de ambiente para separação API/UI | ✅ |
| [024](nep-024-cubo-analitico-multidimensional-granularidade-temporal.md) | Cubo analítico multidimensional com granularidade temporal | ✅ |
| [025](nep-025-pe-backtracking-orientado-ao-cubo.md) | PE e backtracking orientados ao cubo analítico | ✅ |
| [026](nep-026-descontinuacao-legacy-alias-lingua-franca.md) | Descontinuação de legacy/alias e língua franca | ✅ |
| [027](nep-027-centralizacao-de-inferencias-de-benchmark.md) | Centralização das inferências de benchmark | ✅ |

---

## NEPs 028–040 — Ativas / Débito Técnico

| NEP | Título | Status | Prioridade | Nota |
|---|---|---|---|---|
| [028](nep-028-governanca-precedencia-causal-e-isolamento-catalogo-projeto.md) | Governança de precedência causal e isolamento de catálogo | ✅ Implementado | 🔴 Crítico | A1-A4 + D4 ✅ (2026-06-10); modo estrito de catálogo = evolução futura |
| [029](nep-029-divergencia-caminhos-precificacao-unitaria.md) | Divergência na precificação unitária — ausência de fonte canônica | ⚠️ Parcial | 🔴 Crítico | S1 parcial — AGIS calibrado; outros pendentes |
| [030](nep-030-injecao-minima-honesta-benchmark.md) | Injeção mínima honesta na validação de benchmark | 🔵 Em Andamento | 🔴 Crítico | Sprint S4 |
| [031](nep-031-lacunas-modelo-custo-operacional.md) | Lacunas do modelo de custo operacional | ✅ Implementado | 🟠 Alto | L2 diesel ✅; L3 manutenção equipamentos ✅ (auditado 2026-06-10) |
| [032](nep-032-expurgo-precos-unitarios-sbdi-precificacao-bottom-up.md) | Expurgo de `precos_unitarios_sbdi` — precificação bottom-up | ✅ Implementado | 🔴 Crítico | `_compute_preco_cat_from_production()` é rota primária; sbdi emite `VAL-PLAN-SBDI-LEGADO` (auditado 2026-06-10) |
| [033](nep-033-migracao-pdf-renderer-reportlab.md) | Migração PDF renderer: fpdf2 → ReportLab | ✅ Implementado | 🟡 Baixo | RL default desde antes; docstring e docs atualizados (2026-06-10) |
| [034](nep-034-convencao-prefixo-xx-helpers-module-level.md) | Convenção de prefixo `_xx_` em helpers | ✅ Implementado | 🟡 Baixo | Single underscore uniforme em 93+ helpers de skill-05 (auditado 2026-06-10) |
| [035](nep-035-decomposicao-eficiencia-eta-s-p-w-observabilidade.md) | Decomposição Causal da Eficiência η_s × η_p × η_w | ✅ Implementado | 🔴 Crítico | Auditado 2026-06-08 |
| [036](nep-036-campo-eficiencia-matricial-log-linear.md) | Campo de Eficiência Matricial E ∈ ℝ^{I×T} | ✅ Implementado | 🟠 Alto | Auditado 2026-06-08 |
| [037](nep-037-encargos-sociais-do-custo-direto-para-bdi.md) | Migração dos Encargos Sociais para a Camada BDI | ✅ Implementado | 🔴 Crítico | F1-F3 já existiam; F5 memorial adicionado 2026-06-10; F4 mantido por decisão deliberada |
| [038](nep-038-criticidade-rcpsp-compressao-cronograma.md) | Criticidade RCPSP e Teoria de Compressão de Cronograma | ✅ Implementado | 🟡 Alta | Auditado 2026-06-08 |
| [039](nep-039-ciclo-de-vida-benchmark-projeto.md) | Ciclo de vida benchmark-projeto e governança | ✅ Implementado | 🟠 Alto | Fases 1-4 completas; proveniência exposta via consultar_status (2026-06-10) |
| [040](nep-040-implementacao-decomposicao-instancial-custos.md) | Implementação da Decomposição Instancial (`custo_inst_*`) | ✅ Implementado | 🔴 Crítico | Auditado 2026-06-08 |
| [041](nep-041-consolidacao-skills-analise-saida.md) | Consolidação de Skills de Análise, Saída e Financeiro (09+15, 13+14, 06+07+08, freeze 11+12) | ✅ Implementado | 🟠 Alto | Fases 1-4 ✅ (2026-06-11): pipeline 15→11 skills; gate AGIS paridade exata; Fase 5 (re-enumeração cosmética) deferida |
| [042](nep-042-modelo-tres-camadas-precificacao.md) | Modelo de Três Camadas de Precificação — PU_cat, PU_op_autonomo, burden_pool | ✅ Implementado | 🟠 Alto | D1-D3 campos no PontoEquilibrio; D4 view PRECO_UNITARIO_TRES_CAMADAS no relatório (2026-06-10) |
| [043](nep-043-reconciliacao-cr-custo-operacional-pu-catalogo.md) | Reconciliação C_r: custo operacional de equipe vs PU de catálogo | ✅ Resolvido | 🔴 Crítico | 3 bugs curados (n_frentes, encargos skill-06, custo_hora_total_referencia); premissa de igualdade revisada → `instancial ≤ catálogo` (ADR-085); vigiado por golden ADR-114 (2026-06-19) |
| [044](nep-044-cpsat-requisito-sem-fallback-silencioso.md) | CP-SAT como requisito: falha explícita em vez de fallback silencioso | ✅ Implementado | 🟠 Alto | `explore_schedules()` agora lança `ScheduleError` em vez de cair no MINSLK silenciosamente (2026-06-12) |
| [045](nep-045-remocao-milp-scheduler-legado.md) | Remoção do MILPScheduler (código morto) | ✅ Implementado | 🟡 Baixo | milp.py removido; skill-04, skill-13, CLI e testes limpos (2026-06-12) |
| [046](nep-046-lns-metricas-reais.md) | Métricas reais no LNS (remover _simple_metrics trivial) | ✅ Implementado | 🟠 Médio | leveling/idle/utilization reais via resource_usage de _ssgs() (2026-06-12) |
| [047](nep-047-ramp-profiles-lns-completion.md) | Ramp profiles (ADR-074): completar suporte no LNS | ✅ Implementado | 🟠 Médio | _find_start e _book_resources usam _lns_demand_at_offset; CP-SAT conservador documentado (2026-06-12) |
| [048](nep-048-review-composicao-times-indiretos.md) | Review composição times indiretos: MOB mob_schedule dead-code + custo×0.15 | ✅ Fechado | 🟠 Médio | B1/B2 curados; B3/B4 deprecados como limitações aceitas (2026-06-19) |

---

## Roadmap de Sprints (débito técnico)

| Sprint | NEPs / ADRs | Entregável | Estado |
|---|---|---|---|
| **S1** | NEP-032 ✅ + NEP-029 ⚠️ | Base de preço correta em toda a pipeline | ⚠️ NEP-032 concluído; NEP-029 parcial (falta overlay AGIS) |
| **S2** | NEP-031 ✅ + NEP-037 ✅ + ADR-097 F1-F4 ✅ | Modelo de custo completo + encargos separados + centralizações | ✅ Concluído (2026-06-10) |
| **S3** | ADR-105 F1-F3 ✅ + ADR-106 F1-F4/F7 ✅ + ADR-105 F4-F5 + ADR-106 F5-F6 | Engine unificado + fases mob/op/demob | ⚠️ F1-F4/F7 implementados; F5-F6 deferred (catálogo); ADR-105 F4-F5 aguardam dados |
| **S4** | NEP-030 + NEP-039 | Injeção honesta benchmark + ciclo de vida | 💡 Aguarda S3 |

Ver [plano completo](../implementation_plan/plano_engine_custo_sprint_roadmap.md).
