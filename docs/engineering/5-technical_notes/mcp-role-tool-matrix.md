# MCP — Matriz Role × Tool e Handoffs

> Fonte de verdade do código: `src/concilium/presentation/mcp/tools/` e
> `src/concilium/infrastructure/auth/permission_guard.py`  
> Última revisão: 2026-06-23 (43 tools; revisão completa dos register())
> Nota (2026-08-04): `consultar_ponto_equilibrio` adicionada; `simular_cenario_replan`
> depreciada (ver `docs/engineering/2-architecture/adrs/ADR-101-mcp-apps-interface-interativa.md`).
> Contagem de 43 não reauditada nesta nota — ver `test_rbac_mcp_tool_mapping.py` (56) como fonte viva.

---

## 1. Matriz Role × Tool

`✓` = acesso permitido · `—` = sem permissão · `◑` = acesso parcial (restrição de intent)

| Tool | Permissão | operator | engineer | admin | auditor | cat-manager |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **Sistema** | | | | | | |
| `ping` | health:read | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Projetos — leitura** | | | | | | |
| `listar_projetos` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `consultar_status` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `consultar_estrutura_projeto` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `comparar_planos` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `explorar_pool_recursos` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `consultar_job_pipeline` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `listar_jobs_pipeline` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `listar_runs_campanha` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `consultar_benchmark` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| `consultar_ponto_equilibrio` | project:read | ✓ | ✓ | ✓ | ✓ | — |
| **Projetos — criação** | | | | | | |
| `criar_projeto` | project:create | ✓ | ✓ | ✓ | — | — |
| `iniciar_orcamento` | project:create | ✓ | ✓ | ✓ | — | — |
| `nova_versao` | project:create | ✓ | ✓ | ✓ | — | — |
| `gerir_escopo` | project:create | ✓ | ✓ | ✓ | — | — |
| **Projetos — execução** | | | | | | |
| `disparar_pipeline` | project:run | ◑ RFI | ✓ RFI+RFP | ✓ RFI+RFP | — | — |
| `cancelar_job_pipeline` | project:run | ✓ | ✓ | ✓ | — | — |
| `explorar_configuracoes_go` | project:run | ◑ RFI | ✓ RFI+RFP | ✓ RFI+RFP | — | — |
| `empacotar_benchmark` | project:run | ✓ | ✓ | ✓ | — | — |
| `salvar_perfil_bdi` | project:run | ✓ | ✓ | ✓ | — | — |
| `simular_cenario_replan` **[DEPRECATED]** — usar `consultar_ponto_equilibrio` para baseline | project:run | ✓ | ✓ | ✓ | — | — |
| **Projetos — aprovação** | | | | | | |
| `aprovar_versao` | project:approve | — | ✓ | ✓ | — | — |
| **Artefatos** | | | | | | |
| `listar_artefatos_projeto` | artifacts:read | ✓ | ✓ | ✓ | ✓ | — |
| `auditar_plano` | artifacts:read | ✓ | ✓ | ✓ | ✓ | — |
| `obter_artefato` | artifacts:download | ✓ | ✓ | ✓ | ✓ | — |
| `download_benchmark_zip` | artifacts:download | ✓ | ✓ | ✓ | ✓ | — |
| **Catálogo — leitura** | | | | | | |
| `listar_contextos` | catalog:read | ✓ | ✓ | ✓ | — | ✓ |
| `pesquisar_catalogo` | catalog:read | ✓ | ✓ | ✓ | — | ✓ |
| `historico_preco_insumo` | catalog:read | ✓ | ✓ | ✓ | — | ✓ |
| `calcular_pu_producao` | catalog:read | ✓ | ✓ | ✓ | — | ✓ |
| `versoes_catalogo` | catalog:read | ✓ | ✓ | ✓ | — | ✓ |
| `calcular_tributos` | catalog:read | ✓ | ✓ | ✓ | — | ✓ |
| `exportar_pesquisa_mercado` | catalog:read | ✓ | ✓ | ✓ | — | ✓ |
| **Catálogo — validação** | | | | | | |
| `auditar_catalogo` | catalog:validate | ✓ | ✓ | ✓ | — | ✓ |
| `listar_divergencias_rascunho` | catalog:validate | ✓ | ✓ | ✓ | — | ✓ |
| `consultar_impacto_reajuste` | catalog:validate | ✓ | ✓ | ✓ | — | ✓ |
| **Catálogo — escrita** | | | | | | |
| `atualizar_preco_insumo` | catalog:write | — | ✓ | ✓ | — | ✓ |
| `adicionar_variante_producao` | catalog:write | — | ✓ | ✓ | — | ✓ |
| `criar_rascunho_catalogo` | catalog:write | — | ✓ | ✓ | — | ✓ |
| **Catálogo — merge** | | | | | | |
| `aprovar_merge_catalogo` | catalog:merge | — | — | ✓ | — | ✓ |
| `rejeitar_rascunho_catalogo` | catalog:merge | — | — | ✓ | — | ✓ |
| **Financeiro** | | | | | | |
| `obter_resultado_campanha` | financials:read | ✓ | ✓ | ✓ | ✓ | ✓ |
| `comparar_rfi_catalogo` | financials:read | ✓ | ✓ | ✓ | ✓ | ✓ |

**Nota sobre intent (◑):** operator só pode usar `intent=RFI`; engineer e admin podem usar
`intent=RFI` ou `intent=RFP`. Validado em `permission_guard.py` via `INTENT_PERMISSIONS`.

---

## 2. Contagem por role

| Role | Tools acessíveis |
|---|:---:|
| **operator** | 36 |
| **engineer** | 40 |
| **admin** | 42 |
| **auditor** | 16 |
| **cat-manager** | 18 |

---

## 2b. Regiões do diagrama de Euler (análise `eule`)

> Gerado via `eule.Euler(role → tools).as_dict()`. Cada região mostra os tools
> acessíveis a **exatamente** aqueles roles — nem mais, nem menos.
> Nenhuma tool é exclusiva de um único role.

| Zona (roles que compartilham) | Tools |
|---|---|
| **admin ∩ catalog-manager** | `aprovar_merge_catalogo`, `rejeitar_rascunho_catalogo` |
| **admin ∩ engineer** | `aprovar_versao` |
| **admin ∩ engineer ∩ catalog-manager** | `adicionar_variante_producao`, `atualizar_preco_insumo`, `criar_rascunho_catalogo` |
| **admin ∩ engineer ∩ operator** | `cancelar_job_pipeline`, `criar_projeto`, `disparar_pipeline`, `empacotar_benchmark`, `explorar_configuracoes_go`, `gerir_escopo`, `iniciar_orcamento`, `nova_versao`, `salvar_perfil_bdi`, `simular_cenario_replan` |
| **admin ∩ engineer ∩ operator ∩ auditor** | `auditar_plano`, `comparar_planos`, `consultar_benchmark`, `consultar_estrutura_projeto`, `consultar_job_pipeline`, `consultar_status`, `download_benchmark_zip`, `explorar_pool_recursos`, `listar_artefatos_projeto`, `listar_jobs_pipeline`, `listar_projetos`, `listar_runs_campanha`, `obter_artefato` |
| **admin ∩ engineer ∩ operator ∩ catalog-manager** | `auditar_catalogo`, `calcular_pu_producao`, `calcular_tributos`, `consultar_impacto_reajuste`, `exportar_pesquisa_mercado`, `historico_preco_insumo`, `listar_contextos`, `listar_divergencias_rascunho`, `pesquisar_catalogo`, `versoes_catalogo` |
| **admin ∩ engineer ∩ operator ∩ auditor ∩ catalog-manager** | `comparar_rfi_catalogo`, `obter_resultado_campanha` |
| **todos os roles** | `ping` (health:read) |

**Conclusão:** operator não tem tools exclusivas — toda tool acessível a operator
também é acessível a engineer, admin e/ou service-ci. A responsabilidade de operator
é precificação baseada em catálogo (RFI); o planejamento completo (RFP) é de engineer/admin.

---

## 3. Intersecções relevantes

| Tool | Comportamento diferente por role |
|---|---|
| `disparar_pipeline` | operator: RFI apenas; engineer/admin: RFI + RFP |
| `explorar_configuracoes_go` | operator: RFI apenas; engineer/admin: RFI + RFP |
| `atualizar_preco_insumo` | engineer/admin: acesso via projeto; cat-manager: acesso via catálogo (sem ver projetos) |
| `criar_rascunho_catalogo` | engineer pode criar mas não pode fazer merge; cat-manager pode criar e fazer merge; admin pode tudo |
| `obter_resultado_campanha` | ponto de intersecção entre auditor e cat-manager — único tool financeiro acessível pelos dois sem acesso a projetos |

---

## 4. Handoffs entre roles

Um handoff é uma sequência onde a ação de um role cria um estado que exige ação de outro role.

### H1 — Execução → Aprovação (operator → engineer)

```
operator
  └─ disparar_pipeline(intent=RFI)
       └─ versão em estado EM_VALIDACAO
            └─ engineer / admin   ← HANDOFF
                 └─ aprovar_versao(versao_id=...)   ← tool MCP disponível
                      └─ versão → APROVADO
```

### H2 — Exploração → Análise completa (operator → engineer)

```
operator
  └─ explorar_configuracoes_go(intent=RFI)
       └─ campanha com configurações iniciais
            └─ engineer / admin   ← HANDOFF
                 └─ explorar_configuracoes_go(intent=RFP)
                      └─ disparar_pipeline(intent=RFP)
                           └─ análise financeira completa
```

### H3 — Rascunho de catálogo → Merge (engineer → admin ou cat-manager)

```
engineer
  └─ criar_rascunho_catalogo(...)
       └─ atualizar_preco_insumo / adicionar_variante_producao
            └─ listar_divergencias_rascunho   ← validação
                 └─ admin / cat-manager   ← HANDOFF (engineer não pode fazer merge)
                      └─ aprovar_merge_catalogo(rascunho_id=...)
                           └─ catálogo atualizado
```

Este handoff é intencional: segrega quem edita de quem aprova (regra dos quatro olhos).

### H4 — Novo usuário → Onboarding (admin → usuário)

```
admin
  └─ [CLI] concilium ops auth user create
       └─ NotificationService.notify_user_created()   ← ADR-123 (a implementar)
            └─ email com claude_desktop_config.json
                 └─ usuário configura Claude Desktop   ← HANDOFF
                      └─ usuário inicia sessão MCP
```

---

## 5. Gap real identificado

Nenhum gap pendente.
