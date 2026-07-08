# ADR-098 — Rate Limiting com SlowAPI: Proteção contra DDoS e Uso Abusivo

**Status:** ✅ Implementado
**Data:** 2026-06-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-094 (JWT Auth), ADR-096 (Deploy Azure)

---

## Contexto

### Problema

P1. **Pipeline execution é cara computacionalmente.** Cada execução dispara CP-SAT
scheduling (ortools), min-cost flow matching e até 15 skills encadeadas. Um único
cliente pode forçar execuções contínuas que monopolizam o container ACI, negando
serviço a outros usuários.

P2. **JWT auth (ADR-094) não previne abuso por credenciais válidas.** Um token legítimo
compromissado, um agente LLM em loop ou um engenheiro distraído com retry automático
podem atingir o mesmo efeito que um DDoS externo — sem nenhuma proteção atual.

P3. **O endpoint `/auth/token` está exposto a credential stuffing.** Sem limite de
tentativas, um atacante pode testar pares `client_id`/`secret` em volume sem custo.

P4. **Sem headers de rate-limit, agentes LLM não conseguem back-off adequado.**
Claude Desktop e Copilot precisam de `Retry-After` ou `X-RateLimit-*` para
implementar espera adaptativa — sem isso, loops de retry agravam o problema.

---

## Decisão

D1. **SlowAPI como middleware de rate limiting do FastAPI.**

SlowAPI é um wrapper de `limits` para Starlette/FastAPI. É o padrão de facto para
rate limiting em FastAPI, mínimo de configuração e zero lock-in (o backend de
armazenamento é intercambiável).

```python
# src/concilium/presentation/api/rate_limit.py
from slowapi import Limiter
from slowapi.util import get_remote_address

def _rate_limit_key(request: Request) -> str:
    """Chave de rate limit: JWT sub (por usuário) ou IP como fallback."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from concilium.infrastructure.auth.token_service import decode_token
            payload = decode_token(auth.removeprefix("Bearer "))
            if sub := payload.get("sub"):
                return f"user:{sub}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"

limiter = Limiter(key_func=_rate_limit_key)
```

D2. **Limites diferenciados por grupo de rota.**

| Grupo | Rotas | Limite | Justificativa |
|---|---|---|---|
| Auth | `POST /auth/token` | **5/minute** por IP | Anti-brute-force / credential stuffing |
| Pipeline | `POST .../runs`, `POST .../runs/start`, `POST .../rerun` | **10/minute** por usuário | Cada run custa 2–4 vCPU·s |
| Escrita | `POST /api/**`, `PUT /api/**`, `DELETE /api/**` | **60/minute** por usuário | Proteção moderada |
| Leitura | `GET /api/**` | **120/minute** por usuário | Navegação normal de UI/agente |
| Global | todas as rotas | **200/minute** por usuário | Circuit breaker de último recurso |

> **Nota:** Os limites acima são pontos de partida conservadores, ajustáveis por
> `CONCILIUM__RATE_LIMIT_*` env vars sem redeploy.

D3. **Registro no `create_app()` sem acoplamento às rotas.**

```python
# app.py
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .rate_limit import limiter

def create_app() -> FastAPI:
    ...
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    ...
```

D4. **Headers padrão RFC 6585 em todas as respostas.**

SlowAPI injeta automaticamente:
```
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1748736060
Retry-After: 42          ← presente apenas no 429
```

Agentes LLM e UIs usam `Retry-After` para back-off automático sem polling cego.

D5. **Backend de armazenamento: MemoryStorage para instância única (ACI).**

ACI roda um único container por grupo — sem estado compartilhado a sincronizar.
`MemoryStorage` (padrão do SlowAPI) é suficiente e sem dependência externa.

Quando ACI escalar para múltiplas instâncias (cenário futuro), migrar o backend
para Redis via `CONCILIUM__RATE_LIMIT_STORAGE_URI=redis://...` — o `limits` já
suporta `RedisStorage`, nenhuma mudança de código necessária.

D6. **Rate limiting para MCP tools via decorator próprio.**

O MCP server (FastMCP, porta 8080) não passa pelo SlowAPI do FastAPI. Para
`avancar_pipeline` e outras tools de escrita, um decorator leve com contador
em memória protege o pipeline:

```python
# src/concilium/presentation/mcp_server/rate_limit.py
from collections import defaultdict
from time import monotonic

_counters: dict[str, list[float]] = defaultdict(list)

def mcp_rate_limit(calls: int, period_s: int):
    """Decorator: limita tool MCP a `calls` por `period_s` segundos por chave."""
    def decorator(tool_fn):
        @wraps(tool_fn)
        def wrapper(*args, **kwargs):
            key = kwargs.get("project_id", "global")
            now = monotonic()
            window = _counters[key]
            # Remove entradas fora da janela
            _counters[key] = [t for t in window if now - t < period_s]
            if len(_counters[key]) >= calls:
                raise RuntimeError(
                    f"Rate limit atingido para '{tool_fn.__name__}': "
                    f"máximo {calls} chamadas por {period_s}s por projeto."
                )
            _counters[key].append(now)
            return tool_fn(*args, **kwargs)
        return wrapper
    return decorator
```

Aplicado em `pipeline.py`:
```python
@server.tool()
@mcp_rate_limit(calls=10, period_s=60)
def avancar_pipeline(project_id: str, ...) -> dict:
    ...
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | WAF do Application Gateway (WAF_v2 SKU) | Over-engineered e caro para MVP; Standard_v2 já escolhido em ADR-096 |
| R2 | nginx/Caddy como reverse proxy com rate limit | Adiciona hop desnecessário; ACI não tem sidecar trivial |
| R3 | Middleware customizado do zero | SlowAPI já entrega headers RFC + backends + integração FastAPI pronta |
| R4 | Rate limit somente por IP | Usuarios atrás de NAT corporativo compartilham IP; punição coletiva inaceitável |
| R5 | Sem rate limit no MVP | Inaceitável — pipeline é computacionalmente cara e o serviço é público com ADR-096 |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Proteção de compute | Pipeline execution limitada a 10 req/min por usuário — elimina monopolização de ACI |
| Anti-brute-force | `/auth/token` com 5 req/min por IP — credential stuffing inviável |
| Agentes LLM back-off correto | `Retry-After` header permite espera adaptativa sem polling cego |
| Vendor-agnostic | Backend de storage intercambiável (Memory → Redis) sem mudança de código |
| Observabilidade | 429s capturados pelo OTEL (ADR-095) como `concilium.api.rate_limit.exceeded` |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Falso positivo para agente LLM legítimo em burst | Limites conservadores mas ajustáveis via env vars; `Retry-After` permite recuperação automática |
| Contadores perdidos em restart do container | MemoryStorage é efêmero — janelas resetam; aceitável para MVP |
| MCP rate limit não é thread-safe em alta concorrência | FastMCP roda em asyncio single-thread por default — não há concorrência real; ok para MVP |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | `slowapi` adicionado ao `pyproject.toml` + `Limiter` configurado em `app.py` | 🟢 Implementado |
| 2 | `_rate_limit_key()` extrai JWT sub; limites por grupo de rota em `runs.py` e `auth.py` | 🟢 Implementado |
| 3 | Limites de leitura/escrita genéricos via `SlowAPIMiddleware` (global fallback) | 🟢 Implementado |
| 4 | `mcp_rate_limit` decorator aplicado em `avancar_pipeline` | 🟢 Implementado |
| 5 | Métrica OTEL `concilium.api.rate_limit.exceeded{route, user}` emitida no handler 429 | 🟢 Implementado |

## Definition of Done

### Fase 1
- [ ] `slowapi>=0.1.9` em `pyproject.toml`
- [ ] `limiter` instanciado em `rate_limit.py` com `_rate_limit_key`
- [ ] `app.state.limiter`, exception handler e `SlowAPIMiddleware` registrados em `create_app()`

### Fase 2
- [ ] `POST /auth/token` retorna `429` após 5 tentativas em 60s pelo mesmo IP
- [ ] `POST .../runs` retorna `429` após 10 execuções em 60s pelo mesmo usuário
- [ ] Headers `X-RateLimit-*` e `Retry-After` presentes na resposta `429`

### Fase 3
- [ ] Todas as rotas GET respeitam limite de 120/min por usuário
- [ ] Rotas POST/PUT/DELETE (exceto pipeline) respeitam 60/min por usuário

### Fase 4
- [ ] `avancar_pipeline` via MCP retorna erro descritivo após 10 chamadas/min por projeto
- [ ] Teste unitário cobre o decorator `mcp_rate_limit` com clock mockado

### Fase 5
- [ ] Métrica `concilium.api.rate_limit.exceeded` visível no Azure Monitor após 429

---

## Relacionados

[[adr094-jwt-auth-layer]] [[adr096-deploy-azure-acr-aci-dns]] [[adr095-observabilidade]]
