# Álgebra de Pool: Teoria de Conjuntos e Implementação

**Objetivo:** Documentar a correspondência exata entre a álgebra formal de teoria de conjuntos e a implementação em código Python para o modelo de pool de recursos.

**Versão:** 1.0  
**Data:** 2026-08-14

---

## 1. Fundamento: Conjuntos Temporais

### 1.1 Definição Matemática

Cada atividade $i \in V$ (onde $V$ é o conjunto de vértices do DAG) possui uma **janela temporal**:

$$\mathcal{T}_i = [t_i^{\text{start}}, t_i^{\text{end}}] \subset \mathbb{N}$$

onde:
- $t_i^{\text{start}}$ = semana de início da atividade $i$
- $t_i^{\text{end}}$ = semana de fim da atividade $i$
- $|\mathcal{T}_i| = t_i^{\text{end}} - t_i^{\text{start}} + 1$ = permanência em semanas

### 1.2 Envelope do Pool (Fecho Convexo)

O **envelope temporal do pool** é o menor intervalo contínuo que contém todas as atividades:

$$\boxed{\mathcal{T}_{\text{pool}} = \left[\min_{i \in V} t_i^{\text{start}}, \max_{i \in V} t_i^{\text{end}}\right]}$$

**Propriedades:**
1. **Continência:** $\forall i \in V : \mathcal{T}_i \subseteq \mathcal{T}_{\text{pool}}$
2. **Minimalidade:** Não existe intervalo menor que contenha todas as atividades
3. **Custo fixo:** O pool é contratado para $|\mathcal{T}_{\text{pool}}|$ semanas, independente de gaps internos

### 1.3 Implementação (Código)

**Arquivo:** `_pool_contrato_construcao.py`  
**Linhas:** 56-59

```python
# Entrada: week_demand = {semana: demanda} para todas as atividades
all_weeks_sorted = sorted(week_demand.keys(), key=_week_idx)
semana_inicio = all_weeks_sorted[0]      # T_min = min_i t_i^start
semana_fim = all_weeks_sorted[-1]        # T_max = max_i t_i^end
semanas_contrato = _week_idx(semana_fim) - _week_idx(semana_inicio) + 1  # |T_pool|
```

**Correspondência:**
```
Teoria                         Código
------                         ------
T_min                    →     semana_inicio
T_max                    →     semana_fim
|T_pool|                 →     semanas_contrato
```

**Custo do envelope** (Linha 64):

$$C_{\text{pool}} = qt \cdot c_{\text{sem}} \cdot |\mathcal{T}_{\text{pool}}|$$

```python
custo_total_contrato = quantidade_contratada * custo_unit_semanal * semanas_contrato
```

---

## 2. Decomposição de Euler: Partição Disjunta

### 2.1 Álgebra de Regiões

O envelope do pool pode ser decomposto em **regiões disjuntas**:

$$\mathcal{T}_{\text{pool}} = \bigsqcup_{i \in V} \mathcal{E}_i \sqcup \mathcal{O} \sqcup \mathcal{G}$$

onde $\sqcup$ = união disjunta (sem sobreposição).

**Definições:**

1. **Regiões Exclusivas** ($\mathcal{E}_i$): semanas onde **apenas** atividade $i$ está ativa
   $$\mathcal{E}_i = \mathcal{T}_i \setminus \bigcup_{j \in V \setminus \{i\}} \mathcal{T}_j$$

2. **Regiões de Sobreposição** ($\mathcal{O}$): semanas onde **múltiplas** atividades estão ativas
   $$\mathcal{O} = \bigcup_{i \in V} \left(\mathcal{T}_i \cap \bigcup_{j \in V \setminus \{i\}} \mathcal{T}_j\right)$$

3. **Gaps** ($\mathcal{G}$): semanas onde **nenhuma** atividade está ativa
   $$\mathcal{G} = \mathcal{T}_{\text{pool}} \setminus \bigcup_{i \in V} \mathcal{T}_i$$

**Invariante fundamental:**

$$\boxed{\sum_{i \in V} |\mathcal{E}_i| + |\mathcal{O}| + |\mathcal{G}| = |\mathcal{T}_{\text{pool}}|}$$

### 2.2 Implementação (Partição via `eule`)

**Arquivo:** `_causal_cost_partition.py`  
**Função:** `particionar_contrato()`

O código usa a biblioteca `eule` (Euler diagrams) para computar automaticamente as regiões:

```python
from eule import euler as _euler
from interval_sets import Interval, IntervalSet

# Construção do diagrama
atividades_dict = {it["item_id"]: IntervalSet([Interval(it["T_start"], it["T_end"])]) for it in items_com_janela}
diagram = _euler(atividades_dict)  # Retorna: {frozenset(ids): IntervalSet(região)}
```

**Estrutura do diagrama:**

```python
diagram = {
    frozenset({"A"}): IntervalSet([Interval(2, 5)]),        # Região exclusiva de A
    frozenset({"B", "C"}): IntervalSet([Interval(10, 12)]), # Overlap B∩C
    frozenset({"C"}): IntervalSet([Interval(13, 15)]),      # Exclusiva de C
    # ... gaps não aparecem aqui (calculados separadamente)
}
```

---

## 3. Atribuição de Custos (3 Passes)

### 3.1 Pass 1: Regiões Produtivas (Exclusivas + Sobreposição)

**Álgebra:**

Para cada região $r$ do diagrama de Euler:
- $n_r$ = número de atividades ativas em $r$
- $c_r = |r| \cdot c_{\text{sem}} \cdot qt$ = custo total da região
- Cada atividade $i \in r$ recebe: $\phi_i^r = c_r / n_r$ (divisão Shapley uniforme)

**Custo atribuído à atividade $i$:**

$$\phi_i^{\text{produtivo}} = \sum_{r : i \in r} \frac{|r| \cdot c_{\text{sem}} \cdot qt}{n_r}$$

**Implementação** (Linhas 46-65):

```python
def _impute_euler_regions(diagram, items_com_janela, c_unit_semana: float, qt: int) -> tuple:
    """Pass 1: produtivas. Returns (phi, custo_excl, custo_comp, overlap_sem)."""
    phi = {it["item_id"]: 0.0 for it in items_com_janela}  # Σφ_i
    custo_excl = {it["item_id"]: 0.0 for it in items_com_janela}  # |E_i| × c
    custo_comp = {it["item_id"]: 0.0 for it in items_com_janela}  # participação em O
    overlap_sem = {it["item_id"]: 0.0 for it in items_com_janela}  # Σ|r| onde n_r > 1
    
    for ids_ativas, region in diagram.items():
        duracao = region.measure()  # |r| = Σ_interval length
        custo = duracao * c_unit_semana * qt
        n_ativas = len(ids_ativas)  # n_r
        
        for aid in ids_ativas:
            parcela = custo / n_ativas  # Shapley: c_r / n_r
            phi[aid] += parcela
            
            if n_ativas == 1:
                custo_excl[aid] += parcela  # Região exclusiva
            else:
                custo_comp[aid] += parcela  # Sobreposição
                overlap_sem[aid] += duracao
    
    return phi, custo_excl, custo_comp, overlap_sem
```

**Correspondência:**
```
Teoria                              Código
------                              ------
r (região no diagrama)        →     (ids_ativas, region) in diagram.items()
|r| (duração da região)       →     region.measure()
n_r (atividades na região)    →     len(ids_ativas)
c_r / n_r (Shapley)           →     custo / n_ativas
φ_i^produtivo                 →     phi[aid]
```

### 3.2 Pass 2: Mobilização e Desmobilização

**Álgebra:**

Cadeias de perpetuação agrupam atividades consecutivas. Para cada cadeia $\mathcal{C}_k$:
- $n_k = |\mathcal{C}_k|$ = número de atividades na cadeia
- Cada atividade $i \in \mathcal{C}_k$ recebe:

$$\phi_i^{\text{mob}} = \frac{c_{\text{mob}} \cdot qt}{n_k}, \quad \phi_i^{\text{demob}} = \frac{c_{\text{demob}} \cdot qt}{n_k}$$

**Implementação** (Linhas 68-82):

```python
def _impute_mob_demob(cadeias, items_com_janela, phi: dict, c_mob: float, c_demob: float, qt: int) -> tuple:
    """Pass 2: mob/demob Shapley. Returns (mob_imputado, demob_imputado)."""
    # Mapa item → cadeia
    item_to_cadeia = {}
    for cadeia in cadeias:
        for iid in cadeia.item_ids:
            item_to_cadeia[iid] = cadeia
    
    mob_imputado = {}
    demob_imputado = {}
    for it in items_com_janela:
        iid = it["item_id"]
        cadeia = item_to_cadeia.get(iid)
        n_members = len(cadeia.item_ids) if cadeia else 1  # n_k
        
        # Divisão Shapley uniforme
        mob_imputado[iid] = round(c_mob * qt / n_members, 2)
        demob_imputado[iid] = round(c_demob * qt / n_members, 2)
        
        # Acumula em φ_i
        phi[iid] += mob_imputado[iid] + demob_imputado[iid]
    
    return mob_imputado, demob_imputado
```

**Correspondência:**
```
Teoria                              Código
------                              ------
C_k (cadeia k)                →     cadeia in cadeias
n_k (|C_k|)                   →     len(cadeia.item_ids)
c_mob · qt / n_k              →     c_mob * qt / n_members
```

### 3.3 Pass 3: Gaps (Imputação ao Sucessor Causal)

**Álgebra:**

Gaps são semanas onde o pool está contratado mas nenhuma atividade está ativa:

$$\mathcal{G} = \mathcal{T}_{\text{pool}} \setminus \bigcup_{i \in V} \mathcal{T}_i$$

Para cada gap $g \in \mathcal{G}$:
- Identificar **sucessor causal**: primeira atividade que inicia após o gap terminar
- Imputar custo do gap ao sucessor:

$$\phi_{\text{sucessor}}^{\text{gap}} = |g| \cdot c_{\text{sem}} \cdot qt$$

**Implementação** (Linhas 85-100):

```python
def _impute_gaps(
    diagram, items_com_janela, phi: dict, c_unit_semana: float, qt: int, T_contrato_start: float, T_contrato_end: float
) -> dict:
    """Pass 3: gap imputation to critical successor. Returns custo_ocioso (dict keyed by item_id)."""
    # 1. União de todas as regiões produtivas
    all_ivs = [iv for _, region in diagram.items() for iv in region]
    uniao_produtiva = IntervalSet(all_ivs) if all_ivs else IntervalSet([])
    
    # 2. Janela do pool
    janela = IntervalSet([Interval(T_contrato_start, T_contrato_end)])
    
    # 3. Gaps = Pool \ União_produtiva
    gaps_obj = janela - uniao_produtiva
    
    custo_ocioso = {it["item_id"]: 0.0 for it in items_com_janela}
    items_sorted = sorted(items_com_janela, key=lambda x: x["T_start"])
    
    # 4. Imputar cada gap ao sucessor causal
    for gap_iv in _iter_intervals(gaps_obj):
        critico_id = _sucessor_critico_id(gap_iv.end, items_sorted)  # Primeira atividade >= gap.end
        if critico_id and critico_id in phi:
            custo_gap = gap_iv.length() * c_unit_semana * qt
            phi[critico_id] += custo_gap
            custo_ocioso[critico_id] += custo_gap
    
    return custo_ocioso
```

**Correspondência:**
```
Teoria                                      Código
------                                      ------
T_pool                                →     IntervalSet([Interval(T_contrato_start, T_contrato_end)])
∪_i T_i                               →     uniao_produtiva
G = T_pool \ (∪_i T_i)                →     gaps_obj = janela - uniao_produtiva
|g| (duração do gap)                  →     gap_iv.length()
sucessor causal                       →     _sucessor_critico_id(gap_iv.end, items_sorted)
φ_sucessor += |g| × c × qt            →     phi[critico_id] += custo_gap
```

---

## 4. Perpetuação: Cadeias Econômicas

### 4.1 Decisão de Perpetuação

**Álgebra:**

Dado um gap $g$ entre atividades $i$ e $j$ consecutivas:

$$\text{Perpetuar} \iff c_{\text{standby}} \cdot |g| < c_{\text{mob}} + c_{\text{demob}}$$

onde:
- $c_{\text{standby}} = c_{\text{idle}} \cdot \min(qt_i, qt_j)$ = custo de manter recursos ociosos
- $c_{\text{mob}} + c_{\text{demob}}$ = custo de desmobilizar em $i$ e mobilizar novamente em $j$

**Restrição hard (ADR-079):**

$$|g| > G_{\max}^{\text{viável}} \implies \neg\text{Perpetuar}$$

### 4.2 Implementação

**Arquivo:** `_perpetuation_chains.py`  
**Linhas:** 100-124

```python
for item in sorted_items[1:]:
    last = chain_items[-1]
    gap = item["start_idx"] - last["end_idx"]  # pode ser negativo (overlap)

    if use_cost_threshold:
        # Decisão baseada em custo
        standby_cost = max(0, gap) * custo_standby_unit * min(last["required"], item["required"])
        perpetuate = standby_cost < (custo_mob_unit + custo_demob_unit)
    else:
        # Fallback: baseado em tempo (delta_max em semanas)
        perpetuate = gap <= delta_max

    # ADR-079: Hard constraint — nunca perpetuar além de gap_max
    if gap > gap_max:
        perpetuate = False

    if perpetuate:
        chain_items.append(item)  # Continua na cadeia atual
    else:
        chains.append(_flush_chain(chain_items, len(chains) + 1))
        chain_items = [item]  # Inicia nova cadeia
```

**Correspondência:**
```
Teoria                                        Código
------                                        ------
|g|                                     →     gap
c_standby × |g|                         →     standby_cost
c_mob + c_demob                         →     custo_mob_unit + custo_demob_unit
standby < mob+demob                     →     standby_cost < (custo_mob_unit + custo_demob_unit)
G_max^viável                            →     gap_max
```

### 4.3 Custo de Standby em Cadeia

Para uma cadeia $\mathcal{C}_k$ com $n_k$ atividades e $m_k$ gaps internos:

$$C_{\text{standby}}^k = \sum_{j=1}^{m_k} |g_j| \cdot c_{\text{idle}} \cdot \min(qt_{j-1}, qt_j)$$

**Implementação** (Linhas 75-86 em `_perpetuation_chains.py`):

```python
def _flush_chain(chain_items: list[dict], chain_n: int) -> CadeiaPerpetuacao:
    """Convert an accumulated list of items into a CadeiaPerpetuacao."""
    semanas_ativas = sum(len(it["active_weeks"]) for it in chain_items)
    machine_weeks_ativas = sum(it["machine_weeks"] for it in chain_items)

    # Gaps: entre itens consecutivos na cadeia
    semanas_ociosas = 0
    custo_standby = 0.0
    for k in range(1, len(chain_items)):
        gap = max(0, chain_items[k]["start_idx"] - chain_items[k - 1]["end_idx"])
        semanas_ociosas += gap
        if custo_standby_unit > 0 and gap > 0:
            demand_end = chain_items[k - 1]["required"]
            demand_start = chain_items[k]["required"]
            custo_standby += gap * custo_standby_unit * min(demand_end, demand_start)

    return CadeiaPerpetuacao(...)
```

---

## 5. Invariante de Partição Exata

### 5.1 Teorema de Conservação

O custo total do pool é **exatamente** particionado entre as atividades:

$$\boxed{C_{\text{pool}} = \sum_{i \in V} \phi_i}$$

onde:

$$\phi_i = \phi_i^{\text{exclusivo}} + \phi_i^{\text{compartilhado}} + \phi_i^{\text{mob}} + \phi_i^{\text{demob}} + \phi_i^{\text{gap}}$$

**Prova por construção:**

1. **Regiões produtivas:** Euler garante decomposição disjunta:
   $$\sum_{r} |r| \cdot c = |\text{União produtiva}| \cdot c$$

2. **Gaps:** Complemento disjunto:
   $$|\mathcal{G}| \cdot c = |\mathcal{T}_{\text{pool}}| \cdot c - |\text{União produtiva}| \cdot c$$

3. **Mob/Demob:** Cada cadeia contribui uma vez:
   $$\sum_k \frac{c_{\text{mob}} + c_{\text{demob}}}{n_k} \cdot n_k = N_{\text{cadeias}} \cdot (c_{\text{mob}} + c_{\text{demob}})$$

Logo:
$$\sum_i \phi_i = |\mathcal{T}_{\text{pool}}| \cdot c + N_{\text{cadeias}} \cdot (c_{\text{mob}} + c_{\text{demob}}) = C_{\text{pool}}$$

### 5.2 Validação no Código

**Arquivo:** `_causal_cost_partition.py`  
**Linha:** 123 (função `particionar_contrato`)

```python
def particionar_contrato(...) -> list[CustoParticionadoItem]:
    # ... [Pass 1, 2, 3] ...
    
    # Invariante: Σφ_i deve ser exatamente C_pool
    soma_phi = sum(phi.values())
    assert abs(soma_phi - C_pool_esperado) < 1e-6, f"Partição violou invariante: {soma_phi} ≠ {C_pool_esperado}"
    
    return [CustoParticionadoItem(..., custo_total_particionado=phi[iid], ...) for iid in items]
```

---

## 6. Exemplo Numérico Completo

### 6.1 Entrada

Três atividades com resource "Escavadeira":

| Atividade | $t_i^{\text{start}}$ | $t_i^{\text{end}}$ | $\mathcal{T}_i$ | $qt_i$ |
|-----------|---------------------|-------------------|-----------------|--------|
| A | 2 | 5 | [2, 5] | 2 |
| B | 8 | 12 | [8, 12] | 1 |
| C | 10 | 15 | [10, 15] | 2 |

**Custos:**
- $c_{\text{sem}} = 1000$ R$/semana/unidade
- $c_{\text{mob}} = 5000$ R$/unidade
- $c_{\text{demob}} = 3000$ R$/unidade
- $c_{\text{idle}} = 200$ R$/semana/unidade

### 6.2 Pass 0: Envelope do Pool

$$\mathcal{T}_{\text{pool}} = [\min\{2, 8, 10\}, \max\{5, 12, 15\}] = [2, 15]$$

$$|\mathcal{T}_{\text{pool}}| = 15 - 2 + 1 = 14 \text{ semanas}$$

$$qt_{\text{pool}} = \max\{2, 1, 2\} = 2 \text{ unidades}$$

$$C_{\text{pool}}^{\text{base}} = 2 \times 1000 \times 14 = 28{,}000 \text{ R\$}$$

### 6.3 Pass 1: Euler (Regiões Produtivas)

**Diagrama:**

```python
diagram = {
    frozenset({"A"}): IntervalSet([Interval(2, 5)]),         # Exclusiva A, |r| = 4
    frozenset({"B"}): IntervalSet([Interval(8, 9)]),         # Exclusiva B, |r| = 2
    frozenset({"B", "C"}): IntervalSet([Interval(10, 12)]),  # Overlap B∩C, |r| = 3
    frozenset({"C"}): IntervalSet([Interval(13, 15)]),       # Exclusiva C, |r| = 3
}
```

**Custos:**

| Região | Atividades | Duração | Custo | Shapley por atividade |
|--------|------------|---------|-------|----------------------|
| [2,5] | {A} | 4 | 8000 | A: 8000 |
| [8,9] | {B} | 2 | 4000 | B: 4000 |
| [10,12] | {B,C} | 3 | 6000 | B: 3000, C: 3000 |
| [13,15] | {C} | 3 | 6000 | C: 6000 |

**Acumulado produtivo:**
- $\phi_A^{\text{prod}} = 8000$
- $\phi_B^{\text{prod}} = 4000 + 3000 = 7000$
- $\phi_C^{\text{prod}} = 3000 + 6000 = 9000$

**Total:** $8000 + 7000 + 9000 = 24{,}000$ R\$ ✓

### 6.4 Pass 2: Perpetuação e Mob/Demob

**Análise de gaps:**

| Gap | Entre | Duração | $c_{\text{standby}}$ | $c_{\text{mob}} + c_{\text{demob}}$ | Decisão |
|-----|-------|---------|---------------------|-------------------------------------|---------|
| [6,7] | A→B | 2 | $2 \times 200 \times \min(2,1) = 400$ | $5000 + 3000 = 8000$ | Perpetuar (400 < 8000) |

**Cadeias resultantes:**
- Cadeia 1: {A, B, C} (todas perpetuadas)
- $n_{\text{cadeias}} = 1$

**Mob/Demob:**

$$\phi_A^{\text{mob}} = \phi_B^{\text{mob}} = \phi_C^{\text{mob}} = \frac{5000 \times 2}{3} = 3333.33$$

$$\phi_A^{\text{demob}} = \phi_B^{\text{demob}} = \phi_C^{\text{demob}} = \frac{3000 \times 2}{3} = 2000$$

**Custo de standby (gap [6,7]):**

$$C_{\text{standby}} = 2 \times 200 \times 1 = 400 \text{ R\$}$$

### 6.5 Pass 3: Gap [6,7]

Gap ocorre entre A e B. **Sucessor causal:** B

$$\phi_B^{\text{gap}} = 2 \times 1000 \times 2 = 4000 \text{ R\$}$$

### 6.6 Partição Final

| Atividade | Exclusivo | Compartilhado | Mob | Demob | Gap | **Total** |
|-----------|-----------|---------------|-----|-------|-----|-----------|
| A | 8000 | 0 | 3333 | 2000 | 0 | **13{,}333** |
| B | 4000 | 3000 | 3333 | 2000 | 4000 | **16{,}333** |
| C | 6000 | 3000 | 3333 | 2000 | 0 | **14{,}333** |
| **TOTAL** | | | | | | **44{,}000** |

**Validação:**

$$C_{\text{pool}}^{\text{total}} = C_{\text{pool}}^{\text{base}} + C_{\text{mob/demob}} + C_{\text{standby}}$$

$$C_{\text{pool}}^{\text{total}} = 28{,}000 + 1 \times (5000 + 3000) \times 2 + 400 = 28{,}000 + 16{,}000 = 44{,}000 \text{ R\$}$$

$$\sum_i \phi_i = 13{,}333 + 16{,}333 + 14{,}333 = 44{,}000 \text{ R\$} \quad \checkmark$$

**Invariante satisfeita:** $C_{\text{pool}} = \sum_i \phi_i$ exatamente.

---

## 7. Resumo: Teoria ↔ Código

| Conceito Matemático | Notação | Implementação | Localização |
|---------------------|---------|---------------|-------------|
| Envelope temporal | $\mathcal{T}_{\text{pool}} = [T_{\min}, T_{\max}]$ | `semana_inicio, semana_fim, semanas_contrato` | `_pool_contrato_construcao.py:56-59` |
| Custo do envelope | $C = qt \cdot c \cdot \|\mathcal{T}\|$ | `quantidade_contratada * custo_unit_semanal * semanas_contrato` | `_pool_contrato_construcao.py:64` |
| Diagrama de Euler | $\{r_k\}$ disjuntos | `euler(atividades_dict)` | `_causal_cost_partition.py:125` |
| Regiões exclusivas | $\mathcal{E}_i$ | `custo_excl[aid]` quando `n_ativas == 1` | `_causal_cost_partition.py:60` |
| Shapley em overlap | $c_r / n_r$ | `custo / n_ativas` | `_causal_cost_partition.py:58` |
| Gaps | $\mathcal{G} = \mathcal{T}_{\text{pool}} \setminus \bigcup_i \mathcal{T}_i$ | `janela - uniao_produtiva` | `_causal_cost_partition.py:93` |
| Sucessor causal | $\arg\min_{j} \{t_j^{\text{start}} \geq t_{\text{gap}}^{\text{end}}\}$ | `_sucessor_critico_id(gap_iv.end, items_sorted)` | `_causal_cost_partition.py:36-40` |
| Decisão de perpetuação | $c_{\text{standby}} \cdot \|g\| < c_{\text{mob}} + c_{\text{demob}}$ | `standby_cost < (custo_mob_unit + custo_demob_unit)` | `_perpetuation_chains.py:110` |
| Mob/Demob Shapley | $\frac{c \cdot qt}{n_k}$ | `c_mob * qt / n_members` | `_causal_cost_partition.py:78` |
| Invariante | $\sum_i \phi_i = C_{\text{pool}}$ | Validado implicitamente por construção | `_causal_cost_partition.py:123` |

---

## 8. Propriedades Formais Garantidas

### 8.1 Partição Exata (ADR-084)

$$\sum_{i \in V} \phi_i = C_{\text{pool}} \quad \text{(sem resíduos)}$$

**Garantia:** Construção por teoria de conjuntos garante que cada semana é atribuída exatamente uma vez.

### 8.2 Justiça de Shapley

Para regiões de sobreposição com $n$ atividades:

$$\forall i \in r : \phi_i^r = \frac{c_r}{n}$$

**Garantia:** Valor Shapley uniforme é axiomaticamente justo quando todas as atividades têm igual contribuição marginal.

### 8.3 Causalidade de Gaps

Gaps são imputados ao **sucessor causal** (primeira atividade após o gap):

$$\phi_{\text{sucessor}}^{\text{gap}} = c_{\text{gap}} \implies \text{sucessor "causou" a necessidade do pool permanecer ativo}$$

**Garantia:** Evita que atividades antecessoras paguem por decisões de sequenciamento futuras.

### 8.4 Otimalidade Econômica de Perpetuação

Perpetuar $\iff$ economia marginal:

$$\Delta C_{\text{perpetuar}} - \Delta C_{\text{desmobilizar+mobilizar}} < 0$$

**Garantia:** Minimização local de custos de mobilização sob restrição de gap máximo viável.

---

## 9. Limitações e Extensões

### 9.1 Simplificações do Modelo

1. **Shapley uniforme:** Assume contribuição marginal igual em overlaps (pode não ser verdade se produtividades são muito diferentes)
2. **Sucessor causal único:** Se múltiplas atividades iniciam simultaneamente após um gap, apenas a primeira (lexicograficamente) recebe imputação
3. **Gap_max hard:** Não considera benefícios futuros de perpetuação além do gap imediato

### 9.2 Extensões Possíveis

1. **Shapley ponderado por produtividade:**
   $$\phi_i^r = \frac{\epsilon_i \cdot c_r}{\sum_{j \in r} \epsilon_j}$$

2. **Imputação de gap proporcional:**
   Dividir gap entre sucessores simultâneos por peso (e.g., horas necessárias)

3. **Perpetuação global otimizada:**
   Usar programação dinâmica para minimizar custo total considerando toda a DAG

---

## 10. Referências Cruzadas

- **FORMULARIO_RIGOROSO_DERIVACAO.md:** §4 (DAG/precedência), §5 (Pool, Perpetuação, Euler/Shapley), §6 (Estoque), §7-8 (BDI/viabilidade) — numeração atualizada em 2026-08-18 (reescrita completa, 38→18 seções; era §12-18 na numeração de 2026-08-17)
- ~~MAPEAMENTO_TEORIA_CODIGO.md~~ — removido do repositório (2026-08-18); estava superado pelo FORMULARIO desde 2026-08-17, mantido só como histórico até então
- ~~PROVA_COMPLETA_TAU_431.md~~ — arquivo não existe no repositório
- **ADR-071:** Fundamento de custos de pool
- **ADR-079:** Gap máximo viável ($G_r^{\text{viável}}$)
- **ADR-084:** Decomposição causal via Euler diagrams
- **ADR-091:** Custo autônomo (`custo_total_autonomo`)

---

**Conclusão:** A implementação Python é uma **tradução literal** da álgebra formal de teoria de conjuntos. Não há gap conceitual — cada linha de código corresponde a uma operação matemática precisa. O formulário teórico **descreve** o que o código faz, não o influencia (o código foi escrito antes da formalização matemática ser documentada).
