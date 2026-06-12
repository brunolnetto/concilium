# ADR-109: Cardinalidade do Espaço de Campanha GO — Produto Cartesiano de Discretizações

**Status:** Implementado 2026-06-12  
**Relacionado:** ADR-070 (Campanha GO), ADR-108 (CampaignBundleCube)

---

## Contexto

O `GoResearchCampaignBundle` define um espaço de exploração como produto cartesiano de dimensões
discretizadas. Entender a cardinalidade desse espaço — e como ela escala com as escolhas de
discretização e granularidade (global vs por-atividade) — é fundamental para decidir quais levers
incluir, com quantos valores, e qual estratégia de busca adotar.

---

## Análise do Espaço

### Estrutura dos levers por comportamento combinatório

Dois comportamentos fundamentais emergem dos levers de campanha (ADR-070 D2b):

**Tipo G — Global:** um valor se aplica ao projeto inteiro.
Cardinalidade = `k` (número de opções discretas).

**Tipo A — Por-atividade com `[*]`:** o mesmo valor escala todas as n atividades simultaneamente.
O sweep é "global em escala, uniforme em cobertura".
Cardinalidade = `k` (igual ao global — o `[*]` não multiplica o espaço do produto cartesiano).

**Tipo A-ind — Por-atividade independente:** cada uma das n atividades escolhe seu estado
de forma independente.
Cardinalidade = `k^n` (produto exponencial) — intratável para n > 5.

### Invariante: o produto cartesiano de uma spec de campanha

Para uma spec com dimensões D₁, D₂, …, Dₘ cada uma com kᵢ valores:

```
|espaço| = Π kᵢ  (i = 1 … m)
```

Este é o número exato de cenários a avaliar numa busca exaustiva.
`GoResearchCampaignBundle.cardinality()` computa esse valor.

---

## Cardinalidade por Configuração

### Espaço atual (campaign_v1.json — 3 dimensões)

| Dimensão | k | Π acumulado |
|---|---|---|
| `meta.regime_trabalho` | 2 | 2 |
| `n_max` scale | 3 | 6 |
| `n_inicial` scale | 2 | **12** |

**12 cenários · ~2 min com 6 workers.**

### Espaço Classe 1+2+3 completo (7 dimensões globais)

| Dimensão | k | Π acumulado |
|---|---|---|
| `meta.regime_trabalho` | 3 | 3 |
| `meta.objetivo_pool` | 3 | 9 |
| `n_max` scale `[*]` | 3 | 27 |
| `n_inicial` scale `[*]` | 2 | 54 |
| `leadtime_mob_semanas` `[*]` | 3 | 162 |
| `lag_demob_semanas` `[*]` | 3 | 486 |
| `producao_diaria` scale `[*]` | 3 | **1.458** |

```
3⁶ × 2 = 729 × 2 = 1.458 cenários · ~24 min com 6 workers
```

### Espaço por-atividade (n = 11 atividades AGIS)

Para os 3 levers de frota `{n_max, n_inicial, lag_demob}` por atividade:

| Modelo | Fórmula | Cenários | Tempo estimado |
|---|---|---|---|
| **Estruturado** (template global + subset atividades) | `8 × 2^11` | 16.384 | ~4,5 h |
| **Independente** (cada atividade escolhe livremente) | `8^11` | 8,6 × 10⁹ | intratável |

O modelo **estruturado** pressupõe que todas as atividades modificadas recebem o **mesmo padrão
de levers** (o "template"), e para cada atividade escolhe-se independentemente aplicar ou não.
É tratável (16K) mas requer busca guiada, não exaustiva.

### Parâmetros com mesmo comportamento cartesiano A-ind

| Parâmetro | n | k por item | Espaço estruturado |
|---|---|---|---|
| CPU alternativo (Classe 4) | 11 itens | m ≈ 2–3 | `m × 2^11` ≈ 6.000–12.000 |
| `restricoes_mercado` por recurso | 11 tipos | {irrestrito, leve, rígido} | `3^11` ≈ 177.000 |
| `predecessores.completion_threshold` | ~15 arestas DAG | k escalas | `k × 2^15` |

---

## Decisão

### D1 — Classificar levers por tipo combinatório

| Tipo | Comportamento | Estratégia de busca |
|---|---|---|
| **G** (global) | `k` — sempre tratável | Exaustiva |
| **A[*]** (global em escala) | `k` — igual ao global | Exaustiva |
| **A-ind** (per-item independente) | `k^n` — exponencial | Estruturada ou guiada |

### D2 — Fronteira de tratabilidade: 10.000 cenários

Abaixo de 10.000 cenários → busca exaustiva é viável (~3–16h com 6 workers).
Acima → exige busca guiada (Pareto progressivo, amostragem Latin Hypercube, bisseção).

Implicação prática:
- Espaço global de 7 dimensões (1.458) → **exaustivo** ✓
- Espaço per-atividade estruturado (16.384) → **parcialmente exaustivo** ou guiado
- Espaço per-atividade independente (8,6B) → **busca guiada obrigatória**

### D3 — `GoResearchCampaignBundle.cardinality()` é obrigatório antes de executar

Toda campanha deve verificar `bundle.cardinality()` antes de disparar workers.
O runner emite aviso se `cardinality > 10.000`.

```python
n = bundle.cardinality()
if n > 10_000:
    warnings.warn(f"Campanha com {n:,} cenários excede fronteira de tratabilidade. "
                  f"Considere busca guiada (Latin Hypercube, Pareto progressivo).")
```

### D4 — Separação entre espaço de input e espaço de busca

O **espaço de input** (produto cartesiano da spec) é `Π kᵢ`.
O **espaço de busca** pode ser menor — subconjunto amostrado do espaço de input.
A spec declara o espaço; a estratégia de busca decide quantos pontos avaliar.

Dois modos de operação:
- `exhaustive`: avalia todos os cenários do produto cartesiano
- `guided`: avalia uma amostra (via Latin Hypercube, Pareto progressivo, ou busca em duas fases)

---

## Implementação

`GoResearchCampaignBundle.cardinality()` — já implementado em `campaign.py`:
```python
def cardinality(self) -> int:
    result = 1
    for s in self.sweep: result *= len(s.valores)
    return result

def cardinality_breakdown(self) -> list[dict]:
    rows = []; acc = 1
    for s in self.sweep:
        k = len(s.valores); acc *= k
        rows.append({"campo": s.campo, "k": k, "acumulado": acc})
    return rows
```

Aviso de tratabilidade — a implementar em `campaign_service.executar_campanha`:
```python
n = bundle.cardinality()
if n > 10_000:
    import warnings
    warnings.warn(
        f"GoResearchCampaignBundle.cardinality={n:,} excede fronteira de tratabilidade "
        f"(10.000). Busca exaustiva levaria ~{n*6//3600:.0f}h com 6 workers. "
        f"Considere mode='guided'."
    )
```

---

## Consequências

**Positivas:**
- Cardinalidade é auto-documentada em toda spec de campanha
- Fronteira de tratabilidade explícita orienta escolha de estratégia
- A distinção G / A[*] / A-ind esclarece por que `[*]` não explode o espaço

**Riscos:**
- Spec com muitas dimensões A[*] cresce como produto puro — o usuário pode
  inadvertidamente criar campanhas com milhares de cenários
- O modo `guided` não está implementado (apenas `exhaustive` existe hoje)
