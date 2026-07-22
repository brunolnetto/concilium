# ADR-145 — Unificação do Caminho de Escrita de Preço no Catálogo Mestre

**Status:** Proposta
**Data:** 2026-07-22
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-017 (Catalog Lifecycle Management), ADR-024 (Snapshot Auditável), ADR-025 (MCP Catalog Policy), ADR-040 (Master vs. Project Layer), ADR-041 (SCD Type 2), ADR-062 (Versionamento de Contextos — `ConfigVersionService`), ADR-066 (Catalog Overlay Model), ADR-067 (Master Catalog Write API), ADR-120 (Catalog RBAC Lifecycle), ADR-130 (Grafo de Sinergia — achado correlato, ver seção dedicada)

---

## Contexto

### Problema

P1. O caminho de escrita **efetivamente usado hoje** para alterar o preço de um insumo no catálogo mestre — a ferramenta MCP `atualizar_preco_insumo`, que o próprio `criar_rascunho_catalogo` instrui o usuário a chamar ("Use atualizar_preco_insumo/adicionar_variante_producao para editar") — grava a mudança **direto e imediatamente** no arquivo JSON do catálogo mestre, via `_save_preco_insumo_master` (`presentation/mcp/tools/_catalogo_tools_helpers_a.py:191-213`). Essa função é chamada independentemente do estado do rascunho (RASCUNHO, REVISADO ou nada) e **antes** de `aprovar_merge_catalogo` ser sequer invocado.

P2. Consequência direta de P1: o gate de quatro olhos do ADR-120 (`assert_pode_aprovar`, que bloqueia aprovar fora de sequência revisar→aprovar, e proíbe `aprovador == criado_por`) **não protege o dado real**. Ele só controla o ponteiro `current` de uma entidade auxiliar de versionamento genérico (`ConfigVersionService`/ADR-062, `config/contextos/{contexto_id}/`) — não o arquivo de insumo em si. Um preço editado durante a fase de rascunho já está em produção, visível a qualquer resolução de catálogo, mesmo que o rascunho seja depois rejeitado.

P3. `_save_preco_insumo_master` sobrescreve `data["preco_unitario"]` in-place e nunca chama `RepositorioInsumo.atualizar_preco()` (`infrastructure/repositories/insumo.py:176`), que é a implementação correta do modelo SCD Type 2 do ADR-041 (fecha `data_fim_vigencia` do registro anterior em `historico_precos` e abre um novo). Isso significa que **`preco_na_data()` — construído explicitamente para responder "qual era o preço vigente quando o contrato foi assinado" — não tem registro histórico de nenhum preço alterado pela API de escrita real**, apenas dos poucos casos ainda migrados manualmente ou pela CLI `catalog promote`.

P4. Não é gerado nenhum `CatalogSnapshot`/`CatalogDiff` (ADR-024) no momento da escrita. A única forma de saber "o que mudou, quando e por quanto" é reconstruir manualmente o histórico de commits do arquivo — quando a alteração é feita via API MCP em produção (fora de um commit git), não sobra rastro algum.

P5. O parâmetro `justificativa` de `aprovar_merge_catalogo` — descrito na própria docstring da ferramenta como "Motivo da aprovação para o audit trail" — **nunca é persistido**; é apenas ecoado na resposta da chamada MCP (`presentation/mcp/tools/catalogo.py:432-493`). Se o cliente MCP não registrar essa resposta de forma durável, a justificativa de uma aprovação de catálogo se perde permanentemente. Da mesma forma, `nota`/`nota_calibracao` em `_save_preco_insumo_master` é um campo único sobrescrito a cada chamada (não é array append-only) — a justificativa da alteração anterior é perdida na próxima.

P6. Existe uma **terceira implementação**, `CatalogUpdater` (`infrastructure/catalog/updater.py`), que trata `Insumo` com mutação in-place + array de auditoria `auditoria_custo`, e `Producao` como append-only imutável. Nenhum destes dois comportamentos é usado por P1-P5: uma busca em todo `src/` mostra que `CatalogUpdater` não é importado por nenhum orquestrador ou ferramenta MCP viva — é referenciado apenas em um comentário de docstring (`domain/models/project/observacao.py:11`) descrevendo um fluxo pretendido que nunca foi conectado. Ter três implementações divergentes do "como uma mudança de catálogo é persistida" (`CatalogUpdater`, `RepositorioInsumo.atualizar_preco`, `_save_preco_insumo_master`) torna o sistema difícil de raciocinar e já produziu a lacuna de P1-P5 sem que nenhum ADR a tivesse decidido conscientemente.

P11. A aprovação hoje é **monolítica por rascunho** (`aprovar_merge_catalogo`/`rejeitar_rascunho_catalogo` recebem só `contexto_id`+`rascunho_id`, sem seleção por modificação individual) — mas mesmo essa granularidade grosseira está desconectada do dado real, agravando P1/P2. O passo de revisão que deveria mostrar quais insumos mudaram está quebrado: `consultar_impacto_reajuste` lê `diff.get("modificados", {})` (`presentation/mcp/tools/catalogo.py:406-407`), porém `ContextoVersionService.compare()` (`application/services/catalog/contexto_version_service.py:245-262`) nunca produz uma chave `"modificados"` — retorna `"changed"`/`"unchanged"`. Logo `n_insumos_afetados` sempre retorna 0 e `insumos_modificados` sempre retorna lista vazia, independentemente de quantos preços tenham sido alterados. Não é só falta de granularidade por design — o próprio relatório de impacto que subsidiaria uma revisão (ainda que monolítica) é código morto que nunca reporta nada.

### Por que isso quebra "composição referencial temporal fidedigna"

O ADR-066 garante reprodutibilidade de um orçamento/EAP já executado via `resolved_catalog.json` congelado por versão de projeto — mas essa garantia pressupõe que o **catálogo mestre em si** tenha uma trilha auditável e um modelo temporal correto para consultas retroativas (ex.: revisão contratual DNIT/ANTT perguntando "qual era o preço vigente em 2026-03-15"). P1-P6 mostram que, para preços de insumo, essa trilha não existe no caminho de escrita real — o modelo SCD2 (ADR-041) e o snapshot auditável (ADR-024) foram construídos e existem como capacidade de biblioteca, mas o único write path realmente exposto via MCP não os utiliza.

## Decisão

D1. `atualizar_preco_insumo` (e `adicionar_variante_producao`) passam a **escrever apenas dentro do escopo do rascunho** (`config/contextos/{contexto_id}/versions/{rascunho_id}.json`, como um delta `{insumo_id, preco_anterior, preco_novo, jurisdicao_id, nota, autor, timestamp}`), nunca no arquivo do catálogo mestre diretamente. O catálogo mestre só é tocado no momento do commit (D2).

D2. `aprovar_merge_catalogo` passa a ser o único ponto de escrita efetiva no catálogo mestre. Ao promover um rascunho, ele itera os deltas acumulados e, para cada um, chama `RepositorioInsumo.atualizar_preco()` (fechando `data_fim_vigencia` do registro SCD2 anterior e abrindo um novo com `data_inicio_vigencia = data da aprovação`), em vez de sobrescrever `preco_unitario` in-place.

D3. `aprovar_merge_catalogo` gera um `CatalogSnapshot`/`CatalogDiff` (ADR-024) do estado antes/depois do merge, persistido em `config/catalogos/{catalogo_id}/snapshots/` (ou equivalente), vinculado a `contexto_id`, `rascunho_id`, `aprovador`, `justificativa` e `data`. A `justificativa` passa a ser gravada nesse registro, não apenas devolvida na resposta MCP.

D4. As notas de alteração (`nota`/`nota_calibracao`) deixam de ser um campo único sobrescrito e passam a ser um array append-only por insumo (reaproveitando a estrutura de `historico_precos`, que já tem o campo `fonte`).

D5. `CatalogUpdater` (`infrastructure/catalog/updater.py`) é removido do código, já que nenhuma parte viva do sistema o invoca e sua manutenção em paralelo a D1-D4 seria uma quarta implementação divergente. Caso a intenção original de "Producao é append-only imutável" (`PROD-001 → PROD-002`) ainda seja desejada, ela deve ser re-especificada como parte deste mesmo caminho unificado (D2), não preservada como código morto separado.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter `_save_preco_insumo_master` como está e apenas persistir a `justificativa` (fix mínimo) | Resolve P5 mas mantém P1-P4: o preço continua sendo alterado em produção antes da aprovação, e sem histórico SCD2/snapshot. Não fecha a lacuna de fidelidade temporal, só a de auditoria de justificativa. |
| A2 | Reviver `CatalogUpdater` como o caminho oficial, plugando-o em `atualizar_preco_insumo` | `CatalogUpdater` também faz mutação in-place para `Insumo` (só adiciona um array de auditoria) — não resolve P3 (SCD2) nem P4 (snapshot). Teria que ser reescrito de qualquer forma; melhor unificar direto no que já é correto (`RepositorioInsumo.atualizar_preco`). |
| A3 | Gerar `CatalogSnapshot` a cada chamada individual de `atualizar_preco_insumo`, sem esperar o merge do rascunho | Geraria um snapshot por edição isolada durante a fase de rascunho (que pode ser descartada), poluindo o histórico auditável com estados intermediários nunca aprovados. Snapshot deve corresponder a um estado efetivamente promovido. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Quatro olhos real | O gate de aprovação (ADR-120) passa a proteger o dado de fato, não só um ponteiro de metadados — um rascunho rejeitado nunca chega a alterar o preço em produção. |
| Consulta retroativa correta | `preco_na_data()` volta a refletir toda alteração feita via API MCP, habilitando defesa em revisões contratuais (DNIT/ANTT) sobre preço vigente em data específica. |
| Auditoria persistente | `justificativa` de cada aprovação e histórico de notas por insumo deixam de depender da resposta efêmera da chamada MCP. |
| Um único caminho de escrita | Elimina a ambiguidade entre três implementações (`CatalogUpdater`, `RepositorioInsumo.atualizar_preco`, `_save_preco_insumo_master`) — daqui em diante há uma fonte de verdade para "como uma alteração de catálogo é persistida". |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Latência adicional: `atualizar_preco_insumo` não grava mais direto no master, exigindo um passo de merge explícito para o preço "valer" | Já é o comportamento esperado do fluxo de rascunho (ADR-120); o problema é que hoje ele não é respeitado, não que o passo extra seja indesejável. |
| Rascunhos abertos há muito tempo acumulam deltas não aplicados, criando divergência entre "o que o usuário acha que já está valendo" e o catálogo real | `listar_divergencias_rascunho` (já existente) deve deixar claro que nenhuma mudança individual está em produção até o merge — mensagem de retorno de `atualizar_preco_insumo` precisa comunicar isso explicitamente. |
| Migração dos rascunhos em andamento no momento do deploy desta mudança (se houver) | Levantar rascunhos com status RASCUNHO/REVISADO antes do deploy; script de migração único, não recorrente. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `atualizar_preco_insumo`/`adicionar_variante_producao` passam a gravar delta no rascunho (D1); `consultar_impacto_reajuste`/`listar_divergencias_rascunho` corrigidos para ler os deltas reais (hoje leem chave `modificados` inexistente — P11) | Não iniciado |
| F2 | `aprovar_merge_catalogo` aplica deltas via `RepositorioInsumo.atualizar_preco()` (D2) | Não iniciado |
| F3 | Geração de `CatalogSnapshot`/`CatalogDiff` + persistência de `justificativa` no merge (D3) | Não iniciado |
| F4 | Notas de alteração viram array append-only (D4) | Não iniciado |
| F5 | Remoção de `CatalogUpdater` e do comentário obsoleto em `observacao.py` (D5) | Não iniciado |

## Definition of Done

### Fase 1
- [ ] `atualizar_preco_insumo` não escreve mais em `config/catalogos/{id}/insumos/**`, apenas no rascunho ativo
- [ ] Teste cobrindo: rascunho rejeitado após `atualizar_preco_insumo` → preço no catálogo mestre permanece inalterado
- [ ] `consultar_impacto_reajuste` lê a chave correta do retorno de `ContextoVersionService.compare()` (`"changed"`, não `"modificados"`) e passa a reportar `n_insumos_afetados` corretamente
- [ ] Teste cobrindo: rascunho com N deltas de preço → `consultar_impacto_reajuste` retorna `n_insumos_afetados == N`

### Fase 2
- [ ] `aprovar_merge_catalogo` chama `RepositorioInsumo.atualizar_preco()` para cada delta do rascunho aprovado
- [ ] Teste cobrindo: `preco_na_data()` retorna o preço anterior para datas antes da aprovação e o novo preço para datas a partir da aprovação

### Fase 3
- [ ] `CatalogSnapshot` gerado e persistido a cada merge aprovado, com `justificativa` incluída
- [ ] Teste cobrindo: resposta de `aprovar_merge_catalogo` e o registro persistido contêm a mesma `justificativa`

### Fase 4
- [ ] Notas de alteração por insumo acumulam em array, não sobrescrevem

### Fase 5
- [ ] `infrastructure/catalog/updater.py` removido; nenhuma referência residual em código ou docstrings

---

## Achado Correlato: Grafo de Sinergia (ADR-130) sob Overlay de Projeto

Este achado **não faz parte da Decisão** desta ADR (D1-D5, que trata exclusivamente do write path de preço de insumo no catálogo mestre). É documentado aqui por ter surgido na mesma investigação sobre fidelidade referencial temporal do catálogo, e por ser outra manifestação do mesmo padrão de fundo: camadas de resolução do catálogo (master → overlay de projeto → resolved snapshot) sem validação cruzada entre si.

P7. O grafo de sinergia (ADR-130, `domain/models/catalog/producao.py:97-135` — `GrafoSinergiaEquipe`/`RelacaoSinergia`/`CapacidadeElemento`) vive como campo sibling de `composicao_padrao_equipe` dentro do próprio JSON de `Producao`/CPU no catálogo. Seus nós (`elemento_id`) referenciam `funcao_id`/`equip_id`/`insumo_id` daquela composição. O motor de derivação (`domain/services/sinergia_equipe.py`) sempre recebe o **catálogo já resolvido** (master + overlay de projeto aplicado via `CatalogResolver.apply_overlays`), nunca o master cru — não há isolamento entre a camada de override (ADR-040, opt-in por projeto) e o grafo.

P8. Como `_deep_merge` (`catalog_resolver.py:290-298`) substitui listas por inteiro (não mescla item a item), um overlay de projeto que altera `composicao_padrao_equipe.equipamentos`/`funcoes` pode deixar `grafo_sinergia.capacidades`/`relacoes` daquela CPU referenciando um `elemento_id` que não existe mais na composição vigente do projeto — um nó órfão.

P9. Existe uma rede de segurança genérica: `validar_referencias_grafo`/VAL-SINERGIA-01 detecta a referência órfã, e `resolver_producao_efetiva` marca `grafo_invalido=True` e cai para o valor `declarado`/`calibrado` em vez de propagar um cálculo incorreto (`sinergia_equipe.py:205-251`). Não é uma falha silenciosa de cálculo. Mas esse fallback usa um valor calibrado para a composição **anterior** ao overlay, sem re-derivação para o novo contexto do projeto — e a função desenhada especificamente para esse cenário, `revalidar_apos_mudanca_composicao` (`sinergia_equipe.py:254-304`), só é exercitada em teste unitário (`test_adr130_sinergia_equipe.py`); não está conectada a `set_overlay`/`extend_cpu`.

P10. Nenhum ADR ou teste cruza os dois temas hoje — ADR-130 nunca menciona overlay; os testes de overlay (`test_adr066_catalog_overlay.py`, `test_catalog_resolver2.py`) nunca mencionam grafo/sinergia/composição. É uma lacuna de design não analisada, não uma decisão consciente.

**Superfície de risco atual:** o risco só se materializa na interseção de dois opcionais independentes — overlay de projeto (por projeto) **e** CPU com grafo definido (por CPU). Hoje só o catálogo `rfi-r02` tem grafos populados; `mendeslobo` (catálogo primário) não tem nenhuma CPU com grafo, o que limita a exposição prática no curto prazo, mas não a elimina como dívida de arquitetura.

**Encaminhamento:** este achado requer sua própria decisão (conectar `revalidar_apos_mudanca_composicao` ao caminho de overlay, ou validar overlays contra `grafo_sinergia` no momento do `set_overlay`) — não está coberto pelo Plano de Implementação/Definition of Done acima. Recomenda-se abrir um item de backlog ou uma ADR dedicada quando o catálogo `mendeslobo` começar a ganhar CPUs com grafo, ou antes disso, se algum projeto já combinar overlay com CPUs de `rfi-r02`.

---

## Relacionados

- ADR-017 — Catalog Lifecycle Management (Definition of Done ainda lista "audit trail: every catalog change traceable to obra + aprovador" como item aberto; esta ADR fecha essa lacuna especificamente para preço de insumo)
- ADR-024 — Referências em Planilha Editável com Snapshot Auditável (mecanismo de `CatalogSnapshot`/`CatalogDiff` reaproveitado em D3)
- ADR-041 — SCD Type 2 para Rastreabilidade Histórica do Catálogo Master (mecanismo de `atualizar_preco()` reaproveitado em D2)
- ADR-062 — Versionamento Explícito de Contextos e Perfis (`ConfigVersionService.compare()` é onde vive o bug de P11 — chave `"modificados"` inexistente)
- ADR-066 — Catalog Overlay Model (garante fidelidade temporal por-run via `resolved_catalog.json`; esta ADR garante fidelidade temporal do catálogo mestre em si, pré-requisito para que o overlay tenha algo confiável para congelar)
- ADR-120 — Catalog RBAC Lifecycle (o gate de quatro olhos que esta ADR passa a proteger de fato)
- ADR-130 — Composição de Equipe: Grafo de Sinergia / Produtividade Derivada (achado correlato — overlay de projeto pode orfanizar nós do grafo; ver seção dedicada acima)
