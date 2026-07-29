# ADR-166 — Wiring do Custo de RH no Pipeline de Indiretos + Mapeamento Função→Item

**Status:** ✅ Implementado
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-032 (Entidades Versionadas), ADR-120 (Catalog RBAC Lifecycle — regra dos quatro olhos), ADR-136 (Custo MOB Composicional — `permanencia_efetiva_meses` por equipe), ADR-145 (Unificação do Caminho de Escrita de Preço no Catálogo Mestre), ADR-163/164 (CRUD/Batch de Insumo), ADR-165 (Catálogo de Treinamentos, Exames, EPIs e Benefícios de MO — **D9 revisitada aqui**)

---

## Contexto

### Problema

P1. A ADR-165 criou o catálogo de EPI/Treinamento/Exame/Benefício com custo unitário e amortização (`vida_util_dias`/`periodicidade_beneficio`), mas seu D9 explicitamente deferiu duas coisas: (a) wiring desse dado no pipeline de custo de indiretos — a verba QSMS lump de R$3.000/mês ("EPIs e treinamentos", `_dimensionamento.py:_composicao_default_por_categoria`) permanecia inalterada; (b) preenchimento do mapeamento função→item específico via `funcoes_aplicaveis` — o mecanismo existia, sem dado. O usuário decidiu agora fazer os dois.

P2. Investigação do pipeline revelou uma **segunda** verba lump concorrente, na categoria MOB: `_custo_alimentacao_por_equipe` (`_mob.py`) aplica um `custo_pessoa_mes` fixo (R$1.850, hardcoded — comentário no próprio código: "B3-known... idealmente derivar do catálogo") para alimentação/seguro de vida/cesta básica, por pessoa × `permanencia_efetiva_meses` da equipe (ADR-136 F4). Isso cobre exatamente o mesmo domínio dos itens `BENEFICIO` (`BEN-*`) da ADR-165 — ligar um sem desligar o outro duplicaria o custo de benefício.

P3. O catálogo `MAO_OBRA` de `mendeslobo` tem duplicação real de código por função — a mesma função aparece sob 3 a 6 aliases (`MO-<nome>`, `MO-P0xxx`, `P0xxx`, `AGIS-FN-<nome>`, `SV-P0xxx-D/N`). Mapear `funcoes_aplicaveis` para um único alias deixaria as equipes que referenciam outro alias da mesma função sem o custo do item específico.

P4. Não existe, em nenhum lugar do código/dados, um mapeamento função→NR/EPI específico — a própria ADR-165 (alternativa A4) havia rejeitado inferir esse mapeamento por correspondência de nome sem validação humana.

P5. **Achado durante a implementação** (não fazia parte do escopo original): `ContextoVersionService.create_version` (`application/services/catalog/contexto_version_service.py`) clona `existing[-1]` inteiro como base para uma versão nova, removendo só `version`/`created_at`/`created_by`/`motivo`. Como `aprovar_merge_catalogo` grava `_aprovado=True`/`_deltas=[...]` na própria versão aprovada, criar um **segundo** rascunho depois de um primeiro já aprovado o fazia nascer com esse estado herdado — `_aprovado=True` e os deltas antigos — e `atualizar_precos_insumos_lote` rejeitava qualquer edição nova ("rascunho em estado terminal"). Nunca se manifestou antes porque nenhum catálogo tinha um segundo rascunho criado após uma aprovação real até a carga da ADR-165 (F4) nesta sessão.

## Decisão

D1. `atualizar_preco_insumo`/`atualizar_precos_insumos_lote` ganham parâmetro opcional `novos_funcoes_aplicaveis: list[str] | None`, gravado direto em `atributos_especificos.funcoes_aplicaveis` no momento do merge (`_apply_preco_insumo_delta`) — mesmo caminho gated por rascunho/quatro-olhos de `novo_valor_locacao_mensal` (ADR-163 D4). Lista vazia (`[]`) é valor distinto de `None`: "aplica a nenhuma função ainda" vs. "campo não informado nesta chamada". Guard de "informe ao menos um campo" estendido para incluir esse parâmetro.

D2. Nova função `_composicao_qsms_bottom_up(equipes_diretas, catalogo)` (`_dimensionamento.py`) substitui a verba lump QSMS quando o catálogo tem itens EPI/TREINAMENTO/EXAME: para cada função com headcount em `equipes_diretas`, soma o custo mensal amortizado (`preco_unitario ÷ vida_util_dias × dias/mês`) dos itens comuns (`funcoes_aplicaveis=None`) e específicos (`funcao_id` na lista) — EXAME é sempre comum por definição da ADR-165. Retorna `None` (fallback seguro para o lump) se o catálogo não tiver nenhum item RH ou não houver headcount. `_resolve_categoria_comp` chama essa função só para `codigo == "QSMS"`, na mesma posição de prioridade do fallback antigo (overrides explícitos de `categorias_config`/`composicoes_indireto`/`regra_dimensionamento` continuam tendo precedência).

D3. Nova função `_composicao_mob_beneficio_bottom_up(equipes_diretas, catalogo)` (`_mob.py`) substitui o `custo_pessoa_mes` flat de `_custo_alimentacao_por_equipe` quando o catálogo tem `BENEFICIO` ativo — preserva a granularidade de `permanencia_efetiva_meses` por equipe (ADR-136 F4), mas calcula o custo por função em vez de um valor único para toda a equipe: benefício diário (café/almoço/jantar) convertido por dias/mês, mensal (vale-alimentação/cesta básica/seguro de vida) direto. `aplicavel_tipo_contrato` exclui a função só quando o regime é **positivamente** conhecido e não está na lista — regime `None`/desconhecido recebe o benefício (default seguro; não penaliza função sem `tipo_contrato` cadastrado no catálogo). `_custo_mob_composicional` ganha parâmetro `catalogo`, threaded desde `run_custos_indiretos` via `_process_mob_categoria`.

D4. Mapeamento função→item específico confirmado com o usuário (rascunho publicado como artefato, 3 rodadas de pergunta) e aplicado via `scripts/catalog/adr166_mapear_funcoes_aplicaveis.py`:

| Item(ns) | Funções (todos os aliases) |
|---|---|
| `TRE-NR12-MAQUINAS` + `EPI-ABAFADOR-CONCHA` | 64 códigos — operadores de máquina pesada (escavadeira, motoniveladora, rolo, trator, pá carregadeira, betoneira, motoscraper, vibroacabadora, bobcat, fresadora, perfuratriz, guindaste, valetadeira, espargidor) |
| `TRE-OP-MOTOSSERRA`, `TRE-OP-MOTOPODA`, `EPI-ROUPA-MOTOSSERRA`, `EPI-PERNEIRA` + `EPI-ABAFADOR-CONCHA` | 4 códigos — operador de motosserra (motopoda sem função própria no catálogo, ligado à mesma equipe) |
| `TRE-PLANO-TRANSITO` | 33 códigos — motoristas + sinaleiro |
| `TRE-PRODUTOS-QUIMICOS` | 12 códigos — laboratorista/aux. laboratório/espargidor/pintor |
| `TRE-NR35-ALTURA` | 15 códigos — eletricista/montador/montador água-esgoto/carpinteiro/armador |
| `EPI-PROTETOR-FACIAL` | 10 códigos — soldador/mecânico/aux. mecânico/borracheiro |
| `TRE-NR22-MINERACAO` | `[]` — exigência por área/projeto, não por cargo; fica catalogado mas fora do custo bottom-up por função por ora |

D5. Fix do achado P5: `criar_rascunho_catalogo` agora reseta explicitamente todas as chaves de ciclo de vida (`_deltas`, `_revisado`, `_revisado_por`, `_aprovado`, `_aprovado_por`, `_rejeitado`, `_rejeitado_por`, `_motivo_rejeicao`) no `fields` passado a `create_version`, garantindo que todo rascunho novo nasce limpo independente do estado do rascunho anterior.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter `_custo_alimentacao_por_equipe` (MOB) e o bottom-up de `BEN-*` coexistindo | Rejeitada por decisão do usuário — dupla contagem do mesmo conceito de benefício para o mesmo grupo de pessoas. |
| A2 | Café/almoço/jantar e vale-alimentação/cesta-básica como modelos alternativos (só um ativo) | Rejeitada por decisão do usuário — soma todos os 6 itens comuns (exceto jantar para PJ) como default seguro; se forem políticas realmente concorrentes, a correção é remover um grupo do catálogo ou marcar exclusão explícita depois, não modelar a exclusão agora sem dado real de qual política está em vigor. |
| A3 | Popular `funcoes_aplicaveis` só com o código canônico "preferido" por função | Rejeitada — o catálogo tem duplicação real de código por função (achado ADR-163); mapear todos os aliases evita que uma equipe usando um alias "não-preferido" fique sem o custo do item específico. |
| A4 | Inferir o mapeamento função→item sem nenhuma confirmação humana | Rejeitada — a própria ADR-165 (A4) já havia rejeitado essa abordagem; o rascunho foi publicado como artefato e confirmado via 3 perguntas antes de gravar no catálogo. |
| A5 | `TRE-NR22-MINERACAO` mapeado por palpite de função | Rejeitada — NR-22 é tipicamente exigência por área/projeto (quem entra em zona de mineração), não por cargo fixo; `funcoes_aplicaveis` é uma propriedade do catálogo (não muda por projeto). Fica com `[]` (nenhuma função) até existir um mecanismo por-projeto — gap documentado, não silencioso. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Custo de RH deixa de ser número de bolso | QSMS e MOB (benefício) agora refletem headcount real por função, preço de mercado do catálogo e regime de contrato (CLT/PJ), em vez de constantes fixas (R$3.000/mês, R$1.850/pessoa/mês). |
| Zero duplicação de conceito | MOB benefício e QSMS EPI/treinamento/exame passam a ter uma única fonte de verdade (catálogo ADR-165), cada um mapeado para exatamente uma categoria de indireto. |
| Degradação segura preservada em ambos os pontos | Se o catálogo não tiver itens RH (`None`/lista vazia), ambos os bottom-up retornam `None` e o cálculo cai automaticamente para o comportamento legado — nenhum catálogo antigo quebra. |
| Bug crítico de governança fechado antes de afetar mais catálogos | O achado P5 bloquearia qualquer segundo rascunho em qualquer catálogo após uma primeira aprovação — corrigido com teste de regressão dedicado. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `funcoes_aplicaveis` ainda sem FK validada (risco já documentado na ADR-165) | Inalterado por esta ADR — permanece gap conhecido; `auditar_catalogo` ainda não checa referência órfã/descontinuada aqui. |
| `TRE-NR22-MINERACAO` sem função associada não é custeado em nenhum projeto, mesmo em obras de mineração real | Documentado explicitamente (D4) — mecanismo por-projeto fica como trabalho futuro, não parte desta ADR. |
| Mapeamento função→item (D4) é um rascunho por correspondência de nome, confirmado por decisão do usuário mas não por RH/SESMT formal | Mesmo risco residual já assumido na conversa que gerou a confirmação — recomenda-se validação formal periódica. |
| `_composicao_mob_beneficio_bottom_up`/`_composicao_qsms_bottom_up` mudam o valor de indiretos calculado para qualquer orçamento que passe a rodar com o catálogo `mendeslobo` atualizado | Esperado e intencional — é exatamente o objetivo desta ADR (custo real em vez de lump); orçamentos já fechados/aprovados antes desta mudança não são recalculados retroativamente (fora do escopo). |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | D1 — `novos_funcoes_aplicaveis` em `atualizar_preco_insumo`/`atualizar_precos_insumos_lote` | ✅ Implementado |
| F2 | D5 — fix de herança de estado em `criar_rascunho_catalogo` + teste de regressão | ✅ Implementado |
| F3 | D4 — mapeamento função→item aplicado em `mendeslobo` via script | ✅ Implementado |
| F4 | D2 — `_composicao_qsms_bottom_up`, wiring em `_resolve_categoria_comp` | ✅ Implementado |
| F5 | D3 — `_composicao_mob_beneficio_bottom_up`, wiring em `_custo_mob_composicional`/`_process_mob_categoria`/`skill.py` | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] `novos_funcoes_aplicaveis` aceito por `atualizar_preco_insumo` e por item em `atualizar_precos_insumos_lote`
- [x] Teste cobrindo: lista vazia (`[]`) é preservada e distinta de `None`/ausente

### Fase 2
- [x] `criar_rascunho_catalogo` reseta todas as chaves de ciclo de vida no `fields` de `create_version`
- [x] Teste cobrindo (ContextoVersionService real, sem mock): segundo rascunho após aprovação do primeiro nasce em estado `RASCUNHO`, sem `_deltas` herdados

### Fase 3
- [x] 11 insumos atualizados em `mendeslobo` (verificado `auditar_catalogo` → `SAUDAVEL`)

### Fase 4
- [x] `_composicao_qsms_bottom_up` cobre: comum, específico, `funcoes_aplicaveis=[]`, insumo descontinuado, material sem prefixo `EPI-`, soma por headcount
- [x] `_resolve_categoria_comp` usa bottom-up para QSMS quando disponível, cai para lump senão

### Fase 5
- [x] `_composicao_mob_beneficio_bottom_up` cobre: comum, jantar exclui PJ, jantar aplica a regime desconhecido, soma por múltiplas equipes com permanências distintas
- [x] `_custo_mob_composicional`/`_process_mob_categoria`/`skill.py` threaded com `catalogo`, retrocompatível (catálogo sem `BENEFICIO` mantém comportamento legado)

## Nota de Implementação

Implementada via TDD em todas as fases. Suíte completa (14.795+ testes) verde, sem regressões fora do escopo — 1 falha pré-existente e não relacionada em `test_golden_evaluation.py` (confirmada idêntica antes desta ADR).

---

## Relacionados

- ADR-032 — Entidades Versionadas (`InsumoVersionado`, estendida na ADR-165)
- ADR-120 — Catalog RBAC Lifecycle (regra dos quatro olhos, exercida pelo fix de D5)
- ADR-136 — Custo MOB Composicional (`permanencia_efetiva_meses` por equipe, preservada por D3)
- ADR-145 — Unificação do Caminho de Escrita de Preço no Catálogo Mestre (D1 estende o mesmo caminho gated por rascunho/merge)
- ADR-163/164 — CRUD/Batch de Insumo (tools reaproveitadas por D1/D4)
- ADR-165 — Catálogo de Treinamentos, Exames, EPIs e Benefícios de Mão de Obra (D9 revisitada e implementada aqui)
