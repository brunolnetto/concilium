# ADR-141 — Digest Periódico de Rascunhos de Catálogo Pendentes de Aprovação

**Status:** Proposta
**Data:** 2026-07-16
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-140 (critério atômico vs. digest — esta ADR aplica D1/D2/D3), ADR-120 (RBAC do ciclo de vida do catálogo — origem de `criar_rascunho_catalogo`/`aprovar_merge_catalogo`/`rejeitar_rascunho_catalogo`), ADR-134 (mecanismo de envio reaproveitado), ADR-103 (Jobs na Camada de Aplicação — precedente de thread com intervalo reaproveitado)

---

## Contexto

### Problema

P1. **`criar_rascunho_catalogo` (ADR-120) não notifica ninguém.** Um engineer cria um rascunho de contexto de catálogo (`ContextoVersionService.create_version(..., make_current=False)`, marcado com `_rascunho: True`); o catalog-manager só descobre que há algo pendente se pesquisar ativamente via `versoes_catalogo`. Não há hoje nenhum sinal — email, ou de qualquer outro canal — de que uma aprovação está aguardando.

P2. **Pelo critério do ADR-140 D1, este caso exige agregação, não envio atômico.** Um catalog-manager pode ter múltiplos contextos sob sua responsabilidade, e múltiplos engineers podem abrir rascunhos em paralelo — o papel acumula naturalmente várias instâncias do mesmo tipo de evento (condição (e) do ADR-140 D1). Um email por `criar_rascunho_catalogo` faria o catalog-manager receber um email a cada rascunho aberto, potencialmente vários por dia.

P3. **Hoje não existe, no modelo de dados de versionamento (`ConfigVersionService`), nenhuma forma pública de listar apenas os rascunhos pendentes.** `_list_versions()` retorna `version`, `created_at`, `created_by`, `motivo` e alguns campos específicos (`catalogo_id`, `jurisdicao_id`, `perfil_id`, `nome`) — não inclui as flags `_rascunho`/`_rejeitado` gravadas por `criar_rascunho_catalogo`/`rejeitar_rascunho_catalogo` (`presentation/mcp/tools/catalogo.py`). Qualquer consumidor externo precisaria ler os arquivos de versão diretamente, quebrando o encapsulamento do serviço de versionamento (ADR-062).

### Escopo

Aplica o critério do ADR-140 a este caso concreto: define o que conta como "rascunho pendente" (D1), quem recebe o digest (D2) e o mecanismo de disparo (D3, reaproveitando o precedente de `JobService._garbage_collector_loop`). Não altera o fluxo síncrono de `criar_rascunho_catalogo`/`aprovar_merge_catalogo`/`rejeitar_rascunho_catalogo` — nenhum desses três ganha uma chamada de notificação own; o digest é o único canal.

---

## Decisão

### D1 — Definição de "rascunho pendente"

Uma versão de contexto conta como rascunho pendente quando, simultaneamente:

- `_rascunho` é `True` (criada via `criar_rascunho_catalogo`);
- `_rejeitado` não é `True` (não foi descartada via `rejeitar_rascunho_catalogo`);
- `version != current_version` do contexto (ainda não foi promovida via `aprovar_merge_catalogo` — se promovida, a versão continua tendo `_rascunho: True` no arquivo, mas deixa de ser "pendente": já foi decidida).

Isso é suficiente para derivar o estado a partir dos dados já gravados hoje pelos três tools existentes — nenhum novo campo de estado é necessário além de expor os já existentes.

### D2 — Exposição pública em `ConfigVersionService._list_versions`

Estende a lista de campos incluídos em `_list_versions` (hoje restrita a `catalogo_id`, `jurisdicao_id`, `perfil_id`, `nome`) para também incluir, quando presentes no arquivo de versão: `_rascunho`, `_rascunho_descricao`, `_rejeitado`, `_motivo_rejeicao`, `_rejeitado_por`. Mudança aditiva — nenhum consumidor existente de `list_versions()`/`list_entities()` é afetado (novos campos só aparecem quando o dado existe no JSON da versão).

### D3 — Destinatário: role `catalog-manager` com email cadastrado

O digest é enviado para todo `ClientRecord` ativo com `"catalog-manager" in roles` e `email` não vazio (mesmo padrão condicional de todos os 12 casos de uso existentes — ADR-131). Não há hoje conceito de "catalog-manager por contexto" (o RBAC do ADR-120 é um role global, não por contexto) — o digest lista todos os contextos com pendências, agrupados, no mesmo email, para cada destinatário.

### D4 — Conteúdo do digest (reaproveita template genérico, ADR-134 D2)

Um email por destinatário, contendo a lista de `(rascunho_id, "contexto — motivo (criado por X em data)")` como `details` do template `notification.{txt,html}.jinja2` já existente — sem template novo. Assunto: `"[Concilium] N rascunho(s) de catálogo aguardando aprovação"`. Sem `cta` (não há link direto de aprovação via API/UI para rascunho de catálogo hoje — a ação é via tool MCP `aprovar_merge_catalogo`/`rejeitar_rascunho_catalogo`).

Se não houver nenhum rascunho pendente em nenhum contexto no momento da execução do digest, nenhum email é enviado a ninguém (silêncio é o comportamento correto — não gerar "0 pendências" recorrente).

### D5 — Mecanismo de disparo: thread com intervalo, reaproveitando o precedente do ADR-140 D3

Novo componente `DraftDigestScheduler` (`application/services/catalog/draft_digest_scheduler.py`), no mesmo padrão de `JobService._garbage_collector_loop` (`application/jobs/service.py:77-80`): thread daemon com `threading.Event().wait(timeout=intervalo)`. A cada intervalo, chama `enviar_digest_rascunhos_pendentes()`.

Intervalo e habilitação configuráveis via nova `CatalogDigestSettings` (`infrastructure/settings/_catalog_digest.py`), seguindo o padrão de `JobsSettings`/`SmtpSettings`:

- `CONCILIUM__CATALOG_DIGEST_ENABLED` (default `False` — opt-in, mesmo padrão de `CONCILIUM__NOTIFICATIONS_ENABLED`);
- `CONCILIUM__CATALOG_DIGEST_INTERVAL_HOURS` (default `24`).

### D6 — Início do scheduler: `main()`, não `create_app()`

O scheduler é iniciado explicitamente em `presentation/api/app.py::main()` (processo real do servidor), nunca em `create_app()` — mesma razão já documentada para `startup_check()`/`ensure_storage_root()`: `create_app()` é importado por testes (`TestClient`), e um thread real de produção não deve nascer a cada import de teste. Isso evita a alternativa de "lazy start" usada por `JobService` (que dispara no primeiro uso de fato) — um digest que depende de atividade incidental para começar a rodar não cumpriria a garantia de "roda a cada N horas independentemente de uso".

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Notificar diretamente em `criar_rascunho_catalogo` (envio atômico) | Viola o critério D1 do ADR-140 (condição e): catalog-manager receberia 1 email por rascunho, potencialmente vários por dia |
| A2 | CLI + cron externo (ex. GitHub Actions scheduled workflow, ACA scheduled job) em vez de thread in-process | Introduziria uma nova superfície de apresentação (CLI de catálogo, hoje só exposto via MCP) e uma nova peça de infraestrutura de deploy; o padrão thread+intervalo já existe e roda no mesmo processo do servidor sem infraestrutura adicional (ADR-140 D3) |
| A3 | Iniciar o scheduler em `create_app()` | Rodaria a cada import de `app.py` em teste (TestClient), gerando threads reais de produção durante a suíte — mesmo problema que `startup_check()` já evita hoje ficando fora de `create_app()` |
| A4 | Digest por contexto (catalog-manager recebe 1 email por contexto com pendência, não 1 consolidado) | Reintroduziria o mesmo problema que o digest resolve, se o catalog-manager acompanhar muitos contextos — 1 email consolidado por execução do digest, cobrindo todos os contextos, é o ponto do mecanismo |
| A5 | Novo template dedicado em vez do genérico `notification.{txt,html}.jinja2` | Sem necessidade — o contrato `details: list[tuple[str,str]]` (ADR-134 D2) já cobre uma lista de rascunhos pendentes sem exigir layout próprio |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha o gap de P1 sem violar o critério do ADR-140 | Catalog-manager passa a ser avisado de pendências sem receber 1 email por rascunho |
| Zero infraestrutura nova | Reaproveita thread+intervalo (padrão já em produção), template genérico e `NotificationService.send()` existentes |
| Silêncio quando não há pendência | Sem "0 rascunhos pendentes" recorrente — só notifica quando há algo a decidir |
| Aditivo em `_list_versions` | Nenhuma migração de dado necessária — as flags já são gravadas pelos tools existentes desde o ADR-120 |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Rascunho aberto pouco antes do digest pode esperar até quase o intervalo inteiro (até 24h no default) para ser notificado | Aceito — é a natureza de um digest; intervalo é configurável via env var para quem precisar de ciclo mais curto |
| Sem teste em produção real de envio SMTP em massa (N catalog-managers simultâneos) | Baixo risco — número de catalog-managers é pequeno (role administrativo interno); mesmo padrão de `send()` nunca lançar exceção já protege contra falha isolada |
| Thread daemon iniciada em `main()` não tem endpoint de health/observabilidade dedicado | Fora de escopo desta ADR; falha na execução do digest é logada (`logger.exception`) e não interrompe o servidor — consistente com o padrão de resiliência do `NotificationService` |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Settings | `CatalogDigestSettings` (`_catalog_digest.py`), testado | ⬜ |
| F2 — Exposição de estado | `_list_versions` expõe `_rascunho`/`_rejeitado`/campos relacionados (D2), testado | ⬜ |
| F3 — Lógica de negócio | `application/services/catalog/draft_digest_service.py`: `rascunhos_pendentes()` + `enviar_digest_rascunhos_pendentes()`, testado | ⬜ |
| F4 — Notificação | `notify_catalog_drafts_pending()` em `application/services/notifications.py`, testado | ⬜ |
| F5 — Scheduler | `DraftDigestScheduler` (start/stop), testado | ⬜ |
| F6 — Wiring | Início condicional (`CONCILIUM__CATALOG_DIGEST_ENABLED`) em `app.py::main()` | ⬜ |

## Definition of Done

### Fase 1-5 (TDD — teste antes da implementação em cada fase)
- [ ] `CatalogDigestSettings.from_env()` cobre defaults e overrides de env var
- [ ] `_list_versions` inclui `_rascunho`/`_rejeitado`/etc. quando presentes, sem quebrar consumidores existentes (`versoes_catalogo`, `list_contexts`)
- [ ] `rascunhos_pendentes()`: inclui rascunho não-decidido; exclui rejeitado; exclui já promovido (== current_version); exclui versão sem `_rascunho`
- [ ] `enviar_digest_rascunhos_pendentes()`: nenhum email quando não há pendência; 1 email por catalog-manager com email cadastrado; ignora catalog-manager sem email
- [ ] `notify_catalog_drafts_pending()`: assunto/contexto corretos, template genérico, sem `cta`
- [ ] `DraftDigestScheduler`: `start()` inicia thread; `stop()` encerra e faz join; chamar `start()` duas vezes não duplica thread

### Fase 6
- [ ] Scheduler só inicia quando `CONCILIUM__CATALOG_DIGEST_ENABLED=1`; `create_app()` nunca inicia thread real (verificado por import em teste)
- [ ] Suíte completa (`make test`), lint/type/fmt (`make check`) e cobertura (`make cov`) sem regressão

---

## Relacionados

- ADR-140 — Notificação por Email: Critério Atômico vs. Digest (esta ADR é a primeira aplicação concreta de D1-D3)
- ADR-120 — RBAC para Ciclo de Vida do Catálogo (origem do fluxo rascunho→merge/rejeição)
- ADR-134 — Template Jinja2 e separação infra/aplicação (mecanismo de envio reaproveitado)
- ADR-103 — Jobs na Camada de Aplicação (precedente do padrão thread+intervalo)
- ADR-062 — Versionamento genérico de entidades de configuração (`ConfigVersionService`, base de D1/D2)
