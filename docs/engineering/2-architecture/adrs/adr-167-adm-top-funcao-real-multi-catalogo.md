# ADR-167 — ADM/TOP com Função Real + Paridade de Catálogo (mendeslobo × rfi-r02)

**Status:** ✅ Implementado (fases ADM/TOP) — Alojamento implementado na **ADR-168**; LAB implementado na **ADR-169**
**Data:** 2026-07-29
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-163/164 (CRUD/Batch de Insumo), ADR-165 (Catálogo de Treinamentos, Exames, EPIs e Benefícios de MO), ADR-166 (Wiring de Indiretos + Mapeamento Função→Item)

---

## Contexto

### Problema

P1. Auditoria do pipeline de indiretos (pós-ADR-166) encontrou o mesmo padrão de "verba lump hardcoded" em outras categorias além de QSMS/MOB: `_composicao_default_por_categoria` (`_dimensionamento.py`) tem ADM ("Coordenador" R$12.500/mês + "Alojamento" R$3.500/mês) e TOP ("Topógrafo" R$9.216/mês) como números fixos no código-fonte, nunca substituídos por preço real de catálogo.

P2. Causa raiz identificada: os itens de mão de obra desses defaults usam a chave `"funcao"` (texto solto, ex.: `"Coordenador"`) em vez de `"funcao_id"` — `_bcfd_enrich_mo_itens` (`_dimensionamento.py`) só enriquece com preço real do catálogo itens que tenham `funcao_id` **e** não tenham `custo_mensal` já preenchido. Como os defaults já vêm com `custo_mensal` fixo e sem `funcao_id`, o enriquecimento nunca dispara — mesmo com `repo`/`catalogo` disponíveis na chamada.

P3. `MO-TOPOGRAFO` já existe em `mendeslobo` (`P0057`, R$18.000/mês) e em `rfi-r02` (`P0057`, R$17.000/mês) — ambos bem diferentes do lump de R$9.216/mês. Não existe, porém, nenhuma função "Coordenador" em nenhum dos dois catálogos — precisa ser criada.

P4. O usuário decidiu trabalhar também com o catálogo `rfi-r02` (contexto `mendeslobo-rfi`) nesta sessão, e pediu que os dados novos desta sessão (ADR-165: 34 itens RH; ADR-166: mapeamento função→item) também estivessem presentes lá — até então só existiam em `mendeslobo`.

### Achado: JSON Schema de `Insumo` nunca foi atualizado pela ADR-165

Replicar os itens RH em `rfi-r02` expôs um gap que passou despercebido em `mendeslobo`: `config/schemas/catalog/common.schema.json#/$defs/tipoInsumo` (enum usado por `concilium catalog validate`) ainda só listava os 4 tipos antigos — a ADR-165 estendeu o `Literal` Pydantic (`TipoInsumo`, `domain/models/catalog/catalogo.py`) mas nunca o JSON Schema paralelo usado pela validação de CLI. Só foi descoberto agora porque `test_catalog_schema_rfi_r02.py::test_insumos_reais_sem_erros` itera **todos** os arquivos reais de insumo contra o schema — não existe um teste equivalente exaustivo para `mendeslobo`, então o mesmo gap ali segue silencioso até este mesmo teste (ou um análogo) existir para esse catálogo. Corrigido nesta ADR: `tipoInsumo` ganha os 3 valores novos; `insumo.schema.json` ganha `$defs`/`if-then` para `atributosTreinamento`/`atributosExame`/`atributosBeneficio` (espelhando os campos do Pydantic `AtributosInsumo`) e `atributosMaterial` ganha `vida_util_dias`/`funcoes_aplicaveis` (EPI).

### Achado: `rfi-r02` tem roster próprio, menor e sem duplicação de código

`rfi-r02` tem 82 códigos `MAO_OBRA`, todos no formato `P0xxx` **bare** — sem os aliases `MO-*`/`AGIS-FN-*`/`SV-*-D/N` que existem em `mendeslobo` (achado da ADR-163/166). Isso simplifica o remapeamento função→item para este catálogo (sem etapa de agrupamento por alias), mas também significa que nem todo código usado no mapeamento de `mendeslobo` existe em `rfi-r02` — ex.: `P0083` (Soldador) não existe em `rfi-r02`, então o grupo "esmeril" (`EPI-PROTETOR-FACIAL`) fica só com mecânico/aux. mecânico/borracheiro nesse catálogo.

## Decisão

D1. Novo cargo `P0092` "Coordenador" — PJ, R$12.500/mês (mesmo valor do lump antigo, por decisão do usuário), mesma convenção de campo já usada por `MO-ADM-PJ`/`MO-TOPOGRAFO` (`categoria_sindical: "pj_CE"`, `metodo_custo_total: "custo_total_ja_incluido"`, `taxa_encargos_pct: 0.0`). Código `P0092` escolhido por ser o menor número livre em **ambos** os catálogos (`mendeslobo` vai até `P0089`/`SV-*`; `rfi-r02` até `P0093`, com `P0092` livre nos dois) — mesmo `funcao_id` funciona nos dois contextos sem ambiguidade. Criado via `scripts/catalog/adr167_criar_coordenador.py` (rascunho→merge/quatro-olhos, ADR-120) em `mendeslobo` e `mendeslobo-rfi` (rfi-r02).

D2. Os 34 itens RH da ADR-165 (10 EPI + 9 TREINAMENTO + 9 EXAME + 6 BENEFICIO) replicados em `rfi-r02` — `scripts/catalog/adr165_carga_inicial_rh.py` generalizado com parâmetro `--contexto` (default `mendeslobo`, retrocompatível) em vez de contexto hardcoded.

D3. Mapeamento função→item da ADR-166 D4 reaplicado sobre o roster próprio de `rfi-r02` (script novo, `scripts/catalog/adr167_mapear_funcoes_rfi_r02.py` — não reaproveita o agrupamento por alias da ADR-166, que não se aplica aqui): mesmos 7 grupos semânticos (máquinas pesadas, motosserra/motopoda, trânsito, químicos, altura, esmeril, NR-22 sem função), com os códigos `P0xxx` próprios de `rfi-r02`.

D4. `_composicao_default_por_categoria("ADM"/"TOP")` ganha `funcao_id` real (`P0092`/`P0057`) nos itens de mão de obra, no lugar da chave `"funcao"` solta. O valor hardcoded antigo (R$12.500/R$9.216) passa de `custo_mensal` para `valor_mensal` — usado por `_parse_component` só como **fallback**, quando `_bcfd_enrich_mo_itens` não conseguir resolver o `funcao_id` no catálogo (mesma degradação segura da ADR-166 D2/D3). O `custo_fixo_mensal` explícito no componente `mao_de_obra` foi removido de propósito — `_parse_component` agora recalcula a partir do item, o que só funciona se nenhum valor pré-agregado sobrescrever o dado item-a-item.

D5. `config/schemas/catalog/common.schema.json#/$defs/tipoInsumo` estendido com `TREINAMENTO`/`EXAME`/`BENEFICIO` (achado — nunca foi atualizado pela ADR-165); `insumo.schema.json` ganha `$defs` `atributosTreinamento`/`atributosExame`/`atributosBeneficio` + branches `if/then` correspondentes, e `atributosMaterial` ganha `vida_util_dias`/`funcoes_aplicaveis` (para EPI).

D6. **Fora de escopo desta ADR, por decisão explícita do usuário** ("depois corrigir LAB e alojamento respectivamente"): a verba "Alojamento" (ADM, R$3.500/mês) e a verba LAB ("Ensaios laboratoriais", R$4.000/mês) continuam hardcoded — nenhum dos dois tem hoje um tipo de insumo catalogável equivalente (não são cargo de mão de obra). **Atualização**: "Alojamento" foi implementado na ADR-168 (bottom-up por número de casas); LAB foi implementado na ADR-169 (condicional a TERRAPLENAGEM/PAVIMENTACAO — valor em si permanece R$4.000/mês, sem composição por item de equipamento).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Mapear "Coordenador" para uma função já existente (ex.: `Gerente de Contrato Sênior`, `Encarregado Geral Sênior`) | Rejeitada pelo usuário — nenhuma função existente representa semanticamente um "Coordenador"; decisão foi criar um cargo novo dedicado. |
| A2 | Um código diferente por catálogo para "Coordenador" (ex.: `MO-COORDENADOR` em mendeslobo, `P0092` em rfi-r02) | Rejeitada — usar o mesmo `funcao_id` nos dois catálogos evita que o fallback do indireto precise saber em qual catálogo está rodando; escolha de um número livre em ambos resolve isso sem lógica condicional. |
| A3 | Reaproveitar o agrupamento por alias da ADR-166 para o mapeamento de `rfi-r02` | Rejeitada — `rfi-r02` não tem aliases de código (só `P0xxx` bare); a etapa de normalização/agrupamento da ADR-166 seria trabalho morto. Script dedicado, mais simples, usa os códigos diretamente. |
| A4 | Já corrigir também LAB e "Alojamento" nesta ADR | Rejeitada por decisão explícita do usuário — ficam para uma fase seguinte, dado que exigem um tipo de insumo novo (não são cargo de MO). |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| ADM/TOP deixam de ser number de bolso quando o catálogo tem o cargo | TOP passa de R$9.216/mês fixo para R$17.000-18.000/mês real (mendeslobo/rfi-r02); ADM (Coordenador) passa a refletir o valor real cadastrado, quando existir. |
| Paridade entre catálogos | `rfi-r02` deixa de estar defasado em relação a `mendeslobo` para o domínio RH da ADR-165/166 — mesmos itens, mapeamento equivalente ajustado ao roster próprio. |
| Degradação segura preservada | Catálogos sem `P0092`/`P0057` (ex.: `samples`/`test`) continuam usando o valor hardcoded antigo como fallback — nenhum catálogo existente quebra. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| "Alojamento" (ADM) e LAB continuam 100% hardcoded | Gap conhecido e documentado (D5) — fase seguinte explícita, não silenciosa. |
| `P0092` "Coordenador" foi criado com o mesmo valor do lump antigo, sem cotação de mercado independente | Decisão explícita do usuário — aceito; pode ser atualizado depois via `atualizar_preco_insumo` sem re-trabalho estrutural. |
| Paridade `mendeslobo` × `rfi-r02` é mantida manualmente (2 scripts rodados 2 vezes) — sem mecanismo que force os dois catálogos a nunca divergirem de novo | Aceito por ora — mesmo risco que já existia entre catálogos antes desta ADR; um mecanismo de sincronização entre catálogos é maior que o escopo aqui. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `P0092` Coordenador criado em `mendeslobo` e `rfi-r02` | ✅ Implementado |
| F2 | 34 itens RH (ADR-165) replicados em `rfi-r02` | ✅ Implementado |
| F3 | Mapeamento função→item (ADR-166 D4) reaplicado em `rfi-r02` | ✅ Implementado |
| F4 | ADM/TOP com `funcao_id` real + fallback seguro | ✅ Implementado |
| F5 | JSON Schema de `Insumo` atualizado com os 3 tipos da ADR-165 (achado) | ✅ Implementado |
| F6 | LAB + "Alojamento" (ADM) | ⬜ Adiado — fase seguinte |

## Definition of Done

### Fase 1
- [x] `P0092` criado em ambos os catálogos via rascunho→merge/quatro-olhos; `auditar_catalogo` SAUDAVEL nos dois

### Fase 2-3
- [x] `rfi-r02`: 34 insumos RH + 11 atualizações de `funcoes_aplicaveis` aplicadas; `auditar_catalogo` SAUDAVEL

### Fase 4
- [x] Teste cobrindo: TOP sem catálogo usa lump (R$9.216); TOP com `P0057` no catálogo usa preço real (R$18.000); ADM sem catálogo usa lump (R$12.500+R$3.500); ADM com `P0092` usa preço real de Coordenador + preserva Alojamento hardcoded; catálogo presente mas sem o código específico mantém fallback (degradação segura)

### Fase 5
- [x] `tipoInsumo` (`common.schema.json`) inclui `TREINAMENTO`/`EXAME`/`BENEFICIO`; `insumo.schema.json` ganha os `$defs`/`if-then` correspondentes e `atributosMaterial` ganha `vida_util_dias`/`funcoes_aplicaveis`
- [x] `test_catalog_schema_rfi_r02.py::test_insumos_reais_sem_erros` (itera todos os insumos reais de `rfi-r02`) verde
- [x] Testes de censo (`test_adr139_f1bis_classificacao_origem.py`/`test_adr139_f4quater_rfi_bom_usinagem.py`) atualizados para excluir `EPI-*` da exigência de `origem_material` classificado, em ambos os catálogos

## Nota de Implementação

Implementada via TDD. Suíte completa verde (só a falha pré-existente e não relacionada do golden test).

---

## Relacionados

- ADR-163/164 — CRUD/Batch de Insumo (tools reaproveitadas para criar `P0092` e aplicar o mapeamento)
- ADR-165 — Catálogo de Treinamentos, Exames, EPIs e Benefícios de Mão de Obra (replicado em `rfi-r02`)
- ADR-166 — Wiring de Indiretos + Mapeamento Função→Item (mesmo padrão de degradação segura reaplicado a ADM/TOP; mapeamento reaplicado ao roster de `rfi-r02`)
