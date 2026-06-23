# ADR-118 — Auditoria de Invocações de Ferramentas MCP: ToolInvocation + Contexto de Identidade

**Status:** Implementado ✅  
**Data:** 2026-06-22  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-014 (MCP Tool Runtime — proposta), ADR-095 (OTEL), ADR-099 (RBAC), ADR-117 (decorator tagging), ADR-103 (jobs application layer)

---

## Contexto

### Problema

P1. **Nenhuma rastreabilidade por chamada MCP.** Todas as 52 tools executam sem deixar rastro
estruturado: é impossível responder "quem chamou `iniciar_orcamento` às 14h32?" ou "quais tools
foram invocadas por este usuário hoje?". OTEL registra spans, mas esses não são consultáveis como
dados estruturados de negócio.

P2. **`user_id` e `tenant_id` não propagados.** O middleware JWT extrai `_current_roles` do token,
mas o `sub` (user_id) e `tid` (tenant_id) são descartados. Não há como atribuir uma execução a
um usuário concreto dentro do sistema — bloqueio direto para compliance e multi-tenancy.

P3. **ADR-014 definiu `ToolInvocation` como conceito central — nunca implementado.** A proposta
previa: id, tool_name, input, user_id, tenant_id, status, started_at, finished_at, result, error
como entidade de persistência. O sistema ficou com `JobDTO` (granularidade de pipeline, não de tool)
e sem contexto de identidade.

P4. **Conformidade futura bloqueada.** Sem auditoria por chamada e sem user_id, não é possível:
- implementar quotas por usuário
- gerar relatório de atividade para compliance
- auditar uso por tenant em ambientes multi-tenant
- detectar padrões anômalos de uso

---

## Decisão

### D1 — Introdução de `ToolInvocation` como entidade imutável

Cada chamada MCP que chega a término (sucesso ou falha) gera um `ToolInvocation` gravado no
`ToolInvocationRepository`. O modelo é imutável (frozen dataclass) e orientado à privacidade:

```python
@dataclass(frozen=True)
class ToolInvocation:
    id: str            # "ti-{hex:12}"
    tool_name: str     # nome da função (ex: "iniciar_orcamento")
    input_keys: list[str]   # nomes dos parâmetros — nunca os valores (ADR-095 D5)
    user_id: str | None     # JWT sub
    tenant_id: str | None   # JWT tid / tenant_id
    status: str        # "success" | "failed"
    started_at: str    # ISO 8601 UTC
    finished_at: str   # ISO 8601 UTC
    error_type: str | None  # tipo da exceção (ex: "PermissionError") — nunca a mensagem
```

**Privacidade (consistente com ADR-095 D5):** apenas metadados operacionais são registrados.
Valores de parâmetros, mensagens de erro e quaisquer dados de projeto ficam fora do registro.

---

### D2 — Propagação de identidade via contextvars

Dois novos contextvars adicionados a `permission_guard.py` (junto ao `_current_roles` existente):

```python
_current_user_id:   ContextVar[str | None]  # JWT sub
_current_tenant_id: ContextVar[str | None]  # JWT tid / tenant_id
```

Funções públicas:
- `set_auth_context(user_id, tenant_id) -> tuple[Token, Token]`
- `reset_auth_context(tokens)`
- `get_current_user_id() -> str | None`
- `get_current_tenant_id() -> str | None`

O middleware `McpAuthMiddleware` chama `set_auth_context` após `set_roles`, e reseta no `finally`.
Para o transporte stdio (sem HTTP), os contextvars ficam `None` — comportamento seguro e explícito.

---

### D3 — Audit patcher na camada de apresentação

`patch_fastmcp_server_with_audit(server)` em `presentation/mcp/audit.py` envolve `tool.fn` de cada
tool registrada com `_with_audit()`. Posição no pipeline de patches de `build_server()`:

```
patch_fastmcp_server(server)           # OTEL tracing        (ADR-095)
patch_mcp_auth_permissions(server)     # RBAC enforcement    (ADR-099)
patch_fastmcp_server_with_audit(server) # Audit log          (ADR-118)  ← este
validate_tool_coverage(server)
_patch_mcp_with_auth(server)
```

Posicionado após RBAC: falhas de autorização (`PermissionError`) são capturadas com
`error_type="PermissionError"` e `status="failed"` — úteis para auditoria de segurança.

---

### D4 — Repository com buffer circular em memória

Padrão idêntico ao `JobRepository` (ADR-103): interface ABC + implementação `InMemoryToolInvocationRepository`.

```python
class ToolInvocationRepository(ABC):
    def append(invocation: ToolInvocation) -> None
    def list_recent(limit: int = 100) -> list[ToolInvocation]
    def list_by_tool(tool_name: str, limit: int = 100) -> list[ToolInvocation]
    def list_by_user(user_id: str, limit: int = 100) -> list[ToolInvocation]
    def count() -> int
```

A implementação em memória usa `collections.deque(maxlen=N)` — buffer circular thread-safe.
Tamanho configurável via `CONCILIUM__TOOL_INVOCATIONS_MAX_SIZE` (padrão: 10000).

**Tradeoff intencional:** dados são perdidos ao reiniciar o servidor. Esta é a mesma escolha
do `JobRepository`. A interface ABC permite substituição futura por backend persistente (NDJSON,
SQLite, etc.) sem alterar a camada de aplicação.

---

### D5 — Best-effort: falhas na auditoria nunca afetam a tool

Tanto `_with_audit` quanto `_record` são envolvidos em `try/except` sem re-raise. Uma falha no
repositório de auditoria jamais interrompe a execução de uma tool — auditabilidade é secundária
à disponibilidade do serviço.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Registrar no OTEL (spans) em vez de repositório estruturado | Spans têm restrições de privacidade (ADR-095 D5), não são consultáveis como dados de negócio, e têm custo de exportação |
| A2 | Gravar o input completo (não só as chaves) | Viola ADR-095 D5 — parâmetros de tools incluem dados sensíveis de projeto |
| A3 | Implementar persistência em arquivo (NDJSON) desde o início | Over-engineering para MVP; InMemory é suficiente enquanto o volume não justifica persistência durável |
| A4 | Registrar dentro do `_with_tracing` (telemetria) | Mistura responsabilidades — telemetria não deve gerenciar dados de auditoria de negócio |
| A5 | Registrar dentro do `@permission` (RBAC) | RBAC não deve ter dependência em repositório de auditoria; acoplamento errado de camadas |
| A6 | Criar nova camada de middleware ASGI | Middleware ASGI não tem acesso fácil ao nome da tool — o patcher em `tool.fn` tem acesso direto via `tool_fn.__name__` |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Rastreabilidade completa | Toda chamada MCP é registrada com who/what/when/outcome |
| Base para compliance | user_id disponível viabiliza relatórios de atividade e quotas por usuário |
| Fundação multi-tenant | tenant_id propagado habilita isolamento e segmentação por cliente |
| Auditoria de segurança | PermissionError capturado com status="failed" visível no repositório |
| Zero impacto de disponibilidade | Falhas na auditoria são silenciosas (best-effort) |
| Extensível sem mudança de interface | Backend persistente pode substituir InMemory via `reset_tool_invocation_repository` |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Dados perdidos ao reiniciar | InMemory é suficiente para volume atual; ADR futura pode adicionar NDJSON/SQLite |
| Buffer circular descarta entradas antigas | Tamanho padrão 10k cobre >24h com carga típica; ajustável via env var |
| Overhead por chamada de tool | Mínimo: datetime.now + deque.append + contextvar.get — submicrossegundo |
| FastMCP mudar API interna (`_tool_manager._tools`) | Mesmo risco que `patch_fastmcp_server` (ADR-095) — ambos envolvidos em try/except |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `ToolInvocation` model + `ToolInvocationRepository` + InMemory impl | ✅ Implementado |
| F2 | `_current_user_id` / `_current_tenant_id` em `permission_guard.py` | ✅ Implementado |
| F3 | Middleware: `set_auth_context` após `set_roles` | ✅ Implementado |
| F4 | `audit.py`: `patch_fastmcp_server_with_audit` + `_with_audit` | ✅ Implementado |
| F5 | `server.py`: registrar audit patcher no pipeline | ✅ Implementado |
| F6 | Testes unitários: repository, model, audit patcher | ✅ Implementado |
| F7 | Backend NDJSON persistente via BlobStoragePort | ✅ Implementado |
| F8 | Tool MCP de consulta ao audit log (ex: `listar_invocacoes`) | 🔴 Futuro |

---

## Definition of Done

- [x] `ToolInvocation` como frozen dataclass com `to_dict` / `from_dict`
- [x] `ToolInvocationRepository` ABC + `InMemoryToolInvocationRepository` (deque circular)
- [x] `get_tool_invocation_repository()` singleton + `reset_tool_invocation_repository()` para testes
- [x] `CONCILIUM__TOOL_INVOCATIONS_MAX_SIZE` configurável via env
- [x] `_current_user_id` e `_current_tenant_id` contextvars em `permission_guard.py`
- [x] `set_auth_context` / `reset_auth_context` / `get_current_user_id` / `get_current_tenant_id`
- [x] `McpAuthMiddleware` propaga user_id e tenant_id + reseta no finally
- [x] `patch_fastmcp_server_with_audit` em `presentation/mcp/audit.py`
- [x] `audit.py`: privacidade (input_keys, não valores; error_type, não mensagem)
- [x] `audit.py`: best-effort — falha de auditoria nunca propaga exceção
- [x] `server.py`: `patch_fastmcp_server_with_audit` após `patch_mcp_auth_permissions`
- [x] Testes unitários cobrindo model, repository e patcher
- [x] `BlobToolInvocationRepository` em `infrastructure/storage/tool_invocation_store.py`
- [x] `get_tool_invocation_store()` em `store_factory.py`
- [x] `build_server()` instancia e registra o repositório blob via `reset_tool_invocation_repository`
- [x] Testes do store blob (15 casos: NDJSON, filtros, thread safety, round-trip, linha corrompida)
- [ ] Tool MCP de consulta ao audit log (fase futura)

---

## Relacionados

- ADR-014 — MCP Tool Runtime: Plataforma de Execução de Ferramentas (proposta original que define ToolInvocation)
- ADR-095 — OpenTelemetry (privacidade D5: sem dados de projeto em telemetria)
- ADR-099 — RBAC Roles e Permissões (fonte de `_current_roles`)
- ADR-117 — RBAC por Decorator com Tag Introspectável
- ADR-103 — Jobs na Camada de Aplicação (padrão Port/Repository seguido aqui)
