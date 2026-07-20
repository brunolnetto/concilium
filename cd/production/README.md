# Deploy Concilium — Azure

## O que estamos montando

```
Seu código
    │ git push → GitHub Actions constrói a imagem
    ▼
Azure Container Registry  ← guarda as imagens Docker
    │
    ▼
Azure Container Apps  ← roda a API e o servidor MCP
    │  (TLS automático, blue-green nativo via revisions)
    ▼
Azure DNS  ← aponta api.mendesloboconstrucao.com.br e mcp.mendesloboconstrucao.com.br
```

Componentes de suporte (criados uma única vez):
- **Key Vault** — guarda chaves JWT e a senha SMTP; a aplicação busca em runtime
- **Managed Identity** — permite que o container acesse Key Vault e ACR sem senha em variável
- **SharePoint** — guarda os projetos e artefatos do Concilium (backend de storage padrão)

---

## Parte 1 — Bootstrap (feito uma única vez)

> Execute cada bloco em ordem. Se um recurso já existe, o Azure retorna um aviso mas continua.

### 1.0 Instalar o Azure CLI (`az`)

O `az` é a ferramenta de linha de comando que usamos para criar e gerenciar todos os recursos Azure.

**macOS**
```bash
brew install azure-cli
```

**Windows** (PowerShell como administrador)
```powershell
winget install Microsoft.AzureCLI
# ou baixar o instalador MSI em: https://aka.ms/installazurecliwindows
```

**Linux (Ubuntu/Debian)**
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

Verifique a instalação:
```bash
az version   # deve retornar a versão instalada
```

### 1.1 Pré-requisitos locais

```bash
# A extensão containerapp é preview — a mensagem "in preview" é esperada, não é erro
az extension add --name containerapp
az login                                          # abre o browser para autenticação

# Liste as assinaturas disponíveis para encontrar o Subscription ID
az account list --all --output table
# ⚠️  O Tenant ID (ex: b81668e1-...) NÃO é o Subscription ID.
#     Se a lista vier vazia ou só mostrar "N/A(tenant level account)",
#     a conta não tem assinatura Azure ativa — crie uma em portal.azure.com → Subscriptions → Add.

az account set --subscription <SUBSCRIPTION_ID>  # use o ID da coluna SubscriptionId, não TenantId
az group create --name concilium-rg --location brazilsouth
```

### 1.2 Container Registry

```bash
az acr create --name conciliumacr --resource-group concilium-rg \
              --sku Basic --admin-enabled false
```

### 1.3 Managed Identity (usada pelo container para acessar Key Vault e Storage)

```bash
az identity create --name concilium-identity --resource-group concilium-rg

# Salvar para usar nos passos seguintes
IDENTITY_ID=$(az identity show --name concilium-identity \
  --resource-group concilium-rg --query principalId -o tsv)
IDENTITY_RES=$(az identity show --name concilium-identity \
  --resource-group concilium-rg --query id -o tsv)

# Permissão para puxar imagens do ACR
ACR_ID=$(az acr show --name conciliumacr --query id -o tsv)
az role assignment create --assignee $IDENTITY_ID --role AcrPull --scope $ACR_ID
```

### 1.4 Key Vault + chaves JWT

```bash
az keyvault create --name concilium-kv --resource-group concilium-rg \
                   --location brazilsouth --sku standard

az keyvault set-policy --name concilium-kv \
  --object-id $IDENTITY_ID --secret-permissions get list

# Gerar e guardar as chaves JWT (RSA 2048)
openssl genrsa -out jwt-private.pem 2048
openssl rsa -in jwt-private.pem -pubout -out jwt-public.pem
az keyvault secret set --vault-name concilium-kv --name jwt-private-key --file jwt-private.pem
az keyvault secret set --vault-name concilium-kv --name jwt-public-key  --file jwt-public.pem
rm jwt-private.pem jwt-public.pem   # ← nunca deixar no disco
```

### 1.5 SharePoint — App Registration (storage padrão)

O Concilium usa o SharePoint como backend de storage via Microsoft Graph API.
Precisamos de um App Registration no Azure AD com permissão de leitura/escrita no drive.

**No portal Azure (portal.azure.com):**

1. Vá em **Azure Active Directory → App registrations → New registration**
   - Nome: `concilium-sharepoint`
   - Supported account types: *Accounts in this organizational directory only*
   - Clique em **Register**

2. Na app criada, anote o **Application (client) ID** → será `CONCILIUM__SP_CLIENT_ID`

3. Vá em **API permissions → Add a permission → Microsoft Graph → Application permissions**
   - Adicione: `Files.ReadWrite.All` (ou `Sites.ReadWrite.All` se preferir por site)
   - Clique em **Grant admin consent**

4. Gere um certificado para autenticação (mais seguro que client secret):
   ```bash
   openssl req -x509 -newkey rsa:2048 -keyout sp-key.pem -out sp-cert.pem \
     -days 730 -nodes -subj "/CN=concilium-sharepoint"
   ```
   - Em **Certificates & secrets → Certificates**, faça upload do `sp-cert.pem`
   - Guarde o `sp-key.pem` em local seguro → será montado no container como secret

5. Obtenha o **Drive ID** do SharePoint:
   - Acesse a biblioteca de documentos desejada no SharePoint
   - No browser: `https://graph.microsoft.com/v1.0/sites/<site-id>/drives`
   - Anote o `id` do drive que será usado → será `CONCILIUM__SP_DRIVE_ID`

   Ou via CLI (se tiver o site-id):
   ```bash
   # Requer az cli com permissão de leitura no Graph
   SP_SITE_ID=<tenant>.sharepoint.com,<site-guid>,<web-guid>
   az rest --method get \
     --url "https://graph.microsoft.com/v1.0/sites/$SP_SITE_ID/drives" \
     --query "value[].{name:name, id:id}" -o table
   ```

6. Anote o **Tenant ID**:
   ```bash
   az account show --query tenantId -o tsv   # → CONCILIUM__SP_TENANT_ID
   ```

O certificado (`sp-key.pem`) será montado no container como um secret do ACA no passo 1.7.

### 1.6 Azure Container Apps Environment

```bash
az containerapp env create --name concilium-env \
                            --resource-group concilium-rg \
                            --location brazilsouth
```

### 1.7 Primeiro deploy das Container Apps

Copie o bloco abaixo, preencha os `<...>` e execute:

```bash
# Variáveis comuns aos dois containers
# Preencha os valores entre <...> antes de executar
COMMON_ENV="\
  CONCILIUM__AUTH_ENABLED=1 \
  CONCILIUM__STORE_BACKEND=sharepoint \
  CONCILIUM__SP_TENANT_ID=<tenant-id> \
  CONCILIUM__SP_CLIENT_ID=<app-registration-client-id> \
  CONCILIUM__SP_DRIVE_ID=<sharepoint-drive-id> \
  CONCILIUM__SP_CERT_PATH=/run/secrets/sp-cert.pem \
  CONCILIUM__SP_ROOT_PATH=Concilium/prod \
  CONCILIUM__JWT_KEY_VAULT_URL=https://concilium-kv.vault.azure.net \
  CONCILIUM__NOTIFICATIONS_ENABLED=1 \
  CONCILIUM__SMTP_HOST=<smtp-host> \
  CONCILIUM__SMTP_PORT=587 \
  CONCILIUM__SMTP_USER=<smtp-user> \
  CONCILIUM__SMTP_FROM=concilium@mendesloboconstrucao.com.br \
  OTEL_SERVICE_NAME=concilium"

# API REST
az containerapp create \
  --name concilium-api \
  --resource-group concilium-rg \
  --environment concilium-env \
  --image conciliumacr.azurecr.io/concilium:latest \
  --user-assigned "$IDENTITY_RES" \
  --registry-server conciliumacr.azurecr.io \
  --registry-identity "$IDENTITY_RES" \
  --ingress external \
  --target-port 8000 \
  --min-replicas 1 \
  --max-replicas 1 \
  --env-vars \
    $COMMON_ENV \
    CONCILIUM__API_HOST=0.0.0.0 \
    CONCILIUM__API_PORT=8000 \
    OTEL_SERVICE_NAME=concilium-api

# MCP
az containerapp create \
  --name concilium-mcp \
  --resource-group concilium-rg \
  --environment concilium-env \
  --image conciliumacr.azurecr.io/concilium:latest \
  --user-assigned "$IDENTITY_RES" \
  --registry-server conciliumacr.azurecr.io \
  --registry-identity "$IDENTITY_RES" \
  --ingress external \
  --target-port 8080 \
  --min-replicas 1 \
  --max-replicas 1 \
  --env-vars \
    $COMMON_ENV \
    CONCILIUM__MCP_TRANSPORT=streamable-http \
    CONCILIUM__MCP_HOST=0.0.0.0 \
    CONCILIUM__MCP_PORT=8080 \
    OTEL_SERVICE_NAME=concilium-mcp
```

> **Secrets (certificado SharePoint e SMTP_PASSWORD):** após criar a Container App, adicione os secrets:
> ```bash
> az containerapp secret set --name concilium-api --resource-group concilium-rg \
>   --secrets sp-cert="$(cat sp-key.pem)" smtp-password=<valor>
> ```
> Depois referencie como env vars:
> `CONCILIUM__SP_CERT_PATH=secretref:sp-cert` e `CONCILIUM__SMTP_PASSWORD=secretref:smtp-password`.

### 1.8 DNS

```bash
az network dns zone create --resource-group concilium-rg \
                            --name mendesloboconstrucao.com.br

# Ver os nameservers gerados → configurar no Registro.br
az network dns zone show --resource-group concilium-rg \
  --name mendesloboconstrucao.com.br --query nameServers --output table

# CNAME para cada Container App
API_FQDN=$(az containerapp show --name concilium-api \
  --resource-group concilium-rg --query properties.configuration.ingress.fqdn -o tsv)
MCP_FQDN=$(az containerapp show --name concilium-mcp \
  --resource-group concilium-rg --query properties.configuration.ingress.fqdn -o tsv)

az network dns record-set cname set-record \
  --resource-group concilium-rg --zone-name mendesloboconstrucao.com.br \
  --record-set-name api --cname $API_FQDN

az network dns record-set cname set-record \
  --resource-group concilium-rg --zone-name mendesloboconstrucao.com.br \
  --record-set-name mcp --cname $MCP_FQDN
```

### 1.9 GitHub Actions — OIDC

```bash
az ad app create --display-name concilium-github-actions
APP_ID=$(az ad app list --display-name concilium-github-actions --query '[0].appId' -o tsv)

az ad app federated-credential create --id $APP_ID --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:mendeslobo/concilium:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'
```

Secrets a configurar no repositório GitHub:

| Secret | Valor |
|---|---|
| `AZURE_CLIENT_ID` | `$APP_ID` (do comando acima) |
| `AZURE_TENANT_ID` | `$(az account show --query tenantId -o tsv)` |
| `AZURE_SUBSCRIPTION_ID` | `$(az account show --query id -o tsv)` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | URL do Azure Monitor / Datadog |

---

## Parte 2 — Deploy de rotina (a cada mudança de código)

O GitHub Actions faz isso automaticamente ao fazer push para `main`.
Para fazer manualmente:

```bash
NEW_TAG=$(git rev-parse --short HEAD)

# 1. Construir e publicar imagem
az acr build --registry conciliumacr \
             --image concilium:$NEW_TAG \
             --file Dockerfile .

# 2. Deploy como nova revision inativa (0% tráfego)
for APP in concilium-api concilium-mcp; do
  az containerapp update \
    --name $APP --resource-group concilium-rg \
    --image conciliumacr.azurecr.io/concilium:$NEW_TAG \
    --revision-suffix $NEW_TAG \
    --traffic-weight latest=0
done

# 3. Smoke test na revision inativa
API_REV_FQDN=$(az containerapp revision show \
  --name concilium-api --resource-group concilium-rg \
  --revision concilium-api--$NEW_TAG \
  --query properties.fqdn -o tsv)
curl -f https://$API_REV_FQDN/health

# 4. Promoção: 100% de tráfego para a nova revision
for APP in concilium-api concilium-mcp; do
  az containerapp ingress traffic set \
    --name $APP --resource-group concilium-rg \
    --revision-weight ${APP}--$NEW_TAG=100
done

# Rollback (se necessário): substitua $NEW_TAG por $OLD_TAG no passo 4
```

---

## Parte 3 — Referência de variáveis

Use esta tabela para saber onde configurar cada variável.

| Variável | Onde mora | Preciso configurar? |
|---|---|---|
| `CONCILIUM__STORE_BACKEND` | ACA (não-secret) | Sempre — valor: `sharepoint` |
| `CONCILIUM__SP_TENANT_ID` | ACA (não-secret) | Sempre — Tenant ID do Azure AD |
| `CONCILIUM__SP_CLIENT_ID` | ACA (não-secret) | Sempre — App Registration criado no passo 1.5 |
| `CONCILIUM__SP_DRIVE_ID` | ACA (não-secret) | Sempre — ID do drive SharePoint |
| `CONCILIUM__SP_CERT_PATH` | ACA secret (`sp-cert`) | Sempre — caminho do certificado dentro do container |
| `CONCILIUM__SP_ROOT_PATH` | ACA (não-secret) | Recomendado — ex: `Concilium/prod` |
| `CONCILIUM__AUTH_ENABLED` | ACA (não-secret) | Sempre — valor: `1` |
| `CONCILIUM__JWT_KEY_VAULT_URL` | ACA (não-secret) | Sempre |
| KV secret `jwt-private-key` | Key Vault | Criado no passo 1.4 |
| KV secret `jwt-public-key` | Key Vault | Criado no passo 1.4 |
| `OTEL_SERVICE_NAME` | ACA (não-secret) | Recomendado |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | GH Secret | Recomendado |
| `CONCILIUM__NOTIFICATIONS_ENABLED` | ACA (não-secret) | Se usar email |
| `CONCILIUM__SMTP_HOST` | ACA (não-secret) | Se usar email |
| `CONCILIUM__SMTP_USER` | ACA (não-secret) | Se usar email |
| `CONCILIUM__SMTP_FROM` | ACA (não-secret) | Se usar email |
| `CONCILIUM__SMTP_PASSWORD` | ACA secret (`smtp-password`) | Se usar email |
| `CONCILIUM__SMTP_TIMEOUT_SECONDS` | ACA (não-secret) | Opcional — default 15s; timeout de conexão/comando SMTP |
| `CONCILIUM__CATALOG_DIGEST_ENABLED` | ACA (não-secret) | Opcional — default `0`; liga o digest periódico de rascunhos de catálogo pendentes (ADR-141) |
| `CONCILIUM__CATALOG_DIGEST_INTERVAL_HOURS` | ACA (não-secret) | Opcional — default `24`; só tem efeito com `CATALOG_DIGEST_ENABLED=1` |
| `CONCILIUM__VISIBILITY_DIGEST_ENABLED` | ACA (não-secret) | Opcional — default `0`; liga o digest de "quem me consultou" na visibilidade de usuários (ADR-143) |
| `CONCILIUM__VISIBILITY_DIGEST_INTERVAL_SECONDS` | ACA (não-secret) | Opcional — default `300` (5min); só tem efeito com `VISIBILITY_DIGEST_ENABLED=1` |

**Backend alternativo (Azure Blob):** se precisar usar Azure Blob em vez de SharePoint,
substitua as variáveis `SP_*` por `CONCILIUM__AZURE_ACCOUNT`, `CONCILIUM__AZURE_CONTAINER`
e `CONCILIUM__STORE_BACKEND=azure_blob`. Ver `src/concilium/infrastructure/settings.py`.

---

## Validação rápida

```bash
# A API está respondendo?
curl https://api.mendesloboconstrucao.com.br/health

# Startup check (roda dentro do container):
# startup_check() é chamado automaticamente em cada entry point
# — se algo estiver errado, o container falha antes de aceitar tráfego
```
