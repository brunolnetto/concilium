# Prontidão para Produção — Concilium

**Última revisão:** 2026-06-02  
**ADRs cobertas:** 092, 094, 095, 096, 098, 099  
**Responsável:** Engenharia MendesLobo

---

## O Que Está Pronto

| Capacidade | ADR | Status |
|---|---|---|
| API REST (FastAPI) | ADR-048 | ✅ |
| MCP Server — transport streamable-http | ADR-096 | ✅ |
| Autenticação JWT RS256 | ADR-094 | ✅ Device codes, refresh tokens, proxy |
| RBAC — `@permission` em REST + MCP | ADR-099 | ✅ 6 roles, blast radius por compromisso |
| Rate limiting (SlowAPI) | ADR-098 | ✅ Por usuário JWT, por IP, por endpoint |
| Observabilidade OTEL | ADR-095 | ✅ Traces + métricas, sink configurável |
| Formulário QQP/EAP | ADR-092 | ✅ MCP tool + REST + UI Streamlit |
| Imagem Docker multi-stage | ADR-096 | ✅ Non-root, `.dockerignore` correto |
| Infra Bicep (ACR + ACI + AppGW + DNS + KV) | ADR-096 | ✅ Templates em `cd/production/bicep/` |
| Deploy Blue-Green com rollback automático | — | ✅ `cd/scripts/deploy.sh` |
| GitHub Actions CI/CD | ADR-096 | ✅ Build → canary → smoke → promote\|rollback |
| Azure Blob Storage | ADR-096 | ✅ SAS URLs, Managed Identity |
| `startup_check()` — validação de config | — | ✅ Falha rápido antes de servir |
| Settings centralizado | — | ✅ `settings.py`, 68 vars documentadas |

---

## Entrypoint Único de Deploy

Todos os comandos passam por **`cd/scripts/deploy.sh`**.  
Consulte `cd/scripts/deploy.sh help` para a referência completa.

### Bootstrap (único, feito uma vez pelo operador)

```bash
az login && gh auth login

cd/scripts/deploy.sh bootstrap   # resource group + OIDC + Bicep completo
cd/scripts/deploy.sh keys        # JWT RS256 → Key Vault (sem arquivo em disco)
cd/scripts/deploy.sh tls --upload cert.pfx   # TLS produção
# cd/scripts/deploy.sh tls --self-signed     # staging
cd/scripts/deploy.sh github      # GitHub Secrets (lê Azure automaticamente)
cd/scripts/deploy.sh users       # criar usuários e device codes no ACI
```

> **Único passo manual:** configurar os 4 nameservers no Registro.br com os valores
> impressos pelo `bootstrap` no final. Propagação: 24–48h.

### Deploy contínuo (automático a cada push para `main`)

```bash
# Verificar estado dos slots a qualquer momento:
cd/scripts/deploy.sh status

# Re-deploy manual de uma tag específica:
IMAGE_TAG=abc12345 cd/scripts/deploy.sh deploy abc12345
cd/scripts/deploy.sh smoke --slot green
cd/scripts/deploy.sh promote    # ou rollback

# Rotação de chaves JWT (trimestral):
cd/scripts/deploy.sh keys --rotate
```

---

## Fluxo Blue-Green

```
push para main
     │
     ▼
Build & Push → ACR (imagem:sha8)
     │
     ▼
Deploy slot inativo  ← ACI concilium-cg-green ou -blue
(sem tráfego prod)     Mesmo env que produção, IP direto
     │
     ▼
Smoke exaustivo       ← 9 checks: health, auth, JWT roles,
contra o slot novo       RBAC, rate-limit, MCP, TLS, catálogo
     │
   pass?
  /    \
yes    no
 │      │
 ▼      ▼
promote rollback
App GW  deleta
→ green slot
deleta  prod
blue    intacta
```

**Estado** persiste como tag no Resource Group (`active_slot=blue|green`).  
**Rollback** é instantâneo — App Gateway nunca apontou para o slot novo.

---

## Pipelines Automáticas

| Workflow | Trigger | Jobs |
|---|---|---|
| `deploy.yml` | Push → `main` | `build` → `deploy-green` → `smoke` → `promote` ou `rollback` |
| `infra.yml` | Push → `cd/production/bicep/**` ou manual | `validate` → `deploy-infra` → `setup-jwt-keys` |

### Secrets e Variables necessários no GitHub

| Nome | Tipo | Como obter |
|---|---|---|
| `AZURE_CLIENT_ID` | Secret | `az ad app list --display-name concilium-github-actions --query '[0].appId'` |
| `AZURE_TENANT_ID` | Secret | `az account show --query tenantId` |
| `AZURE_SUBSCRIPTION_ID` | Secret | `az account show --query id` |
| `CONCILIUM__AZURE_KEY` | Secret | `az storage account keys list --account-name conciliumstorage --query '[0].value'` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Secret | Portal → App Insights → Connection String |
| `SMOKE_CLIENT_SECRET` | Secret | Secret do usuário `smoke-test` (criado via `deploy.sh users`) |
| `RESOURCE_GROUP` | Variable | `concilium-rg` |
| `CONCILIUM__AZURE_ACCOUNT` | Variable | `conciliumstorage` |
| `CONCILIUM__AZURE_CONTAINER` | Variable | `concilium-projetos` |

> **Não existe** `JWT_SECRET` — chaves JWT vivem no Key Vault.

---

## Variáveis de Ambiente de Produção

> Fonte de verdade: [`src/concilium/infrastructure/settings.py`](../../src/concilium/infrastructure/settings.py)
>
> O módulo documenta todas as 68 variáveis `CONCILIUM__*` com:
> - **Classificação** — `[opt]`, `[req]`, `[cond]`, `[cloud]`
> - **Default** e domínio (`StorageSettings`, `AuthSettings`, etc.)
> - **Onde cada variável mora** por ambiente:
>   `cd/development/.env.api` · `deploy.yml env:` · `GitHub Secrets` · `Azure Key Vault`
>
> O `deploy.sh deploy` injeta exatamente as variáveis documentadas na seção
> "`.github/workflows/deploy.yml env:`" de `settings.py`.
> Qualquer adição de variável começa lá — não aqui.

---

## Roles e Usuários (RBAC — ADR-099)

| Role | Criado via | Usa para |
|---|---|---|
| `admin` | `deploy.sh users` | Gestão de usuários, configuração |
| `operator` | `deploy.sh users` | Engenheiros — criar e executar projetos |
| `service-ci` | `deploy.sh users` | GitHub Actions — criar + executar, sem dados financeiros |
| `auditor` | `deploy.sh users` | Stakeholders — ler resultados financeiros |
| `viewer` | `deploy.sh users` | Leitura básica sem financeiro |

Distribuir acesso: `concilium auth new-device --user <id> --device <nome-maquina>`  
→ imprime o bloco JSON para o usuário colar em `claude_desktop_config.json`.

---

## Monitoramento e Alertas

Após `OTEL_EXPORTER_OTLP_ENDPOINT` configurado:

| Métrica | Threshold | Prioridade |
|---|---|---|
| `concilium.pipeline.skill.duration_ms` p99 > 30s | P2 | Pipeline lento |
| `concilium.api.rate_limit.exceeded` > 5% em 5min | P2 | Abuso ou ataque |
| `concilium.mcp.tool.calls{status=ERROR}` > 5% em 5min | P1 | Falha funcional |
| ACI CPU > 80% por > 2min | P2 | Escalar verticalmente |

Configurar em: Portal Azure → Monitor → Alerts → Create alert rule.

---

## Operações Recorrentes

```bash
# Rotação de chaves JWT (trimestral)
cd/scripts/deploy.sh keys --rotate

# Revogar dispositivo de um usuário
az container exec --resource-group concilium-rg --name concilium-cg-blue \
  --container-name concilium-api \
  --exec-command "concilium auth revoke-device --device macbook-fulano --yes"

# Verificar estado Blue-Green
cd/scripts/deploy.sh status

# Escalar ACI verticalmente (pico de pipelines)
az container update --resource-group concilium-rg \
  --name concilium-cg-blue --cpu 4 --memory 8

# Renovar certificado TLS (Let's Encrypt — 90 dias)
cd/scripts/deploy.sh tls --upload novo-cert.pfx
```

---

## Riscos Residuais

| Risco | Mitigação |
|---|---|
| Restart ACI invalida refresh tokens | Montar Azure Files em `CONCILIUM__AUTH_DATA_PATH` |
| Propagação DNS > 48h | Testar com `curl --resolve` antes de anunciar |
| TLS expirado (Let's Encrypt 90d) | Configurar alerta de expiração no Key Vault |
| `service-ci` comprometido | RBAC limita a `project:create + project:run`; sem financeiro, sem aprovação |
| IP público no ACI (sem VNet) | Adicionar VNet subnet para ACI em hardening futuro |

---

## Pendências Pós-Deploy

| Item | Prioridade |
|---|---|
| Montar Azure Files para `auth-data` (refresh tokens persistentes entre restarts) | **Alta** |
| Configurar alertas P1/P2 no Azure Monitor | **Alta** |
| Validar ADR-092 Fase 5 com projeto real de produção | **Alta** |
| Renovação automática de TLS (cert-manager ou Azure Key Vault rotation) | Média |
| VNet para ACI (eliminar IP público do container) | Média |
| ADR-097 (Tributação Social) — completar implementação | Média |
| ADR-068 (Calendário Operacional) — implementar | Baixa |
