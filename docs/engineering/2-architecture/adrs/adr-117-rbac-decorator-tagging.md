# ADR-117 — RBAC por Decorator com Tag Introspectável: Eliminação de TOOL_PERMISSIONS

**Status:** Implementado ✅  
**Data:** 2026-06-20  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-099 (RBAC role↔tool), ADR-116 (Limpeza/governança MCP), ADR-037 (MCP Facade)

---

## Contexto

### Problema

P1. **Mapeamento tool→permissão duplicado e propenso a drift.** `TOOL_PERMISSIONS` é um dict de 65
entradas em `permission_guard.py` mantido à mão, separado do ponto onde a tool é definida. Adicionar
uma tool exige lembrar de editar o dict; esquecer → a tool cai no `_DEFAULT_TOOL_PERMISSION`
silenciosamente (a mesma classe de "dead code / default silencioso" que ADR-110/116 vêm eliminando).

P2. **Dois mecanismos coexistem.** Algumas tools usam `@permission("X")` inline; todas são também
embrulhadas por `patch_mcp_auth_permissions` lendo o dict. Tools com decorator são checadas duas
vezes; tools sem decorator dependem só do dict. A fonte de verdade é ambígua.

P3. **Auditoria role→tools é uma constante, não uma derivação.** A tabela de quem-acessa-o-quê vive
no dict; deveria ser derivável do próprio código (introspecção), não mantida em paralelo.

---

## Decisão

**D1 — `@permission` passa a taguear a função (`_required_permission`).**

```python
def permission(perm: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **k):
            ...  # checagem runtime (inalterada)
        wrapper._required_permission = perm   # tag introspectável
        return wrapper
    return decorator
```

A tag sobrevive a `@wraps` e é legível via `server._tool_manager._tools[name].fn._required_permission`
(verificado empiricamente). Decorator order: `@server.tool()` por cima, `@permission` embaixo.

**D2 — Toda tool MCP declara `@permission` inline (colocação no ponto de definição).**
As ~45 tools sem decorator passam a tê-lo. A permissão fica ao lado da tool, não num dict remoto.

**D3 — `patch_mcp_auth_permissions` lê a tag, não o dict.**
```python
required_perm = getattr(tool.fn, "_required_permission", None)
```
Permanece como defesa em profundidade (cobre o transporte HTTP), mas a fonte da permissão é a tag.

**D4 — Fail-closed: tool sem `@permission` é erro de governança.**
O teste `test_mcp_tool_governance.py` passa a exigir que **toda** `tool.fn` tenha `_required_permission`.
Não há mais fallback silencioso para default — uma tool sem decorator falha o teste (fail-closed),
forçando a decisão de segurança no ponto de definição.

**D5 — `TOOL_PERMISSIONS` é removido; auditoria vira derivação.**
O dict é deletado. A tabela role→tools é reconstruída por introspecção quando necessária
(`build_tool_permission_map(server)` — relatório, não constante mantida).

**D6 — `ROLE_PERMISSIONS` permanece centralizado (fora de escopo).**
A política role→permissões é global, não atributo de tool — continua como constante em
`permission_guard.py`. Decorators não expressam política role-level.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter `TOOL_PERMISSIONS` e só melhorar o teste de cobertura | Não elimina o drift nem a duplicação de mecanismo (P1/P2) |
| A2 | Decorator-only sem `patch` (remover defesa em profundidade) | Perde a checagem no transporte HTTP; o patch lendo a tag é barato |
| A3 | Mover também `ROLE_PERMISSIONS` para decorators | Política role-level não é por-tool; decorator não expressa |
| A4 | Gerar `TOOL_PERMISSIONS` por codegen a partir dos decorators | Mantém um artefato derivado materializado — drift entre gen e fonte; introspecção em runtime é mais simples |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fonte única | Permissão colocada no ponto de definição da tool — zero drift |
| Fail-closed | Tool nova sem decorator falha o teste; segurança não pode ser esquecida |
| −65 linhas | Dict removido; auditoria derivada por introspecção |
| Defesa em profundidade preservada | `patch_mcp_auth_permissions` continua, agora lendo a tag |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| ~45 tools precisam ganhar o decorator | Mecânico; o teste fail-closed garante cobertura total ao final |
| Ordem de decorator incorreta (`@permission` acima de `@server.tool`) | Convenção documentada + tag ausente → teste falha |
| FastMCP re-embrulhar `tool.fn` e perder a tag | `patch_mcp_auth_permissions` já reatribui `tool.fn` — a tag está no callable que o FastMCP guarda (verificado) |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `@permission` tagueia `_required_permission`; `patch_mcp_auth_permissions` lê a tag | ⬜ |
| F2 | Adicionar `@permission(...)` inline às ~45 tools sem decorator | ⬜ |
| F3 | `build_tool_permission_map(server)` (auditoria derivada) + remover `TOOL_PERMISSIONS` | ⬜ |
| F4 | Governança fail-closed: toda tool tem `_required_permission` | ⬜ |

---

## Definition of Done

- [ ] `@permission` seta `_required_permission`; runtime check inalterado
- [ ] `patch_mcp_auth_permissions` resolve permissão pela tag (sem dict)
- [ ] Todas as 52 tools têm `@permission` inline
- [ ] `TOOL_PERMISSIONS` removido; `build_tool_permission_map` deriva a tabela
- [ ] Governança: tool sem tag falha (fail-closed); cobertura 100%
- [ ] `ROLE_PERMISSIONS` intacto
- [ ] Suite verde sem regressão

---

## Relacionados

- ADR-099 — RBAC role↔tool (origem de TOOL_PERMISSIONS)
- ADR-116 — Limpeza/governança MCP (teste de governança estendido aqui)
- ADR-037 — MCP Facade
