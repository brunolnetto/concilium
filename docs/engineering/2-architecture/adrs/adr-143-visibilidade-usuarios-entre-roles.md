# ADR-143 — Visibilidade de Usuários entre Roles

**Status:** Proposta
**Data:** 2026-07-20
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-099 (RBAC — Roles e Permissões), ADR-117 (RBAC por Decorator), ADR-120 (RBAC de Catálogo — precedente de permissão granular por ação), ADR-123/131/134 (sistema de notificação — usa os mesmos registros de `ClientRecord`)

---

## Contexto

### Problema

P1. **Hoje não existe, em nenhuma camada com RBAC de token (MCP/API), nenhuma forma de um usuário autenticado ver outros usuários do sistema.** A única listagem existente é o comando administrativo `concilium ops auth list-users` (`presentation/cli/commands_auth.py:417-444`), que chama `get_auth_store().list_clients()` diretamente, **sem nenhum decorator `@permission`/`@roles`**, e sempre retorna todos os registros do store sem filtro. O controle de acesso aqui não é RBAC — é apenas "quem tem acesso ao terminal/máquina onde a CLI roda".

P2. **As únicas tools MCP relacionadas a identidade são estritamente self-service.** Em `presentation/mcp/tools/auth_self.py`: `ativar_dispositivo` (`AUTH_PUBLIC`), `renovar_token` (`AUTH_PUBLIC`), `listar_meus_dispositivos` (`AUTH_SELF`) e `revogar_meu_dispositivo` (`AUTH_SELF`) — todas escopadas ao próprio `client_id` resolvido do JWT via `get_current_user_id()`. Nenhuma expõe informação sobre outro usuário. Não existe endpoint REST equivalente em `presentation/api/routes/auth.py` (que só tem `/token`, `/device/activate`, `/token/refresh`, `/token/issue`, `/revoke-pending`, `/revoke-confirm`).

P3. **`permission_guard.py` não modela visibilidade de identidade, só ação sobre recursos de domínio.** As 19 permissões atuais (`PROJECT_*`, `ARTIFACTS_*`, `CATALOG_*`, `FINANCIALS_READ`, `AUTH_MANAGE`, `AUTH_SELF`, `AUTH_PUBLIC`, `SYSTEM_READ`, `HEALTH_READ`) controlam o que um role pode *fazer*, nunca o que um role pode *ver de outro usuário*. `ROLE_PERMISSIONS` (linha 102) e `ROLE_ALLOWED_INTENTS` (linha 115) são os únicos dois mapas role→algo hoje; não há um terceiro para visibilidade.

P4. **`ClientRecord` (`auth_store.py:56-66`) não tem campo de agrupamento além de `roles: list[str]`.** Os 5 roles técnicos atuais são `operator`, `engineer`, `admin`, `auditor`, `catalog-manager` (ADR-099/ADR-120) — não correspondem 1:1 aos 5 papéis de negócio usados na comunicação com stakeholders (TI, Comercial, Engenharia, Suprimentos, Auditoria; ver apresentação `docs/product/2-presentations/2026-07-17/`). Qualquer visibilidade baseada em role hoje opera sobre os nomes técnicos, não sobre os nomes de negócio.

P5. **É plausível que usuários do mesmo grupo de trabalho precisem identificar uns aos outros** — ex.: Engenharia querendo saber quem mais tem esse papel para dividir a revisão de um rascunho de catálogo, ou um operator descobrindo para quem encaminhar um handoff (H2/H3 do fluxo de handoffs já mapeado na apresentação técnica). Hoje essa necessidade não tem nenhuma via de atendimento dentro do sistema — só perguntando manualmente a alguém com acesso à CLI administrativa.

### Escopo

Esta ADR define **se e como** um usuário autenticado pode listar/ver outros usuários do sistema via MCP/API, com visibilidade escopada por role — não a listagem administrativa irrestrita que já existe na CLI (fora de escopo, P1, ver D6). É uma ADR de discussão: os pontos marcados **[A DECIDIR]** são propostas de partida a validar/ajustar em conjunto antes de fechar o status como Aceito.

---

## Decisão

### D1 — Nova permissão dedicada, não reaproveitar `AUTH_MANAGE`/`AUTH_SELF`

Introduzir uma permissão granular nova, `AUTH_LIST_VISIBLE` (nome provisório — **[A DECIDIR]**), distinta de `AUTH_MANAGE` (gestão administrativa plena de usuários, hoje só `admin`) e de `AUTH_SELF` (self-service sobre o próprio registro, todos os roles). Reaproveitar `AUTH_MANAGE` forçaria dar acesso administrativo completo só para habilitar visibilidade parcial; reaproveitar `AUTH_SELF` misturaria "ver a si mesmo" com "ver outros", que são operações de risco diferentes.

### D2 — Matriz de visibilidade por role, análoga a `ROLE_PERMISSIONS`

Introduzir `ROLE_VISIBILITY: dict[str, frozenset[str]]` em `permission_guard.py`, mapeando role do observador → conjunto de roles que ele pode ver (não necessariamente simétrico). Proposta inicial **[A DECIDIR]**:

| Observador | Vê os roles |
|---|---|
| `admin` | todos (`operator`, `engineer`, `admin`, `auditor`, `catalog-manager`) |
| `auditor` | todos (leitura ampla já é o papel do auditor — `FINANCIALS_READ`, `PROJECT_READ` sem restrição de escopo) |
| `engineer` | `engineer`, `admin` (colegas de papel + quem aprova/administra) |
| `operator` | `operator`, `engineer`, `admin` (fluxo RFI→RFP: precisa saber para quem encaminhar) |
| `catalog-manager` | `catalog-manager`, `admin` (fluxo de 4 olhos: colegas + quem administra) |

Esta tabela é o ponto central de discussão desta ADR — os pares exatos devem ser revisados com o usuário antes de aceitar.

### D3 — Campos expostos: subconjunto seguro, nunca o `ClientRecord` completo

A resposta de qualquer tool/endpoint de visibilidade nunca inclui `secret_hash`, `client_code_hash` nem `notes` (podem conter informação administrativa sensível). Campos propostos: `client_id`, `email` (ou mascarado — **[A DECIDIR]**), `roles`, `active`. Sem `created_at`/`deleted_at` salvo decisão em contrário.

### D4 — Implementação como nova MCP tool + endpoint REST espelhado

Seguindo o padrão de `auth_self.py` (ADR-123/117): nova tool `listar_usuarios_visiveis`, gated por `@permission(AUTH_LIST_VISIBLE)`, que resolve o(s) role(s) do JWT do chamador, expande via `ROLE_VISIBILITY` o conjunto de roles visíveis, filtra `get_auth_store().list_clients()` por esse conjunto e projeta os campos de D3. Endpoint REST equivalente em `presentation/api/routes/auth.py` para paridade com o padrão MCP/API dual já estabelecido no resto do sistema.

### D5 — Fonte única de verdade: `permission_guard.py`

`ROLE_VISIBILITY` fica no mesmo módulo que `ROLE_PERMISSIONS`/`ROLE_ALLOWED_INTENTS`, não duplicada em `auth_store.py` nem na camada de apresentação — mantém o precedente de fonte única de verdade para regras de role (ADR-099, ADR-117).

### D6 — CLI `list-users` administrativa permanece inalterada

O comando `concilium ops auth list-users` continua fora do RBAC de token — é ferramenta operacional para quem já tem acesso ao servidor/CLI (tipicamente TI/admin), não ao alcance de usuários finais via MCP/API. Esta ADR não introduz restrição nem expande esse comando; trata exclusivamente da nova via de visibilidade via token (D1-D4).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter o estado atual (nenhuma visibilidade via MCP/API) | Deixa sem resposta a necessidade real descrita em P5; usuário só descobre quem mais está no sistema perguntando informalmente a quem tem acesso à CLI |
| A2 | Visibilidade total — qualquer usuário autenticado vê todos os outros usuários | Vaza informação de composição de equipe/roles sem necessidade de negócio clara (ex. Suprimentos vendo a lista completa de contas de Comercial); contradiz o princípio de menor privilégio já seguido em `permission_guard.py` |
| A3 | Reaproveitar `AUTH_MANAGE` para gatear a nova tool | Obrigaria conceder acesso administrativo pleno (criar/editar/remover usuário) só para habilitar visibilidade — permissão desproporcional ao caso de uso |
| A4 | Adicionar campo de "área"/"departamento" de negócio em `ClientRecord` antes de decidir visibilidade | Fora de escopo desta ADR — a matriz de visibilidade pode ser modelada só com os 5 roles técnicos já existentes; introduzir um campo novo é uma extensão futura independente, não pré-requisito |
| A5 | Expandir a CLI `list-users` com um novo filtro por role, em vez de nova tool MCP/API | Não resolve o problema — a CLI é inacessível ao usuário final (roda no servidor/terminal administrativo), que é exatamente quem precisa dessa visibilidade (P5) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha um gap real sem abrir a superfície inteira | Resolve P5 sem reproduzir o problema de A2 (vazamento de informação) |
| Reaproveita o padrão arquitetural existente | `ROLE_VISIBILITY` espelha `ROLE_PERMISSIONS`/`ROLE_ALLOWED_INTENTS` — mesma fonte de verdade, mesmo decorator `@permission`, sem mecanismo novo |
| Permissão nova e específica evita over-granting | `AUTH_LIST_VISIBLE` separado de `AUTH_MANAGE` mantém o princípio de menor privilégio |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| A matriz de D2 é uma proposta inicial não validada — pode não refletir a necessidade real de cada role | Marcado explicitamente como [A DECIDIR]; é o objeto central de discussão desta ADR antes de mudar o status para Aceito |
| Nova permissão + nova tool aumenta a superfície de RBAC a manter (governança AST do ADR-117) | Consistente com o crescimento já existente da superfície (ADR-116/117/120); segue o mesmo processo de decorator + teto de tools já estabelecido |
| Exposição de `email` para outros usuários pode ser sensível dependendo da política de privacidade interna | [A DECIDIR] — considerar mascarar (ex. mostrar só domínio) se a discussão concluir que o endereço completo não deveria circular entre roles |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Este ADR | Problema documentado, matriz `ROLE_VISIBILITY` proposta para discussão, decisão de escopo de campos (D3) | 💡 Proposta |
| F2 — Validação da matriz | Revisar/ajustar D2 com o usuário; decidir nome final da permissão (D1) e política de exposição de email (D3) | ⬜ Não iniciado |
| F3 — Implementação | `ROLE_VISIBILITY` em `permission_guard.py`; tool MCP `listar_usuarios_visiveis`; endpoint REST espelhado; testes | ⬜ Não iniciado |

## Definition of Done

### Fase 1
- [ ] Matriz de visibilidade (D2) revisada e ajustada com o usuário
- [ ] Nome definitivo da permissão (D1) decidido
- [ ] Política de exposição de campos, especialmente `email` (D3), decidida
- [ ] Status atualizado para Aceito/Decidido

### Fase 3
- [ ] `ROLE_VISIBILITY` implementado em `permission_guard.py` com teste de cobertura por par (observador, alvo)
- [ ] Tool MCP + endpoint REST implementados e gated por `@permission(AUTH_LIST_VISIBLE)`
- [ ] Teste confirmando que `secret_hash`/`client_code_hash`/`notes` nunca aparecem na resposta

---

## Relacionados

- ADR-099 — RBAC: Roles e Permissões (origem de `ROLE_PERMISSIONS`, base para `ROLE_VISIBILITY`)
- ADR-117 — RBAC por Decorator com Tag Introspectável (`@permission`, padrão reaproveitado por D4)
- ADR-120 — RBAC para Ciclo de Vida do Catálogo (precedente de permissão granular nova por necessidade específica, ex. `CATALOG_VALIDATE`/`CATALOG_MERGE`)
- ADR-123/131/134 — Notificação por Email (mesmo `ClientRecord`/`auth_store.py` como fonte de dados de usuário)
