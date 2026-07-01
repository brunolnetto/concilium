#!/usr/bin/env bash
# domain.sh — Custom domain para ACA via ARM API direta.
# Source a partir de provision.sh; não execute diretamente.
#
# Por que ARM em vez de `az containerapp hostname`?
# A extensão containerapp muda entre releases do az CLI.
# A ARM API 2024-03-01 é GA e estável — é o que Terraform/Bicep usam internamente.
#
# Fluxo:
#   prepare  → exibe registros DNS (CNAME + TXT asuid.*) + aguarda HiL
#   finalize → poll DNS → ARM PATCH (Disabled) → ARM PUT cert → poll → ARM PATCH (SniEnabled)

_ARM_API_VER="2024-03-01"

# -- ARM helpers -----------------------------------------------------------------

_arm_rg_prefix() {
    local sub_id
    sub_id=$(az account show --query id -o tsv 2>/dev/null)
    echo "https://management.azure.com/subscriptions/${sub_id}/resourceGroups/${RESOURCE_GROUP}"
}

_arm_get() {
    az rest --method GET \
        --url "$(_arm_rg_prefix)${1}?api-version=${_ARM_API_VER}" \
        --output json 2>/dev/null
}

_arm_put() {
    az rest --method PUT \
        --url "$(_arm_rg_prefix)${1}?api-version=${_ARM_API_VER}" \
        --body "$2" \
        --output json 2>/dev/null
}

_arm_patch() {
    az rest --method PATCH \
        --url "$(_arm_rg_prefix)${1}?api-version=${_ARM_API_VER}" \
        --body "$2" \
        --output json 2>/dev/null
}

_arm_delete() {
    az rest --method DELETE \
        --url "$(_arm_rg_prefix)${1}?api-version=${_ARM_API_VER}" \
        --output none 2>/dev/null
}

# -- Domain data helpers ---------------------------------------------------------

_dapp()              { _arm_get "/providers/Microsoft.App/containerApps/$1"; }
_denv()              { _arm_get "/providers/Microsoft.App/managedEnvironments/$1"; }
_denv_name()         { echo "$1" | jq -r '.properties.environmentId | split("/") | last'; }
# verificationId vive no Container App, não no Managed Environment
_dverification_id()  { echo "$1" | jq -r '.properties.customDomainVerificationId // empty'; }
_dfqdn()             { echo "$1" | jq -r '.properties.configuration.ingress.fqdn // empty'; }
_dlocation()         { echo "$1" | jq -r '.location'; }
_dcustom_domains()   { echo "$1" | jq -c '.properties.configuration.ingress.customDomains // []'; }
_dhostname_binding() { echo "$1" | jq -r --arg h "$2" '.properties.configuration.ingress.customDomains // [] | .[] | select(.name == $h) | .bindingType // empty'; }
_dhostname_cert_id() { echo "$1" | jq -r --arg h "$2" '.properties.configuration.ingress.customDomains // [] | .[] | select(.name == $h) | .certificateId // empty'; }

# -- Domain workflow helpers -----------------------------------------------------

_domain_dns_poll() {
    local hostname="$1" verification_id="$2" app_fqdn="$3"
    local max=60 i=0

    log "Aguardando propagacao DNS para '$hostname'..."
    while true; do
        i=$((i+1))
        [[ $i -gt $max ]] && die "Timeout DNS (${max}x30s = $((max*30/60))min). Verifique os registros."

        local txt_val cname_val txt_ok=false cname_ok=false
        txt_val=$(dig +short TXT "asuid.${hostname}" 2>/dev/null | tr -d '"' | head -1)
        cname_val=$(dig +short CNAME "${hostname}" 2>/dev/null | sed 's/\.$//' | head -1)

        [[ "$txt_val"   == "$verification_id" ]] && txt_ok=true
        [[ "$cname_val" == "$app_fqdn"        ]] && cname_ok=true

        if $txt_ok && $cname_ok; then
            ok "DNS propagado: TXT e CNAME corretos."
            return 0
        fi

        $txt_ok   || log "  TXT   asuid.${hostname}: esperado='${verification_id}' atual='${txt_val:-<vazio>}'"
        $cname_ok || log "  CNAME ${hostname}: esperado='${app_fqdn}' atual='${cname_val:-<vazio>}'"
        echo "  ($i/$max) Aguardando 30s..."
        sleep 30
    done
}

_domain_set_binding() {
    # PATCH customDomains: substitui (ou insere) a entrada do hostname.
    # $1=app_name $2=hostname $3=entry_json $4=current_domains_json
    local app_name="$1" hostname="$2" entry="$3" current_domains="$4"
    local updated_domains
    updated_domains=$(echo "$current_domains" | jq \
        --arg h "$hostname" --argjson e "$entry" \
        '[.[] | select(.name != $h)] + [$e]')
    local body="{\"properties\":{\"configuration\":{\"ingress\":{\"customDomains\":${updated_domains}}}}}"
    _arm_patch "/providers/Microsoft.App/containerApps/${app_name}" "$body" > /dev/null
}

_domain_poll_hostname_reg() {
    # Aguarda o hostname aparecer em customDomains (consistência eventual do ARM).
    local app_name="$1" hostname="$2"
    local max=18 i=0

    log "Aguardando registro do hostname no ARM..."
    while true; do
        i=$((i+1))
        [[ $i -gt $max ]] && die "Timeout: hostname '${hostname}' nao apareceu em customDomains (${max}x10s)."
        local binding
        binding=$(_dhostname_binding "$(_dapp "$app_name" || true)" "$hostname" 2>/dev/null || true)
        [[ -n "$binding" ]] && { ok "Hostname registrado (bindingType=${binding})."; return 0; }
        echo "  ($i/$max) Aguardando 10s..."
        sleep 10
    done
}

_domain_cert_poll() {
    # Imprime o ARM resource ID do certificado em stdout quando Succeeded.
    # Todo o resto (log/ok/progresso) vai para stderr para não contaminar a captura $().
    local env_name="$1" cert_name="$2"
    local max=36 i=0

    log "Aguardando provisionamento do certificado '${cert_name}'..." >&2
    while true; do
        i=$((i+1))
        [[ $i -gt $max ]] && die "Timeout certificado (${max}x10s = $((max*10/60))min)."

        local result state cert_id
        result=$(_arm_get "/providers/Microsoft.App/managedEnvironments/${env_name}/managedCertificates/${cert_name}" || true)
        state=$(echo "$result" | jq -r '.properties.provisioningState // "Pending"' 2>/dev/null || true)
        cert_id=$(echo "$result" | jq -r '.id // empty')

        if [[ "$state" == "Succeeded" ]]; then
            ok "Certificado provisionado." >&2
            echo "$cert_id"   # único output em stdout
            return 0
        fi
        [[ "$state" == "Failed"   ]] && die "Falha ao provisionar certificado '${cert_name}'."
        [[ "$state" == "Canceled" ]] && die "Certificado '${cert_name}' cancelado pelo Azure."

        echo "  Estado: $state ($i/$max)..." >&2
        sleep 10
    done
}

_domain_verify_https() {
    local hostname="$1"
    local max_v=12 v=0

    # Fase 1: TLS — valida CN do certificado (independe de endpoint HTTP existir).
    if command -v openssl &>/dev/null; then
        local cert_cn
        cert_cn=$(echo | openssl s_client -connect "${hostname}:443" -servername "$hostname" 2>/dev/null \
            | openssl x509 -noout -subject 2>/dev/null \
            | grep -oP 'CN\s*=\s*\K[^,/]+' | tr -d ' ')
        if [[ "$cert_cn" == "$hostname" ]]; then
            ok "TLS: CN=${cert_cn}"
        else
            warn "CN do certificado e '${cert_cn:-<nao lido>}', esperado '${hostname}'."
        fi
    fi

    # Fase 2: HTTP — qualquer resposta do servidor (2xx/3xx/4xx) confirma que o
    # tráfego chegou ao app. Erros de conexão ou TLS ainda falham.
    log "Aguardando resposta HTTP de 'https://${hostname}/'..."
    while true; do
        v=$((v+1))
        local http_status
        http_status=$(curl -sSL --max-time 10 -o /dev/null -w "%{http_code}" "https://${hostname}/" 2>/dev/null || true)
        if [[ "$http_status" =~ ^[2-4][0-9]{2}$ ]]; then
            ok "HTTP ${http_status} — aplicacao respondendo."
            return 0
        fi
        [[ $v -ge $max_v ]] && { warn "Sem resposta HTTP apos ${max_v} tentativas (ultimo status: '${http_status:-erro de conexao}'). TLS esta ativo."; return 0; }
        echo "  ($v/$max_v) status=${http_status:-conn_err} — aguardando 10s..."
        sleep 10
    done
}

# -- Domain commands -------------------------------------------------------------

cmd_domain_prepare() {
    local app_name="" hostname=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --app)      app_name="$2"; shift 2 ;;
            --hostname) hostname="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    [[ -n "$app_name" ]] || app_name="$ACA_API_APP"
    [[ -n "$hostname" ]] || die "--hostname e obrigatorio (ex: api.exemplo.com.br)."

    need az; need jq; require_login
    _aca_app_exists "$app_name" || die "Container App '${app_name}' nao encontrado."

    local app_json env_name verification_id app_fqdn
    app_json=$(_dapp "$app_name")
    env_name=$(_denv_name "$app_json")
    verification_id=$(_dverification_id "$app_json")
    app_fqdn=$(_dfqdn "$app_json")

    [[ -n "$verification_id" ]] || die "Nao foi possivel obter verificationId do app '${app_name}'."

    step "Instrucoes DNS para: $hostname"
    echo
    echo -e "  ${N}Crie os seguintes registros no seu provedor DNS (ex: HostGator):${NC}"
    echo
    printf "  %-8s %-42s %s\n" "Tipo" "Nome" "Valor"
    printf "  %-8s %-42s %s\n" "────" "──────────────────────────────────────────" "─────────────────────────────────────────"
    printf "  ${G}%-8s${NC} %-42s %s\n" "CNAME" "${hostname}."        "${app_fqdn}."
    printf "  ${G}%-8s${NC} %-42s %s\n" "TXT"   "asuid.${hostname}."  "${verification_id}"
    echo
    echo "  App:       $app_name"
    echo "  Ambiente:  $env_name"
    echo

    if [[ "${CI:-}" == "true" ]]; then
        log "Modo CI — instrucoes exibidas. Execute quando o DNS estiver pronto:"
        echo "  cd/scripts/provision.sh domain finalize --app $app_name --hostname $hostname"
        return 0
    fi

    read -r -p "  Pressione ENTER quando os registros DNS estiverem criados (Ctrl+C para cancelar)... "
    echo
    cmd_domain_finalize --app "$app_name" --hostname "$hostname"
}

cmd_domain_finalize() {
    # Reconciliador declarativo: observa o estado atual e avança apenas os passos
    # que ainda não convergiram. Idempotente — pode ser reexecutado após falha.
    local app_name="" hostname=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --app)      app_name="$2"; shift 2 ;;
            --hostname) hostname="$2"; shift 2 ;;
            *)          shift ;;
        esac
    done

    [[ -n "$app_name" ]] || app_name="$ACA_API_APP"
    [[ -n "$hostname" ]] || die "--hostname e obrigatorio."

    need az; need jq; need dig; require_login
    _aca_app_exists "$app_name" || die "Container App '${app_name}' nao encontrado."

    # -- Observar estado inicial --------------------------------------------------
    local app_json env_name app_fqdn location verification_id
    app_json=$(_dapp "$app_name")
    env_name=$(_denv_name "$app_json")
    app_fqdn=$(_dfqdn "$app_json")
    location=$(_dlocation "$app_json")
    verification_id=$(_dverification_id "$app_json")   # lido do Container App, não do Env

    [[ -n "$verification_id" ]] || die "customDomainVerificationId nao encontrado no app '${app_name}'."

    local cert_name="cert-$(echo "$hostname" | tr '.' '-')"
    local cert_path="/providers/Microsoft.App/managedEnvironments/${env_name}/managedCertificates/${cert_name}"

    # -- Passo 1: DNS -------------------------------------------------------------
    step "1/4 — DNS"
    _domain_dns_poll "$hostname" "$verification_id" "$app_fqdn"

    # -- Passo 2: hostname binding (Disabled) — idempotente ----------------------
    step "2/4 — Hostname binding"
    app_json=$(_dapp "$app_name")
    local current_binding
    current_binding=$(_dhostname_binding "$app_json" "$hostname")

    if [[ -z "$current_binding" ]]; then
        _domain_set_binding "$app_name" "$hostname" \
            "{\"name\":\"${hostname}\",\"bindingType\":\"Disabled\"}" \
            "$(_dcustom_domains "$app_json")"
        _domain_poll_hostname_reg "$app_name" "$hostname"
    else
        ok "Hostname ja registrado (bindingType=${current_binding})."
    fi

    # -- Passo 3: Managed Certificate — idempotente ------------------------------
    step "3/4 — Managed Certificate"
    local cert_result cert_state cert_id
    log "Consultando estado do certificado '${cert_name}'..."
    cert_result=$(_arm_get "$cert_path" || true)
    cert_state=$(echo "$cert_result" | jq -r '.properties.provisioningState // empty' 2>/dev/null || true)
    log "Estado atual: '${cert_state:-<nao existe>}'"

    if [[ "$cert_state" == "Succeeded" ]]; then
        cert_id=$(echo "$cert_result" | jq -r '.id')
        ok "Certificado ja existe e esta provisionado."
    else
        if [[ "$cert_state" == "Failed" ]] || [[ "$cert_state" == "Canceled" ]]; then
            log "Certificado em estado '${cert_state}' — recriando..."
            _arm_delete "$cert_path"
            sleep 5
        fi
        local cert_body="{\"location\":\"${location}\",\"properties\":{\"subjectName\":\"${hostname}\",\"domainControlValidation\":\"CNAME\"}}"
        log "Criando Managed Certificate via ARM PUT..."
        if ! _arm_put "$cert_path" "$cert_body" > /dev/null; then
            die "ARM PUT falhou para o certificado '${cert_name}'. Verifique az rest manualmente."
        fi
        log "ARM PUT enviado — aguardando provisionamento..."
        cert_id=$(_domain_cert_poll "$env_name" "$cert_name")
    fi

    # -- Passo 4: binding SniEnabled — idempotente --------------------------------
    step "4/4 — Bind SniEnabled"
    app_json=$(_dapp "$app_name")
    local current_cert_id
    current_cert_id=$(_dhostname_cert_id "$app_json" "$hostname")

    if [[ "$current_cert_id" == "$cert_id" ]]; then
        ok "SNI ja configurado para '${hostname}'."
    else
        _domain_set_binding "$app_name" "$hostname" \
            "{\"name\":\"${hostname}\",\"bindingType\":\"SniEnabled\",\"certificateId\":\"${cert_id}\"}" \
            "$(_dcustom_domains "$app_json")"
        ok "Certificado vinculado a '${hostname}'."
    fi

    # -- Verificacao HTTPS + CN --------------------------------------------------
    step "Verificacao HTTPS"
    _domain_verify_https "$hostname"

    ok "Dominio '${hostname}' configurado e ativo."
}

cmd_domain() {
    local subcmd="${1:-help}"; shift 2>/dev/null || true
    case "$subcmd" in
        prepare)  cmd_domain_prepare  "$@" ;;
        finalize) cmd_domain_finalize "$@" ;;
        *)
            echo "Uso: provision.sh domain <prepare|finalize> [opcoes]"
            echo
            echo "  prepare  --app APP --hostname HOST   Exibe DNS; aguarda ENTER (nao-CI)"
            echo "  finalize --app APP --hostname HOST   Poll DNS, ARM cert, bind, HTTPS"
            ;;
    esac
}
