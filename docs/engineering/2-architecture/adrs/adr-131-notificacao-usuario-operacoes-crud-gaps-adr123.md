# ADR-131 — Notificação do Usuário em Operações sobre Seus Próprios Dados: Fechamento das Lacunas do ADR-123

**Status:** ⚠️ Parcialmente Implementado _(F1-F3 completas; F4 parcial — ver Definition of Done)_
**Data:** 2026-07-08
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-123 (serviço de notificação original), ADR-094 (JWT/auth), ADR-099 (RBAC)
**Evolução:** ADR-134 migra os métodos `notify_*` adicionados por esta ADR (`notify_user_edited`,
`notify_device_revoked_admin`) de `NotificationService` para `application/services/notifications.py`,
sobre o `send(template, context)` genérico.

---

## Contexto

### Problema

P1. **Hoje só existe notificação por email na criação de usuário.** `NotificationService.notify_user_created` (`infrastructure/services/notification_service.py:71`) é chamado por `add-user` (`presentation/cli/commands_auth.py:168-176`), condicionado a `--email` ter sido informado. Todas as demais operações que mutam ou afetam o registro do usuário são silenciosas para quem é o dono do dado.

P2. **O próprio ADR-123 já havia especificado a superfície completa** (`notify_user_created`, `notify_user_edited`, `notify_user_removed`, `notify_new_device`, `notify_revoke_pending`), mas a implementação divergiu da spec sem que isso fosse documentado:

| Método especificado (ADR-123) | Existe hoje? | É chamado por alguma operação? |
|---|---|---|
| `notify_user_created` | ✅ | ✅ `add-user` |
| `notify_user_edited` | ❌ não implementado | — não há operação de update de usuário no sistema |
| `notify_user_removed` | ✅ implementado | ❌ **nunca chamado** — `remove-user` não invoca |
| `notify_new_device` | ✅ implementado | ❌ **nunca chamado** — a lógica de detecção de dispositivo desconhecido (F3 do ADR-123) não foi construída |
| `notify_revoke_pending` | ✅ | ✅ `auth.py:270`, `auth_self.py:186` |

P3. **Levantamento completo da camada de apresentação (CLI, API, MCP) confirma o padrão: notificação é exceção, não regra**, para operações que seguramente afetam o usuário-dono do dado:

| Camada | Operação | Efeito sobre o usuário-dono | Notifica hoje? |
|---|---|---|---|
| CLI `commands_auth.py:117` | `add-user` (create) | Conta criada, credencial emitida | ✅ |
| CLI `commands_auth.py:215` | `remove-user` (delete) + revoga todos os dispositivos | Conta apagada, todo acesso cortado sem aviso | ❌ |
| CLI `commands_auth.py:243` | `regenerate-code` (rotação de credencial) | Credencial antiga invalidada, config antigo do usuário para de funcionar | ❌ |
| CLI `commands_auth.py:356` | `revoke-device` (admin, direto) | Dispositivo do usuário revogado sem o duplo-fator do fluxo self-service | ❌ |
| API `auth.py:234` / MCP `auth_self.py:138` | revoke self-service (pending→confirm) | — | ✅ (`notify_revoke_pending`) |

Não existe operação de **update/edit de usuário** hoje (nem em `commands_auth.py`, nem em `auth_store.py` — só há `add_client`, `list_clients`, `remove_client`). "Mudança de papel/role" ou edição de email/notas não é uma operação implementada; é um gap estrutural anterior a este ADR, não um gap de notificação.

P4. **O risco concreto de P3 é operacional, não cosmético.** `regenerate-code` e `revoke-device` (admin) invalidam credenciais/acesso do usuário de forma imediata e silenciosa. O usuário só descobre quando o Claude Desktop para de funcionar, sem saber se foi um bug, um ataque, ou uma ação legítima do admin — o mesmo problema de rastreabilidade que motivou o ADR-123 originalmente.

### Escopo e altitude

Este ADR trata exclusivamente de **notificar o usuário-dono do dado sobre operações executadas sobre seu próprio registro** (create/delete/credential-rotation/device-revoke administrativo). Não inclui:
- Detecção de dispositivo desconhecido (`notify_new_device`, F3 do ADR-123) — gap distinto, de segurança/anomalia, já rastreado e não implementado por falta da lógica de detecção, não por falta de decisão.
- Criação de uma operação de "update/edit de usuário" — não existe hoje; quando for introduzida, D4 abaixo já define a obrigação.

---

## Decisão

### D1 — Fechar o gap trivial: `remove-user` chama `notify_user_removed`

O método já existe e já está testado (implícito no ADR-123). O gap é apenas a ausência da chamada. Alterar `commands_auth.py:215-233` para invocar `get_notification_service().notify_user_removed(user)` antes ou depois de `remove_client`, condicionado a `user.email` estar presente — mesmo padrão condicional já usado em `add-user`.

### D2 — Implementar `notify_user_edited` e usá-lo em `regenerate-code`

`regenerate-code` é, na prática, um `update` parcial do registro do usuário (rotação de `client_code`/credencial) — é o primeiro caso real de "edição" que o sistema já executa, mesmo sem existir um comando `edit-user` genérico. Implementar o método já especificado pelo ADR-123:

```python
def notify_user_edited(self, user: UserRecord, changes: dict) -> None: ...
```

e invocá-lo em `regenerate-code` (`commands_auth.py:243`) com `changes={"client_code": "regenerado"}`. Isso resolve simultaneamente o gap de notificação em `regenerate-code` e a divergência entre a spec do ADR-123 (que previa o método) e a implementação (que nunca o criou).

### D3 — Novo evento: `notify_device_revoked_admin` para revogação administrativa direta

`revoke-device` (CLI, admin) é operacionalmente distinto do fluxo self-service (`notify_revoke_pending`, duplo-opt-in de 24h): é uma ação unilateral do admin, sem confirmação do usuário. Reaproveitar `notify_revoke_pending` seria semanticamente errado (implicaria um fluxo de confirmação que não existe aqui). Adicionar:

```python
def notify_device_revoked_admin(self, user: UserRecord, device: DeviceRecord) -> None: ...
```

chamado a partir de `revoke-device` (`commands_auth.py:356`), condicionado a `user.email`. O corpo do email deixa explícito que a ação foi tomada pelo administrador (não é uma resposta a um pedido do próprio usuário), reduzindo o risco de o usuário interpretar o email como phishing.

### D4 — Regra arquitetural: toda nova operação de mutação sobre `UserRecord` deve invocar `NotificationService`

Para não repetir o padrão que gerou P2/P3 (métodos especificados e nunca ligados), esta ADR fixa a regra: **qualquer comando/endpoint/tool que crie, edite, remova ou revogue acesso de um usuário deve, na mesma revisão de código, invocar o método correspondente do `NotificationService` (existente ou novo) condicionado à presença de email.** Em particular, quando uma operação de `update-user`/`edit-user` genérica for introduzida no futuro, ela é obrigada a chamar `notify_user_edited` (D2) — não uma decisão nova, apenas a aplicação desta regra ao gap estrutural identificado em P3.

Enforcement: checklist de PR (não um teste automatizado — o custo de um lint estrutural para "toda função que muta X chama Y" não se paga para 4 call sites); revisão de código deve tratar ausência de notificação em mutação de usuário como bloqueante, na mesma categoria de rigor que ADR-118 (auditoria) trata ausência de `ToolInvocation`.

### D5 — Manter disparo síncrono e inline (sem fila/event bus)

Não introduzir `application/jobs/` (ADR-102/103) nem `BackgroundTasks` do FastAPI para este disparo. Motivo: (a) `NotificationService._send` já captura exceção e não propaga — uma falha de SMTP nunca bloqueia ou corrompe a operação de CRUD; (b) o volume é de comandos administrativos via CLI, não de tráfego de API — não há request HTTP para desacoplar na maioria dos call sites (D1–D3 são todos CLI); (c) introduzir fila para ~5 call sites de baixíssima frequência é custo de infraestrutura sem benefício mensurável. Caso uma operação equivalente seja exposta futuramente via API HTTP (não existe hoje), `BackgroundTasks` — já em uso em `campaign.py`/`benchmarks.py` — é o padrão a seguir, não uma fila nova.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Criar `update-user`/`edit-user` genérico como parte desta ADR | Fora de escopo — esta ADR trata de notificação sobre operações que já existem; introduzir uma operação nova de CRUD é decisão de produto separada, não de notificação |
| A2 | Reaproveitar `notify_revoke_pending` para o revoke administrativo direto (D3) | Semanticamente incorreto — implica um fluxo de confirmação de 24h que não existe na revogação direta do admin; confundiria o usuário sobre se precisa agir |
| A3 | Enforcement via teste estrutural automatizado (grep/AST) que barra PR sem chamada a `NotificationService` em funções que mutam `UserRecord` | Custo de manutenção do lint não se paga para 4-5 call sites; risco de falso-positivo alto (nem toda mutação é visível a um usuário-dono, ex. migração em lote); resolvido por revisão de código (D4) |
| A4 | Desacoplar via `application/jobs/` ou fila dedicada (ADR-102/103) | Ver D5 — nenhum dos call sites de D1-D3 é uma rota HTTP; overhead de infraestrutura sem call site que justifique |
| A5 | Também implementar `notify_new_device` (F3 do ADR-123) nesta ADR | Fora de escopo — depende de lógica de detecção de dispositivo desconhecido ainda não construída, que é uma feature de segurança/anomalia, não uma notificação de operação CRUD sobre dado próprio |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Paridade com a spec original | `notify_user_removed` finalmente é usado; `notify_user_edited` passa a existir e ter um call site real (`regenerate-code`) |
| Rastreabilidade em ações administrativas silenciosas | Usuário sabe quando a conta foi removida ou a credencial rotacionada, reduzindo confusão/suporte quando o acesso para de funcionar |
| Revogação admin diferenciada da self-service | `notify_device_revoked_admin` evita ambiguidade sobre se a ação exige confirmação do usuário |
| Sem novo componente de infraestrutura | D5 mantém o padrão inline/síncrono já existente e testado |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Regra D4 depende de disciplina de revisão, não de automação | Aceito por custo-benefício (A3); reavaliar automação se o número de call sites crescer substancialmente |
| Usuário sem email cadastrado continua sem notificação em nenhuma operação | Mesmo comportamento condicional já aceito desde o ADR-123 (`add-user`); fora de escopo alterar a obrigatoriedade de email |
| Email de revogação administrativa pode ser mal interpretado como phishing, mesmo com aviso explícito | Reusar template/remetente já estabelecido em `notify_revoke_pending` (mesmo domínio, mesmo padrão visual), não introduzir remetente novo |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — `remove-user`** | `notify_user_removed` chamado em `commands_auth.py:remove-user` | ✅ |
| **F2 — `notify_user_edited`** | Implementar método em `NotificationService`; chamar em `regenerate-code` | ✅ |
| **F3 — `notify_device_revoked_admin`** | Novo método; chamar em `revoke-device` (admin) | ✅ |
| **F4 — Documentação** | Atualizar seção "Arquivos a criar/modificar" do ADR-123 (retroativo) para refletir a implementação real; checklist de PR (D4) documentado em `CONTRIBUTING`/guia de skill relevante | ⚠️ parcial — ver nota abaixo |

F1–F3 são independentes entre si e podem ser implementadas em qualquer ordem ou em paralelo.

## Definition of Done

> **Nota de implementação sobre assinaturas:** os métodos existentes de `NotificationService`
> (`notify_user_created`, `notify_user_removed`, `notify_client_code_migrated`,
> `notify_new_device`, `notify_revoke_pending`) recebem `client_id`/`email` como strings
> soltas, não um objeto `UserRecord`/`DeviceRecord` (esses tipos não existem no código —
> o registro real é `ClientRecord`/`RefreshTokenRecord` em `auth_store.py`). Os dois métodos
> novos (`notify_user_edited`, `notify_device_revoked_admin`) seguem a convenção real já
> estabelecida no arquivo em vez do pseudocódigo genérico de D2/D3, por consistência:
> `notify_user_edited(client_id: str, email: str, changes: dict[str, str])` e
> `notify_device_revoked_admin(client_id: str, device_id: str, email: str)`.

### Fase 1
- [x] `remove-user` chama `notify_user_removed(client_id, email)` quando `email` presente
- [x] Teste cobrindo o call site (mock de `NotificationService`), incluindo os casos sem email e de cliente inexistente

### Fase 2
- [x] `notify_user_edited(client_id, email, changes)` implementado em `NotificationService`, seguindo o padrão síncrono e resiliente a falha dos demais métodos (captura exceção, loga, não propaga)
- [x] `regenerate-code` chama `notify_user_edited` com `changes={"client_code": "regenerado"}`
- [x] Teste cobrindo o call site, incluindo os casos sem email e de cliente não encontrado após a regeneração

### Fase 3
- [x] `notify_device_revoked_admin(client_id, device_id, email)` implementado
- [x] `revoke-device` (admin, CLI) chama o método quando `email` presente
- [x] Teste cobrindo o call site, incluindo o caso sem email (não deve lançar) e o caso de device desconhecido

### Fase 4
- [x] Tabela "Arquivos a criar/modificar" do ADR-123 atualizada com nota apontando para este ADR
- [ ] Regra D4 documentada no guia de contribuição/checklist de PR — **não feito**: o repositório não tem hoje um arquivo `CONTRIBUTING`/checklist de PR centralizado (busca confirmou que não existe); a regra D4 permanece documentada apenas nesta ADR. Criar esse arquivo é decisão de processo maior que o escopo desta ADR — abrir um item de acompanhamento separado se o time quiser um checklist formal.

---

## Relacionados

- ADR-123 — Serviço de Notificação por Email e Gestão de Dispositivos (spec original; este ADR fecha as lacunas entre spec e implementação)
- ADR-094 — Camada de Autenticação JWT (contexto de `UserRecord`/`auth_store.py`)
- ADR-099 — RBAC (papéis afetados pelas operações administrativas de D1/D3)
- ADR-102 / ADR-103 — Pipeline Jobs assíncronos (considerado e rejeitado em D5 para este escopo)
- ADR-118 — Auditoria de Invocações MCP (paralelo de rigor para D4: mutação sem contrapartida obrigatória é tratada como lacuna, não como detalhe)
