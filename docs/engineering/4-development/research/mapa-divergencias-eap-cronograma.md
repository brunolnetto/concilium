# Mapa de Divergências EAP ↔ Cronograma

**Projeto:** Concilium — MendesLobo Construtora  
**Data:** 2026-06-09  
**Objetivo:** Catalogar discrepâncias entre o planejamento (EAP/orçamento) e o cronograma de execução em cada benchmark, identificando merges, reduções de escopo e itens não programados.

---

## Tipos de Divergência

| Tipo | Descrição | Impacto |
|---|---|---|
| **M — Merge** | Múltiplos itens EAP tratados como uma única atividade no cronograma | CPU da atividade consolidada cobre múltiplos quantitativos |
| **R — Redução de escopo** | Item está no planejamento mas foi removido ou não programado | Item não entra no RCPSP; custo excluído do preço de venda |
| **A — Administração excluída** | Serviços VB (custos indiretos embutidos na EAP) ausentes do cronograma | Tratados separadamente como indiretos |
| **D — Duplicata** | Item aparece múltiplas vezes no planejamento com diferentes prefixos (ex: 5.10-5.14 e 5.15-5.19 para trechos distintos) | Pode indicar escopo repetido para fases distintas |

---

## AGIS — MVP 09 e 10 (CE)

**Planejamento:** 11 itens | **Cronograma:** 8 atividades | **Merges:** 3

| Item EAP | Descrição (truncada) | Unid | Status | Tipo | Merge com |
|---|---|---|---|---|---|
| 1.0 | Desmatamento/destocamento ≤15cm | M2 | ✅ | — | — |
| 1.1 | Escavação 1ª cat DMT ≤2000m | M3 | ✅ | — | — |
| **1.2** | **Escavação 1ª cat DMT 2000–3000m** | M3 | ⚠️ Ausente | **M** | **Merge em 1.1** |
| 1.3 | Escavação 2ª cat DMT ≤2000m | M3 | ✅ | — | — |
| **1.4** | **Escavação 2ª cat DMT 2000–3000m** | M3 | ⚠️ Ausente | **M** | **Merge em 1.3** |
| 1.5 | Escavação 3ª cat DMT ≤2000m | M3 | ✅ | — | — |
| **1.6** | **Escavação 3ª cat DMT 2000–3000m** | M3 | ⚠️ Ausente | **M** | **Merge em 1.5** |
| 1.7 | Compactação aterros 100% Proctor Normal | M3 | ✅ | — | — |
| 1.8 | Compactação aterros 100% Proctor Intermediário | M3 | ✅ | — | — |
| 1.9 | Corpo de aterro material 3ª cat | M3 | ✅ | — | — |
| 1.10 | Compactação camada final de aterro de rocha | M3 | ✅ | — | — |

**Nota:** Para 1.1+1.2, o planejamento define DMT distintas mas o projetista usou uma só atividade de cronograma. A CPU correta seria a média ponderada de 2.1 e 2.2 pelo quantitativo.

**CPUs disponíveis:** 2.1–2.5 (excav 1ª/2ª/3ª cat em DMTs distintas), mais compactação, limpeza.

---

## RUMO — Dom Aquino (MT)

**Planejamento:** 50 itens | **Cronograma:** 24 atividades | **Ausentes:** 26

| Seção | Itens ausentes | Tipo | Interpretação |
|---|---|---|---|
| **1.2** | Transporte solo excedente (m3) | **R** | Fora de escopo ou embutido em 2.1 |
| **3.2** | Transporte material demolição para bota-fora | **R** | Bota-fora interno, sem atividade programada |
| **4.9** | Fresagem pavimento 10cm (para encaixes alças) | **R** | Redução de escopo — alças não executadas nesta fase |
| **5.10–5.14** | Escavação valas, regularização, hidrossemeadura (drenagem) | **D** | Duplicata para trecho 2 — merge com 5.5–5.9 |
| **5.15–5.19** | Idem trecho 3 (typo: "Eegularização") | **D** | Duplicata para trecho 3 — merge com 5.5–5.9 |
| **6.1–6.11** | Sinalização horizontal e vertical completa (11 itens) | **R** | Redução de escopo — sinalização não contratada nesta fase |
| **8.1** | Material e mão de obra (VB) | **A** | Administração — item genérico, tratado como indireto |

**CPUs disponíveis (17):** Espalhamento/compactação, limpeza, compactação 95% Proctor, regularização subleito, estabilização granulométrica, imprimação, escavação de valas, boca de lobo BSTC, entre outros. Nenhuma CPU para sinalizações (itens 6.x).

---

## PRIVATE_LOG — Cidade da Serra (ES)

**Planejamento:** 17 itens | **Cronograma:** 10 atividades | **Ausentes:** 7

| Item EAP | Descrição | Unid | Tipo | Interpretação |
|---|---|---|---|---|
| **1.2** | Supressão de árvores isoladas | UN | **R** | Escopo reduzido — poucas árvores, custo absorvido em limpeza |
| **1.7** | Transporte material britagem DMT 1km | M3 | **R** | Logística de britagem não programada separadamente |
| **4.1** | Administração | VB | **A** | Indireto administrativo |
| **4.2** | Topografia | VB | **A** | Indireto de topografia |
| **4.3** | Laboratório | VB | **A** | Indireto de laboratório |
| **4.4** | QSMS | VB | **A** | Indireto QSMS |
| **4.5** | Mob/Desmobilização | VB | **A** | Mobilização |

**Nota:** Os itens 4.1–4.5 (VB) correspondem diretamente aos arquivos `indiretos.*.txt` — já tratados pela pipeline de indiretos.

---

## VALE — Lote 7 e 8 (GO)

**Planejamento:** 16 itens | **Cronograma:** 10 atividades | **Ausentes:** 6

| Item EAP | Descrição | Unid | Tipo | Interpretação |
|---|---|---|---|---|
| **1.3** | Corte destocamento árvores Ø > 30cm | UN | **R** | Supressão de árvores grandes — quantitativo pequeno, absorvido em 1.1 |
| **2.1** | Mata burro (fornecimento + instalação) | UN | **R** | Acessórios de cerca — item de material puro, sem CPU de equipe |
| **2.2** | Porteira de madeira (fornecimento + instalação) | UN | **R** | Idem |
| **2.3** | Porteira metálica (fornecimento + instalação) | UN | **R** | Idem |
| **2.4** | Remoção de mata burro | UN | **R** | Demolição — custo absorvido na terraplenagem geral |
| **2.5** | Remoção de porteira | UN | **R** | Idem |

**Nota:** Os itens 2.1–2.5 são basicamente materiais e serviços de cerca/porteira com execução manual. Sem CPU de equipe mecânica associada. Redução de escopo ou execução por terceiros.

---

## CTC — Barra do Ribeiro (RS)

**Planejamento:** 45 itens | **Cronograma:** 6 atividades | **Ausentes:** 39

Esta é a **maior discrepância** do conjunto: o cronograma contém apenas a seção de terraplenagem.

| Seção Planejamento | Qtd Itens | Tipo | Situação |
|---|---|---|---|
| **1.x — Terraplenagem** | 7 | ✅ Parcial | 6 presentes no cronograma (1.7 ausente) |
| **2.x — Drenagem** (bocas de lobo, PVs, tubos, canaletas) | 24 | **R** | Seção inteira ausente do cronograma |
| **3.x — Pavimentação** (caixas, reforço subleito, base, asfalto) | 9 | **R** | Seção inteira ausente do cronograma |
| **4.x — Administração** (adm, topografia, laboratório, QSMS, mob) | 5 | **A** | Indiretos |

**Interpretação:** O cronograma do CTC representa apenas a **fase de terraplenagem** de um projeto muito maior. As fases de drenagem e pavimentação foram provavelmente postergadas ou são objeto de outro contrato.

**Impacto na calibração:** Os 26 CPUs disponíveis cobrem praticamente toda a drenagem e pavimentação (tubos concreto, bocas de lobo, canaletas, CCR) — mas nenhuma delas aparece no cronograma. **O benchmark RCPSP deve usar apenas as 6 atividades do cronograma.**

---

## LUNDIN — Alto Horizonte (GO)

**Planejamento:** 6 itens | **Cronograma:** 3 atividades | **Ausentes:** 3

| Item EAP | Descrição | Unid | Tipo | Interpretação |
|---|---|---|---|---|
| **1.2** | Corte de árvores isoladas | UN | **R** | Quantitativo pequeno, absorvido em supressão geral |
| **1.4** | Organização de pilha de madeira | MENSAL | **R** | Serviço mensal de gestão — sem CPU de equipe mecânica |
| **1.6** | Aproveitamento interno da madeira | M3 | **R** | Beneficiamento de madeira — terceirizado |

**Nota:** Este benchmark tem o menor escopo do conjunto — apenas 3 atividades de supressão/limpeza. O `producoes.txt` separado confirma as produtividades para as atividades presentes.

---

## MARA_ROSA — Mara Rosa (GO)

**Planejamento:** 7 itens | **Cronograma:** 7 atividades | **Divergências:** ✅ nenhuma

Correspondência perfeita. Benchmark com escopo de supressão vegetal e terraplanagem simples (desmatamento, escavação, aterro + drenagem básica). Tem `producoes.txt` separado — catálogo de produtividades compartilhado com ROSH.

**Nota:** O `producoes.txt` de MARA_ROSA e ROSH são **idênticos** — trata-se de um catálogo de produtividades padrão MendesLobo para obras de mineração GO/MT (Grupo Votorantim). Cobre terraplenagem, drenagem, rede de água e pavimentação, muito além do escopo do próprio benchmark.

---

## ROSH — Parnamirim (RN)

**Planejamento:** 7 itens | **Cronograma:** 7 atividades | **Divergências:** ✅ nenhuma

Correspondência perfeita. Mesmo padrão de MARA_ROSA (escopo de supressão + terraplanagem). `producoes.txt` idêntico ao MARA_ROSA. 6 CPUs disponíveis.

---

## MATEC_HINES — Guarulhos (SP)

**Planejamento:** 9 itens | **Cronograma:** 4 atividades | **Ausentes:** 5  
**CPUs:** ❌ arquivo cpus.txt ausente — único benchmark sem composições unitárias

| Item EAP | Descrição | Tipo | Interpretação |
|---|---|---|---|
| 1.0 | Supressão Vegetal | ✅ Presente | — |
| 1.1 | Remoção Superficial Top Soil | ✅ Presente | — |
| 1.2 | Corte e transporte interno | ✅ Presente | — |
| 1.3 | Aterro compactado 98%/100% PN | ✅ Presente | — |
| **1.4** | **Opcional — Bota-fora externo** | **R** | Item contingencial explicitamente marcado "Opcional" |
| **1.5** | **Opcional — Transporte solo, DMT 8km** | **R** | Idem — só executa se necessário |
| **1.6** | **Opcional — Solo 2ª categoria** | **R** | Idem |
| **1.7** | **Opcional — Solo 3ª categoria (Rochoso)** | **R** | Idem |
| **1.8** | **Opcional — Britagem de rochas** | **R** | Idem |

**Nota especial:** Os 5 ausentes estão explicitamente marcados como "Opcional" no próprio nome do serviço — não é redução de escopo involuntária, é escopo contingencial formalizado. Não são executados se o corte não encontrar material de 2ª/3ª categoria ou se o bota-fora couber internamente.

A ausência de `cpus.txt` neste benchmark significa que as produtividades devem ser obtidas do `producoes.txt` de MARA_ROSA/ROSH (catálogo compartilhado) ou estimadas a partir dos benchmarks vizinhos (MATEC_GUARULHOS, MATEC_UBERLANDIA).

---

## MATEC_UBERLANDIA — Uberlândia (MG)

**Planejamento:** 2 itens | **Cronograma:** 2 atividades | **Divergências:** ✅ nenhuma

O menor benchmark em número de atividades — dois serviços apenas. Correspondência perfeita. 8 CPUs disponíveis (proporcionalmente o maior ratio CPUs/atividades do conjunto, indicando composições detalhadas para um escopo muito restrito).

---

## ODFJELL — Santa Helena (GO)

**Cronograma:** ❌ arquivo ausente — benchmark usa planejamento como fonte de atividades  
**Planejamento:** ~23 itens identificados (seções 1=limpeza, 2=terraplenagem, 3=drenagem)

Os itens do planejamento são a referência direta para o RCPSP. Ausência de cronograma significa que o projetista não gerou o detalhamento semanal — a pipeline infere o schedule a partir dos quantitativos e produtividades.

**Nota importante:** O `referencia.json` deve conter apenas os itens para os quais existe CPU no `cpus.txt`. Os itens de drenagem (3.1–3.13: tubos, caixas, mantas, materiais) são majoritariamente serviços de material, sem CPU de equipe mecânica.

---

## MATEC_GUARULHOS — Guarulhos (SP)

**Cronograma:** ❌ arquivo ausente  
**Planejamento:** 16 itens (1=limpeza, 2=terraplenagem/drenagem, 3=administração)

| Item | Descrição | Tipo |
|---|---|---|
| 1.1–1.2 | Limpeza vegetal + transporte | ✅ Com CPU |
| 2.1–2.6 | Escavação, aterro, solos orgânicos | ✅ Com CPU |
| 2.7–2.9 | Espinha de peixe, bueiro celular, alas | R/Material — sem CPU de equipe |
| 3.1–3.6 | Administração, topografia, laboratório, QSMS, mob | **A** Indiretos |

**CPUs disponíveis (6):** Limpeza vegetal, escavação 1ª cat, aterro compactado, aterro de sobrecarga, escavação de turfas. Itens 2.7–2.9 sem CPU correspondente.

---

## Resumo Consolidado

| Benchmark | Plano | Crono | Ausentes | Merges | Adm | Redução |
|---|---|---|---|---|---|---|
| AGIS | 11 | 8 | 3 | 3 (M) | 0 | 0 |
| RUMO | 50 | 24 | 26 | 3 (D) | 1 (A) | 22 (R) |
| PRIVATE_LOG | 17 | 10 | 7 | 0 | 5 (A) | 2 (R) |
| VALE | 16 | 10 | 6 | 0 | 0 | 6 (R) |
| CTC | 45 | 6 | 39 | 0 | 5 (A) | 34 (R) |
| LUNDIN | 6 | 3 | 3 | 0 | 0 | 3 (R) |
| MARA_ROSA | 7 | 7 | 0 | — | — | — |
| ROSH | 7 | 7 | 0 | — | — | — |
| MATEC_HINES | 9 | 4 | 5 | 0 | 0 | 5 (Opcional) |
| MATEC_UBERLANDIA | 2 | 2 | 0 | — | — | — |
| ODFJELL | ~23 | ❌ s/cron | — | — | — | — |
| MATEC_GUARULHOS | 16 | ❌ s/cron | — | — | 6 (A) | 3 (R/Mat) |

---

## Recomendações para a Pipeline

1. **Merges (AGIS 1.2→1.1, 1.4→1.3, 1.6→1.5):** No `referencia.json`, o item de cronograma deve acumular o quantitativo dos itens mergeados. A CPU associada deve ser a mais representativa (a de DMT menor, que tem maior produtividade). O `planejamento` deve listar **ambos** os quantitativos para o mesmo item.

2. **Reduções de escopo (RUMO sinalização, CTC drenagem):** Esses itens não devem entrar no RCPSP. São candidatos à marcação `"ativo": false` no spec ou simplesmente ausência do cronograma JSON.

3. **Administração/VB (PRIVATE_LOG, CTC):** Já tratados pelos arquivos `indiretos.*.txt`. Não duplicar no spec do cronograma.

4. **CTC:** O benchmarking deve ser feito apenas sobre as 6 atividades de terraplenagem. As CPUs de drenagem e pavimentação são dados válidos para enriquecer o catálogo, mas não para calibrar este benchmark específico.

5. **LUNDIN producoes.txt:** Fonte de verdade para produtividades — usar preferencialmente sobre a extração da linha (C) das CPUs.
