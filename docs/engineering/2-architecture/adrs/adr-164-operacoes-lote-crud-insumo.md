# ADR-164 — Operações em Lote (Batch) para CRUD de Insumo

**Status:** ✅ Implementado
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-116 (Limpeza da Superfície de Tools MCP — teto), ADR-145 (Unificação do Caminho de Escrita de Preço no Catálogo Mestre), ADR-163 (CRUD de Insumo no Catálogo Mestre via MCP)

---

## Contexto

### Problema

P1. `criar_insumo`, `atualizar_preco_insumo` e `descontinuar_insumo` (ADR-163) só operam um insumo por chamada. Um agente/usuário precisando criar ou atualizar N insumos (ex.: aplicar uma cotação de mercado com dezenas de itens) precisa fazer N chamadas MCP sequenciais — sobrecarga de rede proporcional a N, e sem nenhum teto que evite N arbitrariamente grande numa única sessão.

P2. Cada chamada individual de `atualizar_preco_insumo`/`criar_insumo`/`descontinuar_insumo` já faz uma leitura+escrita completa do arquivo do rascunho (`_append_delta_to_rascunho`, `_catalogo_tools_helpers_a.py:294-325`) — N chamadas para N itens significam N×(leitura+escrita) do mesmo arquivo JSON, não só overhead de rede.

P3. O único precedente de "atualização em lote" para catálogo hoje é um antipadrão client-side: `_pcat_apply_batch` (`presentation/ui/templates/_project_page_helpers_b/_pcat_render.py:133-164`) faz um loop no Streamlit disparando uma request HTTP por CPU selecionada — exatamente o efeito que se quer evitar (N requests individuais em vez de uma chamada com N itens).

P4. Não existe, em nenhuma tool MCP ou rota REST deste repositório, precedente de limite superior de tamanho de lista de entrada (nenhum `Field(max_length=...)`, nenhuma validação manual de tamanho). As 3 tools que já aceitam `list[dict]` hoje (`criar_projeto(servicos=...)`, `iniciar_orcamento(eap=...)`, `explorar_configuracoes_go(parametros_sweep=...)`) não têm teto algum.

## Decisão

D1. Três tools novas — `criar_insumos_lote`, `atualizar_precos_insumos_lote`, `descontinuar_insumos_lote` — espelhando as 3 operações de escrita do ADR-163, cada uma recebendo `itens: list[dict[str, Any]]` em vez de campos individuais. Mesmo caminho gated por rascunho (`rascunho_id` obrigatório, escrita efetiva só no merge) — nenhum mecanismo de escrita paralelo.

D2. Teto de `MAX_LOTE_INSUMOS = 100` itens por chamada (`_catalogo_tools_helpers_a.py`), validado antes de qualquer processamento — acima do teto, a chamada inteira é rejeitada sem tocar no rascunho. Escolhido por ser: (a) uma ordem de grandeza acima do caso motivador original do ADR-163 (54 anomalias de plausibilidade), com margem; (b) pequeno o bastante para manter o payload de uma chamada MCP em tamanho razoável.

D3. `_append_delta_to_rascunho` generalizada para `_append_deltas_to_rascunho(deltas_novos: list[dict])` — mesma leitura+escrita única do arquivo do rascunho, agora fazendo `.extend(deltas_novos)` em vez de `.append(delta)`. `_append_delta_to_rascunho` (singular) passa a ser um wrapper de uma linha (`_append_deltas_to_rascunho(..., [delta])`), preservando os 4 call sites individuais existentes sem nenhuma mudança de comportamento. Fecha P2: N itens válidos = 1 leitura + 1 escrita do rascunho, não N.

D4. Validação por item, não all-or-nothing: cada item do lote é validado independentemente (schema, existência/inexistência do insumo, código duplicado dentro do próprio lote) e um item inválido não aborta os demais — a resposta reporta `{"total", "sucesso", "falhas", "resultados": [{"...": ..., "status": "ok"|"erro", "erro"?: str}]}` por item, mesmo padrão de UX do comando CLI `concilium auth batch` (processa linha a linha, resume sucesso/erro ao final). A persistência dos itens **validados**, porém, é atômica: ou todos os deltas válidos são gravados juntos (D3), ou nenhum é (se o rascunho não existir ou estiver em estado terminal).

D5. `criar_insumos_lote` valida adicionalmente `codigo` duplicado **dentro do próprio lote** (não só contra o catálogo mestre) — sem isso, dois itens com o mesmo `codigo` no mesmo lote passariam ambos na validação individual (`validate_insumo_nao_existe` só olha o catálogo mestre), e no merge o segundo delta de criação sobrescreveria silenciosamente o arquivo do primeiro.

D6. Nenhuma mudança em `aprovar_merge_catalogo`: o loop de merge (`catalogo.py`, `for delta in deltas: if tipo == ...`) já processa qualquer quantidade de deltas de cada tipo, sejam eles originados de tools individuais ou de tools de lote — a distinção lote/individual existe só no lado da escrita do rascunho (D3/D4), nunca no lado do merge.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Estender as 3 tools individuais com um parâmetro opcional `itens: list[dict] \| None`, em vez de 3 tools novas | Misturaria dois modos de uso (campos individuais vs. lista) na mesma assinatura, tornando a tool mais confusa; o precedente já existente no repo (`criar_projeto`, `iniciar_orcamento`) é o de uma tool cuja interface primária já É uma lista, não um modo alternativo — mais simples de documentar e usar. |
| A2 | All-or-nothing: um item inválido aborta o lote inteiro | Rejeitada — para um lote de 100 itens, um único erro de digitação descartaria 99 itens válidos, forçando o usuário a descobrir o item ruim e reenviar tudo. Validação por item com resumo de sucesso/erro (D4) é o padrão já usado pelo CLI `auth batch` neste repo. |
| A3 | Sem teto superior (deixar a rede/timeout do transporte MCP ser o limite natural) | Rejeitada — motivo explícito do pedido do usuário ("limitar superiormente para não sobrecarregar a rede"); sem teto explícito, nada impede um payload de milhares de itens numa única chamada. |
| A4 | Teto de 20 ou 50 itens em vez de 100 | Rejeitado por decisão do usuário — 100 dá margem confortável acima do caso motivador (54 anomalias) sem ser tão baixo a ponto de exigir múltiplas chamadas em cenários comuns de cotação de mercado. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Rede | N itens = 1 chamada MCP, não N — resolve a sobrecarga de rede que motivou o pedido. |
| I/O do rascunho | N itens válidos = 1 leitura + 1 escrita do arquivo de rascunho, não N×(leitura+escrita) — ganho que existia mesmo sem o pedido explícito de rede, descoberto na investigação (P2). |
| Sem mudança no merge | `aprovar_merge_catalogo` não precisou de nenhuma alteração — o loop de deltas já era genérico o bastante para lote (D6). |
| Retrocompatibilidade total | As 3 tools individuais do ADR-163 continuam exatamente como estavam; `_append_delta_to_rascunho` preserva a mesma assinatura e comportamento (agora delegando para a versão em lote). |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Payload de resposta grande para lotes de 100 itens (100 entradas em `resultados`) | Aceito — é informação que o chamador precisa para saber o que teve sucesso/falhou; 100 entradas curtas não é um payload problemático. |
| `criar_insumos_lote` não detecta duplicata de `descricao` (só de `codigo`) entre itens do lote | Mesmo comportamento já aceito no `criar_insumo` individual (ADR-163 A6) — sem dedup semântico, só por código; fora de escopo desta ADR. |
| Teto de 100 é um número fixo no código (`MAX_LOTE_INSUMOS`), não configurável por env | Aceito — nenhuma outra constante de teto deste tipo no repo é configurável via env; se necessário no futuro, é uma mudança pontual. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `_append_deltas_to_rascunho` (generalização de `_append_delta_to_rascunho`) | ✅ Implementado |
| F2 | `criar_insumos_lote` | ✅ Implementado |
| F3 | `atualizar_precos_insumos_lote` | ✅ Implementado |
| F4 | `descontinuar_insumos_lote` | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] `_append_deltas_to_rascunho(deltas_novos: list[dict])` grava N deltas numa única leitura+escrita
- [x] `_append_delta_to_rascunho` (singular) delega para a versão em lote sem mudar comportamento — testes de regressão existentes (rascunho inexistente, estado terminal, falha de leitura/escrita) continuam passando sem alteração

### Fase 2
- [x] `criar_insumos_lote` rejeita lista vazia e lista acima de `MAX_LOTE_INSUMOS` sem tocar no rascunho
- [x] Item com `codigo` já existente no catálogo, `codigo` duplicado dentro do lote, ou schema inválido falha só aquele item — demais itens válidos são persistidos
- [x] Resposta reporta `total`/`sucesso`/`falhas`/`resultados` por item

### Fase 3
- [x] `atualizar_precos_insumos_lote` mesma disciplina de teto/validação por item de F2
- [x] Item sem `novo_preco` nem `novo_valor_locacao_mensal`, ou `insumo_id` inexistente, falha só aquele item

### Fase 4
- [x] `descontinuar_insumos_lote` mesma disciplina de teto/validação por item
- [x] Insumo inexistente falha só aquele item; itens válidos são marcados para soft-delete no merge

---

## Relacionados

- ADR-116 — Limpeza da Superfície de Tools MCP (teto de tools — esta ADR soma 3 tools novas)
- ADR-145 — Unificação do Caminho de Escrita de Preço no Catálogo Mestre (mecanismo de rascunho/delta reaproveitado, generalizado para N deltas por chamada)
- ADR-163 — CRUD de Insumo no Catálogo Mestre via MCP (as 3 tools individuais que esta ADR espelha em versão lote; nenhuma mudança nelas)
