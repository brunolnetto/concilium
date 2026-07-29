# ADR-170 — Alojamento como Benefício Catalogado (BEN-ALOJAMENTO)

**Status:** ✅ Implementado
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-165 (Catálogo de Treinamentos, Exames, EPIs e Benefícios — categoria BENEFICIO), ADR-168 (Alojamento Bottom-Up por Número de Casas — precedente que esta ADR estende)

---

## Contexto

### Problema

P1. A ADR-168 implementou o custo de "Alojamento" (categoria ADM) como um cálculo bottom-up (`num_casas = ceil(headcount / capacidade)`), mas a capacidade (3 quartos × 2 pessoas) e o valor de aluguel (R$4.000/mês) ficaram **hardcoded** no código, só configuráveis via override de perfil (`cat["alojamento"]`/`regra["alojamento"]`) — desconectados do catálogo, ao contrário dos demais benefícios (café/almoço/vale-alimentação/cesta-básica/seguro-vida, ADR-165), que já são insumos `BENEFICIO` reais, versionados e auditáveis.

P2. O usuário observou: "Alojamento se enquadra em benefícios" — mesma categoria conceitual dos demais itens de bem-estar do trabalhador, só que compartilhado (uma casa serve várias pessoas) em vez de um custo direto por pessoa.

## Decisão

D1. Novo insumo `BEN-ALOJAMENTO` (tipo `BENEFICIO`) criado em `mendeslobo` e `rfi-r02`: R$4.000/mês (por casa), `periodicidade_beneficio: "mensal"`, mais os dois campos novos abaixo — mesma governança rascunho→merge/quatro-olhos das ADRs anteriores (`scripts/catalog/adr170_criar_ben_alojamento.py`).

D2. `AtributosInsumo` ganha `quartos_por_casa`/`pessoas_por_quarto` (novos, só válidos para `tipo=BENEFICIO`, mesma família de validação de `periodicidade_beneficio`/`aplicavel_tipo_contrato`) — capturam a dimensão de **capacidade compartilhada** que os demais benefícios (custo direto por pessoa) não têm. JSON Schema (`insumo.schema.json#/$defs/atributosBeneficio`) atualizado em conjunto, para não repetir o gap encontrado na ADR-167 (schema desatualizado em relação ao Pydantic).

D3. **Decisão do usuário**: o custo de Alojamento continua aparecendo na categoria **ADM** do relatório de indiretos (não migra para o bottom-up de benefícios do MOB, onde vivem café/almoço/etc.) — só a *fonte* de capacidade/valor muda. Nova função `_alojamento_config_do_catalogo(catalogo)` lê `BEN-ALOJAMENTO` e retorna a config equivalente a `alojamento_config`; `_composicao_default_por_categoria("ADM")` combina as três fontes com prioridade **perfil (`cat`/`regra["alojamento"]`) > catálogo (`BEN-ALOJAMENTO`) > hardcoded** (3 quartos, 2 pessoas, R$4.000 — usado só se nem perfil nem catálogo tiverem o dado).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Mover Alojamento para o bottom-up de benefícios do MOB, junto dos demais | Rejeitada por decisão explícita do usuário — o relatório de indiretos continua mostrando esse custo em ADM. |
| A2 | Generalizar `_custo_mensal_beneficio_por_funcao` (ADR-166 D3) para suportar capacidade compartilhada, tratando Alojamento como só mais um item do loop por função | Rejeitada — matematicamente incompatível: dividir por capacidade *por função* (em vez de pelo headcount total do grupo) superestimaria o número de casas sempre que o headcount de uma função individual for menor que a capacidade de uma casa. O cálculo de Alojamento precisa operar sobre o headcount agregado, não por função — por isso continua uma função dedicada (`_custo_alojamento_bottom_up`, ADR-168), só trocando a *fonte* dos parâmetros. |
| A3 | Um único campo `capacidade_pessoas` em vez de `quartos_por_casa`/`pessoas_por_quarto` separados | Rejeitada — manter os dois campos separados preserva a legibilidade do dado real no catálogo (alguém lendo o insumo vê "3 quartos × 2 pessoas", não um número abstrato "6"); a derivação (`quartos × pessoas`) é trivial no código que consome. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Alojamento ganha trilha de auditoria | Preço e capacidade agora têm histórico de preço, quatro-olhos e SCD Type 2 — mesma disciplina dos demais benefícios, em vez de um número de bolso no código-fonte. |
| Consistência conceitual do catálogo | Todos os itens de bem-estar do trabalhador (EPI/treinamento/exame/benefício, ADR-165) agora vivem no mesmo lugar — Alojamento deixa de ser um caso especial só por ser compartilhado. |
| Degradação segura em 3 camadas | Perfil > catálogo > hardcoded — nenhum caso existente (sem `BEN-ALOJAMENTO` no catálogo, sem override de perfil) muda de comportamento. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Duas "fontes de configuração" para o mesmo dado (perfil e catálogo) podem divergir silenciosamente | Aceito — mesmo padrão de prioridade já usado em outras partes do sistema (override explícito sempre vence dado de referência); documentado explicitamente na prioridade dos 3 níveis. |
| Alojamento continua sendo o único BENEFICIO com dimensão de capacidade compartilhada — próximo item parecido exigiria o mesmo par de campos | Aceito — `quartos_por_casa`/`pessoas_por_quarto` são genéricos o bastante (não amarrados ao nome "alojamento") para reuso direto por outro benefício compartilhado futuro, sem mudança de schema. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `AtributosInsumo.quartos_por_casa`/`pessoas_por_quarto` + validação + JSON Schema | ✅ Implementado |
| F2 | `BEN-ALOJAMENTO` criado em `mendeslobo` e `rfi-r02` | ✅ Implementado |
| F3 | `_alojamento_config_do_catalogo` + prioridade perfil > catálogo > hardcoded em `_composicao_default_por_categoria("ADM")` | ✅ Implementado |

## Definition of Done

- [x] Teste cobrindo: campos novos só válidos em `BENEFICIO` (`VAL-INSUMO-BENEFICIO-01`); valores não-positivos rejeitados; default `None`
- [x] `BEN-ALOJAMENTO` criado nos dois catálogos via rascunho→merge/quatro-olhos; `auditar_catalogo` SAUDAVEL
- [x] Teste cobrindo: sem perfil/catálogo usa hardcoded; com catálogo usa dado real; perfil sobrepõe catálogo; catálogo sem `BEN-ALOJAMENTO` (ou descontinuado) cai no hardcoded
- [x] Teste de integração via `_resolve_categoria_comp` com catálogo real contendo `BEN-ALOJAMENTO`
- [x] Suíte completa verde (só as falhas pré-existentes já confirmadas: golden test e o teste flaky de diff de snapshot)

---

## Relacionados

- ADR-165 — Catálogo de Treinamentos, Exames, EPIs e Benefícios de Mão de Obra (categoria `BENEFICIO` estendida aqui com capacidade compartilhada)
- ADR-168 — Alojamento (ADM) Bottom-Up por Número de Casas (cálculo preservado; só a fonte dos parâmetros muda)
