# Checklist de Variáveis de Ambiente — Produção

> Fonte canônica: `src/concilium/infrastructure/settings.py`  
> Validação automática: chame `startup_check()` em cada entry point antes de aceitar tráfego.

**Legenda:**
- `[req]` — obrigatória; `startup_check()` falha se ausente
- `[cond]` — obrigatória apenas quando uma escolha específica é feita (ex: backend=azure_blob)
- `[opt]` — tem default sensato; funciona sem configurar
- `[cloud]` — URL de um serviço externo que entrega o segredo em runtime (Key Vault)

---

## 🔴 Obrigatórias para qualquer deploy em produção

```bash
# Storage — obrigatório se STORE_BACKEND=azure_blob (padrão de produção)
CONCILIUM__STORE_BACKEND=azure_blob
CONCILIUM__AZURE_ACCOUNT=<nome-da-conta>          # [cond] obrigatório se azure_blob
CONCILIUM__AZURE_CONTAINER=<nome-do-container>    # [req] sempre obrigatório se azure_blob

# Autenticação — obrigatório se AUTH_ENABLED=1
CONCILIUM__AUTH_ENABLED=1
CONCILIUM__JWT_KEY_VAULT_URL=https://<vault>.vault.azure.net   # [cloud] produção

# Telemetria
OTEL_SERVICE_NAME=concilium-api
OTEL_EXPORTER_OTLP_ENDPOINT=https://<endpoint-otel>           # Azure Monitor / Datadog
```

---

## 🟡 Obrigatórias por escolha de backend

### Azure Blob Storage (padrão de produção)

```bash
CONCILIUM__STORE_BACKEND=azure_blob
CONCILIUM__AZURE_ACCOUNT=<storage-account>
CONCILIUM__AZURE_CONTAINER=concilium-prod
# Autenticação: escolher UM dos seguintes:
CONCILIUM__AZURE_KEY=<access-key>            # simples, não recomendado prod
# OU Managed Identity (sem variável — configurar no ACI)
# OU CONCILIUM__AZURE_CONNECTION_STRING=...
CONCILIUM__AZURE_ROOT_PREFIX=v1              # [opt] isola versões no container
```

### AWS S3

```bash
CONCILIUM__STORE_BACKEND=s3
CONCILIUM__S3_BUCKET=<bucket>
CONCILIUM__S3_REGION=sa-east-1              # [opt] default: us-east-1
CONCILIUM__S3_SERVER_SIDE_ENCRYPTION=aws:kms  # [opt] recomendado prod
# Autenticação: IAM Role (sem variável) ou:
CONCILIUM__S3_ACCESS_KEY_ID=<key-id>
CONCILIUM__S3_SECRET_ACCESS_KEY=<secret>
```

### SharePoint

```bash
CONCILIUM__STORE_BACKEND=sharepoint
CONCILIUM__SP_TENANT_ID=<tenant>
CONCILIUM__SP_CLIENT_ID=<app-id>
CONCILIUM__SP_DRIVE_ID=<drive-id>
CONCILIUM__SP_CERT_PATH=/run/secrets/sp-cert.pem  # [cond] preferido em prod
# OU CONCILIUM__SP_CLIENT_SECRET=<secret>           # dev apenas
CONCILIUM__SP_ROOT_PATH=Concilium/prod             # [opt] default: Concilium/prod
```

---

## 🟢 Configurações recomendadas para produção (têm defaults mas devem ser explicitadas)

```bash
# API
CONCILIUM__API_HOST=0.0.0.0
CONCILIUM__API_PORT=8000

# MCP Server
CONCILIUM__MCP_TRANSPORT=streamable-http
CONCILIUM__MCP_HOST=0.0.0.0
CONCILIUM__MCP_PORT=8080
CONCILIUM__MCP_RATE_LIMIT_CALLS=10         # default: 10 calls/60s por IP

# Rate limiting distribuído (default: memory:// — não funciona com múltiplos containers)
CONCILIUM__RATE_LIMIT_STORAGE_URI=redis://redis:6379/0   # obrigatório para múltiplas instâncias

# Runtime
CONCILIUM__PDF_RENDERER=reportlab          # default; alternativa: fpdf2
CONCILIUM__DUCKDB_MEMORY=2048MB            # default: 512MB — aumentar para análises grandes
CONCILIUM__DUCKDB_SPILL_DIR=/tmp/duckdb    # garantir espaço em disco

# Jobs assíncronos
CONCILIUM__MAX_CONCURRENT_JOBS=3           # ajustar por capacidade do ACI
CONCILIUM__JOB_TTL_HOURS=24

# Campanha GO (se usado em produção)
CONCILIUM__CAMPAIGN_MAX_WORKERS=4          # default: 6; ajustar por CPU disponível
```

---

## 🔵 Configurações condicionais de Auth JWT

```bash
# Produção: Azure Key Vault (recomendado — zero segredo em variável)
CONCILIUM__JWT_KEY_VAULT_URL=https://concilium-kv.vault.azure.net
# → keys jwt-private-key e jwt-public-key buscadas em runtime via Managed Identity

# Desenvolvimento local: PEM inline
CONCILIUM__AUTH_ENABLED=1
CONCILIUM__JWT_PRIVATE_KEY_PEM=-----BEGIN RSA PRIVATE KEY-----\n...
CONCILIUM__JWT_PUBLIC_KEY_PEM=-----BEGIN PUBLIC KEY-----\n...
CONCILIUM__AUTH_CLIENTS=[{"client_id":"dev","client_secret":"dev123","roles":["operator"]}]

# Desenvolvimento local: PEM em arquivo
CONCILIUM__JWT_PRIVATE_KEY_PATH=/run/secrets/jwt-private.pem
CONCILIUM__JWT_PUBLIC_KEY_PATH=/run/secrets/jwt-public.pem
```

---

## Templates por ambiente

### `cd/development/.env.api`
```bash
CONCILIUM__API_HOST=0.0.0.0
CONCILIUM__API_PORT=8000
CONCILIUM__API_RELOAD=1
CONCILIUM__STORE_BACKEND=filesystem
CONCILIUM__AUTH_ENABLED=0
OTEL_SDK_DISABLED=true
```

### `.github/workflows/deploy.yml` — env: (não-secretas)
```bash
CONCILIUM__API_HOST=0.0.0.0
CONCILIUM__API_PORT=8000
CONCILIUM__MCP_TRANSPORT=streamable-http
CONCILIUM__MCP_HOST=0.0.0.0
CONCILIUM__MCP_PORT=8080
CONCILIUM__STORE_BACKEND=azure_blob
CONCILIUM__AUTH_ENABLED=1
CONCILIUM__JWT_KEY_VAULT_URL=https://concilium-kv.vault.azure.net
OTEL_SERVICE_NAME=concilium-api
OTEL_EXPORTER_OTLP_ENDPOINT=${{ secrets.OTEL_ENDPOINT }}
```

### `.github/workflows/deploy.yml` — GitHub Secrets (secretas, mascaradas no log)
```
CONCILIUM__AZURE_ACCOUNT       → secrets.CONCILIUM__AZURE_ACCOUNT
CONCILIUM__AZURE_CONTAINER     → secrets.CONCILIUM__AZURE_CONTAINER
CONCILIUM__AZURE_KEY           → secrets.CONCILIUM__AZURE_KEY
OTEL_EXPORTER_OTLP_ENDPOINT    → secrets.OTEL_EXPORTER_OTLP_ENDPOINT
```

> **Nota:** Em produção com Managed Identity, `CONCILIUM__AZURE_KEY` não é necessária.
> O ACI autentica diretamente no Azure Storage sem credencial explícita.

---

## ⚠️ Variáveis que causam falha silenciosa se erradas

| Variável | Sintoma se errada | Diagnóstico |
|---|---|---|
| `CONCILIUM__AZURE_CONTAINER` errado | `BlobServiceError` na primeira leitura | `startup_check()` valida conexão |
| `OTEL_EXPORTER_OTLP_ENDPOINT` inacessível | Logs não chegam ao Azure Monitor; silencioso | Verificar `BatchLogRecordProcessor` warnings |
| `CONCILIUM__RATE_LIMIT_STORAGE_URI=memory://` em multi-instance | Rate limit não funciona entre instâncias | Usar Redis |
| `CONCILIUM__JWT_KEY_VAULT_URL` sem Managed Identity | `401` em todos os requests autenticados | Verificar IAM do ACI |
| `CONCILIUM__DUCKDB_SPILL_DIR` sem espaço | `DuckDB out of memory` em análises grandes | Monitorar `/tmp` |

---

## Variáveis OTel (SDK padrão — não têm prefixo CONCILIUM__)

```bash
OTEL_SDK_DISABLED=false               # default; true em dev/CI
OTEL_SERVICE_NAME=concilium-api       # obrigatório para filtros no Azure Monitor
OTEL_EXPORTER_OTLP_ENDPOINT=https://… # habilita exporter OTLP; vazio = sem telemetria
```

---

## Validação de startup

```python
# Em cada entry point (app.py, server.py, main.py):
from concilium.infrastructure.settings import startup_check
startup_check()   # falha com lista completa de problemas antes de aceitar tráfego
```

`startup_check()` valida conexões com Azure/S3/SharePoint, presença de JWT keys
quando `AUTH_ENABLED=1`, e incompatibilidades entre variáveis.
