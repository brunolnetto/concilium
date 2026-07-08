# NEP-035: Decomposição Causal da Eficiência η_s × η_p × η_w e Hierarquia de Observabilidade

**Status:** Implementado ✅ _(auditado 2026-06-08)_  
**Prioridade:** 🔴 Crítico  
**Área:** Arquitetura e Skills  
**Tipo:** Bug + Feature + Governança  
**Esforço:** XL  
**Identificado em:** 2026-06-01

> **Nota de auditoria (2026-06-08):** Modelo de dados implementado — `DistribuicaoSemanal` contém
> `eta_s`, `eta_p`, `eta_w`, `q_max_celula`, `perda_fisica` em `canonical.py`. Documentação
> desatualizada em relação ao código.

> **Reinterpretação (ADR-124, 2026-06-28):** a decomposição η = η_s · η_p · η_w é
> reinterpretada, não quebrada. `η_p` = η_clima · δ passa a ser o **modelo de planejamento**
> (`η_plan`). `η_s` (alocação n_j/n_max) e `η_w` (gestão residual) são reclassificados como
> fatores de **controle** — sem conteúdo diagnóstico no planejamento. Os campos `eta_s`/`eta_w`
> de `DistribuicaoSemanal` permanecem por retrocompatibilidade, marcados como CONTROLE.

---

## Contexto

O modelo de produção semanal implementado em `DistribuicaoSemanal` representa

```
q_ij = P_i · h · n_j · m_ij · p_j
```

onde `P_i` é a produtividade nominal, `h` as horas semanais, `n_j` os recursos
alocados, `m_ij` a eficiência de gestão e `p_j` a praticabilidade. A capacidade
teórica máxima é

```
q_max_ij = P_i · h · n_max · M_i_max
```

A eficiência semanal é então a decomposição multiplicativa exata

```
η_ij = q_ij / q_max_ij = η_s_j · η_p_j · η_w_ij
```

com os três componentes ortogonais:

| Componente | Fórmula | Significado |
|---|---|---|
| η_s_j = n_j / n_max | Eficiência de alocação | Fração da força planejada efetivamente fielded |
| η_p_j = p_j | Eficiência de praticabilidade | Fator climático + calendário |
| η_w_ij = m_ij / M_max | Eficiência de gestão | Utilização relativa à melhor gestão observável |

A NEP-032 (análise de custo 76→103M) e a implementação de `_build_dist_cell`
(ADR-082-cons) corrigiram o conflação `eficiencia = fator_clima` e separaram
`eficiencia` (= m_ij) de `fator_total` (= p_j × m_ij). Porém três problemas
estruturais permanecem:

---

## Problemas

### P1 — η_s é invisível: subalocação some da métrica

A célula atual não contém `η_s = n_j / n_max`. O denominador de referência
(`n_max × M_max`) nunca é materializado, de modo que uma atividade com metade
das equipes fielded a semana toda produz `η_total = η_p × η_w ≈ 0.9` (clima
bom) em vez do `η_total ≈ 0.45` correto. A perda de **alocação** é absorvida
silenciosamente pelo modelo de custo (via permanência estendida), mas
permanece invisível nos indicadores de eficiência.

### P2 — Agregação temporal usa denominador errado

`diagnostico_pe_builder._compute_item_metrics` computa

```python
eta_real = Σ(fator_total_j × n_j) / Σ(n_j)
```

i.e., pondera pelo recurso **realizado**, não pela **capacidade máxima**. A
agregação correta pelo teorema da média ponderada (Seção 5 do modelo) é

```
η_agg = Σ_j (η_j · q_max_j) / Σ_j q_max_j
```

Para atividades com ramp ou subalocação, os dois denominadores divergem e
`eta_real` fica sistematicamente superestimado. `fator_clima_medio` sofre a
mesma distorção.

### P3 — Perda física e custo de perda não são dimensões first-class

A perda produtiva `λ_ij = 1 − η_ij` existe implicitamente mas nunca é
computada como grandeza física (m³, t, km perdidos) nem convertida em custo de
ineficiência. A decomposição causal `gap_praticabilidade_abs` do PE-builder
(ADR-076/082) expressa um custo-de-perda em R$ para um único fator e não segue
a hierarquia de 4 níveis de observabilidade definida pelo modelo.

---

## Evidência Quantitativa (AGIS)

Executando o rastreamento de η por item sobre o canônico AGIS:

| Item | η_clima | η_efic (m_ij) | η_s | η_total_correto | η_total_atual |
|---|---|---|---|---|---|
| eap-1_5 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| eap-1_0 | 0.961 | 1.000* | ~0.50* | ~0.48 | 0.961 |
| eap-1_9 | 0.856 | 1.000* | ~0.53* | ~0.45 | 0.856 |

(*) n_max não está materializado; valores calculados indiretamente via fe_nec.

A `VAL-PROD-VS-PU` (NEP-035 antecessora) aponta divergências de +12% a +40%
não explicadas por clima — parte substancial desse resíduo é `η_s < 1` (mais
equipes do que o planejado por item, impostas pelo RCPSP para cumprir o prazo).

---

## Objetivo

1. Materializar `η_s`, `η_p`, `η_w` e `q_max_celula` como campos first-class
   em `DistribuicaoSemanal`.
2. Corrigir a agregação temporal para ponderar por capacidade `q_max`.
3. Adicionar `perda_fisica` (= `q_max_celula − q_executada`) como grandeza
   observável.
4. Estabelecer a hierarquia de 4 níveis de observabilidade como contrato do
   domínio.

---

## Decisão

### D1 — Campos de eficiência na célula semanal

Adicionar a `DistribuicaoSemanal`:

```python
q_max_celula:  float  # P_i · h · n_max · M_max (capacidade teórica)
eta_s:         float  # n_j / n_max  (alocação)
eta_p:         float  # p_j = fator_clima × fator_calendario  (praticabilidade)
eta_w:         float  # m_ij / M_max  (gestão; M_max = 1.0 até calibração)
perda_fisica:  float  # q_max_celula − q_executada  (m³, t, km perdidos)
```

`fator_total` passa a ser igual a `η_s × η_p × η_w` (relação de identidade
verificável em teste).

### D2 — `_build_dist_cell` recebe `n_max`

Assinatura atualizada:

```python
def _build_dist_cell(
    producao_semanal_base: float,  # P_i · h
    num_eq: int,                   # n_j
    n_max: int,                    # pico de alocação para a atividade
    fator_clima: float,            # η_p composto
    fator_calendario: float,
    quantitativo: float,
    qtd_acumulada: float,
    M_max: float = 1.0,
) -> DistribuicaoSemanal:
```

`q_max_celula = producao_semanal_base × n_max × M_max`  
`η_s = n_j / n_max`  
`η_p = fator_clima × fator_calendario`  
`capacidade_real = q_max_celula × η_s × η_p`  
`q_executada = min(capacidade_real × η_w, remanescente)` — onde `η_w = q_executada / capacidade_real`.

### D3 — n_max derivado do pico da atividade

- **Modo AUTO_SCHEDULE:** pré-computar `n_max = max(inferred_num_equipes)` sobre
  todos os offsets da atividade antes de construir as células.
- **Modo MANUAL:** `n_max = max(equipes_semanas.values(), default=1)`.

### D4 — Agregação por capacidade no diagnostico_pe_builder

```python
q_max_total = sum(d.q_max_celula for d in active)
if q_max_total > 0:
    eta_real = sum(_eta(d) * d.q_max_celula for d in active) / q_max_total
else:
    eta_real = sum(_eta(d) for d in active) / len(active)  # fallback
```

`fator_clima_medio` e `fator_calendario_medio` recebem a mesma correção de
pesos.

### D5 — Hierarquia de Observabilidade

Contrato de 4 níveis (implementado progressivamente):

| Nível | Métrica | Público | Período |
|---|---|---|---|
| 1 — Global | `η_obra(t)` = Σ Q_i / Σ Q_max_i por semana | Diretoria | Semanal |
| 2 — Causal | Waterfall η_s × η_p × η_w global | Gerência | Mensal |
| 3 — Atividades | Pareto L_ij (perda física/R$) | Planejamento | Por sprint |
| 4 — Fatorial | (η_s, η_p, η_w) por atividade+semana | Engenharia | Sob demanda |

---

## Escopo

### Incluído (esta NEP)

1. Novos campos em `DistribuicaoSemanal` (D1).
2. `_build_dist_cell` com `n_max` e M_max (D2+D3).
3. Pré-cômputo de `n_max` em AUTO e MANUAL (D3).
4. Correção de agregação em `diagnostico_pe_builder` (D4).
5. Testes unitários dos 3 componentes η + perda física.
6. Benchmark AGIS mantém saída equivalente (η não muda o planejamento).

### Excluído (→ NEP-036)

1. Formulação matricial `E ∈ ℝ^{I×T}`.
2. `EficienciaFieldBuilder` e série temporal `η_obra(t)`.
3. Decomposição log-linear e análise estatística.
4. Visualizações dos 4 níveis.

---

## Plano de Implementação

### Fase 1 — Modelo e builder (D1 + D2 + D3)

1. Adicionar campos a `DistribuicaoSemanal` em `canonical.py`.
2. Atualizar `_build_dist_cell` em `skill.py` (skill-04).
3. Atualizar `_emm_process_item` (manual): pré-computa `n_max`.
4. Atualizar `_convert_schedule_to_distribuicao` (AUTO): pré-computa `n_max`
   com dupla passagem sobre os offsets.
5. Atualizar testes `test_adr082_consistencia_base.py`.

### Fase 2 — Agregação (D4)

1. Corrigir `_compute_item_metrics` em `diagnostico_pe_builder.py`.
2. Validar que `eps_cross` (termo cruzado, já existente) é reportado quando
   agregação por q_max diverge da agregação por n_j acima de limiar.

### Fase 3 — Gate de perda física

1. Nova validação `VAL-PERDA-FISICA`: emite AVISO quando `Σ perda_fisica > 5%
   de Σ q_executada` para uma atividade (sinal de sub-entrega material).
2. Reusa `p_bar` de `_mean_praticabilidade` como contexto do aviso.

---

## Critério de Aceite

1. `DistribuicaoSemanal` tem campos `q_max_celula`, `eta_s`, `eta_p`, `eta_w`,
   `perda_fisica`.
2. `fator_total ≈ η_s × η_p × η_w` com tolerância 1e-6 em teste.
3. Semana de pico (`n_j = n_max`, `p_j = 1`): `η_s = η_p = 1.0`, `fator_total = η_w`.
4. `diagnostico_pe_builder` usa `q_max_celula` como peso de agregação.
5. Benchmark AGIS termina com `status_final = BLOQUEADO` (inalterado — η não
   altera o planejamento, apenas a observabilidade).
6. `VAL-PROD-VS-PU` flaga 11 itens (idem antes — mesma lógica, denominador
   correto não afeta o cálculo de `fe_nec`).

---

## Riscos

1. `n_max = 0` em atividades sem recurso atribuído → divisão por zero.
   Mitigação: `n_max = max(n_j, 1)`.
2. Dupla passagem em AUTO aumenta complexidade de `_convert_schedule_to_distribuicao`.
   Mitigação: pré-loop leve sobre `range(sa.duration_weeks)`.
3. Campos novos com `default=0.0` em canonical.json existente → retrocompat OK.

---

## Notas Técnicas

- `src/concilium/domain/models/canonical.py` — `DistribuicaoSemanal` (linha ~251)
- `src/concilium/application/skills/manifests/04-cronograma/skill.py` —
  `_build_dist_cell`, `_emm_process_item`, `_convert_schedule_to_distribuicao`
- `src/concilium/domain/services/diagnostico_pe_builder.py` —
  `_compute_item_metrics`
- `tests/unit/test_adr082_consistencia_base.py`

---

## Resultado Esperado

Ao final da NEP-035, cada célula semanal expressa rigorosamente os três
componentes causais da eficiência. A decomposição `η = η_s · η_p · η_w` é
verificável por inspeção, a agregação temporal é ponderada pela capacidade
teórica, e a perda física `q_max − q` é uma grandeza first-class disponível
para análise nos 4 níveis de observabilidade (implementados na NEP-036).
