# NEPs — Notas de Evolução de Produto

**Projeto:** Concilium — MendesLobo Construtora  
**Última atualização:** 2026-06-09  
**Total:** 40 NEPs | ✅ 27 Concluídas · ⚠️ 8 Parcial/Em Andamento · 💡 0 Proposta · 📄 5 Doc atualizada

---

## Legenda de Status

| Ícone | Status |
|---|---|
| ✅ | Concluído / Implementado — código em produção |
| ⚠️ | Parcialmente Implementado — trabalho em curso |
| 🔵 | Em Andamento — iniciado, sem entrega ainda |
| 💡 | Proposta — identificado, não iniciado |
| 📄 | Doc atualizada — auditoria confirmou implementação |

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
| [028](nep-028-governanca-precedencia-causal-e-isolamento-catalogo-projeto.md) | Governança de precedência causal e isolamento de catálogo | 🔵 Em Andamento | 🔴 Crítico | — |
| [029](nep-029-divergencia-caminhos-precificacao-unitaria.md) | Divergência na precificação unitária — ausência de fonte canônica | ⚠️ Parcial | 🔴 Crítico | S1 parcial — AGIS calibrado; outros pendentes |
| [030](nep-030-injecao-minima-honesta-benchmark.md) | Injeção mínima honesta na validação de benchmark | 🔵 Em Andamento | 🔴 Crítico | Sprint S4 |
| [031](nep-031-lacunas-modelo-custo-operacional.md) | Lacunas do modelo de custo operacional | ⚠️ Parcial | 🟠 Alto | S2: L4 SS/FF feito; L2/L3 pendentes |
| [032](nep-032-expurgo-precos-unitarios-sbdi-precificacao-bottom-up.md) | Expurgo de `precos_unitarios_sbdi` — precificação bottom-up | 🔵 Em Andamento | 🔴 Crítico | Sprint S1 |
| [033](nep-033-migracao-pdf-renderer-reportlab.md) | Migração PDF renderer: fpdf2 → ReportLab | ⚠️ Parcial | 🟡 Baixo | Cleanup pendente; funcional |
| [034](nep-034-convencao-prefixo-xx-helpers-module-level.md) | Convenção de prefixo `_xx_` em helpers | ⚠️ Parcial | 🟡 Baixo | Manutenção incremental |
| [035](nep-035-decomposicao-eficiencia-eta-s-p-w-observabilidade.md) | Decomposição Causal da Eficiência η_s × η_p × η_w | 📄 Implementado | 🔴 Crítico | Auditado 2026-06-08 |
| [036](nep-036-campo-eficiencia-matricial-log-linear.md) | Campo de Eficiência Matricial E ∈ ℝ^{I×T} | 📄 Implementado | 🟠 Alto | Auditado 2026-06-08 |
| [037](nep-037-encargos-sociais-do-custo-direto-para-bdi.md) | Migração dos Encargos Sociais para a Camada BDI | ⚠️ Parcial | 🔴 Crítico | S2: D1-D4 feitos; fe_nec revisado |
| [038](nep-038-criticidade-rcpsp-compressao-cronograma.md) | Criticidade RCPSP e Teoria de Compressão de Cronograma | 📄 Implementado | 🟡 Alta | Auditado 2026-06-08 |
| [039](nep-039-ciclo-de-vida-benchmark-projeto.md) | Ciclo de vida benchmark-projeto e governança | ⚠️ Parcial | 🟠 Alto | Modelos presentes; MCP tools pendentes |
| [040](nep-040-implementacao-decomposicao-instancial-custos.md) | Implementação da Decomposição Instancial (`custo_inst_*`) | 📄 Implementado | 🔴 Crítico | Auditado 2026-06-08 |

---

## Roadmap de Sprints (débito técnico)

| Sprint | NEPs / ADRs | Entregável | Estado |
|---|---|---|---|
| **S1** | NEP-032 + NEP-029 | Base de preço correta em toda a pipeline | 🔵 Em andamento |
| **S2** | NEP-031 + NEP-037 | Modelo de custo completo + encargos separados | ✅ Parcialmente concluído |
| **S3** | ADR-105 + ADR-106 F1-F4 | Engine unificado + janelas de mobilização | 💡 Aguarda S1 |
| **S4** | ADR-106 F5-F6 + NEP-030 | Early dismissal EQ + benchmark limpo | 💡 Aguarda S3 |

Ver [plano completo](../implementation_plan/plano_engine_custo_sprint_roadmap.md).
