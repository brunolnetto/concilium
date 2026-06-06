# ADR-099 — RBAC: Roles e Permissões para Redução de Superfície de Ataque

**Status:** Proposta
**Data:** 2026-06-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-094 (JWT Auth), ADR-098 (Rate Limiting)

---

## Contexto

### Problema

P1. **Blast radius excessivo por chave comprometida.** O modelo atual (ADR-094) usa
escopos planos: `mcp:read` e `pipeline:run`. Uma chave de serviço CI/CD com
`pipeline:run` comprometida pode criar projetos, executar pipelines, baixar bundles
financeiros e até aprovar versões — tudo com um único token.

P2. **Sem separação entre personas de consumidor.** Não há distinção entre:
- Engenheiro de campo que só precisa criar projetos e ver status
- Agente LLM CI/CD que só precisa executar pipelines
- Stakeholder externo que só precisa baixar relatórios
- Admin que gerencia usuários e configurações

P3. **Aprovação de versão sem guarda adequada.** `aprovar_versao` é irreversível
(congela arquivos) mas está protegida apenas por `mcp:read` — qualquer viewer pode
aprovar acidentalmente.

P4. **Sem isolamento por recurso.** Qualquer cliente com `pipeline:run` pode executar
pipelines em qualquer projeto, não apenas nos seus.

---

## Decisão

D1. **Hierarquia de roles com herança.**

```
viewer   ⊂  operator  ⊂  engineer  ⊂  admin
                                     service-ci  (role especializado, sem herança vertical)
                                     auditor     (role especializado, só leitura financeira)
```

D2. **Permissões granulares** (substituem `scopes` planos do ADR-094).

| Permissão | Descrição |
|---|---|
| `project:read` | Listar/consultar projetos, versões, status |
| `project:create` | Criar novos projetos (`criar_projeto_formulario`, `iniciar_orcamento`) |
| `project:run` | Executar pipeline (`avancar_pipeline`, `POST .../runs`) |
| `project:approve` | Aprovar/congelar versão (operação irreversível) |
| `artifacts:read` | Listar artefatos |
| `artifacts:download` | Baixar artefatos e bundles ZIP |
| `catalog:read` | Consultar catálogo de CPUs e insumos |
| `catalog:write` | Escrever no catálogo mestre |
| `financials:read` | Ler dados financeiros (preço de venda, custo, margem) |
| `auth:manage` | Criar usuários, emitir device codes, revogar dispositivos |
| `system:read` | Health check, informações do sistema |

D3. **Mapeamento role → permissões.**

| Role | Permissões |
|---|---|
| `viewer` | `project:read`, `artifacts:read`, `catalog:read` |
| `operator` | `viewer` + `project:create`, `project:run`, `artifacts:download`, `financials:read` |
| `engineer` | `operator` + `project:approve`, `catalog:write` |
| `admin` | `engineer` + `auth:manage`, `system:read` |
| `service-ci` | `project:create`, `project:run` ← sem `financials:read`, sem `project:approve` |
| `auditor` | `project:read`, `artifacts:read`, `artifacts:download`, `financials:read` |

**Blast radius por comprometimento:**

| Role comprometida | O que o atacante pode fazer |
|---|---|
| `viewer` | Ler projetos e artefatos (sem dados financeiros) |
| `service-ci` | Criar projetos e executar pipelines — não vê custos, não aprova |
| `auditor` | Ler resultados financeiros — não executa, não aprova |
| `operator` | Criar + executar + ver resultados — não aprova, não gerencia auth |
| `engineer` | Tudo exceto gestão de usuários |

D4. **JWT claim: `roles` substitui `scopes`.**

```json
{
  "sub": "agente-copilot",
  "org": "mendesloboconstrucao",
  "roles": ["operator"],
  "exp": 1748736000
}
```

As permissões são **derivadas dos roles** em runtime — não ficam no JWT.
Isso permite alterar o mapeamento role → permissão sem revogar tokens existentes.

D5. **`PermissionGuard` — substituição do `scope_guard`.**

```python
# infrastructure/auth/permission_guard.py

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "viewer":     frozenset({"project:read", "artifacts:read", "catalog:read"}),
    "operator":   frozenset({*ROLE_PERMISSIONS["viewer"],
                             "project:create", "project:run",
                             "artifacts:download", "financials:read"}),
    "engineer":   frozenset({*ROLE_PERMISSIONS["operator"],
                             "project:approve", "catalog:write"}),
    "admin":      frozenset({*ROLE_PERMISSIONS["engineer"],
                             "auth:manage", "system:read"}),
    "service-ci": frozenset({"project:create", "project:run"}),
    "auditor":    frozenset({"project:read", "artifacts:read",
                             "artifacts:download", "financials:read"}),
}

def get_permissions(roles: list[str]) -> frozenset[str]:
    """Computa permissões efetivas a partir dos roles do token."""
    result: set[str] = set()
    for role in roles:
        result |= ROLE_PERMISSIONS.get(role, frozenset())
    return frozenset(result)

def require_permission(permission: str, token_roles: list[str]) -> None:
    """Levanta PermissionError se o token não tem a permissão necessária."""
    if permission not in get_permissions(token_roles):
        raise PermissionError(
            f"Permissão '{permission}' necessária. "
            f"Roles do token: {token_roles}. "
            f"Solicite ao admin o role adequado."
        )
```

D6. **Mapeamento endpoint → permissão** (FastAPI dependency).

```python
# presentation/api/deps.py

def require(permission: str):
    def dependency(token: dict = Depends(get_current_token)):
        require_permission(permission, token.get("roles", []))
        return token
    return dependency

# Uso:
@router.post("/formulario/projeto")
def criar_projeto(token: dict = Depends(require("project:create"))):
    ...

@router.post("/{project_id}/runs")
def run_project(token: dict = Depends(require("project:run"))):
    ...
```

D7. **Mapeamento MCP tool → permissão.**

```python
TOOL_PERMISSIONS: dict[str, str] = {
    "listar_projetos":          "project:read",
    "consultar_status":         "project:read",
    "criar_projeto_formulario": "project:create",
    "iniciar_orcamento":        "project:create",
    "avancar_pipeline":         "project:run",
    "aprovar_versao":           "project:approve",
    "listar_artefatos_projeto": "artifacts:read",
    "ler_artefato":             "artifacts:download",
    "baixar_bundle_zip":        "artifacts:download",
    "listar_cpus":              "catalog:read",
    "buscar_cpu":               "catalog:read",
}
```

D8. **Migração de `scopes` para `roles` nos clientes existentes.**

Para compatibilidade, `token_service.py` aceitará ambos até a Fase 3:
- Token com `scopes: ["mcp:read"]` → mapeado para `roles: ["viewer"]`
- Token com `scopes: ["pipeline:run"]` → mapeado para `roles: ["operator"]`
- Token com `roles: ["engineer"]` → usa o novo modelo diretamente

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Manter escopos planos (ADR-094) | Blast radius não endereçado; sem distinção service-ci vs human |
| R2 | ABAC (Attribute-Based Access Control) | Over-engineered para 1 cliente; regras complexas difíceis de auditar |
| R3 | Permissões no JWT (não derivadas) | Atualizar permissões exige revogar todos os tokens; não escalável |
| R4 | OAuth2 completo (authorization server externo) | Dependência pesada; LDAP/Entra ID seriam necessários — prematura para este estágio |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Blast radius reduzido | Comprometimento de `service-ci` não acessa dados financeiros nem aprova versões |
| Separação clara de personas | CI/CD, engenheiros, auditores, admins com roles distintos |
| Migração sem downtime | Compatibilidade com `scopes` antigos na Fase de transição |
| Permissões centralizadas | Uma mudança em `ROLE_PERMISSIONS` propaga imediatamente sem revogar tokens |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Quebra de compatibilidade em tokens existentes | Fase de migração com mapeamento scopes→roles transparente |
| Complexidade adicional de onboarding | `concilium auth new-device` já solicita role; `AGENT_SKILL_TUTORIAL.md` documenta |
| Possível over-permissioning (dar engineer para todos) | Documentar que CI/CD DEVE usar `service-ci`, não `engineer` |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | `permission_guard.py` — ROLE_PERMISSIONS + get_permissions + require_permission | 🔴 Proposta |
| 2 | FastAPI `deps.py` — `require(permission)` dependency em todos os endpoints sensíveis | 🔴 Proposta |
| 3 | MCP `scope_guard.py` → migrar para TOOL_PERMISSIONS + PermissionGuard | 🔴 Proposta |
| 4 | `token_service.py` — claim `roles` no JWT; mapeamento legado scopes→roles | 🔴 Proposta |
| 5 | `auth_store.py` — role associado ao cliente; `new-device` aceita `--role` | 🔴 Proposta |

## Definition of Done

### Fase 1
- [ ] `ROLE_PERMISSIONS` definido com todos os roles
- [ ] `get_permissions(roles)` retorna permissões corretas para cada role
- [ ] `require_permission` levanta `PermissionError` com mensagem descritiva

### Fase 2
- [ ] `/auth/token`, `/auth/device/activate` sem guarda (públicos com rate limit)
- [ ] `/api/projects/.../runs` requer `project:run`
- [ ] `/api/projects/.../approve` requer `project:approve`
- [ ] `/api/formulario/projeto` requer `project:create`
- [ ] `/api/catalogs/` (escrita) requer `catalog:write`

### Fase 3
- [ ] `TOOL_PERMISSIONS` substitui `SCOPES_REQUIRED` em `scope_guard.py`
- [ ] `aprovar_versao` MCP tool requer `project:approve`
- [ ] `criar_projeto_formulario` requer `project:create`
- [ ] `avancar_pipeline` requer `project:run`

### Fase 4
- [ ] JWT emitido com `roles` em vez de `scopes`
- [ ] Tokens antigos com `scopes` continuam funcionando (mapeamento legado)
- [ ] `startup_check()` valida que `AUTH_CLIENTS` usam roles válidos

### Fase 5
- [ ] `concilium auth add-user` aceita `--role` (default: `operator`)
- [ ] `concilium auth new-device` exibe role no bloco JSON
- [ ] `AGENT_SKILL_TUTORIAL.md` atualizado com tabela de roles

---

## Relacionados

[[adr094-jwt-auth-layer]] [[adr098-rate-limiting-slowapi]]
