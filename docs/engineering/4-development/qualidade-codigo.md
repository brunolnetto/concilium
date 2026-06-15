# Qualidade de Código — Rastreamento Contínuo

**Última medição:** 13 de Junho de 2026  
**Ferramenta:** pytest-cov + radon (CC, MI) + relatório `.coverage-reports/report.md`

---

## Metas

| Métrica | Meta | Status atual | Gap |
|---|---|---|---|
| Cobertura de testes | ≥ 95% | 56.3% | −38.7pp |
| Complexidade ciclomática (média) | B+ (CC ≤ 10) | A (CC 4.4) | ✅ média OK, 18 arquivos D |
| Tamanho máximo de arquivo | < 400 linhas | p90 = 369, p99 = 1302 | 51 arquivos > 400 linhas |

---

## Histórico de Snapshots

| Data | Cobertura | CC médio | Arquivos > 400 linhas | Arquivos CC D | Observação |
|---|---|---|---|---|---|
| 2026-06-13 | 56.3% | 4.4 (A) | 51 | 18 | Linha de base |
| 2026-06-13 | ~59% est. | 4.4 (A) | 51 | 18 | Tier 1: +176 testes (domain models, BDI, progress, replanning, pool_validator, MCP schemas) |
| 2026-06-13 | ~64% est. | 4.4 (A) | 51 | 18 | Tier 2: +190 testes (cloud adapters, GDrive, S3, ConfigurationManager, API deps, catalog extraction, ExcelLiveModel, ExcelIngestion) |
| 2026-06-13 | ~72% est. | 4.4 (A) | 51 | 18 | 0% sweep: +251 testes (benchmark comparison, cronograma_parser, reconciliacao, output_packager, catalog mapping, healer, updater, CLI, MCP proxy, eficiência viz) |

> Atualizar esta tabela após cada ciclo de melhoria com os valores extraídos de `.coverage-reports/report.md`.

---

## Baseline — 13 de Junho de 2026

### Distribuição de cobertura (425 arquivos rastreados)

```
  0–10 %  │████████████████████████  87 (20.5%)   ← principal alvo
 10–20 %  │███████████              39 ( 9.2%)
 20–60 %  │█████████████████████    70 (16.5%)
 60–90 %  │████████████████████████ 97 (22.8%)
 90–100%  │████████████████████████████████████ 132 (31.1%)
```

- Arquivos com < 60%: 196 (46.1%)
- Arquivos com < 80%: 246 (57.9%)
- Linhas descobertas: **19.688** de ~35.000 executáveis

### Distribuição de complexidade ciclomática (4.106 funções)

| Rank | CC | Funções | % |
|---|---|---|---|
| A | 1–5 | 3.021 | 73.6% |
| B | 6–10 | 861 | 21.0% |
| C | 11–15 | 98 | 2.4% |
| D | 16+ | 126 | 3.1% |

### Arquivos acima de 400 linhas (51 arquivos)

**Outliers críticos (> 600 linhas com código ativo):**

| Arquivo | Linhas | Cobertura | Prioridade de quebra |
|---|---|---|---|
| `infrastructure/adapters/excel_adapter.py` | 3.605 | 85.4% | Alta |
| `presentation/ui/organisms/layout.py` | 3.413 | 5.7% | Alta |
| `skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py` | 2.905 | 83.7% | Média |
| `skills/manifests/04-cronograma/skill.py` | 2.221 | 77.0% | Média |
| `domain/models/canonical.py` | 1.827 | 97.8% | Baixa |
| `infrastructure/adapters/excel_live_model.py` | 1.302 | 0.0% | Alta |
| `skills/manifests/09-relatorio-e-artefatos/_skill_helpers_a.py` | 1.140 | 71.2% | Média |
| `skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers_a.py` | 1.135 | 87.8% | Baixa |
| `application/services/campaign_service.py` | 1.109 | 65.7% | Alta |
| `infrastructure/settings.py` | 980 | 80.2% | Baixa |
| `application/services/concilium_service.py` | 930 | 32.2% | Alta |
| `application/services/project_service.py` | 850 | 22.4% | Alta |
| `application/services/campaign_report.py` | 809 | 86.1% | Baixa |
| `infrastructure/catalog/query_engine.py` | 797 | 37.4% | Média |
| `presentation/ui/templates/_project_page_helpers_b.py` | 720 | 22.1% | Média |

---

## Plano de Melhoria por Tier

### Tier 1 — Quick wins: lógica pura sem dependências externas

Arquivos com 0% de cobertura que são modelos de domínio, dataclasses ou funções puras.
Testes simples de instanciação e comportamento básico já trazem impacto imediato.

| Arquivo | Linhas faltando | Dificuldade |
|---|---|---|
| `domain/models/bdi.py` | 202 | Baixa |
| `domain/models/jurisdicao.py` | 52 | Baixa |
| `domain/models/overrides.py` | 38 | Baixa |
| `domain/models/perfil.py` | 28 | Baixa |
| `domain/models/referencia.py` | 28 | Baixa |
| `application/progress/models.py` | 30 | Baixa |
| `application/progress/tracker.py` | 153 | Baixa |
| `application/replanning/assessor.py` | 26 | Baixa |
| `application/replanning/detector.py` | 49 | Baixa |
| `application/replanning/validator.py` | 40 | Baixa |
| `presentation/mcp/tools/schemas.py` | 40 | Baixa |
| `presentation/mcp/tools/prompts.py` | 6 | Baixa |
| `application/scheduling/pool_validator.py` | 42 | Baixa |

**Impacto estimado:** +2–3pp de cobertura global

### Tier 2 — Mock de infraestrutura

Adaptadores externos que requerem `unittest.mock`. Padrão já estabelecido no projeto
(ver `tests/unit/test_coverage_boost_misc.py` como referência).

| Arquivo | Linhas faltando | Notas |
|---|---|---|
| `infrastructure/adapters/excel_live_model.py` | 910 | Maior gap individual |
| `infrastructure/adapters/cloud_blob_storage.py` | 12 | Pequeno, fácil |
| `infrastructure/adapters/gdrive_blob_storage.py` | 136 | Requer mock OAuth |
| `infrastructure/adapters/s3_blob_storage.py` | 115 | Requer mock boto3 |
| `infrastructure/config.py` | 123 | Variáveis de ambiente |
| `presentation/api/deps.py` | 7 | FastAPI deps |
| `infrastructure/catalog/excel_ingestion.py` | 68 | Requer mock openpyxl |
| `infrastructure/catalog/extraction/*.py` | ~213 | Funções de parsing |

**Impacto estimado:** +4–6pp de cobertura global

### Tier 3 — CLI commands (Click test runner)

Usar `CliRunner` do Click para testar comandos sem execução real.
Padrão já existe em `tests/unit/test_cli_commands.py`.

| Arquivo | Linhas faltando | Notas |
|---|---|---|
| `presentation/cli/commands_reconciliacao.py` | 75 | 0% cobertura |
| `presentation/cli/commands_health.py` | 78 | 8.7% cobertura |
| `presentation/cli/commands_bdi.py` | 127 | 10.2% cobertura |
| `presentation/cli/commands_benchmark.py` | 250 | 10.3% cobertura |
| `presentation/cli/commands_schedule.py` | 75 | 13.9% cobertura |
| `presentation/cli/commands_config_version.py` | 111 | 14.0% cobertura |
| `presentation/cli/commands_campaign.py` | 86 | 6.0% cobertura |
| `presentation/cli/_commands_manage_helpers_*.py` | ~410 | 8–13% cobertura |

**Impacto estimado:** +5–7pp de cobertura global

### Tier 4 — Visualizações: refatorar + testar (resolve CC e cobertura juntos)

Esses arquivos têm CC=D (≥16) **e** cobertura <12%. A abordagem é extrair a lógica
de cálculo/transformação de dados para funções puras separadas das funções de plot Plotly.
As funções de plot ficam com `# pragma: no cover`; as funções de cálculo ganham testes unitários.

| Arquivo | CC | Cobertura | Linhas faltando |
|---|---|---|---|
| `charts/painel_equilibrio.py` | 60 D | 1.8% | 114 |
| `cube/_relatorio_fallback.py` | 60 D | 3.1% | 107 |
| `cube/_renderers.py` | 21 D | 3.4% | 179 |
| `charts/fluxo_financeiro.py` | 28 D | 3.5% | 71 |
| `cube/linha_recursos_tempo.py` | 36 D | 5.6% | 60 |
| `cube/scurve_custo.py` | 28 D | 6.2% | 85 |
| `cube/bar_atividade_componente.py` | 15 C | 7.1% | 91 |
| `charts/gantt.py` | 16 D | 8.3% | 38 |
| `cube/pool_custo_estado.py` | 17 D | 8.1% | 47 |
| `cube/pool_economia.py` | 31 D | 11.0% | 59 |
| `cube/pool_utilizacao_temporal.py` | 19 D | 11.9% | 44 |

**Impacto estimado:** −6 arquivos CC D + 2–3pp de cobertura global

### Tier 5 — Serviços principais (maior impacto de cobertura, maior risco)

Serviços centrais com baixa cobertura. Exigem fixtures complexas e cuidado para
não criar testes frágeis. Abordar após os tiers 1–3 estabilizarem a suíte.

| Arquivo | Cobertura | Linhas faltando |
|---|---|---|
| `application/services/concilium_service.py` | 32.2% | ~630 |
| `application/services/project_service.py` | 22.4% | ~590 |
| `application/services/_project_service_helpers.py` | 24.5% | ~340 |
| `infrastructure/storage/file_project_repository.py` | 42.3% | ~200 |
| `infrastructure/catalog/query_engine.py` | 37.4% | ~290 |

**Impacto estimado:** +8–12pp de cobertura global (se completados)

### Tier 6 — UI Streamlit (cobertura estrutural mínima)

Templates e páginas Streamlit são intrinsecamente difíceis de testar.
A estratégia é cobertura de "smoke" — importar e verificar que não quebra na construção.
Não buscar 100% nesses arquivos; excluir do threshold ou aplicar `# pragma: no cover`
nas funções de renderização pura.

| Grupo | Arquivos | Linhas faltando |
|---|---|---|
| `presentation/ui/templates/` | ~15 arquivos | ~1.500 |
| `presentation/ui/organisms/` | 2 arquivos (sidebar, layout) | ~1.470 |
| `presentation/ui/molecules/` | 2 arquivos | ~130 |

---

## Arquivos CC D — Lista de Refatoração

18 arquivos com avg CC > 11.4 **e** cobertura < 80% (fonte: Quality Blame do relatório):

| Arquivo | CC médio | CC máx | Cobertura |
|---|---|---|---|
| `charts/painel_equilibrio.py` | 60 D | 60 | 1.8% |
| `cube/_relatorio_fallback.py` | 60 D | 60 | 3.1% |
| `cube/linha_recursos_tempo.py` | 36 D | 36 | 5.6% |
| `cube/pool_economia.py` | 31 D | 31 | 11.0% |
| `charts/fluxo_financeiro.py` | 28 D | 28 | 3.5% |
| `cube/scurve_custo.py` | 28 D | 28 | 6.2% |
| `cube/_renderers.py` | 21.8 D | 31 | 3.4% |
| `cube/pool_utilizacao_temporal.py` | 19 D | 19 | 11.9% |
| `cube/pool_custo_estado.py` | 17 D | 17 | 8.1% |
| `presentation/ui/templates/_perfis_helpers_b.py` | 19.2 D | 34 | 33.5% |
| `charts/gantt.py` | 16 D | 16 | 8.3% |
| `cube/bar_atividade_componente.py` | 15 C | 23 | 7.1% |
| `cli/commands_reconciliacao.py` | 15 C | 15 | 0.0% |
| `benchmarks/referencia_enricher.py` | 14.8 C | 25 | 0.0% |
| `visualizations/eficiencia/eta_obra.py` | 14 C | 14 | 0.0% |
| `visualizations/eficiencia/heatmap_top_n.py` | 14 C | 14 | 0.0% |
| `mcp/tools/formulario.py` | 12 C | 25 | 13.9% |
| `reports/report_markdown_sections.py` | 15.2 C | 42 | 68.3% |

---

## Projeção de Cobertura por Tier

| Após completar | Cobertura estimada |
|---|---|
| Baseline (atual) | 56.3% |
| + Tier 1 (modelos de domínio) | ~59% |
| + Tier 2 (mock de infra) | ~64% |
| + Tier 3 (CLI commands) | ~70% |
| + Tier 4 (visualizações refatoradas) | ~73% |
| + Tier 5 (serviços principais) | ~83% |
| + Tier 6 (UI estrutural) | ~87% |
| + Demais 273 arquivos < 90% | ~95%+ |

> Projeção conservadora. O relatório mostra que cobrir todos os 293 arquivos < 90% levaria a 99.5%.

---

## Como Regenerar o Relatório

```bash
make coverage        # roda testes + gera .coverage-reports/coverage.json e test-report.json
make codebase-stats  # analisa métricas e gera .coverage-reports/report.md
```

Após regenerar, extrair os valores principais e adicionar uma linha na tabela de **Histórico de Snapshots** acima.
