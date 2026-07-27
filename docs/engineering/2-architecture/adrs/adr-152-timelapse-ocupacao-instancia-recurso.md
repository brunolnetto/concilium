# ADR-152 — Timelapse de Ocupação de Instância de Recurso (Pool)

**Status:** Implementado
**Data:** 2026-07-26
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-077 (Recurso Instancial), ADR-083 (Segmentos de Alocação via Euler), ADR-085 (Custo Instancial Composicional Temporal), ADR-128 (`DisponibilidadeConsumivel`/`ReplenishableResource` — padrão de projeção semanal espelhado aqui)

---

## Contexto

### Problema

P1. O pool de recursos (mão-de-obra e equipamento) não individualiza pessoa/máquina física — `InstanciaRecurso` (ADR-077) modela um **slot contratual** ("ESC-3CAT-03"), explicitamente documentado como não sendo um ativo físico específico. Essa não-individualização é uma decisão de escopo já revisitada (ADR-059) e permanece fora do escopo desta ADR.

P2. Apesar de não individualizar, `InstanciaRecurso` já carrega uma linha do tempo **comprimida** por slot: `segmentos_atividade` (blocos contínuos produtivos, ADR-083) e `segmentos_idle` (blocos contínuos de standby, ADR-086). O dado bruto semana-a-semana que origina esses segmentos (`instance_week_map`, um `dict[int, dict[str, str]]` interno a `_assign_instances`/`_resource_instance_assignment.py`) é computado e **descartado logo após a compressão** (`_compress_to_segments`) — nunca persistido nem exposto como função pública.

P3. Materiais consumíveis já têm exatamente esse tipo de projeção pública: `project_estoque_semanal()` (`replenishable.py`, ADR-128) devolve `dict[semana, nível]` recomputado sob demanda a partir do cronograma resolvido. Não existe equivalente para pool — quem precisa de visão semana-a-semana de ocupação de um contrato hoje teria que reimplementar a expansão de segmentos manualmente, sem função testada e centralizada.

---

## Decisão

### D1 — Nova função pura `project_ocupacao_semanal(instancia: InstanciaRecurso) -> dict[str, str]`

Expande os campos já persistidos em `InstanciaRecurso` — `segmentos_atividade`, `segmentos_idle`, `semana_entrada`, `semana_saida` — num dict semana → status, com precedência estrutural e sem ambiguidade:

```python
def project_ocupacao_semanal(instancia: InstanciaRecurso) -> dict[str, str]:
    """Expande os segmentos comprimidos de uma InstanciaRecurso em status semana-a-semana.

    Análogo a project_estoque_semanal (ADR-128) para material: reconstrói uma
    projeção fina a partir de dado já persistido, sem tocar o solver nem recomputar
    a atribuição de slots.

    Cada semana do span [semana_entrada, semana_saida] recebe exatamente um status:
    "prod" (coberta por segmentos_atividade), "idle" (coberta por segmentos_idle),
    ou "off" (não coberta por nenhum segmento — fora do ciclo mob/demob, custo zero).
    """
```

A regra de precedência é puramente estrutural (nenhuma interpretação de `semana_mobilizacao`/`semana_desmobilizacao` é necessária): toda semana do span que aparece em algum `SegmentoAtividade` de `segmentos_atividade` é `"prod"`; toda semana em `segmentos_idle` é `"idle"`; o residual é `"off"`. Isso cobre corretamente o caso de uma instância nunca utilizada (nenhum segmento em nenhuma das duas listas → todas as semanas do span são `"off"`) sem precisar decidir como interpretar a convenção legada de `semana_mobilizacao=""` (ADR-085) — a convenção legada já se reflete nos segmentos em si (quando `apply_idle_gaps=False`, `segmentos_idle` fica vazio e o modelo de custo trata o span inteiro como ativo por outra via; a projeção aqui apenas reporta o que os segmentos de fato dizem, sem reinterpretar regra de custo).

### D2 — Agregação por contrato: `project_ocupacao_contrato_semanal`

```python
def project_ocupacao_contrato_semanal(
    contrato: RecursoContrato, instancias: list[InstanciaRecurso]
) -> dict[str, dict[str, int]]:
    """{semana: {"prod": N, "idle": N, "off": N}} — soma project_ocupacao_semanal
    de todas as instâncias do contrato. N total por semana == quantidade_contratada.
    """
```

Visão de contrato inteiro — quantos slots estão em cada estado por semana — sem exigir do consumidor iterar instância por instância.

### D3 — Localização: `src/concilium/application/scheduling/pool_timelapse.py`

Mesmo módulo/camada de `replenishable.py` (`application/scheduling/`): função pura, sem efeito colateral, sem dependência do CP-SAT, operando só sobre modelos canônicos já construídos. Não entra em `domain/services/` porque, como `replenishable.py`, é projeção de relatório sobre resultado já resolvido, não uma regra de negócio de domínio.

### D4 — Escopo explicitamente fechado

Esta ADR **não** altera: o solver CP-SAT (`add_cumulative` permanece como restrição de capacidade agregada — ver discussão que motivou esta ADR), o schema de `InstanciaRecurso`/`RecursoContrato` (nenhum campo novo), `_build_instancias_recurso`/`_assign_instances` (a lógica de atribuição de slots não muda), nem a cadeia de custo (`FuncaoEquipe`, `encargo_resolver`, `equipe_custo_engine`). É estritamente uma função de leitura aditiva sobre dado já existente e já testado.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Persistir `instance_week_map` diretamente como novo campo em `InstanciaRecurso` | Duplicaria informação já representada por `segmentos_atividade`/`segmentos_idle` — risco de os dois ficarem inconsistentes entre si; reconstruir por expansão é barato (`O(semanas)`) e mantém uma única fonte de verdade |
| A2 | Individualizar identidade física (indivíduo/máquina) junto com o timelapse | Fora de escopo — avaliado e descartado em discussão prévia: exigiria reformular o CP-SAT (atribuição por unidade em vez de `add_cumulative` agregado) e reformar toda a cadeia de custo (`FuncaoEquipe`, `encargo_resolver`); ADR-059 já registra que `InstanciaEquipamento`/instâncias de pool são identidade lógica, não física, por decisão deliberada |
| A3 | Expor `instance_week_map` diretamente de `_resource_instance_assignment.py` em vez de reconstruir a partir dos segmentos públicos | Aumentaria o acoplamento a um módulo interno (`_`-prefixed, considerado privado); os segmentos já são a interface pública estabelecida (ADR-083/085/086) — reconstituir a partir deles preserva o limite de encapsulamento existente |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Timelapse de pool alcança paridade de visibilidade com material | Relatórios/API podem consultar ocupação semana-a-semana de um slot/contrato, análogo a `project_estoque_semanal` |
| Zero regressão | Função pura e aditiva — não toca solver, schema nem custo; nenhum teste existente muda de comportamento |
| Reaproveita dado já validado | `segmentos_atividade`/`segmentos_idle` já são produzidos e testados por ADR-083/085/086 |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Ainda não é identidade física — "instância 3 ativa na semana X" não diz qual pessoa/máquina fisicamente ocupou o slot | Já documentado como não-objetivo desta ADR (ver A2); consumidores devem tratar a instância como slot contratual, nunca como ativo rastreável |
| Reconstrução por expansão é `O(semanas)` por instância a cada chamada (sem cache) | Aceitável — mesma ordem de grandeza de `project_estoque_semanal`, que já opera assim sem problema de performance relatado |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `project_ocupacao_semanal` (por instância) + testes | ✅ |
| F2 | `project_ocupacao_contrato_semanal` (agregado por contrato) + testes | ✅ |

Integração com API/relatório/dashboard fica fora desta ADR — entrega é a função de domínio testada, pronta para consumo futuro (mesmo padrão de `replenishable.py`, que também não nasceu com endpoint próprio).

## Definition of Done

### Fase 1-2 (TDD — teste antes da implementação)

- [x] Semana coberta por um `SegmentoAtividade` de `segmentos_atividade` → `"prod"`
- [x] Semana coberta por um segmento de `segmentos_idle` → `"idle"`
- [x] Semana do span `[semana_entrada, semana_saida]` não coberta por nenhum dos dois → `"off"`
- [x] Instância nunca utilizada (`segmentos_atividade` e `segmentos_idle` ambos vazios) → todas as semanas do span são `"off"`
- [x] `project_ocupacao_contrato_semanal` soma corretamente `prod`/`idle`/`off` por semana entre todas as instâncias do contrato; total por semana == `quantidade_contratada`
- [x] Suíte completa sem regressão (`tests/unit/application/scheduling/test_adr152_pool_timelapse.py`, 9 testes; suíte completa 14413 passed, 0 failed)

---

## Relacionados

- ADR-077 — Recurso Instancial (define `InstanciaRecurso`, o slot que esta ADR projeta)
- ADR-083 — Segmentos de alocação via diagrama de Euler (`segmentos_atividade`)
- ADR-085 — Custo Instancial Composicional Temporal (ciclo de vida prod/idle/off, `segmentos_idle`)
- ADR-128 — Disponibilidade de Recursos Consumíveis (`project_estoque_semanal`, o padrão espelhado aqui para pool)
- ADR-059 — Permanência de Recursos sem Dismissal (registra que instâncias de pool são identidade lógica, não física — fundamenta a exclusão de escopo A2)
