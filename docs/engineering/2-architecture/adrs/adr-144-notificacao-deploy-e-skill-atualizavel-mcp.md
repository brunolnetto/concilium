# ADR-144 — Notificação de Deploy e Skill de Instruções Atualizável via MCP

**Status:** Proposta
**Data:** 2026-07-20
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-093 (MCP como Serviço de Artefatos), ADR-101 (MCP Apps — recursos `ui://`), ADR-123 (Notificação por Email e Gestão de Dispositivos), ADR-140 (Critério Atômico vs. Digest — dedup por transição de estado, reaproveitado aqui para um canal diferente de email), ADR-141/ADR-143 (precedentes de scheduler — não reaproveitados nesta ADR, ver D4)

---

## Contexto

### Problema

P1. **O arquivo de instruções de uso do Concilium (`src/concilium/infrastructure/services/templates/concilium_usage_tutorial.skill`) é distribuído uma única vez, sem versão, sem forma de atualização sob demanda.** É lido do disco por `_read_skill_tutorial()` (`application/services/notifications.py:25-32`) e anexado só em dois fluxos: `notify_user_created` (cadastro, `commands_auth.py:241`) e `notify_client_code_migrated` (migração de código legado, `commands_auth.py:758`). Não tem cabeçalho de versão/data/hash — começa direto em `# Tutorial — Criar e Executar Projetos via MCP`. Não existe hoje nenhuma tool MCP, endpoint REST ou comando CLI que reenvie ou sirva esse conteúdo fora desses dois emails de onboarding.

P2. **O usuário não tem como saber se está com uma cópia desatualizada.** Confirmado nesta mesma sessão: dois documentos técnicos (`guia-fachada-mcp.md`, `pipeline-jobs-testing-guide.md`) ainda referenciavam `obter_estatisticas_jobs()`, removida há semanas (ADR-116 F5) — o próprio arquivo `.skill` já estava correto, mas nada além de uma auditoria manual garante isso. Um usuário cujo anexo de onboarding é anterior a uma remoção/renomeação de tool não tem nenhum sinal de que suas instruções estão obsoletas.

P3. **Não existe registro runtime consultável de deploys/revisions promovidas.** `cd/scripts/deploy.sh::cmd_deploy`/`cmd_promote` (linhas 155-260, 477-575) só escrevem `active_revision`/`deployed_revision`/`image_tag` em `$GITHUB_OUTPUT` — efêmero, existe só dentro da execução do workflow. Não há arquivo, blob, nem endpoint com histórico de "o que foi promovido, quando". `GET /health`/`ping()` não expõem tag de imagem nem revision atual (a versão do FastAPI é uma string fixa `"0.3.0"` no metadata, não reflete o deploy real).

P4. **Não existe nenhum sinal hoje, de nenhum tipo, quando o sistema muda de versão em produção.** Nenhum dos usuários cadastrados (`ClientRecord`, `auth_store.py:56-66`) fica sabendo quando uma nova revision é promovida — mesmo que essa revision remova uma tool, mude uma permissão (como o próprio ADR-143 fez nesta sessão) ou corrija um bug relevante para o fluxo deles.

P5. **Email como canal de entrega tem um problema estrutural para este caso de uso específico, distinto da fadiga de frequência do ADR-140.** Mesmo que a frequência de deploys (várias vezes por dia em períodos ativos) fosse resolvida com um digest, o problema real é *quando* a notícia é útil: o usuário precisa saber que algo mudou no momento em que está prestes a **usar** o sistema, não em um horário arbitrário de corte do digest. Email é *push* fora de banda — depende de ser lido antes da próxima sessão, o que não é garantido, e carrega toda a fragilidade já mapeada do `NotificationService` (SMTP síncrono, sem timeout, sem retry).

### Escopo

Esta ADR define três peças que se conectam: (1) um registro de deploy consultável, (2) a entrega dessa informação **embutida na resposta de `ping()`** — o tool que já é convenção documentada de início de sessão ("Use no início de uma sessão para confirmar que o sistema está disponível") — em vez de um canal de email separado, e (3) versionamento simples do skill file com uma tool MCP dedicada para buscar o conteúdo atual sob demanda. É uma ADR de discussão — pontos marcados **[A DECIDIR]** são propostas de partida.

**Divergência deliberada do padrão ADR-140/141/143:** as três notificações anteriores (catálogo, visibilidade) são entregues por email, com scheduler in-process dedicado. Esta ADR entrega por um canal diferente — a própria resposta de uma tool MCP já chamada no fluxo normal — e por isso **não introduz nenhum scheduler novo**. O princípio de dedup por transição de estado (ADR-140 D2) é reaproveitado, mas adaptado ao canal: em vez de "não enviar o mesmo digest duas vezes", é "não repetir o mesmo aviso ao mesmo `client_id` em toda chamada de `ping()` para sempre".

---

## Decisão

### D1 — Registro de deploy persistente (novo)

Introduzir um blob append-only `deploy/history.json` (prefixo "sistema", mesmo padrão de `auth/`, `observability/`) com uma entrada por promoção: `{image_tag, api_revision, mcp_revision, promoted_at, resumo}`. `resumo` é texto curto — **[A DECIDIR]** se preenchido manualmente (flag `--changelog` no `deploy.sh promote`) ou derivado automaticamente de `git log <tag_anterior>..<tag_nova> --oneline` no momento do build. Como o conteúdo vai ser embutido numa resposta de tool (D2), `resumo` deve ser curto (1-2 linhas) — não o corpo longo que um email digest suportaria.

**Mecanismo de escrita — o ponto mais aberto desta ADR — três candidatos:**

a. `cd/scripts/deploy.sh cmd_promote` escreve direto no blob storage de sistema, usando as credenciais Azure já presentes no ambiente de CI (`AZURE_ACCOUNT`/`AZURE_CONTAINER`/`AZURE_KEY`, já passadas em `_run-deploy-command.yml`) — **precisa confirmar se essas credenciais apontam para o mesmo backend usado em produção (hoje SharePoint, ADR-047) ou são de um backend Azure Blob separado/legado**; isso não ficou claro na investigação e precisa ser confirmado antes de escolher esta via.
b. Um novo comando CLI (`concilium ops deploy record-promotion ...`) executado **dentro do container recém-promovido** via `az containerapp exec` — reaproveita as credenciais reais de storage que o app já usa em runtime, sem depender de saber qual backend a CI está configurada para acessar.
c. MVP sem storage novo: não persistir um log completo — só a última entrada (`deploy/latest.json`, sobrescrito a cada promoção, sem histórico) — suficiente para D2, que só precisa comparar "a última promoção" contra o cursor de cada `client_id`, não uma lista completa.

Proposta de partida: **(b)**, por reaproveitar credenciais já corretas e não introduzir ambiguidade de backend; (c) é o MVP mais barato se a equipe preferir começar pequeno e não precisar de histórico completo, só do estado mais recente.

### D2 — Entrega: embutida na resposta de `ping()`, não por email

`ping()` (`presentation/mcp/tools/system.py`, `@permission("health:read")`) passa a incluir um campo `novidades` na resposta quando há algo não visto ainda pelo `client_id` que chamou:

```
{
  status: "ok",
  ...campos de health check existentes...,
  novidades: {
    deploy: {resumo: "...", promoted_at: "..."} | null,
    skill_desatualizado: true | false
  }
}
```

`client_id` vem de `get_current_user_id()` (mesmo padrão já usado em `auth_directory.py`/ADR-143). Sem identidade resolvível (ex. AUTH_ENABLED=0 em dev), `novidades` não é computado — não há `client_id` para versionar o cursor.

### D3 — Dedup por cursor em `ClientRecord`, dois campos distintos

Dois novos campos em `ClientRecord` (`auth_store.py`), mesma convenção de extensão aditiva já usada para `email`/`client_code_hash` (ADR-123):

- `last_deploy_seen: str = ""` — timestamp (`promoted_at`) da última entrada de deploy já entregue a este `client_id`. **Atualizado pelo próprio `ping()`**, no momento em que inclui o aviso na resposta — o aviso é "entregue e reconhecido" assim que aparece uma vez, mesmo que o usuário não aja sobre ele. Isso é intencional: `ping()` está *avisando*, o dado em si (o que mudou) é curto e já está na própria resposta.
- `last_skill_version_seen: int = 0` — versão do `.skill` (D5) que este `client_id` já buscou. **Atualizado pela tool de D6** (`obter_instrucoes_atualizadas()`), não por `ping()` — `ping()` só *aponta* que há versão nova (`skill_desatualizado: true`), quem *entrega* o conteúdo é a outra tool, e é nesse momento que o cursor avança.

Essa distinção importa: se `ping()` marcasse `last_skill_version_seen` como visto só por mencionar que existe versão nova, um usuário que ignorasse o aviso nunca mais veria o lembrete — o cursor de skill só avança quando o conteúdo de fato é buscado.

### D4 — Sem scheduler novo

Como a entrega é por-chamada (D2), não por push periódico, não há necessidade de nenhum componente in-process novo (thread, `Event.wait`, singleton) — ao contrário do padrão dos ADR-141/143. `ping()` já roda por-request; a leitura de `deploy/history.json` (ou `deploy/latest.json`, se optar por (c) em D1) e a comparação de cursor acontecem inline na própria chamada.

### D5 — Versionamento do skill file: contador explícito, não mtime

Adicionar um cabeçalho ao `.skill` (`# Versão: N — AAAA-MM-DD`, incrementado manualmente a cada edição de conteúdo relevante, não a cada commit trivial). **Mtime do arquivo é rejeitado como versão** (ver Alternativas A4) — não sobrevive de forma confiável a cópias/anexos de email, e um usuário comparando duas cópias não tem como inspecionar mtime de um anexo recebido.

### D6 — Nova tool MCP: sempre lê o arquivo atual, nunca o congela no boot

Nova tool `obter_instrucoes_atualizadas()` (nome provisório — **[A DECIDIR]**), sem `project_id` (mesmo padrão "de sistema" de `ping()`), gated por `AUTH_SELF` (self-service, já concedida a todos os roles). Reaproveita `_read_skill_tutorial()` — hoje privada em `notifications.py`, precisa ser promovida a uma função de serviço compartilhada (ex. `application/services/skill_content.py`) para não duplicar a leitura do arquivo entre o fluxo de email de onboarding e a tool nova. Ao ser chamada, atualiza `last_skill_version_seen` (D3) do `client_id` para a versão atual.

**Achado crítico da investigação, que motiva esta decisão de design:** o precedente mais próximo de "servir conteúdo estático via MCP" (`_register_ui_resources`, ADR-101, `server.py:138-166`) lê o HTML **uma vez, no boot do servidor**, e nunca mais — se a tool nova seguisse esse padrão, ficaria presa à versão do último restart do processo, o que anularia o propósito de "sempre pegar a versão mais atual". A tool precisa ler o arquivo do disco a cada chamada, como `_read_skill_tutorial()` já faz corretamente hoje.

### D7 — O aviso em `ping()` sempre aponta para a tool de conteúdo

Quando `novidades.skill_desatualizado: true`, a resposta de `ping()` inclui uma mensagem fixa: "Suas instruções estão desatualizadas — chame `obter_instrucoes_atualizadas()` para pegar a versão mais recente." Não há comparação de conteúdo/hash — a checagem é puramente numérica (`last_skill_version_seen < versão_atual`).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Digest de email periódico (design original desta ADR, revisado nesta mesma sessão) | Push fora de banda — depende do email ser lido antes da próxima sessão; carrega a fragilidade já mapeada do `NotificationService` (SMTP síncrono, sem retry); `ping()` embutido entrega exatamente no momento em que a informação é acionável, sem esse risco |
| A2 | Notificação atômica por deploy (1 email por promoção) | Mesmo problema de A1, agravado pela frequência de deploys (P5 original) |
| A3 | Reenviar o `.skill` inteiro por email a cada mudança | Mesma fadiga; contradiz a preferência já estabelecida (ADR-141/143) por pull sob demanda quando uma tool de consulta é viável |
| A4 | Servir o skill via recurso `ui://` (MCP Apps, ADR-101) em vez de tool | Recursos `ui://` são HTML renderizado em iframe para apps interativos — o skill é texto de instruções que o agente deve ler como contexto, não uma interface visual; e o padrão de leitura-no-boot do `_register_ui_resources` é incompatível com "sempre a versão atual" (ver D6) |
| A5 | Usar mtime do arquivo como versão | Não sobrevive de forma confiável a cópias/anexos de email; um usuário não tem como inspecionar mtime de um anexo recebido para comparar |
| A6 | Detecção automática de mudança via hash do conteúdo do skill, em vez de contador de versão manual | Mais mecânico, mas contador manual (D5) já resolve o problema com menos partes móveis, e um humano decide o que conta como "mudança relevante" (evita bump por commit trivial) |
| A7 | Marcar `last_skill_version_seen` como visto assim que `ping()` menciona a novidade, sem esperar a busca real | Rejeitado (ver D3) — um usuário que ignorasse o aviso uma vez nunca mais o veria; o cursor só avança quando o conteúdo é de fato entregue |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Entrega garantida no momento relevante | Diferente de email, o aviso aparece exatamente quando o agente confirma que o sistema está disponível — o início de toda sessão, por convenção já documentada |
| Nenhum componente novo em background | D4 — sem scheduler, sem thread, sem infraestrutura de digest; a lógica inteira roda inline em `ping()` |
| Usuário sempre pode pegar a versão atual das instruções | D6 elimina a dependência do anexo estático de onboarding para ficar atualizado |
| Deploys ficam auditáveis | D1 cria o primeiro registro runtime consultável de "o que foi promovido, quando" — hoje não existe nenhum |
| Fecha o tipo de gap encontrado nesta sessão | P2 (docs desatualizadas sem sinal para o usuário) passa a ter um caminho de correção sem depender de auditoria manual |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Mecanismo de escrita do deploy log (D1) depende de confirmar qual backend as credenciais de CI realmente acessam | Marcado explicitamente como o ponto mais aberto da ADR; opção (b) (escrever via `az containerapp exec` dentro do container já promovido) evita a ambiguidade por usar as credenciais reais de runtime |
| Só funciona se o agente de fato chamar `ping()` | Aceitável — é convenção já documentada de início de sessão; quem pula esse passo também pulava qualquer benefício de um digest de email que não lesse |
| Dois novos campos em `ClientRecord` (D3) — mais estado a manter por usuário | Extensão aditiva simples, mesmo padrão já usado para `email`/`client_code_hash`; sem migração necessária (`_client_record()` já usa `setdefault` para campos novos) |
| D7 é uma checagem numérica de versão, não uma detecção de relevância do que mudou | Aceitável como F1 — um humano decide quando incrementar a versão (D5), o que já filtra bumps triviais |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Este ADR | Problema documentado, decisões D1-D7 propostas para discussão | 💡 Proposta |
| F2 — Validação | Confirmar mecanismo de escrita do deploy log (D1); nome da tool (D6); formato exato de `resumo` | ⬜ Não iniciado |
| F3 — Deploy log | `deploy/history.json` (ou `deploy/latest.json`, conforme D1); comando CLI ou passo de CI para escrever a entrada na promoção | ⬜ Não iniciado |
| F4 — `ping()` com novidades | Dois campos novos em `ClientRecord`; lógica de comparação de cursor embutida em `ping()` (D2/D3) | ⬜ Não iniciado |
| F5 — Skill atualizável via MCP | Cabeçalho de versão no `.skill` (D5); `application/services/skill_content.py` (promove `_read_skill_tutorial` a serviço compartilhado); tool MCP nova (D6); atualização de cursor ao ser chamada |

## Definition of Done

### Fase 1
- [ ] Mecanismo de escrita do deploy log (D1) confirmado com o usuário
- [ ] Nome definitivo da tool MCP (D6) decidido
- [ ] Status atualizado para Aceito/Decidido

### Fase 3-5 (após validação)
- [ ] `deploy/history.json`/`latest.json` populado por pelo menos um deploy real
- [ ] Teste confirmando que `ping()` sem novidade pendente não inclui o campo `novidades` (ou o inclui vazio) e não atualiza cursores sem necessidade
- [ ] Teste confirmando que `last_deploy_seen` avança ao ser entregue por `ping()`, e `last_skill_version_seen` só avança quando `obter_instrucoes_atualizadas()` é de fato chamada (D3/A7)
- [ ] Tool MCP testada confirmando que lê o arquivo a cada chamada (não congela conteúdo no boot do servidor)
- [ ] Cabeçalho de versão presente no `.skill` e exposto no retorno da tool

---

## Relacionados

- ADR-093 — MCP como Serviço de Artefatos (precedente de "servir conteúdo via MCP", escopado a projeto — esta ADR generaliza para conteúdo de sistema)
- ADR-101 — MCP Apps (precedente rejeitado para D6 — recursos `ui://` são para HTML interativo, e o padrão de leitura-no-boot motivou o cuidado explícito em D6)
- ADR-123 — Notificação por Email (infraestrutura de envio existente, mas **não** reaproveitada nesta ADR — ver P5/Escopo para a divergência deliberada)
- ADR-140 — Critério Atômico vs. Digest (o princípio de dedup por transição de estado, D2 daquela ADR, é reaproveitado aqui para um canal diferente de email — ver D3)
- ADR-141/ADR-143 — Digests por email com scheduler in-process (padrão **não** seguido nesta ADR — ver D4 e Alternativa A1 para o porquê)
