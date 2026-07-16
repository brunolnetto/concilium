# ADR-128 — Disponibilidade de Recursos Consumíveis: Estoque, Taxa de Consumo e Reabastecimento (Diesel, Combustível, Material)

**Status:** ⚠️ Parcialmente Implementado _(2026-07-15: F1/F2/F3/F5 completos — F2 inclui repropagação de precedência (Fase 2b), ver nota; F5 conecta o motor ao pipeline real de skill-04 e a `Escopo.logistica_consumiveis` como fonte de dado real de projeto; F4 permanece com o dashboard/UI ainda não conectado a essa fonte, ver nota)_
**Data:** 2026-07-02
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-107 (generalização tipo_combustivel), ADR-090 (BDI sistemático diesel/material), ADR-046 (motor RCPSP)

---

## Contexto

### Problema

P1. **Recursos consumíveis (diesel/combustível, material) hoje são modelados apenas como taxa de consumo, sem estoque.** `AtributosInsumo.consumo_litros_hora` (L/h) é um fluxo puro — não há capacidade de tanque, estoque inicial, ou reabastecimento como conceito de domínio. A única referência a "tanque" no sistema é uma heurística de **UI** (variável `tanque_sugerido = pico_l * 1.5 * 2`, em `src/concilium/presentation/ui/organisms/layout.py`), que é puramente apresentacional: calcula um dimensionamento sugerido para exibição, mas não alimenta o motor de agendamento nem é uma restrição real de disponibilidade.

P2. **O motor RCPSP (`src/concilium/application/scheduling/models.py`) assume disponibilidade irrestrita de recursos consumíveis.** `ResourcePool` modela apenas recursos contáveis/reutilizáveis (`resources: dict[str, int]`) — não existe um conceito de recurso que se esgota com o uso e precisa ser reabastecido. Se a taxa de consumo de uma atividade (diesel de uma frota de equipamentos, por exemplo) supera a capacidade de reabastecimento real (frequência/capacidade de comboios de combustível, disponibilidade de fornecedor de material), o cronograma gerado hoje **não captura esse risco de atraso** — ele é invisível até acontecer em campo.

P3. **Material já tem campos de proveniência não operacionalizados.** `AtributosInsumo.fornecedor_referencia` e `prazo_entrega` existem no schema desde a modelagem original do catálogo, mas — conforme mapeado na exploração de curadoria do catálogo — nenhuma lógica de negócio os lê hoje. Eles são candidatos naturais a alimentar o lead time de reabastecimento que esta ADR propõe modelar, em vez de introduzir campos redundantes.

P4. **Risco de negócio concreto:** em obras com equipamentos de grande porte (frota de escavação, terraplenagem), a indisponibilidade de comboio de diesel no momento necessário — ou capacidade de tanque do equipamento insuficiente para o turno — já gera atraso real em campo. Hoje o modelo de custo (ADR-090) sabe *quanto* diesel custa, mas não *se* ele estará disponível a tempo.

---

## Decisão

### D1 — Modelo de estoque/disponibilidade para recursos consumíveis

Novo conceito de domínio, aplicável a `Insumo` do tipo `MATERIAL` ou `EQUIPAMENTO`/categoria `COMBUSTIVEL`, opcional (não retroativamente obrigatório):

```python
@dataclass
class DisponibilidadeConsumivel:
    capacidade_armazenamento: float | None   # ex.: litros (tanque), unidades (material) — None = sem limite modelado
    estoque_inicial: float = 0.0
    taxa_reabastecimento_max: float | None   # unidade/semana — capacidade logística (ex.: comboio)
    lead_time_reabastecimento_dias: float | None  # tempo entre pedido e chegada
```

`lead_time_reabastecimento_dias` reaproveita semanticamente o campo já existente `AtributosInsumo.prazo_entrega` (materiais) em vez de duplicá-lo — mas com uma ressalva importante: `prazo_entrega` hoje é `str | None`, texto livre (ex.: `"Imediato"`, `"15 dias"`), não um número. Reaproveitá-lo exige uma etapa de normalização/parsing (ou, alternativamente, migrar o campo para um tipo estruturado em uma ADR de catálogo futura) antes de alimentar `lead_time_reabastecimento_dias: float`. Sem essa normalização, a proposta não é implementável como está — registra-se aqui como pré-requisito explícito da Fase 3. Para diesel/combustível, não há campo equivalente hoje; `lead_time_reabastecimento_dias` seria um dado novo.

### D2 — Restrição de disponibilidade no motor RCPSP

Nova classe de recurso no motor de agendamento (`src/concilium/application/scheduling/models.py`), paralela a `ResourcePool` mas com semântica de fluxo/estoque:

```python
@dataclass
class ReplenishableResource:
    resource_id: str
    disponibilidade: DisponibilidadeConsumivel
    consumo_por_semana: dict[str, float]  # activity_id -> taxa de consumo projetada
```

O agendador projeta o nível de estoque semana a semana (`estoque[t] = estoque[t-1] + reabastecimento[t] - consumo[t]`); se o estoque projetado ficar negativo em algum ponto do cronograma proposto, a atividade correspondente recebe uma folga adicional (delay) até que o reabastecimento acumulado torne o consumo viável — análogo ao tratamento de recurso reutilizável indisponível, mas com contabilidade de fluxo em vez de contagem de unidades.

### D3 — Diesel/combustível: taxa de reabastecimento vem da capacidade logística, não do preço

`taxa_reabastecimento_max` para combustível é um dado operacional (capacidade de comboio × frequência de viagens), não um dado de catálogo de preço — deve ser inserido no nível de **projeto/escopo** (condições logísticas do sítio de obra), não no `Insumo` global do catálogo, para não misturar dado de preço com dado de logística de canteiro específico.

### D4 — UI: `tanque_sugerido` passa a derivar do mesmo modelo

O cálculo hoje em `src/concilium/presentation/ui/organisms/layout.py` (bloco que computa `tanque_sugerido`) deixa de ser uma heurística isolada e passa a ler `DisponibilidadeConsumivel` quando presente, mantendo o fallback heurístico atual (`pico_l × 1.5 × 2`) quando o dado real não estiver preenchido — single source of truth entre dashboard e motor de agendamento.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Modelar disponibilidade só como alerta de dashboard (não afeta o cronograma) | Não resolve P4 — o objetivo é que o RCPSP capture o atraso, não só reportá-lo depois |
| A2 | Estoque/capacidade como campo obrigatório em todo `Insumo` consumível | Rejeitado — a maioria dos projetos hoje não tem esse dado; opcionalidade evita quebrar o catálogo existente |
| A3 | Colocar `taxa_reabastecimento_max` no catálogo (nível de `Insumo`) | Rejeitado — capacidade logística (comboio) é uma característica do canteiro/projeto, não do insumo em si; dois projetos usando o mesmo diesel têm capacidades logísticas diferentes |
| A4 | Reaproveitar `ResourcePool` existente para consumíveis, sem nova classe | Rejeitado — `ResourcePool` é contagem de unidades discretas reutilizáveis; misturar semântica de fluxo/estoque no mesmo tipo geraria ambiguidade no motor |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Risco de atraso visível no cronograma | Indisponibilidade de diesel/material passa a gerar folga/atraso explícito no RCPSP, não só ser descoberto em campo |
| Reaproveita campos mortos do catálogo | `prazo_entrega`/`fornecedor_referencia` (identificados como não utilizados) ganham consumidor real |
| Consistência dashboard ↔ motor | `tanque_sugerido` deixa de ser número isolado sem lastro operacional |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Motor RCPSP ganha complexidade (nova classe de restrição) | Escopo tratado como opt-in: sem `DisponibilidadeConsumivel` preenchida, comportamento atual (disponibilidade irrestrita) é preservado |
| Dado logístico (capacidade de comboio) raramente disponível hoje | Introduzir como campo opcional de projeto/escopo; UI pode sugerir default a partir de heurística existente |
| Acoplamento entre camada de custo (ADR-090) e camada de cronograma | Manter `DisponibilidadeConsumivel` como modelo de agendamento, não de custo — custo de diesel continua vindo de `pu_calculator`/BDI, inalterado |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `DisponibilidadeConsumivel` no domínio; opcional em `Insumo`/`Escopo` | ✅ Implementado |
| F2 | `ReplenishableResource` no motor de agendamento; projeção de estoque semana a semana; repropagação de atraso para sucessores no DAG (Fase 2b) | ✅ Implementado como duas passadas de reparo pós-CP-SAT em laço de ponto fixo (ver nota de implementação) |
| F3 | Parsing/normalização de `prazo_entrega` (hoje `str \| None`, texto livre) para dias numéricos; reaproveitamento como lead time de reabastecimento de material | ✅ Implementado |
| F4 | `tanque_sugerido` (UI) lendo `DisponibilidadeConsumivel` com fallback heurístico atual | ⚠️ Implementado como capacidade pura (ver nota de implementação) |
| F5 | Integração no pipeline real de skill-04 (`CpSatScheduler` + `build_replenishable_resources`, antes chamados só em teste); `Escopo.logistica_consumiveis` como fonte real de dado de projeto (fecha a lacuna registrada em F4 — ver nota); relatório causal de atraso por recurso/atividade (`VAL-ESTOQUE-DELAY-01/02`) | ✅ Implementado |

### Nota de implementação (2026-07-08)

**F2 — estratégia escolhida:** em vez de embutir a contabilidade de estoque diretamente
no modelo CP-SAT (ex.: `reservoir constraint` do OR-Tools, que exigiria modelar eventos de
consumo/reabastecimento como variáveis de tempo do solver — escopo maior do que cabia nesta
entrega), a Fase 2 foi implementada como um **passo de reparo pós-processamento**:
`concilium.application.scheduling.replenishable.apply_replenishable_delay` projeta o
estoque semanal (`project_estoque_semanal`) sobre a solução já produzida pelo CP-SAT e, se
inviável, atrasa iterativamente a atividade consumidora até o reabastecimento acumulado
tornar o consumo viável. `CpSatScheduler.schedule()` aceita `replenishable_resources`
opcional (default `None` → comportamento idêntico ao pré-ADR-128, testado como regressão
zero). **Limitação conhecida à época (fechada em Fase 2b, ver abaixo):** o atraso não era
repropagado para sucessores no DAG de precedências — um cronograma onde a atividade
atrasada tem sucessores dependentes podia gerar uma violação de precedência que essa
primeira fase não resolvia.

**F2b — repropagação de atraso para sucessores (2026-07-12):** fecha a limitação acima com
uma **segunda passada determinística de reparo**, não com um reservoir constraint nativo
no CP-SAT — a mesma razão de escopo já registrada acima para a Fase 2 original se aplica
igualmente aqui (embutir a contabilidade de estoque diretamente no solver continua sendo um
rewrite maior e mais arriscado do que o reparo pós-processamento).
`concilium.application.scheduling.precedence_repropagation.repropagate_precedence_delays`
percorre o `ActivityDAG` em ordem topológica (considerando `dag.precedence` e as
precedências estendidas SS/FF/FS+lag, tanto `dag.extended_precedences` quanto as passadas
explicitamente ao scheduler) e empurra — nunca antecipa — qualquer sucessor cuja posição
atual viole a precedência contra seu predecessor (possivelmente já deslocado por esta mesma
função ou pelo reparo de estoque), cascateando transitivamente ao longo da cadeia. Essa
função só conhece precedência — nada sabe sobre recursos/estoque.

`CpSatScheduler.schedule()` orquestra as duas passadas (reparo de estoque +
repropagação de precedência) em um **laço de ponto fixo** limitado a
`_MAX_REPAIR_ROUNDS = 10` rodadas: repropagar um atraso pode empurrar uma atividade que
consome um *outro* recurso consumível, reabrindo uma violação de estoque já resolvida
para esse recurso (e vice-versa) — daí a necessidade de iterar em vez de uma única
passada. Em cada rodada: aplica-se `apply_replenishable_delay` para cada
`ReplenishableResource`, depois `repropagate_precedence_delays` uma vez; o laço para
assim que uma rodada não produz nenhuma mudança de posição (ponto fixo), ou ao atingir a
cota. **10 é um limite heurístico, não uma prova formal de convergência** — não há uma
demonstração de que o processo sempre converge nesse número de rodadas para qualquer DAG
arbitrário (em teoria, alternâncias adversariais entre múltiplos recursos consumíveis
poderiam, em tese, exigir mais rodadas); na prática, cronogramas reais estabilizam em 1-3
rodadas, e o valor foi escolhido generoso o suficiente para cobrir isso com folga sem
custo de desempenho perceptível. **`_validate_repaired_schedule` permanece inalterado como
rede de segurança final:** nem o reparo de estoque nem a repropagação de precedência sabem
avaliar capacidade de `ResourcePool` (recursos reutilizáveis) ou o horizonte — se o laço de
ponto fixo esgotar a cota sem estabilizar, ou se o cronograma final ainda violar
capacidade de pool/horizonte (por exemplo, uma repropagação que empurra duas atividades a
colidirem sobre um recurso reutilizável compartilhado — cenário coberto em teste), o
scheduler continua marcando o `ScheduleOutput` como `feasible=False` em vez de devolver um
cronograma inválido como viável.

**F4 — estado da conexão UI↔dado real:** `calcular_tanque_sugerido()` (função pura,
testada) já prioriza `DisponibilidadeConsumivel.capacidade_armazenamento` sobre a
heurística quando presente, e `_render_cube_diesel_metrics` aceita esse dado como
parâmetro opcional. O que **não** foi feito nesta entrega: plugar uma fonte real de
`DisponibilidadeConsumivel` em nível de projeto/escopo (D3) ao call site do dashboard —
esse modelo de dado de projeto/canteiro ainda não existe no sistema; a UI hoje sempre
chama com `disponibilidade=None`, preservando o comportamento heurístico atual.

### Nota de implementação (2026-07-15) — F5

Até esta entrega, `CpSatScheduler.schedule()` aceitava `replenishable_resources` desde a
Fase 2 e `build_replenishable_resources` (ADR-139 F4) já sabia montar os recursos a
partir do catálogo — mas **nenhum código de produção os chamava**; ambos só eram
exercitados por teste. F5 fecha essa lacuna, com escopo completo (motor + config de
usuário + relatório de causa), e fecha também o `D3`/`F4` acima registrado como pendente
("modelo de dado de projeto/canteiro ainda não existe no sistema") — agora existe, para
o *scheduler* (não para o dashboard, ver ressalva abaixo).

**Terceira fonte de restrição — `Escopo.logistica_consumiveis`:** `build_replenishable_resources`
ganhou um parâmetro `disponibilidade_overrides: dict[str, DisponibilidadeConsumivel] | None`
(`replenishable_builder.py`). Antes, um insumo só virava `ReplenishableResource` se tivesse
`atributos_especificos.disponibilidade` no catálogo OU fosse produzido internamente
(`GERACAO_INTERNA`, ADR-139). Diesel raramente cai em qualquer dos dois casos — é comprado
externamente e o catálogo hoje quase nunca declara `disponibilidade` para ele. O novo
campo opcional `Escopo.logistica_consumiveis: dict[insumo_id, LogisticaConsumivelConfig] | None`
(`domain/models/project/escopo.py`), exposto via `gerir_escopo` (MCP) → `create_escopo`
(repositório/store) → propagado automaticamente para `inputs["logistica_consumiveis"]` de
toda skill via `escopo_meta` (nenhuma mudança necessária em `runtime/mixins/execution.py`,
que já espalha todo o meta do escopo nos inputs) — dá ao *projeto* o poder de restringir um
insumo mesmo sem nenhuma declaração de catálogo. Overrides de projeto têm prioridade sobre
declaração de catálogo quando ambos existem para o mesmo insumo (dado real de canteiro >
default de catálogo).

**Relatório causal de atraso:** antes, o laço de reparo só produzia um booleano
implícito (`feasible`) — nenhum registro de *qual* recurso atrasou *qual* atividade
sobrevivia. `apply_replenishable_delay` (`replenishable.py`) ganhou um parâmetro opcional
`delay_causes: dict[tuple[str, str], int] | None` (default `None` — compatível com todo
call site/teste existente) que acumula `{(resource_id, activity_id): semanas_de_atraso}`;
`CpSatScheduler.schedule()` popula um novo campo aditivo `ScheduleOutput.estoque_delays:
list[EstoqueDelayCause]`, propagado até o `cronograma` canônico
(`ScheduleCandidateCanonical`/`Cronograma.estoque_delays`, ambos aditivos). Skill-04 traduz
isso em dois códigos novos (prefixo `VAL-ESTOQUE-*`, já estabelecido por
`VAL-ESTOQUE-PROD-01`/`VAL-ESTOQUE-CAP-01`, não `VAL-SCHED-*`): `VAL-ESTOQUE-DELAY-01`
(AVISO, atraso reparado, cronograma segue viável) e `VAL-ESTOQUE-DELAY-02` (ERRO, atraso
não reparável — bloqueia downstream por `gate=true`). Um terceiro código,
`VAL-ESTOQUE-ALGO-01` (AVISO), cobre o caso em que a restrição foi declarada mas o
algoritmo de scheduling selecionado não é CP-SAT (única implementação que aplica
`ReplenishableResource` hoje) — torna visível a restrição silenciosamente ignorada em vez
de um no-op mudo.

**Por que um parâmetro mutável em vez de mudar o tipo de retorno:** `apply_replenishable_delay`
já tinha múltiplos call sites/testes assumindo `list[ScheduledActivity]` como retorno; um
terceiro parâmetro opcional com default `None` preserva 100% de compatibilidade, seguindo o
mesmo idioma já usado em todo o skill-04 (`validacoes: list` acumulado por referência).

**`selector._explore_cpsat` precisou de um branch não-raising:** antes, qualquer
infeasibilidade do CP-SAT levantava `ScheduleError` (tratada como falha técnica de
pipeline). Estoque de consumível insuficiente é um resultado de **negócio** (faltou
diesel), não uma falha de solver — levantar exceção interromperia o pipeline de forma
incorreta. Quando `sched.feasible is False` e `sched.estoque_delays` não é vazio,
`_explore_cpsat` agora retorna `ExploreResult(..., error="estoque_insuficiente")` sem
lançar, espelhando o padrão já usado por `_compare_cpsat` (utilitário de comparação,
nunca levanta). Toda outra causa de infeasibilidade continua levantando `ScheduleError`
inalterada.

**Correção de um gap encontrado durante a implementação:** `_validate_repaired_schedule`
(rede de segurança final do laço de ponto fixo) nunca reverificava estoque negativo —
só checava precedência/capacidade de pool/horizonte. Quando o laço esgota
`_MAX_REPAIR_ROUNDS` sem convergir (ex.: `capacidade_armazenamento` menor que o consumo de
uma única semana — nenhum atraso jamais resolve isso, pois o teto sempre limita o estoque
antes do consumo), o cronograma podia ficar com estoque ainda negativo e mesmo assim ser
reportado `feasible=True`. `CpSatScheduler.schedule()` ganhou uma checagem explícita
(`has_estoque_negativo(project_estoque_semanal(...))`) após o laço, fechando esse caso —
coberto por teste dedicado (`test_stock_permanently_negative_after_repair_rounds_exhausted_marks_infeasible`).

**Ressalva importante — o que F5 NÃO fecha:** esta entrega conecta o *scheduler*
(skill-04), não o *dashboard*. A linha de DoD da F4 sobre "fonte real de
`DisponibilidadeConsumivel` conectada ao dashboard" permanece pendente — `tanque_sugerido`/
`_render_cube_diesel_metrics` continuam recebendo `disponibilidade=None` sempre; ligar a UI
à mesma fonte de projeto (`Escopo.logistica_consumiveis`) é trabalho futuro, não coberto aqui.

## Definition of Done

### Fase 1
- [x] `DisponibilidadeConsumivel` definido, validado (capacidade/estoque ≥ 0), campos opcionais

### Fase 2
- [x] Projeção de estoque semanal implementada e testada com cenário de estoque negativo → atraso
- [x] Cenário sem `DisponibilidadeConsumivel` preenchida reproduz exatamente o comportamento atual (regressão zero)
- [x] Atraso repropagado para sucessores no DAG de precedências (Fase 2b — `repropagate_precedence_delays` + laço de ponto fixo em `CpSatScheduler.schedule()`; `_validate_repaired_schedule` permanece como rede de segurança para capacidade de pool/horizonte)

### Fase 3-4
- [x] Estratégia de parsing de `prazo_entrega` (texto livre → dias) definida e testada com os valores reais hoje presentes no catálogo (ex.: "Imediato")
- [x] `prazo_entrega` de material alimentando lead time sem novo campo duplicado (`DisponibilidadeConsumivel.from_prazo_entrega`)
- [x] `tanque_sugerido` consistente entre UI e modelo quando dado real está presente (capacidade pura implementada e testada)
- [ ] Fonte real de `DisponibilidadeConsumivel` em nível de projeto/escopo conectada **ao dashboard** (pendente — F5 conecta o *scheduler*, não a UI; ver nota de implementação F5)

### Fase 5
- [x] `build_replenishable_resources` chamado a partir do pipeline real de skill-04 (não só de teste), com regressão zero provada por integração fim a fim
- [x] `Escopo.logistica_consumiveis` exposto via `gerir_escopo` → `create_escopo` (repositório/store) → propagado a `inputs` de toda skill sem mudança em `execution.py`
- [x] Cenário diesel-restrito (config de projeto, sem declaração de catálogo) delatando atraso real, causal, através de `run_cronograma`
- [x] `VAL-ESTOQUE-DELAY-01` (AVISO, reparado) / `VAL-ESTOQUE-DELAY-02` (ERRO, irreparável) / `VAL-ESTOQUE-ALGO-01` (AVISO, algoritmo não suporta) disparando corretamente, sem crash no caso ERRO (`selector._explore_cpsat` não-raising)

---

## Relacionados

- ADR-107: Generalização do tipo de combustível — taxonomia de `TipoCombustivel` reaproveitada aqui
- ADR-090: BDI sistemático diesel/material — camada de custo, permanece inalterada; esta ADR trata de disponibilidade/risco de atraso, não de custo
- ADR-046: Implementação RCPSP completa — motor de agendamento onde `ReplenishableResource` se insere
