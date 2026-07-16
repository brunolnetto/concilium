# ADR-140 — Notificação por Email: Critério Atômico vs. Digest para Eventos de Alta Frequência

**Status:** Proposta
**Data:** 2026-07-16
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-123, ADR-126, ADR-131, ADR-134 (padrão de notificação existente); ADR-103 (Jobs na Camada de Aplicação — precedente de mecanismo de loop com intervalo); ADR-120 (RBAC de catálogo — motiva um dos candidatos futuros)

---

## Contexto

### Problema

P1. **Não existe hoje nenhum critério documentado para decidir quando um novo caso de uso de email deve ser atômico (síncrono, inline, 1 evento → 1 email) ou agregado (digest).** O ADR-131 D5 decidiu, para os 12 casos de uso existentes, manter disparo síncrono e inline sem fila/event bus — decisão correta para aquele conjunto, mas motivada por uma característica específica desses eventos (comandos administrativos raros, disparados por decisão humana explícita) que não se generaliza automaticamente para qualquer notificação futura.

P2. **Uma análise exploratória do sistema de notificação identificou candidatos de email para eventos de negócio que hoje não notificam ninguém, mas cujo perfil de frequência é estruturalmente diferente dos 12 casos existentes:**

- **Aprovação de rascunho de catálogo** (`aprovar_merge_catalogo`/`rejeitar_rascunho_catalogo`, ADR-120) — um engineer pode submeter múltiplos rascunhos por dia; um catalog-manager pode ter vários contextos sob revisão simultaneamente. Um email por submissão o colocaria em contato repetido com o mesmo tipo de evento em curto intervalo.
- **Falha de execução de pipeline/job** (`application/jobs/service.py`, state machine `AGUARDANDO_FILA → EM_EXECUCAO → CONCLUIDO/ERRO`) — pipelines podem rodar dezenas de vezes por dia por projeto durante exploração de cenários; um email por falha de execução repetiria o mesmo alerta a cada nova tentativa.
- **Anomalias de `catalog_reasonability`** (outliers via IQR) — a análise roda a cada pipeline/reprocessamento; sem controle de estado, a mesma anomalia dispararia um novo email a cada execução, mesmo sem nenhuma mudança real na condição.
- **Alertas financeiros/BDI** (custo, C_r, matriz de eficiência) — recalculados a cada pipeline; um alerta de "limite de custo ultrapassado" sem dedup dispararia a cada recálculo enquanto o projeto permanecer no mesmo estado, não apenas na transição que importa.

O traço comum: nos quatro casos, o evento-gatilho é subproduto de **reprocessamento automático** (rodar de novo o pipeline, reavaliar o catálogo), não de uma ação humana distinta e intencional — e o mesmo destinatário pode acumular várias instâncias do "mesmo" sinal em pouco tempo. Isso é estruturalmente diferente dos 12 casos do ADR-131/134, onde cada email corresponde a uma decisão humana específica e não recorrente para aquele destinatário.

P3. **Não existe nenhuma infraestrutura de agregação, dedup ou cooldown de email em todo o projeto.** Confirmado por busca exaustiva nos módulos de notificação e nos domínios candidatos (catálogo, jobs, analytics) — zero ocorrência de `digest`/`batch`/`throttle`/`debounce`/`cooldown`/`dedup`. Implementar qualquer um dos candidatos de P2 no padrão atual (`NotificationService.send()` chamado inline a cada evento) reproduziria o problema descrito, não o resolveria.

P4. **Gap correlato, fora de escopo desta ADR, mas evidência do mesmo vácuo:** `notify_ownership_invite_expired` (ADR-134 D6) só dispara *lazily* — se e quando alguém tenta aceitar um convite já vencido — porque não há nenhum job proativo que varra TTLs expirados. Não há hoje, em todo o sistema de notificação, nenhum mecanismo agendado/periódico — reforça P3, mas corrigir esse gap específico não é objeto desta ADR.

P5. **Achado descartado após reanálise:** a investigação inicial apontou `migrate-legacy-codes` (`presentation/cli/commands_auth.py:388-441`) como um caso onde N emails disparariam na mesma execução — mas isso **não é o problema de fadiga descrito em P2**. Cada usuário migrado recebe exatamente um email para o seu próprio endereço, com seu próprio anexo de configuração — é fan-out correto para N destinatários distintos, não repetição do mesmo sinal para o mesmo destinatário. O comando já é resiliente: `NotificationService.send()` nunca propaga exceção, o loop continua entre usuários, cada iteração já reporta sucesso/falha (`rprint`) e uma seção final agrega os casos de entrega manual (sem email cadastrado ou falha de envio). Não há gap real a fechar aqui — citado por registrar a correção e evitar que o mesmo engano se repita numa análise futura.

### Escopo

Esta ADR define **o critério de decisão** (D1) e **o padrão de dedup por transição de estado** (D2) a aplicar em qualquer notificação futura, e propõe **o mecanismo concreto de agregação** a reaproveitar (D3) quando esses casos forem implementados. **Não implementa** nenhuma das notificações de catálogo, pipeline, anomalias ou financeiras citadas em P2 — cada uma é decisão de produto separada, com sua própria ADR/PR, que deve aplicar o critério aqui definido.

---

## Decisão

### D1 — Critério: quando um caso de uso de email deve ser atômico vs. agregado

**Mantém-se atômico/inline (padrão ADR-131 D5)** quando o evento satisfaz **todas** as condições:

a. É 1:1 com uma ação humana distinta e intencional (não um subproduto de recálculo/reprocessamento automático);
b. O mesmo destinatário não deve, no funcionamento normal do sistema, receber o mesmo tipo de evento repetidamente em uma janela curta de tempo;
c. Quando há fan-out em lote (um comando dispara N emails), cada destinatário é distinto e recebe exatamente um email relevante para si (precedente validado: `migrate-legacy-codes`, P5).

**Exige agregação/dedup** quando **qualquer uma** das condições abaixo se aplica:

d. O evento deriva de reprocessamento automático que pode legitimamente se repetir para a mesma condição de fundo (reexecução de pipeline, reavaliação de catálogo, recálculo financeiro) — a notificação deve ser disparada pela **transição de estado** (D2), não pelo evento bruto;
e. O papel do destinatário acumula naturalmente várias instâncias do mesmo tipo de evento em operação normal (ex.: catalog-manager com múltiplos rascunhos pendentes simultâneos).

Os 4 candidatos de P2 (aprovação de catálogo, falha de pipeline, anomalias de reasonability, alertas financeiros) se enquadram em (d) e/ou (e) — nenhum deles deve ser implementado como envio atômico por evento bruto.

### D2 — Dedup por transição de estado, não por evento bruto

Para alertas derivados de recálculo (anomalias, thresholds, falhas repetidas), a notificação dispara **apenas na transição** — ex. `normal → anômalo`, `abaixo-do-limite → acima-do-limite`, `sem-falha → falhou`, nunca a cada execução que mantém o mesmo estado. Isso requer persistir o último estado notificado (ex.: em metadado do projeto/contexto/job) e comparar a cada execução — nunca confiar em cache sem revalidar contra o estado real, para não perder uma transição de volta (`anômalo → normal` também é sinal, se o caso de uso decidir notificar isso).

Para acúmulo de itens pendentes de ação humana (rascunhos de catálogo aguardando aprovação), o disparo não é por transição de estado individual, mas por **digest periódico** (D3) — o destinatário recebe um resumo consolidado do que está pendente no momento da execução do digest, não um email por item.

### D3 — Mecanismo de agregação a introduzir: job agendado com intervalo, não fila/broker

Não introduzir fila de mensagens ou event bus (mantém a rejeição de infraestrutura pesada já estabelecida no ADR-131 D5/A4). O precedente arquitetural já existe no próprio código: `JobService._garbage_collector_loop` (`application/jobs/service.py:77-80`) — uma thread daemon com `Event.wait(timeout=intervalo)` que roda uma função de limpeza periodicamente.

Cada futuro caso de uso de digest/dedup deve seguir o mesmo padrão: um componente com loop de intervalo configurável (ex. diário para digest de rascunhos pendentes; por execução de pipeline para dedup de anomalias/thresholds) que consulta o estado atual do domínio correspondente e, quando há algo a notificar, chama `NotificationService.send()`/`application/services/notifications.py` (reaproveitando templates genéricos do ADR-134 D2) — nunca reimplementando o envio.

### D4 — `migrate-legacy-codes` permanece inalterado

Conforme P5, a reanálise não encontrou gap real: o fluxo já é resiliente e já expõe status por usuário e resumo de entrega manual. Nenhuma mudança de código é proposta por esta ADR para esse comando.

### D5 — Regra de referência para ADRs futuras

Toda ADR futura que introduza um novo caso de uso de email deve, na seção de Decisão, aplicar explicitamente o critério D1 (justificando atômico ou agregado) e, se agregado, especificar o estado que dispara D2 e reaproveitar o mecanismo de D3 em vez de propor um novo.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter todos os casos futuros no padrão atômico/inline do ADR-131 D5 | Geraria fadiga real ao mesmo destinatário para eventos derivados de reprocessamento automático (P2) — perfil de frequência incompatível com a premissa que justificou D5 (ação humana rara) |
| A2 | Fila/broker de mensagens (Celery, RabbitMQ, Azure Service Bus) para desacoplar e agregar | Custo de infraestrutura desproporcional ao volume real; o padrão de thread com intervalo já existe (`_garbage_collector_loop`) e resolve o mesmo problema sem novo componente externo — consistente com a rejeição de A4 no ADR-131 |
| A3 | Dedup por hash/igualdade textual do corpo do email | Frágil a variações triviais (ex. um valor numérico mudando na 3ª casa decimal geraria "novo" alerta); dedup deve ser por transição de estado de domínio (D2), não por comparação de texto |
| A4 | Corrigir `migrate-legacy-codes` com um resumo agregado ao admin | Descartada após reanálise (P5) — o comando já expõe status por usuário em tempo real e uma seção final de entrega manual já agregada; não há gap a fechar |
| A5 | Implementar diretamente os 4 casos de uso de P2 nesta mesma ADR | Fora de escopo — cada um é decisão de produto independente (o que constitui "pendente", qual o intervalo do digest, quem é o destinatário exato); esta ADR define o critério e o mecanismo, não os casos concretos |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Critério explícito evita decisão ad-hoc | Cada ADR futura de notificação aplica D1 em vez de reabrir a discussão atômico-vs-agregado do zero |
| Reaproveita mecanismo já validado | D3 usa o mesmo padrão de thread+intervalo já em produção em `JobService`, sem novo componente de infraestrutura |
| Preserva a decisão original para os casos existentes | Nenhuma migração é exigida para os 12 casos de uso do ADR-131/134 — eles já satisfazem D1(a-c) |
| Dedup por estado evita fadiga sem exigir infraestrutura pesada | D2 resolve o problema central (mesmo destinatário, mesmo sinal, repetido) com persistência simples de estado, não com fila |
| Correção documentada de um falso positivo | P5 registra que `migrate-legacy-codes` foi investigado e descartado, evitando reinvestigação futura do mesmo achado |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| ADR de critério, sem feature concreta entregue — risco de ficar só no papel | D5 torna obrigatório citar e aplicar esta ADR em qualquer PR/ADR futura que introduza notificação nova; revisão de código como enforcement (mesmo padrão de custo-benefício aceito no ADR-131 A3) |
| D2 introduz um novo dado a manter (último estado notificado) — risco de drift entre estado registrado e estado real | O digest/dedup sempre revalida contra o estado real do domínio na execução, nunca confia apenas no valor persistido como fonte de verdade — o valor persistido só serve para decidir se already notificou aquele estado |
| Nenhum destinatário-admin centralizado hoje (sem CC, sem lista de distribuição) — um digest precisa saber "para quem" agregar | Fora de escopo desta ADR; cada caso de uso futuro (ex. digest de catálogo) resolve isso ao definir seu destinatário (ex. todos com role `catalog-manager` no contexto), não é um problema do mecanismo genérico |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Este ADR | Critério D1, padrão de dedup D2, mecanismo de agregação D3 documentados; achado de `migrate-legacy-codes` investigado e descartado (P5/D4) | 💡 Proposta |
| F2 — Aplicação (fora desta ADR) | Cada caso de uso futuro (aprovação de catálogo, falha de pipeline, anomalias de reasonability, alertas financeiros) ganha sua própria ADR aplicando D1-D3 | ⬜ Não iniciado |

## Definition of Done

### Fase 1
- [ ] ADR revisado e status atualizado para Aceito/Decidido
- [ ] `migrate-legacy-codes` confirmado como não precisando de mudança (D4) — nenhuma ação de código nesta fase
- [ ] Critério D1 e mecanismo D3 referenciáveis por número desta ADR em decisões futuras

---

## Relacionados

- ADR-123 — Serviço de Notificação por Email (origem do `NotificationService`)
- ADR-126 — Project Ownership (motivou as 5 notificações de handover, todas atômicas por satisfazerem D1 a-c)
- ADR-131 — Notificação em CRUD de usuário (decisão D5 de manter síncrono/inline para os casos existentes — esta ADR generaliza o critério por trás dessa decisão)
- ADR-134 — Template Jinja2 e separação infra/aplicação (mecanismo de envio reaproveitado por D3)
- ADR-103 — Jobs na Camada de Aplicação (precedente do padrão thread+intervalo reaproveitado em D3)
- ADR-120 — RBAC para Ciclo de Vida do Catálogo (motiva o candidato de aprovação de rascunho citado em P2, a ser implementado em ADR futura)
