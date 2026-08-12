# ADR-176 — TOP Condicional a Obras Lineares + Reconciliação de MOB/Desmob a Partir de Ações Diretas e Indiretas

**Status:** ⚠️ Parcialmente Implementado _(F1-F4 ✅ 2026-08-03, em worktree separada `adr176-mob-reconciliacao`; F5 — reconciliar o 4º modelo `RegimeEquipamento` — segue proposta)_
**Data:** 2026-08-03
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-125 (Hierarquia C_prod/C_pool/Contrato), ADR-136 (Custo Mob/Demob no Pool), ADR-137 (Precificação Mob/Demob — Três Modelos Desconexos, **A1 reaberta aqui**), ADR-165–170 (catálogo RH + composição bottom-up), ADR-175 (formulário sem composição manual de indiretos)

---

## Contexto

### Problema

P1. Ao revisar o formulário de criação de projeto ([[ADR-175]]), o usuário trouxe um framework de classificação para as 5 categorias de indireto: **ADM e QSMS são comuns/estruturais** (praticamente todo projeto tem essa infraestrutura de retaguarda — tratamento correto já é "sempre presente por default"); **TOP e LAB são circunstanciais** (só compõem quando o projeto realmente precisar, análise caso a caso); **MOB/desmob é categoricamente diferente das outras quatro** — não é "time"/headcount de uma função, é consequência do conjunto de ações diretas (atividades da EAP) e indiretas (o próprio setup de ADM/TOP/LAB/QSMS) do projeto.

P2. LAB já tem gate circunstancial (ADR-169: só cobra com CPU de TERRAPLENAGEM/PAVIMENTACAO no projeto). **TOP não tem gate nenhum** — `_composicao_default_por_categoria("TOP")` sempre inclui o Topógrafo (`P0057`), independente do tipo de obra ou das categorias de CPU presentes.

P3. MOB/desmob indireto (skill-06, `_mob.py`) já foi objeto de duas ADRs anteriores que documentaram, mas **conscientemente não corrigiram**, um problema estrutural: a ADR-137 (D4) decidiu explicitamente **não unificar** os três modelos de precificação de mob/demob existentes no sistema — pool (`RecursoContrato.custo_mob_unit`), custo direto (`EquipeDireta`/catálogo) e indireto de projeto (`_mob.py`) — citando o risco de repetir um erro já cometido duas vezes na mesma sessão daquela ADR (achar que modelos "duplicados" eram iguais quando eram estruturalmente incompatíveis, ver ADR-136 F5).

P4. **Investigação desta sessão mostra que a premissa que sustentava essa cautela não se sustenta hoje** para o núcleo físico do problema — só para parte do que hoje vive dentro da categoria MOB:

- O comentário `# ADR-090: MOB é overhead administrativo` em `_mob.py:290` é **rótulo de roteamento de BDI** (qual alíquota de BDI-indireto se aplica), não uma afirmação sobre a natureza física do custo.
- O campo `categorias: ["equipamentos","mao_obra","verbas"]` do schema (`indiretoCategoriaFase`) — hoje metadado morto, nunca lido por nenhum código — mostra que a intenção original de MOB **sempre foi** ser decomponível nos mesmos universos de recurso dos modelos de pool/direto (equipamento, mão de obra), não uma categoria de "canteiro administrativo" à parte.
- O único exemplo real de item de `dados_mobilizacao.mobilizacoes` no repositório é `"Mob. equip.", 3 un., Goiânia→Aracoiaba, 2200 km` — transporte de **equipamento produtivo**, o mesmo universo físico dos modelos 1/2.
- No benchmark AGIS, o lump de MOB (R$4,05M) é da mesma ordem de grandeza de transportar a frota real do projeto (69 unidades × 2200 km × R$/km ≈ R$3,8M, 6,4% de diferença) — **não** é da ordem de grandeza de canteiro/administrativo, que já tem linha própria dentro de ADM (alojamento, verbas administrativas).
- **Porém**: o cálculo composicional de `_mob.py` também soma, no mesmo bucket, um termo de alimentação/seguro/cesta-básica por permanência de equipe (`_mob.py:173-185`) e viagens de rotação de pessoal (`baixadas`) — **isso não é mob/demob de coisa nenhuma**, é overhead recorrente contaminando a categoria. **F2 confirmou que este termo NÃO duplica nenhum outro cálculo**: é o próprio bottom-up de BENEFICIO da ADR-166 D3 (`_composicao_mob_beneficio_bottom_up`), que soma café/almoço/vale-alimentação/cesta-básica/seguro-vida — universo de insumo disjunto do bottom-up de QSMS (`_composicao_qsms_bottom_up`, só EPI/TREINAMENTO/EXAME) e sem relação com o cubo de roster real (ADR-174, `cubo_roster_real_builder.py`, que é view analítica separada e nunca realimenta este total). A hipótese de duplicidade original está descartada — o termo só está **mal-categorizado** (não é mob/demob), não duplicado.

P5. **Double-counting ativo confirmado em produção**: o benchmark SERRA_VERDE tem, simultaneamente, (a) 4 composições de CPU (`PROD-REJEITO-COMP-EQ*`) com valores reais não-zero de `custo_mobilizacao`/`custo_desmobilizacao` de catálogo (modelo 2, direto — R$6.500/equipamento e R$800/função, os mesmos valores que a ADR-137 D2 apontou como suspeitos de placeholder em outros contextos) e (b) um lump MOB indireto de R$10,69M (modelo 3). Os dois entram em somas diferentes (`custo_total_final` da equipe vs. `Indireto` MOB) que se somam no resultado financeiro final — sem nenhuma validação detectando a sobreposição.

P6. Em AGIS/AGIS-RFI, o pool **forma de fato** (26 `recurso_pool`, 9 `contratos_recurso`), mas `custo_mob_unit`/`custo_demob_unit` são 0,0 em 100% dos contratos (ADR-137 P1: `rcpsp_spec` auto-derivado omite `resource_costs` propositalmente) — então hoje, na prática, **só o modelo 3 (indireto, lump importado) carrega valor não-zero** nesses projetos; a decisão de perpetuação (ADR-073) roda em modo heurístico de tempo, não econômico.

P7. Achado adicional, não coberto pela ADR-137: existe um **quarto modelo** de precificação de mob/demob — `RegimeEquipamento.custo_mob`/`custo_demob` (`campanha_equipamento.py`) deriva `20%`/`15%` do custo mensal do equipamento como proxy heurística. Mesmo evento físico, quarta fórmula independente.

## Decisão

### D1 — TOP ganha gate circunstancial análogo ao LAB ✅ Implementado

`_composicao_default_por_categoria("TOP")` só cobra o Topógrafo (`quantidade=1`) quando o projeto tem CPU de **TERRAPLENAGEM, PAVIMENTACAO, DRENAGEM ou SANEAMENTO** — obras lineares que exigem locação topográfica de rede/perfil/greide (decisão do usuário: conjunto mais amplo que o do LAB, que cobre só TERRAPLENAGEM/PAVIMENTACAO). Fora desse conjunto (ex.: projeto só com OBRAS_ARTE/DIVERSOS), `quantidade=0`. `cpu_categorias_presentes=None` (categorias do projeto desconhecidas) preserva o comportamento antigo — sempre cobra —, mesma degradação segura da ADR-169.

### D2 — Reabrir a Alternativa A1 da ADR-137: os três modelos de mob/demob representam o mesmo evento físico e devem convergir para uma única fonte de custo por recurso

Decisão do usuário, ciente do risco documentado pela própria ADR-137. A investigação desta sessão (P4) sustenta que **o núcleo físico dos três modelos é o mesmo** (mobilizar/desmobilizar uma unidade de recurso produtivo até o canteiro) — não a mesma armadilha que a ADR-136 já identificou duas vezes (ali, os "duplicados" eram regras de negócio para decisões diferentes; aqui, é o mesmo evento físico com três réguas de preço independentes). A unificação **não é direta na categoria MOB inteira** — primeiro é preciso decompor.

### D3 — Decompor a categoria MOB indireta antes de unificar ✅ Implementado (F2)

`_custo_mob_composicional`/lump de projeto misturava três coisas que precisavam ser tratadas separadamente. `_custo_mob_decomposto` (novo, `_mob.py`) expõe os 3 sub-totais explicitamente (`MobBreakdown`), com `_custo_mob_composicional` preservado como wrapper retrocompatível (mesma assinatura, paridade numérica exata — testada):

1. **`transporte_total`** — mobilização/desmobilização de equipamento e mão de obra até o canteiro (`num_unidades × distancia_km × custo_km`). **Unificável** com os modelos 1 (pool) e 2 (`EquipeDireta`) — mesmo evento físico, deveria ter uma única fonte de custo por tipo de recurso. Fonte para F4.
2. **`beneficio_pessoal_total`** — alimentação/seguro/cesta-básica por permanência de equipe. **Não é mob/demob** — mas **F2 confirmou que não há sobreposição** com QSMS ou com o cubo de roster real (ver P4 acima). Fica na categoria MOB por ausência de categoria melhor (mesmo precedente da ADR-170 D3 para Alojamento em ADM) — não é movido, só isolado estruturalmente para não contaminar a unificação de `transporte_total` em F4.
3. **`baixadas_total`** — viagens periódicas de rotação de pessoal (`num_pessoas × valor_por_pessoa × n_ocorrencias`). Natureza própria (recorrente, não one-time de entrada/saída) — fica fora do escopo de unificação de F4 (que trata só de `transporte_total`).

### D3.1 — Resolver ADR-137 D2 no catálogo real: caminhões diferenciados de equipamento sobre esteira/prancha ✅ Implementado (F3)

Investigação em `PROD-REJEITO-COMP-EQ1..4-001.json` (mendeslobo, SERRA_VERDE) confirmou o achado da ADR-137 D2: os 8 equipamentos de cada composição tinham exatamente o mesmo `custo_mobilizacao`/`custo_desmobilizacao` (R$6.500,00), incluindo os 2 caminhões (Caminhão Pipa `E0013`, Caminhão Basculante `E0005`) — que rodam por conta própria até o canteiro, sem exigir prancha, ao contrário dos outros 6 (trator de esteiras, motoniveladora, trator de pneus, pá carregadeira, escavadeira, rolo compactador — todos fora-de-estrada).

Pesquisa de mercado (frete de prancha no Brasil) não trouxe preço confiável e diferenciado por classe de peso/equipamento — só confirmou a distinção estrutural qualitativa (caminhão não precisa de prancha; equipamento fora-de-estrada precisa, com licenciamento especial). Decisão do usuário: diferenciar só essa distinção estrutural, sem fingir precisão por peso específico de cada máquina. Caminhões passam para R$1.300,00 (20% do valor de prancha) nos 4 arquivos; os 6 equipamentos que exigem prancha mantêm R$6.500,00 inalterado (não há evidência de que esteja errado, só de que fora aplicado uniformemente a categorias distintas).

Confirmado que este campo (`custo_mobilizacao`/`custo_desmobilizacao` do equipamento) não participa da calibração de `custo_hora_total_referencia`/`valor_horario` desses 4 CPUs (que depende de `num_pessoas`/`num_unidades`/`preco_h_unitario`, ver memória `num-pessoas-fracionario-e-calibrado-nao-corrigir`) — suíte completa (SERRA_VERDE/golden/mob/calibração) verde após a mudança, sem impacto na calibração real.

### D4 — Fonte única de custo de mob/demob por recurso, consumida nos três contextos ✅ Implementado

**D4.1 — Indireto de projeto deixa de contar de novo o que o direto já pagou.** `_transporte_ja_contabilizado_direto` (`_mob.py`) soma `custo_mobilizacao_mensal + custo_desmobilizacao_mensal` de todas as `EquipeDireta` do projeto — o mesmo dado de catálogo já usado pelo custo direto (ADR-137 P2). `_process_mob_categoria` desconta esse valor do `transporte_total` da categoria MOB indireta, floor em zero, **nos dois caminhos** (lump pré-agregado via `categorias_config` — o que todo benchmark real usa hoje — e o composicional via `_custo_mob_decomposto`). Não desconta de `beneficio_pessoal_total`/`baixadas_total` (só de `transporte_total`, quando disponível separadamente). Elimina por construção o double-count confirmado em SERRA_VERDE (P5).

**D4.2 — Pool ganha custo real de mob/demob quando o rcpsp_spec é auto-derivado.** `_derive_rcpsp_from_canonical` (skill-05, `_pool_contrato_construcao.py`) passa a popular `resource_costs[tipo]["custo_mob_unit"/"custo_demob_unit"]` a partir do mesmo campo `custo_mobilizacao`/`custo_desmobilizacao` por função/equipamento embutido na composição do tipo (`_custo_mob_demob_unit_composicao`, reaproveita `_accum_mob_costs_list` de skill-05 — zero divergência de fórmula) — antes, `resource_costs` era omitido propositalmente e `RecursoContrato.custo_mob_unit`/`custo_demob_unit` ficavam sempre `0.0` no caminho automático (ADR-137 P1), rodando a decisão de perpetuação (ADR-073) sempre em modo heurístico de tempo. Só popula quando há custo real (>0) — sem dado no catálogo, `resource_costs` continua ausente, comportamento idêntico ao anterior.

**Achado durante a implementação, corrigido antes de fechar D4.2:** popular `resource_costs` fazia `resource_costs_absent` (`_setup_contratos_context`) virar `False` para o spec inteiro, desligando sem querer o fallback de custo idle (ADR-085, `cus_mo + cus_locacao`) mesmo quando só `custo_mob_unit`/`custo_demob_unit` foram populados (sem `custo_idle_semanal_unit`) — um teste de regressão pré-existente (`test_retrocompat_sem_idle_mantem_monolitico`) pegou isso na hora. Corrigido distinguindo 3 casos em vez de 2: chave ausente (fallback liga, igual antes); `resource_costs={}` explícito (sentinela ADR-071, fallback desliga, igual antes); `resource_costs` não-vazio sem `custo_idle_semanal_unit` para nenhum tipo (fallback continua ligado — caso novo desta ADR). Suíte completa (15139 testes) + ruff + ty verdes após a correção.

Isso resolve por construção o double-counting confirmado em SERRA_VERDE (P5): o mesmo recurso não pode ser precificado duas vezes se há uma única fonte de preço unitário (o dado de catálogo, corrigido em D3.1) e a linha de projeto passa a descontar o que já foi contado, em vez de somar uma estimativa paralela e desconectada.

### D5 — Reconciliar o quarto modelo (`RegimeEquipamento` 20%/15%)

Fora do escopo desta rodada de implementação — registrado como gap conhecido a resolver na mesma iniciativa de unificação (F5).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter a decisão da ADR-137 (não unificar), aceitando os 3+1 modelos desconexos como estão | Rejeitada pelo usuário — a investigação desta sessão mostra que o núcleo físico dos modelos é o mesmo evento, não cenários genuinamente incompatíveis (diferente do caso já resolvido pela ADR-136 F5); double-counting já confirmado ativo em produção (SERRA_VERDE) é um custo real de não agir. |
| A2 | Unificar a categoria MOB inteira como está, sem decompor primeiro | Rejeitada — o bucket de MOB mistura transporte de recurso (unificável) com verba de pessoal recorrente e baixadas (natureza diferente); unificar sem decompor replicaria a dupla contagem em vez de resolvê-la. |
| A3 | TOP usar o mesmo conjunto de categorias do LAB (só TERRAPLENAGEM/PAVIMENTACAO) | Rejeitada pelo usuário — TOP cobre um conjunto mais amplo (obras lineares, incluindo DRENAGEM/SANEAMENTO), circunstância diferente do LAB (ensaio laboratorial de solo/pavimento). |
| A4 | Implementar a unificação completa (D3/D4) nesta mesma sessão | Rejeitada por escopo — depende de decisão de dado (ADR-137 D2, valores de catálogo) e toca skill-04/05/06 + pool simultaneamente; fica como plano de fases proposto, não código fechado agora. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| TOP deixa de ser cobrado em projetos sem obra linear | Projetos só com OBRAS_ARTE/DIVERSOS não pagam mais um Topógrafo fantasma. |
| Double-counting confirmado (SERRA_VERDE) passa a ter caminho de correção | D3/D4 endereçam a causa raiz (três fontes de preço para o mesmo evento), não um patch pontual. |
| Decisão de perpetuação do pool deixa de rodar sempre em modo heurístico de tempo | Uma vez que D4 popular `custo_mob_unit`/`custo_demob_unit` reais, a decisão econômica (ADR-073) volta a ser possível em projetos com pool formado. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| D2-D5 são um programa de trabalho multi-sessão, não uma correção isolada | Fases explícitas (F2-F5), cada uma com Definition of Done própria; nenhuma implementação "boa parte feita" sem teste. |
| ~~D3.2 (mover `verba_pessoal_recorrente` para BENEFICIO) pode já estar duplicado com ADR-165/166 sem confirmação ainda~~ | **Resolvido em F2**: confirmado que não há sobreposição — universos de insumo disjuntos (BENEFICIO vs. EPI/TREINAMENTO/EXAME) e o cubo de roster real não realimenta o total financeiro. |
| D4 depende da ADR-137 D2 (revisão dos valores R$6.500/800 de catálogo — decisão de dado, não de código) | Sequenciar F4 depois da resposta de D2; não inventar valor de catálogo novo sem validação de quem mantém os dados. |
| Reverter projetos históricos calculados com os 3 modelos desconexos muda o `total` financeiro | Esperado e correto (mesmo padrão já aceito na ADR-136 D2) — comunicar como correção de bug, não mudança de comportamento neutra, quando F4 for implementada. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | TOP ganha gate circunstancial (TERRAPLENAGEM/PAVIMENTACAO/DRENAGEM/SANEAMENTO) | ✅ Implementado |
| F2 | Decompor `_custo_mob_composicional`/lump em `transporte_total` vs. `beneficio_pessoal_total` vs. `baixadas_total` (`MobBreakdown`/`_custo_mob_decomposto`); confirmar (ou descartar) sobreposição de `beneficio_pessoal_total` com BENEFICIO (ADR-165/166) — **descartada** | ✅ Implementado |
| F3 | Resolver ADR-137 D2 no catálogo real: caminhões (rodoviário, sem prancha) diferenciados de equipamento fora-de-estrada (requer prancha) — R$1.300 vs. R$6.500 mantido, nos 4 arquivos `PROD-REJEITO-COMP-EQ1..4` | ✅ Implementado |
| F4 | Fonte única de `transporte_recurso`: indireto desconta o que `EquipeDireta` já contabilizou (D4.1); pool ganha `custo_mob_unit`/`custo_demob_unit` reais quando `rcpsp_spec` é auto-derivado, sem desligar o fallback de idle ADR-085 (D4.2) | ✅ Implementado |
| F5 | Reconciliar `RegimeEquipamento` (20%/15%) com a fonte única de F4 | ⬜ Proposto |

## Definition of Done

### Fase 1
- [x] `_composicao_default_por_categoria("TOP")` aplica gate por `cpu_categorias_presentes` (TERRAPLENAGEM/PAVIMENTACAO/DRENAGEM/SANEAMENTO); `None` preserva comportamento antigo
- [x] Testes cobrindo: cada categoria do gate aplica isoladamente; conjunto vazio e categorias fora do gate (OBRAS_ARTE/DIVERSOS) zeram; `None` preserva lump legado; ADM não é afetado (`test_adr176_top_condicional_obras_lineares.py`)
- [x] Suíte completa (15103 testes) + ruff + ty sem novos erros

### Fase 2
- [x] `_custo_mob_decomposto` (`_mob.py`) retorna `MobBreakdown` com `transporte_total`/`beneficio_pessoal_total`/`baixadas_total`, mais `total` e `mobilizacoes` (mesmos campos de sempre)
- [x] `_custo_mob_composicional` preservado como wrapper retrocompatível — mesma assinatura, mesmo retorno `(total, mobilizacoes)`; paridade numérica exata testada contra o cálculo manual pré-ADR-176
- [x] Investigação de sobreposição de `beneficio_pessoal_total` com QSMS (`_composicao_qsms_bottom_up`) e com o cubo de roster real (ADR-174) — **sem sobreposição confirmada** (universos de insumo disjuntos; cubo é view analítica que não realimenta o total financeiro)
- [x] `MobBreakdown`/`_custo_mob_decomposto` exportados em `_skill_helpers/__init__.py` — disponíveis para F4
- [x] Testes cobrindo cada sub-total isoladamente, o total como soma dos três, o bottom-up de benefício contando como `beneficio_pessoal_total` (não `transporte_total`), e paridade exata do wrapper (`test_adr176_mob_decomposto.py`)
- [x] Suíte completa (15110 testes, F1+F2 juntos) + ruff + ty sem novos erros

### Fase 3
- [x] Confirmado no catálogo real (`PROD-REJEITO-COMP-EQ1..4-001.json`) que os 8 equipamentos tinham `custo_mobilizacao`/`custo_desmobilizacao` uniformes (R$6.500,00), incluindo os 2 caminhões
- [x] Pesquisa de mercado realizada (frete de prancha) — sem preço confiável por classe de peso; decisão do usuário: diferenciar só rodoviário (caminhão) vs. requer-prancha (demais), R$1.300 (20% de R$6.500) para caminhões
- [x] `E0013`/`E0005` atualizados para R$1.300,00 (mob e demob) nos 4 arquivos; os outros 6 equipamentos mantidos em R$6.500,00
- [x] Teste de regressão cobrindo os 4 arquivos × 8 equipamentos (`test_adr176_mob_transporte_diferenciado.py`)
- [x] Confirmado que a calibração de `custo_hora_total_referencia`/`valor_horario` desses 4 CPUs não depende deste campo — suíte completa (15122 testes) + ruff + ty sem novos erros

### Fase 4
- [x] `_transporte_ja_contabilizado_direto` soma `custo_mobilizacao_mensal`/`custo_desmobilizacao_mensal` de todas as `EquipeDireta`
- [x] `_process_mob_categoria` desconta esse valor do `transporte_total`, floor em zero, nos dois caminhos (lump `categorias_config` e composicional via `_custo_mob_decomposto`) — sem afetar `beneficio_pessoal_total`/`baixadas_total`
- [x] `_custo_mob_demob_unit_composicao` (reaproveita `_accum_mob_costs_list` de skill-05, zero divergência de fórmula) deriva custo unitário de mob/demob por tipo de recurso a partir da composição
- [x] `_derive_rcpsp_from_canonical` popula `resource_costs[tipo]["custo_mob_unit"/"custo_demob_unit"]` só quando há custo real (>0); ausência de dado no catálogo preserva o comportamento anterior (chave `resource_costs` ausente)
- [x] `_setup_contratos_context` distingue 3 casos (chave ausente / `{}` explícito sentinela ADR-071 / não-vazio sem idle) — fallback de custo idle (ADR-085) preservado; regressão pega e corrigida antes de fechar (`test_retrocompat_sem_idle_mantem_monolitico`)
- [x] Testes cobrindo: soma de mob/demob por composição, dedup no lump e no composicional (incluindo floor em zero quando o desconto excede o lump), população condicional de `resource_costs`, e os 4 casos de `resource_costs_absent` (`test_adr176_mob_dedup_transporte_direto.py`, `test_adr176_pool_mob_demob_unit.py`)
- [x] Suíte completa (15139 testes) + ruff + ty sem novos erros

### Fase 5
- [ ] A definir — reconciliar `RegimeEquipamento` (20%/15%) com a fonte única de D4

---

## Relacionados

- ADR-125 — Hierarquia de Custo C_prod/C_pool/Contrato (mob/demob fora de `C_pool`, decisão que permanece válida — esta ADR não mexe em *onde* mob/demob entra na hierarquia, só em *de onde vem o número*)
- ADR-136 — Custo de Mob/Demob no Pool (populou `custo_mob_instancia`/`custo_demob_instancia` reais; base sobre a qual D4 constrói a fonte única)
- ADR-137 — Precificação de Mob/Demob: Três Modelos Desconexos (A1 reaberta por esta ADR; D2/D3 seguem pendentes e agora fazem parte do plano F3/F5)
- ADR-165–170 — Catálogo RH + composição bottom-up (padrão de degradação segura reaplicado ao gate de TOP; candidato a absorver `verba_pessoal_recorrente` em F2)
- ADR-169 — LAB Condicional (padrão que esta ADR estende ao TOP)
- ADR-175 — Formulário sem composição manual de indiretos (origem da conversa que trouxe o framework comum/circunstancial/consequência desta ADR)
