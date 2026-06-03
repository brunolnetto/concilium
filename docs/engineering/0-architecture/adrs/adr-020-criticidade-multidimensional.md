# ADR-020 — Criticidade Multi-Dimensional sem Score Sintético

**Status:** Implementado  
**Data:** 2026-05-03  
**Data Implementado:** 2026-05-04  
**Implementadores:** models/canonical.py (DimensaoCriticidade, CriticidadeProfile, CostCriticalityResult), skills/09-cost-criticality  
**Contexto:** MendesLobo Construtora — Concilium

---

## Problema

A skill `09-cost-criticality` combinava quatro dimensões (cost share, duration share,
margin sensitivity, criticidade de recurso) numa soma ponderada normalizada:

```
score = w_cost×norm(c) + w_dur×norm(d) + w_sens×norm(s) + w_rec×norm(r)
```

Essa abordagem tem dois problemas fundamentais:

1. **Incompatibilidade dimensional**: custo (R$), duração (dias), sensibilidade (proxy
   de proporção) e criticidade operacional (booleano) não têm unidade comum. Normalizar
   para [0,1] e somar presume taxas de troca entre dimensões sem fundamento empírico.

2. **Opacidade**: um score 0.62 não comunica ao engenheiro *por qual razão* a atividade
   é crítica — se por custo, prazo ou recurso. A classificação resultante (A, B, C) perde
   rastreabilidade.

---

## Decisão

Substituir o score sintético por **dominância de Pareto + ordenação lexicográfica**.

### Dominância de Pareto

Atividade A **domina** B se A ≥ B em *todas* as dimensões e A > B em pelo menos uma.
O conjunto de atividades não dominadas por nenhuma outra forma a **fronteira de Pareto**.

Dimensões comparadas (por percentil, para ordinalidade):
- `custo`: cost_share da atividade
- `duracao`: duration_share no caminho crítico
- `recurso`: criticidade operacional (CONSTRANGIDO > LIVRE)
- `sensibilidade`: proporção de custo variável (proxy de risco de overrun)

### Ordenação Lexicográfica

Para ranquear atividades sem combinação aritmética, usar prioridade de dimensão
conforme contexto de orçamentação de obras:

1. `custo` (primário — impacto financeiro direto)
2. `recurso` (se empate em custo, restrição operacional tem prioridade sobre prazo)
3. `duracao` (impacto no prazo)
4. `sensibilidade` (risco de overrun)

### Classificação

Com N atividades:
- **A+**: na fronteira de Pareto E rank_lexicografico ≤ ⌈N×0.20⌉
- **A**: na fronteira de Pareto OU rank_lexicografico ≤ ⌈N×0.40⌉
- **B**: rank_lexicografico ≤ ⌈N×0.70⌉
- **C**: demais

A classificação é determinística e auditável — sem pesos arbitrários.

---

## Modelo Canônico

`cost_criticality_report: dict | None` → `CostCriticalityResult | None`

```python
class DimensaoCriticidade(BaseModel):
    valor_raw: float
    rank: int        # 1 = mais crítico
    percentil: float # 1.0 = mais crítico

class CriticidadeProfile(BaseModel):
    atividade_id: str
    custo: DimensaoCriticidade
    duracao: DimensaoCriticidade
    recurso: DimensaoCriticidade
    sensibilidade: DimensaoCriticidade
    pareto_frontier: bool
    rank_lexicografico: int
    classe: Literal["A+", "A", "B", "C"]
    interpretacao: str

class CostCriticalityResult(BaseModel):
    atividades: list[CriticidadeProfile]
    n_pareto_frontier: int
    criterio_primario: Literal["custo", "duracao", "recurso"]
    n_atividades: int
```

---

## Impacto

| Consumidor | Mudança |
|------------|---------|
| `skill 10` | `custo_criticality.get("atividades", [])` → `.atividades`; `.get("class")` → `.classe` |
| `skill 13` | `cost_criticality_report.get("atividades", [])` → `.atividades`; `.get("class")` → `.classe` |
| `skill 14` | Novo consumidor nativo do tipo estruturado |

---

## Consequências

- **Positivo**: interpretação transparente; sem parâmetros de peso para calibrar;
  a fronteira de Pareto comunica exatamente quais atividades são multi-dimensionalmente críticas.
- **Tradeoff**: atividades com alta criticidade num único eixo não são automaticamente A+;
  isso é intencional — a classificação A+ requer liderança holística.
- **Compatibilidade**: campo renomeado de `dict` para tipo estruturado; consumidores dict-based
  quebram e devem ser atualizados (skills 10, 13 — feito neste ADR).

---

## Validações

| Código | Skill | Significado |
|--------|-------|-------------|
| VAL-CC-01 | 09 | Report gerado com pelo menos uma atividade |
| VAL-CC-02 | 09 | Fronteira de Pareto não vazia |
| VAL-CC-PRECONDICAO | 09 | equipes_diretas e planejamento presentes |

## Definition of Done

- [x] `DimensaoCriticidade` model: `valor_raw`, `rank`, `percentil`
- [x] `CriticidadeProfile` model: `atividade_id`, four dimensions (`custo`, `duracao`, `recurso`, `sensibilidade`), `pareto_frontier`, `rank_lexicografico`, `classe`, `interpretacao`
- [x] `CostCriticalityResult` model: `atividades`, `n_pareto_frontier`, `criterio_primario`, `n_atividades`
- [x] `cost_criticality_report` field in `CanonicalModel` typed as `CostCriticalityResult | None` (replaces untyped `dict | None`)
- [x] Pareto frontier computed across four dimensions; dominance check is strict (≥ all, > at least one)
- [x] Lexicographic ranking order: custo → recurso → duracao → sensibilidade
- [x] Classification A+/A/B/C using Pareto membership + rank thresholds (20% / 40% / 70%)
- [x] Skill 10 updated to consume `.atividades` and `.classe` (not legacy dict `.get("class")`)
- [x] Skill 13 updated to consume `.atividades` and `.classe` (not legacy dict `.get("class")`)
- [x] VAL-CC-01: report generated with at least one activity
- [x] VAL-CC-02: Pareto frontier non-empty
- [x] VAL-CC-PRECONDICAO: `equipes_diretas` and `planejamento` present
