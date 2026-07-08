# ADR-122 — Migração de ACI para Azure Container Apps (ACA)

**Status:** ✅ Implementado  
**Data:** 2026-06-23  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-096 (deploy Azure), ADR-099 (RBAC/JWT)

---

## Contexto

O Concilium está hospedado em Azure Container Instances (ACI) com blue-green via Application Gateway pool switching (implementado em `cd/scripts/deploy.sh` e `cd/production/bicep/modules/aci.bicep`).

ACI é adequado para cargas de trabalho pontuais e de curta duração (triggers, jobs únicos). O Concilium, entretanto, precisa de disponibilidade síncrona e semi-contínua:

- A API REST (`concilium-api :8000`) e o servidor MCP (`concilium-mcp :8080`) precisam responder a qualquer momento durante o horário de operação.
- Blue-green em ACI exige troca manual de backend pool no Application Gateway — operação frágil, sem rollback atômico.
- ACI não oferece escalonamento horizontal, health probes configuráveis por revisão, nem gestão de tráfego fracionado nativa.

## Decisão

Migrar de ACI para **Azure Container Apps (ACA)**.

ACA oferece:
- **Revisões** (revisions) com **traffic splitting nativo** — blue-green sem App Gateway pool switching.
- **Escalonamento** por HTTP requests, CPU ou fila (KEDA) — o ACI não escala.
- **Ingress gerenciado** com TLS automático via certificados gerenciados pelo Azure — elimina a dependência do Application Gateway para TLS.
- **Managed Identity** suportada nativamente — sem mudança no modelo de autenticação com Key Vault e Azure Storage.
- Modelo de cobrança por vCPU/hora + memória + requests — mais econômico para cargas semi-contínuas com idle noturno (vs. ACI que cobra 24h mesmo parado).

A política de ativação/desativação do serviço (horário de funcionamento) se beneficia do escalonamento para zero do ACA: configurar `minReplicas=0` fora do horário de operação elimina custo de idle.

## Arquitetura alvo

```
GitHub Actions
    │ build + push
    ▼
Azure Container Registry (conciliumacr)
    │ pull via Managed Identity
    ▼
Azure Container Apps Environment (concilium-env)
    ├── concilium-api  (Container App, ingress externo :443, HTTP/2)
    └── concilium-mcp  (Container App, ingress externo :443, HTTP/2)
    │
    ▼
Azure DNS Zone (mendesloboconstrucao.com.br)
    ├── api.mendesloboconstrucao.com.br → ACA ingress FQDN
    └── mcp.mendesloboconstrucao.com.br → ACA ingress FQDN
```

O Application Gateway é removido da topologia. TLS é gerenciado pelo ingress do ACA.

## Blue-green com revisões ACA

```bash
# Deploy de nova revisão (inativa, 0% tráfego)
az containerapp update \
  --name concilium-api \
  --resource-group concilium-rg \
  --image conciliumacr.azurecr.io/concilium:$NEW_TAG \
  --revision-suffix $NEW_TAG \
  --traffic-weight latest=0

# Smoke tests na revisão inativa via revision-specific FQDN
REVISION_FQDN=$(az containerapp revision show \
  --name concilium-api \
  --resource-group concilium-rg \
  --revision concilium-api--$NEW_TAG \
  --query properties.fqdn -o tsv)
curl https://$REVISION_FQDN/health

# Promoção: 100% tráfego para nova revisão
az containerapp ingress traffic set \
  --name concilium-api \
  --resource-group concilium-rg \
  --revision-weight concilium-api--$NEW_TAG=100

# Desativar revisão anterior
az containerapp revision deactivate \
  --name concilium-api \
  --resource-group concilium-rg \
  --revision concilium-api--$OLD_TAG
```

## Arquivos impactados

| Arquivo | Ação |
|---|---|
| `cd/production/bicep/modules/aci.bicep` | Substituir por módulo ACA (`containerapp.bicep`) |
| `cd/production/bicep/main.bicep` | Referenciar novo módulo ACA; remover app-gateway se TLS gerenciado |
| `cd/scripts/deploy.sh` | Reescrever comandos `az container` → `az containerapp` |
| `/.github/workflows/deploy.yml` | Adaptar steps de deploy/smoke/rollback |
| `cd/production/README.md` | Atualizar topologia e instruções de setup |

## Consequências

**Positivas:**
- Blue-green atômico sem risco de App Gateway misconfiguration.
- Escalonamento para zero fora do horário — reduz custo operacional.
- TLS gerenciado — elimina rotação manual de certificados.
- Rollback instantâneo via traffic weight.

**Negativas / trade-offs:**
- ACA tem cold start (~5-10s) quando `minReplicas=0`. Aceitável fora do horário de operação; configurar `minReplicas=1` durante janela de uso.
- Bicep e deploy.sh precisam ser reescritos (não é migração incremental — ACI e ACA têm APIs distintas).
- ACA Environment tem custo fixo de ~$0.04/hora independente de replicas — planejar no orçamento.
