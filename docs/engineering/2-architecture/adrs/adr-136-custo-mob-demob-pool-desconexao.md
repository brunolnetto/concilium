# ADR-136 — Custo de Mobilização/Desmobilização: Campos Mortos no Pool e Cálculo Desconectado (Skill-06)

**Status:** ⚠️ Parcialmente Implementado _(F1/F2/F3/F6 ✅; F4/F5 deferidas — ver nota)_
**Data:** 2026-07-10
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-085 (Custo Instancial Composicional Temporal), ADR-125 (Hierarquia de Custo C_prod/C_pool/Contrato), ADR-105 (Mobilização e Desmobilização — Política Integrada), ADR-106 (LifecycleEngine), ADR-104 (Centralização do Cálculo de Custos), NEP-043 (Reconciliação C_r)

> **Nota de escopo desta PR (2026-07-10):** implementadas F1 (levantamento —
> consolidado no Contexto/P1-P5), F2 (reconciliação ADR-085/ADR-125), F3
> (popular `custo_mob_instancia`/`custo_demob_instancia` reais no pool) e F6
> parcial (regressão confirmando que `C_pool < total` deixou de ser uma
> tautologia). F4 (conectar skill-06/`_mob.py` ao ciclo de vida real do pool) e
> F5 (decisão sobre `equipe_custo_engine.py`) são deferidas para PR(s)
> subsequentes — ambas exigem desenho de interface entre skill-05 e skill-06
> (F4) ou um levantamento de call sites mais amplo (F5) que não é seguro
> encaixar na mesma mudança que corrige os campos mortos do pool.

---

## Contexto

### Problema

P1. **ADR-085 e ADR-125 têm fórmulas mutuamente incompatíveis para onde mob/demob entram na hierarquia de custo, e nenhuma revogação formal reconcilia isso.**

ADR-085 D3 (2026-05-29, `Status: Implementado`) define o custo da instância **incluindo** mob/demob dentro do próprio pool:

$$\text{custo}(I_k) = \sum_{\text{prod}} c_r + \sum_{\text{idle}} c_r^{\text{idle}} + c_r^{\text{mob}} + c_r^{\text{demob,efetivo}}$$

ADR-125 D1 (2026-06-28, `Status: ✅ Implementado`) decide o **oposto** deliberadamente:

```
C_pool_i = C_prod_i + (γ_i^mo + κ·γ_i^eq) · n_s          (exclui mob/demob)
total_i  = C_pool_i + c_mob + c_dem + mob_window + demob_window
```

com a alternativa "incluir mob/demob em C_pool" avaliada e **rejeitada** (A2: "mob/demob são overhead de canteiro... não variam com n_p ou n_s — são eventos de entrada/saída do pool"). ADR-125 é uma decisão consciente e bem fundamentada — mas ADR-085 continua com `Status: Implementado` e sua fórmula original no texto, sem nenhuma nota apontando que D3 foi substituída. Dois ADRs "vigentes" descrevem hoje a mesma grandeza de forma incompatível.

P2. **No caminho real do pool RCPSP (skill-05), a estrutura de dados para o ciclo de vida por instância existe, mas o custo nunca é calculado — os campos ficam mortos.**

`InstanciaRecurso` (`domain/models/canonical/_pool_recursos.py:221-232`) tem `custo_mob_instancia`, `custo_demob_instancia`, `semana_mobilizacao`, `semana_desmobilizacao`, `desmob_antecipada_aplicada` — a modelagem de dados está correta e alinhada com o ciclo de vida `mob→(idle|prod)→demob` de ambos os ADRs. Mas:

- `calcular_custo_instancia_composicional` (`_custo_diferenciado_permanencia.py:47-94`) **não tem parâmetro para custo de mobilização** — só recebe `c_demob_efetivo`.
- `_compute_instancia_lifecycle` (`_resource_instance_assignment.py:93-166`), que chama essa função, passa **`c_demob_efetivo=0.0` hardcoded**.
- `custo_mob_instancia` nunca é atribuído em lugar nenhum do código-fonte (confirmado por busca no repositório) — existe apenas na definição do modelo Pydantic e em leitura de relatório PDF legado.
- `custo_demob_instancia` é sempre gravado como `0.0` (`_resource_instance_build.py:167`).

Consequência: para qualquer projeto que use o pool RCPSP real, `total` do contrato de recurso nunca reflete mob/demob. Isso viola diretamente o próprio D4 do ADR-125 — "mob/demob precisam ser rastreados no total para... validação de que `C_pool ≤ total` (mob/demob não foram absorvidos indevidamente)" — porque, com o valor sempre zero, essa validação é vácua: `C_pool ≤ total` é sempre trivialmente verdadeira, não porque mob/demob foi corretamente contabilizado, mas porque nunca existiu no cálculo.

P3. **A implementação formalmente correta do ADR-125 existe, mas está isolada — nenhum caminho de produção a consome.**

`LifecycleEngine`/`CustoEquipeDecomposicao` (`domain/services/financial/equipe_custo_engine.py`) implementa `custo_produtivo`/`custo_pool` exatamente como especificado em ADR-125 D5. O próprio Definition of Done do ADR-125 já registra essa limitação: nenhum call site de precificação em produção hoje consome `custo_produtivo`/`custo_pool` diretamente. O engine roda para equipes diretas/indiretas fora do pool RCPSP, não para os contratos de recurso do pool.

P4. **O único lugar do sistema onde mob/demob efetivamente produz um número no resultado financeiro (`_mob.py`, skill-06 + `mob_scheduling.py`) é cego ao pool.**

Esse caminho:
- Não referencia `InstanciaRecurso`, `RecursoContrato`, `LifecycleEngine` nem qualquer conceito de pool.
- Infere janelas de mobilização a partir de datas agregadas do projeto inteiro (`infer_mob_windows`), não da janela real de cada instância de recurso.
- Herda o bug de granularidade descrito na revisão anterior deste ADR: ao computar o termo de alimentação/seguro de vida/cesta básica associado à permanência da equipe, usa um único par `(headcount agregado, prazo_meses do projeto)` em vez da permanência real por equipe — que, ironicamente, **já está disponível por instância** em `InstanciaRecurso.semana_mobilizacao`/`.semana_desmobilizacao` (P2), só que em um modelo de dados totalmente desconectado deste cálculo.

P5. **Síntese:** a hierarquia `C_prod ≤ C_pool ≤ total`, incluindo onde mob/demob se encaixam nela, está formalizada corretamente em texto (ADR-125) e implementada corretamente em um engine isolado (`equipe_custo_engine.py`) — mas não em nenhum caminho do pipeline que efetivamente processa o pool de recursos (skill-05), nem no único módulo que gera um número real de mob/demob no output financeiro (skill-06). Não há duplicidade de contagem — há ausência total de conexão entre três peças que deveriam ser uma só: a decisão arquitetural, a estrutura de dados do pool, e o cálculo que chega ao usuário final.

## Decisão

### D1 — Reconciliar formalmente ADR-085 e ADR-125

Adicionar nota de superseding parcial em ADR-085: sua fórmula D3 (mob/demob dentro de `custo(I_k)`) é substituída, quanto à posição de mob/demob na hierarquia, pela decisão do ADR-125 D1/D4 (mob/demob fora de `C_pool`, dentro de `total`). ADR-125 prevalece por ser a decisão mais recente, com racional de rejeição documentado para a alternativa equivalente (A2). Preservar a fórmula original de ADR-085 D3 como registro histórico — não reescrever o texto do ADR antigo, apenas anotar a superseding no cabeçalho (mesmo padrão já usado em ADR-080 → ADR-085, ver `INDEX.md`).

### D2 — Popular `custo_mob_instancia`/`custo_demob_instancia` no caminho real do pool (skill-05)

`calcular_custo_instancia_composicional` ganha parâmetro para custo de mobilização (hoje inexistente). `_compute_instancia_lifecycle` deixa de hardcodar `c_demob_efetivo=0.0` e passa a computar o valor real a partir de `semana_mobilizacao`/`semana_desmobilizacao` e das taxas de mob/demob do recurso, alimentando **apenas `total`** do contrato — nunca `C_pool`, per ADR-125 D1. Isso restaura a verificação `C_pool ≤ total` como uma validação real, não uma tautologia.

### D3 — Skill-06 (`_mob.py`) passa a derivar mob/demob do ciclo de vida real do pool, não de datas agregadas do projeto

Uma vez que D2 popule os campos por instância, `_mob.py`/`mob_scheduling.py` deixam de usar `infer_mob_windows` sobre datas do projeto como um todo e passam a derivar a janela de mobilização/desmobilização por equipe a partir de `InstanciaRecurso.semana_mobilizacao`/`.semana_desmobilizacao`. Isso fecha, como efeito colateral, o gap de granularidade por equipe identificado na revisão anterior deste ADR — sem introduzir uma segunda fonte de verdade (ex.: um campo `equipes_permanencia` de input manual): a fonte de verdade passa a ser o próprio ciclo de vida do pool, já calculado pela skill-05.

### D4 — Avaliar o papel de `equipe_custo_engine.py` após D2/D3

Se D2/D3 tornam o cálculo baseado em pool a fonte real de mob/demob para projetos com pool RCPSP formado, é preciso decidir se `LifecycleEngine`/`CustoEquipeDecomposicao` continua útil como caminho paralelo (para equipes diretas/indiretas fora de qualquer pool — ex. skill-05/07 sem pool formado) ou se deve ser reconciliado com D2. **Não decidir isso nesta ADR** — depende do levantamento de F1 (Plano de Implementação) sobre quais projetos/skills realmente não formam pool.

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Deixar ADR-085 e ADR-125 coexistindo sem reconciliação, documentando o conflito só nesta ADR | Perpetua a ambiguidade para quem ler ADR-085 isoladamente no futuro — a nota de superseding (D1) é custo baixo e evita repetir a investigação feita aqui |
| A2 | Corrigir apenas o cálculo de `_mob.py` (granularidade por equipe) sem tocar nos campos mortos do pool (D2) | Trataria o sintoma mais visível sem resolver a causa raiz — os campos do pool continuariam mortos, e qualquer consumidor futuro de `InstanciaRecurso.custo_mob_instancia`/`.custo_demob_instancia` (ex.: relatórios, cubo analítico) continuaria recebendo zero |
| A3 | Migrar todo o cálculo de mob/demob para dentro de `C_pool` (reverter para a formulação do ADR-085) | Contradiria a decisão já fundamentada do ADR-125 (mob/demob não escalam com `n_p`/`n_s`, são eventos de entrada/saída, corretamente tratados como DI de campo) — não há justificativa nova para reabrir essa decisão |
| A4 | Descontinuar `equipe_custo_engine.py` nesta ADR, já que nenhum call site o consome hoje | Prematuro sem o levantamento de F1 — pode haver um uso pretendido (equipes fora de pool) que só ainda não foi conectado, não que deva ser eliminado |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Um único modelo mental vigente | ADR-085 e ADR-125 deixam de contradizer-se silenciosamente; qualquer leitura futura de ambos chega à mesma conclusão |
| `total` do contrato de recurso passa a ser real | A validação `C_pool ≤ total` (D4 do ADR-125) volta a ter significado — hoje é sempre trivialmente verdadeira por mob/demob ser zero |
| Fecha o gap de granularidade por equipe sem nova fonte de verdade | D3 deriva a permanência por equipe do próprio ciclo de vida do pool (já calculado), em vez de exigir um input manual paralelo — mesmo princípio que motivou o NEP-043 (evitar duas fontes divergentes para o mesmo dado) |
| Clareza sobre o papel de `equipe_custo_engine.py` | D4 força uma decisão explícita (manter como caminho paralelo válido, ou reconciliar) em vez de deixá-lo como código morto/não referenciado indefinidamente |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Projetos com dados históricos calculados com mob/demob sempre zero terão `total` diferente após D2 | Esperado e correto — o valor anterior estava sistematicamente subestimado; comunicar como correção de bug, não mudança de comportamento neutra |
| D3 acopla `_mob.py` (skill-06) a uma saída de `InstanciaRecurso` (skill-05) que hoje ele não consome | Escopo de implementação inclui mapear exatamente a interface entre as duas skills antes de escrever código — não assumir que os dados já fluem prontos entre elas |
| Nenhum projeto de benchmark além do AGIS foi auditado para confirmar se depende do caminho `_mob.py` legado ou de config pré-agregada (ver ADR/revisão anterior) | Mantido como item do levantamento em F1 — não resolvido por esta ADR isoladamente |
| D4 pode revelar que `equipe_custo_engine.py` tem um propósito real não documentado, exigindo retrabalho do plano | F1 inclui levantamento desse ponto antes de qualquer decisão de descontinuação |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| **F1 — Levantamento** | Mapear quais skills/projetos formam pool RCPSP real vs. dependem de equipes diretas fora de pool; confirmar call sites (ou ausência deles) de `equipe_custo_engine.py`; confirmar quais benchmarks exercitam `_mob.py` legado vs. config pré-agregada | ✅ |
| **F2 — Reconciliação documental (D1)** | Nota de superseding parcial em ADR-085, referenciando esta ADR e ADR-125 | ✅ |
| **F3 — Popular custo do pool (D2)** | `calcular_custo_instancia_composicional` ganha parâmetro de mobilização; `_compute_instancia_lifecycle` computa valores reais em vez de `0.0` hardcoded; `total` do contrato passa a refletir mob/demob | ✅ |
| **F4 — Conectar skill-06 ao pool (D3)** | `_mob.py`/`mob_scheduling.py` derivam janelas de mob/demob de `InstanciaRecurso` em vez de `infer_mob_windows` sobre datas agregadas | ⬜ _(deferida — ver nota de escopo)_ |
| **F5 — Decisão sobre `equipe_custo_engine.py` (D4)** | Com base em F1, decidir manter como caminho paralelo ou reconciliar com F3 | ⬜ _(deferida — ver nota de escopo)_ |
| **F6 — Regressão** | Teste que confirma `C_pool ≤ total` como validação real (não vácua) após F3; teste de regressão no AGIS reproduzindo a granularidade por equipe via F4 | ⚠️ _(parcial — C_pool ≤ total ✅; granularidade AGIS depende de F4)_ |

## Definition of Done

### Fase 1
- [x] Levantamento documentado: confirmado que `equipe_custo_engine.py`/`LifecycleEngine` já implementa corretamente a hierarquia do ADR-125 (mob/demob somados só em `total`, nunca em `custo_pool`), mas nenhum call site de produção o consome — é código duplicado e desconectado do pipeline real do pool (skill-05). `_mob.py` (skill-06) não referencia `InstanciaRecurso`/pool em nenhum ponto — cego à granularidade por equipe. Detalhado no Contexto (P1-P5) desta ADR.

### Fase 2
- [x] ADR-085 atualizado com nota de superseding parcial (D3, quanto à posição de mob/demob), apontando para ADR-125 e esta ADR

### Fase 3
- [x] `calcular_custo_instancia_composicional` aceita `c_mob_efetivo` como parâmetro (retrocompatível, default `0.0`)
- [x] `_compute_instancia_lifecycle` computa `custo_mob_instancia`/`custo_demob_instancia` reais — mob sempre que a instância é utilizada; demob apenas quando a desmob antecipada é efetivamente aplicada — em vez de `0.0` hardcoded
- [x] `_build_instancia_slot` popula `InstanciaRecurso.custo_mob_instancia` (antes nunca atribuído em lugar nenhum do código)
- [x] `_sum_inst_categories` inclui `custo_mob_instancia` na categoria EQ (mantendo o invariante categorial `Σ custo_inst_cat == custo_total_particionado`)
- [x] Cubo de pool (ADR-086, `cubo_pool_builder.py`): H1 (`Σ células == custo_total_contrato`) reconciliado para `Σ células == custo_total_contrato − (mob+demob)` — mob/demob são custo de evento, sem célula própria por semana; `validar_invariantes_cubo_pool`/`_check_h1` ganham parâmetro `instancias` (opcional, retrocompatível) para calcular o desconto
- [x] Testes cobrindo o cálculo real (unitário em `calcular_custo_instancia_composicional`, em `_compute_instancia_lifecycle`, e pipeline-level confirmando que `custo_instancia_total`/`custo_total_contrato` refletem os valores)

### Fase 4 — Deferida
- [ ] `_mob.py`/`mob_scheduling.py` consomem `InstanciaRecurso.semana_mobilizacao`/`.semana_desmobilizacao` em vez de `infer_mob_windows`
- [ ] Teste de regressão no AGIS reproduzindo a tabela de 7 equipes com permanências distintas (1,3–12,0 meses) via dados do pool, não via input manual
- **Motivo do adiamento:** exige desenhar a interface entre skill-05 (produtor de `InstanciaRecurso`) e skill-06 (consumidor em `_mob.py`), que hoje não existe — arriscado encaixar na mesma mudança que corrigiu os campos mortos do pool (F3). Também não pode ser validado contra o AGIS diretamente, pois o benchmark AGIS contorna `_mob.py` via config pré-agregada (P4) — exigiria uma fixture sintética nova.

### Fase 5 — Deferida
- [ ] Decisão documentada sobre `equipe_custo_engine.py` (manter/reconciliar), com justificativa baseada em F1
- **Motivo do adiamento:** F1 já confirmou que o engine está correto porém desconectado (não é código morto por engano — foi escrito para eventualmente unificar skill-05/07, ADR-106). Decidir seu destino definitivo é mais seguro após F4 estar implementada, já que F4 pode mudar o que faz sentido consolidar.

### Fase 6
- [x] Teste validando `C_pool ≤ total` com mob/demob real (não sempre zero) em pelo menos um projeto de benchmark (`test_c_pool_menor_que_total_quando_ha_mobilizacao`)
- [ ] Teste de regressão no AGIS reproduzindo a granularidade por equipe — depende de F4

---

## Relacionados

- ADR-085 — Custo Instancial Composicional Temporal (formulação original; D3 reconciliada por esta ADR quanto à posição de mob/demob)
- ADR-125 — Hierarquia de Custo C_prod/C_pool/Contrato (decisão vigente sobre mob/demob como indireto; ponto de partida desta ADR)
- ADR-105 — Mobilização e Desmobilização de Mão-de-Obra e Equipamentos (política integrada que `_mob.py` implementa)
- ADR-106 — LifecycleEngine (origem de `equipe_custo_engine.py`, avaliado em D4)
- ADR-104 — Centralização do Cálculo de Custos (EquipeDireta)
- NEP-043 — Reconciliação C_r: Custo Operacional de Equipe vs. PU de Catálogo (mesmo princípio de D3: evitar duas fontes de verdade divergentes para o mesmo dado)
- `docs/product/3-reference_files/prompts/camilla_agis.txt` — processo manual de referência que originalmente expôs o gap de granularidade por equipe (P4)

**Nota de revisão:** esta ADR substitui integralmente uma versão anterior sob o mesmo número, que tratava apenas do sintoma de granularidade por equipe em `_mob.py` sem a investigação da causa raiz arquitetural (contradição ADR-085/ADR-125 e campos mortos no pool). O escopo foi ampliado após investigação adicional na mesma sessão de trabalho.
