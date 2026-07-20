# ADR-144 — Notificação de Deploy e Skill de Instruções Atualizável via MCP

**Status:** Proposta
**Data:** 2026-07-20
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-093 (MCP como Serviço de Artefatos), ADR-101 (MCP Apps — recursos `ui://`), ADR-123 (Notificação por Email e Gestão de Dispositivos), ADR-131 (Notificação em Operações CRUD), ADR-134 (Template Jinja2 e separação infra/aplicação), ADR-140 (Critério Atômico vs. Digest), ADR-141 (Digest de Rascunhos de Catálogo), ADR-143 (Visibilidade de Usuários + Digest)

---

## Contexto

### Problema

P1. **O arquivo de instruções de uso do Concilium (`src/concilium/infrastructure/services/templates/concilium_usage_tutorial.skill`) é distribuído uma única vez, sem versão, sem forma de atualização sob demanda.** É lido do disco por `_read_skill_tutorial()` (`application/services/notifications.py:25-32`) e anexado só em dois fluxos: `notify_user_created` (cadastro, `commands_auth.py:241`) e `notify_client_code_migrated` (migração de código legado, `commands_auth.py:758`). Não tem cabeçalho de versão/data/hash — começa direto em `# Tutorial — Criar e Executar Projetos via MCP`. Não existe hoje nenhuma tool MCP, endpoint REST ou comando CLI que reenvie ou sirva esse conteúdo fora desses dois emails de onboarding.

P2. **O usuário não tem como saber se está com uma cópia desatualizada.** Confirmado nesta mesma sessão: dois documentos técnicos (`guia-fachada-mcp.md`, `pipeline-jobs-testing-guide.md`) ainda referenciavam `obter_estatisticas_jobs()`, removida há semanas (ADR-116 F5) — o próprio arquivo `.skill` já estava correto, mas nada além de uma auditoria manual garante isso. Um usuário cujo anexo de onboarding é anterior a uma remoção/renomeação de tool não tem nenhum sinal de que suas instruções estão obsoletas.

P3. **Não existe registro runtime consultável de deploys/revisions promovidas.** `cd/scripts/deploy.sh::cmd_deploy`/`cmd_promote` (linhas 155-260, 477-575) só escrevem `active_revision`/`deployed_revision`/`image_tag` em `$GITHUB_OUTPUT` — efêmero, existe só dentro da execução do workflow. Não há arquivo, blob, nem endpoint com histórico de "o que foi promovido, quando". `GET /health`/`ping()` não expõem tag de imagem nem revision atual (a versão do FastAPI é uma string fixa `"0.3.0"` no metadata, não reflete o deploy real).

P4. **Não existe nenhuma notificação hoje quando o sistema muda de versão em produção.** Nenhum dos usuários cadastrados (`ClientRecord`, `auth_store.py:56-66`) fica sabendo quando uma nova revision é promovida — mesmo que essa revision remova uma tool, mude uma permissão (como o próprio ADR-143 fez nesta sessão) ou corrija um bug relevante para o fluxo deles.

P5. **Deploys não são um evento raro.** Pela cadência observada nesta sessão e no histórico de ADRs implementadas (múltiplas por dia em períodos de trabalho ativo), promover uma revision nova pode acontecer várias vezes ao dia — isso é relevante para D2 abaixo, pois muda a resposta do critério do ADR-140.

### Escopo

Esta ADR define quatro peças que se conectam: (1) um registro de deploy consultável, (2) o critério de notificação sobre esse registro (atômico vs. digest, aplicando ADR-140 D1 explicitamente, conforme exigido por ADR-140 D5), (3) versionamento simples do skill file, e (4) uma tool MCP que sirva sempre a versão atual desse arquivo, sem depender de reenvio de email. É uma ADR de discussão — pontos marcados **[A DECIDIR]** são propostas de partida.

---

## Decisão

### D1 — Registro de deploy persistente (novo)

Introduzir um blob append-only `deploy/history.json` (prefixo "sistema", mesmo padrão de `auth/`, `observability/`) com uma entrada por promoção: `{image_tag, api_revision, mcp_revision, promoted_at, resumo}`. `resumo` é texto livre — **[A DECIDIR]** se preenchido manualmente (flag `--changelog` no `deploy.sh promote`) ou derivado automaticamente de `git log <tag_anterior>..<tag_nova> --oneline` no momento do build.

**Mecanismo de escrita — o ponto mais aberto desta ADR — três candidatos:**

a. `cd/scripts/deploy.sh cmd_promote` escreve direto no blob storage de sistema, usando as credenciais Azure já presentes no ambiente de CI (`AZURE_ACCOUNT`/`AZURE_CONTAINER`/`AZURE_KEY`, já passadas em `_run-deploy-command.yml` — **precisa confirmar se essas credenciais apontam para o mesmo backend usado em produção (hoje SharePoint, ADR-047) ou são de um backend Azure Blob separado/legado**; isso não ficou claro na investigação e precisa ser confirmado antes de escolher esta via.
b. Um novo comando CLI (`concilium ops deploy record-promotion ...`) executado **dentro do container recém-promovido** via `az containerapp exec` — reaproveita as credenciais reais de storage que o app já usa em runtime, sem depender de saber qual backend a CI está configurada para acessar.
c. MVP sem storage novo: não persistir nada — a "fonte de verdade" do que mudou é sempre `git log` entre tags, e o scheduler (D3) só precisa saber qual foi a última tag notificada (isso *ainda* precisa de 1 dado persistido — a última tag notificada — mas não um log completo).

Proposta de partida: **(b)**, por reaproveitar credenciais já corretas e não introduzir ambiguidade de backend; (c) é o MVP mais barato se a equipe preferir começar pequeno.

### D2 — Critério de notificação: digest, não atômico (aplica ADR-140 D1 explicitamente)

Por P5, um deploy não satisfaz a condição (b) do ADR-140 D1 ("o mesmo destinatário não deve receber o mesmo tipo de evento repetidamente em janela curta") — múltiplos deploys por dia por um mesmo destinatário cai em (d)/(e): **exige agregação**. Notificar por email a cada promoção reproduziria exatamente a fadiga que o ADR-140 existe para prevenir.

**Notificação por transição de estado (D2 do ADR-140):** o gatilho não é "houve um deploy", é "há deploy(s) novo(s) desde o último aviso a este destinatário" — mesmo padrão do `VisibilityDigestScheduler` (ADR-143 D8): dedup pelo cursor "última entrada de `deploy/history.json` já notificada", revalidado contra o estado real a cada execução.

### D3 — Mecanismo: novo scheduler seguindo o padrão já estabelecido

`DeployDigestScheduler`, mesmo esqueleto de `DraftDigestScheduler`/`VisibilityDigestScheduler`: thread daemon, `Event.wait(intervalo)`, singleton, nunca iniciado em `create_app()`. Intervalo **[A DECIDIR]** — candidato natural: diário (mesma cadência de `DraftDigestScheduler`, já que "o que mudou hoje" é uma cadência razoável para um resumo de deploys, mais lenta que o digest de visibilidade de 5min do ADR-143, que reagia a um sinal de alta frequência diferente). Só envia quando há entrada nova em `deploy/history.json` desde o cursor do destinatário (time-gating por conteúdo, mesmo princípio do ADR-143 D8).

### D4 — Destinatários: papéis operacionais, não broadcast geral **[A DECIDIR]**

Nenhuma notificação hoje faz broadcast puro para todos os usuários ativos independente de role (o precedente mais próximo, `notify_visibility_queried`, ainda é 1:1 por usuário afetado, não broadcast). Proposta de partida: `admin` e `engineer` — roles com contexto operacional para agir sobre uma mudança de sistema (ex.: uma tool removida que eles usam em automação). `operator`/`auditor`/`catalog-manager` ficariam de fora por padrão, mas isso é exatamente o tipo de decisão que fica marcada em aberto para validar com o usuário.

### D5 — Versionamento do skill file: contador explícito, não mtime

Adicionar um cabeçalho ao `.skill` (`# Versão: N — AAAA-MM-DD`, incrementado manualmente a cada edição de conteúdo relevante, não a cada commit trivial). **Mtime do arquivo é rejeitado como versão** (ver Alternativas A4) — não sobrevive de forma confiável a cópias/anexos de email, e um usuário comparando duas cópias não tem como inspecionar mtime de um anexo recebido.

### D6 — Nova tool MCP: sempre lê o arquivo atual, nunca o congela no boot

Nova tool `obter_instrucoes_atualizadas()` (nome provisório — **[A DECIDIR]**), sem `project_id` (mesmo padrão "de sistema" de `ping()`, `presentation/mcp/tools/system.py`), gated por `AUTH_SELF` (self-service, já concedida a todos os roles). Reaproveita `_read_skill_tutorial()` — hoje privada em `notifications.py`, precisa ser promovida a uma função de serviço compartilhada (ex. `application/services/skill_content.py`) para não duplicar a leitura do arquivo entre o fluxo de email e a tool nova.

**Achado crítico da investigação, que motiva esta decisão de design:** o precedente mais próximo de "servir conteúdo estático via MCP" (`_register_ui_resources`, ADR-101, `server.py:138-166`) lê o HTML **uma vez, no boot do servidor**, e nunca mais — se a tool nova seguisse esse padrão, ficaria presa à versão do último restart do processo, o que anularia o propósito de "sempre pegar a versão mais atual". A tool precisa ler o arquivo do disco a cada chamada, como `_read_skill_tutorial()` já faz corretamente hoje.

### D7 — Vínculo entre o digest de deploy e a tool de instruções

Quando o digest de deploy (D2/D3) inclui uma promoção cujo `resumo` menciona mudança de tool/skill, o corpo do email adiciona uma linha fixa apontando para a tool nova: "As instruções de uso podem ter mudado — chame `obter_instrucoes_atualizadas()` para pegar a versão mais recente." Não há detecção automática de "o conteúdo do skill mudou" nesta ADR — é um lembrete textual sempre presente no digest de deploy, não uma comparação de hash (fora de escopo, ver Alternativas A5).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Notificação atômica por deploy (1 email por promoção) | Viola ADR-140 D1(d)/(e) — múltiplos deploys/dia (P5) gerariam fadiga real ao mesmo destinatário |
| A2 | Reenviar o `.skill` inteiro por email a cada mudança | Mesma fadiga de A1; e contradiz a preferência já estabelecida (ADR-141/143) por pull sob demanda em vez de push repetido quando uma tool de consulta é viável |
| A3 | Servir o skill via recurso `ui://` (MCP Apps, ADR-101) em vez de tool | Recursos `ui://` são HTML renderizado em iframe para apps interativos — o skill é texto de instruções que o agente deve ler como contexto, não uma interface visual; e o padrão de leitura-no-boot do `_register_ui_resources` é incompatível com "sempre a versão atual" (ver D6) |
| A4 | Usar mtime do arquivo como versão | Não sobrevive de forma confiável a cópias/anexos de email; um usuário não tem como inspecionar mtime de um anexo recebido para comparar |
| A5 | Detecção automática de mudança via hash do conteúdo do skill, disparando notificação dedicada | Fora de escopo desta ADR — exigiria mais um estado a persistir (último hash notificado) e um segundo critério de digest paralelo ao de deploy; o lembrete textual fixo (D7) resolve o problema prático com menos mecanismo novo |
| A6 | Escrever o registro de deploy usando fila/broker de mensagens | Rejeitado pelo mesmo precedente do ADR-131/140 — thread com intervalo já resolve, sem infraestrutura nova |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Usuário sempre pode pegar a versão atual das instruções | D6 elimina a dependência do anexo estático de onboarding para ficar atualizado |
| Deploys ficam auditáveis | D1 cria o primeiro registro runtime consultável de "o que foi promovido, quando" — hoje não existe nenhum |
| Reaproveita critério e mecanismo já validados | D2/D3 aplicam ADR-140 D1 explicitamente (exigido por D5 daquela ADR) e o mesmo esqueleto de scheduler dos dois digests já implementados |
| Fecha o tipo de gap encontrado nesta sessão | P2 (docs desatualizadas sem sinal para o usuário) passa a ter um caminho de correção sem depender de auditoria manual |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Mecanismo de escrita do deploy log (D1) depende de confirmar qual backend as credenciais de CI realmente acessam | Marcado explicitamente como o ponto mais aberto da ADR; opção (b) (escrever via `az containerapp exec` dentro do container já promovido) evita a ambiguidade por usar as credenciais reais de runtime |
| Mais um scheduler in-process a operar (soma três: GC de jobs, digest de catálogo, digest de visibilidade, agora digest de deploy) | Mesmo padrão já aceito nas ADRs anteriores; custo marginal por seguir exatamente o mesmo esqueleto |
| D4 (destinatários) pode deixar de fora alguém que precisava saber | Decisão explicitamente marcada para validar com o usuário antes de implementar; fácil de ajustar depois (é um filtro de `list_clients()`, não uma migração de dado) |
| D7 é um lembrete textual sempre presente, não uma detecção real — pode ficar noise se nada relevante mudou no skill naquele deploy | Aceitável como F1; se se mostrar ruidoso em uso real, A5 (hash do skill) fica como candidato de refinamento futuro |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Este ADR | Problema documentado, decisões D1-D7 propostas para discussão | 💡 Proposta |
| F2 — Validação | Confirmar mecanismo de escrita do deploy log (D1); decidir destinatários (D4); decidir intervalo do scheduler (D3); nome da tool (D6) | ⬜ Não iniciado |
| F3 — Deploy log | `deploy/history.json`, comando CLI ou passo de CI para escrever a entrada na promoção | ⬜ Não iniciado |
| F4 — Digest de deploy | `DeployDigestScheduler`, `enviar_digest_deploy()`, `notify_deploy_digest()` (reaproveitando template genérico, ADR-134) | ⬜ Não iniciado |
| F5 — Skill atualizável via MCP | Cabeçalho de versão no `.skill` (D5); `application/services/skill_content.py` (promove `_read_skill_tutorial` a serviço compartilhado); tool MCP nova (D6); vínculo no digest (D7) | ⬜ Não iniciado |

## Definition of Done

### Fase 1
- [ ] Mecanismo de escrita do deploy log (D1) confirmado com o usuário
- [ ] Destinatários (D4) decididos
- [ ] Intervalo do scheduler (D3) decidido
- [ ] Nome definitivo da tool MCP (D6) decidido
- [ ] Status atualizado para Aceito/Decidido

### Fase 3-5 (após validação)
- [ ] `deploy/history.json` populado por pelo menos um deploy real
- [ ] `DeployDigestScheduler` com teste confirmando que um tick sem entrada nova nunca chama `NotificationService.send()`
- [ ] Tool MCP testada confirmando que lê o arquivo a cada chamada (não congela conteúdo no boot do servidor)
- [ ] Cabeçalho de versão presente no `.skill` e exposto no retorno da tool

---

## Relacionados

- ADR-093 — MCP como Serviço de Artefatos (precedente de "servir conteúdo via MCP", escopado a projeto — esta ADR generaliza para conteúdo de sistema)
- ADR-101 — MCP Apps (precedente rejeitado para D6 — recursos `ui://` são para HTML interativo, e o padrão de leitura-no-boot motivou o cuidado explícito em D6)
- ADR-123/131/134 — Notificação por Email (infraestrutura de envio reaproveitada; nenhum template novo necessário)
- ADR-140 — Critério Atômico vs. Digest (D2 desta ADR aplica D1 daquela explicitamente, conforme exigido por D5 do ADR-140)
- ADR-141 — Digest de Rascunhos de Catálogo (precedente direto de scheduler reaproveitado em D3)
- ADR-143 — Visibilidade de Usuários + Digest (precedente mais recente do mesmo padrão de scheduler + time-gating por conteúdo)
