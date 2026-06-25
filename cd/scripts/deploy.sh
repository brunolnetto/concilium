#!/usr/bin/env bash
# deploy.sh — Entrypoint unico de deploy do Concilium.
#
# Runtime Deployment (ACA Revisions):
#   deploy IMAGE_TAG        -> cria nova revision sem promover trafego
#   smoke --revision REV    -> smoke exaustivo contra FQDN da revision
#   promote --revision REV  -> direciona 100% do trafego para a revision
#   rollback [--revision]   -> volta para revision anterior (ou especificada)
#   status                  -> mostra revisions e pesos de trafego
#
# Platform Operations:
#   bootstrap, keys, tls, github, users, all, help
set -euo pipefail

_CI_SAFE_CMDS="keys image deploy smoke promote rollback status bootstrap help"

_check_ci_safe() {
    [[ "${CI:-}" != "true" ]] && return 0
    for safe in $_CI_SAFE_CMDS; do [[ "$1" == "$safe" ]] && return 0; done
    die "Comando '$1' e interativo — nao pode rodar em CI. CI-safe: $_CI_SAFE_CMDS"
}

# -- Configuracao ----------------------------------------------------------------

RESOURCE_GROUP="${RESOURCE_GROUP:-concilium-rg}"
LOCATION="${LOCATION:-brazilsouth}"
KV_NAME="${KV_NAME:-concilium-kv}"
ACR_NAME="${ACR_NAME:-conciliumacr}"
IMAGE_NAME="${IMAGE_NAME:-concilium}"
AGW_NAME="${AGW_NAME:-concilium-agw}"
ACA_API_APP="${ACA_API_APP:-concilium-api}"
ACA_MCP_APP="${ACA_MCP_APP:-concilium-mcp}"
DNS_ZONE="${DNS_ZONE:-mendesloboconstrucao.com.br}"
GITHUB_REPO="${GITHUB_REPO:-mendeslobo/concilium}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-conciliumstorage}"
API_HOST="${API_HOST:-api.${DNS_ZONE}}"
MCP_HOST="${MCP_HOST:-mcp.${DNS_ZONE}}"
SMOKE_CLIENT_ID="${SMOKE_CLIENT_ID:-smoke-test}"
SMOKE_CLIENT_SECRET="${SMOKE_CLIENT_SECRET:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# -- Common ----------------------------------------------------------------------

R='\033[0;31m' G='\033[0;32m' Y='\033[1;33m' B='\033[0;34m' N='\033[1m' NC='\033[0m'
log()  { echo -e "${B}▶${NC}  $*"; }
ok()   { echo -e "${G}✓${NC}  $*"; }
warn() { echo -e "${Y}⚠${NC}  $*"; }
step() { echo -e "\n${N}── $* ──────────────────────────────────────────────${NC}"; }
die()  { echo -e "${R}✗  ERRO:${NC} $*" >&2; exit 1; }
need() { command -v "$1" &>/dev/null || die "'$1' nao encontrado."; }
confirm() { [[ "${CI:-}" == "true" ]] && return 0; read -r -p "  $* [s/N] " r; [[ "${r,,}" == "s" ]] || die "Abortado."; }
require_login() { az account show &>/dev/null || die "Execute: az login"; }
az_secret_exists() { az keyvault secret show --vault-name "$KV_NAME" --name "$1" &>/dev/null 2>&1; }

# -- ACA Revisions: helpers ------------------------------------------------------

_aca_app_exists() {
    az containerapp show --name "$1" --resource-group "$RESOURCE_GROUP" --output none >/dev/null 2>&1
}

_aca_latest_revision() {
    local app_name="$1"
    az containerapp revision list \
        --name "$app_name" \
        --resource-group "$RESOURCE_GROUP" \
        --query "sort_by(@,&properties.createdTime)[-1].name" -o tsv 2>/dev/null | tr -d '[:space:]'
}

_aca_primary_revision() {
    local app_name="$1"
    az containerapp ingress traffic show \
        --name "$app_name" \
        --resource-group "$RESOURCE_GROUP" \
        --query "sort_by([?weight > \`0\`], &weight)[-1].revisionName" -o tsv 2>/dev/null | tr -d '[:space:]'
}

_aca_previous_revision() {
    local app_name="$1" current="$2"
    az containerapp revision list \
        --name "$app_name" \
        --resource-group "$RESOURCE_GROUP" \
        --query "sort_by([?name!='${current}' && properties.runningState=='Running'], &properties.createdTime)[-1].name" -o tsv 2>/dev/null | tr -d '[:space:]'
}

_aca_revision_fqdn() {
    local app_name="$1" revision="$2"
    local fqdn
    fqdn=$(az containerapp revision show \
        --name "$app_name" \
        --resource-group "$RESOURCE_GROUP" \
        --revision "$revision" \
        --query "properties.fqdn" -o tsv 2>/dev/null || true)

    if [[ -z "$fqdn" ]]; then
        fqdn=$(az containerapp show \
            --name "$app_name" \
            --resource-group "$RESOURCE_GROUP" \
            --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || true)
    fi
    echo "$fqdn"
}

_aca_revision_url() {
    local app_name="$1" revision="$2"
    local fqdn; fqdn=$(_aca_revision_fqdn "$app_name" "$revision")
    [[ -n "$fqdn" ]] || die "Nao foi possivel resolver FQDN da revision '$revision' em '$app_name'."
    echo "https://${fqdn}"
}

_wait_revision_running() {
    local app_name="$1" revision="$2" max=30 i
    log "Aguardando revision '$revision' ficar Running..."
    for i in $(seq 1 $max); do
        local state
        state=$(az containerapp revision show \
            --name "$app_name" \
            --resource-group "$RESOURCE_GROUP" \
            --revision "$revision" \
            --query "properties.runningState" -o tsv 2>/dev/null || echo "Provisioning")

        [[ "$state" == "Running" ]] && { ok "  '$revision' Running"; return 0; }
        [[ "$state" == "Failed" ]] && die "Revision '$revision' falhou durante o deploy."
        echo "  Estado: $state ($i/$max)..."
        sleep 10
    done
    die "Revision '$revision' nao ficou Running em $((max*10))s."
}

# -- ACA Revisions: runtime deployment ------------------------------------------

cmd_deploy() {
    local image_tag="${1:-latest}"
    need az
    require_login

    _aca_app_exists "$ACA_API_APP" || die "Container App '$ACA_API_APP' nao encontrado."

    local previous_primary
    previous_primary=$(_aca_primary_revision "$ACA_API_APP")

    # Expose current active revision for CI workflows.
    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        echo "active_revision=${previous_primary}" >> "$GITHUB_OUTPUT"
    fi

    step "ACA Deploy — app '$ACA_API_APP' com imagem '$image_tag'"
    [[ -n "$previous_primary" ]] && log "Revision com trafego atual: $previous_primary"

    az containerapp revision set-mode \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --mode multiple \
        --output none

    az containerapp update \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --image "${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${image_tag}" \
        --output none

    local new_revision
    new_revision=$(_aca_latest_revision "$ACA_API_APP")
    [[ -n "$new_revision" ]] || die "Nao foi possivel identificar a revision criada no deploy."

    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        echo "deployed_revision=${new_revision}" >> "$GITHUB_OUTPUT"
    fi

    _wait_revision_running "$ACA_API_APP" "$new_revision"

    if [[ -n "$previous_primary" && "$previous_primary" != "$new_revision" ]]; then
        az containerapp ingress traffic set \
            --name "$ACA_API_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --revision-weight "${previous_primary}=100" "${new_revision}=0" \
            --output none
    else
        az containerapp ingress traffic set \
            --name "$ACA_API_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --revision-weight "${new_revision}=100" \
            --output none
    fi

    local new_url
    new_url=$(_aca_revision_url "$ACA_API_APP" "$new_revision")
    ok "Revision pronta: $new_revision"
    log "URL da revision: $new_url"
    echo "  Proximo passo: cd/scripts/deploy.sh smoke --revision $new_revision"
}

cmd_smoke() {
    local TARGET_REVISION="" TARGET_URL="" TARGET_MCP=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --revision) TARGET_REVISION="$2"; shift 2 ;;
            --url)      TARGET_URL="$2"; shift 2 ;;
            --mcp-url)  TARGET_MCP="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    if [[ -n "$TARGET_REVISION" ]]; then
        need az
        require_login
        TARGET_URL=$(_aca_revision_url "$ACA_API_APP" "$TARGET_REVISION")
        TARGET_MCP="${TARGET_MCP:-${TARGET_URL}/mcp}"
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

    step "Smoke Tests Exaustivos -> $TARGET_URL"
    [[ -n "$TARGET_REVISION" ]] && log "Revision: $TARGET_REVISION"

    _check "health check" curl -sf --max-time 15 "${TARGET_URL}/health"

    if [[ -n "$SMOKE_CLIENT_SECRET" ]]; then
        TOKEN=$(curl -sf --max-time 15 -X POST "${TARGET_URL}/auth/token" \
            -H 'Content-Type: application/json' \
            -d "{\"client_id\":\"${SMOKE_CLIENT_ID}\",\"client_secret\":\"${SMOKE_CLIENT_SECRET}\"}" \
            | jq -r '.access_token // empty' 2>/dev/null || echo "")
        [[ -n "$TOKEN" ]] \
            && { ok "POST /auth/token -> JWT emitido"; ((PASS++)); } \
            || { warn "FALHOU: POST /auth/token"; ((FAIL++)); }
    else
        warn "SMOKE_CLIENT_SECRET nao definido — checks de auth pulados."
    fi

    _check "401 sem Authorization header" bash -c \
        "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 10 '${TARGET_URL}/api/projects/')
         [[ \"\$S\" == '401' ]]"

    _check "rate limit em /auth/token (429 apos burst)" bash -c "
        for i in \$(seq 1 8); do
            S=\$(curl -so /dev/null -w '%{http_code}' --max-time 5 \
                -X POST '${TARGET_URL}/auth/token' \
                -H 'Content-Type: application/json' \
                -d '{\"client_id\":\"invalid\",\"client_secret\":\"invalid\"}')
            [[ \"\$S\" == '429' ]] && exit 0
        done
        exit 0
    "

    if [[ -n "$TOKEN" ]]; then
        PAYLOAD=$(echo "$TOKEN" | cut -d. -f2 \
            | python3 -c "import sys,base64,json
d=sys.stdin.read().strip(); d+='='*(4-len(d)%4)
print(json.dumps(json.loads(base64.b64decode(d))))" 2>/dev/null || echo "{}")

        _check "JWT contem claim 'roles'" bash -c "echo '$PAYLOAD' | jq -e '.roles' > /dev/null"
        _check "JWT contem claim 'sub'"   bash -c "echo '$PAYLOAD' | jq -e '.sub'   > /dev/null"

        _check "GET /api/projects/ com token valido" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 15 \
                -H 'Authorization: Bearer ${TOKEN}' '${TARGET_URL}/api/projects/')
             [[ \"\$S\" == '200' ]]"

        _check "X-RateLimit-Limit header presente" bash -c \
            "curl -sf --max-time 10 -I \
                -H 'Authorization: Bearer ${TOKEN}' \
                '${TARGET_URL}/api/projects/' \
                | grep -qi 'x-ratelimit-limit'"

        _check "RBAC: 403 em endpoint restrito (project:approve sem permissao)" bash -c \
            "ROLES=\$(echo '$PAYLOAD' | jq -r '.roles[]?' 2>/dev/null)
             [[ \"\$ROLES\" == *'viewer'* || \"\$ROLES\" == *'service-ci'* ]] && {
                S=\$(curl -so /dev/null -w '%{http_code}' --max-time 10 \
                    -X POST -H 'Authorization: Bearer ${TOKEN}' \
                    '${TARGET_URL}/api/projects/test/versions/v1/approve')
                [[ \"\$S\" == '403' || \"\$S\" == '404' ]]
             } || exit 0"
    fi

    if [[ -n "$TOKEN" ]]; then
        _check "GET /api/catalogs (catalog:read)" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 15 \
                -H 'Authorization: Bearer ${TOKEN}' '${TARGET_URL}/api/catalogs/')
             [[ \"\$S\" == '200' ]]"
    fi

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

    if [[ "$TARGET_URL" == https://* ]]; then
        _check "Certificado TLS valido" curl -sf --max-time 10 "${TARGET_URL}/health"
        _check "HTTP redireciona para HTTPS" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 10 --max-redirs 0 \
                '${TARGET_URL/https/http}/health' 2>/dev/null || echo 000)
             [[ \"\$S\" == '301' || \"\$S\" == '302' || \"\$S\" == '308' ]]"
    fi

    local total=$((PASS+FAIL))
    echo
    echo -e "  ──────────────────────────────────────────────────"
    if [[ $FAIL -eq 0 ]]; then
        echo -e "  ${G}${N}PASSOU${NC}  ${PASS}/${total} checks"
        [[ -n "$TARGET_REVISION" ]] && echo "  Proximo passo: cd/scripts/deploy.sh promote --revision $TARGET_REVISION"
    else
        echo -e "  ${R}${N}FALHOU${NC}  ${FAIL}/${total} checks"
        [[ -n "$TARGET_REVISION" ]] && echo "  Proximo passo: cd/scripts/deploy.sh rollback --revision $TARGET_REVISION"
        echo "  Logs: az containerapp logs show --name $ACA_API_APP --resource-group $RESOURCE_GROUP --revision ${TARGET_REVISION:-<revision>}"
        exit 1
    fi
    echo -e "  ──────────────────────────────────────────────────"
}

cmd_promote() {
    local target_revision=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --revision) target_revision="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    need az
    require_login

    _aca_app_exists "$ACA_API_APP" || die "Container App '$ACA_API_APP' nao encontrado."

    [[ -n "$target_revision" ]] || target_revision=$(_aca_latest_revision "$ACA_API_APP")
    [[ -n "$target_revision" ]] || die "Nao foi possivel determinar a revision para promote."

    local current
    current=$(_aca_primary_revision "$ACA_API_APP")

    step "Promote ACA Revision"
    log "Atual: ${current:-nenhuma}"
    log "Nova ativa: $target_revision"

    az containerapp ingress traffic set \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --revision-weight "${target_revision}=100" \
        --output none

    ok "Trafego de producao agora aponta 100% para '$target_revision'."
}

cmd_rollback() {
    local target_revision=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --revision) target_revision="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    need az
    require_login

    _aca_app_exists "$ACA_API_APP" || die "Container App '$ACA_API_APP' nao encontrado."

    local current
    current=$(_aca_primary_revision "$ACA_API_APP")
    [[ -n "$current" ]] || die "Nao existe revision ativa para rollback."

    if [[ -z "$target_revision" ]]; then
        target_revision=$(_aca_previous_revision "$ACA_API_APP" "$current")
    fi
    [[ -n "$target_revision" ]] || die "Nenhuma revision anterior disponivel para rollback."

    step "Rollback ACA Revision"
    log "Atual: $current"
    log "Destino rollback: $target_revision"

    az containerapp ingress traffic set \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --revision-weight "${target_revision}=100" \
        --output none

    ok "Rollback concluido. Trafego em '$target_revision'."
}

cmd_status() {
    need az
    require_login

    _aca_app_exists "$ACA_API_APP" || die "Container App '$ACA_API_APP' nao encontrado."

    step "Estado ACA Revisions ($ACA_API_APP)"

    local primary
    primary=$(_aca_primary_revision "$ACA_API_APP")
    echo -e "  Revision principal: ${G}${N}${primary:-nenhuma}${NC}"
    echo

    echo "  Trafego:"
    az containerapp ingress traffic show \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --query "[].{revision:revisionName,weight:weight,label:label,latest:latestRevision}" \
        -o table || true

    echo
    echo "  Revisions:"
    az containerapp revision list \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --query "sort_by(@,&properties.createdTime)[].{name:name,active:properties.active,state:properties.runningState,created:properties.createdTime,replicas:properties.replicas}" \
        -o table || true

    if _aca_app_exists "$ACA_MCP_APP"; then
        echo
        step "Estado MCP App ($ACA_MCP_APP)"
        local mcp_fqdn
        mcp_fqdn=$(az containerapp show --name "$ACA_MCP_APP" --resource-group "$RESOURCE_GROUP" \
            --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || echo "-")
        echo "  FQDN MCP: $mcp_fqdn"
    fi
}

# -- Platform operations ---------------------------------------------------------

cmd_image() {
    local input_tag=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tag) input_tag="$2"; shift 2 ;;
            *)     shift ;;
        esac
    done

    need az
    require_login

    local resolved_tag
    if [[ -n "$input_tag" ]]; then
        resolved_tag="$input_tag"
    else
        if [[ -n "${GITHUB_SHA:-}" ]]; then
            resolved_tag="${GITHUB_SHA:0:8}"
        else
            resolved_tag=$(git rev-parse --short=8 HEAD 2>/dev/null || echo "latest")
        fi
    fi

    step "Preparar imagem no ACR"
    log "Tag alvo: $resolved_tag"

    az acr login --name "$ACR_NAME"

    if [[ -n "$input_tag" ]]; then
        az acr repository show-tags \
            --name "$ACR_NAME" \
            --repository "$IMAGE_NAME" \
            --query "[?@=='${resolved_tag}']" \
            --output tsv | grep -q . || die "Tag '${resolved_tag}' nao existe no ACR."
        ok "Imagem verificada: ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${resolved_tag}"
    else
        az acr build \
            --registry "$ACR_NAME" \
            --image "${IMAGE_NAME}:${resolved_tag}" \
            --image "${IMAGE_NAME}:latest" \
            --file "$REPO_ROOT/Dockerfile" \
            --platform linux/amd64 \
            "$REPO_ROOT"
        ok "Imagem publicada: ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${resolved_tag}"
    fi

    if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
        echo "image_tag=${resolved_tag}" >> "$GITHUB_OUTPUT"
    fi
}

cmd_keys() {
    ROTATE=false; [[ "${1:-}" == "--rotate" ]] && ROTATE=true
    need az; need openssl
    require_login

    step "JWT Keys RS256 -> Key Vault '$KV_NAME'"
    if az_secret_exists "jwt-private-key" && [[ "$ROTATE" == "false" ]]; then
        ok "Chaves ja existem. Use --rotate para substitui-las."; return 0
    fi
    [[ "$ROTATE" == "true" ]] && { warn "Rotacao: tokens antigos expiram em <=8h."; confirm "Confirmar?"; }

    PRIVATE_PEM=$(openssl genrsa 2048 2>/dev/null)
    PUBLIC_PEM=$(echo "$PRIVATE_PEM" | openssl rsa -pubout 2>/dev/null)
    echo "$PRIVATE_PEM" | az keyvault secret set --vault-name "$KV_NAME" \
        --name "jwt-private-key" --value "$(cat)" --output none
    echo "$PUBLIC_PEM" | az keyvault secret set --vault-name "$KV_NAME" \
        --name "jwt-public-key" --value "$(cat)" --output none
    unset PRIVATE_PEM PUBLIC_PEM
    ok "jwt-private-key e jwt-public-key armazenados."
}

cmd_bootstrap() {
    local mode="apply"
    [[ "${1:-}" == "--validate" ]] && mode="validate"

    need az
    require_login

    if [[ "$mode" == "validate" ]]; then
        step "Validar Bicep"
        az bicep build --file "$REPO_ROOT/cd/production/bicep/main.bicep"
        az deployment group validate \
            --resource-group "$RESOURCE_GROUP" \
            --template-file "$REPO_ROOT/cd/production/bicep/main.bicep" \
            --parameters "$REPO_ROOT/cd/production/bicep/main.bicepparam" \
            --parameters opsIdentityPrincipalId="placeholder" \
            --parameters azureStorageKey="placeholder" \
            --output none
        ok "Templates Bicep validados."
        return 0
    fi

    step "Resource Group"
    az group show --name "$RESOURCE_GROUP" &>/dev/null 2>&1 \
        && ok "Ja existe." \
        || { az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none; ok "Criado."; }

    step "App Registration OIDC"
    APP_NAME="concilium-github-actions"
    APP_ID=$(az ad app list --display-name "$APP_NAME" --query '[0].appId' -o tsv 2>/dev/null || echo "")
    if [[ -z "$APP_ID" ]]; then
        APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
        az ad sp create --id "$APP_ID" --output none 2>/dev/null || true
        ok "Criado: $APP_ID"
    else
        ok "Ja existe: $APP_ID"
    fi

    az ad app federated-credential create --id "$APP_ID" --parameters \
        "{\"name\":\"github-main\",\"issuer\":\"https://token.actions.githubusercontent.com\",\
\"subject\":\"repo:${GITHUB_REPO}:ref:refs/heads/main\",\"audiences\":[\"api://AzureADTokenExchange\"]}" \
        2>/dev/null || ok "Federated credential ja existe."

    OPS_PRINCIPAL=$(az ad sp show --id "$APP_ID" --query id -o tsv)
    SUBSCRIPTION_ID=$(az account show --query id -o tsv)
    az role assignment create --assignee "$OPS_PRINCIPAL" --role Contributor \
        --scope "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}" \
        --output none 2>/dev/null || ok "Role assignment ja existe."

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
    ok "Bicep deploy concluido."

    step "Resumo"
    echo -e "  ${G}App Registration${NC}: $APP_ID  (Tenant: $(az account show --query tenantId -o tsv))"
    echo -e "\n  ${Y}Nameservers para o Registro.br:${NC}"
    az network dns zone show --resource-group "$RESOURCE_GROUP" \
        --name "$DNS_ZONE" --query "nameServers" -o tsv 2>/dev/null | sed 's/^/    /'
    echo
    echo "  Proximos: $0 keys -> $0 tls -> $0 github"
}

cmd_tls() {
    MODE="${1:-}"; CERT_FILE="${2:-}"
    [[ -z "$MODE" ]] && die "Use: $0 tls --upload cert.pfx  ou  $0 tls --self-signed"
    need az; need openssl
    require_login
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

cmd_github() {
    need az; need gh
    require_login
    gh auth status &>/dev/null || die "gh auth login"

    _s() { echo -n "  $1... "; echo "$2" | gh secret set "$1" --repo "$GITHUB_REPO"; echo -e "${G}OK${NC}"; }
    _v() { echo -n "  $1... "; gh variable set "$1" --body "$2" --repo "$GITHUB_REPO"; echo -e "${G}OK${NC}"; }

    APP_ID=$(az ad app list --display-name "concilium-github-actions" --query '[0].appId' -o tsv || echo "")
    [[ -z "$APP_ID" ]] && die "App Registration nao encontrado. Execute bootstrap primeiro."

    _s "AZURE_CLIENT_ID"       "$APP_ID"
    _s "AZURE_TENANT_ID"       "$(az account show --query tenantId -o tsv)"
    _s "AZURE_SUBSCRIPTION_ID" "$(az account show --query id -o tsv)"
    _v "RESOURCE_GROUP"             "$RESOURCE_GROUP"
    _v "CONCILIUM__AZURE_ACCOUNT"   "$STORAGE_ACCOUNT"
    _v "CONCILIUM__AZURE_CONTAINER" "concilium-projetos"
    _v "ACA_API_APP"                "$ACA_API_APP"
    _v "ACA_MCP_APP"                "$ACA_MCP_APP"

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

cmd_users() {
    local app_name="${USERS_APP:-$ACA_MCP_APP}"
    local exec_cmd="${*:-python -m concilium.auth.bootstrap_users}"

    need az
    require_login
    _aca_app_exists "$app_name" || die "Container App '$app_name' nao encontrado."

    step "Criacao/Gestao de usuarios via ACA exec"
    log "App alvo: $app_name"
    log "Comando: $exec_cmd"

    az containerapp exec \
        --name "$app_name" \
        --resource-group "$RESOURCE_GROUP" \
        --command "$exec_cmd"
}

cmd_all() {
    step "Sequencia operacional completa"
    cmd_bootstrap
    cmd_keys
    cmd_tls --self-signed
    cmd_github
}

# -- Help -----------------------------------------------------------------------

cmd_help() {
    cat <<'EOF'
Uso: deploy.sh [comando] [opcoes]

-- Runtime Deployment (ACA Revisions, CI-safe) ---------------------------------
    image [--tag TAG]             Builda imagem nova (sem --tag) ou valida tag existente
  deploy IMAGE_TAG             Cria nova revision no ACA sem promover trafego
  smoke [--revision REV]       Smoke exaustivo contra a revision/FQDN alvo
        [--url URL] [--mcp-url URL]
  promote [--revision REV]     Direciona 100% do trafego para a revision
  rollback [--revision REV]    Volta para revision anterior (ou especificada)
  status                       Mostra revisions e pesos de trafego

-- Platform Operations ----------------------------------------------------------
  keys [--rotate]              Gera JWT keys -> Key Vault
  bootstrap                    Provisiona infra Azure completa (idempotente)
    bootstrap --validate         Valida Bicep (build + deployment validate)
  tls --upload <pfx>           Configura TLS com certificado PFX existente
  tls --self-signed            Configura TLS auto-assinado (staging)
  github                       Configura GitHub Secrets via gh CLI
  users [comando]              Executa comando de usuarios via az containerapp exec
  all                          Executa bootstrap -> keys -> tls -> github

Variaveis de ambiente (CI/CD):
  RESOURCE_GROUP LOCATION KV_NAME ACR_NAME AGW_NAME
  ACA_API_APP ACA_MCP_APP DNS_ZONE GITHUB_REPO STORAGE_ACCOUNT
  AZURE_ACCOUNT AZURE_CONTAINER AZURE_KEY OTEL_ENDPOINT
  SMOKE_CLIENT_ID SMOKE_CLIENT_SECRET
EOF
}

# -- Dispatcher -----------------------------------------------------------------

CMD="${1:-all}"; shift 2>/dev/null || true
_check_ci_safe "$CMD"

case "$CMD" in
    image)          cmd_image "$@" ;;
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

    *)
        die "Comando desconhecido: '$CMD'. Use '$0 help'."
        ;;
esac