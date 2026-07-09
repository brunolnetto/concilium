# ADR-134 — Notificação por Email: Template Jinja2 Compartilhado e Separação Infraestrutura/Aplicação

**Status:** ✅ Implementado
**Data:** 2026-07-08
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-123 (serviço de notificação original), ADR-126 (Project Ownership — motiva as 5 notificações novas), ADR-131 (últimos métodos adicionados ao padrão atual)

---

## Contexto

### Problema

P1. **`NotificationService` hoje tem 7 métodos `notify_*`, cada um construindo o corpo do email por concatenação de f-strings em texto puro.** Não existe HTML, não existe template compartilhado, não existe fallback `multipart/alternative` — todo `_build_message` produz sempre `MIMEText(body, "plain", "utf-8")`. Visualmente inconsistente e pouco profissional para comunicação com clientes/engenheiros de obra.

P2. **`NotificationService` mistura duas responsabilidades que deveriam ser separadas.** A classe expõe um método por *evento de negócio* (`notify_user_created`, `notify_revoke_pending`, `notify_device_revoked_admin`, ...) — ou seja, a camada de infraestrutura (SMTP, MIME, retry/log de falha) sabe qual é o assunto, qual é o texto e quais variáveis cada caso de uso de negócio precisa. Isso acopla infraestrutura a domínio: toda nova notificação de negócio exige editar o serviço de infra.

P3. **O ADR-126 (Project Ownership) introduz 5 eventos de handover que hoje não notificam ninguém** — `OwnershipTransferAction.action` (`audit_service.py`) já define o conjunto exato: `transfer_forced`, `invite_created`, `invite_accepted`, `invite_rejected`, `invite_expired`. No padrão atual (P1+P2), isso significa +5 métodos de string manual na infraestrutura, agravando o problema em vez de resolvê-lo.

P4. **Sem fallback texto simples, a entregabilidade e a experiência em clientes de email variados ficam piores** do que um email bem formado `multipart/alternative` (HTML + texto).

### Escopo

Esta ADR trata do mecanismo de renderização/envio (infraestrutura) e do ponto de corte entre infraestrutura e aplicação. Não define o conteúdo visual definitivo (cores, logo) — o layout base é deliberadamente minimalista, ajustável sem nova decisão arquitetural.

---

## Decisão

### D1 — `NotificationService` (infraestrutura) expõe um método genérico

```python
class NotificationService:
    def send(
        self,
        *,
        to: str,
        subject: str,
        template: str,
        context: dict[str, Any],
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> None:
        """Renderiza `template` (par {template}.txt.jinja2 / {template}.html.jinja2) com
        `context`, monta multipart/alternative e envia via SMTP. Nunca propaga exceção
        (mesmo padrão dos métodos atuais: captura, loga, segue)."""
```

Os métodos atuais (`notify_user_created`, `notify_revoke_pending`, etc.) são **removidos** da infraestrutura — a infra não sabe mais nada sobre casos de uso de negócio, só sabe renderizar+enviar.

### D2 — Um template genérico cobre a maioria dos casos, evitando explosão de arquivos

```python
context = {
    "heading": str,                                  # "Bem-vindo ao Concilium"
    "intro": str | None,                              # parágrafo introdutório
    "details": list[tuple[str, str]] | None,          # pares chave/valor (ex.: "Projeto", "Lote A")
    "cta": {"label": str, "url": str} | None,         # botão de ação opcional
    "footer_note": str | None,                        # nota final (ex.: "Este link expira em 24h")
}
```

`templates/email/notification.{txt,html}.jinja2` consome esse contrato. Casos que precisem de um layout genuinamente diferente (ex.: anexo de config com passos numerados, `notify_user_created`) podem introduzir um novo par de templates com nome próprio — o argumento `template` do D1 já suporta isso; não é a exceção que quebra o design, é o mecanismo de extensão.

### D3 — Layout base HTML compartilhado

`templates/email/_base.html.jinja2`: cabeçalho com nome do produto, bloco de conteúdo (`{% block content %}`), rodapé com contato/suporte. Todo template HTML estende essa base — visual consistente em qualquer notificação, atual ou futura. CSS inline (compatibilidade com clientes de email que descartam `<style>` externo).

### D4 — Casos de uso migram para a camada de aplicação

Novo módulo `application/services/notifications.py`: uma função fina por evento de negócio, que monta o `context` (D2) e chama `get_notification_service().send(...)`. Exemplo:

```python
def notify_user_created(email: str, client_id: str, client_code: str, config_attachment: bytes) -> None:
    get_notification_service().send(
        to=email,
        subject="Bem-vindo ao Concilium",
        template="user_created",  # layout próprio — anexo com passos (D2, exceção justificada)
        context={"client_id": client_id, "client_code": client_code},
        attachments=[("claude_desktop_config.json", config_attachment, "application/json")],
    )
```

Call sites (`presentation/cli/commands_auth.py`, `presentation/api/routes/auth.py`, `presentation/api/routes/projects.py`, `presentation/mcp/tools/auth_self.py`, `application/services/project/_ownership_helpers.py`) passam a importar de `application/services/notifications.py`, nunca mais de `infrastructure/services/notification_service.py` diretamente.

### D5 — Migração completa dos 7 métodos existentes, sem coexistência de dois padrões

`notify_user_created`, `notify_client_code_migrated`, `notify_user_removed`, `notify_user_edited`, `notify_device_revoked_admin`, `notify_new_device`, `notify_revoke_pending` — todos migram para funções em `application/services/notifications.py` sobre o `send()` genérico (D1). Nenhum método de negócio permanece na infraestrutura.

### D6 — Cinco novas notificações de ownership (ADR-126)

Mapeamento 1:1 com `OwnershipTransferAction.action`:

| Função (aplicação) | Destinatário | Gatilho |
|---|---|---|
| `notify_ownership_transfer_forced` | novo dono | admin transfere direto (D4.1) **ou** `remove-user --reassign-to` (D7) — mesmo código de domínio (`transfer_ownership_forced`), mesma notificação |
| `notify_ownership_invite_created` | dono proposto | dono atual inicia handover voluntário |
| `notify_ownership_invite_accepted` | dono anterior | destinatário aceita |
| `notify_ownership_invite_rejected` | dono anterior | destinatário rejeita |
| `notify_ownership_invite_expired` | dono anterior | convite vence sem resposta (TTL) |

Não há uma 6ª notificação para D7: `remove-user --reassign-to` chama o mesmo helper `transfer_ownership_forced()` de D4.1 — reaproveita `notify_ownership_transfer_forced`, sem novo caso de uso.

Todas as 5 usam o template genérico (D2): `heading` + `details` (projeto, dono anterior/novo) + `cta` (link de aceite/rejeição quando aplicável).

### D7 — Nova dependência: Jinja2

Adicionar `jinja2` ao `pyproject.toml`. Escolhido sobre `string.Template` (stdlib) por dois motivos concretos: herança de template (D3, `{% extends %}`) e autoescape em HTML (proteção contra dado de usuário — nome de projeto, nome de dono — quebrar o markup).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | `string.Template` (stdlib) em vez de Jinja2 | Sem herança de template nem autoescape; reimplementar ambos manualmente não se paga frente a uma dependência pequena e amplamente usada |
| A2 | Um arquivo de template HTML por caso de uso (12 arquivos) | D2 cobre a maioria com 1 template parametrizado; arquivo próprio é a exceção (D2, `user_created`), não a regra |
| A3 | Manter `notify_*` na infraestrutura, só trocar a montagem de string por Jinja2 internamente | Não resolve P2 (mistura de responsabilidades) — troca a técnica de string, mantém o acoplamento infra↔domínio |
| A4 | Adicionar uma 6ª notificação de ownership dedicada a D7 (remove-user) | D7 reaproveita o mesmo código/ação de D4.1 (`transfer_forced`) — notificação duplicada seria redundante, não uma decisão de produto nova |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Aparência profissional e consistente | Todo email usa o mesmo layout base (D3); mudar visual = mudar 1 arquivo, não N métodos |
| Extensão sem tocar infraestrutura | Nova notificação de negócio = 1 função pequena em `application/services/notifications.py`, zero mudança em `NotificationService` |
| Fallback texto puro | `multipart/alternative` melhora entregabilidade e suporte a clientes sem HTML |
| Contrato claro entre camadas | Infra não conhece nenhum caso de uso de negócio; aplicação não conhece MIME/SMTP |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Nova dependência (`jinja2`) | Pequena, pura-Python, sem transitivas pesadas; largamente usada no ecossistema |
| Refactor toca 5+ call sites existentes | Migração em uma única PR (D5), sem período de coexistência dos dois padrões — evita bifurcação de manutenção |
| Autoescape HTML não cobre o corpo texto puro | Dado de usuário (nome de projeto/dono) em `context` é sempre string simples validada em schema anterior (Pydantic); sem HTML/script embutido esperado nesse dado |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Infraestrutura | `jinja2` no `pyproject.toml`; `NotificationService.send()` (D1); templates `_base.html.jinja2` + `notification.{txt,html}.jinja2` (D2/D3) | ✅ |
| F2 — Migração dos 7 existentes | `application/services/notifications.py` com as 7 funções (D4/D5); atualização de todos os call sites; remoção dos métodos de negócio da infra | ✅ |
| F3 — Ownership (ADR-126) | 5 funções novas (D6); wiring em `_ownership_helpers.py` (accept/reject/expired/forced) e nas rotas de `transfer-ownership` | ✅ |
| F4 — Documentação | Nota em ADR-123/ADR-131 apontando para esta ADR como evolução do padrão de notificação | ✅ |

## Definition of Done

### Fase 1
- [x] `jinja2` adicionado como dependência
- [x] `NotificationService.send()` implementado, com teste cobrindo: renderização texto+HTML, multipart/alternative, exceção nunca propaga
- [x] `_base.html.jinja2` + `notification.{txt,html}.jinja2` renderizam corretamente com um `context` de exemplo

### Fase 2
- [x] As 7 funções de aplicação implementadas e testadas (mock do `NotificationService.send`)
- [x] Todos os call sites atualizados (`commands_auth.py`, `routes/auth.py`, `mcp/tools/auth_self.py`)
- [x] Nenhum método de negócio (`notify_user_created`, etc.) remanescente em `infrastructure/services/notification_service.py`
- [x] Suíte completa sem regressão

### Fase 3
- [x] 5 funções de ownership implementadas e testadas
- [x] `_ownership_helpers.py` (accept/reject/expired/forced) chama a notificação correspondente
- [x] Teste de regressão: `remove-user --reassign-to` dispara `notify_ownership_transfer_forced` (D7, reaproveitamento de D4.1)

### Fase 4
- [x] Nota de evolução adicionada em ADR-123 e ADR-131 apontando para esta ADR

### Nota de implementação
`presentation/api/routes/projects.py` (rotas de `transfer-ownership`) **não** foi alterada diretamente —
a notificação foi conectada no ponto único `application/services/project/_ownership_helpers.py` (D4/D6),
que é a camada por trás de todos os call sites de ownership (CLI `remove-user --reassign-to`, rotas HTTP
de `transfer-ownership`, `accept`, `reject`). Isso evita duplicar o wiring em cada rota/call site.

---

## Relacionados

- ADR-123 — Serviço de Notificação por Email (origem do `NotificationService`; este ADR reformula seu contrato público)
- ADR-126 — Project Ownership (motiva as 5 notificações novas de D6)
- ADR-131 — Notificação em CRUD de usuário (últimos métodos adicionados ao padrão que esta ADR substitui)
