# ADR-081: Precedência EAP com Derivação Automática e Threshold de Conclusão Parcial

**Status:** Implementado ✅ _(auditado 2026-06-09)_

> **Nota:** `completion_threshold_pct` e `predecessores_tipados()` implementados. NEP-031 L4 adicionou SS/FF (Sprint S2).  
**Data:** 2026-05-26  
**Autores:** Bruno Peixoto / Concilium  
**Dependências:** ADR-004, ADR-046, ADR-072, ADR-074

---

## 1. Contexto

### 1.1 Duas fontes redundantes de precedência

O pipeline atualmente mantém precedências em **dois lugares distintos**:

| Campo | Onde vive | Formato | Quem preenche |
|---|---|---|---|
| `spec.eap[].predecessores` | `EapItem.predecessores: list[str \| PrecedenciaItem]` | Tipado: FS/SS/FF + lag | Planejador (manual) |
| `spec.rcpsp_spec.precedence` | `rcpsp_spec["precedence"]: list[[str, str]]` | Par simples `[pred_id, succ_id]` | Planejador (manual) |

O NEP-031 L4 introduziu `PrecedenciaItem` com tipo (FS/SS/FF) e `lag` em semanas.
Entretanto, `_extract_dag_from_spec` (skill-04) continua lendo apenas `rcpsp_spec.precedence`,
ignorando `eap[].predecessores`. O planejador que especifica predecessores na EAP deve
**duplicar** a informação no rcpsp_spec para que o scheduler a respeite.

Isso contraria a lógica de projetos de construção: a ordenação das atividades (desmatamento
→ escavação → aterro → compactação) é **conhecimento tácito** da engenharia de obra,
já expressado ao estruturar a EAP. Não deveria exigir re-especificação em formato de baixo
nível.

### 1.2 A restrição FS estrita é incompatível com a realidade

O scheduler implementa:

```python
# scheduler.py linha 31
earliest_start[aid] = max(
    earliest_start.get(p, 0) + act_map[p].duration_weeks for p in preds
)
```

Ou seja: a atividade sucessora só pode iniciar quando o predecessor está **100% concluído**
(`duration_weeks` inteiras de defasagem). Isso modela o caso mais conservador — e frequentemente
irreal em obras de terraplenagem e construção pesada.

Exemplos práticos que violam FS estrita:

| Precedência física | Threshold razoável | Justificativa |
|---|---|---|
| Desmatamento → Escavação 1a cat | 30–50% | A escavação pode começar em trechos já desmatados |
| Escavação → Aterro | 20–40% | Aterro inicia no km 0 enquanto escavação avança no km 1 |
| Aterro → Compactação | 10–20% | Compactação começa quando há volume suficiente de aterro lançado |
| Escav. 3a cat DMT2000 → Escav. 3a cat DMT3000 | 80–100% | Mesmas frentes, sequenciamento rigoroso |

O campo `lag` em `PrecedenciaItem` só modela defasagem rígida em semanas — não captura
"pode iniciar quando X% do predecessor estiver concluído", que é a notação natural da
programação de obras (ex.: CPM com sobreposição de tarefas).

### 1.3 Consequência de cronograma

A rigidez FS 100% força serialização desnecessária de atividades que fisicamente podem
ser sobrepostas. O MINSLK/MINSLK resultante posterga o início de sucessores e resulta em
makespan maior, maior permanência de recursos e, portanto, maior N4. 

---

## 2. Decisão

### A. Derivação Automática de Precedência da EAP

Quando `rcpsp_spec.precedence` está **ausente ou vazio**, skill-04 deriva as arestas do DAG
diretamente de `canonical.eap[].predecessores`, usando `predecessores_tipados()`.

**Regra de fusão** (quando ambos os campos existem):
1. Arestas de `eap[].predecessores` constituem a base
2. Arestas em `rcpsp_spec.precedence` são adicionadas como **suplemento** (override de
   granularidade fina para pares que não estão na EAP ou que precisam de restrição extra)
3. Para o mesmo par `(pred, succ)`, `rcpsp_spec.precedence` prevalece (permite ao
   planejador endurecer ou suavizar uma relação da EAP)

Isso elimina a necessidade de duplicar a informação no caso padrão. `rcpsp_spec.precedence`
torna-se um mecanismo de exceção.

### B. `completion_threshold_pct` em `PrecedenciaItem` e `ArestaActivityDag`

Adicionar campo:

```python
class PrecedenciaItem(BaseModel):
    item_id: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = Field(default=0, ge=0, description="Lag em semanas")
    completion_threshold_pct: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fração do quantitativo do predecessor que deve estar concluída antes de "
            "este item poder iniciar (apenas para tipo='FS'). "
            "θ=1.0 (default): comportamento clássico FS — 100% do predecessor. "
            "θ=0.5: successor pode iniciar quando predecessor atingiu 50% de conclusão."
        ),
    )
```

Idem em `ArestaActivityDag`:

```python
class ArestaActivityDag(BaseModel):
    de: str
    para: str
    tipo: Literal["FS", "SS", "FF"] = "FS"
    lag: int = Field(default=0, ge=0)
    completion_threshold_pct: float = Field(default=1.0, ge=0.0, le=1.0)
```

### C. Semântica do Threshold por Tipo de Relação

#### FS com threshold θ (caso principal)

```
start_j ≥ start_i + ⌈θ × duration_i⌉ + lag
```

Interpretação: o sucessor `j` pode iniciar quando o predecessor `i` tiver completado
`θ × 100%` do seu quantitativo, com defasagem adicional `lag` semanas.

| θ | Behavior |
|---|---|
| `1.0` (default) | `start_j ≥ end_i + lag` — FS clássico |
| `0.7` | `start_j ≥ start_i + ⌈0.7 × d_i⌉ + lag` |
| `0.0` | `start_j ≥ start_i + lag` — equivalente a SS com lag |

#### SS com lag (tipo = "SS")

```
start_j ≥ start_i + lag
```

`completion_threshold_pct` é ignorado para SS (a restrição é sobre início, não conclusão).

#### FF com lag (tipo = "FF")

```
end_j ≥ end_i + lag  →  start_j ≥ start_i + (duration_i - duration_j) + lag
```

`completion_threshold_pct` é ignorado para FF por enquanto. Uma extensão futura pode
modelar FF parcial: `end_j ≥ start_i + ⌈θ × d_i⌉ + lag`.

### D. Tradução para o `ActivityDAG` e schedulers

#### `_extract_dag_from_spec` (skill-04)

```python
def _extract_dag_from_spec(
    spec: dict,
    activities: list[Activity],
    eap_items: list[EapItem],
) -> ActivityDAG:
    """Deriva DAG de precedência.

    Prioridade:
      1. rcpsp_spec.precedence (override explícito, sem threshold)
      2. eap[].predecessores (fonte canônica, com tipo/lag/threshold)
    """
    arestas: dict[tuple[str, str], ArestaActivityDag] = {}

    # Base: eap.predecessores (inclui threshold)
    for item in eap_items:
        for pred in item.predecessores_tipados():
            key = (pred.item_id, item.item_id)
            arestas[key] = ArestaActivityDag(
                de=pred.item_id,
                para=item.item_id,
                tipo=pred.tipo,
                lag=pred.lag,
                completion_threshold_pct=pred.completion_threshold_pct,
            )

    # Suplemento/override: rcpsp_spec.precedence (sem threshold — FS 100%)
    for p in spec.get("precedence", []):
        pred_id, succ_id = str(p[0]), str(p[1])
        key = (pred_id, succ_id)
        arestas[key] = ArestaActivityDag(
            de=pred_id, para=succ_id,
            tipo="FS", lag=0,
            completion_threshold_pct=1.0,  # conservador por padrão
        )

    return ActivityDAG(
        activities=activities,
        arestas=list(arestas.values()),
    )
```

#### `ActivityDAG.predecessors_com_aresta(aid)` (nova API)

Para que schedulers acessem o threshold por aresta:

```python
def predecessors_com_aresta(self, activity_id: str) -> list[ArestaActivityDag]:
    """Retorna as arestas de entrada (predecessores) de uma atividade."""
    return [a for a in self.arestas if a.para == activity_id]
```

O método `predecessors(aid) → list[str]` existente é mantido para compatibilidade.

#### Atualização dos schedulers (MINSLK, LNS, MILP)

**MINSLK / LNS** — `_compute_earliest_starts`:

```python
def _compute_earliest_starts(act_map, dag, topo_order):
    earliest_start: dict[str, int] = {}
    for aid in topo_order:
        arestas = dag.predecessors_com_aresta(aid)
        if arestas:
            earliest_start[aid] = max(
                _pred_release(a, earliest_start, act_map)
                for a in arestas
            )
        else:
            earliest_start[aid] = 0
    return earliest_start

def _pred_release(aresta: ArestaActivityDag, earliest: dict, act_map: dict) -> int:
    """Semana a partir da qual o predecesssor libera o sucessor."""
    pred_start = earliest.get(aresta.de, 0)
    d_pred = act_map[aresta.de].duration_weeks
    θ = aresta.completion_threshold_pct

    if aresta.tipo == "FS":
        offset = math.ceil(θ * d_pred)
    elif aresta.tipo == "SS":
        offset = 0
    elif aresta.tipo == "FF":
        # FF: end_j ≥ end_pred + lag → start_j ≥ start_pred + d_pred - d_j + lag
        # Aproximação conservadora: trata como FS 100%
        offset = d_pred
    else:
        offset = d_pred  # fallback seguro

    return pred_start + offset + aresta.lag
```

E na atribuição de start no loop principal:

```python
# Em vez de: pred_finish = max(scheduled[p].end_week for p in preds)
arestas_entrada = dag.predecessors_com_aresta(aid)
pred_finish = max(
    (
        scheduled[a.de].start_week
        + math.ceil(a.completion_threshold_pct * act_map[a.de].duration_weeks)
        + a.lag
        for a in arestas_entrada
        if a.de in scheduled
    ),
    default=0,
)
```

**MILP** — `_add_precedence_constraints`:

```python
def _add_precedence_constraints(prob, dag, act_map, x):
    for aresta in dag.arestas:
        pred_id, succ_id = aresta.de, aresta.para
        dur_pred = act_map[pred_id].duration_weeks
        θ = aresta.completion_threshold_pct
        offset = math.ceil(θ * dur_pred) + aresta.lag

        pred_start = pulp.lpSum(t * v for t, v in x[pred_id].items())
        succ_start = pulp.lpSum(t * v for t, v in x[succ_id].items())
        prob += succ_start >= pred_start + offset, f"prec_{pred_id}_{succ_id}"
```

---

## 3. `completion_threshold_pct` no `referencia.json`

O campo pode ser especificado diretamente em `spec.eap[].predecessores`:

```json
{
  "spec": {
    "eap": [
      {
        "item_id": "eap-1_2",
        "descricao": "Esc/carg/transp 1aCat DMT<=3000m",
        "predecessores": [
          {
            "item_id": "eap-1_0",
            "tipo": "FS",
            "lag": 0,
            "completion_threshold_pct": 0.30
          }
        ]
      }
    ]
  }
}
```

Interpretação: "a escavação 1a cat DMT3000 pode iniciar quando 30% do desmatamento
estiver concluído".

Para projetos que não especificam o campo, `completion_threshold_pct` assume `1.0`
por padrão — **comportamento idêntico ao atual**, sem quebra retroativa.

---

## 4. Consequências

### 4.1 Cronograma

Com thresholds < 1.0 em precedências de terraplenagem típicas, o scheduler pode:
- Sobreposição de frentes em diferentes trechos da obra
- Makespan reduzido
- Permanência de recursos menor → N4 menor → bridge gap menor

### 4.2 Validação de consistência

O sistema deve verificar que a sobreposição resultante é **fisicamente realizável**:
- Recursos compartilhados entre predecessor e sucessor continuam sendo tratados pelo pool
  de recursos RCPSP (sem conflito duplo de alocação)
- O threshold não viola restrições de produção (i.e., o successor não precisa de output do
  predecessor para sua entrada quando θ < 1.0)

A segunda verificação é domínio-específica e está fora do escopo do scheduler genérico;
cabe ao planejador parametrizar valores consistentes com a realidade da obra.

### 4.3 Compatibilidade retroativa

- `completion_threshold_pct = 1.0` (default): comportamento idêntico ao atual
- `rcpsp_spec.precedence` existente continua sendo respeitado como override
- `EapItem.predecessores` como string legada (`["eap-1_3"]`): convertido via
  `predecessores_tipados()` com `completion_threshold_pct = 1.0`

---

## 5. Rejeições

### R1 — Inferência automática de precedência por tipo de CPU

Seria possível inferir que "Compactação só começa após Aterro" a partir dos tipos de
CPU (CPU-TERRA-COMPAC-* após CPU-TERRA-CORPO-ATERRO-*). Rejeitado porque:
- Requer ontologia de CPUs por função construtiva (alto acoplamento)
- Não generaliza para obras não-terraplenagem
- Falsos positivos em sequenciamentos alternativos (ex.: compactação e aterro simultâneos
  em frentes distintas)

A especificação explícita em `eap[].predecessores` é o equilíbrio correto entre
expressividade e manutenibilidade.

### R2 — Threshold como percentual de `semanas_contrato` (não de `duration_weeks`)

Definir `offset = ceil(θ × semanas_contrato_pred)` em vez de `ceil(θ × duration_weeks)`.
Rejeitado: `duration_weeks` é o span real de execução da atividade; `semanas_contrato` é
um conceito de custo de pool. O threshold deve refletir progresso físico da atividade,
não custo de contrato.

### R3 — Threshold como número absoluto de semanas

`start_j ≥ start_i + N_semanas` é exatamente o campo `lag` existente. O `completion_threshold_pct`
é uma abstração de nível superior que escala automaticamente com a duração do predecessor,
tornando o parâmetro invariante a mudanças de productivity/schedule (se a atividade encurta
de 30 para 20 semanas, um threshold de 0.3 continua significando "30% concluído" = 6 semanas,
não mais as 9 hardcoded em `lag`).

---

## 6. Testes Planejados

| Classe | Nº testes | O que cobre |
|---|---|---|
| `TestDerivacaoPrec_da_EAP` | 5 | arestas derivadas de eap.predecessores; fusão com rcpsp_spec.precedence |
| `TestThresholdFS` | 8 | θ=1.0 (FS clássico), θ=0.5, θ=0.0 (SS-like); arredondamento ceil |
| `TestThresholdSS_FF` | 4 | SS ignora θ; FF trata como θ=1.0 |
| `TestSchedulerMINSLK_com_threshold` | 6 | makespan reduzido com θ<1.0; recursos não conflitam |
| `TestCompatibilidadeRetroativa` | 4 | str legada → threshold=1.0; sem rcpsp_spec.precedence → deriva da EAP |
| `TestReferencia_json` | 3 | parsing de completion_threshold_pct em spec.eap[].predecessores |

Total planejado: **30 testes**.

---

## 7. Relacionados

[[adr004-scheduling-algorithms]] [[adr046-auto-schedule]]
[[adr072-productive-duration-window-constraint]] [[adr074-ramp-integration-auto-schedule]]
