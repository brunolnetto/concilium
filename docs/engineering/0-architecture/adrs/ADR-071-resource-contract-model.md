# ADR-071: Resource Contract Model — Custo de Pool de Recursos por Contrato

**Status:** Implementado  
**Data:** 2026-05-25  
**Autor:** Bruno Peixoto  
**Relacionado:** ADR-046, ADR-016, ADR-030, ADR-072

---

## 1. Contexto

O modelo de custo anterior (até ADR-070) tratava cada `EquipeDireta` como detentora de recursos **disjuntos**: o `custo_total` de cada item era calculado multiplicando o custo semanal da equipe pelo número de semanas que a equipe estava ativa **para aquele item**, independentemente de outras atividades.

O RCPSP (ADR-046) já modelava um **pool compartilhado** de recursos — `resource_pool` no `rcpsp_spec` define a capacidade máxima de cada tipo de recurso disponível ao projeto — mas essa informação era usada apenas como **restrição de escalonamento** (garantia de não-violação de capacidade), nunca como base para o cálculo de custo.

Isso gerava uma inflação sistemática do orçamento de equipes:

```
Modelo anterior (disjunto):
  custo_total = Σ_itens ( custo_semanal_item × semanas_ativas_item )
  → cada item "possui" suas próprias máquinas e trabalhadores

Realidade (pool compartilhado):
  custo_contrato(T) = pool_size(T) × custo_unit_sem(T) × semanas_contrato(T)
  → uma frota de N máquinas é contratada para a obra inteira
  → o custo é dividido entre os itens proporcionalmente ao uso
```

### Exemplo concreto (AGIS)

| Tipo | Pool | Itens | Semanas autônomas | Semanas contrato | Diferença |
|------|------|-------|-------------------|-----------------|-----------|
| ESC-3CAT | 10 | eap-1_5 (4u×49w), eap-1_6 (4u×49w), eap-1_9 (2u×52w) | 10×49 + 10×49 + 4×52 = ~1186 machine-weeks | 10 × span_ativo | ≤ disjunto |
| ATERRO | 5 | eap-1_7 (3u×51w), eap-1_8 (2u×3w), eap-1_10 (1u×6w) | 15+6+6 = 27 machine-weeks autônomos | 5 × span_ativo | depende do cronograma |

---

## 2. Problema

### P1 — Dupla contagem de recursos compartilháveis
Quando dois itens usam o mesmo tipo de recurso em semanas sobrepostas ou sequenciais, o modelo disjunto cobra pelo recurso duas vezes — uma por item. Mas na realidade o projeto contrata um conjunto único de máquinas/trabalhadores.

### P2 — Custo desacoplado da estrutura contratual real
Obras lineares (corredores ferroviários, rodovias) são contratadas com uma **frota** por tipo de serviço. O contrato diz: "10 escavadeiras 3ª categoria por 52 semanas". O modelo disjunto não representa essa realidade.

### P3 — VAL-COB-NEG espúrio
O aviso "preço de venda abaixo do custo da equipe" disparava para todos os 11 itens do AGIS porque o custo autônomo (45 semanas × equipe completa) era 5–10× maior que o preço de venda calibrado para uma obra pontual. Com o modelo de contrato, o custo atribuído por item é uma fração proporcional do contrato, tornando a comparação preço × custo mais realista.

---

## 3. Decisão

### D1 — Novo artefato canonical: `contratos_recurso`

Para cada tipo de recurso presente em `rcpsp_spec.resource_pool`, o skill-05 produz um `RecursoContrato`:

```
contrato_id:          "contrato-{tipo_id.lower()}"
tipo_id:              ex. "ESC-3CAT"
quantidade_contratada: pool_size(T)        # do rcpsp_spec.resource_pool
semana_inicio:        min(semana ativa de qualquer item usando T)
semana_fim:           max(semana ativa de qualquer item usando T)
semanas_contrato:     semana_fim_idx - semana_inicio_idx + 1
custo_unit_semanal:   média ponderada (por machine-weeks) do custo por unidade-semana
custo_total_contrato: quantidade × custo_unit × semanas_contrato
items_cobertos:       [item_ids que usam T]
```

### D2 — `custo_unit_semanal` derivado das EquipeDiretas

Para o item Ii usando tipo T com `required_resources[T] = R_i`:

```
custo_unit_sem_i   = EquipeDireta(Ii).custo_total / (R_i × active_weeks_i)
custo_unit_sem(T)  = Σ(custo_unit_sem_i × R_i × active_weeks_i) / Σ(R_i × active_weeks_i)
```

A média ponderada por machine-weeks garante que itens com mais uso pesam mais na determinação do custo unitário.

### D3 — Atribuição proporcional ao uso (machine-weeks)

```
machine_weeks_i     = R_i × active_weeks_i
total_machine_weeks = Σ_j machine_weeks_j   (somente itens usando T)
frac_i              = machine_weeks_i / total_machine_weeks

custo_atribuido_i   = custo_contrato(T) × frac_i
```

### D4 — `EquipeDireta.custo_total` passa a ser o custo atribuído

Para itens cobertos por um contrato de pool (i.e., que têm `required_resources` no `rcpsp_spec`):

```
EquipeDireta.custo_total        ← custo_atribuido_i   (novo: atribuição proporcional)
EquipeDireta.custo_total_autonomo ← custo original disjunto (preservado para diagnóstico)
EquipeDireta.contrato_tipo_id   ← tipo_id do RecursoContrato
EquipeDireta.fracao_atribuicao  ← frac_i
```

Itens sem `required_resources` (não cobertos por pool) mantêm comportamento anterior: `custo_total = custo_total_autonomo`.

### D5 — Skills 06 e 08 sem alteração de interface

Skill-06 e skill-08 lêem `EquipeDireta.custo_total` sem conhecer se é autônomo ou atribuído. A interface downstream é preservada; apenas o valor muda. Os `contratos_recurso` ficam disponíveis no canonical para relatórios e auditoria.

---

## 4. Consequências

### Positivas
- Orçamento de equipes alinhado com a estrutura contratual real de obras lineares.
- VAL-COB-NEG passa a comparar atribuição proporcional vs. preço de venda — resultado mais representativo.
- `contratos_recurso` é um artefato auditável que responde "quantas máquinas de cada tipo, por quanto tempo, a que custo?".

### Negativas / Riscos
- Se `rcpsp_spec` não estiver presente (modo MANUAL_ALLOCATION), o modelo permanece disjunto — comportamento anterior preservado.
- O `custo_unit_semanal` é uma média ponderada; se itens do mesmo tipo tiverem CPUs muito diferentes, a média pode ser imprecisa. Mitigação: monitorar dispersão de custo unitário por tipo.
- Items com `required_resources` mas sem schedule ativo (sem `distribuicao_semanal`) não recebem atribuição e mantêm custo autônomo com aviso INFO.

---

## 5. Alternativas Consideradas

| Alternativa | Por que rejeitada |
|---|---|
| Productive-weeks-only (Direção B) | Não modela o contrato; subestima custo de recursos ociosos entre atividades sequenciais |
| Custo de corredor full (ADR-046 original) | Inflação sistemática; VAL-COB-NEG espúrio para todos os itens |
| ADR-016 Classe C (divisão por simultâneos) | Correto para recursos de infraestrutura (servidores, almoxarifado), não para frotas de obra |

---

## 6. Notas de Implementação

- Função principal: `_build_contratos_recurso(equipes, rcpsp_spec, sched_lookup)` em `_skill_helpers_a.py`
- Ativada somente quando `inputs.get("rcpsp_spec")` está presente
- Conversão de semana: `"S052"` → `52` via `int(s.lstrip("S"))`
- O canonical serializa `contratos_recurso` como lista JSON; pode ser visto em `canonical.json` pós-pipeline
