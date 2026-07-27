# ADR-153 — Identidade Física de Recurso: Anotação Declarativa de Segmento (Fase 1)

**Status:** Parcialmente Implementado
**Data:** 2026-07-26
**Contexto:** MendesLobo Construtora — Concilium
**Dependências:** ADR-077 (Recurso Instancial), ADR-083 (Segmentos de Alocação), ADR-152 (Timelapse de Ocupação — `project_ocupacao_semanal`), ADR-059 (Permanência de Recursos — instância de pool é identidade lógica, não física)

---

## Contexto

### Problema

P1. O pool de recursos (mão-de-obra e equipamento) modela `InstanciaRecurso` como um **slot contratual**, não um ativo físico — decisão deliberada e já revisitada (ADR-059). Uma discussão de arquitetura (2026-07-26) mapeou a distância até "identidade física real" (saber que o pedreiro X ou a escavadeira placa Y especificamente ocupou um slot numa semana) em **três frentes independentes**, cada uma grande sozinha:

1. **Reformulação do solver** — `add_cumulative` (restrição de capacidade agregada) trocado por atribuição por unidade (unit-based RCPSP), com risco real de explosão combinatória nos cronogramas que hoje resolvem exato;
2. **`InstanciaRecurso` como entidade persistente** — hoje é rótulo pós-hoc recomputado a cada rodada de schedule (algoritmo guloso em `_assign_instances`), não uma entidade com identidade real rastreada ao longo do tempo/projetos;
3. **Reforma da cadeia de custo** — `FuncaoEquipe`, `encargo_resolver`, `equipe_custo_engine` assumem função/tipo agregado; individualizar exigiria um eixo de dado novo (salário real por matrícula, custo real por ativo) inexistente hoje em qualquer lugar do catálogo.

Nenhuma ADR prévia reduz esse esforço — é greenfield dentro do sistema existente, e nenhuma das três frentes é segura para implementar em uma única sessão sem risco real de regressão de performance do solver ou de inconsistência na cadeia de custo.

P2. Ao mesmo tempo, existe uma necessidade concreta e imediatamente atendível: **rastreabilidade/auditoria** — depois que um cronograma é resolvido e os segmentos de cada `InstanciaRecurso` são conhecidos (`segmentos_atividade`, ADR-083/152), um gestor de obra frequentemente sabe (ou quer registrar) qual ativo físico específico efetivamente ocupou um segmento — por exemplo, para consulta de manutenção, ou porque o ativo foi substituído no meio do contrato (cenário que a própria documentação de `InstanciaRecurso` já prevê: "o ativo físico que ocupa um slot pode variar por substituição ou manutenção"). Hoje não há nenhum campo para registrar essa informação, nem que seja um rótulo simples sem nenhuma implicação de custo ou de solver.

---

## Decisão

Esta ADR resolve **apenas P2** (Fase 1 — anotação declarativa, sem custo nem solver). As três frentes de P1 permanecem addressed nesta ADR apenas como plano futuro explícito (Fases 2 e 3), não implementadas agora — ver Plano de Implementação.

### D1 — Novo campo opcional em `SegmentoAtividade`: `identidade_fisica_id: str | None = None`

```python
class SegmentoAtividade(BaseModel):
    activity_id: str
    semana_inicio: str
    semana_fim: str
    machine_weeks: int = 0
    identidade_fisica_id: str | None = None  # NOVO — ADR-153 F1
```

Puramente aditivo: default `None`, não quebra nenhum consumidor existente (`_enrich_particao_overhead`, `CuboPoolInstancial`/ADR-086, `project_ocupacao_semanal`/ADR-152). Nunca preenchido pelo solver ou por `_build_instancias_recurso`/`_assign_instances` — o algoritmo de atribuição de slots (ADR-077) continua inteiramente agnóstico a identidade física, exatamente como antes.

### D2 — Função pura de enriquecimento: `atribuir_identidade_fisica_segmentos`

```python
def atribuir_identidade_fisica_segmentos(
    instancias: list[InstanciaRecurso],
    atribuicoes: dict[tuple[str, str], str],
) -> list[InstanciaRecurso]:
    """Enriquece segmentos_atividade com identidade_fisica_id a partir de uma
    declaração externa {(instancia_id, semana_inicio): identidade_fisica_id}.

    Não modifica as instâncias originais — retorna novas instâncias. Chaves sem
    correspondência em nenhum segmento são ignoradas silenciosamente (a declaração
    pode se referir a uma rodada de schedule diferente, ou a um slot que não teve
    atividade atribuída nesta rodada).
    """
```

A chave de correspondência é `(instancia_id, semana_inicio)` — identifica um segmento de forma unívoca dentro de uma instância (segmentos de uma mesma instância nunca se sobrepõem nem repetem `semana_inicio`, por construção de `_compress_to_segments`). `activity_id` sozinho não serve de chave porque a mesma atividade pode gerar dois segmentos não-contíguos na mesma instância (gap intermediário ocupado por outra atividade).

A declaração (`atribuicoes`) é fornecida externamente por quem chama a função — esta ADR **não** especifica de onde essa declaração vem (nenhuma UI, nenhum campo em `Escopo`, nenhuma integração com o pipeline real de skill-05). É deliberadamente simétrico ao próprio `project_ocupacao_semanal` (ADR-152 D3): função de domínio pura e testada, pronta para consumo futuro, sem wiring prematuro.

### D3 — Localização: `src/concilium/application/scheduling/pool_identidade_fisica.py`

Mesmo padrão de `pool_timelapse.py` (ADR-152): módulo de `application/scheduling/`, função pura sem efeito colateral, sem dependência do CP-SAT.

### D4 — Fases 2 e 3: explicitamente não implementadas nesta ADR

- **Fase 2 (solver)**: qualquer garantia de que o *mesmo* ativo físico permaneça associado a um slot ao longo de múltiplos segmentos, ou que o solver raciocine sobre identidade física ao decidir alocação, está fora de escopo. `add_cumulative` permanece inalterado.
- **Fase 3 (custo)**: nenhuma mudança em `FuncaoEquipe`, `encargo_resolver`, `equipe_custo_engine` ou `RecursoContrato`. `identidade_fisica_id` não tem nenhum efeito sobre nenhum campo de custo — é estritamente um rótulo de rastreabilidade. Individualizar custo real por pessoa/ativo continua exigindo um eixo de dado que não existe em nenhuma camada do catálogo hoje.

Essas duas fases ficam registradas aqui como plano explícito para não se perderem, mas **não têm data nem compromisso de execução** — são decisões de escopo grande demais para uma sessão, análogas em tamanho a outras reformas já vistas neste projeto (ex.: ADR-046 RCPSP completo, ADR-099 RBAC), que historicamente levaram múltiplas ADRs sequenciais e semanas de trabalho.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Implementar as três fases (solver + entidade persistente + custo) nesta mesma ADR/sessão | Rejeitado — risco real de regressão de performance do solver sem validação incremental, e risco de inconsistência na cadeia de custo sem um ciclo de revisão próprio; nenhuma ADR prévia no projeto tenta reformas desse tamanho numa única entrega |
| A2 | Persistir identidade física em `InstanciaRecurso` (nível de instância, não de segmento) | Rejeitado — a própria semântica de `InstanciaRecurso` prevê que o ativo físico pode variar por substituição/manutenção *dentro* do mesmo contrato; identidade pertence ao segmento, não ao slot inteiro |
| A3 | Não fazer nada agora — esperar até haver orçamento para as três fases completas | Rejeitado — a necessidade de rastreabilidade (P2) é real e imediatamente atendível sem nenhum dos riscos das fases 2/3; não há motivo para bloquear o valor incremental |
| A4 | Fazer a declaração de identidade via override em `Escopo` (padrão ADR-128/151, `logistica_consumiveis`) já nesta ADR | Deferido para uma Fase 1-bis futura — adicionaria wiring ao pipeline real de skill-05 que não foi pedido nem validado; mantém a mesma disciplina de escopo de ADR-152 D3 (função pronta, sem integração prematura) |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Rastreabilidade de ativo físico por segmento, sem risco de solver/custo | Quem sabe qual ativo ocupou um segmento pode registrar isso de forma auditável |
| Zero regressão | Campo novo com default `None`; função pura aditiva; nenhum consumidor existente muda de comportamento |
| Caminho aberto e documentado para Fases 2/3 | Decisão registrada evita que o assunto se perca, sem forçar compromisso prematuro de escopo grande |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Sem Fase 2, não há garantia de que o rótulo declarado reflita continuidade real entre segmentos (o solver pode, em tese, atribuir o mesmo slot a ativos diferentes em segmentos consecutivos sem que isso seja detectável automaticamente) | Documentado como limitação conhecida; a declaração é responsabilidade de quem a fornece, mesma classe de risco que `deficit_provisionado_externamente` (ADR-151) |
| Sem Fase 3, o campo não tem nenhum efeito prático em custo — pode ser lido como "não fez nada de útil" por quem esperava individualização de custo | Documentado explicitamente como não-objetivo desta fase; valor entregue é rastreabilidade, não custo |
| Função ainda não tem nenhum ponto de entrada real (sem UI, sem override em `Escopo`) | Mesma decisão já validada em ADR-152 D3; entrega é a função testada, integração é trabalho futuro sob demanda |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 | `SegmentoAtividade.identidade_fisica_id` (campo) + `atribuir_identidade_fisica_segmentos` (função) + testes | ✅ |
| F2 | Reformulação do solver CP-SAT para atribuição por unidade (unit-based RCPSP) | ⬜ (não iniciada — fora de escopo desta ADR) |
| F3 | Reforma da cadeia de custo para granularidade individual (`FuncaoEquipe`, `encargo_resolver`, `equipe_custo_engine`) | ⬜ (não iniciada — fora de escopo desta ADR) |

## Definition of Done

### Fase 1 (TDD — teste antes da implementação)

- [x] `SegmentoAtividade(identidade_fisica_id=None)` é o comportamento padrão (nenhum consumidor existente quebra)
- [x] `atribuir_identidade_fisica_segmentos` aplica o rótulo ao segmento correto via chave `(instancia_id, semana_inicio)`
- [x] Segmento sem entrada correspondente em `atribuicoes` mantém `identidade_fisica_id=None`
- [x] Chave em `atribuicoes` sem correspondência em nenhuma instância/segmento é ignorada silenciosamente (sem exceção)
- [x] Instâncias originais não são mutadas (função pura — retorna novas instâncias)
- [x] Múltiplos segmentos da mesma instância recebem rótulos independentes corretamente
- [x] Suíte completa sem regressão (`tests/unit/application/scheduling/test_adr153_pool_identidade_fisica.py`, 7 testes; suíte completa 14437 passed, 0 failed)

### Fase 2 e 3

Não iniciadas nesta ADR — ver D4. Retomar apenas como decisão explícita e planejada separadamente, dado o tamanho (provavelmente exige ADRs próprias, uma por frente).

---

## Relacionados

- ADR-077 — Recurso Instancial (define `InstanciaRecurso`/slot, o objeto que esta ADR anota)
- ADR-083 — Segmentos de alocação (`SegmentoAtividade`, o objeto estendido por esta ADR)
- ADR-152 — Timelapse de Ocupação de Instância de Recurso (padrão de função pura aditiva espelhado aqui; `project_ocupacao_semanal` e `atribuir_identidade_fisica_segmentos` são complementares — status + identidade por semana)
- ADR-059 — Permanência de Recursos sem Dismissal (funda a decisão de que instâncias de pool são identidade lógica, não física — motiva por que isso é rótulo declarativo e não atribuição automática)
- Achado de conversa 2026-07-26: memórias `modelagem-recursos-pool-gaps-individualizacao` e `perpetuacao-pool-slot-contratual-nao-identidade` documentam a avaliação completa das três frentes que motivou esta ADR
