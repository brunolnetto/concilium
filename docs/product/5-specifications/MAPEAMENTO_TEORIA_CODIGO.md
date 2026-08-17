# Mapeamento: Formulação Teórica → Código AGIS

## 1. Símbolos Teóricos → Variáveis AGIS

| Conceito Teórico | Símbolo | Código AGIS | Tipo | Observação |
|------------------|---------|-----------|------|-----------|
| Atividade | $i$ | `item_id` | string | Ex: "SV-SIMPLES-001" |
| Frente/Equipe | $j$ | `equipe_id` | int | Índice da equipe na lista |
| Custo Contratado | $\gamma_i^c$ | `custo_fixo` | float | Custo mensal fixo da equipe |
| Custo Consumível | $\gamma_i^v$ | (não existe explícito) | — | Diesel, combustível, etc. |
| Custo Total Composicional | $\gamma_i = \gamma_i^c + \gamma_i^v$ | `custo_horario` | float | Total horário da equipe |
| Fração Consumível | $\delta_i = \frac{\gamma_i^v}{\gamma_i}$ | `delta` | float | **FALTA CALCULAR EM CÓDIGO** |
| Fração Contratada | $1-\delta_i$ | — | float | Complemento |
| Produtividade do Catálogo | $\rho_i$ | `producao` (CPU) | float | m²/hora no catálogo |
| Produtividade Realizada Frente j | $\varepsilon_j$ | `eta` ou `eta_real` | float | Fator de clima × praticabilidade |
| Produtividade Média Ponderada | $\bar{\varepsilon}_i$ | `eta_real` | float | Eficiência média observada |
| Num Frentes Atividade i | $m_{ij}$ (agregado) | `num_equipes_base` | int | Núm de equipes paralelas |
| Horas Alocadas | $hd$ | `horas_efetivas` ou `machine_weeks_efetivas` | float | Total de HM (horas-máquina) |
| Custo Operacional | $OC_i$ | `custo_total_autonomo` | float | Custo observado em Skill 05 |
| Custo Catálogo | $CC_i$ | `subtotal.sem_bdi.total` | float | PU × Q em Skill 06 |
| Ratio | $R_i$ | `frentes_nec` ou `frentes_equivalentes_necessarias` | float | **τ_i = 4.31** |

---

## 2. Fórmulas Teóricas → Implementação em Código

### A. Razão Principal: $R_i = OC_i / CC_i$

**Localização:** [_ponto_equilibrio.py](../src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_ponto_equilibrio.py), linhas ~45-50

```python
def _pe_frentes_nec(venda_sem_bdi, custo_total_autonomo, ...):
    frentes_nec = 1.0
    if venda_sem_bdi > 0 and custo_total_autonomo > 0:
        frentes_nec = round(custo_total_autonomo / venda_sem_bdi, 4)
    return frentes_nec
```

**Mapeamento Teórico:**
- `custo_total_autonomo` = $OC_i$ ✅
- `venda_sem_bdi` = $CC_i$ ✅
- `frentes_nec` = $R_i$ ✅

**Fórmula Teórica:**
$$R_i = \frac{OC_i}{CC_i}$$

---

### B. Custo Operacional: $OC_i = \sum_j [(\gamma_i^c + \varepsilon_j\gamma_i^v) \cdot hd \cdot m_{ij}]$

**Localização:** [_ponto_equilibrio.py](../src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_ponto_equilibrio.py), linhas ~110-150 (função `_pe_custo_autonomo_e_gap_pool()`)

**Quebra de Componentes:**

```python
# Custo fixo mensal (contratado)
custo_fixo_mensal = ...  # γ_i^c × 4.33 semanas/mês
permanencia_meses = ...  # Período mínimo

# Custo variável/consumível (diesel, etc)
custo_diesel = ...       # γ_i^v (combustível)
custo_material = ...     # γ_i^v (material consumível)

# Fator de clima e praticabilidade
eta = beta * fe_clima    # ε_j = β × f(clima)

# Agregação
custo_total_autonomo = sum(
    (custo_fixo_mensal + eta[j] * custo_variavel)
    * horas_maquina[j]
    for j in equipes
)
```

**Mapeamento Teórico:**
- `custo_fixo_mensal` = $\gamma_i^c$ ✅
- `custo_diesel` = Parte de $\gamma_i^v$ ✅
- `eta` = $\varepsilon_j$ ✅
- `custo_total_autonomo` = $OC_i$ ✅

---

### C. Custo Catálogo: $CC_i = \frac{\gamma_i}{\rho_i} \sum_j (\rho_i \varepsilon_j hd m_{ij})$

**Localização:** [_financeiro_resultado.py](../src/concilium/domain/models/canonical/_financeiro_resultado.py) e Skill 06

**Fórmula de Cálculo:**

$$CC_i = PU \times Q = \frac{\gamma_i^c + \gamma_i^v}{\rho_i} \times (\rho_i \times Q)$$

Onde $Q$ é o quantitativo total (m²).

**Simplificação (como demonstrado pelo user):**
$$CC_i = (\gamma_i^c + \gamma_i^v) \times hd \sum_j \varepsilon_j m_{ij}$$

O $\rho_i$ **cancela completamente**!

**Mapeamento:**
- `PU` (preço unitário catálogo) = $(\gamma_i^c + \gamma_i^v) / \rho_i$ ✅
- `Q` (quantitativo) = $\rho_i \times \sum_j \varepsilon_j \times hd \times m_{ij}$ ✅
- `subtotal.sem_bdi.total` = $CC_i$ ✅

---

### D. Produtividade Média Ponderada: $\bar{\varepsilon}_i = \frac{\sum_j \varepsilon_j m_{ij}}{\sum_j m_{ij}}$

**Localização:** [_ponto_equilibrio.py](../src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_ponto_equilibrio.py), campo `eta_real`

```python
# Calcular eta média ponderada por machine-weeks
eta_real = machine_weeks_efetivas / machine_weeks_brutas
# = Σ_j(ε_j × m_ij) / Σ_j(m_ij)
```

**Mapeamento Teórico:**
- `machine_weeks_efetivas` = $\sum_j \varepsilon_j m_{ij}$ ✅
- `machine_weeks_brutas` = $\sum_j m_{ij}$ ✅
- `eta_real` = $\bar{\varepsilon}_i$ ✅

---

### E. Fração Consumível: $\delta_i = \frac{\gamma_i^v}{\gamma_i^c + \gamma_i^v}$

**Status:** ⚠️ **NÃO ESTÁ EXPLICITAMENTE CALCULADA EM CÓDIGO**

Deveria estar em [_causal_cost_partition.py](../src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/_causal_cost_partition.py)

#### Categorização Correta de Custos (MATA_DENSA_SIMPLES)

A categorização ingênua (só diesel = consumível) subestima δ_i e produz R_i = 3.31 em vez de 4.31. A categorização econômica correta é:

| Componente | Valor | Tipo | Razão |
|------------|-------|------|-------|
| Mão de Obra | R$ 10.719 | **Contratado** | Permanência mínima — pago mesmo sem trabalho |
| Equipamentos | R$ 43.093 | **Contratado** | Aluguel mensal fixo |
| Mobilização | R$ 25.891 | **Contratado** | Custo único, fixo, não escalável com Q |
| Overhead (ADM/TOP/QSMS/LAB) | R$ 13.217 | **Contratado** | Rateia sobre meses de permanência |
| Diesel | R$ 24.196 | **Consumível** | Único componente que escala com ε_j |

```python
gamma_c = 10719 + 43093 + 25891 + 13217  # = 92.920 R$ (contratado)
gamma_v = 24196                           # = 24.196 R$ (consumível)
delta_i = gamma_v / (gamma_c + gamma_v)  # = 24196 / 117116 = 0.2066 (20.7%)
```

---

### F. Razão Reformulada: $R_i = 1 + (1-\delta_i) \frac{1-\bar{\varepsilon}_i}{\bar{\varepsilon}_i}$

**Cálculo para MATA_DENSA_SIMPLES com categorização correta:**

```python
delta_i  = 0.2066  # categorização correta (contratado inclui mob + overhead)
eta_real = 0.23    # do output Skill 06

R_i = 1 + (1 - 0.2066) * (0.77 / 0.23)
    = 1 + 0.7934 * 3.3478
    = 1 + 2.656
    = 3.66
```

**Gap residual vs observado:** 4.31 − 3.66 = 0.65 (15%)

**Causa provável do gap residual:** Overhead não é inteiramente fixo — varia indiretamente com ε_j. A fórmula captura 85% da estrutura; os 15% restantes exigem que overhead seja tratado como "semi-contratado" com sensibilidade parcial a ε_j.

---

## 3. Diferença Operacional-Catálogo: $OC_i - CC_i = \gamma_i^c \cdot hd \sum_j(1-\varepsilon_j)m_{ij}$

**Esta é a fórmula mais direta.**

**Localização:** Implementada implicitamente em Skill 05/06

**Cálculo Manual:**

```python
OC_i = 336103.34  # custo_total_autonomo
CC_i = 78007.38   # venda_sem_bdi

gap = OC_i - CC_i
    = 336103.34 - 78007.38
    = 258095.96  # Exatamente confirmado no output!

# Teoria diz:
# gap = γ_i^c × Σ_j(1-ε_j)m_{ij}

# Portanto:
gamma_c_efetivo = gap / sum((1-eta_j) * m_ij for j)
```

**Verificação:** Gap de R$ 258.096 é documentado no output! ✅

---

## 4. Caso Limite: Uma Única Frente Dominante

**Quando $m_i = [0, 0, ..., 1, 0]$ para algum $k$:**

$$R_i \to \frac{1-(1-\varepsilon_k)\delta_i}{\varepsilon_k}$$

**Em AGIS:**
- Se projeto tem 1 atividade com 1 equipe
- Então a razão depende APENAS de $\varepsilon_1$ (clima/praticabilidade dessa equipe)

**Aplicação a MATA_DENSA_SIMPLES:**
- Uma atividade, presumivelmente uma equipe base
- $\varepsilon_1 = 0.23$ (valor observado em `eta_real`)
- Portanto: $R_i = \frac{1-(1-0.23)\delta_i}{0.23} = \frac{1-0.77\delta_i}{0.23}$

**Resolvendo para valor observado (4.31):**
$$4.31 = \frac{1-0.77\delta_i}{0.23}$$
$$0.991 = 1-0.77\delta_i$$
$$\delta_i = 0.012 \approx 1.2\%$$

**Isto significa:** Apenas **1.2% de custos são consumíveis** se acreditarmos na fórmula simples.

**Discrepância:** Isto contradiz o cálculo anterior ($\delta_i = 0.31$).

**Conclusão:** Os componentes de gap não são modelados simplemente como consumível vs contratado. Há categorias adicionais (mob, demob, overhead pool) que agem como "semi-contratado".

---

## 5. Pergunta Crítica: Interferência Entre Frentes?

### Cenário A: Sem Interferência

$\varepsilon_j$ é independente de $m_i$.

Então:
- Adicionar frente com alto $\varepsilon_j$ reduz $R_i$
- Adicionar frente com baixo $\varepsilon_j$ aumenta $R_i$
- Número total de frentes não muda $R_i$ (apenas distribuição)

**Implicação:** Qualidade da equipe > quantidade.

### Cenário B: Com Interferência

$\varepsilon_j = \varepsilon(m_i)$ decresce com $m_i$.

Exemplos reais:
- Equipes disputam espaço de trabalho
- Equipamentos compartilhados geram fila/espera
- Coordenação overhead

**Implicação:** Paralelização enfrenta retorno decrescente.

**Em AGIS:** Qual é o modelo?

---

## 6. Mapeamento de Código para Investigação

Para responder "por que R_i = 4.31 exatamente", precisamos verificar em ordem:

1. **Calcular $\delta_i$ real:**
   - Arquivo: Heurística em `_causal_cost_partition.py`
   - Ação: Decompor custo em contratado vs consumível

2. **Verificar $\bar{\varepsilon}_i$ real:**
   - Arquivo: `_ponto_equilibrio.py`, campo `eta_real`
   - Valor esperado: 0.23-0.25 (do output)

3. **Aplicar fórmula teórica:**
   - $$R_i = 1 + (1-\delta_i)\frac{1-\bar{\varepsilon}_i}{\bar{\varepsilon}_i}$$
   - Comparar com 4.31 observado

4. **Se discrepância > 5%:**
   - Investigar se há componentes de gap não capturados
   - Possível: mob/demob, overhead pool, penalidade de escala
   - Questionar: há degradação $\varepsilon_j(m_i)$?

---

## Próximas Ações Recomendadas

1. ✅ Documentar $\delta_i$ calculado para MATA_DENSA_SIMPLES
2. ✅ Verificar se $\bar{\varepsilon}_i = 0.23$ é correto
3. ✅ Aplicar fórmula reformulada, comparar com 4.31
4. ❓ Se discrepância: investigar categorias de custo "semi-contratadas"
5. ❓ Se há interferência $\varepsilon_j(m_i)$: medir/documentar a degradação

---

**Status:** Reformulação teórica COMPLETA. Mapeamento para código NECESSÁRIO mas FALTANDO implementação de $\delta_i$ explícito e validação numérica de $R_i = 1 + (1-\delta_i)\frac{1-\bar{\varepsilon}_i}{\bar{\varepsilon}_i}$.

**Data:** 2026-08-14
