# ADR-083 — Partição de Custo em Pool Compartilhado: Atribuição Temporal Causal (Muitos-para-Muitos)

**Status:** ✅ Implementado  
**Data:** 2026-05-28  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** ADR-071 (Resource Contract Model), ADR-073 (Perpetuação de Instâncias), ADR-082 (Levers de Ponto de Equilíbrio)

---

## 1. Contexto

### 1.1 Estrutura atual (ADR-071)

O `ResourcePool` implementa uma relação **muitos-para-muitos** entre recursos físicos e atividades:
- Um recurso instancial (ex.: escavadeira ESC-3CAT unidade 2) atende sequencialmente as atividades
  `eap-1_5 → eap-1_6 → eap-1_9` dentro de um único contrato de janela `[T_start, T_end]`.
- A atribuição de custo é **proporcional a machine-weeks** (ADR-071 D3):

```
frac_i = (R_i × active_weeks_i) / Σ_j(R_j × active_weeks_j)
custo_atribuido_i = custo_contrato_total × frac_i
```

O `custo_total_autonomo` preserva o custo disjunto (se o item contratasse o recurso exclusivamente).

### 1.2 Limitação identificada: `gap_praticabilidade = 0`

Na seção de gaps do `PontoEquilibrio` (ADR-082), a fórmula original computava:

```python
gap_praticabilidade = custo_total_autonomo - (custo_fixo_mensal × permanencia_efetiva)
                    ≡ 0  # identidade aritmética — mesma duração em ambos os lados
```

A causa raiz: a praticabilidade climática **alonga a duração** da atividade (mais semanas para
produzir o mesmo Q), e o custo autônomo já reflete essa duração estendida. Subtrair o custo
proporcional à mesma duração produz zero estruturalmente.

**Correção implementada** (skill-08, commit contemporâneo):

```python
# ADR-083 §4: gap = C_autônomo × (1 − η̄)
# Derivação: team_weeks = T_nom/η̄  →  C_real = C_cat/η̄  →  gap = C_real × (1 − η̄)
gap_praticabilidade_abs = custo_total_autonomo * (1.0 - fator_clima_v)
```

onde `fator_clima_v = Σ(fator_clima_j × n_j) / Σ(n_j)` é a média ponderada por team-weeks
do fator climático semanal — exatamente `η̄` da derivação formal.

### 1.3 Problema em aberto: opacidade do `gap_pool`

O `gap_pool_overhead = custo_operacional_real − custo_total_autonomo` reporta um número único,
mas não responde:

- O compartilhamento **economizou** custo de mob/demob (perpetuação, ADR-073)?
- Ou gerou **overhead de ociosidade** pelos gaps de espera entre atividades?
- O saldo líquido foi positivo (overhead) ou negativo (economia) para este item?

Sem essa decomposição, o lever `fechar_gap_pool` no painel de equilíbrio é unidimensional e
não aponta qual variável operacional o planejador deve atacar.

---

## 2. Modelo Formal de Partição Temporal

### 2.1 Janela de contrato e blocos de tempo

Para um contrato de tipo de recurso `T` cobrindo atividades `A = {a₁, a₂, …, aₙ}` em ordem
cronológica, a janela `[W_start, W_end]` é decomposta em blocos:

```
[mob] [produtivo_a₁] [gap_12] [produtivo_a₂] [gap_23] … [produtivo_aₙ] [demob]
```

onde:
- `mob` = semanas de mobilização da frota (custo_mob_contrato)
- `produtivo_aᵢ` = semanas em que o recurso trabalha para aᵢ (sem gaps)
- `gap_ij` = semanas ociosas entre fim de aᵢ e início de aⱼ (dentro do contrato ativo)
- `demob` = semanas de desmobilização (custo_demob_contrato)

Custo total do contrato:

$$C_{\text{contrato}} = C_{\text{mob}} + \sum_i C_{\text{prod},i} + \sum_{ij} C_{\text{gap},ij} + C_{\text{demob}}$$

### 2.2 Atribuição causal vs. proporcional

A atribuição proporcional atual (ADR-071 D3) distribui `C_mob + C_demob + C_gaps` linearmente
com o uso. Isso oculta a causalidade:

| Bloco de custo | Causa real | Atribuição causal |
|---|---|---|
| `C_mob` | contrato iniciado pela **primeira atividade** da cadeia | → aᵢ que inicia a cadeia (ADR-073) |
| `C_prod_i` | produção direta para aᵢ | → aᵢ (inequívoco) |
| `C_gap_ij` | aⱼ não pôde iniciar enquanto aᵢ terminava (restrição de predecessores de **aⱼ**) | → aⱼ (causalidade do sucessor) |
| `C_demob` | contrato encerrado pela **última atividade** da cadeia | → aᵢ que encerra a cadeia |

### 2.3 Valor de Shapley para n=2 (resultado fechado)

Para duas atividades A e B compartilhando um recurso (B sucede A no contrato):

- `v({A}) = C_mob + C_prod_A + C_demob` (custo autônomo de A)
- `v({B}) = C_mob + C_prod_B + C_demob` (custo autônomo de B)
- `v({A,B}) = C_mob + C_prod_A + C_gap_AB + C_prod_B + C_demob` (custo conjunto)

Shapley:

$$\phi_A = C_{\text{prod},A} + \frac{C_{\text{mob}} + C_{\text{gap},AB} + C_{\text{demob}}}{2}$$

$$\phi_B = C_{\text{prod},B} + \frac{C_{\text{mob}} + C_{\text{gap},AB} + C_{\text{demob}}}{2}$$

Gap de pool para cada atividade:

$$\text{gap\_pool}_A = \phi_A - v(\{A\}) = \frac{C_{\text{gap},AB} - C_{\text{mob}} - C_{\text{demob}}}{2}$$

**Interpretação direta**:
- Se `C_gap < C_mob + C_demob`: `gap_pool < 0` → compartilhamento é uma **economia** (mob/demob evitados > custo do gap)
- Se `C_gap > C_mob + C_demob`: `gap_pool > 0` → compartilhamento é um **overhead** (gap ativo excede mob/demob)

Esta é exatamente a condição de perpetuação de ADR-073:
`gap × c_idle < c_mob + c_demob ⟺ gap_pool < 0 ⟺ sharing é vantajoso`.

### 2.4 Decomposição para n arbitrário

Para n atividades em cadeia, os componentes do gap_pool de aᵢ são:

```
economia_mob_demob_i  = -(custo_mob_autonomo + custo_demob_autonomo) × (1 − κᵢ_mob)
overhead_ocioso_i     = C_gap_predecessora_i + C_gap_sucessora_i × proporção_causal_i

gap_pool_i = overhead_ocioso_i − economia_mob_demob_i
```

onde `κᵢ_mob` é a fração do custo de mobilização carregada por aᵢ na cadeia (1.0 para a
primeira atividade, 0.0 para as intermediárias, 1.0 para a última em demob).

Para n=2 com Shapley, `economia_mob_i = (C_mob + C_demob) / 2` e
`overhead_ocioso_i = C_gap / 2`, reproduzindo o resultado fechado acima.

---

## 3. Decisão

### D1 — Introduzir `PartitionamentoPool` no `RecursoContrato`

Estender `RecursoContrato` (canonical.py) com um mapa por item dos componentes causais:

```python
class CustoParticionadoItem(BaseModel):
    item_id: str
    custo_produtivo: float          # C_prod_i: semanas produtivas × custo_unit × R_i
    custo_mob_imputado: float       # fração de C_mob atribuída causalmente a este item
    custo_demob_imputado: float     # fração de C_demob atribuída causalmente a este item
    custo_ocioso_imputado: float    # C_gap atribuído causalmente (predecessor ou Shapley)
    custo_total_particionado: float # soma dos 4 componentes
    economia_vs_autonomo: float     # custo_autonomo - custo_total_particionado (>0 = economia)
```

### D2 — Atualizar `gap_pool` no `PontoEquilibrio` para ser signed

O `gap_pool_overhead` atual assume que o pool sempre gera custo adicional (nome "overhead"
induz viés). Renomear para `gap_pool_abs` (já existe no modelo) com semântica signed:

- `gap_pool_abs > 0`: item PAGA MAIS no contrato compartilhado do que pagaria autonomamente
  (ociosidade > economia de mob)
- `gap_pool_abs < 0`: item ECONOMIZA com o contrato compartilhado
  (mob/demob evitados > custo de ociosidade carregado)

### D3 — Expor decomposição no lever `fechar_gap_pool`

Quando `CustoParticionadoItem` estiver disponível, o lever deve conter no `restricoes`:

```python
restricoes = [
    f"Ociosidade imputada: R$ {custo_ocioso_imputado:,.0f}",
    f"Economia mob/demob: −R$ {economia_mob:,.0f}",
    f"Saldo líquido: {'overhead' if gap > 0 else 'economia'} R$ {abs(gap):,.0f}",
]
```

Quando `gap_pool < 0` (pool é vantajoso), o lever `fechar_gap_pool` NÃO deve aparecer no
painel de equilíbrio (não há gap a fechar — há uma vantagem a preservar). A skill-08 deve
omitir o lever quando `gap_pool_abs < 0`.

### D4 — Praticabilidade: fórmula corrigida (implementada)

Como derivado na seção 1.2, a fórmula do `gap_praticabilidade_abs` é corrigida para:

```python
gap_praticabilidade_abs = custo_total_autonomo × (1 − η̄)
```

Esta fórmula é **válida independentemente da presença de pool** porque `custo_total_autonomo`
representa o custo que o item teria com recursos próprios, sob as mesmas condições climáticas
do schedule atual. A decomposição de praticabilidade é portanto **ortogonal** à decomposição
de pool.

---

## 4. Consequências

### 4.1 Positivas

- `gap_pool` torna-se um indicador **diagnóstico bilateral**: positivo indica agenda operacional,
  negativo confirma que o modelo de pool está gerando economia real.
- O planner recebe um acionável direto: "reduzir gap de N semanas entre eap-1_5 e eap-1_9
  economiza R$ X de ociosidade de contrato".
- `gap_praticabilidade` deixa de ser zero estrutural e passa a refletir o custo real de
  clima/terreno, alimentando corretamente o lever `fechar_gap_praticabilidade` com magnitude
  proporcional a `(1 − η̄)`.

### 4.2 Negativas / Restrições

- `CustoParticionadoItem` requer que `_build_contratos_recurso` (skill-05) processe os gaps
  entre atividades no cronograma — disponível via `cron_lookup` mas não computado hoje.
- Para n > 3 atividades por contrato, o Shapley exato tem complexidade O(2^n). Usar a
  atribuição causal simplificada (D1) em vez de Shapley para n > 3.
- Se `rcpsp_spec` estiver ausente (modo MANUAL_ALLOCATION), `gap_pool_abs = 0` e a decomposição
  não é computada — comportamento correto pois não há contrato de pool.

---

## 5. Alternativas Consideradas

| Alternativa | Por que rejeitada |
|---|---|
| Machine-weeks proporcional sem decomposição (ADR-071 atual) | Opaca: não distingue economia de mob de custo de ociosidade |
| Custo produtivo puro (sem atribuir gap/mob) | Subavalia o custo real; `Σ partições < C_contrato` — violação de conservação |
| Shapley para todo n | O(2^n) computação; para n=10 atividades (AGIS) inviável em real-time; substituído por atribuição causal aproximada |
| Atribuição ao PREDECESSOR para C_gap | Economicamente incorreto: o gap existe por restrição DO SUCESSOR (predecessor já finalizou) |

---

## 6. Notas de Implementação

### Fase 1 — Implementada (este commit)
- `gap_praticabilidade_abs = custo_total_autonomo × (1 − η̄)` em skill-08 `_build_pe_for_equipe`
- `fator_clima_v` computado ANTES do cálculo de gap_praticabilidade (reordenação de código)

### Fase 2 — Implementada (sprint atual)
- Estendido `_build_contratos_recurso` (skill-05) com `_compute_particao_por_tipo`:
  computa `custo_produtivo`, `custo_mob_imputado` (Shapley igual), `custo_ocioso_imputado`
  (gap de espera imputado ao sucessor) e `economia_mob` por item da cadeia de perpetuação.
- Adicionado `CustoParticionadoItem` em canonical.py; campo `particao_por_item: list[CustoParticionadoItem]`
  em `RecursoContrato`.
- `_build_pe_for_equipe` (skill-08) consome `CustoParticionadoItem` quando disponível e
  decompõe `overhead_ocioso / economia_mob` no lever `fechar_gap_pool`.
- Lever `fechar_gap_pool` omitido quando `gap_pool_abs ≤ 0` (pool vantajoso — D3 correto).
- Invariante de conservação coberto em `tests/unit/test_adr076_pe_calibracao.py`.

### Invariante de conservação (obrigatório em testes)

```python
assert abs(
    sum(item.custo_total_particionado for item in contrato.particao_por_item)
    - contrato.custo_total_contrato
) < 0.02  # tolerância de arredondamento R$ 2 centavos
```
