# ADR-139 — Origem de Materiais Consumíveis (Aquisição Externa × Geração Interna) e Padrão Produtor-Consumidor entre Atividades

**Status:** ⚠️ Parcialmente Implementado _(F1–F4 ✅, incl. backfill, classificação de origem completa — 45 externos com 2 decisões revisadas por dossiê, 3 gerados, 49 placeholders AGIS —, enriquecimento produtor-consumidor dos dois catálogos com justificativas normativas DNIT; F5 ✅ pipeline (integração real no skill-04, ver ADR-128 F5) — pende apenas F5 (UI: `tanque_sugerido`/dashboard), ver Plano de Implementação)_
**Data:** 2026-07-14
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-128 (disponibilidade de recursos consumíveis — `DisponibilidadeConsumivel`/`ReplenishableResource`), ADR-138 §D7 (nota de design que antecipou esta ADR), ADR-030 (`MaterialEquipe`), ADR-053 (separação CPU × Produtividade), ADR-130 (grafo de sinergia — `precondicao` de material), ADR-129 (cotação por proximidade geográfica)

---

## Contexto

### Problema

P1. **`MATERIAL` é um bucket único, sem distinção de origem.** `TipoInsumo` (`domain/models/catalog/catalogo.py`) admite `MATERIAL | MAO_OBRA | EQUIPAMENTO | TERCEIRIZADO`; nenhum campo em `Insumo`, `ComposicaoItem` ou `MaterialEquipe` distingue um material **de aquisição externa** (tinta, areia comprada, aço, emulsão asfáltica) de um material **gerado internamente pela própria obra** (terra escavada de corte reaproveitada em aterro, brita produzida em usina própria, solo selecionado de jazida do canteiro). Os únicos ganchos correlatos — `AtributosInsumo.fornecedor_referencia`, `prazo_entrega`, `disponibilidade` — são opcionais, de texto livre e **vazios em 100% dos 94 materiais do catálogo `mendeslobo`** (a própria ADR-128 os chamou de "campos mortos").

P2. **O modelo de estoque da ADR-128 só conhece reabastecimento externo.** `DisponibilidadeConsumivel` (`estoque_inicial`, `capacidade_armazenamento`, `taxa_reabastecimento_max`, `lead_time_reabastecimento_dias`) e `ReplenishableResource` (`application/scheduling/models.py`) projetam o balanço semanal `estoque[t] = estoque[t-1] + reabastecimento[t] − consumo[t]`, onde `reabastecimento[t]` deriva exclusivamente de `taxa_reabastecimento_max` — capacidade logística de fornecedor/comboio. **Não existe forma de uma atividade abastecer o estoque consumido por outra**: o padrão corte→aterro (a frente de escavação produz o material que a frente de compactação consome) ou usina→pavimentação não é modelável. O vocabulário produtor-consumidor aparece no código apenas do lado consumidor (`consumo_por_semana: dict[activity_id → taxa]`); não há nó produtor.

P3. **A ponte conceitual já existe, mas é só documental.** O grafo de sinergia (ADR-130) tem o tipo de relação `precondicao` para material intra-equipe ("material disponível é precondição de produção"), e a ADR-130 o conecta narrativamente à ADR-128 no RCPSP — mas o motor de sinergia explicitamente não altera taxa para `precondicao`, e nenhum código liga a produção de uma atividade ao estoque de outra.

P4. **Sem a distinção de origem, camadas a jusante tratam material gerado como comprável.** A cotação por proximidade (ADR-129) e a análise de tendência de preço (`application/catalog/price_trend.py`) assumem que todo `MATERIAL` tem preço de mercado e fornecedor; o cubo analítico (`analytics/cubo_analitico.py`) mapeia todo material para a propriedade única `consumivel`. O balanço de massas corte/aterro e a decisão bota-fora interno × externo — hoje discutidos apenas em documento de research (`docs/engineering/4-development/research/mapa-divergencias-eap-cronograma.md`) — não têm representação no modelo.

P5. **A lacuna já foi formalmente registrada.** A ADR-138 §D7, ao migrar 30 CPUs de BOM genuíno para `MaterialEquipe`, deixou nota de design explícita: entradas de `materiais` hoje não carregam nenhum sinal de proveniência ("consumo operacional direto" vs. "BOM convertido"), e "vale uma ADR própria para dar a essas entradas um campo/flag dedicado". Esta é essa ADR — estendida para cobrir também a dimensão de origem (externa × interna) e o fluxo produtor-consumidor que ela habilita.

### Princípio

A distinção de origem é **atributo ortogonal ao tipo**: um material gerado internamente continua sendo `MATERIAL` para toda a cadeia de composição, precificação e validação existente. O que muda é (a) como ele entra no estoque (produção de outra atividade, não compra) e (b) quais análises fazem sentido para ele (cotação/fornecedor não; balanço temporal e capacidade de armazenamento sim).

---

## Decisão

**D1 — Novo campo `origem_material` no `Insumo`, restrito a `tipo == "MATERIAL"`.**

```python
OrigemMaterial = Literal["AQUISICAO_EXTERNA", "GERACAO_INTERNA"]

class Insumo(BaseModel):
    ...
    origem_material: OrigemMaterial | None = None  # ADR-139; None = não classificado
```

- `None` é o default retrocompatível — os 94 materiais de `mendeslobo` e todos os catálogos existentes permanecem válidos byte-idênticos sem migração obrigatória.
- Nova validação **VAL-INSUMO-ORIGEM-01** (ERRO): `origem_material` preenchido em insumo cujo `tipo != "MATERIAL"`.
- Semântica de preço: para `GERACAO_INTERNA`, `preco_unitario`/`fonte_preco` passam a representar **custo interno de produção** (ou `0.0` quando o custo já está integralmente capturado na CPU produtora — caso típico de terra escavada, cujo custo é a própria atividade de escavação). A decisão de *como* ratear custo de produção interna entre produtora e consumidora fica fora de escopo desta ADR (ver §Fora de escopo).
- Consumidores que devem passar a filtrar por origem: cotação por proximidade (ADR-129) e `price_trend.py` excluem `GERACAO_INTERNA` (não há fornecedor a cotar); o cubo analítico ganha a propriedade `origem_material` na dimensão de insumo.

**D2 — Proveniência da entrada `MaterialEquipe` (resolve ADR-138 §D7).**

```python
class MaterialEquipe(BaseModel):
    ...
    origem_entrada: Literal["consumo_operacional", "bom_convertido"] | None = None  # ADR-139
```

- `consumo_operacional` = semântica original ADR-030 D2 (água de umectação, aditivo — consumo por hora de operação da equipe); `bom_convertido` = quantidade de BOM por unidade de produto convertida via `consumo_por_hora = coeficiente × valor_horario` (ADR-138 F2).
- Backfill determinístico: as 33 entradas criadas pela migração da ADR-138 F2 (lista conhecida do script `migrate_composicao_itens_material.py`) recebem `bom_convertido`; as demais permanecem `None` até classificação.
- Este eixo é **ortogonal** a D1: um `bom_convertido` pode ser de aquisição externa (cimento) ou geração interna (brita própria).

**D3 — Lado produtor no catálogo: `MaterialGerado` em `Producao`, simétrico a `MaterialEquipe`.**

```python
class MaterialGerado(BaseModel):
    insumo_id: str            # deve referenciar Insumo com origem_material == "GERACAO_INTERNA"
    geracao_por_hora: float   # quantidade gerada por hora de operação da equipe
    unidade: str

class Producao(BaseModel):
    ...
    materiais_gerados: list[MaterialGerado] = Field(default_factory=list)  # ADR-139
```

- Base horária deliberadamente idêntica à de `MaterialEquipe.consumo_por_hora` (pós-ADR-138, os fluxos horários vivem em `Producao`): quem tem o dado por unidade de produto converte com a mesma fórmula price-preserving `geracao_por_hora = geracao_por_unidade × valor_horario`.
- Nova validação **VAL-PROD-GERACAO-01** (ERRO): `MaterialGerado.insumo_id` referencia insumo inexistente ou com `origem_material != "GERACAO_INTERNA"`.
- Exemplo canônico: CPU de escavação com `valor_horario = 120 m³/h` gera `MaterialGerado(insumo_id="MA-SOLO-CORTE", geracao_por_hora=120.0, unidade="m3")` (fator de empolamento, se aplicável, entra no coeficiente).

**D4 — Balanço de estoque do RCPSP ganha o termo de produção interna.**

```python
class ReplenishableResource(BaseModel):
    ...
    consumo_por_semana: dict[str, float]                                  # existente
    producao_por_semana: dict[str, float] = Field(default_factory=dict)   # ADR-139: activity_id -> taxa
```

O balanço de `project_estoque_semanal` (`application/scheduling/replenishable.py`) passa a:

```
estoque[t] = estoque[t-1] + reabastecimento_externo[t] + producao_interna[t] − consumo[t]
```

- `producao_interna[t]` = soma das taxas das atividades produtoras **ativas na semana `t`** segundo o cronograma corrente — a produção acompanha o schedule da produtora, exatamente como o consumo já acompanha o da consumidora.
- Para recurso 100% `GERACAO_INTERNA`, `taxa_reabastecimento_max = None` (sem compra); `capacidade_armazenamento` da ADR-128 ganha uso novo e natural: pilha/bota-espera limitada.
- Reparo de estoque negativo: mantém a heurística existente (`apply_replenishable_delay` atrasa a consumidora) dentro do laço de ponto fixo já implementado no `cpsat_scheduler.py` (Fase 2b, reparo ↔ repropagação de precedência). Atrasar a **produtora** nunca ajuda (só reduz estoque futuro); o caso "consumidora antes da produtora" converge pelo mesmo mecanismo de delay incremental, sob o cap de iterações existente. Estoque acima de `capacidade_armazenamento` gera AVISO (**VAL-ESTOQUE-CAP-01**), não delay — descartar/bota-fora é decisão econômica, não de agenda.
- Nova validação **VAL-ESTOQUE-PROD-01** (ERRO): `activity_id` em `producao_por_semana` ausente do `ActivityDAG`.

**D5 — Física no catálogo, pareamento no projeto (mesma filosofia da ADR-128 D3).** O catálogo declara a física da CPU (`geracao_por_hora`, `consumo_por_hora`); **qual frente abastece qual estoque** — o plano de destinação corte→aterro, quantas pilhas intermediárias existem, se há bota-fora externo complementar — é dado de **projeto/escopo** (condições do canteiro), materializado na montagem dos `ReplenishableResource` de cada schedule, não no `Insumo` global. Dois projetos usando a mesma CPU de escavação podem destinar o material de formas diferentes.

**D6 — Fora de escopo desta ADR (nomeado explicitamente):**
- **Custo de transporte/DMT do material gerado** (bota-fora interno × externo como decisão econômica): o DMT existe hoje só como atributo de calibração/matching de CPUs (`AtributosCategoriaCPU.dmt_*`); precificar a destinação é ADR futura.
- **Rateio do custo de produção interna** entre atividade produtora e consumidora (D1 fixa apenas a semântica do `preco_unitario`).
- **Otimização de balanço de massas** (cut-fill optimization): esta ADR viabiliza *verificar* um plano de destinação dado, não *otimizá-lo*.
- **Estoque espacializado** (localização de pilhas, distância entre frentes): o estoque continua escalar por recurso, como na ADR-128.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Novo valor em `TipoInsumo` (ex.: `MATERIAL_GERADO`) em vez de campo ortogonal | Quebraria `CATEGORIA_TIPO_MAPA` (`domain/validations/cpu_insumo.py`), `InsumoReferencia.tipo` e todo consumidor que hoje faz `tipo == "MATERIAL"`; origem é atributo do material, não um tipo novo — o mesmo insumo areia pode ser comprado num projeto e produzido em outro (aí sim seriam dois `Insumo` distintos, distinguidos pelo campo, não pelo tipo) |
| A2 | Modelar produtor-consumidor como precedência SS/FF com lag no `ActivityDAG` (NEP-031) em vez de estoque | Precedência não captura acúmulo, capacidade de armazenamento nem taxas divergentes (produtora mais rápida que consumidora); o balanço temporal da ADR-128 já existe e é o mecanismo certo — falta só o termo de produção |
| A3 | Usar o campo livre `categoria` já presente nos JSONs de material (ex.: `categoria: "GERADO"`) | String livre, não tipada, invisível ao modelo Pydantic (`extra="ignore"`), não validável — repetiria o padrão "campo morto" de `fornecedor_referencia`/`prazo_entrega` que a ADR-128 diagnosticou |
| A4 | Declarar `geracao_por_hora` no nível de projeto/escopo, junto com o pareamento | A física da geração (quanto uma escavadeira produz de material por hora) é propriedade da CPU/produtividade, tão de catálogo quanto `consumo_por_hora`; só o **pareamento** produtora→estoque→consumidora é de projeto (D5) — mesma separação que a ADR-128 D3 fez para `taxa_reabastecimento_max` |
| A5 | Backfill obrigatório de `origem_material` nos 94 materiais existentes já nesta ADR | Classificação exige julgamento de domínio (areia pode ser comprada ou de jazida própria conforme o contexto da empresa); default `None` + script assistido de classificação (F1) evita chutar dado de catálogo — mesmo princípio do Step 0 da ADR-138 (verificar antes de mudar dado) |
| A6 | Reparar estoque negativo atrasando a atividade produtora além da consumidora | Atrasar a produtora nunca aumenta estoque disponível para a consumidora — só o reduz; o reparo existente (delay da consumidora) é suficiente e já converge no laço de ponto fixo da Fase 2b |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Corte→aterro modelável | O padrão produtor-consumidor entre frentes (hoje ausente de código e ADRs) passa a ser verificável no RCPSP: consumidora só avança quando a produtora acumulou material |
| Resolve o débito da ADR-138 §D7 | Entradas `MaterialEquipe` ganham proveniência explícita (`consumo_operacional` × `bom_convertido`); o esticamento semântico documentado deixa de ser invisível no dado |
| Análises de suprimento ficam honestas | Cotação (ADR-129) e tendência de preço deixam de tratar material gerado como comprável; lista de compras derivável por `origem_material == "AQUISICAO_EXTERNA"` |
| Reaproveita a ADR-128 inteira | Nenhum modelo novo de estoque: um campo novo (`producao_por_semana`) e um termo novo no balanço; `capacidade_armazenamento` ganha uso real (pilha limitada) |
| Retrocompatibilidade total | Todos os campos novos são opcionais com default; catálogos e schedules existentes permanecem válidos e byte-idênticos sem migração |
| Ponte ADR-130 → ADR-128 deixa de ser só documental | `precondicao` de material no grafo de sinergia passa a ter contraparte executável no estoque do scheduler |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Mais um eixo de classificação para o editor de catálogo manter | Campos opcionais (`None` = não classificado); validações só disparam quando preenchido errado, nunca por ausência; script de classificação assistida em F1 |
| Laço de ponto fixo do scheduler ganha acoplamento novo (delay da consumidora não muda produção, mas repropagação de precedência pode mover a produtora) | Cap de iterações existente da Fase 2b mantido; teste de convergência com cadeia produtora→consumidora encadeada por precedência entra no DoD de F3 |
| `preco_unitario` com semântica dupla (preço de compra × custo interno) pode confundir consumidores de preço | Semântica fixada em D1 e documentada no docstring; rateio real de custo interno explicitamente deferido (D6) — até lá, convenção `0.0` para custo já capturado na produtora |
| Dado de `geracao_por_hora` não existe em nenhum catálogo hoje | Igual ao precedente da ADR-130 F4 (grafo populado só em `rfi-r02`): motor primeiro, dado depois; F4 escolhe um piloto real (terraplenagem `rfi-r02`, que já tem os clusters de escavação) |
| Risco de sobre-classificação (marcar tudo como `GERACAO_INTERNA` para zerar compra) | VAL-PROD-GERACAO-01 exige produtora declarada no catálogo; sem `MaterialGerado` correspondente, estoque de recurso sem reabastecimento externo fica negativo e o schedule denuncia |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Modelo de origem | `OrigemMaterial` + `Insumo.origem_material` + `MaterialEquipe.origem_entrada`; VAL-INSUMO-ORIGEM-01; backfill `bom_convertido` das 33 entradas da ADR-138 F2 (script `backfill_origem_entrada_bom_convertido.py`, idempotente, dry-run padrão); docstrings | ✅ Implementado _(código + backfill aplicado em `mendeslobo`)_ |
| F1-bis — Classificação de origem (dado) | Script assistido `classify_origem_material.py` executado sobre os 94 materiais `mendeslobo`: 43 `AQUISICAO_EXTERNA` (fonte_preco de compra), 49 placeholders AGIS sem classificação (não são materiais físicos — ADR-138 §D7), 2 sinalizados para o editor (`MA-BGTC-MIX`/`MA-CBUQ-FAIXA-C`: usina própria × compra); nenhum `GERACAO_INTERNA` chutado (A5) | ✅ Implementado _(os 2 ambíguos foram resolvidos via composições de usinagem — ver nota abaixo)_ |
| F2 — Lado produtor no catálogo | `MaterialGerado` + `Producao.materiais_gerados`; VAL-PROD-GERACAO-01 (wired em `validar_cpu_completa`); cure_schema tolerante aos campos novos (verificado por teste) | ✅ Implementado |
| F3 — Scheduler | `ReplenishableResource.producao_por_semana`; termo de produção em `project_estoque_semanal`; VAL-ESTOQUE-PROD-01 (fail-loud em `CpSatScheduler.schedule`); VAL-ESTOQUE-CAP-01 (AVISO — `project_overflow_semanal`/`violation_estoque_acima_capacidade`); integração no laço de ponto fixo com teste de convergência | ✅ Implementado |
| F4 — Builder + piloto + filtros de preço | `build_replenishable_resources` (`application/scheduling/replenishable_builder.py`, aceita modelos e dicts de bundle) — **fecha também a lacuna da ADR-128 F4** ("sem fonte real de projeto/escopo": nenhum código de produção construía `ReplenishableResource`); piloto corte→aterro em `rfi-r02` com dado real (`MA-SOLO-ESCAVADO-3CAT` GERACAO_INTERNA + `materiais_gerados` na escavação 3ª cat 142,16 m³/h + consumo `bom_convertido` no corpo de aterro 214,92 m³/h — consumidora mais rápida que produtora, delay verificado no CP-SAT de ponta a ponta); `price_trend.py` exclui `GERACAO_INTERNA`; VAL-INS-VAL-01 isenta material gerado de "preço zerado" (preço 0.0 é a convenção D1, não dado faltante) | ✅ Implementado |
| F4 — Reescopo cubo/cotação (nota) | **Cubo**: propagar `origem_material` até `CelulaAnalitica` criaria campo morto — o builder do cubo agrega custo mensal por categoria sem `insumo_id` nas células, e material gerado tem custo de aquisição 0 (não gera célula de custo); adiar até existir fonte de dado real, em vez de repetir o anti-padrão "campo morto" que a ADR-128 diagnosticou. **Cotação ADR-129**: verificado que é exclusiva de diesel (`geo_diesel_resolver.py`) — o filtro de origem não se aplica lá; o ponto real de análise de preço de MATERIAL é o `price_trend`, já filtrado | ✅ Decidido (reescopo) |
| F5 — Pipeline skill-04 | `selector.py`/skill-04 agora constroem `ReplenishableResource` (via `build_replenishable_resources`, incl. o pareamento produtor-consumidor desta ADR) e passam para `CpSatScheduler.schedule()` no pipeline real — ver ADR-128 F5 para o detalhe completo (config de projeto, relatório causal, testes) | ✅ Implementado (2026-07-15, ver ADR-128 F5) |
| F5 — UI (dashboard) | Projeção de estoque de material gerado na UI a partir de `project_estoque_semanal` (não do cubo — estoque é grandeza física do schedule, não custo); inclui fechar o gap pré-existente do `tanque_sugerido` (call-site nunca passa `disponibilidade`) | ⏳ Pendente |

## Definition of Done

### F1
- [x] `OrigemMaterial` e `Insumo.origem_material` com default `None`; catálogos existentes carregam sem alteração (preços verificados pela suíte completa, incluindo os testes price-preserving da ADR-138 F2 sobre `mendeslobo`)
- [x] `MaterialEquipe.origem_entrada` com default `None`; backfill das 33 entradas da ADR-138 F2 aplicado e idempotente (teste TDD sobre fixture + censo do catálogo real)
- [x] VAL-INSUMO-ORIGEM-01 implementada com teste TDD (origem em MAO_OBRA/EQUIPAMENTO/TERCEIRIZADO → ERRO)
- [ ] (F1-bis) Script de classificação assistida executado; classificação dos 94 materiais `mendeslobo` revisada por editor de catálogo (não chutada)
- [x] Suíte completa sem regressões; `ruff check`/`ty check src` limpos (ty: mesmos 9 diagnósticos pré-existentes do baseline)

### F2
- [x] `MaterialGerado` + `Producao.materiais_gerados` (default lista vazia)
- [x] VAL-PROD-GERACAO-01 com teste TDD (insumo inexistente, `AQUISICAO_EXTERNA` e não classificado → ERRO)
- [x] `cure_schema` não descarta nem corrompe os campos novos em catálogos legados (teste sobre `cure_producao`/`_normalize_team`)

### F3
- [x] Balanço com termo de produção: teste unitário produtora ativa → estoque cresce; produtora inativa → só reabastecimento externo
- [x] Recurso 100% interno (`taxa_reabastecimento_max=None`): consumidora agendada antes da produtora recebe delay até viabilidade
- [x] VAL-ESTOQUE-CAP-01 (AVISO) quando estoque projetado excede `capacidade_armazenamento`; excedente não gera delay
- [x] Teste de convergência do ponto fixo com cadeia produtora→consumidora ligada também por precedência no DAG
- [x] Suíte completa sem regressões

### F1-bis (classificação assistida — executada)
- [x] `scripts/catalog/classify_origem_material.py` (dry-run padrão, idempotente, nunca sobrescreve): 43 materiais com `fonte_preco` de compra → `AQUISICAO_EXTERNA`; 49 placeholders AGIS (ADR-138 §D7) deliberadamente sem classificação (não são materiais físicos); nenhum `GERACAO_INTERNA` proposto automaticamente (exige conhecimento de canteiro)
- [x] Revisão dos 2 casos ambíguos (`MA-BGTC-MIX`, `MA-CBUQ-FAIXA-C`) — **resolvida em duas etapas**: (1ª) classificados `AQUISICAO_EXTERNA` pelo critério do recorte do catálogo (sem usina modelada), com nota de preço defasado; (2ª, definitiva) **composições de usinagem modeladas** (`build_usinagem_bgtc_cbuq.py`: `PROD-USINAGEM-BGTC-001` SICRO 6416042 e `PROD-USINAGEM-CBUQ-001` SICRO 6416078, com 19 insumos SICRO-referenciados 202604-SP) → reclassificados `GERACAO_INTERNA` com **preço concluído pela composição**: custo horário bottom-up ÷ produção **derivada pelo grafo de sinergia** (ADR-130: capacidade da usina justificada → gargalo → 113,18 m³/h / 99,60 t/h; `resolver_producao_efetiva` com fonte "derivado" == declarado, validado por teste). Preços: BGTC R$ 92,50 → **R$ 301,23/m³** (ref. SICRO 202604-SP 308,83 com TF+FIC não modelados); CBUQ R$ 385 → **R$ 484,26/t** (usinagem 199,84 + CAP 5,545% × R$ 5.200/t ANP; mercado posto-usina 495–680). Preços legados preservados em `historico_precos`; grafos com `precondicao` do ligante (ponte ADR-130→ADR-128/139) e cadeia usina→pavimentação fechada (produz `MA-BGTC-MIX`, base BGTC consome — E2E no CP-SAT)
- [x] Pares "revisáveis" fundamentados por norma (revisão F1-bis): aterros PN/PI ← solo 1ª cat confirmado por **DNIT 108/2009-ES §5.1** (aterro com solo de corte/empréstimo 1ª/2ª cat; Proctor aplica-se a solos; SICRO de compactação não inclui material — o solo vem do corte, exatamente o padrão produtor-consumidor) + rolo pé-de-carneiro na composição; reforço de subleito ← solo selecionado por **DNIT 138/2010-ES §5.1** (ISC de projeto, expansão ≤ 1%, corte selecionado ou jazida); justificativas atualizadas no dado e no mapeamento

### F4
- [x] `build_replenishable_resources` com teste TDD (fluxos produtor/consumidor, horas por atividade, disponibilidade declarada × default interno, irrestrito sem declaração, VAL-PROD-GERACAO-01 fail-loud)
- [x] Piloto corte→aterro em `rfi-r02` com dado real de `geracao_por_hora` e pareamento de projeto (D5); teste E2E catálogo real → builder → CP-SAT (aterro adiado até estoque acumular, estoque não-negativo)
- [x] Enriquecimento completo dos catálogos `rfi-r02` E `mendeslobo` (mesmo molde do ADR-130 F4, script idempotente `enrich_produtor_consumidor.py` com mapeamento declarativo e justificativa por entrada): 3 insumos `GERACAO_INTERNA` por catálogo (solo 1ª/2ª/3ª cat); rfi-r02 com 8 produtoras (escavações × DMT, canaletas, rebaixo 20 cm com conversão m²→m³) e 5 consumidoras; mendeslobo com 6 produtoras (ATI-011/012, ESCO-CARGA 1/2/3 cat, vala de drenagem) e 7 consumidoras (aterros PN/PI, corpo de aterro 3ª cat, camada final de rocha, reaterro de vala); exclusões deliberadas documentadas no script (valas de tubo sem seção, resíduo vegetal/entulho, agregados comprados, rejeito filtrado = fornecimento externo ADR-128); QA de dado em `test_adr139_f4_enriquecimento_catalogos.py` valida o dado contra o próprio mapeamento (censo, taxas, integridade referencial, balanço de massas fechado por catálogo, E2E nos dois catálogos)
- [x] `price_trend` exclui `GERACAO_INTERNA`; VAL-INS-VAL-01 isenta material gerado de preço zero (TDD)
- [x] Cubo/cotação reescopados com justificativa registrada (ver Plano — evitar campo morto; ADR-129 é só diesel)
- [x] Schemas JSON do catálogo (`config/schemas/catalog/`) formalizam os campos novos: `insumo.origem_material`, `atributosMaterial.disponibilidade` (`$defs/disponibilidadeConsumivel`), `materialEquipe.origem_entrada`, `producao.materiais_gerados` (`$defs/materialGerado`) — validados pelos testes de schema do `rfi-r02`

### F4-bis — Cura de insumos AGIS com código trocado (achado da revisão de preço)
- [x] Dossiê: códigos de insumo deslocados na importação AGIS (descrição+preço+consumo coerentes entre si, código apontando outro material); **erro crítico corrigido** — CPU-PAVIM-ATI-058/061 consumiam massa asfáltica (72 kg/m² = 3 cm × 2,4 t/m³) a preço de CAP puro (R$ 5.300/t): material R$ 381,60/m² ≈ 10× o real → repontadas para `MA-CBUQ-FAIXA-C` (massa usinada gerada) ≈ R$ 34,87/m²
- [x] `cure_insumos_agis_codigo_trocado.py` (idempotente): 5 repoints (ATI-058/061 → CBUQ usinado; ATI-023 → `MA-BGTC-MIX`, consolidando a duplicata `MA-BRITA-GRADUADA`; ATI-019 → novo `MA-CCR`; ATI-062 → novo `MA-EMULSAO-RR2C-GRANEL`), 4 códigos mentirosos marcados `_superseded_por` sem consumidor restante (remoção = decisão do editor); QA em `test_adr139_f4_cura_agis.py`
- [x] Consolidação de agregados canônicos (F4-ter, `consolida_agregados_canonicos.py`): as "duplicatas" eram três **gerações de preço** do mesmo material (cotação empresa 2025-05; cotação AGIS 2026; referência SICRO 202604-SP). Regra aplicada, derivada da hierarquia de fontes do catálogo (NEP-032: empresa > referência): **um canônico por material**, preço vigente = cotação de mercado mais recente da empresa (AGIS 2026: pedrisco 145, brita 2 145, brita 3 140, rachão 147, pó de pedra 165; mai/2025 quando única: brita 1 78, areia média 68 — com `_alerta_preco` de defasagem −55%/−52% p/ recotação), SICRO preservado em `historico_precos`; 3 canônicos novos (rachão, areia grossa, areia fina) absorvem órfãos; 9 repoints; 10 códigos superseded sem consumidor (incl. gêmeos `*-SICRO` e todos os `MA-{BSTC,BDTC,BTTC}-CORPO-*`); usinagens re-concluídas na base da empresa: BGTC 301,23 → **245,63/m³**, CBUQ 484,26 → **466,30/t** (cascata nos snapshots ADR-138, documentada); QA em `test_adr139_f4ter_consolidacao_agregados.py`
- [ ] Recotação pelo editor dos 2 canônicos com alerta de defasagem (`MA-BRITA-1` 78 vs SICRO 172,79; `MA-AREIA-MEDIA` 68 vs 140,84 — cotações de mai/2025); ao recotar, os preços de BGTC/CBUQ re-concluem via `build_usinagem_bgtc_cbuq.py --apply`

### F4-quater — rfi-r02: classificação completa, usinagem CBUQ da casa e restauração de BOM
- [x] Censo: inventário de materiais do rfi-r02 é LIMPO (M0001–M0037 — o mendeslobo herdou esses dados com códigos embaralhados), mas 38/41 materiais eram ÓRFÃOS: as CPUs não declaravam BOM (custo de material zero em CBUQ, TSD, BGTC, CCR, tubos, piso, guias…)
- [x] Classificação 100%: 38 materiais → `AQUISICAO_EXTERNA` (fontes `planilha_rfi_r02`/`ANTT_2026_Nordeste` adicionadas às fontes de compra do script)
- [x] Usinagem CBUQ própria (`PROD-USINAGEM-CBUQ-RFI-001`): ancorada na usina E0043 que JÁ existia no catálogo (R$ 392/h — dado da casa) + física SICRO 6416078; produção derivada pelo grafo (99,60 t/h, gargalo E0043); `MA-CBUQ-FAIXA-C` gerado com preço concluído **R$ 506,92/t** (CAP da planilha a R$ 6.091/t domina); nota explícita: confirmar a classe real da E0043 — se menor que 100/140 t/h, capacidade e preço re-derivam
- [x] Restauração de BOM (24 entradas, `restore_bom_usinagem_rfi_r02.py`): identidades físicas 1 m³/m³ e 1 m/m (CCR, BGTC comprada — sem usina de solos no rfi —, pó de pedra, rachão compactado, tubos PVC/concreto, piso, guia, manta), espessura×densidade (CBUQ 0,072 t/m²) e coeficientes das CPUs gêmeas mendeslobo (pintura de ligação 0,39 kg/m², TSD 1,0 kg/m²); numeração comercial da planilha lida com âncoras (Brita 01=pedrisco … Brita 04=rachão); QA em `test_adr139_f4quater_rfi_bom_usinagem.py`
- [ ] Fora, documentado no script: ATI-047 (tubo PBA 150 mm sem insumo), corpos celulares BSCC/BDCC/BTCC (moldados in loco — BOM de concreto/aço/forma sem coeficiente de evidência), ATI-054 sub-base estabilizada; e confirmação da classe da usina E0043 pelo campo

### F5 — pipeline (implementado 2026-07-15, ver ADR-128 F5 para o detalhe completo)
- [x] Skill-04 adota `CpSatScheduler` + `build_replenishable_resources` no pipeline real (incl. pareamento produtor-consumidor desta ADR via `producoes_por_atividade`)
- [x] Regressão zero provada por integração fim a fim; relatório causal de atraso (`VAL-ESTOQUE-DELAY-01/02`)
- [ ] **Achado 2026-07-25 — AGIS quebrou após o wiring (regressão não coberta na integração original):** `CPU-TERRA-COMPAC-PN`/`CPU-TERRA-COMPAC-PI` (produtividades) consomem `MA-SOLO-ESCAVADO-1CAT` para as **duas** (demanda agregada ~1.165.046 m³), enquanto a produção real de 1CAT na EAP AGIS é só ~444.378 m³ (déficit ~720.668 m³) — e `MA-SOLO-ESCAVADO-2CAT` (produção ~691.257 m³, quantidade quase idêntica ao déficit) não é consumido por CPU nenhuma. É pareamento de categoria de solo incompleto (D5), não bug de scheduler: o reparo de estoque (`_MAX_REPAIR_ROUNDS`, ADR-128) esgota corretamente porque o déficit é estrutural (quantidade), não de timing. Resultado: `VAL-ESTOQUE-DELAY-02` marca o schedule AGIS como infeasible → `custo_direto` agregado cai a zero, quebrando `tests/integration/cost/test_cost_decomposition_adr104.py` (baseline de custo de 2026-06-12, anterior a este wiring). Rfi-r02 (`MA-SOLO-ESCAVADO-3CAT`) não tem esse problema — fecha exato.
- [x] **Correção derivável aplicada (`scripts/catalog/cure_pareamento_solo_compac_pn_agis.py`):** o quantitativo do item de EAP que usa `CPU-TERRA-COMPAC-PN` (1.135.635,3 m³) bate — casa decimal a casa decimal — com a soma exata de 1CAT+2CAT reais da EAP (444.378,2 + 691.257,1), o mesmo padrão já correto do par 3CAT. BOM de `CPU-TERRA-COMPAC-PN-PROD-001` dividido proporcionalmente (67,70 + 105,31 m³/h, soma preserva o `valor_horario` original de 173,01). `CPU-TERRA-COMPAC-PI` (29.411,0 m³) não foi tocado — seu volume não bate com nenhuma soma residual, não é derivável objetivamente dos dados disponíveis.
- [ ] **Achado 2026-07-25 (2/2) — infeasibilidade tem uma segunda causa, independente do pareamento:** mesmo com o BOM de PN corrigido, `concilium benchmark run --slug AGIS --reset` continua retornando `INVIAVEL`. O motivo mudou: agora é `"violou precedência, capacidade de pool ou horizonte"` (não mais esgotamento do `_MAX_REPAIR_ROUNDS` por estoque negativo) — e o mesmo erro, **antes** da correção do BOM, já apontava `MA-SOLO-ESCAVADO-1CAT→eap-1_7 (+10sem)` **e** `MA-SOLO-ESCAVADO-3CAT→eap-1_9 (+10sem)` simultaneamente, isto é: mesmo o par 3CAT (cuja quantidade sempre fechou exata) já precisava de +10 semanas de atraso via `apply_replenishable_delay`, e essa correção de timing está sendo rejeitada por `_validate_repaired_schedule` (violação de precedência, capacidade do `ResourcePool` ou do horizonte `H` do projeto). Ver resolução em ADR-128 F7 (gap `inferir_pool_minimo`×reparo) e achado 3/3 abaixo (causa raiz real).

### F5-ter — Vínculo produtor-consumidor de solo nunca existia no mendeslobo (achado 2026-07-25, 3/3 — causa raiz real)
- [ ] **Achado:** instrumentando `apply_replenishable_delay` diretamente (após corrigir F5-bis e ADR-128 F7), descobri que `ReplenishableResource.producao_por_semana` está **vazio** (`{}`) para `MA-SOLO-ESCAVADO-{1,2,3}CAT` no projeto AGIS — a compactação consome material que **nenhuma atividade produz**, então o estoque é negativo desde a primeira semana de consumo e nunca se recupera, independente de timing, pool ou horizonte. Causa raiz no catálogo: as 6 produtividades de escavação `CPU-TERRA-ESCO-CARGA-{1,2,3}CAT-DMT{2000,3000}-PROD-001` em `config/catalogos/mendeslobo/produtividades/` nunca declararam `materiais_gerados` — ao contrário das equivalentes em `rfi-r02`, que já têm esse campo (confirmação numérica: os `valor_horario` do mendeslobo — 231,87 / 230,91 / 158,28 / 158,78 / 142,02 / 142,16 — batem exatos com os `geracao_por_hora` já usados em rfi-r02, que herdou esses dados de mendeslobo mas nunca replicou o campo de volta).
- [x] **Corrigido** (`scripts/catalog/cure_producao_escavacao_solo_mendeslobo.py`, idempotente): replica o padrão de rfi-r02 (coeficiente 1 m³ escavado = 1 m³ de material) para as 6 produtividades. Resultado confirmado via `concilium benchmark run --slug AGIS --reset`: `MA-SOLO-ESCAVADO-1CAT` deixa de aparecer no erro (resolvido por completo).
- [ ] **Achado residual — 2 problemas menores, ainda abertos, de escala muito menor que os anteriores:**
  1. `MA-SOLO-ESCAVADO-2CAT`: produção (eap-1_3+eap-1_4, 12.682,4 m³/semana combinado quando ambas ativas) excede em muito o consumo (eap-1_7, 4.212,4 m³/semana) — está convergindo (a contagem de semanas negativas cai a cada rodada do reparo: 26→23→20→...) mas pode não caber na cota de `_MAX_REPAIR_ROUNDS=10` porque cada chamada de `apply_replenishable_delay` só avança 1 semana por rodada antes de auto-interromper (heurística de estagnação). Não confirmado se resolve com mais rodadas ou se precisa de outro ajuste.
  2. `MA-SOLO-ESCAVADO-3CAT`: descoberto um **terceiro consumidor** não contabilizado na análise original — `CPU-TERRA-COMPAC-FINAL-ROCHA` (item `eap-1_10`, "compactação de camada final de aterro de rocha", 24.721,17 m³), além de `CPU-TERRA-CORPO-ATERRO-3CAT` (`eap-1_9`, 981.153,5 m³, já sabidamente exato). Produção total de 3CAT (eap-1_5+eap-1_6 = 981.153,5 m³) cobre exatamente `eap-1_9` sozinho, sem sobra para `eap-1_10` — déficit residual de ~24.721 m³ (exatamente a quantidade de `eap-1_10`). **Decisão de engenharia necessária, não derivável dos dados**: a "camada final de aterro de rocha" é uma parte distinta e adicional do aterro (precisaria de mais 3CAT excavado em algum lugar não identificado), ou é uma sobreposição/redundância com o "corpo do aterro" já contabilizado em `eap-1_9` (nesse caso talvez o consumo de `eap-1_10` não devesse ser adicional)? Não decidido — fica para o usuário/engenheiro de obra.

### F5 — UI (pendente)
- [ ] Projeção de estoque de material gerado na UI a partir de `project_estoque_semanal`; `tanque_sugerido` recebendo `disponibilidade` real no call-site

---

## Relacionados

- ADR-128 — Disponibilidade de Recursos Consumíveis (modelo de estoque estendido por esta ADR)
- ADR-138 §D7 — nota de design que antecipou o flag de proveniência (resolvida em D2)
- ADR-030 — `MaterialEquipe` (D2 estende; `MaterialGerado` de D3 é seu simétrico)
- ADR-053 — separação CPU × Produtividade (fluxos horários vivem em `Producao`)
- ADR-130 — grafo de sinergia (`precondicao` de material ganha contraparte executável)
- ADR-129 — cotação por proximidade (passa a filtrar por origem)
- ADR-016 / ADR-133 — compartilhamento de recursos reutilizáveis (complementar: esta ADR trata fluxo de consumíveis, não contagem de reutilizáveis)
- `docs/engineering/4-development/research/mapa-divergencias-eap-cronograma.md` — análise de bota-fora interno/externo que motivou o caso corte→aterro
