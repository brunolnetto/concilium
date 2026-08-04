# ADR-178 — Gate de Plausibilidade Pré-Merge de Catálogo

**Status:** Proposta
**Data:** 2026-08-04
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-120 (Regra dos Quatro Olhos), ADR-130 (Grafo de Sinergia), ADR-139 (Materiais Consumíveis), ADR-145 (Unificação do Caminho de Escrita de Preço), ADR-150 (Rascunho de Catálogo por Projeto), ADR-177 (`mesclar_catalogo` Durabilidade + Governança)

---

## Contexto

### Problema

P1. **Nenhum dos três caminhos de consolidação de catálogo roda auditoria de plausibilidade hoje.** `mesclar_catalogo` (`_impl_mesclar_catalogo`, `_catalogo_tools_helpers_b.py:344`), `aprovar_merge_catalogo` (`catalogo.py:637-756`, gate único é `assert_pode_aprovar`, `catalog_draft_lifecycle.py:143-162`) e `catalog promote` (`_commands_manage_helpers_b.py:150`) verificam permissão/quatro-olhos (ADR-120/145/150/177), mas nenhum chama `verificar_plausibilidade`/`verificar_integridade`. `auditar_catalogo` (`catalogo.py:106-145`) existe como tool MCP separada, disparada manualmente — hoje é o único jeito de saber se um catálogo tem dado implausível, e nada impede que esse dado atravesse um merge sem revisão.

P2. **O próprio checker de plausibilidade tinha um bug real, corrigido como pré-requisito desta ADR** (issue aberta nesta sessão, ver Nota de Implementação): `_pc_mo_salario_minimo` e `_pc_mo_zscore` (`_plausibility_checks.py`) ignoravam o campo `unidade` do insumo (`"h"` vs `"mes"`) e dividiam por `horas_mes` mesmo quando `preco_unitario` já era taxa horária — gerando 33 falsos "ERRO de salário abaixo do mínimo" no catálogo `mendeslobo` (e 1 no `rfi-r02`) sobre insumos com preço correto (ex.: `AGIS-FN-AJUD`, `unidade: "h"`, `preco_unitario: 19.45`, com nota explícita `"Taxa horária já inclui encargos"`). O motor de cálculo de PU (`pu_calculator.py:281-302`) já tratava `unidade` corretamente — o bug estava isolado no auditor, sem cobertura de teste. Isso importa para esta ADR porque um gate automático **bloqueante** construído sobre um checker com falso-positivo sistemático teria travado merges legítimos.

P3. **Merge é por registro completo, não por campo — risco de apagar dado quando a cobertura é desigual entre catálogos.** Levantamento direto nos dados: `grafo_sinergia` (ADR-130) está populado em 67/67 (100%) produções do `rfi-r02`, mas só 8/169 (4,7%) do `mendeslobo`; `origem_material`/`disponibilidade` (ADR-139) tem 63/593 insumos populados no `mendeslobo` vs. 44/218 no `rfi-r02`. Nenhum dos dois catálogos é estritamente mais completo — cada um tem lacunas que o outro cobre. Se o merge de uma colisão (mesmo código em ambos os lados) escolher um registro "vencedor" por inteiro (o padrão atual de `aplicar_merge`/`gerar_relatorios`), o campo populado do lado perdedor é descartado silenciosamente — sem erro, sem aviso, porque campo ausente não é anomalia de plausibilidade.

P4. **25 duplicatas de mão-de-obra no `mendeslobo` não são bloqueadas, e um merge por código as perpetua.** `_pc_mo_duplicatas` já detecta (severidade `AVISO`) o mesmo cargo cadastrado sob 2-3 códigos (`P00xx`/`MO-P00xx`/`MO-<slug>`) com mesma descrição e preço — mas como o merge opera por identidade de código, essas duplicatas atravessam o merge como itens distintos, e qualquer composição que referencie um código diferente do "escolhido" pelo merge para o mesmo cargo físico passa a divergir sem detecção. `cure_plausibility.py` já sabe consolidar isso (`cure_duplicatas`), mas roda fora do fluxo de merge/aprovação, escrevendo direto no bundle.

## Decisão

D1. **`mesclar_catalogo(dry_run=True)` e a fase de revisão de `aprovar_merge_catalogo` passam a rodar `verificar_plausibilidade` + `verificar_integridade` sobre o resultado projetado do merge** (o bundle combinado do preview, não os catálogos originais isolados) — porque uma duplicata ou colisão pode só emergir da combinação dos dois lados, não existindo em nenhum catálogo isoladamente. O resultado é anexado ao preview persistido (`merges_pendentes/{merge_id}.json`, mecanismo já existente da ADR-177) sob uma chave nova `plausibilidade_pre_merge`.

D2. **Anomalias de severidade `ERRO` bloqueiam a aplicação (`dry_run=False`) por padrão.** Para destravar mesmo assim, a chamada aceita `ignorar_erros_plausibilidade: bool = False` — se `True`, exige `justificativa` (parâmetro já existente na ADR-177, hoje opcional, passa a ser obrigatório neste caso) e a lista de erros ignorados é persistida no `CatalogDiff` (D4 da ADR-177), nunca descartada silenciosamente.

D3. **Anomalias de severidade `AVISO` não bloqueiam, mas ficam obrigatoriamente visíveis no payload de `dry_run=True`/na tela de revisão do rascunho** — o segundo ator do quatro-olhos (ADR-120) passa a ver os avisos de plausibilidade como parte do que está aprovando, em vez de precisar rodar `auditar_catalogo` manualmente à parte.

D4. **Merge de colisão passa a ser campo-a-campo para um subconjunto explícito de campos "enriquecidos"**: `grafo_sinergia`, `origem_material`, `disponibilidade`. Regra: se o registro perdedor da colisão tem valor não-nulo nesse campo e o vencedor não, o valor não-nulo é copiado para o registro final antes de persistir — independente de qual lado "venceu" o resto da colisão. Escopo deliberadamente restrito a esses 3 campos (os únicos com cobertura comprovadamente desigual entre `mendeslobo`/`rfi-r02` hoje); não generaliza para todo o schema de `Insumo`/`Producao`.

D5. **Duplicata de mão-de-obra (`_pc_mo_duplicatas`) passa a ter severidade `ERRO` especificamente dentro do contexto de pré-merge** (nova função `verificar_plausibilidade_pre_merge()`, que chama `verificar_plausibilidade()` e reclassifica só essa categoria) — sem alterar a severidade `AVISO` do modo `plausibilidade` standalone usado por `auditar_catalogo` fora do fluxo de merge. Motivo: fora do merge, duplicata é um problema de qualidade de dado a corrigir quando conveniente; dentro do merge, é um problema estrutural que o próprio merge vai piorar (perpetuar 2-3 códigos para o mesmo cargo no catálogo consolidado).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Auditar os dois catálogos separadamente antes do merge, sem checar o resultado combinado | Rejeitada (P4) — não captura duplicata/colisão que só existe na combinação dos dois lados. |
| A2 | Bloquear aplicação em qualquer `AVISO`, não só `ERRO` | Rejeitada — geraria fricção excessiva; outlier estatístico (z-score) não é necessariamente erro de dado, e hoje `mendeslobo` tem 30 avisos legítimos que não impedem uso do catálogo em produção. |
| A3 | Fundir os 25 duplicados automaticamente via `cure_plausibility.cure_duplicatas` antes de qualquer merge, sem revisão humana | Rejeitada — risco de fundir dois cargos que só parecem iguais (mesma descrição normalizada + preço) mas são intencionalmente distintos; fica como sugestão de correção revisável, não ação automática silenciosa. |
| A4 | Generalizar o merge campo-a-campo (D4) para todo o schema de `Insumo`/`Producao` | Rejeitada por ora — desproporcional; só os 3 campos com desigualdade de cobertura comprovada nos dados reais hoje. Revisar se outros campos mostrarem o mesmo padrão. |
| A5 | Rotear o gate pelo sistema de `_deltas` de rascunho (ADR-145/163/164) em vez de anexar ao preview da ADR-177 | Rejeitada — mesmo argumento da ADR-177 (P4 daquela ADR): o sistema de deltas não cobre merge de bundle inteiro; reusar o preview+TTL já existente é mais barato que estender deltas primeiro. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Fecha o gap real encontrado nesta sessão | Hoje é possível mesclar catálogos com erro crítico de plausibilidade sem nenhum bloqueio; D1/D2 fecham isso. |
| Não perde dado de cobertura desigual | D4 evita que o merge escolha um catálogo "vencedor" e descarte silenciosamente `grafo_sinergia`/`origem_material` que só o lado perdedor tinha. |
| Duplicata para de se perpetuar | D5 força resolução de duplicata de MO antes de consolidar catálogos, em vez de arrastar 2-3 códigos para o mesmo cargo no catálogo final. |
| Reaproveita mecanismo existente | D1/D2/D3 estendem o preview+TTL+quatro-olhos da ADR-177 em vez de inventar um novo gate paralelo. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `ignorar_erros_plausibilidade=True` pode se tornar o caminho padrão se a auditoria gerar ruído | Exigir `justificativa` obrigatória e persistir no `CatalogDiff` cria trilha auditável; se o padrão for abusado, fica visível em auditoria posterior. |
| D4 (merge campo-a-campo) tem escopo restrito a 3 campos — outros campos com o mesmo problema não são cobertos | Aceito por ora (A4 rejeitada); documentado para revisão se outro campo mostrar cobertura desigual comprovada. |
| D5 cria uma segunda noção de severidade para a mesma anomalia (`AVISO` fora do merge, `ERRO` dentro) — pode confundir quem só conhece o modo `auditar_catalogo` standalone | Documentar explicitamente na resposta da tool qual contexto gerou a severidade (`"contexto": "pre_merge"` no `detalhe` da anomalia). |
| Checker de plausibilidade pode ter outros bugs além do já corrigido (P2) — gate bloqueante herda qualquer falso-positivo futuro | Cobertura de teste do bug corrigido nesta sessão (`unidade="h"`) documentada; recomenda-se auditoria de cobertura dos demais `_pc_*` antes de tornar D2 bloqueante em produção (fora de escopo desta ADR, ver Relacionados). |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F0 | Fix do bug de `unidade` em `_pc_mo_salario_minimo`/`_pc_mo_zscore` + testes de regressão (pré-requisito, P2) | ✅ |
| F1 | D1 — `verificar_plausibilidade_pre_merge()` sobre o bundle projetado do preview, anexado a `merges_pendentes/{merge_id}.json` | ⬜ |
| F2 | D2 — bloqueio em `ERRO` + `ignorar_erros_plausibilidade`/`justificativa` obrigatória + persistência no `CatalogDiff` | ⬜ |
| F3 | D3 — avisos expostos no payload de `dry_run=True` e na revisão de `aprovar_merge_catalogo` | ⬜ |
| F4 | D4 — merge campo-a-campo para `grafo_sinergia`/`origem_material`/`disponibilidade` em `aplicar_merge` | ⬜ |
| F5 | D5 — `verificar_plausibilidade_pre_merge()` reclassifica `_pc_mo_duplicatas` para `ERRO` só neste contexto | ⬜ |

## Definition of Done

### Fase 0
- [x] `_mo_preco_hora`/`_preco_hora` respeitam `unidade` em `_plausibility_checks.py` e `cure_plausibility.py`
- [x] Teste de regressão cobrindo insumo `unidade="h"` plausível (não falso-positivo) e genuinamente abaixo do mínimo (ainda detectado)
- [x] Re-auditoria confirmada: `mendeslobo` 35→2 erros reais, `rfi-r02` 1→0

### Fase 1-5
- [ ] `mesclar_catalogo(dry_run=True)` retorna `plausibilidade_pre_merge` no payload
- [ ] `dry_run=False` com erro crítico não ignorado retorna erro sem aplicar
- [ ] `dry_run=False` com `ignorar_erros_plausibilidade=True` sem `justificativa` retorna erro de validação
- [ ] Teste: colisão onde só o lado perdedor tem `grafo_sinergia` não-nulo preserva o valor no registro final
- [ ] Teste: duplicata de MO detectada no bundle combinado do preview aparece como `ERRO` em `plausibilidade_pre_merge`, mas continua `AVISO` em `auditar_catalogo(modo="plausibilidade")` fora do contexto de merge

## Nota de Implementação

A Fase 0 (fix do bug de `unidade`) foi implementada e verificada nesta sessão, antes da redação desta ADR — é pré-requisito lógico (P2), não parte do gate em si. Achados que motivaram esta ADR:

- Re-auditoria pós-fix do `mendeslobo`: 2 erros reais restantes — `MO-P0001` (preço 200,0 vs. referência RFI 1830,51, unidade `mes` — erro de lançamento genuíno) e `MO-OPERADOR-DE-MOTOSCRA` (α=2,777 fora de `[1.0, 2.5]`, já auto-corrigível por `cure_plausibility.cure_erros_fisicos`). `rfi-r02`: 0 erros.
- `P0058`/`MO-SALA-TEC` ("Sala Técnica", R$24.720 e R$12.000/mês) — investigado: não referenciado em nenhuma composição/CPU do `mendeslobo` hoje (dado órfão, sem impacto em PU calculado). É o mesmo par AGIS-import-com-encargos-embutidos (`P0058`, α implícito 2,06) vs. negociado-CLT-normalizado-ADR-009 (`MO-SALA-TEC`, salário-base sem encargos) que já existe para outros 25 cargos — mas o dedup atual (`_build_dup_map`, chave `(descrição, preço)`) não captura este par porque os preços diferem (encargos embutidos vs. não). Descrição "Sala Técnica" para um cargo é ambígua (`classe_compartilhamento.capacidade_cobertura=10`, mesmo padrão usado por `MO-GERENTE`/`MO-ADM-PJ` — sugere papel de suporte técnico compartilhado entre até 10 frentes, não uma sala física) — decisão de renomeação/consolidação fica para revisão humana, não é bloqueante por estar órfão.
- 25 duplicatas detectadas por `_pc_mo_duplicatas` no `mendeslobo`, 0 no `rfi-r02`.
- Cobertura desigual confirmada nos dados reais (base da D4): `grafo_sinergia` 67/67 no `rfi-r02` vs. 8/169 no `mendeslobo`; `origem_material` 63/593 no `mendeslobo` vs. 44/218 no `rfi-r02`; `disponibilidade` 0/0 nos dois (gap total, não coberto por nenhum catálogo — fora de escopo desta ADR, é lacuna de dado em ambos os lados, não risco de merge).

---

## Relacionados

- ADR-120 — Regra dos Quatro Olhos (reusada em D3)
- ADR-130 — Grafo de Sinergia (campo coberto por D4; achado de cobertura 8/169 no `mendeslobo` corrige o status "sem dados" do doc original da ADR-130, F4)
- ADR-139 — Materiais Consumíveis (campos cobertos por D4)
- ADR-145 — Unificação do Caminho de Escrita de Preço no Catálogo Mestre
- ADR-150 — Rascunho de Catálogo por Projeto
- ADR-177 — `mesclar_catalogo` Durabilidade + Governança (preview+TTL+quatro-olhos reaproveitado por D1/D2/D3)
- ADR-179 — Similaridade Determinística de Insumos para Detecção de Duplicatas (upgrade concreto de `_pc_mo_duplicatas`, o motor natural para D5 quando F1-F5 desta ADR forem implementadas; revisa a contagem "25 duplicatas" citada em P4/Nota de Implementação — o motor de similaridade achou muitas mais)
- Achado desta sessão — bug de `unidade` em `_pc_mo_salario_minimo`/`_pc_mo_zscore` (pré-requisito P2, Fase 0)
