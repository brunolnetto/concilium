# ADR-073 — Instance Matching e Perpetuação de Recursos Π

**Status:** Implementado
**Data:** 2026-05-25
**Autores:** Bruno Peixoto, Claude Sonnet 4.6
**Contexto:** ADR-071 (Resource Contract Model), ADR-072 (Productive Duration), ADR-046 (RCPSP)

---

## 1. Contexto

O modelo de contrato de pool (ADR-071) cobra um único custo de contrato para cada
tipo de recurso durante o span total do corredor (`semanas_contrato = last_week - first_week + 1`).
No entanto, ele não modela a estrutura de mobilização dentro desse span:

1. **Mob/demob por atividade (modelo anterior)**: `_calc_custo_mob_desmob` contava
   transições em cada item individualmente — como se cada item mobilizasse e
   desmobilizasse sua própria frota independentemente.

2. **Perpetuação real**: Quando um item termina e outro começa logo em seguida usando
   o mesmo tipo de recurso, a frota **não é desmobilizada e remobilizada** — ela é
   mantida entre as atividades (perpetuada). O custo é um `custo_standby_semanal`
   durante o gap, que tende a ser muito menor que `custo_mob + custo_demob`.

### Formalização (de `docs/product/4-research/resource_management.md`)

Dado o DAG G = (A, E) e os conjuntos de recursos R = L ∪ Q, define-se:

**Relação de perpetuação** Π ⊆ A × A × R:

```
(i, j, r) ∈ Π  ⟺  i e j usam r,  gap(i→j) ≤ δ_r  ou  gap × c_idle < c_mob + c_demob
```

onde `gap(i→j) = start_j - end_i` (semanas entre fim de i e início de j).

**Instâncias perpetuadas**:
```
π_{ij,r} = min(e_{j,r}, e_{i,r})          # unidades que transitam de i para j
```

**Demanda líquida nova** em j para recurso r:
```
ν_{j,r} = e_{j,r} - Σ_{i: (i,j,r)∈Π} π_{ij,r}
```

**Total mobilizado**:
```
M_r = Σ_j ν_{j,r}   (≤ R_r^naive = Σ_j e_{j,r})
```

### Cadeia de perpetuação

A cadeia de perpetuação para tipo r é o fecho transitivo de Π restrito a r: uma
sequência de atividades i₁ → i₂ → … → iₖ onde cada par consecutivo perpetua o
recurso. Cada cadeia gera **1 mobilização** (no início de i₁) e **1 desmobilização**
(no fim de iₖ).

---

## 2. Problema

### P1 — Dupla contagem de mob/demob
O modelo anterior contava 1 mobilização e 1 desmobilização por **item** mesmo quando
a frota seria mantida entre itens. Para AGIS com 11 atividades RCPSP, isso inflava
`M_r` desnecessariamente (embora os custos unitários de mob/demob fossem zero no
catálogo AGIS).

### P2 — Ausência de custo standby na lacuna
Os gaps entre atividades de mesma frota dentro de um contrato não tinham custo
standby associado. Na realidade, manter equipamentos ociosos custa
`custo_standby_semanal × gap_weeks × unidades`.

### P3 — Sem artefato auditável de cadeia
Não havia representação canônica das cadeias de perpetuação, dificultando o
diagnóstico de "qual frota foi mantida entre quais atividades".

---

## 3. Decisão

### D1 — Threshold de perpetuação (δ_r)

Quando `custo_mob + custo_demob > 0` para o tipo r:
```
perpetuar ↔  gap_weeks × custo_standby < custo_mob + custo_demob
```

Quando ambos os custos são zero (catálogo não populado), usa-se threshold de tempo:
```
perpetuar ↔  gap_weeks ≤ δ_default = 2
```

`δ_default = 2` (duas semanas de folga operacional entre atividades) é configurável
via campo `delta_perpetuacao_semanas` no `rcpsp_spec`.

### D2 — `CadeiaPerpetuacao`: novo artefato canônico

Para cada tipo de recurso presente no `rcpsp_spec.resource_pool`, o skill-05 produz
uma lista de `CadeiaPerpetuacao`:

```
cadeia_id:           "cadeia-{tipo_id.lower()}-{n}"
tipo_id:             ex. "DESMAT"
item_ids:            [lista de item_ids cobertos pela cadeia, em ordem de início]
semana_inicio:       primeira semana ativa do primeiro item
semana_fim:          última semana ativa do último item
semanas_ativas:      soma de active_weeks de todos os itens da cadeia
semanas_ociosas:     soma dos gap_weeks dentro da cadeia
n_mobilizacoes:      1  (por definição)
n_desmobilizacoes:   1  (por definição)
custo_standby:       Σ gap_k × custo_standby_unit × min(demand_end_i, demand_start_j)
machine_weeks_ativas: Σ required_i × active_weeks_i
delta_aplicado_semanas: δ efetivo usado
```

O campo `cadeias_perpetuacao: list[CadeiaPerpetuacao]` é adicionado ao `CanonicalModel`.

### D3 — Mob/demob contado por cadeia

A função `_calc_custo_mob_desmob` continua operando por item (para compatibilidade
downstream). Porém, `_build_contratos_recurso` agora:

1. Agrupa itens em cadeias via `_build_perpetuation_chains`
2. Computa `custo_mob_desmob_contrato = n_cadeias × (custo_mob_unit + custo_demob_unit) × quantidade_contratada`
3. Computa `custo_standby_total = Σ_{cadeia} cadeia.custo_standby`
4. Armazena ambos em `RecursoContrato` (novos campos)

> **Nota**: Para catálogos sem `custo_mobilizacao`/`custo_desmobilizacao`
> (como AGIS), o efeito financeiro é zero mas o artefato `CadeiaPerpetuacao`
> é produzido e serve como diagnóstico de M_r.

### D4 — `R_r^naive` como upper bound diagnóstico

O campo `r_naive` em `RecursoContrato` registra:
```
R_r^naive = Σ_i e_{i,r}   (soma disjunta, ignora DAG e perpetuação)
```

Compara com `peak_demand` (R_r*) e `sum(ν_{j,r})` (M_r) para medir a eficiência
do escalonamento e da perpetuação.

---

## 4. Algoritmo `_build_perpetuation_chains`

```
Input:  items = [{item_id, start_idx, end_idx, required, active_weeks}] por tipo_id
        custo_mob_unit, custo_demob_unit, custo_standby_unit, delta_max

1. Ordenar items por start_idx (ASC), desempate por end_idx (ASC)
2. chain_atual = [items[0]]
3. Para cada item i (idx > 0):
   a. gap = start_idx(i) - end_idx(chain_atual[-1])
   b. Se custo_mob_unit + custo_demob_unit > 0:
        perpetuar = (gap × custo_standby_unit < custo_mob_unit + custo_demob_unit)
      Senão:
        perpetuar = (gap <= delta_max) AND (gap >= 0)
   c. Se perpetuar:
        chain_atual.append(i)
      Senão:
        EMITIR chain_atual como cadeia
        chain_atual = [i]
4. EMITIR chain_atual como cadeia
Output: list[CadeiaPerpetuacao]
```

**Sobreposição**: Se `gap < 0` (atividades se sobrepõem), perpetuar automaticamente
(já compartilham a mesma frota na mesma semana — gap = 0 aplicado).

---

## 5. Consequências

### Positivas
- M_r calculado corretamente; `cadeias_perpetuacao` é artefato auditável.
- Custo de mob/demob por contrato corre a `n_cadeias`, não `n_items`.
- `custo_standby` modela adequadamente o custo de manutenção da frota em gaps.
- Infrastructure pronta para quando o catálogo tiver `custo_mobilizacao` populado.

### Restrições / Riscos
- `δ_default = 2` é configurável mas pode não refletir a realidade de todos os
  tipos de recursos (equipamentos pesados vs. mão de obra simples).
- `custo_standby_unit` ainda não populado no catálogo AGIS → custo standby = R$0.
  O modelo está correto estruturalmente; a precisão financeira cresce quando o
  catálogo for enriquecido.
- Sobreposições (gap < 0) são tratadas como perpetuação — correto para recursos
  compartilhados mas pode mascarar conflitos de pool (já detectados pelo scheduler).

---

## 6. Alternativas Rejeitadas

| Alternativa | Razão de rejeição |
|---|---|
| Continuar com mob/demob por item | Contagem errada de M_r; inflação futura quando custos forem populados |
| Usar grafo de precedência estrito (só arestas do DAG) | AGIS não tem precedências — perpetuação necessária por proximidade temporal |
| Campo `delta` por tipo de recurso em catálogo | Complexidade de cadastro; `delta_default=2` é suficiente como bootstrap |

---

## 7. Arquivos Afetados

| Arquivo | Mudança |
|---------|---------|
| `src/concilium/domain/models/canonical.py` | Adiciona `CadeiaPerpetuacao`; adiciona `cadeias_perpetuacao: list[CadeiaPerpetuacao]` e campos `custo_mob_desmob_contrato`, `custo_standby_total`, `r_naive`, `n_cadeias` em `RecursoContrato` |
| `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py` | Adiciona `_build_perpetuation_chains`; atualiza `_build_contratos_recurso` |
