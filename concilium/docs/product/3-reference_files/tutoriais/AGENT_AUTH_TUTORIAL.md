# Autenticação para Agentes — Concilium MCP

Este guia cobre como obter e usar um token JWT para acessar o Concilium via MCP ou REST.

---

## 1. Obter um token

```bash
curl -s -X POST https://api.mendesloboconstrucao.com.br/auth/token \
  -H "Content-Type: application/json" \
  -d '{"client_id": "SEU_CLIENT_ID", "client_secret": "SEU_CLIENT_SECRET"}' \
  | jq -r .access_token
```

O token expira em **8 horas** por padrão. Service accounts CI/CD podem solicitar até 90 dias com `"ttl_days": 90`.

---

## 2. Usar o token na API REST

```bash
TOKEN="eyJ..."

# Listar projetos
curl -H "Authorization: Bearer $TOKEN" \
  https://api.mendesloboconstrucao.com.br/api/projects

# Executar pipeline
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"base_version": null}' \
  https://api.mendesloboconstrucao.com.br/api/projects/PROJETO_ID/runs
```

---

## 3. Configurar Claude Desktop (MCP HTTP)

Edite `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "concilium": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/client-http"],
      "env": {
        "MCP_SERVER_URL": "https://mcp.mendesloboconstrucao.com.br/mcp",
        "MCP_AUTH_TOKEN": "Bearer eyJ..."
      }
    }
  }
}
```

> **Nota:** O transport HTTP do MCP usa `streamable-http`. O token deve ser
> incluído como `Authorization: Bearer <token>` em cada request.

---

## 4. Renovação automática (script)

```bash
#!/usr/bin/env bash
# renew-token.sh — salva token renovado em ~/.concilium-token
curl -sf -X POST https://api.mendesloboconstrucao.com.br/auth/token \
  -H "Content-Type: application/json" \
  -d "{\"client_id\": \"${CONCILIUM_CLIENT_ID}\", \
       \"client_secret\": \"${CONCILIUM_CLIENT_SECRET}\"}" \
  | jq -r .access_token > ~/.concilium-token && echo "Token renovado."
```

Agende via `cron` a cada 7 horas:
```
0 */7 * * * /path/to/renew-token.sh
```

---

## 5. Escopos disponíveis

| Scope | Operações permitidas |
|---|---|
| `mcp:read` | Listar projetos, consultar status, baixar artefatos |
| `mcp:write` | Criar projetos, aplicar overrides |
| `pipeline:run` | Executar pipeline, avançar skills |

Os escopos são configurados por `client_id` em `CONCILIUM__AUTH_CLIENTS` (env var do servidor).

---

## 6. Erros comuns

| Status | Causa | Solução |
|---|---|---|
| `401 Unauthorized` | Token ausente, expirado ou inválido | Renovar token |
| `403 Forbidden` | Token válido mas escopo insuficiente | Usar client_id com escopo adequado |
| `429 Too Many Requests` | Rate limit atingido | Aguardar `Retry-After` segundos |
