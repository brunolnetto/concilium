# ADR-094 — Camada de Autenticação JWT para MCP e API

**Status:** Implementado
**Data:** 2026-05-30
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-096 (Deploy Azure)

---

## Contexto

### Problema

P1. Com o MCP server e a API REST expostos publicamente (ADR-096), qualquer cliente
não autenticado pode acionar o pipeline, consumir compute e acessar dados de projetos
de clientes. Não há controle de acesso hoje.

P2. Diferentes consumidores têm diferentes níveis de permissão: um agente LLM pode
precisar apenas ler artefatos, enquanto um engenheiro sênior pode executar pipelines.
Um controle granular por operação é necessário.

P3. Credenciais embutidas em `claude_settings.json` ou variáveis de ambiente são
frágeis e difíceis de revogar individualmente.

---

## Decisão

D1. **JWT como mecanismo único de autenticação.** Todos os requests incluem:

```
Authorization: Bearer <JWT>
```

Claims do JWT:
```json
{
  "sub": "user_id ou service_account_id",
  "org": "mendesloboconstrucao",
  "scopes": ["mcp:read", "mcp:write", "pipeline:run"],
  "exp": 1748736000
}
```

D2. **Validação no Application Gateway — antes do container.** Requests sem token
válido recebem `401 Unauthorized` sem tocar o app. O FastMCP/FastAPI nunca vê
requests não autenticados.

D3. **Scopes por operação.**

```python
SCOPES_REQUIRED = {
    "criar_projeto_formulario":   ["pipeline:run"],
    "avancar_pipeline":           ["pipeline:run"],
    "auditar_plano":              ["mcp:read"],
    "explorar_pool_recursos":     ["mcp:read"],
    "baixar_bundle_zip":          ["mcp:read"],
    "listar_projetos":            ["mcp:read"],
}
```

D4. **Emissão de tokens via `POST /auth/token`** com `{client_id, client_secret}`.
No MVP, endpoint próprio assinado com chave RS256 em Azure Key Vault. Migração
para Azure Active Directory B2C quando houver > 5 usuários ativos.

D5. **Perfis de consumidor e TTL.**
- Claude Desktop / Copilot: token de curta duração (8h), renovado automaticamente
- Engenheiros: token interativo via UI (8h)
- CI/CD e calibração histórica: service account com token de longa duração (90d)

D6. **Chave RS256 no Azure Key Vault via Managed Identity** — sem credenciais
embutidas no container.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | API Key estática | Sem expiração, sem scopes, não revogável individualmente |
| R2 | OAuth2 completo no MVP | Complexidade desproporcional para o estágio atual |
| R3 | mTLS | Difícil de configurar para agentes LLMs que não controlam o TLS client |
| R4 | Sem autenticação no MVP | Inaceitável — serviço público exposto a dados de projetos de clientes |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Acesso granular | Scopes por operação — agente LLM não pode executar pipeline sem permissão |
| Revogação imediata | Token de service account revogado sem afetar outros usuários |
| Chave segura | RS256 em Key Vault; rotação sem redeploy do container |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Fricção adicional no setup de agentes | Documentar `claude_settings.json` com instruções de autenticação |
| Token expirado interrompe fluxo de agente | Agente deve detectar 401 e solicitar novo token antes de re-tentar |
| Gestão de client_secrets para múltiplos agentes | Rotação semestral documentada; Key Vault centraliza |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Azure Key Vault + chave RS256 | ✅ Implementado |
| 2 | `POST /auth/token` endpoint + emissão JWT | ✅ Implementado |
| 3 | TLS termination no Application Gateway (cert Key Vault) | ✅ Implementado |
| 4 | Middleware de scopes no FastMCP (fallback de segurança interno) | ✅ Implementado |
| 5 | Documentação de autenticação para agentes + `claude_settings.json` | 🔴 Pendente |

## Definition of Done

### Fase 1
- [ ] Key Vault provisionado com chave RS256
- [ ] ACI acessa Key Vault via Managed Identity sem credenciais hardcoded
- [x] Seam de carregamento implementado (`CONCILIUM__JWT_PRIVATE_KEY_PEM` / `_PATH`)

### Fase 2
- [x] `POST /auth/token` retorna JWT válido para credenciais corretas
- [x] `401` retornado para credenciais inválidas
- [x] Token inclui scopes corretos por perfil de consumidor
- [x] TTL configurável (8h padrão, até 90d para service accounts)

### Fase 3
- [ ] Application Gateway rejeita requests sem `Authorization: Bearer`
- [ ] Requests com token expirado recebem `401` antes de atingir o container

### Fase 4
- [x] `JWTAuthMiddleware` valida Bearer token em todas as rotas FastAPI
- [x] `scope_guard.check_scope()` verifica scopes por tool MCP
- [x] Tool sem scope adequado retorna `PermissionError` descritivo
- [x] 30 testes unitários verdes

### Fase 5
- [ ] `AGENT_SKILL_TUTORIAL.md` inclui seção de autenticação com exemplo
- [ ] `claude_settings.json` template com configuração de token

## Arquivos Criados

| Arquivo | Descrição |
|---|---|
| `src/concilium/infrastructure/auth/jwt_config.py` | Carregamento RS256 key pair — env/arquivo/ephemeral |
| `src/concilium/infrastructure/auth/client_store.py` | Validação client_id/secret (plaintext + sha256 hash) |
| `src/concilium/infrastructure/auth/token_service.py` | Emissão e decodificação JWT RS256 (PyJWT) |
| `src/concilium/presentation/api/routes/auth.py` | `POST /auth/token` — Fase 2 |
| `src/concilium/presentation/api/middleware/jwt_auth.py` | Middleware FastAPI — Fase 4 fallback |
| `src/concilium/presentation/mcp_server/guards/scope_guard.py` | Guard de scopes para tools MCP |
| `tests/unit/test_adr094_jwt_auth.py` | 30 testes unitários |

---

## Relacionados

[[adr096-deploy-azure-acr-aci-dns]] [[adr095-observabilidade]]
