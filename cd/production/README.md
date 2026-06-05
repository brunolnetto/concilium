# Deploy Concilium — Azure (ADR-096)

Topologia: **ACR → ACI → Application Gateway → DNS**

```
GitHub Actions
    │ build + push
    ▼
Azure Container Registry (conciliumacr)
    │ pull via Managed Identity
    ▼
Azure Container Instances (concilium-cg)
    ├── concilium-api  :8000  (FastAPI REST)
    └── concilium-mcp  :8080  (FastMCP streamable-http)
    │
    ▼
Application Gateway (concilium-agw)  ← TLS termination
    │
    ▼
Azure DNS Zone (mendesloboconstrucao.com.br)
    ├── api.mendesloboconstrucao.com.br → A → App Gateway IP
    └── mcp.mendesloboconstrucao.com.br → A → App Gateway IP
```

---

## Pré-requisitos

```bash
az extension add --name containerapp  # se necessário
az login
az account set --subscription <SUBSCRIPTION_ID>

# Criar resource group
az group create --name concilium-rg --location brazilsouth
```

---

## Fase 1 — Build local da imagem

```bash
docker build -t concilium:local .
docker run --rm -e CONCILIUM__API_HOST=0.0.0.0 -p 8000:8000 concilium:local
curl http://localhost:8000/health
```

---

## Fase 2 — ACR e CI/CD

### Setup único (feito uma vez)

```bash
# Criar ACR
az acr create --name conciliumacr --resource-group concilium-rg \
              --sku Basic --admin-enabled false

# Criar Managed Identity
az identity create --name concilium-identity --resource-group concilium-rg

# Atribuir AcrPull à identity
IDENTITY_ID=$(az identity show --name concilium-identity \
  --resource-group concilium-rg --query principalId -o tsv)
ACR_ID=$(az acr show --name conciliumacr --query id -o tsv)
az role assignment create --assignee $IDENTITY_ID \
  --role AcrPull --scope $ACR_ID

# Build e push manual (primeiro push)
az acr build --registry conciliumacr \
             --image concilium:latest \
             --file Dockerfile .
```

### GitHub Actions OIDC (deploy automático)

No repositório GitHub, configure os secrets:
- `AZURE_CLIENT_ID` — Client ID da App Registration com federated credential
- `AZURE_TENANT_ID` — Tenant ID do Azure AD
- `AZURE_SUBSCRIPTION_ID` — Subscription ID
- `JWT_SECRET` — chave RS256 para JWT (ADR-094)
- `CONCILIUM__AZURE_ACCOUNT` — nome da Storage Account
- `CONCILIUM__AZURE_CONTAINER` — nome do blob container
- `CONCILIUM__AZURE_KEY` — Storage Account key (ou usar Managed Identity)
- `OTEL_EXPORTER_OTLP_ENDPOINT` — endpoint Azure Monitor

```bash
# Criar App Registration com federated credential para OIDC
az ad app create --display-name concilium-github-actions
APP_ID=$(az ad app list --display-name concilium-github-actions --query '[0].appId' -o tsv)

# Federated credential para o repositório
az ad app federated-credential create --id $APP_ID --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:mendeslobo/concilium:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

---

## Fase 3 — ACI via Bicep (recomendado)

```bash
az deployment group create \
  --resource-group concilium-rg \
  --template-file deploy/bicep/main.bicep \
  --parameters @deploy/bicep/main.bicepparam \
  --parameters jwtSecret="$(az keyvault secret show --vault-name concilium-kv --name jwt-secret --query value -o tsv)" \
  --parameters azureStorageKey="$(az storage account keys list --account-name conciliumstorage --query '[0].value' -o tsv)"
```

### Verificar saúde

```bash
az container show \
  --resource-group concilium-rg --name concilium-cg \
  --query "{ip: ipAddress.ip, fqdn: ipAddress.fqdn, api: containers[0].instanceView.currentState.state, mcp: containers[1].instanceView.currentState.state}" \
  --output table

curl http://<ACI_IP>:8000/health
```

---

## Fase 4 — TLS com Application Gateway

O template `modules/app-gateway.bicep` cria o gateway sem certificado TLS (só HTTP→HTTPS redirect).
Para ativar HTTPS:

### Opção A: Certificado gerenciado (Key Vault + App Gateway)

```bash
# 1. Criar Key Vault
az keyvault create --name concilium-kv --resource-group concilium-rg \
                   --location brazilsouth --sku standard

# 2. Gerar ou importar certificado PFX
# (ex: Let's Encrypt via Certbot ou certificado da CA)
az keyvault certificate import \
  --vault-name concilium-kv \
  --name tls-cert \
  --file certificate.pfx

# 3. Referenciar no Application Gateway
CERT_ID=$(az keyvault certificate show --vault-name concilium-kv \
  --name tls-cert --query 'id' -o tsv)
az network application-gateway ssl-cert create \
  --gateway-name concilium-agw \
  --resource-group concilium-rg \
  --name tls-cert \
  --key-vault-secret-id $CERT_ID
```

### Adicionar listeners HTTPS (após certificado)

```bash
# Listener API HTTPS
az network application-gateway http-listener create \
  --gateway-name concilium-agw --resource-group concilium-rg \
  --name api-https-listener --frontend-port 443 \
  --ssl-cert tls-cert --host-name api.mendesloboconstrucao.com.br

# Listener MCP HTTPS
az network application-gateway http-listener create \
  --gateway-name concilium-agw --resource-group concilium-rg \
  --name mcp-https-listener --frontend-port 443 \
  --ssl-cert tls-cert --host-name mcp.mendesloboconstrucao.com.br

# Routing rules
az network application-gateway rule create \
  --gateway-name concilium-agw --resource-group concilium-rg \
  --name api-rule --priority 200 --rule-type Basic \
  --http-listener api-https-listener \
  --address-pool api-pool --http-settings api-settings

az network application-gateway rule create \
  --gateway-name concilium-agw --resource-group concilium-rg \
  --name mcp-rule --priority 300 --rule-type Basic \
  --http-listener mcp-https-listener \
  --address-pool mcp-pool --http-settings mcp-settings
```

---

## Fase 5 — DNS Zone

```bash
# Após deploy do Bicep, obtém nameservers gerados pelo Azure
az network dns zone show \
  --resource-group concilium-rg \
  --name mendesloboconstrucao.com.br \
  --query nameServers --output table

# Configure esses NS no Registro.br (ou registrador do domínio mendesloboconstrucao.com.br)
```

---

## Fase 6 — Azure Blob Storage (já implementado)

O adapter `AzureBlobStorage` já existe em `src/concilium/infrastructure/adapters/azure_blob_storage.py`.
Configure as variáveis de ambiente no container:

```bash
CONCILIUM__STORE_BACKEND=azure_blob
CONCILIUM__AZURE_ACCOUNT=conciliumstorage
CONCILIUM__AZURE_CONTAINER=concilium-projetos
CONCILIUM__AZURE_KEY=<storage-account-key>   # ou Managed Identity (sem key)
```

Criar o container blob:
```bash
az storage container create \
  --name concilium-projetos \
  --account-name conciliumstorage \
  --auth-mode login
```

---

## Variáveis de Ambiente — Referência completa

| Variável | Descrição | Exemplo |
|---|---|---|
| `CONCILIUM__API_HOST` | Bind host da API | `0.0.0.0` |
| `CONCILIUM__API_PORT` | Porta da API | `8000` |
| `CONCILIUM__MCP_TRANSPORT` | Transport MCP: `stdio` ou `streamable-http` | `streamable-http` |
| `CONCILIUM__MCP_HOST` | Bind host do MCP HTTP | `0.0.0.0` |
| `CONCILIUM__MCP_PORT` | Porta do MCP HTTP | `8080` |
| `CONCILIUM__STORE_BACKEND` | Backend de storage: `filesystem` ou `azure_blob` | `azure_blob` |
| `CONCILIUM__AZURE_ACCOUNT` | Storage Account name | `conciliumstorage` |
| `CONCILIUM__AZURE_CONTAINER` | Blob container name | `concilium-projetos` |
| `CONCILIUM__AZURE_KEY` | Storage Account key (ou omitir para Managed Identity) | — |
| `JWT_SECRET` | Chave RS256 para JWT (ADR-094) | — |
| `OTEL_SERVICE_NAME` | Nome do serviço no OpenTelemetry (ADR-095) | `concilium-api` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Endpoint OTLP (Azure Monitor) | `https://...` |
| `CONCILIUM__CONFIG_ROOT` | Diretório de configuração (catalogs, perfis…) | `/workspace/concilium/config` |
