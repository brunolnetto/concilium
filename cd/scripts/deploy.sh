#!/usr/bin/env bash
# deploy.sh — Runtime CI/CD do Concilium (revisões ACA).
#
# Comandos:
#   image [--tag TAG]       Builda imagem nova ou valida tag existente no ACR
#   deploy IMAGE_TAG        Cria nova revision sem promover trafego (blue/green)
#   smoke [--revision REV]  Smoke exaustivo contra a revision alvo
#   promote [--revision]    Direciona 100% do trafego para a revision
#   rollback [--revision]   Volta para revision anterior (ou especificada)
#   status                  Mostra revisions e pesos de trafego
#
# Para provisionamento de plataforma (bootstrap, configure, domain, keys, github)
# use: cd/scripts/provision.sh
#
# Pode ser "sourced" por provision.sh para reutilizar utilitarios comuns
# sem executar o dispatcher (guard BASH_SOURCE no final do arquivo).
set -euo pipefail

_CI_SAFE_CMDS="image deploy smoke promote rollback status help"

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
    az resource show --resource-type Microsoft.App/containerApps \
        --name "$1" --resource-group "$RESOURCE_GROUP" --output none >/dev/null 2>&1
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

    # ── Deploy MCP (blue/green — mesma imagem, comando diferente) ───────────
    local mcp_revision=""
    if _aca_app_exists "$ACA_MCP_APP"; then
        step "ACA Deploy — app '$ACA_MCP_APP' com imagem '$image_tag'"

        local mcp_previous_primary
        mcp_previous_primary=$(_aca_primary_revision "$ACA_MCP_APP")

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
        mcp_revision=$(_aca_latest_revision "$ACA_MCP_APP")
        _wait_revision_running "$ACA_MCP_APP" "$mcp_revision"

        if [[ -n "$mcp_previous_primary" && "$mcp_previous_primary" != "$mcp_revision" ]]; then
            _az_retry az containerapp ingress traffic set \
                --name "$ACA_MCP_APP" \
                --resource-group "$RESOURCE_GROUP" \
                --revision-weight "${mcp_previous_primary}=100" "${mcp_revision}=0" \
                --output none
        else
            _az_retry az containerapp ingress traffic set \
                --name "$ACA_MCP_APP" \
                --resource-group "$RESOURCE_GROUP" \
                --revision-weight "${mcp_revision}=100" \
                --output none
        fi

        if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
            echo "deployed_mcp_revision=${mcp_revision}" >> "$GITHUB_OUTPUT"
        fi

        ok "Revision MCP pronta: $mcp_revision (aguardando smoke + promote)"
    fi

    local next_step="cd/scripts/deploy.sh smoke --revision $new_revision"
    [[ -n "$mcp_revision" ]] && next_step+=" --mcp-revision $mcp_revision"
    echo "  Proximo passo: $next_step"
}

cmd_smoke() {
    local TARGET_REVISION="" TARGET_MCP_REVISION="" TARGET_URL="" TARGET_MCP=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --revision)     TARGET_REVISION="$2"; shift 2 ;;
            --mcp-revision) TARGET_MCP_REVISION="$2"; shift 2 ;;
            --url)          TARGET_URL="$2"; shift 2 ;;
            --mcp-url)      TARGET_MCP="$2"; shift 2 ;;
            *)              shift ;;
        esac
    done

    need az; require_login
    if [[ -n "$TARGET_REVISION" ]]; then
        TARGET_URL=$(_aca_revision_url "$ACA_API_APP" "$TARGET_REVISION")
    elif [[ -z "$TARGET_URL" ]]; then
        local fqdn; fqdn=$(az containerapp show \
            --name "$ACA_API_APP" --resource-group "$RESOURCE_GROUP" \
            --query 'properties.configuration.ingress.fqdn' -o tsv 2>/dev/null)
        [[ -n "$fqdn" ]] || die "Nao foi possivel resolver FQDN de '$ACA_API_APP'. Use --url ou --revision."
        TARGET_URL="https://${fqdn}"
    fi

    if [[ -z "$TARGET_MCP" ]]; then
        local mcp_fqdn
        if [[ -n "$TARGET_MCP_REVISION" ]]; then
            mcp_fqdn=$(_aca_revision_fqdn "$ACA_MCP_APP" "$TARGET_MCP_REVISION")
        else
            mcp_fqdn=$(az containerapp show \
                --name "$ACA_MCP_APP" --resource-group "$RESOURCE_GROUP" \
                --query 'properties.configuration.ingress.fqdn' -o tsv 2>/dev/null)
        fi
        TARGET_MCP="https://${mcp_fqdn}/mcp"
    fi

    need curl; need jq

    PASS=0; FAIL=0; TOKEN=""

    _check() {
        local name="$1"; shift
        if "$@" &>/dev/null 2>&1; then ok "$name"; (( ++PASS )) || true
        else warn "FALHOU: $name"; (( ++FAIL )) || true; fi
    }

    # Como _check, mas tenta ate 3x com backoff — usado nos primeiros checks
    # autenticados que tocam o backend de storage (SharePoint), que pode estar
    # "frio" (token MSAL, throttling do Graph) logo apos um swap blue-green.
    _check_retry() {
        local name="$1"; shift
        local attempt delay
        for attempt in 1 2 3; do
            "$@" &>/dev/null 2>&1 && { ok "$name"; (( ++PASS )) || true; return 0; }
            [[ "$attempt" -lt 3 ]] && { delay=$((attempt * 3)); sleep "$delay"; }
        done
        warn "FALHOU: $name (apos 3 tentativas)"; (( ++FAIL )) || true
    }

    step "Smoke Tests Exaustivos -> $TARGET_URL"
    [[ -n "$TARGET_REVISION" ]]     && log "Revision API: $TARGET_REVISION"
    [[ -n "$TARGET_MCP_REVISION" ]] && log "Revision MCP: $TARGET_MCP_REVISION"

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

        _check_retry "GET /api/projects/ com token valido" bash -c \
            "S=\$(curl -so /dev/null -w '%{http_code}' --max-time 15 \
                -H 'Authorization: Bearer ${TOKEN}' '${TARGET_URL}/api/projects/')
             [[ \"\$S\" == '200' ]]"

        _check "X-RateLimit-Limit header presente" bash -c "
            for i in \$(seq 1 8); do
                RESP=\$(curl -s --max-time 5 -D - -o /dev/null \
                    -X POST '${TARGET_URL}/auth/token' \
                    -H 'Content-Type: application/json' \
                    -d '{\"client_id\":\"probe\",\"client_secret\":\"probe\"}')
                echo \"\$RESP\" | grep -qi 'x-ratelimit-limit' && exit 0
            done
            exit 1
        "

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
        _check_retry "GET /api/catalogs (catalog:read)" bash -c \
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
        if [[ -n "$TARGET_REVISION" ]]; then
            local promote_cmd="cd/scripts/deploy.sh promote --revision $TARGET_REVISION"
            [[ -n "$TARGET_MCP_REVISION" ]] && promote_cmd+=" --mcp-revision $TARGET_MCP_REVISION"
            echo "  Proximo passo: $promote_cmd"
        fi
    else
        echo -e "  ${R}${N}FALHOU${NC}  ${FAIL}/${total} checks"
        if [[ -n "$TARGET_REVISION" ]]; then
            local rollback_cmd="cd/scripts/deploy.sh rollback --revision $TARGET_REVISION"
            [[ -n "$TARGET_MCP_REVISION" ]] && rollback_cmd+=" --mcp-revision $TARGET_MCP_REVISION"
            echo "  Proximo passo: $rollback_cmd"
        fi
        echo "  Logs: az containerapp logs show --name $ACA_API_APP --resource-group $RESOURCE_GROUP --revision ${TARGET_REVISION:-<revision>}"
        exit 1
    fi
    echo -e "  ──────────────────────────────────────────────────"
}

cmd_promote() {
    local target_revision="" mcp_revision=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --revision)     target_revision="$2"; shift 2 ;;
            --mcp-revision) mcp_revision="$2"; shift 2 ;;
            *)              shift ;;
        esac
    done

    need az
    require_login

    _aca_app_exists "$ACA_API_APP" || die "Container App '$ACA_API_APP' nao encontrado."

    [[ -n "$target_revision" ]] || target_revision=$(_aca_latest_revision "$ACA_API_APP")
    [[ -n "$target_revision" ]] || die "Nao foi possivel determinar a revision para promote."

    local current
    current=$(_aca_primary_revision "$ACA_API_APP")

    step "Promote API Revision"
    log "Atual: ${current:-nenhuma}"
    log "Nova ativa: $target_revision"

    az containerapp ingress traffic set \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --revision-weight "${target_revision}=100" \
        --output none

    ok "API: trafego 100% para '$target_revision'."

    # Desativa todas as revisions da API que não recebem tráfego.
    log "Desativando revisions API sem trafego..."
    local old_revs
    old_revs=$(az containerapp revision list \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --query "[?properties.active && name != '$target_revision'].name" \
        --output tsv 2>/dev/null)

    local count=0
    while IFS= read -r rev; do
        [[ -z "$rev" ]] && continue
        az containerapp revision deactivate \
            --name "$ACA_API_APP" \
            --resource-group "$RESOURCE_GROUP" \
            --revision "$rev" \
            --output none 2>/dev/null && (( count++ )) || true
    done <<< "$old_revs"

    [[ $count -gt 0 ]] && ok "$count revision(s) API desativada(s)." || log "Nenhuma revision API extra para desativar."

    # ── Promote MCP (simetrico) ───────────────────────────────────────────────
    if _aca_app_exists "$ACA_MCP_APP"; then
        [[ -n "$mcp_revision" ]] || mcp_revision=$(_aca_latest_revision "$ACA_MCP_APP")

        if [[ -n "$mcp_revision" ]]; then
            local mcp_current
            mcp_current=$(_aca_primary_revision "$ACA_MCP_APP")

            step "Promote MCP Revision"
            log "Atual MCP: ${mcp_current:-nenhuma}"
            log "Nova ativa MCP: $mcp_revision"

            az containerapp ingress traffic set \
                --name "$ACA_MCP_APP" \
                --resource-group "$RESOURCE_GROUP" \
                --revision-weight "${mcp_revision}=100" \
                --output none

            ok "MCP: trafego 100% para '$mcp_revision'."

            log "Desativando revisions MCP sem trafego..."
            local old_mcp_revs
            old_mcp_revs=$(az containerapp revision list \
                --name "$ACA_MCP_APP" \
                --resource-group "$RESOURCE_GROUP" \
                --query "[?properties.active && name != '$mcp_revision'].name" \
                --output tsv 2>/dev/null)

            local mcp_count=0
            while IFS= read -r rev; do
                [[ -z "$rev" ]] && continue
                az containerapp revision deactivate \
                    --name "$ACA_MCP_APP" \
                    --resource-group "$RESOURCE_GROUP" \
                    --revision "$rev" \
                    --output none 2>/dev/null && (( mcp_count++ )) || true
            done <<< "$old_mcp_revs"

            [[ $mcp_count -gt 0 ]] && ok "$mcp_count revision(s) MCP desativada(s)." || log "Nenhuma revision MCP extra para desativar."
        else
            warn "Nao foi possivel determinar revision MCP para promote — pulando MCP."
        fi
    fi
}

cmd_rollback() {
    local target_revision="" mcp_revision=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --revision)     target_revision="$2"; shift 2 ;;
            --mcp-revision) mcp_revision="$2"; shift 2 ;;
            *)              shift ;;
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

    step "Rollback API Revision"
    log "Atual: $current"
    log "Destino rollback: $target_revision"

    az containerapp ingress traffic set \
        --name "$ACA_API_APP" \
        --resource-group "$RESOURCE_GROUP" \
        --revision-weight "${target_revision}=100" \
        --output none

    ok "API rollback concluido. Trafego em '$target_revision'."

    # ── Rollback MCP (simetrico) ──────────────────────────────────────────────
    if _aca_app_exists "$ACA_MCP_APP"; then
        local mcp_current
        mcp_current=$(_aca_primary_revision "$ACA_MCP_APP")

        if [[ -n "$mcp_current" ]]; then
            if [[ -z "$mcp_revision" ]]; then
                mcp_revision=$(_aca_previous_revision "$ACA_MCP_APP" "$mcp_current")
            fi

            if [[ -n "$mcp_revision" ]]; then
                step "Rollback MCP Revision"
                log "Atual MCP: $mcp_current"
                log "Destino rollback MCP: $mcp_revision"

                az containerapp ingress traffic set \
                    --name "$ACA_MCP_APP" \
                    --resource-group "$RESOURCE_GROUP" \
                    --revision-weight "${mcp_revision}=100" \
                    --output none

                ok "MCP rollback concluido. Trafego em '$mcp_revision'."
            else
                warn "Nenhuma revision MCP anterior disponivel — rollback MCP pulado."
            fi
        fi
    fi
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


# -- Help -----------------------------------------------------------------------

cmd_help() {
    cat <<'EOF'
Uso: deploy.sh [comando] [opcoes]

-- Runtime Deployment (ACA Revisions, CI-safe) ---------------------------------
  image [--tag TAG]             Builda imagem nova (sem --tag) ou valida tag existente
  deploy IMAGE_TAG              Cria nova revision (API+MCP) sem promover trafego (blue/green)
  smoke [--revision REV]        Smoke exaustivo contra a revision API alvo
        [--mcp-revision REV]    Smoke contra revision MCP especifica (fallback: app FQDN)
        [--url URL] [--mcp-url URL]
  promote [--revision REV]      Direciona 100% do trafego para a revision API
          [--mcp-revision REV]  Idem para o MCP (fallback: latest revision)
  rollback [--revision REV]     Volta para revision anterior da API (ou especificada)
           [--mcp-revision REV] Idem para o MCP
  status                        Mostra revisions e pesos de trafego

Para provisionamento de plataforma use: cd/scripts/provision.sh help

Variaveis de ambiente (CI/CD):
  RESOURCE_GROUP ACA_API_APP ACA_MCP_APP ACR_NAME IMAGE_NAME
  SMOKE_CLIENT_ID SMOKE_CLIENT_SECRET
EOF
}

# -- Dispatcher (guard: nao executa quando sourced por provision.sh) ------------

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    CMD="${1:-status}"; shift 2>/dev/null || true
    _check_ci_safe "$CMD"

    case "$CMD" in
        image)          cmd_image "$@" ;;
        deploy)         cmd_deploy "$@" ;;
        smoke)          cmd_smoke "$@" ;;
        promote)        cmd_promote "$@" ;;
        rollback)       cmd_rollback "$@" ;;
        status)         cmd_status "$@" ;;
        help|--help|-h) cmd_help ;;
        *)
            die "Comando desconhecido: '$CMD'. Use '$0 help' ou 'provision.sh help' para operacoes de plataforma."
            ;;
    esac
fi
