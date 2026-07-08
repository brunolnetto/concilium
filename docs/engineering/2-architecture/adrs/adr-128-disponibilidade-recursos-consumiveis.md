# ADR-128 — Disponibilidade de Recursos Consumíveis: Estoque, Taxa de Consumo e Reabastecimento (Diesel, Combustível, Material)

**Status:** ⚠️ Parcialmente Implementado _(2026-07-08: F1/F3 completos; F2 implementado como reparo pós-processamento — ver nota; F4 implementado como capacidade pura, não conectado a uma fonte de dado real de projeto/escopo)_
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
| F2 | `ReplenishableResource` no motor de agendamento; projeção de estoque semana a semana | ⚠️ Implementado como reparo pós-CP-SAT (ver nota de implementação) |
| F3 | Parsing/normalização de `prazo_entrega` (hoje `str \| None`, texto livre) para dias numéricos; reaproveitamento como lead time de reabastecimento de material | ✅ Implementado |
| F4 | `tanque_sugerido` (UI) lendo `DisponibilidadeConsumivel` com fallback heurístico atual | ⚠️ Implementado como capacidade pura (ver nota de implementação) |

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
zero). **Limitação conhecida e documentada no código:** o atraso não é repropagado para
sucessores no DAG de precedências — um cronograma onde a atividade atrasada tem sucessores
dependentes pode gerar uma violação de precedência que esta fase não resolve. Repropagação
completa (2ª passada de resolução de precedências, ou reservoir constraint nativo no
CP-SAT) fica para uma Fase 2b futura.

**F4 — estado da conexão UI↔dado real:** `calcular_tanque_sugerido()` (função pura,
testada) já prioriza `DisponibilidadeConsumivel.capacidade_armazenamento` sobre a
heurística quando presente, e `_render_cube_diesel_metrics` aceita esse dado como
parâmetro opcional. O que **não** foi feito nesta entrega: plugar uma fonte real de
`DisponibilidadeConsumivel` em nível de projeto/escopo (D3) ao call site do dashboard —
esse modelo de dado de projeto/canteiro ainda não existe no sistema; a UI hoje sempre
chama com `disponibilidade=None`, preservando o comportamento heurístico atual.

## Definition of Done

### Fase 1
- [x] `DisponibilidadeConsumivel` definido, validado (capacidade/estoque ≥ 0), campos opcionais

### Fase 2
- [x] Projeção de estoque semanal implementada e testada com cenário de estoque negativo → atraso
- [x] Cenário sem `DisponibilidadeConsumivel` preenchida reproduz exatamente o comportamento atual (regressão zero)
- [ ] Atraso repropagado para sucessores no DAG de precedências (limitação conhecida — Fase 2b)

### Fase 3-4
- [x] Estratégia de parsing de `prazo_entrega` (texto livre → dias) definida e testada com os valores reais hoje presentes no catálogo (ex.: "Imediato")
- [x] `prazo_entrega` de material alimentando lead time sem novo campo duplicado (`DisponibilidadeConsumivel.from_prazo_entrega`)
- [x] `tanque_sugerido` consistente entre UI e modelo quando dado real está presente (capacidade pura implementada e testada)
- [ ] Fonte real de `DisponibilidadeConsumivel` em nível de projeto/escopo conectada ao dashboard (pendente — depende de modelo de dado de projeto ainda não existente)

---

## Relacionados

- ADR-107: Generalização do tipo de combustível — taxonomia de `TipoCombustivel` reaproveitada aqui
- ADR-090: BDI sistemático diesel/material — camada de custo, permanece inalterada; esta ADR trata de disponibilidade/risco de atraso, não de custo
- ADR-046: Implementação RCPSP completa — motor de agendamento onde `ReplenishableResource` se insere
