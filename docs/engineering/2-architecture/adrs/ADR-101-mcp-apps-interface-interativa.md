# ADR-101 — MCP Apps: Interface Interativa de Relatórios e Formulários no Chat

**Status:** Parcialmente Implementado — Fases 1–2 ✅ | Fases 3–5 🔴 Proposta _(auditado 2026-06-08)_
**Data:** 2026-06-03

> **Nota de auditoria (2026-06-08):** Apps MCP confirmados em
> `src/concilium/presentation/mcp/apps/`: `formulario-qqp/`, `dashboard-resultado/`,
> `diagnostico-pe/`, `artefatos/`. Status já estava correto; confirmado via filesystem.
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-092 (Formulário QQP/EAP), ADR-093 (Artefatos MCP), ADR-096 (Deploy Azure), ADR-099 (RBAC)

---

## Contexto

### Problema

P1. **Entregáveis do Concilium chegam ao usuário como texto ou arquivos anexos.**
O fluxo atual — `avancar_pipeline` → `listar_artefatos` → `baixar_bundle_zip` — é adequado
para automação mas frustrante para o engenheiro de campo que precisa explorar resultados
interativamente: tabelas de planejamento, gráficos de cronograma, diagnósticos de
ponto de equilíbrio. Texto não é suficiente; Excel com download é tedioso.

P2. **O formulário QQP/EAP (ADR-092) é uma sequência de perguntas em texto.**
Criar um projeto por `criar_projeto_formulario` exige que o agente faça perguntas
uma a uma ou o usuário preencha um formulário Streamlit separado. Não há forma de
apresentar o formulário completo — com validação, defaults, busca semântica de CPU
e preview da EAP — diretamente no chat onde a conversa está acontecendo.

P3. **Análise de cenários exige iteração visual.**
Diagnóstico de ponto de equilíbrio, ajuste de levers (reduzir equipe, mudar regime
de trabalho, trocar CPU) e impacto no resultado financeiro precisam de feedback
imediato. Hoje isso é feito via múltiplas chamadas `avancar_pipeline` + texto —
sem contexto visual acumulado.

P4. **Entrega de artefatos ricos (PDF, Gantt, planilha) requer download.**
O usuário sai do chat para abrir o arquivo, perde o contexto da conversa e não pode
interagir com os dados (zoom no Gantt, filtro na tabela, drill-down no cubo analítico).

---

## Decisão

D1. **Adotar MCP Apps como canal de entrega de interfaces interativas.**

MCP Apps é uma extensão oficial do protocolo MCP que permite a tools declarar um
`_meta.ui.resourceUri` apontando para um recurso `ui://` no servidor. O host
(Claude Desktop, Claude.ai, VS Code Copilot) renderiza o recurso em um iframe
sandboxado diretamente no chat.

```
Tool description:
  _meta.ui.resourceUri = "ui://concilium/formulario-qqp"

Fluxo:
  1. Host precarrega o recurso ui://
  2. Agente chama a tool
  3. Host renderiza HTML/JS no iframe sandboxado
  4. App ↔ Host: JSON-RPC via postMessage
  5. App chama tools do servidor (ex: buscar_cpu, criar_projeto)
  6. Host roteia para o MCP server existente
```

D2. **Quatro apps prioritários, em ordem de valor.**

**App 1 — Formulário QQP/EAP interativo** (`ui://concilium/formulario-qqp`)
Substitui `criar_projeto_formulario` por um formulário completo no chat:
- Seção 1: Identificação do projeto (nome, tipo, localização, datas, regime)
- Seção 2: QQP dinâmico — lista de serviços + busca semântica de CPU em tempo real
- Seção 3: Preview da EAP gerada antes de criar o projeto
- Seção 4: Confirmação e criação via `criar_projeto_formulario`

**App 2 — Dashboard financeiro** (`ui://concilium/dashboard-resultado`)
Renderiza o resultado pós-`08-consolidacao-financeira`:
- Cubo analítico interativo (face por natureza/atividade/insumo)
- Tabela de planejamento com filtros e ordenação
- Gráficos de curva S, fluxo de caixa, composição de custos
- Atualiza ao chamar `avancar_pipeline` (push do host para o app)

**App 3 — Diagnóstico de ponto de equilíbrio** (`ui://concilium/diagnostico-pe`)
Interface de levers interativos:
- Sliders para num_equipes, horas_dia, dias_semana, objetivo_pool
- Impacto calculado em tempo real via `simular_impacto_replan`
- Exibe fe_nec, gap_pool, ações recomendadas
- Botão "Aplicar" chama `aplicar_sugestao_replan`

**App 4 — Visualizador de artefatos** (`ui://concilium/artefatos`)
Viewer inline para:
- PDF do relatório (pan/zoom sem download)
- Gantt interativo do cronograma (expandir atividades, filtrar por equipe)
- Excel preview (navegar abas)

D3. **Protocolo: dialect JSON-RPC via postMessage.**

O app comunica-se com o host via `postMessage`. O SDK oficial é
`@modelcontextprotocol/ext-apps` mas o protocolo pode ser implementado em vanilla JS.
O servidor MCP existente (FastMCP, porta 8080) serve os recursos `ui://` como HTML/JS.

```python
# No MCP server — registrar recursos ui://
@server.resource("ui://concilium/formulario-qqp")
async def serve_formulario_app() -> ResourceContents:
    html = (Path(__file__).parent / "apps" / "formulario" / "index.html").read_text()
    return ResourceContents(
        uri="ui://concilium/formulario-qqp",
        mimeType="text/html",
        text=html,
    )

# Na tool existente — adicionar _meta.ui
@server.tool()
def criar_projeto_formulario(...) -> dict:
    """Cria projeto a partir de QQP."""
    # lógica existente inalterada
    ...
```

D4. **Tool descriptions declaram `_meta.ui` para tools com app associado.**

```python
# Ferramenta com suporte a MCP App
criar_projeto_formulario._meta = {
    "ui": {
        "resourceUri": "ui://concilium/formulario-qqp",
        "permissions": [],
        "csp": {"default-src": ["'self'", "https://cdn.jsdelivr.net"]},
    }
}
```

D5. **Apps são build targets separados do servidor MCP.**

Cada app é um SPA (Single Page Application) bundled como HTML único autocontido.
O bundle inclui JS e CSS inline para evitar dependências externas, exceto CDN
explicitamente listado em `csp`. Frameworks suportados: React, Vue, Svelte, vanilla JS.

```
src/concilium/presentation/mcp_server/apps/
  formulario-qqp/
    src/          ← código fonte (React/Vanilla)
    dist/
      index.html  ← bundle final (HTML + JS + CSS inline)
  dashboard-resultado/
    ...
```

D6. **Segurança: iframe sandboxado + RBAC do servidor.**

O host renderiza os apps em iframe com `sandbox="allow-scripts allow-same-origin"`.
O app não pode acessar o DOM do host, cookies ou navegação. Chamadas de tool via
postMessage passam pelo mesmo `McpAuthMiddleware` (ADR-099) — um app não eleva
privilégios além do token do usuário.

D7. **Clientes suportados atuais.**

Claude Desktop, Claude.ai, VS Code GitHub Copilot, Goose, Postman — todos listados
no client matrix oficial. O MCP server em Azure (ADR-096) serve os recursos `ui://`
via HTTP transport (`streamable-http`).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| R1 | Streamlit standalone (ADR-048) | Usuário sai do chat; sem bidirectional data flow; auth separada |
| R2 | Retornar HTML como texto na resposta | Hosts não renderizam HTML em mensagens; sem comunicação bidirecional |
| R3 | Link para dashboard externo | Contexto perdido; auth separada; não integra com tools existentes |
| R4 | Embeds via `image/png` base64 | Estático, sem interatividade; não aceita inputs do usuário |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| UX dramatically better | Engenheiro de campo cria projeto e vê resultado sem sair do chat |
| Zero mudança nas tools existentes | `_meta.ui` é aditivo — tools sem app continuam funcionando normalmente |
| Reutiliza infra existente | FastMCP em Azure já serve HTTP; só adicionamos recursos `ui://` |
| Bidirectional data flow grátis | App chama tools do servidor pelo mesmo canal JWT autenticado |
| Context preservation | Dashboard fica no mesmo thread da conversa que gerou o projeto |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Suporte por host não universal | Hosts sem suporte recebem só o resultado textual da tool — sem regressão |
| Manutenção de dois frontends (Streamlit + MCP Apps) | MCP Apps substitui gradualmente Streamlit para os fluxos agenticos; Streamlit fica para humanos diretos |
| Bundle size: apps grandes degradam cold start | Build com tree-shaking; bundle < 500KB por app; recursos externos via CDN |
| Breakage em updates do protocolo MCP Apps (ainda em extensão) | Versionar apps no `resourceUri`: `ui://concilium/formulario-qqp/v1` |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| 1 | Servidor de recursos `ui://` no FastMCP + `_meta.ui` em tools | ✅ Implementado |
| 2 | App 1: Formulário QQP/EAP interativo (vanilla JS) | ✅ Implementado |
| 3 | App 2: Dashboard financeiro com cubo analítico | 🔴 Proposta |
| 4 | App 3: Diagnóstico de ponto de equilíbrio com levers | 🔴 Proposta |
| 5 | App 4: Visualizador de artefatos (PDF, Gantt, Excel) | 🔴 Proposta |

## Definition of Done

### Fase 1
- [ ] `server.resource("ui://concilium/...")` registrado e servindo HTML
- [ ] `criar_projeto_formulario` declara `_meta.ui.resourceUri`
- [ ] Host renderiza placeholder HTML ao chamar a tool no Claude Desktop
- [ ] Teste: recurso `ui://` acessível via `/mcp` endpoint em staging

### Fase 2
- [ ] Formulário QQP com 3 seções funcionais no iframe
- [ ] Busca semântica de CPU chama `buscar_cpu` via postMessage
- [ ] Criação de projeto chama `criar_projeto_formulario` via postMessage
- [ ] App funciona em Claude Desktop e Claude.ai

### Fase 3
- [ ] Dashboard renderiza resultado de `08-consolidacao-financeira`
- [ ] Gráficos de cubo analítico interativos (filtro por face/medida)
- [ ] Host push: dashboard atualiza ao receber novo resultado de `avancar_pipeline`

### Fase 4
- [ ] Sliders de levers chamam `simular_impacto_replan` em tempo real
- [ ] "Aplicar" chama `aplicar_sugestao_replan` e fecha o app

### Fase 5
- [ ] PDF renderizado com pan/zoom via PDF.js
- [ ] Gantt interativo com drill-down por atividade
- [ ] Excel preview com navegação de abas

---

## Relacionados

[[adr092-formulario-qqp-eap]] [[adr093-mcp-artefatos-zip-bundle]]
[[adr096-deploy-azure-acr-aci-dns]] [[adr099-rbac-roles-permissoes]]
