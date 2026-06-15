# Guia da Fachada MCP — Referência de Ferramentas de Negócio

**Projeto:** Concilium — MendesLobo Construtora  
**Audiência:** Engenheiros, Planejadores, CEO (via agente IA)  
**Versão:** 1.0 — 2026-06-12  
**Referências:** ADR-013, ADR-031, ADR-037, ADR-070, ADR-101

---

## O que é a Fachada MCP

O MCP (Model Context Protocol) é a interface pela qual um agente de IA interage com o sistema Concilium. Em vez de expor funções técnicas granulares, a fachada expõe **operações de negócio**: iniciar um orçamento, avançar o planejamento, simular cenários, consultar resultados.

**Princípio central (ADR-013):** cada tool MCP deve fazer sentido para um engenheiro ou gestor, não para um desenvolvedor. Nunca retorna JSON canônico bruto — sempre uma visão orientada à decisão.

**Total de ferramentas:** 48 registradas em 14 módulos.

---

## Grupo 1 — Criação de Projeto

Três formas de criar um projeto, dependendo de quanto você já sabe:

| Tool | Quando usar | Input chave |
|---|---|---|
| `criar_projeto_formulario` | Serviços descritos em linguagem natural ("escavação de 1ª cat., 50.000 m³") | lista de serviços + localização |
| `iniciar_orcamento` | EAP já definida com cpu_ids conhecidos | EAP estruturada com cpu_id por item |
| `criar_projeto_spec` | Spec JSON completo disponível (importação ou migração) | dict ProjetoSpec validado |

**Ordem de preferência:** se tem a EAP com CPUs → `iniciar_orcamento`. Se só tem a lista de serviços → `criar_projeto_formulario`. Se tem o JSON completo → `criar_projeto_spec`.

---

## Grupo 2 — Ciclo de Vida do Projeto

### `consultar_status(project_id)`
Visão completa do estado do projeto: escopos, plano ativo, skills executadas, resultado financeiro atual, integridade da pipeline. Ponto de partida para qualquer interação com um projeto existente.

### `listar_projetos()`
Lista todos os projetos com versão atual, contexto e data de criação. Use para orientar o usuário antes de pedir um `project_id`.

### `consultar_estrutura_projeto(project_id)`
Árvore de escopos → planos com margem de cada plano. Use quando o projeto tem múltiplos escopos ou planos alternativos.

### `configurar_escopo(project_id, ...)` / `gerenciar_plano(project_id, ...)`
Operações de estrutura: criar escopo, criar/aprovar/arquivar plano. Use quando o projeto tem múltiplos cenários de planejamento para comparação.

### `aprovar_versao(project_id, ...)` / `nova_versao(project_id, ...)`
Ciclo de aprovação de planos: `aprovar_versao` congela um plano como referência; `nova_versao` cria uma alternativa sem afetar o plano aprovado.

### `salvar_perfil_bdi(project_id, ...)`
Registra o perfil de BDI (taxas de markup, regime tributário) com versionamento e diff. Use quando as taxas de BDI mudam por negociação ou revisão tributária.

---

## Grupo 3 — Pipeline de Planejamento

A pipeline executa as skills na sequência: escopo → produtividade climática → catálogo → cronograma → equipes → resultado financeiro. Cada skill usa o canonical da skill anterior como entrada.

### `disparar_pipeline(project_id, skill_id, inputs, ...)` *(recomendado)*
Dispara uma skill de forma **assíncrona** — retorna `job_id` imediatamente. Use `consultar_job_pipeline` para acompanhar.

### `consultar_job_pipeline(job_id)`
Retorna status do job: `AGUARDANDO_FILA` → `EM_EXECUCAO` → `CONCLUIDO` / `ERRO` / `CANCELADO`. Quando `CONCLUIDO`, traz o resultado da skill.

### `cancelar_job_pipeline(job_id, motivo)`
Cancela job em fila ou em execução. Jobs em estado final (CONCLUIDO, ERRO) não podem ser cancelados.

### `listar_jobs_pipeline(project_id)` / `obter_estatisticas_jobs()`
Visão operacional: todos os jobs de um projeto, ou estatísticas globais do worker pool.

### `avancar_pipeline(...)` *(síncrono — legado)*
Executa uma skill de forma síncrona. Risco de timeout para skills pesadas (>30s). Preferir `disparar_pipeline` + polling.

---

## Grupo 4 — Catálogo

### Pesquisa e diagnóstico
| Tool | O que faz |
|---|---|
| `listar_contextos()` | Lista contextos disponíveis (mendeslobo, etc.) |
| `pesquisar_catalogo(contexto_id, query)` | Busca CPUs por texto — para encontrar cpu_id de um serviço |
| `consultar_saude_catalogo(contexto_id)` | % insumos com preço, % CPUs calculáveis |
| `avaliar_plausibilidade_catalogo(contexto_id)` | Detecta outliers de preço e produtividade |
| `verificar_integridade_catalogo(contexto_id, ...)` | Consistência referencial + PUs recalculadas |

### Atualização
| Tool | O que faz |
|---|---|
| `atualizar_preco_insumo(...)` | Atualiza preço de insumo com rastreabilidade (quem, quando, motivo) |
| `adicionar_variante_producao(...)` | Cria variante de produção (equipe alternativa para mesma CPU) |
| `calcular_pu_producao(...)` | Simula PU com novos encargos/diesel sem persistir |

### Histórico e comparação de preços
| Tool | O que faz |
|---|---|
| `consultar_preco_insumo_temporal(...)` | Preço de um insumo em data específica |
| `tendencia_precos_catalogo(...)` | Evolução histórica de preços (inflação/deflação) |
| `comparar_rfi_catalogo(...)` | Divergências entre RFI e catálogo master |

### Versionamento de contexto *(ADR-062)*
| Tool | O que faz |
|---|---|
| `listar_versoes_catalogo(contexto_id)` | Histórico de versões: data, autor, motivo de cada versão |
| `comparar_versoes_catalogo(contexto_id, v_a, v_b)` | Diff entre duas versões: campos adicionados, removidos, modificados |

---

## Grupo 5 — Análise

### `auditar_plano(project_id, escopo_id, plano_id)`
Avaliação de viabilidade do plano ativo: resultado financeiro, gargalos operacionais, alertas. Use após completar a pipeline para ter o diagnóstico consolidado.

### `comparar_planos(project_id, escopo_id, plano_a, plano_b)`
Comparação lado a lado de dois planos: custo, margem, prazo, composição de BDI. Use quando há dois cenários alternativos.

### `explorar_pool_recursos(project_id, face, ...)`
Cubo de alocação de recursos com 7 faces analíticas (ADR-086):
- `instancia_ciclo_vida` — ciclo de vida de cada equipamento no pool
- `custo_estado_componente` — custo por estado (ativo/idle/mob/demob)
- `utilizacao_temporal` — histograma de utilização semanal
- `atividade_instancia` — quais atividades usam quais instâncias
- `causa_custo` — origem do custo (produtivo, ocioso, mobilização)
- `economia_pool` — ganho de compartilhamento vs. dedicado
- `cadeia_perpetuacao` — interações de custo entre atividades

---

## Grupo 6 — Replanejamento

### `simular_cenario_replan(project_id, tipo, parametros)`
Estimativa linear do impacto de mudanças de regime ou frentes **sem re-executar a pipeline**. Retorna `delta_custo`, `delta_margem`, itens impactados. Use para feedback imediato antes de decidir se vale re-planejar formalmente.

Parâmetros suportados (`tipo = "lever_adjust"`):
- `fator_equipes` — multiplicador de frentes
- `horas_dia` — override de horas por dia
- `dias_semana` — override de dias por semana
- `meta_margem_pct` — nova meta de margem

> **Limitação:** modelo linear — subestima impacto de mudanças grandes. Para cenários críticos, use `disparar_pipeline` após ajustar o spec.

---

## Grupo 7 — Campanha GO (Exploração Paramétrica)

### `explorar_configuracoes_go(project_id, parametros_sweep, ...)`
Executa N cenários em paralelo variando combinações de parâmetros (regime, frentes, pool, CPU alternativo). Retorna `run_id` e shortlist dos melhores cenários. **É a ferramenta de "what-if" formal** — contrasta com `simular_cenario_replan` que é linear e informal.

### `listar_runs_campanha(project_id)`
Histórico de execuções de campanha do projeto.

### `obter_resultado_campanha(project_id, run_id)`
Shortlist completo, métricas O e EF dos cenários recomendados, cubo analítico.

---

## Grupo 8 — Benchmark

### `listar_benchmarks()` / `executar_benchmark(slug, ...)`
Gerência de benchmarks: lista projetos de referência, executa benchmark completo (pipeline + relatório + pacote ZIP).

### `consultar_benchmark(benchmark_id)` / `listar_benchmarks_nep039()`
Ciclo de vida NEP-039: metadados, histórico de execuções, projetos derivados, imutabilidade.

### `editar_benchmark(benchmark_id, patch)` / `marcar_benchmark_imutavel(benchmark_id)`
Edição controlada: se imutável, gera nova versão automaticamente. Depois de `marcar_benchmark_imutavel`, edições criam v+1 em vez de editar in-place.

---

## Grupo 9 — Artefatos

### `listar_artefatos_projeto(project_id, versao)`
Lista todos os artefatos gerados pelas skills: relatórios MD/PDF, planilhas, JSONs analíticos. Classificados por audiência (`agente` | `humano` | `ambos`).

### `ler_artefato_texto(project_id, nome_arquivo)` / `baixar_artefato_binario(...)`
Leitura de artefatos texto (MD, JSON, CSV) ou download de binários (PDF, XLSX) em base64.

### `baixar_bundle_zip(project_id, versao, filtro)`
Pacote ZIP com todos os artefatos da versão, incluindo `MANIFESTO.md` (ADR-093).

---

## Grupo 10 — Tributação

Ferramentas de cálculo tributário e de encargos trabalhistas, independentes de projeto:

| Tool | O que faz |
|---|---|
| `calcular_custo_empregador_clt(salario_base, categoria)` | Custo total do empregador: salário + todos os encargos CLT horista (177,7%) ou mensalista (106%) |
| `calcular_inss_empregado(salario_bruto)` | INSS do empregado com alíquota efetiva (tabela 2026) |
| `calcular_irrf(base_calculo)` | IRRF mensal com tabela Lei 15.270/2025 |

---

## Grupo 11 — Sistema

### `ping()`
Health check de toda a infraestrutura: config root, contextos, catálogos, projetos. Retorna status de cada componente. Use no início de uma sessão para confirmar que o sistema está disponível.

---

## Fluxo Típico de Uso

```
1. ping()                           — confirmar sistema OK
2. listar_contextos()               — saber contextos disponíveis
3. pesquisar_catalogo(...)          — encontrar cpu_ids para os serviços
4. criar_projeto_formulario(...)    — criar projeto
   ou iniciar_orcamento(...)
5. disparar_pipeline(project_id, "01-escopo-e-eap", ...)
6. consultar_job_pipeline(job_id)   — aguardar conclusão
7. disparar_pipeline(project_id, "02-produtividade-climatica", ...)
   ... (repetir para cada skill)
8. auditar_plano(project_id, ...)   — diagnóstico final
9. explorar_configuracoes_go(...)   — what-if paramétrico
10. listar_artefatos_projeto(...)   — acessar entregáveis
```

---

## Autenticação e Rate Limits

- **JWT obrigatório** (ADR-099): todas as tools verificam token via `McpAuthMiddleware`
- **Permissões por tool:** `project:read`, `project:run`, `project:create`, `catalog:read`, etc.
- **Rate limits:**
  - `criar_projeto_formulario`: 5 chamadas/60s
  - `disparar_pipeline`: gerenciado pelo pool de workers (`max_concurrent_jobs`)
  - demais: sem limite explícito
