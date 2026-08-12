# ADR-181 — Modelo Unificado de Custo e Calendário de Mobilização/Desmobilização

**Status:** ✅ Implementado _(F1-F6 ✅ 2026-08-12, worktree `mob-demob-modelo-unificado`)_
**Data:** 2026-08-12
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-054 (Workforce Mobilization Policy — `MobilizacaoPolicy` renomeada para `WorkforcePolicy` por D7), ADR-090 (BDI sistemático — MOB como overhead), ADR-105 (Mobilização/Desmobilização integrada), ADR-106 (EquipeCustoEngine/LifecycleEngine — leadtime/lag, F5 bloqueada por dado), ADR-125 (Hierarquia C_prod/C_pool/Contrato), ADR-136 (Custo Mob/Demob no Pool), ADR-137 (Precificação Mob/Demob — Três Modelos Desconexos, **A1 já reaberta pela ADR-176**), ADR-138 (fail-loud condicional, padrão replicado em D3), ADR-165–170 (catálogo RH + composição bottom-up), ADR-175 (formulário sem composição manual de indiretos), ADR-176 (TOP condicional + reconciliação MOB — D4.1/D4.2 generalizados por D2/D4 desta ADR)

---

## Contexto

### Problema

P1. Hoje existem **4 modelos desconexos** para o mesmo evento físico (mobilizar/desmobilizar um recurso produtivo até o canteiro), já documentados de forma incremental por ADRs anteriores mas nunca fechados numa arquitetura-alvo única:

- (a) `WorkforcePolicy`/curva de força (ADR-054, renomeada de `MobilizacaoPolicy` nesta ADR — ver D7) — dimensionamento de quantas equipes existem por semana, não custo.
- (b) `EquipeCustoEngine`/`LifecycleEngine.leadtime_mob_semanas`/`lag_demob_semanas` (ADR-106 F5) — custo de janela de pré/pós-ativação por atividade; "bloqueado por dado" desde a ADR-106, na prática nunca populado no catálogo real.
- (c) Indireto categoria `MOB`/`ADM` da skill-06 (`_mob.py`) — bottom-up por transporte/headcount, com guard anti-double-count parcial da ADR-176 (`_transporte_ja_contabilizado_direto`) que só enxerga `EquipeDireta.custo_mobilizacao_mensal`/`custo_desmobilizacao_mensal`.
- (d) `CampanhaEquipamento.custo_mob`/`custo_demob` (pool) — desconectado dos outros três, exceto pela ponte parcial que a ADR-176 D4.2 já construiu.

P2. **Achado novo desta sessão**: `leadtime_mob_semanas` hoje só afeta **custo**, nunca desloca datas do RCPSP. `infer_mob_windows()` (`mob_scheduling.py`) usa uma janela fixa hardcoded de 7 dias (`safety_margin_days`) antes da primeira atividade, **independente do valor de `leadtime_mob_semanas`** — documentado explicitamente no tutorial do agente ("isso nunca muda" quanto à data). Era possível configurar `leadtime_mob_semanas=8` (8 semanas de custo de MO+equipamento parado) com o cronograma tratando a mobilização como se levasse 1 semana — inconsistência real entre custo e calendário, confirmada por leitura de código (`scheduler.py`/`cpsat_scheduler.py` nunca referenciavam o campo) e pela própria documentação de uso da skill.

P3. Não existia, em lugar nenhum do código, modelagem de **tempo de aquisição/contratação** (procurement leadtime) — o prazo entre decidir contratar/alugar/comprar um recurso e esse recurso estar contratualmente disponível para começar a se mobilizar fisicamente. Busca exaustiva (scheduler, `campanha_equipamento.py`, RH ADR-165/166) não encontrou nenhum campo equivalente; o candidato mais próximo (`vida_util_dias` de RH) é ciclo de revalidação de EPI/exame, não tempo de disponibilização de recurso.

P4. Caso real que expôs o problema (projeto CMOC Ouvidor/GO, contexto `mendeslobo`): a investigação de por que atividades de supressão vegetal mostravam "avanço quase-zero com poucas equipes" levou a duas causas concretas, **nenhuma delas mob/demob em si**, mas que motivaram a auditoria desta ADR:

- `CPU-TERRA-ATI-001` tinha `valor_horario` em **un/h** (árvore) enquanto a EAP quantificava o serviço em **m²** — bug de unidade (fora de escopo desta ADR, tratado separadamente); a tentativa de "consertar" via número de equipes produziu um projeto com 92 equipes (fisicamente implausível) e outro, mais realista (8 equipes), permanentemente infeasible.
- Na mesma investigação, os 4 valores lump de mob/desmob/canteiro/madeira do RFI original (`v7.json` do contexto `mendeslobo`, ~R$674k mob / R$289k desmob / R$1,37M/mês canteiro / R$71,91/m³ madeira) foram encontrados como `fonte_preco: "negociado"` **sem nenhuma composição ou memória de cálculo documentada** em lugar nenhum do repositório. Uma reconstrução manual especulativa (`v12.json`, decomposição "explicado"+"residual") foi feita, mas nunca confirmada com o cliente/fornecedor real.

P5. O guard anti-double-count da ADR-176 (D4.1) só reconhece `EquipeDireta.custo_mobilizacao_mensal`/`custo_desmobilizacao_mensal`. Se mob/demob for decomposto como **insumo de catálogo inserido direto na EAP** (exatamente o que `v12.json` está fazendo para o CMOC Ouvidor, com insumos `TERCEIRIZADO`/`servico` do tipo `SUPVEG-MOB-*`), o guard não enxerga esse caminho — reproduzindo o double-count já confirmado em produção em SERRA_VERDE (ADR-176 P5), caso a categoria indireta `MOB` do perfil do contexto seja ativada no futuro para o mesmo projeto. Hoje, para `mendeslobo`, `categorias_indireto` do perfil está vazio (skill-06 não roda MOB/ADM neste contexto) — não há double-count *ativo*, mas o guard permanece estruturalmente incapaz de detectá-lo se isso mudar.

## Decisão

### D1 — Duas fontes de custo com contratos diferentes, não uma "fonte única"

Investigação confirma que os modelos (b) e (c) não são formas concorrentes de calcular a mesma coisa — são **duas fases fisicamente diferentes** que o sistema historicamente tratou como se fossem uma:

- **Logística de deslocamento físico** (transportar pessoas/equipamento até o canteiro e de volta) — evento de projeto, dirigido por distância × headcount, indireto por natureza (ADR-090 já acertou isso). Fonte: skill-06 `_mob.py`.
- **Janela de ramp-up/ramp-down por atividade** (custo pago com produção reduzida durante mobilização/desmobilização de uma frente específica) — por atividade, custo direto. Fonte: `EquipeCustoEngine` (ADR-106).

Não se decompõe/unifica essas duas em uma fonte só — mantém-se a separação já correta, só formalizando-a como decisão explícita (fecha a ambiguidade que a ADR-137/176 deixaram implícita).

### D2 — Pool vira fonte de custo unitário, não um terceiro modelo independente ✅ Implementado (F5)

`CampanhaEquipamento`/`RecursoContrato.custo_mob_unit`/`custo_demob_unit` deixam de ser valores isolados só para a decisão de perpetuação — passam a alimentar também a agregação de projeto em `_mob.py`. Em vez de recalcular `Σ movimentações × custo_unitário` do zero, usa-se diretamente `RecursoContrato.custo_mob_desmob_contrato` (ADR-073: `n_cadeias × (custo_mob_unit+custo_demob_unit) × quantidade_contratada`, já populado pela ADR-176 D4.2) — esse campo já é o custo REAL realizado, incluindo o desconto de movimentações evitadas por cadeias de perpetuação, então usar direto evita superestimar o desconto com uma contagem ingênua de `quantidade_contratada`.

`_custo_pool_ja_contabilizado_direto(contratos_recurso)` (`_mob.py`) soma esse campo em todos os contratos e é somado aos outros dois descontos (EquipeDireta, insumo tagueado) em `_process_mob_categoria`, via novo parâmetro `contratos_recurso=canonical_in.contratos_recurso`. Retorna `0.0` sem contratos ou sem o campo populado — degradação segura.

### D3 — `leadtime_mob_semanas` não vira obrigatório; ganha aviso condicional de qualidade ✅ Implementado (F3)

Não se torna obrigatório em todo o catálogo (quebraria a maioria das CPUs existentes, mesmo problema que bloqueou a ADR-106 F5). Em vez disso, replica-se o padrão fail-loud condicional do ADR-138: `_checar_leadtime_mob_ausente` (skill-05, `_dimensionamento_orquestracao.py`) roda logo após `custo_total_final` ser resolvido para cada `EquipeDireta` — se `item.leadtime_mob_semanas is None` **e** `custo_total_final > TETO_MATERIALIDADE_MOB` (constante nova em `domain/constants.py`, R$50.000, compartilhada com D6), emite `ValidacaoItem(codigo="VAL-MOB-LEADTIME-01", status="AVISO")` em vez de assumir silenciosamente 0. Abaixo do teto ou com o campo já preenchido (inclusive `0`, presença explícita): nenhum aviso.

### D4 — Guard anti-double-count generalizado por insumo tagueado, não por campo fixo ✅ Implementado (F4)

O guard da ADR-176 (`_transporte_ja_contabilizado_direto`) passa a ser um entre três descontos somados. Novo campo `Insumo.classificacao_mob_demob: bool = False` (`domain/models/catalog/catalogo.py`) marca um insumo cujo custo é evento físico de mob/demob (independente do `tipo` — na prática `TERCEIRIZADO`/`SERVICO`, ex.: `SUPVEG-MOB-*`/`SUPVEG-CANTEIRO-*` do `v12.json`). `_custo_direto_insumo_mob_tagueado(eap, catalogo)` (`_mob.py`) percorre a EAP, resolve a CPU de cada item e soma `quantitativo × Σ(coeficiente × preco_unitario)` sobre as linhas de `composicao_itens` cujo insumo tem a tag — mesmo campo do ADR-138, generalizado para detecção de double-count. Fecha o gap que o `v12.json` do CMOC Ouvidor expôs (P5): decompor mob/demob como insumo de catálogo na EAP, antes, passava batido pelo guard.

**Desvio do texto original desta ADR**: a proposta inicial usava um campo `driver: "mobilizacao"` — renomeado para `classificacao_mob_demob: bool` durante a implementação para evitar colisão de nome com `IndirectoCategoria.driver` (campo pré-existente em `_mob.py` com semântica totalmente diferente: como o custo indireto amortiza — `"one_time"`/`"projeto"`/`"mensal"` — não uma tag de insumo).

### D5 — Calendário de mobilização: separar aquisição de mobilização física, ambas afetando earliest_start no RCPSP ✅ Implementado (F1, F2)

Duas fases sequenciais de "resource readiness", tratadas como **floor absoluto a partir de t=0** (via `max()`, nunca soma aditiva sobre a precedência — procurement pode ocorrer em paralelo com atividades anteriores do projeto):

1. **`leadtime_aquisicao_semanas`** (novo campo, `EapItem`/`Atividade`) — prazo entre decisão de contratar e recurso contratualmente disponível. Sem custo direto associado (fornecedor normalmente não cobra standby nesse período).
2. **`leadtime_mob_semanas`** (existente, ADR-106) — prazo de deslocamento físico após contratação. Passa a **também** empurrar `earliest_start`, além de continuar gerando custo como já fazia (`EquipeCustoEngine`, inalterado).

Implementação:

- `Activity.readiness_weeks` (`scheduling/models.py`) — soma dos dois, `int ≥ 0`, default `0` (backward compat).
- `SerialScheduler._compute_earliest_starts` (`scheduler.py`) — `earliest_start[aid] = max(precedence_earliest, act_map[aid].readiness_weeks)`.
- `CpSatScheduler._add_activity_variables` (`cpsat_scheduler.py`) — `readiness_weeks` vira o lower bound da variável `start` (equivalente a max() expresso no domínio da variável); janela (`window_weeks`) incompatível com o readiness dispara `ScheduleError` fail-loud em vez de truncar silenciosamente.
- `LnsScheduler` herda o fix automaticamente — delega ao `SerialScheduler` (SSGS) internamente, sem variável de start própria.
- `_resolve_spec_activity_readiness_weeks` (`_spec.py`) — resolve o valor a partir do `EapItem` correspondente (mesmo lookup por `item_id` que `_compute_productive_weeks` já fazia — evita reintroduzir a ambiguidade item_id↔atividade_id documentada no issue #142/#125).
- Propagação `EapItem.leadtime_aquisicao_semanas` → `Atividade.leadtime_aquisicao_semanas` (skill-01, mesmo padrão de `leadtime_mob_semanas`); override via `criar_projeto_formulario` (`cronograma[*].leadtime_aquisicao_semanas`); schema (`config/schemas/projeto_spec.schema.json`) documentado com default `0`.

F1 cobriu só o caminho **AUTO** (EAP → `rcpsp_spec` auto-derivado, `a["item_id"] == EapItem.item_id`). **F2 fecha o modo MANUAL**: `_resolve_eap_item_for_activity_id` (`_spec.py`) traduz `activity_id` para `EapItem` em dois passos — primeiro tenta `item_id` direto (AUTO), senão percorre `canonical_in.atividades` procurando `atividade_id == activity_id` e resolve o `EapItem` via `eap_item_id` (MANUAL, UUID explícito) — réplica local da mesma ambiguidade item_id↔atividade_id que `_validacao._build_activity_item_map` já documenta (issue #125/#142), sem importar de lá (`_validacao.py` já importa de `_spec.py` — ciclo).

### D6 — Insumo `fonte_preco="negociado"` acima de teto de materialidade exige composição mínima ✅ Implementado (F6)

Insumo com `fonte_preco: "negociado"` acima de `TETO_MATERIALIDADE_MOB` (R$50.000, mesma constante de D3) deve ter composição mínima documentada, em vez de lump-sum sem rastro. Novo campo `AtributosInsumo.memoria_calculo: str | None` (texto livre) e novo método `ValidadorCPUInsumo.validar_composicao_negociado()` (`domain/validations/cpu_insumo.py`), emitindo `VAL-CAT-NEGOCIADO-01` (`AVISO`) quando `fonte_preco == "negociado"`, `preco_unitario > teto` e `atributos_especificos.memoria_calculo` ausente/vazio. Wired em `_cq_validate_insumos` (`presentation/cli/_commands_manage_helpers_a.py`), rodando junto de `validar_vigencia`/`validar_encoding` no `catalog quality`. Isso teria sinalizado o `v7.json` do CMOC Ouvidor antes de ele virar dado "confiável" sem ser. Fecha a lacuna de origem do RFI (P4).

**Desvio do texto original**: a proposta inicial listava "headcount, distância, verba" como composição estruturada; implementado como campo único de texto livre (`memoria_calculo`) — mob/demob é só um dos casos de uso deste gate (qualquer insumo "negociado" de alto valor se beneficia), então uma estrutura rígida por categoria (headcount/distância/verba) não generalizaria para material/equipamento/outros tipos sem inflar o schema; texto livre é a composição mínima mais simples que ainda força alguém a explicar o número antes de aprovar.

### D7 — Renomear `MobilizacaoPolicy` → `WorkforcePolicy` (ADR-054) ✅ Implementado

`MobilizacaoPolicy` (curva de força — quantas equipes existem por semana e como rampeiam) gerava confusão com o significado de "mobilização" usado no resto desta ADR (deslocamento físico de recurso até o canteiro) — são conceitos disjuntos que só compartilhavam a palavra. O simulador correspondente já se chamava `WorkforcePolicySimulator` (nome correto desde a origem); só a classe de política ficou para trás. Renomeada em todo o código-fonte, testes e a nota técnica `formalizacao_teorica.md`.

**Escopo deliberadamente contido**: mantido sem alteração o nome do campo serializado `mobilizacao_policy` (em `Atividade`/EAP) e o arquivo de override `mobilizacao_policy_override.json` (projetos existentes já persistem dados sob essas chaves) — só o identificador Python `MobilizacaoPolicy` foi renomeado, não a chave JSON/wire. Também não renomeadas as classes da camada HTTP (`presentation/api/schemas.py`): `MobilizacaoPolicyIn`/`MobilizacaoPolicyUpsertRequest` — são DTOs de um contrato de API adjacente, não o nome da classe pedido, e renomeá-las mudaria nomes de schema no OpenAPI gerado (superfície pública, fora do escopo pedido).

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Unificar os 4 modelos numa única fonte de custo | Rejeitada — (b) e (c) são fases fisicamente distintas (contratação/deslocamento vs. ramp-up produtivo); forçar uma fonte só replicaria o erro que a ADR-136 F5 já identificou (tratar cenários estruturalmente diferentes como duplicados). |
| A2 | `leadtime_mob_semanas` obrigatório em todo catálogo | Rejeitada — mesma trava de dado que bloqueou a ADR-106 F5; quebraria a maioria das CPUs existentes sem trazer valor proporcional. |
| A3 | `readiness_weeks` aditivo sobre o earliest_start de precedência (em vez de floor via max()) | Rejeitada — superestimaria sistematicamente o prazo em qualquer atividade cujo predecessor já leve mais tempo que o readiness (procurement pode ocorrer em paralelo); max() é o modelo correto na ausência de um otimizador de duas etapas completo. |
| A4 | `driver: "mobilizacao"` como nome do campo de tag em D4 | Rejeitada durante a implementação — colidia com `IndirectoCategoria.driver` pré-existente em `_mob.py` (semântica diferente); usado `classificacao_mob_demob: bool` em vez disso (ver nota em D4). |
| A5 | Composição estruturada (headcount/distância/verba) como campos típados em D6 | Rejeitada — mob/demob é só um caso de uso do gate; estrutura rígida por categoria não generalizaria para outros tipos de insumo "negociado" (material, equipamento). Texto livre (`memoria_calculo`) cobre o mesmo objetivo (forçar explicação) sem inflar o schema por categoria. |

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Calendário deixa de ser sistematicamente otimista em mobilização | `leadtime_mob_semanas`/`leadtime_aquisicao_semanas` agora empurram `earliest_start` no RCPSP (SerialScheduler, CP-SAT, LNS), nos modos AUTO e MANUAL — antes, só afetavam custo. |
| Double-count estrutural do v12 (CMOC Ouvidor) tem caminho de correção | D4 fecha o mesmo tipo de brecha que a ADR-176 já corrigiu para `EquipeDireta`, agora generalizada para insumo de catálogo tagueado (`classificacao_mob_demob`) e para pool (`custo_mob_desmob_contrato`) — os 3 modelos históricos da ADR-137 agora descontam do indireto MOB. |
| Falha alta em vez de truncamento silencioso | Janela incompatível com o readiness dispara `ScheduleError` explícito (CP-SAT), não um cronograma artificialmente comprimido. |
| Ausência de leadtime em atividade material vira sinal visível | `VAL-MOB-LEADTIME-01` (D3) substitui "assume 0 silenciosamente" por aviso de qualidade condicional acima do teto — sem exigir preenchimento em todo catálogo. |
| Origem de dado "negociado" deixa de ser aceita sem rastro | `VAL-CAT-NEGOCIADO-01` (D6) teria sinalizado o `v7.json` do RFI antes de virar dado "confiável" sem ser. |
| `MobilizacaoPolicy`/mobilização física deixam de compartilhar nome sem compartilhar significado | D7 — curva de força (`WorkforcePolicy`) e deslocamento físico (mob/demob) são conceitos disjuntos; nome deixa de sugerir relação que não existe. |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| `readiness_weeks` pode tornar projetos com leadtime alto e prazo apertado infeasible onde antes "funcionavam" (silenciosamente incorretos) | Comportamento correto e esperado (mesmo padrão aceito na ADR-136 D2) — comunicar como correção de bug de calendário, não mudança de comportamento neutra. |
| Nenhum dado real de `leadtime_aquisicao_semanas`/`classificacao_mob_demob`/`memoria_calculo` existe ainda no catálogo | Defaults (`0`/`False`/`None`) preservam comportamento idêntico ao anterior até que o dado seja preenchido — nenhuma das 3 fases quebra catálogo existente. |
| Renomear `MobilizacaoPolicy` é breaking change para qualquer código externo ao repo que importe o nome antigo | Sem alias de retrocompatibilidade (mesmo padrão de renomes anteriores aceitos, ex. ADR-136 D2) — nome antigo não existe mais em `_LAZY_MAP` de `domain/models/__init__.py`. Campo serializado (`mobilizacao_policy`) e arquivo de override não mudaram, então dado persistido de projeto não é afetado. |

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | Calendário: `leadtime_aquisicao_semanas` (novo) + `leadtime_mob_semanas` (existente) empurram `earliest_start` no RCPSP (SerialScheduler + CP-SAT + LNS via SSGS); caminho AUTO (EAP auto-derivada) | ✅ Implementado |
| F2 | Modo MANUAL: propagar `readiness_weeks` também quando `rcpsp_spec` usa `atividade_id`/UUID explícito | ✅ Implementado |
| F3 | D3 — aviso de qualidade condicional (`VAL-MOB-LEADTIME-01`) quando dimensionamento de equipe direta roda sem `leadtime_mob_semanas` acima do teto de materialidade | ✅ Implementado |
| F4 | D4 — guard anti-double-count generalizado por insumo tagueado (`classificacao_mob_demob`) na composição de CPU usada na EAP | ✅ Implementado |
| F5 | D2 — pool (`RecursoContrato.custo_mob_desmob_contrato`) vira terceiro desconto consumido pela agregação de projeto em `_mob.py` | ✅ Implementado |
| F6 | D6 — gate de qualidade de catálogo (`VAL-CAT-NEGOCIADO-01`): `fonte_preco="negociado"` acima do teto de materialidade exige `atributos_especificos.memoria_calculo` | ✅ Implementado |
| F7 | D7 — renomear `MobilizacaoPolicy` → `WorkforcePolicy` em todo o código-fonte, testes e documentação técnica viva | ✅ Implementado |

## Definition of Done

### Fase 1
- [x] `Activity.readiness_weeks: int = 0` (`scheduling/models.py`), validado `≥ 0` em `__post_init__`
- [x] `SerialScheduler._compute_earliest_starts` aplica `max(precedence_earliest, readiness_weeks)` — floor, não soma
- [x] `CpSatScheduler._add_activity_variables` usa `readiness_weeks` como lower bound de `start`; `ScheduleError` fail-loud quando incompatível com `window_weeks`
- [x] `LnsScheduler` herda o fix sem mudança própria (delega ao SSGS)
- [x] `EapItem.leadtime_aquisicao_semanas`/`Atividade.leadtime_aquisicao_semanas` (canonical, `_eap.py`), propagado em skill-01 (`_build_atividades_for_item`)
- [x] Override via `criar_projeto_formulario` (`cronograma[*].leadtime_aquisicao_semanas`, `formulario.py`) + schema (`projeto_spec.schema.json`)
- [x] `_resolve_spec_activity_readiness_weeks` (`_spec.py`) resolve a partir do `EapItem` pelo mesmo lookup por `item_id` de `_compute_productive_weeks` — sem reintroduzir ambiguidade item_id↔atividade_id (issue #125/#142)
- [x] Testes cobrindo: default 0 (backward compat), floor vs. soma aditiva sobre precedência, readiness binding quando precedência permitiria início mais cedo, lower bound no CP-SAT, `ScheduleError` em janela incompatível, resolução a partir de `EapItem` (incluindo canonical ausente e item desconhecido) — `test_adr181_readiness_weeks.py`
- [x] Suíte completa (scheduling + skills + domain/models) + ruff + ty sem novos erros

### Fase 2
- [x] `_resolve_eap_item_for_activity_id` (`_spec.py`) traduz `activity_id` → `EapItem` via `item_id` direto (AUTO) ou via `canonical_in.atividades[*].atividade_id` → `eap_item_id` (MANUAL)
- [x] `_resolve_spec_activity_readiness_weeks` usa o novo resolver — cobre os dois modos com a mesma função
- [x] Testes cobrindo: resolução via UUID de atividade explícito, UUID desconhecido (retorna 0) — `test_adr181_readiness_weeks.py::TestSpecActivityReadinessResolution`
- [x] Suíte completa + ruff + ty sem novos erros

### Fase 3
- [x] `TETO_MATERIALIDADE_MOB: float = 50_000.0` (`domain/constants.py`), compartilhado com F6/D6
- [x] `_checar_leadtime_mob_ausente(item, custo_total_final, validacoes)` (skill-05, `_dimensionamento_orquestracao.py`) — `VAL-MOB-LEADTIME-01`/`AVISO` quando `leadtime_mob_semanas is None` e custo acima do teto; presença explícita (inclusive `0`) nunca dispara
- [x] Chamado em `_dimensionar_item_equipe` logo após `custo_total_final` ser resolvido
- [x] Testes cobrindo: acima/abaixo do teto, presença explícita do campo, limite exclusivo no teto — `test_adr181_f3_leadtime_mob_aviso.py`
- [x] Suíte completa (skills 05) + ruff + ty sem novos erros

### Fase 4
- [x] `Insumo.classificacao_mob_demob: bool = False` (`domain/models/catalog/catalogo.py`)
- [x] `_custo_direto_insumo_mob_tagueado(eap, catalogo)` (`_mob.py`) — soma `quantitativo × Σ(coeficiente × preco_unitario)` sobre `composicao_itens` tagueados, por item de EAP
- [x] `_process_mob_categoria` soma esse desconto ao de `EquipeDireta` (parâmetro novo `eap`, propagado de `canonical_in.eap` em `skill.py`)
- [x] Testes cobrindo: sem insumo tagueado, soma simples, multiplicação por quantitativo, múltiplos itens de EAP, CPU desconhecida, integração com o lump (isolado e somado ao desconto de `EquipeDireta`) — `test_adr181_f4_guard_insumo_tagueado.py`
- [x] Suíte completa (skills 06, validations) + ruff + ty sem novos erros

### Fase 5
- [x] `_custo_pool_ja_contabilizado_direto(contratos_recurso)` (`_mob.py`) — soma `RecursoContrato.custo_mob_desmob_contrato` de todos os contratos
- [x] `_process_mob_categoria` soma esse terceiro desconto (parâmetro novo `contratos_recurso`, propagado de `canonical_in.contratos_recurso`)
- [x] Testes cobrindo: soma multi-contrato, contrato sem o campo, uso do custo já realizado (não quantidade bruta), integração com os outros 2 descontos simultaneamente — `test_adr181_f5_pool_ja_contabilizado.py`
- [x] Suíte completa (skills 06) + ruff + ty sem novos erros

### Fase 6
- [x] `AtributosInsumo.memoria_calculo: str | None = None` (`domain/models/catalog/catalogo.py`)
- [x] `ValidadorCPUInsumo.validar_composicao_negociado(insumo)` (`domain/validations/cpu_insumo.py`) — `VAL-CAT-NEGOCIADO-01`/`AVISO`
- [x] Wired em `_cq_validate_insumos` (`presentation/cli/_commands_manage_helpers_a.py`), junto de `validar_vigencia`/`validar_encoding`
- [x] Testes cobrindo: fonte_preco≠negociado, abaixo do teto, acima sem composição, acima com `memoria_calculo`, string vazia não conta, limite exclusivo no teto — `test_cpu_insumo_validation2.py::TestValidarComposicaoNegociado`
- [x] Suíte completa (validations) + ruff + ty sem novos erros

### Fase 7
- [x] `MobilizacaoPolicy` → `WorkforcePolicy` em `domain/models/planning/mobilizacao.py`, `domain/services/planning/mobilizacao_simulator.py`, `domain/models/__init__.py` (`_LAZY_MAP`), `domain/models/canonical/_eap.py`, `application/services/_concilium_service_helpers.py`, `application/skills/manifests/04-cronograma/_skill_helpers/_scheduling.py`, `presentation/api/routes/mobilization.py`, `presentation/api/schemas.py`, `docs/engineering/5-technical_notes/formalizacao_teorica.md`
- [x] Campo serializado `mobilizacao_policy` e arquivo `mobilizacao_policy_override.json` preservados (ver nota de escopo em D7)
- [x] Classes de DTO da API (`MobilizacaoPolicyIn`/`MobilizacaoPolicyUpsertRequest`) preservadas (ver nota de escopo em D7)
- [x] Testes existentes atualizados (`test_mobilizacao_simulator.py`, `test_concilium_service_helpers2.py`, `test_fat_concilium_service.py`, `test_nep031_lacunas_modelo.py`, `test_skill_04_wmp_integration.py`) — nomes de classe de teste (`TestMobilizacaoPolicyValidation` etc.) preservados intencionalmente, só a referência ao símbolo renomeado foi atualizada
- [x] Suíte completa + ruff sem novos erros

### Validação final (todas as fases)
- [x] Suíte completa: 15235 testes verdes (+29 sobre o baseline de F1), 0 regressão
- [x] `ruff check` e `ty check` sem novos erros em nenhum arquivo tocado (incluindo os diretórios de skill com hífen, checados explicitamente por caminho)

---

## Relacionados

- ADR-090 — BDI sistemático (MOB como overhead → BDI_indireto; D1 desta ADR mantém essa fronteira)
- ADR-105 — Mobilização/Desmobilização integrada (workforce + equipment)
- ADR-106 — EquipeCustoEngine/LifecycleEngine (F5 — janela de custo — permanece como estava; D5 desta ADR adiciona o efeito de calendário que faltava)
- ADR-125 — Hierarquia C_prod/C_pool/Contrato (mob/demob fora de C_pool — decisão que permanece válida)
- ADR-136 — Custo de Mob/Demob no Pool (base sobre a qual D2 constrói a fonte de custo unitário)
- ADR-137 — Precificação de Mob/Demob: Três Modelos Desconexos (A1 reaberta pela ADR-176; D1/D2 desta ADR fecham a reabertura formalizando a separação em duas fontes)
- ADR-138 — Fail-loud condicional para dado de composição ausente (padrão replicado em D3)
- ADR-165–170 — Catálogo RH + composição bottom-up
- ADR-175 — Formulário sem composição manual de indiretos
- ADR-176 — TOP condicional + reconciliação MOB (D4.1 é a base que D4 desta ADR generaliza; D4.2 é a base que D2 desta ADR generaliza; D5 da ADR-176 — reconciliar `RegimeEquipamento` — permanece proposto, fora de escopo aqui)
- ADR-054 — Workforce Mobilization Policy (classe `MobilizacaoPolicy` renomeada para `WorkforcePolicy` por D7 desta ADR; conceito e comportamento da curva de força não mudam, só o nome)
