# ADR-150 — Rascunho de Catálogo com Escopo de Projeto: Promoção Gated ao Catálogo Master

**Status:** ⚠️ Parcialmente Implementado _(2026-07-24 — F1-F5 do escopo de INSUMO completas; CPU/BDI e levantamento de uso real do CLI antigo pendentes, ver Estado de Implementação)_
**Data:** 2026-07-24
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-040 (camadas master/project — esta ADR completa a Fase 3/4 pendente), ADR-120 (RBAC e state machine de 4-olhos, reaproveitada), ADR-126 (project ownership, `require_owner_or_admin`), ADR-141 (digest de rascunhos pendentes — estendido para cobrir origem de projeto), ADR-145 (rascunho como único caminho de escrita efetiva no master — este ADR fecha um desvio residual)

---

## Estado de Implementação (2026-07-24)

| Fase | Item | Status |
|---|---|---|
| F1 | Identidade de rascunho de projeto (`abrir_ou_obter_rascunho_projeto`, `_rascunho_estado.json`) | ✅ `catalog_draft_lifecycle.py` |
| F2 | Gate dual ownership+quatro-olhos (`assert_pode_promover_projeto`) | ✅ `catalog_draft_lifecycle.py` |
| F3 | Escrita efetiva unificada + tool MCP `promover_override_projeto` | ✅ `_catalogo_tools_helpers_c.py`, `catalogo.py` |
| F4 | `catalog promote` (CLI) redirecionado ao core gated | ✅ `_commands_manage_helpers_b.py` — **mas sem levantamento real de uso** (ver Achados) |
| F5 | Digest estendido para `projeto_id` + dono do projeto | ✅ `draft_digest_service.py` |
| — | Promoção de overrides de **CPU** (`cpus_override.json`) e **BDI** (`bdi_override.json`) | ⬜ Não implementado — apenas insumo de preço está coberto (ver Achados) |

### Achados adicionais durante a implementação (não previstos no desenho original)

- **Bug de bypass adicional descoberto no próprio `catalog promote` antigo**: além de escrever sem gate (P2), a função `_cp_validate_override` buscava overrides pela chave plana (`insumo_id`), enquanto `atualizar_preco_insumo(projeto_id=...)` sempre grava com chave composta (`f"{insumo_id}::{jurisdicao_id or 'BASE'}"`) — ou seja, o comando antigo **nunca encontrava** os overrides gravados pelo tool MCP real. Corrigido junto com D4 (o novo core usa o mesmo parser de chave composta do tool MCP).
- **Bug pré-requisito, fora do desenho original**: `atualizar_preco_insumo(projeto_id=...)` gravava em `overrides/catalog_prices.json` — um arquivo que **nenhum outro ponto do sistema lia** (nem `resolver_preco`, nem o pipeline real via `lifecycle_coordinator._inject_project_catalog_layers`, nem o antigo `catalog promote`). O override "livre" nunca chegava a lugar nenhum. Corrigido para gravar em `insumos_override.json` (o arquivo real).
- **Escopo reduzido a insumos de preço**: a promoção gated (`promover_override_projeto`/CLI) cobre apenas `insumos_override.json`. `cpus_override.json` (produtividade/composição calibrada) e `bdi_override.json` (alíquotas) continuam sem nenhum caminho de promoção ao master — nem o antigo (removido), nem o novo. Considerar ADR de continuação se/quando a promoção desses dois vier a ser necessária.
- **Granularidade do CLI mudou**: `catalog promote` deixou de aceitar `--insumo`/`--data-vigencia` (promoção de 1 insumo por chamada) — agora promove todos os overrides de insumo pendentes do projeto de uma vez, mesma semântica do tool MCP. Não foi feito levantamento de uso real em produção antes dessa mudança (DoD F4, item 1, propositalmente deixado em aberto).

---

## Contexto

### Problema

P1. Overrides de projeto (ADR-040) já são editados livremente por qualquer profissional do projeto via `atualizar_preco_insumo(projeto_id=...)`, sem aprovação — isso é correto e deliberado (liberdade operacional, ADR-040 C2). O que falta é a outra ponta: a promoção desses overrides ao catálogo master nunca ganhou o mesmo rigor de governança que o rascunho global já tem.

P2. **A promoção existente hoje contorna toda a governança do catálogo mestre.** O comando `concilium manage catalog promote` (`_impl_catalog_promote`, `presentation/cli/_commands_manage_helpers_b.py:184`) grava diretamente no arquivo do insumo master via `_write_json` — sem `rascunho_id`, sem `CatalogSnapshot`/`CatalogDiff` (ADR-024), sem checagem de 4-olhos, sem exigir role `catalog:merge`. O único controle é a flag `--force` (confirmação de intenção, não autorização) e um `--actor` de texto livre não autenticado. Isso contradiz diretamente a premissa da ADR-145 de que `aprovar_merge_catalogo` é "o único ponto de escrita efetiva no catálogo mestre" — na prática existem dois caminhos, e um deles não tem gate nenhum.

P3. `owner_id` de projeto (ADR-126, `require_owner_or_admin`) não tem nenhuma conexão com o RBAC de catálogo (ADR-120, role `catalog:merge`). Hoje não há como expressar "o dono deste projeto está autorizando a promoção de uma calibração ao master" como uma checagem distinta de "sou catalog-manager e aprovo qualquer rascunho, de qualquer projeto".

P4. Overrides de projeto não têm identidade de rascunho — são um dict solto por código de insumo em `overrides/insumos_override.json`, sem os estados RASCUNHO/REVISADO/APROVADO/REJEITADO que o rascunho global já tem via `RascunhoCatalogoStateMachine` (ADR-120 D5). Não há hoje como listar "overrides deste projeto pendentes de decisão" da mesma forma que `rascunhos_pendentes()` (ADR-141) lista rascunhos globais.

P5. A Fase 3/4 do ADR-040 (survey/promote) segue com Definition of Done parcialmente desmarcado desde 2026-05-15 — a lacuna documentada nunca foi formalmente fechada, apesar do comando CLI existir e estar em uso.

### Escopo

Fecha a Fase 3/4 pendente do ADR-040 com um mecanismo de promoção formalmente gated, reaproveitando a state machine de 4-olhos do ADR-120/141 e o gate de ownership do ADR-126. Não altera o fluxo de edição livre do override de projeto em si (D2 do ADR-040 permanece intacto); altera apenas o caminho de promoção ao master.

---

## Decisão

D1. **Override de projeto ganha identidade de rascunho promovível.** Cada override de insumo/CPU/BDI de projeto passa a ser rastreado como um rascunho com `projeto_id` associado, reaproveitando `RascunhoCatalogoStateMachine` (ADR-120 D5) com um campo opcional `projeto_id` — os mesmos 4 estados (RASCUNHO → REVISADO → APROVADO|REJEITADO), sem duplicar a máquina de estados.

D2. **Gate de promoção: ownership E catalog:merge, ambos exigidos.** A promoção de um override de projeto ao catálogo master só é permitida quando, simultaneamente:
   - (a) o ator que inicia a promoção satisfaz `require_owner_or_admin` (ADR-126) — é o `owner_id` do projeto de origem ou admin; e
   - (b) a aprovação final vem de um ator com role `catalog:merge` (catalog-manager/admin) diferente de quem editou o override (4-olhos, reaproveitando `_checar_quatro_olhos`, ADR-120).

   As duas checagens são independentes e cumulativas — nenhuma substitui a outra. Isso preserva integralmente a proteção 4-olhos do rascunho global (ADR-120/141/145); a checagem de ownership é uma camada adicional, não uma alternativa mais fraca.

D3. **Escrita efetiva reaproveita o caminho único de `aprovar_merge_catalogo`.** A promoção passa a chamar o mesmo mecanismo de aplicação de delta que o rascunho global usa hoje (`RepositorioInsumo.atualizar_preco()`, SCD2/ADR-041, geração de `CatalogSnapshot`/`CatalogDiff` com justificativa persistida no registro, ADR-145). Grava direto na estrutura viva que o pipeline de fato lê hoje (a mesma usada por `aprovar_merge_catalogo`) — não empilha sobre `config/contextos/.../versions/`, que tem o bug conhecido do ADR-062 (pipeline real ignora o diretório de versões).

D4. **`catalog promote` (CLI) é substituído, não mantido como caminho paralelo.** `_impl_catalog_promote` (escrita direta via `_write_json`, sem gate algum, P2) é redirecionado para o novo fluxo gated ou removido — não pode continuar existindo como segundo caminho de escrita sem 4-olhos/ownership no catálogo mestre.

D5. **Rascunhos de projeto pendentes entram no digest existente.** Estende `rascunhos_pendentes()` (ADR-141) para incluir rascunhos com `projeto_id`, endereçados tanto ao catalog-manager quanto ao(s) dono(s) do projeto de origem — sem novo mecanismo de notificação (reaproveita ADR-141 D2-D5 integralmente).

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| X1 | Manter `catalog promote` CLI como está, só documentar como "uso administrativo de confiança" | Não fecha P2 — continua sendo um caminho de escrita sem 4-olhos/ownership; documentar um bypass não é o mesmo que fechá-lo |
| X2 | Ownership OU catalog:merge (qualquer um dos dois basta, não os dois) | Enfraquece a proteção 4-olhos existente — reintroduziria o P1 do ADR-040 (calibração oportunística de um único ator virando benchmark corporativo sem segundo olhar) |
| X3 | Novo lifecycle dedicado para rascunho de projeto (state machine própria, paralela à `RascunhoCatalogoStateMachine`) | Duplicaria a máquina de estados já testada do ADR-120 D5 para o mesmo conjunto de 4 estados; um campo `projeto_id` opcional na mesma classe cobre o caso sem duplicação |
| X4 | Corrigir primeiro o bug do ADR-062 (pipeline ignora `versions/`) como pré-requisito bloqueante desta ADR | Fora do escopo — D3 já evita a armadilha ao escrever direto na estrutura que o pipeline lê hoje, sem depender do `ConfigVersionService` versionado; o bug do ADR-062 é tratado como item independente, citado aqui só como risco a não repetir |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha P2 (bypass de governança) | O caminho de escrita efetiva no master volta a ser único de fato — `catalog promote` deixa de ser uma segunda porta sem 4-olhos |
| Liga ownership (ADR-126) ao RBAC de catálogo (ADR-120) pela primeira vez | Dono do projeto ganha um papel formal na curadoria do que seu time criou, sem virar aprovador único |
| Reaproveita praticamente toda a infraestrutura existente | State machine (ADR-120 D5), snapshot/diff (ADR-024/145), digest (ADR-141) — nenhuma peça nova de governança, só uma nova origem (`projeto_id`) para o mesmo fluxo |
| Fecha formalmente a Fase 3/4 do ADR-040 | Definition of Done pendente desde 2026-05-15 passa a ter um caminho concreto de conclusão |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Dois aprovadores exigidos (owner + catalog:merge) pode atrasar promoções urgentes de projeto | Aceito — é o mesmo trade-off que o 4-olhos já aceita para o rascunho global; urgência não é motivo para reduzir a governança do benchmark corporativo |
| Overrides já gravados hoje (`overrides/*.json`) não têm `projeto_id`/estado de rascunho | Migração aditiva: overrides existentes sem estado explícito são lidos como RASCUNHO implícito na primeira leitura pós-deploy; nenhum dado é perdido |
| Remoção do `catalog promote` direto pode quebrar scripts/rotinas operacionais que já dependem dele | Levantamento de uso real antes de remover; se em uso, período de transição com aviso de depreciação antes da remoção definitiva |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Identidade de rascunho de projeto | `RascunhoCatalogoStateMachine` ganha `projeto_id` opcional; overrides existentes migram para RASCUNHO implícito | ✅ Implementado |
| F2 — Gate de promoção | Nova função de promoção que checa `require_owner_or_admin` (D2a) + `_checar_quatro_olhos`/role `catalog:merge` (D2b) antes de aplicar | ✅ Implementado |
| F3 — Escrita efetiva unificada | Promoção de projeto reaproveita `RepositorioInsumo.atualizar_preco()` + `CatalogSnapshot`/`CatalogDiff` (D3) | ✅ Implementado (só insumos — ver Achados) |
| F4 — Descontinuação do bypass | `_impl_catalog_promote` (CLI) redirecionado para o novo fluxo gated ou removido, conforme levantamento de uso (D4) | ⚠️ Redirecionado; levantamento de uso real não foi feito |
| F5 — Digest | `rascunhos_pendentes()` estendido para incluir `projeto_id` e notificar donos de projeto (D5) | ✅ Implementado |

---

## Definition of Done

### Fase 1
- [x] `RascunhoCatalogoStateMachine` aceita `projeto_id` opcional sem quebrar rascunhos globais existentes (sem `projeto_id`) — via `abrir_ou_obter_rascunho_projeto`, arquivo de estado próprio (`overrides/_rascunho_estado.json`), sem alterar a classe `RascunhoCatalogoStateMachine` em si (já era agnóstica ao "dono" do JSON)
- [x] Overrides já gravados em `overrides/*.json` são lidos corretamente como RASCUNHO implícito — `abrir_ou_obter_rascunho_projeto` cria o estado lazy na primeira chamada

### Fase 2
- [x] Promoção sem `owner_id` compatível é bloqueada com `PermissionError` (reaproveitando `require_owner_or_admin`)
- [x] Promoção pelo próprio autor do override é bloqueada (4-olhos, reaproveitando `_checar_quatro_olhos`)
- [x] Promoção por ator com `catalog:merge` mas que não é dono do projeto nem admin é bloqueada

### Fase 3
- [x] Promoção aplicada gera `CatalogSnapshot`/`CatalogDiff` idêntico em formato ao gerado por `aprovar_merge_catalogo` hoje — mesma função `build_and_persist_snapshot` reaproveitada
- [x] Preço promovido é lido corretamente pelo pipeline real (skill que consome `RepositorioInsumo`) — verificado via escrita real em `config/catalogos/.../insumos/*.json` (mesmo arquivo/caminho de `aprovar_merge_catalogo`), sem depender de `ConfigVersionService.versions/`

### Fase 4
- [ ] Levantamento de uso real de `concilium manage catalog promote` documentado — **não feito** (sem acesso a logs de produção nesta sessão); risco aceito e registrado em Achados
- [x] `catalog promote` redireciona para o fluxo gated — `_cp_validate_override`/`_cp_update_price_history` (escrita direta) removidos; nenhum caminho de escrita direta em `insumo_file` sobrevive fora de `_impl_promover_override_projeto`

### Fase 5
- [x] `rascunhos_pendentes()` inclui overrides de projeto pendentes, com `projeto_id` no retorno
- [x] Digest (ADR-141) notifica tanto catalog-manager quanto dono do projeto de origem, sem duplicar envio (união de sets por email)

---

## Relacionados

- ADR-040 — Hierarquia de Camadas de Catálogo (esta ADR completa a Fase 3/4 pendente)
- ADR-120 — RBAC e State Machine de 4-Olhos do Rascunho de Catálogo (reaproveitada integralmente)
- ADR-126 — Project Ownership (`require_owner_or_admin`, gate de ownership)
- ADR-141 — Digest de Rascunhos Pendentes (estendido para cobrir `projeto_id`)
- ADR-145 — Unificação do Caminho de Escrita do Catálogo Mestre (esta ADR fecha o desvio residual do `catalog promote` CLI)
- ADR-062 — Versionamento de Contextos (risco conhecido citado em D3/X4, não resolvido aqui)
- ADR-130 — Grafo de Sinergia de Equipe (achado correlato em aberto do ADR-145: overlay de projeto pode orfanizar nós do grafo — fora de escopo desta ADR, citado como consideração futura)
