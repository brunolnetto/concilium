# ADR-120 — RBAC para Ciclo de Vida do Catálogo: Validação, Atualização e Aprovação de Merge

**Status:** Implementado ✅  
**Data:** 2026-06-22  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-040 (catalog governance), ADR-099 (RBAC), ADR-117 (decorator tags), ADR-119 (multi-actor)

---

## Contexto

### Problema

P1. **O catálogo é um recurso cross-projeto sem governança própria.** Uma alteração de preço em `atualizar_preco_insumo` afeta imediatamente todos os projetos que usam aquele catálogo — mas hoje qualquer `engineer` pode fazer essa alteração sem revisão ou aprovação. Não há conceito de "rascunho de catálogo" separado do ativo.

P2. **`catalog:write` é granularidade única para operações de risco muito diferente.** Adicionar uma variante de produção (`adicionar_variante_producao`) é uma operação de menor risco que aprovar um merge de reajuste de preços de 50 insumos. Ambas usam `catalog:write` hoje.

P3. **Não existe operação de merge/promoção de versão de catálogo.** O sistema versiona o catálogo (`listar_versoes_catalogo`, `comparar_versoes_catalogo`), mas não há fluxo de trabalho para promover uma versão de rascunho para ativa, nem aprovação multi-etapa de uma campanha de atualização de preços.

P4. **Papel de "Gestor de Catálogo" não existe.** Um engenheiro de custos especializado em manutenção de catálogos (SICRO, SINAPI, precificação própria) não tem um role adequado — ou tem acesso demais (admin) ou de menos (engineer com catalog:write genérico).

---

## Decisão

### D1: Três Novas Permissões de Catálogo

| Permissão | Semântica |
|---|---|
| `catalog:validate` | Executar verificações de saúde, plausibilidade e integridade; gerar relatórios de divergência |
| `catalog:write` | Criar/editar rascunhos de catálogo: novos preços, variantes, CPUs em estado de rascunho |
| `catalog:merge` | Promover um rascunho de catálogo para ativo; aprovar merge de campanha de reajuste |

> `catalog:read` (existente) continua cobrindo consultas somente-leitura sem modificação.

### D2: Novo Role — `catalog-manager`

Especialista em manutenção de catálogo de referência. Não tem acesso a projetos dos clientes, somente ao catálogo.

```python
_CATALOG_MANAGER = frozenset({
    CATALOG_READ,
    CATALOG_VALIDATE,
    CATALOG_WRITE,
    CATALOG_MERGE,
    FINANCIALS_READ,   # necessário para avaliar impacto de reajuste
})
```

### D3: Remapeamento de Roles Existentes

| Role | `catalog:read` | `catalog:validate` | `catalog:write` | `catalog:merge` |
|---|:---:|:---:|:---:|:---:|
| `viewer` | ✅ | — | — | — |
| `operator` | ✅ | ✅ | — | — |
| `engineer` | ✅ | ✅ | ✅ | — |
| `catalog-manager` | ✅ | ✅ | ✅ | ✅ |
| `admin` | ✅ | ✅ | ✅ | ✅ |

**Mudança em relação ao estado atual:**
- `engineer` perde `catalog:merge` (que não existia, mas agora é explícito como ausente)
- `engineer` mantém `catalog:write` (rascunhos e variantes)
- `catalog-manager` ganha o role novo
- `operator` ganha `catalog:validate` (pode rodar health checks sem poder escrever)

### D4: Remapeamento das MCP Tools de Catálogo

| Tool MCP | Permissão atual | Nova permissão | Justificativa |
|---|---|---|---|
| `listar_contextos` | `catalog:read` | `catalog:read` | sem mudança |
| `pesquisar_catalogo` | `catalog:read` | `catalog:read` | sem mudança |
| `listar_versoes_catalogo` | `catalog:read` | `catalog:read` | sem mudança |
| `comparar_versoes_catalogo` | `catalog:read` | `catalog:read` | sem mudança |
| `consultar_preco_insumo_temporal` | `catalog:read` | `catalog:read` | sem mudança |
| `tendencia_precos_catalogo` | `catalog:read` | `catalog:read` | sem mudança |
| `calcular_pu_producao` | `catalog:read` | `catalog:read` | sem mudança |
| `comparar_rfi_catalogo` | `financials:read` | `financials:read` | sem mudança |
| **`consultar_saude_catalogo`** | `catalog:read` | **`catalog:validate`** | geração de relatório de saúde |
| **`avaliar_plausibilidade_catalogo`** | `catalog:read` | **`catalog:validate`** | análise de divergência de preços |
| **`verificar_integridade_catalogo`** | `catalog:read` | **`catalog:validate`** | verificação estrutural |
| `atualizar_preco_insumo` | `catalog:write` | `catalog:write` | sem mudança |
| `adicionar_variante_producao` | `catalog:write` | `catalog:write` | sem mudança |

**Novas tools a criar (F2):**

| Tool MCP (nova) | Permissão | Descrição |
|---|---|---|
| `criar_rascunho_catalogo` | `catalog:write` | Inicia uma campanha de atualização em estado de rascunho |
| `listar_divergencias_rascunho` | `catalog:validate` | Relatório de diff entre rascunho e catálogo ativo |
| `aprovar_merge_catalogo` | `catalog:merge` | Promove rascunho para ativo após revisão |
| `rejeitar_rascunho_catalogo` | `catalog:merge` | Descarta rascunho com justificativa |
| `consultar_impacto_reajuste` | `catalog:validate` | Simula impacto financeiro do rascunho em projetos ativos |

### D5: Fluxo de Trabalho de Merge de Catálogo

```
Operador/Engineer (catalog:write)
  └─ criar_rascunho_catalogo(contexto_id, descricao)
       └─ atualizar_preco_insumo(...)  [múltiplas chamadas no rascunho]
       └─ adicionar_variante_producao(...)
       └─ listar_divergencias_rascunho()   [catalog:validate — any operator+]
       └─ consultar_impacto_reajuste()     [catalog:validate — mostra ΔR$ por projeto]

Catalog-Manager / Admin (catalog:merge)
  └─ comparar_versoes_catalogo(rascunho, ativo)
  └─ aprovar_merge_catalogo(rascunho_id, justificativa)
       └─ catálogo ativo atualizado
       └─ VersionAction auditado (ADR-119 D5)
  OU
  └─ rejeitar_rascunho_catalogo(rascunho_id, motivo)
```

### D6: Auditoria de Ações de Catálogo

Toda operação `catalog:write` e `catalog:merge` gera um `CatalogAction` no audit trail (complemento ao `VersionAction` do ADR-119):

```python
@dataclass
class CatalogAction:
    ts: datetime
    actor_id: str
    actor_role: str
    action: Literal["write_draft", "validate", "merge", "reject"]
    contexto_id: str
    rascunho_id: str | None
    n_insumos_afetados: int | None
    detalhes: dict
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter `catalog:write` para merge também | Perde separação de responsabilidade; engineer que edita preços não deveria aprovar seu próprio rascunho |
| A2 | Rascunho como branch Git do repositório de catálogo | Excede complexidade operacional; o modelo atual de overlay JSON é suficiente |
| A3 | Fazer merge automático após N aprovações | Workflow multi-step sem aprovador único aumenta ambiguidade de responsabilidade |
| A4 | Usar `project:approve` para merge de catálogo | Aprovação de projeto e aprovação de catálogo são ações independentes com atores distintos |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Princípio dos 4 olhos | Quem edita o rascunho não pode fazer o merge — separa author de approver |
| Impacto visível antes do merge | `consultar_impacto_reajuste` permite estimar ΔR$ em todos os projetos antes de promover |
| Role especializado | `catalog-manager` permite onboarding de especialistas de custos sem acesso a projetos |
| Rastreabilidade completa | Todo preço alterado em produção tem audit trail de quem editou e quem aprovou |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Fricção para pequenas correções de preço | Permitir fast-track (admin pode aprovar e mergear em um passo) |
| `catalog-manager` sem acesso a projetos pode ser limitante | Role pode ser combinado: um user pode ter `engineer` + `catalog-manager` |
| Rascunhos órfãos (criados e nunca aprovados) | TTL configurável + listagem de rascunhos pendentes para limpeza |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `CATALOG_VALIDATE`, `CATALOG_MERGE` em `permission_guard.py`; `_CATALOG_MANAGER` frozenset; `ROLE_PERMISSIONS["catalog-manager"]`; `_OPERATOR` ganha `catalog:validate`; `_ADMIN` ganha `catalog:merge` | ✅ 2026-06-22 |
| F2 | `auditar_catalogo` remapeada para `@permission("catalog:validate")` (era `catalog:read`) | ✅ 2026-06-22 |
| F3 | 5 novas tools: `criar_rascunho_catalogo`, `listar_divergencias_rascunho`, `consultar_impacto_reajuste`, `aprovar_merge_catalogo`, `rejeitar_rascunho_catalogo`; ceiling 40→45 | ✅ 2026-06-22 |
| F4 | `CatalogAction` dataclass com `action`, `contexto_id`, `rascunho_id`, `n_insumos_afetados` | ✅ 2026-06-22 |
| F5 | 34 testes: permissões, roles, `CatalogAction`, novas tools; `engineer` sem `catalog:merge`; `catalog-manager` sem `project:run` | ✅ 2026-06-22 |

## Definition of Done

### Fase 1
- [x] `CATALOG_VALIDATE = "catalog:validate"` e `CATALOG_MERGE = "catalog:merge"` em `permission_guard.py`
- [x] `_CATALOG_MANAGER` frozenset definido com `catalog:{read,validate,write,merge}` + `financials:read`
- [x] `ROLE_ALLOWED_INTENTS` de ADR-119 não afeta catalog-manager (sem ProcurementIntent)
- [x] Testes: catalog-manager tem `catalog:merge`, engineer não tem

### Fase 2
- [x] `auditar_catalogo(modo=)` com `@permission("catalog:validate")` (consolida as 3 tools antigas)
- [x] `operator` tem `catalog:validate` (pode rodar health checks)
- [x] `viewer` não tem `catalog:validate`

### Fase 3-4
- [x] 5 novas tools registradas com permissions corretas (write/validate/merge)
- [x] `aprovar_merge_catalogo` e `rejeitar_rascunho_catalogo` requerem `catalog:merge`
- [x] `CatalogAction` dataclass pronta; tools emitem via audit trail best-effort

### Fase 5
- [x] 34 testes: permissões, roles, `CatalogAction`, novas tools
- [x] `engineer` sem `catalog:merge`; `catalog-manager` sem `project:run`; `viewer` sem `catalog:validate`

---

## Relacionados

- ADR-040: Catalog Governance Master Project — versionamento do catálogo; este ADR adiciona workflow de merge com controle de acesso
- ADR-099: RBAC — adiciona `catalog:validate`, `catalog:merge` e role `catalog-manager`  
- ADR-117: Decorator tags — novas permissões precisam de `@permission("catalog:validate")` e `@permission("catalog:merge")` nas tools
- ADR-119: Gestão Multi-Ator — `CatalogAction` complementa `VersionAction` no audit trail
