# ADR-143 — Visibilidade de Usuários entre Roles

**Status:** Implementado
**Data:** 2026-07-20
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-099 (RBAC — Roles e Permissões), ADR-117 (RBAC por Decorator), ADR-120 (RBAC de Catálogo — precedente de permissão granular por ação), ADR-123/131/134 (sistema de notificação — usa os mesmos registros de `ClientRecord`), ADR-118 (Auditoria de Invocações MCP — trilha passiva de quem consultou quem), ADR-140/141 (critério atômico vs. digest — aplicado à notificação do usuário consultado)

---

## Contexto

### Problema

P1. **Hoje não existe, em nenhuma camada com RBAC de token (MCP/API), nenhuma forma de um usuário autenticado ver outros usuários do sistema.** A única listagem existente é o comando administrativo `concilium ops auth list-users` (`presentation/cli/commands_auth.py:417-444`), que chama `get_auth_store().list_clients()` diretamente, **sem nenhum decorator `@permission`/`@roles`**, e sempre retorna todos os registros do store sem filtro. O controle de acesso aqui não é RBAC — é apenas "quem tem acesso ao terminal/máquina onde a CLI roda".

P2. **As únicas tools MCP relacionadas a identidade são estritamente self-service.** Em `presentation/mcp/tools/auth_self.py`: `ativar_dispositivo` (`AUTH_PUBLIC`), `renovar_token` (`AUTH_PUBLIC`), `listar_meus_dispositivos` (`AUTH_SELF`) e `revogar_meu_dispositivo` (`AUTH_SELF`) — todas escopadas ao próprio `client_id` resolvido do JWT via `get_current_user_id()`. Nenhuma expõe informação sobre outro usuário. Não existe endpoint REST equivalente em `presentation/api/routes/auth.py` (que só tem `/token`, `/device/activate`, `/token/refresh`, `/token/issue`, `/revoke-pending`, `/revoke-confirm`).

P3. **`permission_guard.py` não modela visibilidade de identidade, só ação sobre recursos de domínio.** As 19 permissões atuais (`PROJECT_*`, `ARTIFACTS_*`, `CATALOG_*`, `FINANCIALS_READ`, `AUTH_MANAGE`, `AUTH_SELF`, `AUTH_PUBLIC`, `SYSTEM_READ`, `HEALTH_READ`) controlam o que um role pode *fazer*, nunca o que um role pode *ver de outro usuário*. `ROLE_PERMISSIONS` (linha 102) e `ROLE_ALLOWED_INTENTS` (linha 115) são os únicos dois mapas role→algo hoje; não há um terceiro para visibilidade.

P4. **`ClientRecord` (`auth_store.py:56-66`) não tem campo de agrupamento além de `roles: list[str]`.** Os 5 roles técnicos atuais são `operator`, `engineer`, `admin`, `auditor`, `catalog-manager` (ADR-099/ADR-120) — não correspondem 1:1 aos 5 papéis de negócio usados na comunicação com stakeholders (TI, Comercial, Engenharia, Suprimentos, Auditoria; ver apresentação `docs/product/2-presentations/2026-07-17/`). Qualquer visibilidade baseada em role hoje opera sobre os nomes técnicos, não sobre os nomes de negócio.

P5. **É plausível que usuários do mesmo grupo de trabalho precisem identificar uns aos outros** — ex.: Engenharia querendo saber quem mais tem esse papel para dividir a revisão de um rascunho de catálogo, ou um operator descobrindo para quem encaminhar um handoff (H2/H3 do fluxo de handoffs já mapeado na apresentação técnica). Hoje essa necessidade não tem nenhuma via de atendimento dentro do sistema — só perguntando manualmente a alguém com acesso à CLI administrativa.

P6. **Ver o registro de outro usuário levanta uma questão de reciprocidade: o usuário consultado deveria ficar sabendo que foi consultado?** Dispositivos (`RefreshTokenRecord`, `auth_store.py:110-141`) nunca devem circular entre usuários — são dados estritamente self-service (`AUTH_SELF`, já escopados ao próprio `client_id`) e vivem num registro separado do `ClientRecord`, então nem chegam a ser candidatos a expor em D3. Mas notificar o usuário consultado a cada consulta, por email, reproduziria exatamente o problema de fadiga que o ADR-140 já mapeou (P2 daquela ADR): um mesmo destinatário pode ser consultado por vários observadores em pouco tempo, e o evento-gatilho (ser consultado) não é uma ação humana distinta e intencional do próprio destinatário — é subproduto da leitura de outra pessoa.

### Escopo

Esta ADR define **se e como** um usuário autenticado pode listar/ver outros usuários do sistema via MCP/API, com visibilidade escopada por role — não a listagem administrativa irrestrita que já existe na CLI (fora de escopo, P1, ver D6).

**Nota de implementação (2026-07-20):** todos os pontos antes marcados [A DECIDIR] foram validados em conversa direta com o usuário e implementados nesta mesma entrada — não houve uma fase F2 separada de validação. Ver arquivos por decisão nas notas de cada seção abaixo.

---

## Decisão

### D1 — Nova permissão dedicada, não reaproveitar `AUTH_MANAGE`/`AUTH_SELF`

Introduzida a permissão granular `AUTH_LIST_VISIBLE = "auth:list-visible"` (`permission_guard.py`), distinta de `AUTH_MANAGE` (gestão administrativa plena de usuários, hoje só `admin`) e de `AUTH_SELF` (self-service sobre o próprio registro, todos os roles). Concedida a todos os 5 roles (`_OPERATOR`, herdada por `engineer`/`admin`; `_CATALOG_MANAGER`; `_AUDITOR`) — a matriz de D2 é quem filtra o quê cada um vê, não esta permissão (que só decide se pode chamar a tool).

### D2 — Matriz de visibilidade por role, análoga a `ROLE_PERMISSIONS`

Implementada `ROLE_VISIBILITY: dict[str, frozenset[str]]` em `permission_guard.py` + helper `visible_roles_for(roles)` (união para tokens multi-role), mapeando role do observador → conjunto de roles que ele pode ver:

| Observador | Vê os roles |
|---|---|
| `admin` | todos (`operator`, `engineer`, `admin`, `auditor`, `catalog-manager`) |
| `auditor` | todos (leitura ampla já é o papel do auditor — `FINANCIALS_READ`, `PROJECT_READ` sem restrição de escopo) |
| `engineer` | `engineer`, `admin` (colegas de papel + quem aprova/administra) |
| `operator` | `operator`, `engineer`, `admin` (fluxo RFI→RFP: precisa saber para quem encaminhar) |
| `catalog-manager` | `catalog-manager`, `admin` (fluxo de 4 olhos: colegas + quem administra) |

Validada com o usuário sem alterações nesta entrada.

### D3 — Campos expostos: subconjunto seguro, nunca o `ClientRecord` completo, nunca dispositivos

A resposta de qualquer tool/endpoint de visibilidade nunca inclui `secret_hash`, `client_code_hash` nem `notes` (podem conter informação administrativa sensível) e **nunca inclui dispositivos** — `RefreshTokenRecord`/`list_devices()` (`auth_store.py:110-141,467`) permanece estritamente self-service (`AUTH_SELF`), fora do alcance de qualquer outro usuário, mesmo `admin` via esta tool (gestão de dispositivo de terceiro já é coberta por fluxo administrativo separado, ADR-123/131). Campos implementados (`application/services/visibility_service.py::list_visible_users`): `client_id`, `email`, `roles`, `active`. **Email exposto sem mascaramento** — decisão explícita do usuário ("apenas sobre seus roles ou mesmo e-mail para acesso"): o propósito da tool é justamente permitir contato entre roles, mascarar o email anularia essa finalidade. Sem `created_at`/`deleted_at`. Exclui sempre o próprio chamador e clients soft-deleted (`deleted_at`).

### D4 — Implementação como nova MCP tool + endpoint REST espelhado

Seguindo o padrão de `auth_self.py` (ADR-123/117): tool `listar_usuarios_visiveis` (`presentation/mcp/tools/auth_directory.py`), gated por `@permission("auth:list-visible")`, que resolve o(s) role(s) do JWT do chamador, expande via `ROLE_VISIBILITY` o conjunto de roles visíveis, filtra `get_auth_store().list_clients()` por esse conjunto e projeta os campos de D3. Endpoint REST equivalente `GET /auth/users/visible` (`presentation/api/routes/auth.py::list_visible_users_route`) para paridade com o padrão MCP/API dual já estabelecido no resto do sistema. Lógica de filtragem/projeção compartilhada em `application/services/visibility_service.py` — nenhuma das duas camadas de apresentação duplica a regra.

### D5 — Fonte única de verdade: `permission_guard.py`

`ROLE_VISIBILITY` fica no mesmo módulo que `ROLE_PERMISSIONS`/`ROLE_ALLOWED_INTENTS`, não duplicada em `auth_store.py` nem na camada de apresentação — mantém o precedente de fonte única de verdade para regras de role (ADR-099, ADR-117).

### D6 — CLI `list-users` administrativa permanece inalterada

O comando `concilium ops auth list-users` continua fora do RBAC de token — é ferramenta operacional para quem já tem acesso ao servidor/CLI (tipicamente TI/admin), não ao alcance de usuários finais via MCP/API. Esta ADR não introduz restrição nem expande esse comando; trata exclusivamente da nova via de visibilidade via token (D1-D4).

### D7 — Notificação do usuário consultado: critério do ADR-140 aplica-se, exige agregação

Ser consultado por outro usuário se enquadra em D1(d)/(e) do ADR-140: é subproduto da ação de leitura de terceiro (não uma ação humana distinta do próprio destinatário), e o mesmo destinatário pode acumular várias consultas de observadores diferentes em pouco tempo. **Não há notificação atômica por consulta individual** — reproduziria exatamente a fadiga que o critério do ADR-140 existe para prevenir. Duas vias, ambas implementadas, não excludentes:

a. **Trilha passiva via auditoria (ADR-118):** toda chamada à tool `listar_usuarios_visiveis` já fica registrada em `ToolInvocation` (ator, timestamp), sem nenhum código novo de notificação — suficiente para reconstruir "quem me consultou" sob demanda, sem incomodar ninguém.
b. **Digest periódico (opt-in):** `enviar_digest_visibilidade()` (`application/services/visibility_digest_service.py`) drena `AuthStore.pop_pending_visibility_queries()`, agrupa por alvo e envia um resumo agregado ("observer_id (roles) — Nx") por destinatário ativo com email cadastrado — nunca por consulta individual. Eventos são gravados por `AuthStore.record_visibility_queries()` a cada chamada de `list_visible_users` (`application/services/visibility_service.py`), um registro por (observador, alvo) — self-queries nunca são registradas.

### D8 — Mecanismo do digest: intervalo curto com time-gating por conteúdo novo, não o job de observability

Reaproveita o *padrão* já decidido no ADR-140 D3 (thread com `Event.wait(intervalo)`, precedente `JobService._garbage_collector_loop`/`DraftDigestScheduler`), não um componente novo: `VisibilityDigestScheduler` (`application/services/visibility_digest_scheduler.py`) — intervalo padrão **300s (5min)**, configurável via `CONCILIUM__VISIBILITY_DIGEST_INTERVAL_SECONDS` (`infrastructure/settings/_visibility_digest.py`), bem menor que o digest de catálogo (ADR-141, 24h) — cadência sugerida pelo usuário por analogia ao job `concilium-observability`, que roda a cada 5min. O gatilho de envio não é o tick do timer, é **time-gating por conteúdo**: `pop_pending_visibility_queries()` drena o store e só envia (`enviar_digest_visibilidade`) quando há eventos pendentes — sem pendências, não consulta `list_clients()` nem chama `NotificationService.send()` (mesmo silêncio do ADR-141 D4). Desligado por padrão (`CONCILIUM__VISIBILITY_DIGEST_ENABLED=False`), iniciado apenas em `app.py::main()` (nunca em `create_app()`, mesma convenção do ADR-141 D6).

**Não reaproveita o job `concilium-observability` em si**: ele tem responsabilidade única e já testada (ciclo Bronze/Silver/Gold do pipeline de dados), rodando como Azure Container Apps Job com trigger de `Schedule` (`cd/scripts/provision.sh:340`, `--cron-expression "*/5 * * * *"`, processamento internamente time-gated em `pipeline.py:227`) — misturar "enviar digest de visibilidade de usuários" nesse mesmo job/comando acoplaria dois domínios sem relação. `VisibilityDigestScheduler` é um scheduler in-process próprio, seguindo o mesmo padrão de thread já estabelecido (ADR-140/141), só que reaproveitando a mesma *ideia* de time-gating por conteúdo do job de observability, não o job.

**Simplificação assumida**: se o envio do email falhar para um alvo (SMTP indisponível), os eventos daquele lote já foram drenados do store e são perdidos — não há retry nem persistência do que falhou. Aceitável dado que o digest é um "aviso sem ação necessária" (D7b), não um alerta crítico; ver risco correspondente em Consequências.

### D9 — Regra de referência: quando notificar terceiro sobre visibilidade

Resolvido nesta mesma entrada: o digest (D7b) foi habilitado como funcionalidade opt-in (desligada por padrão, D8), não deferida para ADR futura — a via (a) (auditoria passiva via ADR-118) continua como baseline mínimo sem nenhuma configuração adicional.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter o estado atual (nenhuma visibilidade via MCP/API) | Deixa sem resposta a necessidade real descrita em P5; usuário só descobre quem mais está no sistema perguntando informalmente a quem tem acesso à CLI |
| A2 | Visibilidade total — qualquer usuário autenticado vê todos os outros usuários | Vaza informação de composição de equipe/roles sem necessidade de negócio clara (ex. Suprimentos vendo a lista completa de contas de Comercial); contradiz o princípio de menor privilégio já seguido em `permission_guard.py` |
| A3 | Reaproveitar `AUTH_MANAGE` para gatear a nova tool | Obrigaria conceder acesso administrativo pleno (criar/editar/remover usuário) só para habilitar visibilidade — permissão desproporcional ao caso de uso |
| A4 | Adicionar campo de "área"/"departamento" de negócio em `ClientRecord` antes de decidir visibilidade | Fora de escopo desta ADR — a matriz de visibilidade pode ser modelada só com os 5 roles técnicos já existentes; introduzir um campo novo é uma extensão futura independente, não pré-requisito |
| A5 | Expandir a CLI `list-users` com um novo filtro por role, em vez de nova tool MCP/API | Não resolve o problema — a CLI é inacessível ao usuário final (roda no servidor/terminal administrativo), que é exatamente quem precisa dessa visibilidade (P5) |
| A6 | Notificar por email a cada consulta individual (atômico) | Viola o critério do ADR-140 D1(d)/(e) — o mesmo destinatário pode ser consultado por múltiplos observadores em pouco tempo, gerando fadiga; é exatamente o caso que motivou o critério atômico-vs-digest daquela ADR |
| A7 | Reaproveitar o job `concilium-observability` (ACA Scheduled Job, ADR-112) para também disparar o digest de visibilidade | Acopla dois domínios sem relação (pipeline de observabilidade vs. notificação de identidade) só porque ambos têm cadência curta; o padrão de time-gating desse job vale como precedente (D8), mas o job em si mantém responsabilidade única |
| A8 | Expor dispositivos de outros usuários a `admin` via a nova tool, já que `admin` tem `AUTH_MANAGE` | Rejeitada mesmo para `admin` — gestão de dispositivo de terceiro já tem fluxo administrativo próprio (ADR-123/131); misturar isso na tool de visibilidade (cujo propósito é descoberta leve de contato) amplia desnecessariamente o escopo de dados expostos |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha um gap real sem abrir a superfície inteira | Resolve P5 sem reproduzir o problema de A2 (vazamento de informação) |
| Reaproveita o padrão arquitetural existente | `ROLE_VISIBILITY` espelha `ROLE_PERMISSIONS`/`ROLE_ALLOWED_INTENTS` — mesma fonte de verdade, mesmo decorator `@permission`, sem mecanismo novo |
| Permissão nova e específica evita over-granting | `AUTH_LIST_VISIBLE` separado de `AUTH_MANAGE` mantém o princípio de menor privilégio |
| Dispositivos permanecem estritamente self-service | D3 fecha explicitamente essa lacuna — nenhum outro usuário, nem `admin` via esta tool, vê dispositivos de terceiro |
| Notificação ao consultado não reproduz fadiga | D7 aplica o critério já formalizado no ADR-140 em vez de reabrir a discussão atômico-vs-digest do zero |
| Digest reaproveita padrão de mecanismo já validado, com granularidade adequada ao caso | D8 usa a mesma ideia de time-gating do job de observability (ADR-112) sem acoplar os dois domínios |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| A matriz de D2 poderia não refletir a necessidade real de cada role | Validada diretamente com o usuário nesta entrada antes da implementação; se algum par se mostrar errado em uso real, é um ajuste isolado em `ROLE_VISIBILITY` (dict simples), sem migração de dado |
| Nova permissão + nova tool aumenta a superfície de RBAC a manter (governança AST do ADR-117) | Consistente com o crescimento já existente da superfície (ADR-116/117/120); segue o mesmo processo de decorator + teto de tools já estabelecido; `test_rbac_mcp_tool_mapping.py` atualizado com a nova permissão |
| Exposição de `email` sem mascaramento entre roles | Decisão explícita do usuário — a finalidade da tool é permitir contato, mascarar anularia o propósito; escopo de quem vê quem já é limitado por D2 |
| Digest de D8 introduz mais um scheduler in-process a operar (além de `_garbage_collector_loop` e `DraftDigestScheduler`) | Aceitável por seguir padrão já validado; desligado por padrão (opt-in), mesmo padrão de risco aceito para o digest de catálogo (ADR-141) |
| Intervalo curto (5min) para o digest gera mais execuções de verificação do que o digest diário de catálogo (ADR-141) | Mitigado pelo time-gating por conteúdo (D8): sem consulta pendente, o tick nem chama `list_clients()` — custo de um tick vazio é uma leitura de um blob JSON pequeno |
| Falha de envio (SMTP indisponível) descarta os eventos já drenados do lote, sem retry | Aceitável para um digest informativo "sem ação necessária" (D7b); eventos futuros continuam sendo registrados normalmente, só o lote da falha específica é perdido |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Este ADR | Problema documentado, matriz `ROLE_VISIBILITY`, escopo de campos (D3), critério de notificação ao consultado (D7-D9) | ✅ Implementado |
| F2 — Validação da matriz e da política de notificação | Matriz (D2), permissão `AUTH_LIST_VISIBLE` (D1), política de email sem mascaramento (D3), e habilitação do digest (D7b) com intervalo 300s (D8) — todos validados diretamente com o usuário nesta mesma entrada | ✅ Implementado |
| F3 — Implementação da visibilidade | `ROLE_VISIBILITY`/`AUTH_LIST_VISIBLE` em `permission_guard.py`; `visibility_service.py`; tool MCP `listar_usuarios_visiveis`; endpoint REST `GET /auth/users/visible`; testes | ✅ Implementado |
| F4 — Implementação do digest | `VisibilityDigestScheduler`/`visibility_digest_service.py`; `VisibilityDigestSettings`; `notify_visibility_queried`; wiring em `app.py::main()`; testes | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] Matriz de visibilidade (D2) revisada e ajustada com o usuário
- [x] Nome definitivo da permissão (D1) decidido: `AUTH_LIST_VISIBLE = "auth:list-visible"`
- [x] Política de exposição de campos, especialmente `email` (D3), decidida: sem mascaramento
- [x] Decisão sobre habilitar ou não o digest de D7(b): habilitado (opt-in), intervalo 300s (D8)
- [x] Status atualizado para Implementado

### Fase 3
- [x] `ROLE_VISIBILITY` implementado em `permission_guard.py` com teste de cobertura por par (observador, alvo) — `tests/unit/test_permission_guard_visibility.py`
- [x] Tool MCP + endpoint REST implementados e gated por `@permission("auth:list-visible")` — `tests/unit/test_mcp_auth_directory_tool.py`, `tests/unit/test_api_auth_visible_users.py`
- [x] Teste confirmando que `secret_hash`/`client_code_hash`/`notes`/dispositivos nunca aparecem na resposta — `tests/unit/test_visibility_service.py::test_response_fields_never_include_secrets_or_devices`

### Fase 4
- [x] Scheduler de digest implementado com time-gating por consulta nova desde o último envio — `tests/unit/test_visibility_digest_service.py`, `tests/unit/test_visibility_digest_scheduler.py`
- [x] Teste confirmando que sem consulta pendente o digest não consulta `list_clients()` nem envia — `test_sem_pendencias_nao_consulta_clientes_nem_envia`
- [x] Confirmado que o job `concilium-observability` (ADR-112) permanece sem nenhuma mudança — nenhum arquivo de `cd/`/observability tocado por esta ADR

---

## Relacionados

- ADR-099 — RBAC: Roles e Permissões (origem de `ROLE_PERMISSIONS`, base para `ROLE_VISIBILITY`)
- ADR-117 — RBAC por Decorator com Tag Introspectável (`@permission`, padrão reaproveitado por D4)
- ADR-120 — RBAC para Ciclo de Vida do Catálogo (precedente de permissão granular nova por necessidade específica, ex. `CATALOG_VALIDATE`/`CATALOG_MERGE`)
- ADR-123/131/134 — Notificação por Email (mesmo `ClientRecord`/`auth_store.py` como fonte de dados de usuário)
- ADR-118 — Auditoria de Invocações MCP (`ToolInvocation`, base da via passiva D7a)
- ADR-140 — Critério Atômico vs. Digest (aplicado a D7: ser consultado é caso (d)/(e), exige agregação)
- ADR-141 — Digest de Rascunhos de Catálogo (precedente direto de mecanismo reaproveitado em D8, com intervalo bem mais curto)
- ADR-112 — Pipeline de Observabilidade Medalhão (precedente de time-gating por conteúdo reaproveitado em D8; job em si permanece sem mudança, D8/A7)
