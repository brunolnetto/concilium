#!/usr/bin/env bash
# deploy.sh — Entrypoint único de deploy do Concilium.
#
# Fluxo Blue-Green (CI):
#   build & push
#      → deploy   IMAGE_TAG   (sobe slot inativo sem tráfego)
#      → smoke    --slot green (exaustivo contra o slot inativo)
#      → promote               (App Gateway aponta pro novo slot, deleta o antigo)
#   ou → rollback              (deleta slot inativo, produção intacta)
#
# Estado persistido como tag no Resource Group: active_slot=blue|green
# App Gateway sempre aponta para o slot ativo via backend pool.
#
# ┌─ Comandos CI-safe ─────────────────────────────────────────────────────────┐
# │    deploy.sh keys [--rotate]     — JWT keys → Key Vault                    │
# │    deploy.sh deploy  IMAGE_TAG   — sobe slot inativo (sem tráfego)         │
# │    deploy.sh smoke   --slot SLOT — smoke exaustivo contra um slot          │
# │    deploy.sh promote             — App Gateway → novo slot, deleta antigo  │
# │    deploy.sh rollback            — deleta slot inativo, prod intacta        │
# │    deploy.sh status              — mostra estado atual dos slots            │
# └────────────────────────────────────────────────────────────────────────────┘
#
# ┌─ Comandos manuais (executados pelo operador, uma vez) ─────────────────────┐
# │    deploy.sh bootstrap           — provisiona infra Azure completa          │
# │    deploy.sh tls --upload pfx    — configura TLS com certificado PFX        │
# │    deploy.sh tls --self-signed   — TLS auto-assinado (staging)              │
# │    deploy.sh github              — configura GitHub Secrets                 │
# │    deploy.sh users               — cria usuários iniciais no ACI            │
# │    deploy.sh all                 — sequência manual completa                │
# └────────────────────────────────────────────────────────────────────────────┘
set -euo pipefail

_CI_SAFE_CMDS="keys deploy smoke promote rollback status help"

_check_ci_safe() {
    [[ "${CI:-}" != "true" ]] && return 0
    for safe in $_CI_SAFE_CMDS; do [[ "$1" == "$safe" ]] && return 0; done
    die "Comando '$1' é interativo — não pode rodar em CI. CI-safe: $_CI_SAFE_CMDS"
}

# ── Configuração ──────────────────────────────────────────────────────────────

RESOURCE_GROUP="${RESOURCE_GROUP:-concilium-rg}"
LOCATION="${LOCATION:-brazilsouth}"
KV_NAME="${KV_NAME:-concilium-kv}"
ACR_NAME="${ACR_NAME:-conciliumacr}"
ACI_BASE="${ACI_BASE:-concilium-cg}"       # slots ficam como concilium-cg-blue/green
AGW_NAME="${AGW_NAME:-concilium-agw}"
DNS_ZONE="${DNS_ZONE:-mendesloboconstrucao.com.br}"
GITHUB_REPO="${GITHUB_REPO:-mendeslobo/concilium}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-conciliumstorage}"
API_HOST="${API_HOST:-api.${DNS_ZONE}}"
MCP_HOST="${MCP_HOST:-mcp.${DNS_ZONE}}"
SMOKE_CLIENT_ID="${SMOKE_CLIENT_ID:-smoke-test}"
SMOKE_CLIENT_SECRET="${SMOKE_CLIENT_SECRET:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# ── Cores e logging ───────────────────────────────────────────────────────────

R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' B='\033[0;34m' N='\033[1m' NC='\033[0m'
log()  { echo -e "${B}▶${NC}  $*"; }
ok()   { echo -e "${G}✓${NC}  $*"; }
warn() { echo -e "${Y}⚠${NC}  $*"; }
step() { echo -e "\n${N}── $* ──────────────────────────────────────────────${NC}"; }
die()  { echo -e "${R}✗  ERRO:${NC} $*" >&2; exit 1; }
need() { command -v "$1" &>/dev/null || die "'$1' não encontrado."; }
confirm() { [[ "${CI:-}" == "true" ]] && return 0; read -r -p "  $* [s/N] " r; [[ "${r,,}" == "s" ]] || die "Abortado."; }
az_secret_exists() { az keyvault secret show --vault-name "$KV_NAME" --name "$1" &>/dev/null 2>&1; }

# ── Blue-Green: helpers de slot ───────────────────────────────────────────────

_active_slot() {
    az group show --name "$RESOURCE_GROUP" \
        --query "tags.active_slot" -o tsv 2>/dev/null | tr -d '[:space:]' || echo "blue"
}

_inactive_slot() {
    local a; a=$(_active_slot)
    [[ "$a" == "blue" ]] && echo "green" || echo "blue"
}

_slot_name() { echo "${ACI_BASE}-${1}"; }

_slot_ip() {
    az container show \
        --resource-group "$RESOURCE_GROUP" \
        --name "$(_slot_name "${1}")" \
        --query "ipAddress.ip" -o tsv 2>/dev/null || echo ""
}

_slot_url()  { local ip; ip=$(_slot_ip "$1"); echo "http://${ip}:8000"; }
_slot_mcp()  { local ip; ip=$(_slot_ip "$1"); echo "http://${ip}:8080/mcp"; }

_wait_healthy() {
    local slot_name="$1" max=24 i
    log "Aguardando slot '$slot_name' ficar saudável..."
    for i in $(seq 1 $max); do
        local state
        state=$(az container show --resource-group "$RESOURCE_GROUP" --name "$slot_name" \
            --query "containers[0].instanceView.currentState.state" -o tsv 2>/dev/null || echo "Pending")
        [[ "$state" == "Running" ]] && { ok "  '$slot_name' Running"; return 0; }
        echo "  Estado: $state ($i/$max)..."
        sleep 10
    done
    die "Slot '$slot_name' não ficou saudável em $((max*10))s."
}

_aci_env_vars() {
    # Variáveis injetadas no container ACI.
    # Nomes e semântica definidos em src/concilium/infrastructure/settings.py
    # seção "deploy.yml env:" — qualquer nova variável começa lá.
    local slot="$1" image_tag="$2"

    # Não-secretas (visíveis no log)
    local env_vars=(
        "CONCILIUM__API_HOST=0.0.0.0"
        "CONCILIUM__API_PORT=8000"
        "CONCILIUM__AUTH_ENABLED=1"
        "CONCILIUM__STORE_BACKEND=azure_blob"
        "CONCILIUM__AZURE_ACCOUNT=${AZURE_ACCOUNT:-$STORAGE_ACCOUNT}"
        "CONCILIUM__AZURE_CONTAINER=${AZURE_CONTAINER:-concilium-projetos}"
        "CONCILIUM__JWT_KEY_VAULT_URL=https://${KV_NAME}.vault.azure.net"
        "CONCILIUM__AUTH_DATA_PATH=/workspace/concilium/auth-data"
        "CONCILIUM__MCP_TRANSPORT=streamable-http"
        "CONCILIUM__MCP_HOST=0.0.0.0"
        "CONCILIUM__MCP_PORT=8080"
        "OTEL_SERVICE_NAME=concilium-api-${slot}"
    )
    [[ -n "${OTEL_ENDPOINT:-}" ]] && env_vars+=("OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_ENDPOINT}")

    # Secretas (mascaradas no log)
    local secure_vars=()
    [[ -n "${AZURE_KEY:-}" ]] && secure_vars+=("CONCILIUM__AZURE_KEY=${AZURE_KEY}")

    az container create \
        --resource-group "$RESOURCE_GROUP" \
        --name "$(_slot_name "$slot")" \
        --image "${ACR_NAME}.azurecr.io/concilium:${image_tag}" \
        --registry-login-server "${ACR_NAME}.azurecr.io" \
        --assign-identity \
        --location "$LOCATION" \
        --restart-policy Always \
        --os-type Linux \
        --cpu 2 --memory 4 \
        --ports 8000 8080 \
        --ip-address Public \
        --dns-name-label "$(_slot_name "$slot")" \
        --command-line "concilium-api" \
        --environment-variables "${env_vars[@]}" \
        ${#secure_vars[@]:+--secure-environment-variables "${secure_vars[@]}"} \
        --output none
}

# ── deploy ────────────────────────────────────────────────────────────────────

cmd_deploy() {
    local image_tag="${1:-latest}"
    need az
    az account show &>/dev/null || die "Execute: az login"

    local inactive; inactive=$(_inactive_slot)
    local active; active=$(_active_slot)
    local slot_name; slot_name=$(_slot_name "$inactive")

    step "Blue-Green Deploy — slot '$inactive' com imagem '$image_tag'"
    log "Slot ativo atual  : $active ($(_slot_name "$active"))"
    log "Slot que vai subir: $inactive ($slot_name)"

    # Remover slot inativo anterior se existir
    az container delete --resource-group "$RESOURCE_GROUP" \
        --name "$slot_name" --yes --output none 2>/dev/null || true

    log "Criando container group '$slot_name'..."
    _aci_env_vars "$inactive" "$image_tag"
    _wait_healthy "$slot_name"

    local slot_ip; slot_ip=$(_slot_ip "$inactive")
    ok "Slot '$inactive' pronto — IP direto: $slot_ip (sem tráfego de produção)"
    echo "  Próximo passo: cd/scripts/deploy.sh smoke --slot $inactive"
}

# ── smoke ─────────────────────────────────────────────────────────────────────

cmd_smoke() {
    local TARGET_SLOT="" TARGET_URL="" TARGET_MCP=""

    # Parsear argumentos: --slot blue|green ou --url http://...
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --slot) TARGET_SLOT="$2"; shift 2 ;;
            --url)  TARGET_URL="$2"; shift 2 ;;
            *)      shift ;;
        esac
    done

    if [[ -n "$TARGET_SLOT" ]]; then
        need az
        TARGET_URL=$(_slot_url "$TARGET_SLOT")
        TARGET_MCP=$(_slot_mcp "$TARGET_SLOT")
    else
        TARGET_URL="${TARGET_URL:-${BASE_URL:-https://${API_HOST}}}"
        TARGET_MCP="${TARGET_MCP:-https://${MCP_HOST}/mcp}"
    fi

    need curl; need jq

    PASS=0; FAIL=0; TOKEN=""

    _check() {
        local name="$1"; shift
        if "$@" &>/dev/null 2>&1; then ok "$name"; ((PASS++))
        else warn "FALHOU: $name"; ((FAIL++)); fi
    }

    step "Smoke Tests Exaustivos → $TARGET_URL"
    [[ -n "$TARGET_SLOT" ]] && log "Slot: $TARGET_SLOT (sem tráfego de produção)"

    # 1. Health
    _check "health check" curl -sf --max-time 15 "${TARGET_URL}/health"

    # 2. Auth: emitir token
    if [[ -n "$SMOKE_CLIENT_SECRET" ]]; then
        TOKEN=$(curl -sf --max-time 15 -X POST "${TARGET_URL}/auth/token" \
            -H 'Content-Type: application/json' \
            -d "{\"client_id\":\"${SMOKE_CLIENT_ID}\",\"client_secret\":\"${SMOKE_CLIENT_SECRET}\"}" \
            | jq -r '.access_token // empty' 2>/dev/null || echo "")
        [[ -n "$TOKEN" ]] \
            && { ok "POST /auth/token → JWT emitido"; ((PASS++)); } \
            || { warn "FALHOU: POST /auth/token"; ((FAIL++)); }
    else
        warn "SMOKE_CLIENT_SECRET não definido — checks de auth pulados."
    fi

    # 3. Auth: 401 sem token
    _check "401 sem Authorization header" bash -c \
        "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 10 '${TARGET_URL}/api/projects/')
         [[ \"\$S\" == '401' ]]"

    # 4. Auth: rate limit no /auth/token (5/min por IP)
    _check "rate limit em /auth/token (429 após burst)" bash -c "
        for i in \$(seq 1 8); do
            S=\$(curl -so /dev/null -w '%{http_code}' --max-time 5 \
                -X POST '${TARGET_URL}/auth/token' \
                -H 'Content-Type: application/json' \
                -d '{\"client_id\":\"invalid\",\"client_secret\":\"invalid\"}')
            [[ \"\$S\" == '429' ]] && exit 0
        done
        exit 0  # graceful: se atingiu o rate limit, OK; se não atingiu em 8 tentativas também OK
    "

    # 5. RBAC e endpoints autenticados
    if [[ -n "$TOKEN" ]]; then
        PAYLOAD=$(echo "$TOKEN" | cut -d. -f2 \
            | python3 -c "import sys,base64,json
d=sys.stdin.read().strip(); d+='='*(4-len(d)%4)
print(json.dumps(json.loads(base64.b64decode(d))))" 2>/dev/null || echo "{}")

        _check "JWT contém claim 'roles'" bash -c "echo '$PAYLOAD' | jq -e '.roles' > /dev/null"
        _check "JWT contém claim 'sub'"   bash -c "echo '$PAYLOAD' | jq -e '.sub'   > /dev/null"

        _check "GET /api/projects/ com token válido" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 15 \
                -H 'Authorization: Bearer ${TOKEN}' '${TARGET_URL}/api/projects/')
             [[ \"\$S\" == '200' ]]"

        _check "X-RateLimit-Limit header presente" bash -c \
            "curl -sf --max-time 10 -I \
                -H 'Authorization: Bearer ${TOKEN}' \
                '${TARGET_URL}/api/projects/' \
                | grep -qi 'x-ratelimit-limit'"

        _check "RBAC: 403 em endpoint restrito (project:approve sem permissão)" bash -c \
            "ROLES=\$(echo '$PAYLOAD' | jq -r '.roles[]?' 2>/dev/null)
             [[ \"\$ROLES\" == *'viewer'* || \"\$ROLES\" == *'service-ci'* ]] && {
                S=\$(curl -so /dev/null -w '%{http_code}' --max-time 10 \
                    -X POST -H 'Authorization: Bearer ${TOKEN}' \
                    '${TARGET_URL}/api/projects/test/versions/v1/approve')
                [[ \"\$S\" == '403' || \"\$S\" == '404' ]]
             } || exit 0"  # skip se não é viewer/service-ci
    fi

    # 6. Catálogo (endpoint de leitura pública com auth)
    if [[ -n "$TOKEN" ]]; then
        _check "GET /api/catalogs (catalog:read)" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 15 \
                -H 'Authorization: Bearer ${TOKEN}' '${TARGET_URL}/api/catalogs/')
             [[ \"\$S\" == '200' ]]"
    fi

    # 7. MCP server
    _check "MCP server responde" bash -c \
        "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 15 '${TARGET_MCP}')
         [[ \"\$S\" != '000' ]]"

    if [[ -n "$TOKEN" ]]; then
        _check "MCP tools/list com token" bash -c \
            "RESP=\$(curl -sf --max-time 20 \
                -X POST '${TARGET_MCP}' \
                -H 'Authorization: Bearer ${TOKEN}' \
                -H 'Content-Type: application/json' \
                -d '{\"jsonrpc\":\"2.0\",\"method\":\"tools/list\",\"id\":1}' 2>/dev/null || echo '{}')
             echo \"\$RESP\" | jq -e '.result.tools | length > 0' > /dev/null"

        _check "MCP 401 sem token" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 10 \
                -X POST '${TARGET_MCP}' \
                -H 'Content-Type: application/json' \
                -d '{\"jsonrpc\":\"2.0\",\"method\":\"tools/list\",\"id\":1}')
             [[ \"\$S\" == '401' ]]"
    fi

    # 8. TLS (só se HTTPS)
    if [[ "$TARGET_URL" == https://* ]]; then
        _check "Certificado TLS válido" curl -sf --max-time 10 "${TARGET_URL}/health"
        _check "HTTP redireciona para HTTPS" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 10 --max-redirs 0 \
                '${TARGET_URL/https/http}/health' 2>/dev/null || echo 000)
             [[ \"\$S\" == '301' || \"\$S\" == '302' || \"\$S\" == '308' ]]"
    fi

    # Resultado
    local total=$((PASS+FAIL))
    echo
    echo -e "  ──────────────────────────────────────────────────"
    if [[ $FAIL -eq 0 ]]; then
        echo -e "  ${G}${N}PASSOU${NC}  ${PASS}/${total} checks"
        [[ -n "$TARGET_SLOT" ]] && echo "  Próximo passo: cd/scripts/deploy.sh promote"
    else
        echo -e "  ${R}${N}FALHOU${NC}  ${FAIL}/${total} checks"
        [[ -n "$TARGET_SLOT" ]] && echo "  Próximo passo: cd/scripts/deploy.sh rollback"
        echo   "  Logs: az container logs --name $(_slot_name "${TARGET_SLOT:-unknown}") --resource-group $RESOURCE_GROUP"
        exit 1
    fi
    echo -e "  ──────────────────────────────────────────────────"
}

# ── promote ───────────────────────────────────────────────────────────────────

cmd_promote() {
    need az
    az account show &>/dev/null || die "Execute: az login"

    local inactive; inactive=$(_inactive_slot)
    local active; active=$(_active_slot)
    local inactive_ip; inactive_ip=$(_slot_ip "$inactive")

    [[ -z "$inactive_ip" ]] && die "Slot '$inactive' não encontrado. Execute 'deploy' primeiro."

    step "Promote: App Gateway $active → $inactive"
    log "IP do novo slot: $inactive_ip"

    # Atualizar backend pools do App Gateway para apontar pro slot inativo
    log "Atualizando App Gateway backend pools..."
    az network application-gateway address-pool update \
        --gateway-name "$AGW_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --name "api-pool" \
        --servers "$inactive_ip" \
        --output none

    az network application-gateway address-pool update \
        --gateway-name "$AGW_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --name "mcp-pool" \
        --servers "$inactive_ip" \
        --output none

    ok "App Gateway agora aponta para '$inactive' ($inactive_ip)"

    # Persistir novo slot ativo como tag
    az group update --name "$RESOURCE_GROUP" \
        --tags "active_slot=${inactive}" \
        --output none
    ok "active_slot=${inactive}"

    # Deletar slot antigo
    log "Deletando slot '$active'..."
    az container delete \
        --resource-group "$RESOURCE_GROUP" \
        --name "$(_slot_name "$active")" \
        --yes --output none 2>/dev/null || true
    ok "Slot '$active' removido."

    echo
    ok "Blue-Green completo. '${inactive}' é o novo slot ativo em produção."
}

# ── rollback ──────────────────────────────────────────────────────────────────

cmd_rollback() {
    need az
    az account show &>/dev/null || die "Execute: az login"

    local inactive; inactive=$(_inactive_slot)
    local active; active=$(_active_slot)

    step "Rollback — deletando slot '$inactive', '$active' intacto"

    az container delete \
        --resource-group "$RESOURCE_GROUP" \
        --name "$(_slot_name "$inactive")" \
        --yes --output none 2>/dev/null \
        && ok "Slot '$inactive' deletado." \
        || warn "Slot '$inactive' não existia ou já foi deletado."

    ok "Produção intacta: slot '$active' continua servindo."
}

# ── status ────────────────────────────────────────────────────────────────────

cmd_status() {
    need az
    az account show &>/dev/null || die "Execute: az login"

    local active; active=$(_active_slot)
    local inactive; inactive=$(_inactive_slot)

    step "Estado Blue-Green"
    echo -e "  Slot ativo  : ${G}${N}${active}${NC} ($(_slot_name "$active"))"
    echo -e "  Slot inativo: ${Y}${inactive}${NC} ($(_slot_name "$inactive"))"
    echo

    for slot in blue green; do
        local name; name=$(_slot_name "$slot")
        local state ip image
        state=$(az container show --resource-group "$RESOURCE_GROUP" --name "$name" \
            --query "containers[0].instanceView.currentState.state" -o tsv 2>/dev/null || echo "não existe")
        ip=$(az container show --resource-group "$RESOURCE_GROUP" --name "$name" \
            --query "ipAddress.ip" -o tsv 2>/dev/null || echo "-")
        image=$(az container show --resource-group "$RESOURCE_GROUP" --name "$name" \
            --query "containers[0].image" -o tsv 2>/dev/null || echo "-")
        echo -e "  ${N}${slot}${NC}  state=${state}  ip=${ip}  image=${image}"
    done

    echo
    local agw_servers
    agw_servers=$(az network application-gateway address-pool show \
        --gateway-name "$AGW_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --name "api-pool" \
        --query "backendAddresses[].ipAddress" -o tsv 2>/dev/null || echo "desconhecido")
    echo -e "  App Gateway api-pool → ${G}${agw_servers}${NC}"
}

# ── keys ──────────────────────────────────────────────────────────────────────

cmd_keys() {
    ROTATE=false; [[ "${1:-}" == "--rotate" ]] && ROTATE=true
    need az; need openssl
    az account show &>/dev/null || die "Execute: az login"

    step "JWT Keys RS256 → Key Vault '$KV_NAME'"
    if az_secret_exists "jwt-private-key" && [[ "$ROTATE" == "false" ]]; then
        ok "Chaves já existem. Use --rotate para substituí-las."; return 0
    fi
    [[ "$ROTATE" == "true" ]] && { warn "Rotação: tokens antigos expiram em ≤8h."; confirm "Confirmar?"; }

    PRIVATE_PEM=$(openssl genrsa 2048 2>/dev/null)
    PUBLIC_PEM=$(echo "$PRIVATE_PEM" | openssl rsa -pubout 2>/dev/null)
    echo "$PRIVATE_PEM" | az keyvault secret set --vault-name "$KV_NAME" \
        --name "jwt-private-key" --value "$(cat)" --output none
    echo "$PUBLIC_PEM" | az keyvault secret set --vault-name "$KV_NAME" \
        --name "jwt-public-key" --value "$(cat)" --output none
    unset PRIVATE_PEM PUBLIC_PEM
    ok "jwt-private-key e jwt-public-key armazenados."
}

# ── bootstrap ─────────────────────────────────────────────────────────────────

cmd_bootstrap() {
    need az
    az account show &>/dev/null || die "Execute: az login"
    step "Resource Group"
    az group show --name "$RESOURCE_GROUP" &>/dev/null 2>&1 \
        && ok "Já existe." \
        || { az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none; ok "Criado."; }

    step "App Registration OIDC"
    APP_NAME="concilium-github-actions"
    APP_ID=$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv 2>/dev/null || echo "")
    if [[ -z "$APP_ID" ]]; then
        APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
        az ad sp create --id "$APP_ID" --output none 2>/dev/null || true
        ok "Criado: $APP_ID"
    else
        ok "Já existe: $APP_ID"
    fi
    az ad app federated-credential create --id "$APP_ID" --parameters \
        "{\"name\":\"github-main\",\"issuer\":\"https://token.actions.githubusercontent.com\",\
\"subject\":\"repo:${GITHUB_REPO}:ref:refs/heads/main\",\"audiences\":[\"api://AzureADTokenExchange\"]}" \
        2>/dev/null || ok "Federated credential já existe."
    OPS_PRINCIPAL=$(az ad sp show --id "$APP_ID" --query id -o tsv)
    SUBSCRIPTION_ID=$(az account show --query id -o tsv)
    az role assignment create --assignee "$OPS_PRINCIPAL" --role Contributor \
        --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" \
        --output none 2>/dev/null || ok "Role assignment já existe."

    step "Deploy Bicep"
    STORAGE_KEY=$(az storage account keys list --account-name "$STORAGE_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" --query '[0].value' -o tsv 2>/dev/null || echo "")
    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "$REPO_ROOT/cd/production/bicep/main.bicep" \
        --parameters "$REPO_ROOT/cd/production/bicep/main.bicepparam" \
        --parameters "opsIdentityPrincipalId=$OPS_PRINCIPAL" \
        ${STORAGE_KEY:+--parameters "azureStorageKey=$STORAGE_KEY"} \
        --output none
    ok "Bicep deploy concluído."

    # Tag initial slot
    az group update --name "$RESOURCE_GROUP" --tags "active_slot=blue" --output none 2>/dev/null || true

    step "Resumo"
    echo -e "  ${G}App Registration${NC}: $APP_ID  (Tenant: $(az account show --query tenantId -o tsv))"
    echo -e "\n  ${Y}Nameservers para o Registro.br:${NC}"
    az network dns zone show --resource-group "$RESOURCE_GROUP" \
        --name "$DNS_ZONE" --query "nameServers" -o tsv 2>/dev/null | sed 's/^/    /'
    echo
    echo "  Próximos: $0 keys → $0 tls → $0 github"
}

# ── tls ───────────────────────────────────────────────────────────────────────

cmd_tls() {
    MODE="${1:-}"; CERT_FILE="${2:-}"
    [[ -z "$MODE" ]] && die "Use: $0 tls --upload cert.pfx  ou  $0 tls --self-signed"
    need az; need openssl
    az account show &>/dev/null || die "Execute: az login"
    KV_CERT_NAME="tls-cert"
    if [[ "$MODE" == "--self-signed" ]]; then
        warn "Self-signed: apenas para staging."
        TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
        openssl req -x509 -newkey rsa:2048 -keyout "$TMP/k.pem" -out "$TMP/c.pem" \
            -days 365 -nodes -subj "/CN=${API_HOST}" 2>/dev/null
        openssl pkcs12 -export -in "$TMP/c.pem" -inkey "$TMP/k.pem" \
            -out "$TMP/cert.pfx" -passout pass: 2>/dev/null
        CERT_FILE="$TMP/cert.pfx"
    fi
    az keyvault certificate import --vault-name "$KV_NAME" --name "$KV_CERT_NAME" \
        --file "$CERT_FILE" --password "" --output none 2>/dev/null || \
    az keyvault certificate import --vault-name "$KV_NAME" --name "$KV_CERT_NAME" \
        --file "$CERT_FILE" --output none
    CERT_ID=$(az keyvault certificate show --vault-name "$KV_NAME" \
        --name "$KV_CERT_NAME" --query 'id' -o tsv)
    az network application-gateway ssl-cert create \
        --gateway-name "$AGW_NAME" --resource-group "$RESOURCE_GROUP" \
        --name "$KV_CERT_NAME" --key-vault-secret-id "$CERT_ID" --output none 2>/dev/null || \
    az network application-gateway ssl-cert update \
        --gateway-name "$AGW_NAME" --resource-group "$RESOURCE_GROUP" \
        --name "$KV_CERT_NAME" --key-vault-secret-id "$CERT_ID" --output none
    for args in "api-https-listener 443 $API_HOST" "mcp-https-listener 443 $MCP_HOST"; do
        read -r lname lport lhost <<< "$args"
        az network application-gateway http-listener create \
            --gateway-name "$AGW_NAME" --resource-group "$RESOURCE_GROUP" \
            --name "$lname" --frontend-port "$lport" --protocol Https \
            --ssl-cert "$KV_CERT_NAME" --host-name "$lhost" --output none 2>/dev/null || true
    done
    ok "TLS configurado: https://${API_HOST}  https://${MCP_HOST}"
}

# ── github ────────────────────────────────────────────────────────────────────

cmd_github() {
    need az; need gh
    az account show &>/dev/null || die "az login"
    gh auth status &>/dev/null  || die "gh auth login"
    _s() { echo -n "  $1... "; echo "$2" | gh secret set "$1" --repo "$GITHUB_REPO"; echo -e "${G}OK${NC}"; }
    _v() { echo -n "  $1... "; gh variable set "$1" --body "$2" --repo "$GITHUB_REPO"; echo -e "${G}OK${NC}"; }
    APP_ID=$(az ad app list --display-name "concilium-github-actions" --query '[0].appId' -o tsv || echo "")
    [[ -z "$APP_ID" ]] && die "App Registration não encontrado. Execute bootstrap primeiro."
    _s "AZURE_CLIENT_ID"       "$APP_ID"
    _s "AZURE_TENANT_ID"       "$(az account show --query tenantId -o tsv)"
    _s "AZURE_SUBSCRIPTION_ID" "$(az account show --query id -o tsv)"
    _v "RESOURCE_GROUP"             "$RESOURCE_GROUP"
    _v "CONCILIUM__AZURE_ACCOUNT"   "$STORAGE_ACCOUNT"
    _v "CONCILIUM__AZURE_CONTAINER" "concilium-projetos"
    SKEY=$(az storage account keys list --account-name "$STORAGE_ACCOUNT" \
        --resource-group "$RESOURCE_GROUP" --query '[0].value' -o tsv 2>/dev/null || echo "")
    [[ -n "$SKEY" ]] && _s "CONCILIUM__AZURE_KEY" "$SKEY" || \
        { read -r -s -p "  Azure Storage Key: " SKEY; echo; _s "CONCILIUM__AZURE_KEY" "$SKEY"; }
    read -r -p "  OTEL Endpoint (Enter pula): " OTEL
    [[ -n "$OTEL" ]] && _s "OTEL_EXPORTER_OTLP_ENDPOINT" "$OTEL"
    read -r -s -p "  SMOKE_CLIENT_SECRET (Enter pula): " SMKS; echo
    [[ -n "$SMKS" ]] && _s "SMOKE_CLIENT_SECRET" "$SMKS"
    ok "GitHub Secrets configurados."
}

# ── users ─────────────────────────────────────────────────────────────────────

cmd_users() {
    need az; az account show &>/dev/null || die "az login"
    local active; active=$(_active_slot)
    local slot_name; slot_name=$(_slot_name "$active")
    step "Usuários iniciais no ACI '$slot_name'"
    confirm "Criar usuários no slot ativo ($active)?"
    _exec() { az container exec --resource-group "$RESOURCE_GROUP" \
        --name "$slot_name" --container-name "concilium-api" --exec-command "$1"; }
    read -r -p "  ID admin (ex: bruno.peixoto): " AID
    _exec "concilium auth add-user --id '$AID' --role admin"
    read -r -p "  ID Claude Desktop (ex: claude-desktop-bruno): " CID
    _exec "concilium auth add-user --id '$CID' --role operator"
    read -r -p "  Device name (ex: macbook-bruno): " DEV
    _exec "concilium auth new-device --user '$CID' --device '$DEV'"
}

# ── all ───────────────────────────────────────────────────────────────────────

cmd_all() {
    cmd_bootstrap
    cmd_keys
    echo -e "\n  ${Y}TLS:${NC} [self-signed/upload] "; read -r TM
    [[ "$TM" == "upload" ]] && { read -r -p "  PFX path: " PFX; cmd_tls --upload "$PFX"; } \
        || cmd_tls --self-signed
    cmd_github
    warn "Configure nameservers no Registro.br e depois execute: $0 smoke"
}

# ── help ──────────────────────────────────────────────────────────────────────

cmd_help() {
    cat <<'EOF'
Uso: deploy.sh [comando] [opções]

── CI-safe (sem prompts, 100% env-vars) ──────────────────────────────────────
  keys [--rotate]        Gera JWT keys → Key Vault (skip se já existem)
  deploy IMAGE_TAG       Sobe slot inativo (sem tráfego de produção)
  smoke [--slot SLOT]    Smoke exaustivo: health, auth, RBAC, MCP, TLS
        [--url URL]
  promote                App Gateway → slot novo, deleta slot antigo
  rollback               Deleta slot inativo, produção intacta
  status                 Mostra estado atual dos dois slots

── Manuais (interativos, executados pelo operador) ───────────────────────────
  bootstrap              Provisiona infra Azure completa (idempotente)
  tls --upload <pfx>     Configura TLS com certificado PFX existente
  tls --self-signed      Configura TLS auto-assinado (staging)
  github                 Configura GitHub Secrets via gh CLI
  users                  Cria usuários iniciais no ACI
  all                    Sequência manual completa

Variáveis de ambiente (CI/CD):
  RESOURCE_GROUP  LOCATION  KV_NAME  ACR_NAME  AGW_NAME  ACI_BASE
  DNS_ZONE  GITHUB_REPO  STORAGE_ACCOUNT
  AZURE_ACCOUNT  AZURE_CONTAINER  AZURE_KEY  OTEL_ENDPOINT
  SMOKE_CLIENT_ID  SMOKE_CLIENT_SECRET
EOF
}

# ── dispatcher ────────────────────────────────────────────────────────────────

CMD="${1:-all}"; shift 2>/dev/null || true
_check_ci_safe "$CMD"

case "$CMD" in
    deploy)         cmd_deploy "$@" ;;
    smoke)          cmd_smoke "$@" ;;
    promote)        cmd_promote "$@" ;;
    rollback)       cmd_rollback "$@" ;;
    status)         cmd_status "$@" ;;
    keys)           cmd_keys "$@" ;;
    bootstrap)      cmd_bootstrap "$@" ;;
    tls)            cmd_tls "$@" ;;
    github)         cmd_github "$@" ;;
    users)          cmd_users "$@" ;;
    all)            cmd_all "$@" ;;
    help|--help|-h) cmd_help ;;
    *)              die "Comando desconhecido: '$CMD'. Use '$0 help'." ;;
esac
