#!/usr/bin/env bash
# provision.sh — Operações de infraestrutura e provisionamento do Concilium.
#
# Executado manualmente por operadores; não roda em CI rotineiro.
#
# Comandos:
#   configure               Aplica env vars em ambos os containers ACA (idempotente)
#   keys [--rotate]         Gera JWT keys -> Key Vault
#   bootstrap               Provisiona infra Azure base (idempotente)
#     bootstrap --validate    Valida Bicep (build + deployment validate)
#   github                  Configura GitHub Secrets/Vars via gh CLI
#   domain prepare/finalize Custom domain via ARM API (ver domain.sh)
#   exec [comando]          az containerapp exec (sem args: shell interativo)
#   all                     Executa bootstrap -> keys -> github
#
# Diferente de deploy.sh (CI/CD de revisões), provision.sh lida com
# configuração de plataforma, certificados, segredos e DNS — operações
# que mudam raramente e requerem contexto humano.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Carrega utilitários comuns e helpers ACA do deploy.sh (sem executar o dispatcher).
# shellcheck source=./deploy.sh
source "${SCRIPT_DIR}/deploy.sh"

# Carrega comandos de domínio customizado.
# shellcheck source=./domain.sh
source "${SCRIPT_DIR}/domain.sh"

# -- Provisioning commands -------------------------------------------------------

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
          - name: CONCILIUM__SP_SYSTEM_ROOT_PATH
            value: ${SP_SYSTEM_ROOT_PATH:-${SP_ROOT_PATH}/sistema}
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
          - name: CONCILIUM__SP_SYSTEM_ROOT_PATH
            value: ${SP_SYSTEM_ROOT_PATH:-${SP_ROOT_PATH}/sistema}
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
    echo "  Proximos passos: $0 github"
}

cmd_observability_job() {
    need az
    require_login

    [[ -n "$SP_TENANT_ID" ]]     || die "SP_TENANT_ID nao definido."
    [[ -n "$SP_CLIENT_ID" ]]     || die "SP_CLIENT_ID nao definido."
    [[ -n "$SP_CLIENT_SECRET" ]] || die "SP_CLIENT_SECRET nao definido."
    [[ -n "$SP_DRIVE_ID" ]]      || die "SP_DRIVE_ID nao definido."

    # Isolamento sistema vs. projetos (ver sessao "sistema/" no SharePoint) —
    # mesmo default usado na configuracao manual e em cmd_configure.
    local sp_system_root="${SP_SYSTEM_ROOT_PATH:-${SP_ROOT_PATH}/sistema}"

    local env_vars=(
        "CONCILIUM__CONFIG_ROOT=/app"
        "CONCILIUM__STORE_BACKEND=sharepoint"
        "CONCILIUM__SP_TENANT_ID=${SP_TENANT_ID}"
        "CONCILIUM__SP_CLIENT_ID=${SP_CLIENT_ID}"
        "CONCILIUM__SP_CLIENT_SECRET=${SP_CLIENT_SECRET}"
        "CONCILIUM__SP_DRIVE_ID=${SP_DRIVE_ID}"
        "CONCILIUM__SP_ROOT_PATH=${SP_ROOT_PATH}"
        "CONCILIUM__SP_SYSTEM_ROOT_PATH=${sp_system_root}"
        "OTEL_SERVICE_NAME=concilium-observability"
    )

    step "Container Apps Job — '$ACA_OBSERVABILITY_JOB'"

    if _aca_job_exists "$ACA_OBSERVABILITY_JOB"; then
        log "Job ja existe — atualizando imagem/comando/env vars."
        az containerapp job update \
            --name "$ACA_OBSERVABILITY_JOB" \
            --resource-group "$RESOURCE_GROUP" \
            --image "${ACR_NAME}.azurecr.io/${IMAGE_NAME}:latest" \
            --command "concilium" "ops" "observability" "cycle" \
            --set-env-vars "${env_vars[@]}" \
            --output none
    else
        # Bootstrap em 2 fases. A ARM valida sincronamente (na propria chamada
        # de create/update) se a imagem consegue ser puxada com a identidade
        # informada — uma identidade system-assigned so ganha principalId
        # depois que o recurso existe, entao "criar ja com a imagem privada +
        # identidade" sempre falha (chicken-and-egg: AcrPull ainda nao existe
        # no momento da validacao). Fase 1: cria com imagem publica (nao
        # precisa de credencial nenhuma) so pra materializar a identidade.
        # Fase 2: concede AcrPull, espera propagar, e so entao troca pra
        # imagem real + registries — isso via --yaml, pois `job update` nao
        # expõe --registry-identity/--registry-server como flags (so
        # `job create` tem essas Configuration Arguments).
        #
        # (Reusar concilium-identity via --mi-user-assigned + --registry-identity
        # no mesmo `create` foi tentado antes e falhou com IdentityDoesNotExist —
        # bug de ordering na extensao containerapp beta 1.3.0b4 quando a mesma
        # identidade ja esta anexada a outro recurso no resource group. Uma
        # identidade system-assigned nova evita esse bug. O job nao precisa de
        # Key Vault/AZURE_CLIENT_ID — so usa SP_CLIENT_ID/SECRET, MSAL, nao
        # managed identity, pra autenticar no SharePoint.)
        log "Job nao existe — bootstrap fase 1: imagem publica so pra criar a identidade."
        az containerapp job create \
            --name "$ACA_OBSERVABILITY_JOB" \
            --resource-group "$RESOURCE_GROUP" \
            --environment "$ACA_ENV_NAME" \
            --trigger-type Schedule \
            --cron-expression "*/5 * * * *" \
            --replica-timeout 300 \
            --replica-retry-limit 1 \
            --replica-completion-count 1 \
            --parallelism 1 \
            --cpu 0.5 --memory 1.0Gi \
            --image "mcr.microsoft.com/k8se/quickstart:latest" \
            --container-name "$ACA_OBSERVABILITY_JOB" \
            --mi-system-assigned \
            --output none

        local acr_id principal_id
        acr_id=$(az acr show --name "$ACR_NAME" --query 'id' -o tsv)
        principal_id=$(az containerapp job show --name "$ACA_OBSERVABILITY_JOB" --resource-group "$RESOURCE_GROUP" \
            --query 'identity.principalId' -o tsv)

        step "AcrPull -> identidade system-assigned do job"
        az role assignment create \
            --assignee "$principal_id" \
            --role AcrPull \
            --scope "$acr_id" \
            --output none
        ok "AcrPull concedido. Aguardando propagacao RBAC..."
        sleep 45

        log "Bootstrap fase 2: imagem real + registries via --yaml."
        local job_yaml; job_yaml=$(mktemp /tmp/observability-job-XXXXXX.yaml)
        {
            echo "properties:"
            echo "  configuration:"
            echo "    registries:"
            echo "      - server: ${ACR_NAME}.azurecr.io"
            echo "        identity: system"
            echo "  template:"
            echo "    containers:"
            echo "      - name: ${ACA_OBSERVABILITY_JOB}"
            echo "        image: ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:latest"
            echo "        command: [\"concilium\", \"ops\", \"observability\", \"cycle\"]"
            echo "        env:"
            for kv in "${env_vars[@]}"; do
                echo "          - name: ${kv%%=*}"
                echo "            value: \"${kv#*=}\""
            done
        } > "$job_yaml"
        az containerapp job update \
            --name "$ACA_OBSERVABILITY_JOB" \
            --resource-group "$RESOURCE_GROUP" \
            --yaml "$job_yaml" \
            --output none
        rm -f "$job_yaml"
    fi

    ok "Container Apps Job '$ACA_OBSERVABILITY_JOB' configurado."
    echo "  Proximo passo: az containerapp job start --name $ACA_OBSERVABILITY_JOB --resource-group $RESOURCE_GROUP (disparo manual opcional)"
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
    echo "  Proximos passos: $0 configure"
}

cmd_exec() {
    local app_name="${USERS_APP:-$ACA_MCP_APP}"
    local exec_cmd="${*:-}"

    need az
    require_login
    _aca_app_exists "$app_name" || die "Container App '$app_name' nao encontrado."

    step "Gestao de usuarios via ACA exec"
    log "App alvo: $app_name"

    local cmd="${exec_cmd:-/bin/sh}"
    [[ -z "$exec_cmd" ]] && log "Abrindo shell interativo — use 'concilium ops auth --help'"
    [[ -n "$exec_cmd" ]] && log "Comando: $cmd"

    az containerapp exec \
        --name "$app_name" \
        --resource-group "$RESOURCE_GROUP" \
        --command "$cmd" || true
    stty sane 2>/dev/null || true
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
Uso: provision.sh [comando] [opcoes]

-- Plataforma ------------------------------------------------------------------
  bootstrap               Provisiona infra Azure base via Bicep (idempotente)
    bootstrap --validate    Valida templates Bicep sem aplicar
  keys [--rotate]         Gera JWT keys RS256 e grava no Key Vault
  github                  Configura GitHub Secrets/Vars via gh CLI
  configure               Aplica env vars em ambos os containers ACA (idempotente)
  observability-job       Cria/atualiza o Container Apps Job de observabilidade
                          (Bronze->Silver->Gold, trigger Schedule a cada 5min)
  all                     Executa bootstrap -> keys -> github

-- Custom Domain (Human-in-the-Loop) ------------------------------------------
  domain prepare --app APP --hostname HOST
                          Exibe registros DNS necessarios; aguarda ENTER (interativo)
                          Em CI imprime instrucoes e sai (execute finalize manualmente)
  domain finalize --app APP --hostname HOST
                          Reconcia DNS -> Managed Certificate -> binding SNI -> HTTPS

-- Operacoes -------------------------------------------------------------------
  exec [comando]          az containerapp exec (sem args: shell interativo)

Variaveis de ambiente:
  RESOURCE_GROUP LOCATION KV_NAME ACR_NAME IMAGE_NAME
  ACA_API_APP ACA_MCP_APP ACA_ENV_NAME ACA_OBSERVABILITY_JOB GITHUB_REPO
  SP_TENANT_ID SP_CLIENT_ID SP_CLIENT_SECRET SP_DRIVE_ID SP_ROOT_PATH SP_SYSTEM_ROOT_PATH
  SMOKE_CLIENT_ID SMOKE_CLIENT_SECRET SMTP_PASSWORD
  OTEL_EXPORTER_OTLP_ENDPOINT
EOF
}

# -- Dispatcher -----------------------------------------------------------------

CMD="${1:-help}"; shift 2>/dev/null || true

case "$CMD" in
    configure)      cmd_configure "$@" ;;
    observability-job) cmd_observability_job "$@" ;;
    keys)           cmd_keys "$@" ;;
    bootstrap)      cmd_bootstrap "$@" ;;
    github)         cmd_github "$@" ;;
    domain)         cmd_domain "$@" ;;
    exec)           cmd_exec "$@" ;;
    all)            cmd_all "$@" ;;
    help|--help|-h) cmd_help ;;
    *)
        die "Comando desconhecido: '$CMD'. Use '$0 help'."
        ;;
esac
