# ADR-078: Pré-processamento Estrutural de Compartilhamento de Recursos

**Status:** Implementado  
**Data:** 2026-05-26  
**Autores:** Bruno Peixoto / Concilium  
**Dependências:** ADR-071, ADR-072, ADR-073, ADR-075, ADR-077

---

## 1. Contexto

O documento `docs/product/4-research/recursos.md` (2026-05-25) formalizou um conjunto
de lacunas no tratamento econômico do compartilhamento de recursos entre atividades:

### 1.1 Lacunas identificadas

| Lacuna | ADR afetado | Impacto |
|---|---|---|
| Matching maximiza `Σπ` (contagem) em vez de economia real | ADR-073 | Perpetuações com gap longo aumentam custo |
| `λ_0 = 0` ignora estrutura disponível | ADR-075 (Modo B) | Convergência lenta (4–10 iterações) |
| `custo_standby` usa custo plano independente da unidade de faturamento | ADR-077 | Limiar 35% não reflete `c_r^idle` real |
| Planejador sem visibilidade de pares rentáveis antes da otimização | — | Decisões de sequenciamento sem suporte quantitativo |

### 1.2 Formalismo central

Para um recurso `r` com gap `g` semanas entre atividades `i` e `j`, a **economia real**
de uma perpetuação é:

```
ΔC_real = π × [(c_mob + c_demob) − g × c_idle] = π × η × (c_mob + c_demob)
```

onde `η_{ij,r} = 1 − g × c_idle / (c_mob + c_demob) ∈ (0, 1]`.

A perpetuação só é economicamente viável quando `g < gap_r^max`:

```
gap_r^max = ceil((c_mob + c_demob) / c_idle) − 1
```

---

## 2. Decisão

Implementar uma **Fase 0 de pré-processamento estrutural** que:

1. Calcula `gap_r^max` por tipo de recurso a partir de `resource_costs` no `rcpsp_spec`
2. Avalia cada par `(i, j)` de atividades que compartilham um tipo de recurso:
   - `η_{ij,r}` — índice de eficiência descontando custo idle
   - `ov_{ij,r}` — sobreposição de quantidade do bundle
   - `Ω_{ij}` — índice de sobreposição econômica `∈ [0, 1]`
   - `ΔC_ij^pot` — economia potencial máxima do par
   - `λ_0(i,j)` — penalidade inicial para Scheduling Modo B
3. Produz `RelatorioOportunidades` como artefato de saída da skill-05

---

## 3. Extensão do Input: `resource_costs`

Seção opcional em `rcpsp_spec` (sem esta seção, a fase 0 é pulada e nenhum
`OportunidadeCompartilhamento` é gerado):

```json
"resource_costs": {
  "ESC-3CAT": {
    "custo_mob_unit":        80000.0,
    "custo_demob_unit":      40000.0,
    "custo_idle_semanal_unit": 12000.0,
    "unidade_faturamento":  "dia_cal"
  },
  "ATERRO": {
    "custo_mob_unit":        60000.0,
    "custo_demob_unit":      30000.0,
    "custo_idle_semanal_unit":  9000.0,
    "unidade_faturamento":  "dia_cal"
  }
}
```

### 3.1 `unidade_faturamento`

| Valor | Semântica | `c_idle` por semana |
|---|---|---|
| `hora_prod` | Fatura só quando produz | 0 — `gap_r^max = ∞` |
| `dia_cal` | Fatura por dia calendário (contínuo) | `custo_idle_semanal_unit` |
| `mes` | Fatura mensalmente | `custo_idle_semanal_unit` |

---

## 4. Novos Modelos de Domínio (`canonical.py`)

### 4.1 `OportunidadeCompartilhamento`

```python
class OportunidadeCompartilhamento(BaseModel):
    atividade_i: str          # item_id anterior
    atividade_j: str          # item_id posterior
    tipo_id: str              # tipo de recurso compartilhado
    gap_semanas: int          # semanas entre fim de i e início de j
    gap_max_semanas: int      # gap_r^max para este tipo
    eta: float                # η ∈ [0, 1] — eficiência com desconto de idle
    omega_bundle: float       # Ω ∈ [0, 1] — fração econômica do bundle compartilhável
    delta_c_pot: float        # R$ — economia potencial máxima do par
    lambda0: float            # δC × Ω — penalidade inicial para Scheduling Modo B
    recursos_compartilhaveis: dict[str, int]  # ov_vector {tipo: min(q_i, q_j)}
    economicamente_viavel: bool               # gap <= gap_max
```

### 4.2 `RelatorioOportunidades`

```python
class RelatorioOportunidades(BaseModel):
    total_oportunidades: int
    total_economia_pot: float        # Σ delta_c_pot (apenas viáveis)
    oportunidades_podadas: int       # count(economicamente_viavel=False)
    lambda0_total: float             # Σ lambda0 (apenas viáveis) — prioridade do Scheduling
    oportunidades: list[OportunidadeCompartilhamento]  # ordenadas por delta_c_pot desc
    gap_max_por_tipo: dict[str, int]                   # {tipo_id: gap_r^max}
```

---

## 5. Extensão de `RecursoContrato`

Campos opcionais adicionados (backward-compatible, default `0.0` / `"hora_prod"`):

```python
custo_mob_unit: float = 0.0          # R$/unidade — mobilização
custo_demob_unit: float = 0.0        # R$/unidade — desmobilização
custo_idle_semanal_unit: float = 0.0 # R$/unidade/semana — standby contínuo
unidade_faturamento: str = "hora_prod"
gap_max_economico: int = 9999        # calculado em skill-05
```

---

## 6. Algoritmos Formais

### 6.1 `_gap_max_economico(c_mob, c_demob, c_idle, unidade) → int`

```
Se unidade == "hora_prod" ou c_idle <= 0:
    retornar 9999   # ∞ — nunca há custo idle

budget = c_mob + c_demob
gap_max = ceil(budget / c_idle) − 1
retornar max(0, gap_max)
```

**Verificação:** `budget = 10 000, c_idle = 2 500 → ceil(4.0) − 1 = 3`  
`3 × 2 500 = 7 500 < 10 000 ✓` | `4 × 2 500 = 10 000 ≮ 10 000 ✗`

### 6.2 `_eta_perpetuacao(gap, c_mob, c_demob, c_idle, unidade) → float`

```
Se gap <= 0 ou unidade == "hora_prod" ou c_idle <= 0:
    retornar 1.0

η = 1 − (gap × c_idle) / (c_mob + c_demob)
retornar clamp(η, 0.0, 1.0)
```

### 6.3 `_sobreposicao_bundle(equipe_i, equipe_j, mob_demob_costs) → (ov, omega)`

Onde `equipe_i: dict[tipo_id, int]` e `mob_demob_costs: dict[tipo_id, float]`.

```
ov = {r: min(equipe_i[r], equipe_j[r]) para r em union(equipe_i, equipe_j)}

numerador   = Σ_r ov[r] × mob_demob_costs[r]
denominador = Σ_r max(equipe_i[r], equipe_j[r]) × mob_demob_costs[r]

Ω = numerador / denominador  (0 se denominador = 0)
```

### 6.4 `_delta_c_pot(q_i, q_j, ov_vector, eta, mob_demob_costs) → float`

```
k_min = min(q_i, q_j)
soma_ov = Σ_r ov_vector[r] × mob_demob_costs[r]
ΔC = k_min × eta × soma_ov / max(q_i, q_j)   # normalizado por escala
```

> **Nota de implementação:** para atividades single-resource, `k_min / max(q_i, q_j)` = `ov_ratio`.
> A fórmula compacta implementada é: `ΔC = ov_value × eta × (c_mob + c_demob)` onde
> `ov_value = min(q_i, q_j)`.

### 6.5 `λ_0(i, j) = ΔC_ij^pot × Ω_{ij}`

Inicializa a penalidade do Scheduling Modo B (ADR-075). Pares com alta sobreposição
e alta economia potencial recebem penalidade alta, induzindo serialização desde a
primeira iteração do Lagrangiano.

---

## 7. Pipeline de Pré-processamento

```
Entrada: rcpsp_spec (com resource_costs), contratos_recurso, cron_lookup

(1) Verificar presença de resource_costs — sem ela, retornar None imediatamente

(2) Para cada tipo_id em resource_costs:
    → calcular gap_r^max
    → atualizar RecursoContrato correspondente com campos de mob/demob/idle

(3) Para cada par de atividades (i, j) que compartilha tipo_id:
    → determinar qual vem antes pelo cron_lookup
    → calcular gap = start_j − end_i
    → se gap < 0: atividades se sobrepõem → pular
    → calcular η, ov_vector, Ω, ΔC_pot, λ_0
    → criar OportunidadeCompartilhamento

(4) Ordenar por ΔC_pot descrescente

(5) Emitir VAL-PRE-PROCESSAMENTO-OK ou VAL-PRE-PROCESSAMENTO-SKIP

Saída: RelatorioOportunidades | None
```

---

## 8. Wiring no Pipeline

### 8.1 `skill-05/skill.py`

Após `_build_instancias_recurso`:

```python
relatorio_oportunidades = None
if contratos_recurso and rcpsp_spec and rcpsp_spec.get("resource_costs"):
    relatorio_oportunidades = _build_pre_processamento_compartilhamento(
        contratos_recurso, rcpsp_spec, cron_lookup, validacoes
    )
```

### 8.2 `skill-09/_skill_helpers_a.py`

```python
"relatorio_oportunidades": (
    canonical_in.relatorio_oportunidades.model_dump()
    if canonical_in.relatorio_oportunidades else None
),
```

### 8.3 `runtime.py`

Nova função `_md_relatorio_oportunidades(relatorio)` produz seção:

```markdown
## 🔗 Grafo de Oportunidades de Compartilhamento

| Par (i → j) | Tipo | Gap | gap_max | η | Ω | ΔC Potencial | λ_0 | Viável? |
|...         |
```

---

## 9. Validators

| Código | Status | Condição |
|---|---|---|
| `VAL-PRE-PROCESSAMENTO-OK` | OK | `resource_costs` presente, ≥ 1 oportunidade gerada |
| `VAL-PRE-PROCESSAMENTO-SKIP` | AVISO | `resource_costs` ausente no rcpsp_spec |
| `VAL-OPT-INVIAVEL` | AVISO | ≥ 1 aresta `economicamente_viavel=False` (gap > gap_max) |

---

## 10. Resultados AGIS (estimativa com `resource_costs` calibrado)

Com os seguintes parâmetros estimados para o benchmark AGIS:

| Tipo | c_mob | c_demob | c_idle/sem | gap_max |
|---|---|---|---|---|
| ESC-3CAT | R$ 80.000 | R$ 40.000 | R$ 12.000 | 9 semanas |
| ESC-2CAT | R$ 60.000 | R$ 30.000 | R$ 9.000 | 9 semanas |
| ESC-1CAT | R$ 40.000 | R$ 20.000 | R$ 6.000 | 9 semanas |
| ATERRO | R$ 50.000 | R$ 25.000 | R$ 7.500 | 9 semanas |
| DESMAT | R$ 20.000 | R$ 10.000 | R$ 3.000 | 9 semanas |

Pares esperados (baseado no schedule MINSLK com makespan 48w):
- `(eap-1_5 → eap-1_9, ESC-3CAT)`: gap variável dependendo do schedule
- `(eap-1_6 → eap-1_9, ESC-3CAT)`: idem

---

## 11. Consequências

### 11.1 Imediatas (este ADR)
- `RelatorioOportunidades` disponível como artefato de planejamento pré-otimização
- `gap_max_economico` persistido em cada `RecursoContrato` para auditoria
- `lambda0` calculado por par — pronto para uso no Scheduling Modo B (ADR-075)

### 11.2 Futuras (ADR-079)
- Substituir objetivo do Matching de `max Σπ` para `max Σ η × π × (c_mob + c_demob)`
- Passar `G_r^viável` (arestas podadas por `gap_r^max`) como input do min-cost flow
- Inicializar `λ_0` do Scheduling Modo B com valores deste relatório
- `custo_standby` em ADR-077 refinado usando `c_idle × semanas_standby`
  em vez de `custo_unit_semanal × semanas_standby`

---

## 12. Rejeições

- **"Calcular tudo inline em ADR-073"**: violaria separação de concerns; o pré-processamento
  é estático (sem solver) e pertence a skill-05 como fase própria.
- **"Inferir c_mob de custo_unit_semanal"**: introduz heurística não auditável; o input
  explícito via `resource_costs` é a única fonte de verdade.
