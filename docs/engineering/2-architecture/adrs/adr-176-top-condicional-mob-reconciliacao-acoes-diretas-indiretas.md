# ADR-176 — TOP Condicional a Obras Lineares + Reconciliação de MOB/Desmob a Partir de Ações Diretas e Indiretas

**Status:** ⚠️ Parcialmente Implementado _(F1/TOP ✅ 2026-08-03; F2-F5/MOB propostas — decisão de dado e trabalho multi-sessão, não fechável nesta rodada)_
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
- **Porém**: o cálculo composicional de `_mob.py` também soma, no mesmo bucket, um termo de alimentação/seguro/cesta-básica por permanência de equipe (`_mob.py:173-185`) e viagens de rotação de pessoal (`baixadas`) — **isso não é mob/demob de coisa nenhuma**, é overhead recorrente contaminando a categoria. Esse termo provavelmente já duplica o que a ADR-165/166 calcula via BENEFICIO bottom-up (café/almoço/vale-alimentação/cesta-básica/seguro-vida por função) — não confirmado nesta ADR, fica como F2.

P5. **Double-counting ativo confirmado em produção**: o benchmark SERRA_VERDE tem, simultaneamente, (a) 4 composições de CPU (`PROD-REJEITO-COMP-EQ*`) com valores reais não-zero de `custo_mobilizacao`/`custo_desmobilizacao` de catálogo (modelo 2, direto — R$6.500/equipamento e R$800/função, os mesmos valores que a ADR-137 D2 apontou como suspeitos de placeholder em outros contextos) e (b) um lump MOB indireto de R$10,69M (modelo 3). Os dois entram em somas diferentes (`custo_total_final` da equipe vs. `Indireto` MOB) que se somam no resultado financeiro final — sem nenhuma validação detectando a sobreposição.

P6. Em AGIS/AGIS-RFI, o pool **forma de fato** (26 `recurso_pool`, 9 `contratos_recurso`), mas `custo_mob_unit`/`custo_demob_unit` são 0,0 em 100% dos contratos (ADR-137 P1: `rcpsp_spec` auto-derivado omite `resource_costs` propositalmente) — então hoje, na prática, **só o modelo 3 (indireto, lump importado) carrega valor não-zero** nesses projetos; a decisão de perpetuação (ADR-073) roda em modo heurístico de tempo, não econômico.

P7. Achado adicional, não coberto pela ADR-137: existe um **quarto modelo** de precificação de mob/demob — `RegimeEquipamento.custo_mob`/`custo_demob` (`campanha_equipamento.py`) deriva `20%`/`15%` do custo mensal do equipamento como proxy heurística. Mesmo evento físico, quarta fórmula independente.

## Decisão

### D1 — TOP ganha gate circunstancial análogo ao LAB ✅ Implementado

`_composicao_default_por_categoria("TOP")` só cobra o Topógrafo (`quantidade=1`) quando o projeto tem CPU de **TERRAPLENAGEM, PAVIMENTACAO, DRENAGEM ou SANEAMENTO** — obras lineares que exigem locação topográfica de rede/perfil/greide (decisão do usuário: conjunto mais amplo que o do LAB, que cobre só TERRAPLENAGEM/PAVIMENTACAO). Fora desse conjunto (ex.: projeto só com OBRAS_ARTE/DIVERSOS), `quantidade=0`. `cpu_categorias_presentes=None` (categorias do projeto desconhecidas) preserva o comportamento antigo — sempre cobra —, mesma degradação segura da ADR-169.

### D2 — Reabrir a Alternativa A1 da ADR-137: os três modelos de mob/demob representam o mesmo evento físico e devem convergir para uma única fonte de custo por recurso

Decisão do usuário, ciente do risco documentado pela própria ADR-137. A investigação desta sessão (P4) sustenta que **o núcleo físico dos três modelos é o mesmo** (mobilizar/desmobilizar uma unidade de recurso produtivo até o canteiro) — não a mesma armadilha que a ADR-136 já identificou duas vezes (ali, os "duplicados" eram regras de negócio para decisões diferentes; aqui, é o mesmo evento físico com três réguas de preço independentes). A unificação **não é direta na categoria MOB inteira** — primeiro é preciso decompor.

### D3 — Decompor a categoria MOB indireta antes de unificar

`_custo_mob_composicional`/lump de projeto hoje mistura três coisas que precisam ser tratadas separadamente:

1. **`transporte_recurso`** — mobilização/desmobilização de equipamento e mão de obra até o canteiro. **Unificável** com os modelos 1 (pool) e 2 (`EquipeDireta`) — mesmo evento físico, deveria ter uma única fonte de custo por tipo de recurso.
2. **`verba_pessoal_recorrente`** — alimentação/seguro/cesta-básica por permanência de equipe. **Não é mob/demob** — candidato a fundir com (ou ser substituído por) o bottom-up de BENEFICIO já existente (ADR-165/166), não com os modelos 1/2. Verificar sobreposição antes de mover (F2).
3. **`baixadas`** — viagens periódicas de rotação de pessoal. Natureza própria (recorrente, não one-time de entrada/saída) — avaliar separadamente se pertence a MOB ou a outra categoria (TOP/QSMS de campo).

### D4 — Fonte única de custo de mob/demob por recurso, quando `transporte_recurso` estiver isolado

Uma vez isolado (D3.1), o custo de mobilizar/desmobilizar um tipo de recurso (equipamento ou função) passa a ter **uma fonte por tipo de recurso** — via catálogo (preço real, resolvendo a pendência D2 da ADR-137 sobre os valores R$6.500/800) —, consumida nos três contextos: threshold de perpetuação do pool (`custo_mob_unit`/`custo_demob_unit`), custo direto de equipe (`EquipeDireta`), e a linha de indireto de projeto passa a ser a **soma/rollup** dos eventos reais de mobilização do projeto (não uma estimativa paralela e desconectada). Isso resolve por construção o double-counting confirmado em SERRA_VERDE (P5): o mesmo recurso não pode ser precificado duas vezes se há uma única fonte de preço unitário e a linha de projeto é agregação, não estimativa independente.

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
| D3.2 (mover `verba_pessoal_recorrente` para BENEFICIO) pode já estar duplicado com ADR-165/166 sem confirmação ainda | F2 investiga antes de mover — não presumir a sobreposição sem verificar valores reais lado a lado. |
| D4 depende da ADR-137 D2 (revisão dos valores R$6.500/800 de catálogo — decisão de dado, não de código) | Sequenciar F4 depois da resposta de D2; não inventar valor de catálogo novo sem validação de quem mantém os dados. |
| Reverter projetos históricos calculados com os 3 modelos desconexos muda o `total` financeiro | Esperado e correto (mesmo padrão já aceito na ADR-136 D2) — comunicar como correção de bug, não mudança de comportamento neutra, quando F4 for implementada. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | TOP ganha gate circunstancial (TERRAPLENAGEM/PAVIMENTACAO/DRENAGEM/SANEAMENTO) | ✅ Implementado |
| F2 | Decompor `_custo_mob_composicional`/lump em `transporte_recurso` vs. `verba_pessoal_recorrente` vs. `baixadas`; confirmar (ou descartar) sobreposição de `verba_pessoal_recorrente` com BENEFICIO (ADR-165/166) | ⬜ Proposto |
| F3 | Resolver ADR-137 D2 (dado de catálogo real por tipo de equipamento/função, substituindo R$6.500/800) — decisão de dado, não de código | ⬜ Proposto |
| F4 | Fonte única de `transporte_recurso` por tipo de recurso, consumida por pool (`custo_mob_unit`/`custo_demob_unit`), `EquipeDireta` e indireto de projeto (rollup); eliminar double-count confirmado (SERRA_VERDE) | ⬜ Proposto |
| F5 | Reconciliar `RegimeEquipamento` (20%/15%) com a fonte única de F4 | ⬜ Proposto |

## Definition of Done

### Fase 1
- [x] `_composicao_default_por_categoria("TOP")` aplica gate por `cpu_categorias_presentes` (TERRAPLENAGEM/PAVIMENTACAO/DRENAGEM/SANEAMENTO); `None` preserva comportamento antigo
- [x] Testes cobrindo: cada categoria do gate aplica isoladamente; conjunto vazio e categorias fora do gate (OBRAS_ARTE/DIVERSOS) zeram; `None` preserva lump legado; ADM não é afetado (`test_adr176_top_condicional_obras_lineares.py`)
- [x] Suíte completa (15103 testes) + ruff + ty sem novos erros

### Fases 2-5
- [ ] A definir na sessão de implementação de cada fase — bloqueadas por decisão de dado (F3) e investigação de sobreposição (F2) antes de qualquer código novo

---

## Relacionados

- ADR-125 — Hierarquia de Custo C_prod/C_pool/Contrato (mob/demob fora de `C_pool`, decisão que permanece válida — esta ADR não mexe em *onde* mob/demob entra na hierarquia, só em *de onde vem o número*)
- ADR-136 — Custo de Mob/Demob no Pool (populou `custo_mob_instancia`/`custo_demob_instancia` reais; base sobre a qual D4 constrói a fonte única)
- ADR-137 — Precificação de Mob/Demob: Três Modelos Desconexos (A1 reaberta por esta ADR; D2/D3 seguem pendentes e agora fazem parte do plano F3/F5)
- ADR-165–170 — Catálogo RH + composição bottom-up (padrão de degradação segura reaplicado ao gate de TOP; candidato a absorver `verba_pessoal_recorrente` em F2)
- ADR-169 — LAB Condicional (padrão que esta ADR estende ao TOP)
- ADR-175 — Formulário sem composição manual de indiretos (origem da conversa que trouxe o framework comum/circunstancial/consequência desta ADR)
