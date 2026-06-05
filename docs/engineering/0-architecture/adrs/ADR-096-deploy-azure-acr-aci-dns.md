# ADR-096 — Deploy Azure: ACR → ACI → Application Gateway → DNS → Domínio Mendes Lobo

**Status:** APROVADO
**Data:** 2026-05-30
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-094 (JWT Auth), ADR-095 (Observabilidade)

---

## Contexto

### Problema

P1. O Concilium roda hoje como ferramenta CLI/local. O fluxo principal de produção —
criação de projeto via QQP/EAP (ADR-092), execução do pipeline, consulta de artefatos
(ADR-093) — acontece inteiramente no ambiente local do desenvolvedor. Agentes remotos
(Claude Desktop, Copilot) e engenheiros fora da rede local não têm acesso ao MCP server.

P2. Não há URL estável para o serviço. Integrações com agentes externas exigem que
o host local esteja ativo e exposto via túnel (ngrok, etc.) — frágil e inseguro.

P3. Artefatos gerados ficam presos no filesystem local — não compartilháveis com
stakeholders remotos sem envio manual de arquivos.

---

## Decisão

D1. **Topologia de deploy.**

```
[Imagem Docker]
      │
      ▼
Azure Container Registry (ACR)       ← repositório privado de imagens
      │
      ▼
Azure Container Instances (ACI)       ← container serverless (sem K8s)
      │
      ▼
Azure Application Gateway             ← TLS termination + routing
      │
      ▼
Azure DNS Zone                        ← mcp.mendesloboconstrucao.com.br
```

D2. **Por que ACI e não AKS.** ACI é a escolha certa para este estágio:
- Sem overhead de orquestração K8s para serviço de nicho de engenharia
- Billing por segundo (adequado para uso esporádico — pipelines não são contínuos)
- Startup em ~5s vs. provisionar nó de K8s
- Escala vertical simples (vcpu + memória) para picos de pipeline

D3. **Imagem Docker e build pipeline.**

O `Dockerfile` existente no repo é a base. A imagem expõe:
- Porta **8000**: FastAPI REST
- Porta **8080**: FastMCP MCP server

```bash
az acr build --registry conciliumacr \
             --image concilium-mcp:latest \
             --file Dockerfile .
```

D4. **Domínio e DNS.**

```
# Azure DNS Zone: mendesloboconstrucao.com.br
mcp.mendesloboconstrucao.com.br  →  CNAME  →  Application Gateway IP
api.mendesloboconstrucao.com.br  →  CNAME  →  Application Gateway IP
```

D5. **Azure Blob Storage para artefatos.** O `ProjectStore` ganha adapter Azure Blob.
Artefatos são persistidos na nuvem, viabilizando URLs pré-assinadas (ADR-093) e
durabilidade independente do ciclo de vida do container.

D6. **Configuração ACI.**

```yaml
containers:
- name: concilium-mcp
  image: conciliumacr.azurecr.io/concilium-mcp:latest
  resources:
    requests: {cpu: 2.0, memoryInGB: 4.0}
  environmentVariables:
  - name: JWT_SECRET
    secureValue: (Azure Key Vault reference)
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: (Azure Monitor endpoint)
```

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Azure App Service | Overhead de PaaS desnecessário; menos controle de runtime |
| R2 | Azure Kubernetes Service (AKS) | Over-engineering para serviço de nicho com baixo tráfego |
| R3 | VM dedicada | Custo e manutenção inaceitáveis para equipe pequena |
| R4 | Ngrok / túnel local | Não é produção; instável e inseguro |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| URL estável | Agentes e usuários têm endpoint permanente e confiável |
| Escalabilidade | ACI escala verticalmente sem intervenção manual |
| Artefatos na nuvem | URLs pré-assinadas para compartilhamento com stakeholders remotos |
| Domínio próprio | `mcp.mendesloboconstrucao.com.br` reforça identidade da empresa |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Cold start ACI (~5s) pode impactar primeiro request | Warm-up probe no Application Gateway; aceitar latência no deploy |
| Custo de infraestrutura recorrente | ACI paga por execução; escala a zero quando inativo |
| Segredos no container | Azure Key Vault + Managed Identity — sem credenciais em variáveis de ambiente |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Dockerfile production-ready (sem dados locais embutidos) | 🟢 Implementado |
| 2 | ACR e push via GitHub Actions CI/CD | 🟢 Implementado |
| 3 | ACI deployment (container-group.yaml) | 🟢 Implementado |
| 4 | Application Gateway com TLS (cert gerenciado pelo Azure) | 🟢 Bicep pronto — cert TLS requer provisionamento Azure |
| 5 | Azure DNS Zone + CNAME para domínio Mendes Lobo | 🟢 Bicep pronto — NS requer config no Registro.br |
| 6 | Azure Blob Storage adapter para ProjectStore | 🟢 Já existia (AzureBlobStorage adapter) |

## Definition of Done

### Fase 1
- [ ] Dockerfile não contém dados de projetos ou credenciais hardcoded
- [ ] Build local da imagem funciona sem erros

### Fase 2
- [ ] GitHub Actions faz build e push para ACR em merge para main
- [ ] Tag de imagem inclui git SHA

### Fase 3
- [ ] Container rodando em ACI com health check respondendo
- [ ] MCP server acessível internamente na porta 8080

### Fase 4
- [ ] HTTPS funcional via Application Gateway
- [ ] Certificado TLS válido e renovação automática

### Fase 5
- [ ] `mcp.mendesloboconstrucao.com.br` resolve para Application Gateway
- [ ] `api.mendesloboconstrucao.com.br` resolve para Application Gateway

### Fase 6
- [ ] `ProjectStore` persiste artefatos em Azure Blob Storage
- [ ] URLs pré-assinadas funcionais com TTL=15min (ADR-093)

---

## Relacionados

[[adr094-jwt-auth-layer]] [[adr095-observabilidade]]
[[adr093-mcp-artefatos-zip-bundle]]
