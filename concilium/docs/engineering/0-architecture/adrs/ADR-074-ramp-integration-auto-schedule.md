# ADR-074 — Integração de Perfil de Rampa em AUTO_SCHEDULE

**Status:** Implementado
**Data:** 2026-05-25
**Autores:** Bruno Peixoto, Claude Sonnet 4.6
**Contexto:** ADR-072 (Productive Duration), ADR-073 (Perpetuação), ADR-046 (RCPSP), ADR-054 (WMP)

---

## 1. Contexto

Após ADR-072, `duration_weeks` de cada atividade RCPSP equivale às semanas
produtivas (tempo que a equipe efetivamente trabalha). Porém, o demand profile
dentro dessas semanas era **constante e máximo**:

```
required_resources["DESMAT"] = 5  →  5 equipes em todas as semanas da atividade
```

Na realidade, equipes são mobilizadas gradualmente: a primeira semana pode ter
1 equipe, depois 3, depois 5 (plateau), depois redução no final (desmobilização).

No modo MANUAL_ALLOCATION, o WMP (ADR-054) já suporta perfis de rampa via
`num_equipes_por_semana`. No modo AUTO_SCHEDULE (RCPSP), não havia suporte.

### Formalização (de `docs/product/4-research/resource_management.md`)

```
k_i(t) = intensidade de uso da atividade i no tempo t:
  fase ramp-up:    min(K_i^max, floor(ρ_i+ × (t - s_i)))    para t ∈ [s_i, s_i + T_up)
  fase plateau:    K_i^max                                   para t ∈ [s_i + T_up, f_i - T_down)
  fase ramp-down:  max(0, K_i^max - floor(ρ_i- × (t - t_i*))) para t ∈ [f_i - T_down, f_i)

onde:
  ρ_i+   = taxa de mobilização (unidades/semana)
  ρ_i-   = taxa de desmobilização (unidades/semana)
  T_up   = ceil((K_i^max - n_inicial) / ρ_i+)   semanas de ramp-up
  T_down = ceil(K_i^max / ρ_i-)                  semanas de ramp-down
  t_i*   = inicio da fase de ramp-down = f_i - T_down
  K_i^max = peak demand = required_resources[r] (recurso primário)
```

O demand real de recurso r no tempo t é:
```
demand_{i,r}(t) = k_i(t) × e_{i,r}  (onde e_{i,r} = required_resources[r] / K_i^max)
```

---

## 2. Problema

### P1 — Superestimação de demanda no scheduler
O SGS (ADR-004) tratava todas as semanas de uma atividade com demanda máxima.
Isso impedia o scheduler de posicionar atividades em janelas onde o pool seria
brevemente excedido apenas nas semanas de plateau, mesmo quando a rampa
admitiria esse posicionamento.

### P2 — machine-weeks inflados no contrato
`_build_contratos_recurso` computava `machine_weeks_i = required_i × active_weeks_i`.
Com rampa, as semanas iniciais e finais têm demanda menor — os machine-weeks reais
são menores que o valor flat, resultando em atribuição proporcional ligeiramente
inflada para itens com rampas longas.

### P3 — Inconsistência entre modos
Em MANUAL_ALLOCATION, a distribuição semanal captura a rampa real (via WMP).
Em AUTO_SCHEDULE, a distribuição resultante era sempre flat (= required_resources).
Os dois modos produziam perfis de uso inconsistentes para o mesmo tipo de projeto.

---

## 3. Decisão

### D1 — `ramp_params` em `rcpsp_spec.activities[]` (entrada opcional)

```json
{
  "item_id": "eap-1_0",
  "duration_weeks": 14,
  "required_resources": {"DESMAT": 5},
  "ramp_params": {
    "n_inicial": 1,
    "taxa_mobilizacao": 1.0,
    "taxa_desmobilizacao": 1.0
  }
}
```

Campos de `ramp_params`:
- `n_inicial: int` — equipes na semana 0 da atividade (default: 0)
- `taxa_mobilizacao: float` — equipes adicionadas por semana na fase up (default: K_max = instantâneo)
- `taxa_desmobilizacao: float` — equipes removidas por semana na fase down (default: mesmo que mob)

Se `ramp_params` ausente, a atividade mantém demanda flat (comportamento legado).

### D2 — `ramp_profile: list[float] | None` em `Activity`

O modelo de scheduling (`Activity` em `models.py`) recebe novo campo:
```python
ramp_profile: list[float] | None = None
```

Valores em [0.0, 1.0] representando fração do peak demand a cada semana da atividade.
A demanda real de recurso r na semana t é:
```
demand_r_t = max(0, round(required_resources[r] × ramp_profile[t]))
```

Quando `ramp_profile is None`, comportamento flat (sem alteração de interface).

### D3 — SGS usa `ramp_profile` para feasibility check e booking

`SerialScheduler._can_schedule` e `_book_resources` são atualizados para usar
`ramp_profile[week_offset]` em vez da demanda flat quando disponível:

```python
# Em _can_schedule:
for offset, w in enumerate(range(start, start + activity.duration_weeks)):
    demand_factor = activity.ramp_profile[offset] if activity.ramp_profile else 1.0
    for res, qty in activity.required_resources.items():
        demand = max(0, round(qty * demand_factor))
        if used + demand > available: return False

# Em _book_resources:
for offset, w in enumerate(range(t, end)):
    demand_factor = activity.ramp_profile[offset] if activity.ramp_profile else 1.0
    for res, qty in activity.required_resources.items():
        demand = max(0, round(qty * demand_factor))
        resource_usage[w][res] += demand
```

### D4 — MILP usa flat peak (sem alteração)

O MILP (`milp.py`) continua usando `required_resources` flat para as restrições
de capacidade. O ramp torna as restrições menos restritivas (o problema só fica
mais relaxado), então a solução MILP com flat é feasível sob ramp — o ramp é
aplicado post-hoc pelo SGS e pelo cálculo de custo.

### D5 — `_build_contratos_recurso` usa machine-weeks reais

```python
# Antes (flat):
machine_weeks_i = required_i × len(active_weeks)

# Depois (ramp-aware):
if activity has ramp_profile:
    machine_weeks_i = sum(round(required_i × p) for p in ramp_profile)
else:
    machine_weeks_i = required_i × len(active_weeks)
```

A atribuição proporcional de custo por item fica mais precisa para itens com rampas.

---

## 4. Derivação de `ramp_profile`

A função `_compute_ramp_profile(duration_weeks, ramp_params, n_pico)` em `skill.py`:

```
1. T_up   = ceil((n_pico - n_inicial) / taxa_mob)   se taxa_mob > 0 e n_pico > n_inicial
2. T_down = ceil(n_pico / taxa_desmob)              se taxa_desmob > 0
3. T_plateau = max(0, duration_weeks - T_up - T_down)

Para t em 0..duration_weeks-1:
  fase up    (t < T_up):      val = n_inicial + taxa_mob × (t+1)   → clamped a n_pico
  fase plat  (T_up ≤ t < T_up+T_plateau):  val = n_pico
  fase down  (t ≥ T_up+T_plateau):  offset = t - T_up - T_plateau
                                     val = max(0, n_pico - taxa_desmob × (offset+1))
  profile[t] = val / n_pico   → float em [0.0, 1.0]
```

Se `T_up + T_down > duration_weeks`, reduz T_down para
`max(0, duration_weeks - T_up)` e T_up para `duration_weeks` se necessário
(garantia de que o profile tem exatamente `duration_weeks` elementos).

---

## 5. Exemplo (AGIS — eap-1_0 Desmatamento)

```
duration_weeks = 14, required_resources["DESMAT"] = 5
ramp_params = {n_inicial: 1, taxa_mobilizacao: 1.0, taxa_desmobilizacao: 1.0}

T_up   = ceil((5-1)/1.0) = 4 semanas
T_down = ceil(5/1.0)     = 5 semanas
T_plateau = max(0, 14 - 4 - 5) = 5 semanas

profile = [0.4, 0.6, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.8, 0.6, 0.4, 0.2, 0.0]
            ↑------ ramp-up -----↑  ↑-------- plateau --------↑  ↑--- ramp-down ---↑

Demanda DESMAT por semana: [2, 3, 4, 5, 5, 5, 5, 5, 5, 4, 3, 2, 1, 0]
machine_weeks reais = 2+3+4+5×6+4+3+2+1 = 44  vs  5×14 = 70 flat
```

---

## 6. Consequências

### Positivas
- Scheduler pode acomodar mais atividades em janelas estreitas (menor peak em ramp)
- Atribuição de custo por item mais precisa (machine-weeks menores para itens com rampa)
- Consistência entre AUTO_SCHEDULE e MANUAL_ALLOCATION no modelo de uso de recursos
- Cadeias de perpetuação (ADR-073) calculadas com machine-weeks reais

### Restrições / Riscos
- `ramp_params` é **opcional** — projetos sem rampa mantêm comportamento flat legado
- Se `T_up + T_down > duration_weeks`, o profile é truncado (sem plateau): equipes
  são mobilizadas mas não atingem o plateau. O planejador deve aumentar
  `duration_weeks` ou reduzir as taxas.
- O MILP usa flat peak — se a feasibilidade MILP depender do ramp, o MILP pode
  explorar soluções que o SGS com ramp não encontre. Mitigação: sempre usar SGS
  primeiro (já padrão pelo fallback chain de ADR-046).
- `distribuicao_semanal` em AUTO_SCHEDULE agora reflete a rampa: `num_equipes`
  varia por semana em vez de ser constante. Isso é correto mas quebra a suposição
  de "equipe flat" em relatórios visuais — documentar na release note.

---

## 7. Alternativas Rejeitadas

| Alternativa | Razão de rejeição |
|---|---|
| Ramp apenas para custo (não para scheduling) | Inconsistência: scheduler vê capacidade inflada enquanto custo usa real |
| `ramp_profile: list[int]` (absoluto) | Requer saber o n_pico para normalizar; floats são mais genéricos entre recursos |
| Ramp per-resource (dict) | Adiciona complexidade; em praticamente todos os casos RCPSP todos os recursos rampam juntos |
| Aplicar ramp no MILP | Bilinearidade x_{it} × profile[t-s_i] → solver non-linear; flat é conservativo e correto |

---

## 8. Arquivos Afetados

| Arquivo | Mudança |
|---------|---------|
| `src/concilium/application/scheduling/models.py` | Adiciona `ramp_profile: list[float] \| None = None` a `Activity` |
| `src/concilium/application/scheduling/scheduler.py` | `_can_schedule` e `_book_resources` usam `ramp_profile` |
| `src/concilium/application/skills/manifests/04-cronograma/skill.py` | `_compute_ramp_profile` + `_extract_activities_from_spec` estendido |
| `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers_a.py` | `_build_contratos_recurso` usa machine-weeks reais com ramp |
