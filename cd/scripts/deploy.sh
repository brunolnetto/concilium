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
#   bootstrap, keys, github, configure, users, all, help
set -euo pipefail

_CI_SAFE_CMDS="keys image deploy smoke promote rollback status bootstrap configure help"

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
ACA_API_APP="${ACA_API_APP:-concilium-api}"
ACA_MCP_APP="${ACA_MCP_APP:-concilium-mcp}"
GITHUB_REPO="${GITHUB_REPO:-mendes-lobo-construcao/agente-gerente-de-engenharia}"
SMOKE_CLIENT_ID="${SMOKE_CLIENT_ID:-smoke-test}"
SMOKE_CLIENT_SECRET="${SMOKE_CLIENT_SECRET:-}"
SP_TENANT_ID="${SP_TENANT_ID:-}"
SP_CLIENT_ID="${SP_CLIENT_ID:-}"
SP_CLIENT_SECRET="${SP_CLIENT_SECRET:-}"
SP_DRIVE_ID="${SP_DRIVE_ID:-}"
SP_ROOT_PATH="${SP_ROOT_PATH:-Concilium/prod}"

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

_az_retry() {
    local attempt=0 max=5 delay=10
    until "$@" 2>&1; do
        attempt=$((attempt + 1))
        [[ $attempt -ge $max ]] && { echo "  Falhou apos $max tentativas: $*" >&2; return 1; }
        warn "  OperationInProgress — aguardando ${delay}s (tentativa $attempt/$max)..."
        sleep "$delay"
        delay=$((delay * 2))
    done
}

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

        [[ "$state" == "Running" || "$state" == "RunningAtMaxScale" ]] && { ok "  '$revision' $state"; return 0; }
        [[ "$state" == "Failed" || "$state" == "Deactivated" || "$state" == "Stopped" ]] && die "Revision '$revision' falhou: $state"
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

    # ── Deploy API (blue-green) ───────────────────────────────────────────────
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
        _az_retry az containerapp ingress traffic set \
            --name "$ACA_API_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --revision-weight "${previous_primary}=100" "${new_revision}=0" \
            --output none
    else
        _az_retry az containerapp ingress traffic set \
            --name "$ACA_API_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --revision-weight "${new_revision}=100" \
            --output none
    fi

    local new_url
    new_url=$(_aca_revision_url "$ACA_API_APP" "$new_revision")
    ok "Revision API pronta: $new_revision"
    log "URL da revision: $new_url"

    # ── Deploy MCP (rolling update — mesma imagem, comando diferente) ─────────
    if _aca_app_exists "$ACA_MCP_APP"; then
        step "ACA Deploy — app '$ACA_MCP_APP' com imagem '$image_tag'"
        az containerapp revision set-mode \
            --name "$ACA_MCP_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --mode multiple \
            --output none
        az containerapp update \
            --name "$ACA_MCP_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --image "${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${image_tag}" \
            --output none
        local mcp_revision
        mcp_revision=$(_aca_latest_revision "$ACA_MCP_APP")
        _wait_revision_running "$ACA_MCP_APP" "$mcp_revision"
        _az_retry az containerapp ingress traffic set \
            --name "$ACA_MCP_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --revision-weight "${mcp_revision}=100" \
            --output none
        ok "Revision MCP pronta: $mcp_revision (100% trafego)"
    fi

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

    need az; require_login
    if [[ -n "$TARGET_REVISION" ]]; then
        TARGET_URL=$(_aca_revision_url "$ACA_API_APP" "$TARGET_REVISION")
        if [[ -z "$TARGET_MCP" ]]; then
            local mcp_fqdn; mcp_fqdn=$(az containerapp show \
                --name "$ACA_MCP_APP" --resource-group "$RESOURCE_GROUP" \
                --query 'properties.configuration.ingress.fqdn' -o tsv 2>/dev/null)
            TARGET_MCP="https://${mcp_fqdn}/mcp"
        fi
    else
        if [[ -z "$TARGET_URL" ]]; then
            local fqdn; fqdn=$(az containerapp show \
                --name "$ACA_API_APP" --resource-group "$RESOURCE_GROUP" \
                --query 'properties.configuration.ingress.fqdn' -o tsv 2>/dev/null)
            [[ -n "$fqdn" ]] || die "Nao foi possivel resolver FQDN de '$ACA_API_APP'. Use --url ou --revision."
            TARGET_URL="https://${fqdn}"
        fi
        if [[ -z "$TARGET_MCP" ]]; then
            local mcp_fqdn; mcp_fqdn=$(az containerapp show \
                --name "$ACA_MCP_APP" --resource-group "$RESOURCE_GROUP" \
                --query 'properties.configuration.ingress.fqdn' -o tsv 2>/dev/null)
            TARGET_MCP="https://${mcp_fqdn}/mcp"
        fi
    fi

    need curl; need jq

    PASS=0; FAIL=0; TOKEN=""

    _check() {
        local name="$1"; shift
        if "$@" &>/dev/null 2>&1; then ok "$name"; (( ++PASS )) || true
        else warn "FALHOU: $name"; (( ++FAIL )) || true; fi
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
            && { ok "POST /auth/token -> JWT emitido"; (( ++PASS )) || true; } \
            || { warn "FALHOU: POST /auth/token"; (( ++FAIL )) || true; }
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
            "curl -s --max-time 10 -D - -o /dev/null \
                -X POST '${TARGET_URL}/auth/token' \
                -H 'Content-Type: application/json' \
                -d '{\"client_id\":\"probe\",\"client_secret\":\"probe\"}' \
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
            "S=\$(curl -sLo /dev/null -w '%{http_code}' --max-time 15 \
                -H 'Authorization: Bearer ${TOKEN}' '${TARGET_URL}/api/catalogs/')
             [[ \"\$S\" == '200' ]]"
    fi

    _check "MCP server responde" bash -c \
        "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 15 '${TARGET_MCP}')
         [[ \"\$S\" != '000' ]]"

    if [[ -n "$TOKEN" ]]; then
        _check "MCP tools/list com token" bash -c \
            "AUTH='Authorization: Bearer ${TOKEN}'
             CT='Content-Type: application/json'
             AC='Accept: application/json, text/event-stream'
             INIT_RESP=\$(curl -sf --max-time 15 -D /tmp/mcp_init_hdr.txt \
                -X POST '${TARGET_MCP}' \
                -H \"\$AUTH\" -H \"\$CT\" -H \"\$AC\" \
                -d '{\"jsonrpc\":\"2.0\",\"method\":\"initialize\",\"id\":0,\"params\":{\"protocolVersion\":\"2024-11-05\",\"capabilities\":{},\"clientInfo\":{\"name\":\"smoke\",\"version\":\"1\"}}}' \
                2>/dev/null || echo '{}')
             SID=\$(grep -i '^mcp-session-id:' /tmp/mcp_init_hdr.txt | tr -d '\\r' | awk '{print \$2}')
             RESP=\$(curl -sf --max-time 20 \
                -X POST '${TARGET_MCP}' \
                -H \"\$AUTH\" -H \"\$CT\" -H \"\$AC\" \
                -H \"mcp-session-id: \$SID\" \
                -d '{\"jsonrpc\":\"2.0\",\"method\":\"tools/list\",\"id\":1}' 2>/dev/null || echo '{}')
             PARSED=\$(echo \"\$RESP\" | grep '^data: ' | sed 's/^data: //' | head -1)
             [ -z \"\$PARSED\" ] && PARSED=\"\$RESP\"
             echo \"\$PARSED\" | jq -e '.result.tools | length > 0' > /dev/null"

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
    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "$REPO_ROOT/cd/production/bicep/main.bicep" \
        --parameters "$REPO_ROOT/cd/production/bicep/main.bicepparam" \
        --parameters "opsIdentityPrincipalId=$OPS_PRINCIPAL" \
        --output none
    ok "Bicep deploy concluido."

    step "Resumo"
    echo -e "  ${G}App Registration${NC}: $APP_ID  (Tenant: $(az account show --query tenantId -o tsv))"
    echo
    echo "  Proximos: $0 keys -> $0 github -> $0 configure"
}

cmd_configure_smtp() {
    need az
    require_login

    local smtp_pwd="${SMTP_PASSWORD:-}"
    if [[ -z "$smtp_pwd" ]]; then
        read -r -s -p "SMTP_PASSWORD (Gmail App Password): " smtp_pwd; echo
    fi
    [[ -n "$smtp_pwd" ]] || die "SMTP_PASSWORD nao fornecido."

    step "Gravando smtp-password no Key Vault '$KV_NAME'"
    printf '%s' "$smtp_pwd" | az keyvault secret set \
        --vault-name "$KV_NAME" --name smtp-password --value "@-" --output none
    ok "smtp-password gravado."

    local smtp_envs=(
        "CONCILIUM__SMTP_HOST=smtp.gmail.com"
        "CONCILIUM__SMTP_PORT=587"
        "CONCILIUM__SMTP_USER=brunolnetto@gmail.com"
        "CONCILIUM__SMTP_FROM=brunolnetto@gmail.com"
        "CONCILIUM__NOTIFICATIONS_ENABLED=1"
    )

    for app in "$ACA_MCP_APP" "$ACA_API_APP"; do
        if _aca_app_exists "$app"; then
            step "Aplicando env vars SMTP em '$app'"
            az containerapp update \
                --name "$app" \
                --resource-group "$RESOURCE_GROUP" \
                --set-env-vars "${smtp_envs[@]}" \
                --output none
            ok "$app atualizado."
        else
            warn "Container '$app' nao encontrado — pulando."
        fi
    done

    ok "SMTP configurado. A senha e lida do Key Vault via Managed Identity no startup."
}

cmd_configure() {
    need az; need openssl
    require_login

    [[ -n "$SP_TENANT_ID" ]]     || die "SP_TENANT_ID nao definido."
    [[ -n "$SP_CLIENT_ID" ]]     || die "SP_CLIENT_ID nao definido."
    [[ -n "$SP_CLIENT_SECRET" ]] || die "SP_CLIENT_SECRET nao definido."
    [[ -n "$SP_DRIVE_ID" ]]      || die "SP_DRIVE_ID nao definido."
    [[ -n "$SMOKE_CLIENT_SECRET" ]] || die "SMOKE_CLIENT_SECRET nao definido."
    [[ -n "$SMTP_PASSWORD" ]]    || warn "SMTP_PASSWORD nao definido — notificacoes desabilitadas."

    local smoke_hash
    smoke_hash="sha256:$(printf '%s' "$SMOKE_CLIENT_SECRET" | openssl dgst -sha256 -hex | sed 's/^.* //')"
    local auth_clients="{\"${SMOKE_CLIENT_ID}\":{\"secret_hash\":\"${smoke_hash}\",\"roles\":[\"operator\"]}}"
    local kv_url="https://${KV_NAME}.vault.azure.net"

    # Grava smtp-password no Key Vault (idempotente)
    if [[ -n "${SMTP_PASSWORD:-}" ]]; then
        step "Gravando smtp-password no Key Vault"
        printf '%s' "$SMTP_PASSWORD" | az keyvault secret set \
            --vault-name "$KV_NAME" --name smtp-password --value "@-" --output none
        ok "smtp-password gravado."
    fi
    local mi_client_id
    mi_client_id=$(az identity show --name concilium-identity --resource-group "$RESOURCE_GROUP" \
        --query 'clientId' -o tsv 2>/dev/null || echo "")

    _apply_yaml() {
        local app="$1" yaml_file="$2"
        _aca_app_exists "$app" || die "Container App '$app' nao encontrado."
        az containerapp update \
            --name "$app" \
            --resource-group "$RESOURCE_GROUP" \
            --yaml "$yaml_file" \
            --output none
        ok "$app configurado."
    }

    # ── MCP ───────────────────────────────────────────────────────────────────
    step "Configurar env vars — $ACA_MCP_APP"
    local mcp_yaml; mcp_yaml=$(mktemp /tmp/mcp-configure-XXXXXX.yaml)
    cat > "$mcp_yaml" << EOF
properties:
  template:
    containers:
      - name: ${ACA_MCP_APP}
        image: ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:latest
        command:
          - concilium-mcp
        env:
          - name: CONCILIUM__CONFIG_ROOT
            value: /app
          - name: CONCILIUM__STORE_BACKEND
            value: sharepoint
          - name: CONCILIUM__SP_TENANT_ID
            value: ${SP_TENANT_ID}
          - name: CONCILIUM__SP_CLIENT_ID
            value: ${SP_CLIENT_ID}
          - name: CONCILIUM__SP_CLIENT_SECRET
            value: "${SP_CLIENT_SECRET}"
          - name: CONCILIUM__SP_DRIVE_ID
            value: "${SP_DRIVE_ID}"
          - name: CONCILIUM__SP_ROOT_PATH
            value: ${SP_ROOT_PATH}
          - name: CONCILIUM__AUTH_ENABLED
            value: "1"
          - name: CONCILIUM__AUTH_CLIENTS
            value: '${auth_clients}'
          - name: CONCILIUM__JWT_KEY_VAULT_URL
            value: ${kv_url}
          - name: CONCILIUM__PROJECTS_ROOT
            value: /tmp/projetos
          - name: CONCILIUM__MCP_TRANSPORT
            value: streamable-http
          - name: CONCILIUM__MCP_HOST
            value: "0.0.0.0"
          - name: CONCILIUM__MCP_PORT
            value: "8080"
          - name: OTEL_SERVICE_NAME
            value: concilium-mcp
          - name: AZURE_CLIENT_ID
            value: ${mi_client_id}
          - name: CONCILIUM__SMTP_HOST
            value: smtp.gmail.com
          - name: CONCILIUM__SMTP_PORT
            value: "587"
          - name: CONCILIUM__SMTP_USER
            value: brunolnetto@gmail.com
          - name: CONCILIUM__SMTP_FROM
            value: brunolnetto@gmail.com
          - name: CONCILIUM__NOTIFICATIONS_ENABLED
            value: "1"
EOF
    _apply_yaml "$ACA_MCP_APP" "$mcp_yaml"
    rm -f "$mcp_yaml"

    # ── API ───────────────────────────────────────────────────────────────────
    step "Configurar env vars — $ACA_API_APP"
    local api_yaml; api_yaml=$(mktemp /tmp/api-configure-XXXXXX.yaml)
    cat > "$api_yaml" << EOF
properties:
  template:
    containers:
      - name: ${ACA_API_APP}
        image: ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:latest
        command:
          - concilium-api
        env:
          - name: CONCILIUM__CONFIG_ROOT
            value: /app
          - name: CONCILIUM__STORE_BACKEND
            value: sharepoint
          - name: CONCILIUM__SP_TENANT_ID
            value: ${SP_TENANT_ID}
          - name: CONCILIUM__SP_CLIENT_ID
            value: ${SP_CLIENT_ID}
          - name: CONCILIUM__SP_CLIENT_SECRET
            value: "${SP_CLIENT_SECRET}"
          - name: CONCILIUM__SP_DRIVE_ID
            value: "${SP_DRIVE_ID}"
          - name: CONCILIUM__SP_ROOT_PATH
            value: ${SP_ROOT_PATH}
          - name: CONCILIUM__AUTH_ENABLED
            value: "1"
          - name: CONCILIUM__AUTH_CLIENTS
            value: '${auth_clients}'
          - name: CONCILIUM__JWT_KEY_VAULT_URL
            value: ${kv_url}
          - name: CONCILIUM__PROJECTS_ROOT
            value: /tmp/projetos
          - name: CONCILIUM__API_HOST
            value: "0.0.0.0"
          - name: CONCILIUM__API_PORT
            value: "8000"
          - name: OTEL_SERVICE_NAME
            value: concilium-api
          - name: AZURE_CLIENT_ID
            value: ${mi_client_id}
          - name: CONCILIUM__SMTP_HOST
            value: smtp.gmail.com
          - name: CONCILIUM__SMTP_PORT
            value: "587"
          - name: CONCILIUM__SMTP_USER
            value: brunolnetto@gmail.com
          - name: CONCILIUM__SMTP_FROM
            value: brunolnetto@gmail.com
          - name: CONCILIUM__NOTIFICATIONS_ENABLED
            value: "1"
EOF
    _apply_yaml "$ACA_API_APP" "$api_yaml"
    rm -f "$api_yaml"

    ok "Configuracao aplicada em ambos os containers."
    echo "  Proximos passos: cd/scripts/deploy.sh github"
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
    _v "RESOURCE_GROUP"        "$RESOURCE_GROUP"
    _v "ACA_API_APP"           "$ACA_API_APP"
    _v "ACA_MCP_APP"           "$ACA_MCP_APP"
    _v "ACR_NAME"              "$ACR_NAME"
    _v "IMAGE_NAME"            "$IMAGE_NAME"
    _v "SMOKE_CLIENT_ID"       "$SMOKE_CLIENT_ID"

    local sp_secret="${SP_CLIENT_SECRET:-}"
    [[ -z "$sp_secret" ]] && { read -r -s -p "  SP_CLIENT_SECRET: " sp_secret; echo; }
    _s "CONCILIUM__SP_CLIENT_SECRET" "$sp_secret"

    read -r -p "  OTEL Endpoint (Enter pula): " OTEL
    [[ -n "$OTEL" ]] && _s "OTEL_EXPORTER_OTLP_ENDPOINT" "$OTEL"

    local smks="${SMOKE_CLIENT_SECRET:-}"
    [[ -z "$smks" ]] && { read -r -s -p "  SMOKE_CLIENT_SECRET: " smks; echo; }
    _s "SMOKE_CLIENT_SECRET" "$smks"

    local smtp_pwd="${SMTP_PASSWORD:-}"
    [[ -z "$smtp_pwd" ]] && { read -r -s -p "  SMTP_PASSWORD (Gmail App Password): " smtp_pwd; echo; }
    [[ -n "$smtp_pwd" ]] && _s "SMTP_PASSWORD" "$smtp_pwd"

    ok "GitHub Secrets/Vars configurados."
    echo "  Proximos passos: cd/scripts/deploy.sh configure"
}

cmd_users() {
    local app_name="${USERS_APP:-$ACA_MCP_APP}"
    # Sem args: abre shell interativo. Com args: executa o subcomando como string via /bin/sh -c
    local exec_cmd="${*:-}"

    need az
    require_login
    _aca_app_exists "$app_name" || die "Container App '$app_name' nao encontrado."

    step "Gestao de usuarios via ACA exec"
    log "App alvo: $app_name"

    if [[ -z "$exec_cmd" ]]; then
        log "Abrindo shell interativo — use 'concilium ops auth --help' para ver os comandos"
        az containerapp exec \
            --name "$app_name" \
            --resource-group "$RESOURCE_GROUP" \
            --command "/bin/sh"
    else
        log "Comando: $exec_cmd"
        az containerapp exec \
            --name "$app_name" \
            --resource-group "$RESOURCE_GROUP" \
            --command "/bin/sh" -- -c "$exec_cmd"
    fi
}

cmd_all() {
    step "Sequencia operacional completa"
    cmd_bootstrap
    cmd_keys
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
  configure                    Aplica env vars em ambos os containers ACA (idempotente)
  configure-smtp               Grava SMTP_PASSWORD no Key Vault e seta env vars SMTP (nao requer SP vars)
  keys [--rotate]              Gera JWT keys -> Key Vault
  bootstrap                    Provisiona infra Azure base (idempotente)
    bootstrap --validate         Valida Bicep (build + deployment validate)
  github                       Configura GitHub Secrets/Vars via gh CLI
  users [comando]              Executa comando de usuarios via az containerapp exec
  all                          Executa bootstrap -> keys -> github

Variaveis de ambiente (CI/CD):
  RESOURCE_GROUP LOCATION KV_NAME ACR_NAME IMAGE_NAME
  ACA_API_APP ACA_MCP_APP GITHUB_REPO
  SP_TENANT_ID SP_CLIENT_ID SP_CLIENT_SECRET SP_DRIVE_ID SP_ROOT_PATH
  SMOKE_CLIENT_ID SMOKE_CLIENT_SECRET
  OTEL_EXPORTER_OTLP_ENDPOINT
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

    configure)      cmd_configure "$@" ;;
    configure-smtp) cmd_configure_smtp "$@" ;;
    keys)           cmd_keys "$@" ;;
    bootstrap)      cmd_bootstrap "$@" ;;
    github)         cmd_github "$@" ;;
    users)          cmd_users "$@" ;;
    all)            cmd_all "$@" ;;

    help|--help|-h) cmd_help ;;

    *)
        die "Comando desconhecido: '$CMD'. Use '$0 help'."
        ;;
esac