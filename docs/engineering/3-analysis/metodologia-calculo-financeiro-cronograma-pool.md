# Metodologia de Cálculo Financeiro, Cronograma e Pool de Recursos

**Projeto:** Concilium — MendesLobo Construtora  
**Audiência:** Engenheiros e CEO  
**Versão:** 1.0 — 2026-06-12  
**Referências:** NEP-042, NEP-043, ADR-075, ADR-081, ADR-091, ADR-097, ADR-105

---

## 1. Introdução e Objetivo

Este documento formaliza a metodologia matemática adotada pelo sistema Concilium para:

1. Calcular o **custo operacional** de cada atividade a partir da composição de equipes
2. Derivar o **cronograma** como solução de um problema de otimização com restrições de recursos
3. Gerenciar o **pool compartilhado** de equipamentos como contrato de capacidade
4. Produzir o **breakdown financeiro** em três camadas e o **resultado agregado** de venda

O resultado final é uma cadeia auditável da forma:

```
Composição de equipe (catálogo)
    → Custo operacional autônomo (skill-05)
    → Cronograma RCPSP (skill-04)
    → Pool e contratos de recurso (skill-05 / ADR-091)
    → Bridge N1 → N2 → N3 (skill-06)
    → Indiretos + BDI → Venda (skill-07/08)
```

---

## 2. Definições Fundamentais

### 2.1 Índices e conjuntos

| Símbolo | Definição |
|---|---|
| `i` | Atividade (item da EAP) |
| `j` | Semana do cronograma |
| `r` | Tipo de recurso (equipamento) |
| `R_i` | Conjunto de recursos utilizados pela atividade `i` |
| `N_i` | Número de semanas produtivas da atividade `i` (duração efetiva) |
| `n_j` | Número de frentes (equipes paralelas) alocadas na semana `j` |

### 2.2 Parâmetros globais

| Símbolo | Valor | Definição |
|---|---|---|
| `S` | 4,33 | Semanas por mês |
| `h_dia` | configurável | Horas produtivas por dia |
| `d_semana` | 6 | Dias úteis por semana (regime de obra) |
| `h_sem` | `h_dia × d_semana` | Horas produtivas por semana |
| `h_mes` | `h_dia × d_semana × S` | Horas produtivas por mês |

### 2.3 Parâmetros por recurso `r`

| Símbolo | Definição |
|---|---|
| `w_r` | Salário base mensal (MO) ou custo de locação mensal (EQ) |
| `τ_r` | Taxa de encargos sociais (MO) |
| `κ_r` | Custo de manutenção por hora produtiva (EQ) |
| `f_r` | Consumo de combustível em litros por hora (EQ) |
| `p_d` | Preço do diesel por litro |

### 2.4 Parâmetros por atividade `i`

| Símbolo | Definição |
|---|---|
| `P_i` | Produtividade da equipe-padrão em unidades por hora |
| `Q_i` | Quantidade total a executar (unidades) |
| `n_{eq,i}` | Número de equipes paralelas (frentes) |
| `η_i` | Eficiência global: `η_s × η_p × η_w` |
| `η_s` | Eficiência de escala (fracção de semanas ativas vs. permanência) |
| `η_p` | Fator climático (dias úteis realizáveis / dias calendário) |
| `η_w` | Fator de eficiência operacional |

---

## 3. Custo Semanal de Recurso — `C_r^{sem}`

O custo semanal de cada categoria de recurso é a unidade atômica de todos os cálculos subsequentes.

### 3.1 Mão-de-obra (MO)

**Encargos sociais** são resolvidos por categoria sindical (ADR-097 §D1/D2):

```
τ_r =
    encargo_override              se explicitamente fornecido
    percentual_encargos_local     se configurado no item
    ENCARGOS_CLT_HORISTA          se categoria sindical = "horista"
    ENCARGOS_MENSALISTA           caso contrário
```

**Custo mensal MO** (com separação encargos — NEP-037):

```
custo_MO_base_r  = w_r × (1 + he_r)              [salário + horas extras]
custo_encargos_r = w_r × τ_r × (1 + he_r)        [encargos CLT separados]
custo_MO_r       = custo_MO_base_r + custo_encargos_r

Exceção (taxa all-in, nota "inclui encargos"):
    custo_MO_r = w_r × (1 + he_r)                [τ_r = 0 — evitar dupla contagem]
```

**Custo semanal MO:**

```
C_r^{sem}(MO) = custo_MO_r / S
```

### 3.2 Equipamento (EQ)

**Conversão para custo mensal** (ADR-034):

```
custo_locacao_mensal_r =
    p_r × d_semana × S          se unidade = "dia_calendario"
    p_r                         se unidade = "mes"
    p_r × h_mes                 se unidade = "hora_produtiva"

custo_manut_r = κ_r × h_mes

custo_EQ_r = custo_locacao_mensal_r + custo_manut_r
```

**Custo semanal EQ:**

```
C_r^{sem}(EQ) = custo_EQ_r / S
```

> Durante standby (gap entre atividades): locação continua integral; manutenção = 0.

### 3.3 Combustível (COMB)

```
consumo_r_L_h =
    override_projeto             se fornecido explicitamente
    override_cpu                 se configurado na CPU
    consumo_litros_hora          se campo do catálogo > 0
    custo_diesel_h / p_d         derivado da decomposição SBDI

C_r^{sem}(COMB) = consumo_r_L_h × h_sem × p_d
```

### 3.4 Custo semanal total do recurso `r`

```
C_r^{sem} = C_r^{sem}(MO) + C_r^{sem}(EQ) + C_r^{sem}(COMB)
```

---

## 4. Preço Unitário de Catálogo — `PU_cat`

O preço unitário de catálogo representa o custo para produzir **1 unidade** à eficiência plena, sem considerar escala, clima ou pool.

```
PU_cat_i = Σ_{r ∈ R_i} C_r^{sem} / (P_i × h_sem)

Decomposto:
    PU_MO_i   = Σ_r C_r^{sem}(MO)   / (P_i × h_sem)
    PU_EQ_i   = Σ_r C_r^{sem}(EQ)   / (P_i × h_sem)
    PU_COMB_i = Σ_r C_r^{sem}(COMB) / (P_i × h_sem)
    PU_MAT_i  = custo_material_mensal_i / (P_i × h_mes)

    PU_cat_i  = PU_MO_i + PU_EQ_i + PU_COMB_i + PU_MAT_i
```

**Identidade fundamental** (NEP-043): quando `η = 1`,

```
PU_cat_i × Q_i = C_{op,i}   [custo operacional total da atividade i]
```

Esta identidade é o critério de auditabilidade entre skill-05 e skill-06.

---

## 5. Custo Operacional Autônomo — Skill-05

### 5.1 Célula temporal

Para cada semana `j` da atividade `i`:

```
c_{ij} = n_j × [ C_fixo_i^{sem} + C_comb_i^{sem} × η_j ]

onde:
    C_fixo_i^{sem}  = (custo_MO_i + custo_EQ_i) / S
    C_comb_i^{sem}  = custo_COMB_i / S
    η_j             = fator_clima_j × fator_calendario_j
```

> A fórmula reflete que MO e EQ são **fixos** (pagos independente de produção), enquanto COMB é **variável** (proporcional à produção realizada).

### 5.2 Eficiência global

```
MW_i   = Σ_j n_j          [machine-weeks brutas — recursos × semanas contratadas]
eMW_i  = Σ_j (n_j × η_j)  [machine-weeks efetivas — produção real]

η_real_i = eMW_i / MW_i   [eficiência média ponderada]
```

### 5.3 Custo total autônomo

```
custo_aut_i = Σ_j c_{ij}
            = C_fixo_i^{sem} × MW_i + C_comb_i^{sem} × eMW_i
```

### 5.4 Quantidade produzida e permanência

```
Q_i  = P_i × h_sem × eMW_i     [unidades produzidas]
T_i  = MW_i / S                 [permanência em meses — duração real do contrato]
```

### 5.5 Ajuste por número de frentes (ADR-091)

Quando `n_{eq,i} > 1` frentes operam em paralelo, o custo armazenado por atividade representa **1 frente**:

```
custo_total_1fr_i = custo_aut_i / n_{eq,i}   [armazenado em EquipeDireta.custo_total]
custo_total_i     = custo_total_1fr_i × n_{eq,i} = custo_aut_i   [custo real]
```

> **Ponto crítico (NEP-043 Bug 1):** qualquer agregação deve usar `custo_total × n_{eq,i}`, nunca `custo_total` diretamente.

### 5.6 Ramp profile (ADR-074)

Quando a atividade possui perfil de rampa `ρ_i = [ρ_{i,0}, ..., ρ_{i,d-1}]`:

```
demanda_r_j = max(0, round(req_r_i × ρ_{i,j}))

onde ρ_{i,j} ∈ [0, 1] e len(ρ_i) = duration_weeks_i
```

O ramp profile reduz a demanda de recursos nas semanas de ramp-up/down, permitindo maior paralelismo no cronograma.

---

## 6. Modelo de Cronograma — RCPSP

### 6.1 Formulação do problema

O sistema resolve um **Resource-Constrained Project Scheduling Problem (RCPSP)**:

```
Minimizar:   C_max = max_i (start_i + duration_i)     [makespan]

Sujeito a:
    (P1) Precedência com threshold θ:
         start_j ≥ start_i + ⌈θ_{ij} × duration_i⌉   ∀ (i,j) ∈ E

    (P2) Capacidade de recursos:
         Σ_{i: start_i ≤ t < end_i} demanda_{r,i,t} ≤ pool_r   ∀ r, ∀ t

    (P3) Janela de execução (ADR-072):
         start_i + duration_i ≤ window_weeks_i         se definido
```

Onde `θ_{ij} ∈ [0, 1]` é o **completion threshold** da aresta `(i, j)`:
- `θ = 1.0`: FS clássico (sucessor começa após término completo)
- `θ = 0.5`: sucessor pode iniciar após 50% do predecessor concluído
- `θ = 0.0`: equivalente a SS (início simultâneo)

### 6.2 Seleção de algoritmo (ADR-075)

```
n ≤ 200 atividades → CP-SAT (solver exato OR-Tools, timeout 60s)
n > 200 atividades → LNS (Lagrangian Neighborhood Search heurístico)
```

**CP-SAT** resolve o RCPSP exato com garantia de otimalidade dentro do timeout.  
**LNS** usa relaxação Lagrangiana + SSGS (Serial Schedule Generation Scheme) para projetos grandes.

### 6.3 Heurísticas SSGS (fallback / análise comparativa)

Quando operado diretamente (SerialScheduler), cinco regras de prioridade são suportadas:

| Regra | Critério de prioridade |
|---|---|
| **MINSLK** | Menor folga total (critical-path aware) |
| **LPT** | Maior duração (longest processing time) |
| **MAXRES** | Maior demanda de recursos |
| **ES** | Menor earliest start (precedence-driven) |
| **GR** | Earliest feasible slot (greedy) |

### 6.4 Earliest start com threshold (ADR-081)

```
ES_i = max_{p ∈ predecessores(i)} (ES_p + ⌈θ_{p,i} × duration_p⌉)
LS_i = min_{s ∈ sucessores(i)} (LS_s - ⌈θ_{i,s} × duration_i⌉)

Folga total: TF_i = LS_i - ES_i
```

### 6.5 Qualidade do cronograma

O score composto avalia a qualidade relativa a um deadline:

```
score_makespan     = min(1, (deadline / makespan)²)    [50% do peso]
score_leveling     = max(0, 1 - CV(carga_semanal))     [20%]
score_idle         = 1 / (1 + semanas_ociosas)         [15%]
score_utilizacao   = utilização_média_recursos          [15%]

Q = 0.50 × score_makespan
  + 0.20 × score_leveling
  + 0.15 × score_idle
  + 0.15 × score_utilizacao

onde CV = desvio_padrão(carga_semanal) / média(carga_semanal)
```

> Leveling mede uniformidade de uso do pool: CV baixo = carga distribuída = pool bem aproveitado.

---

## 7. Pool de Recursos — Inferência e Otimização (ADR-091)

### 7.1 Conceito

O pool é um **contrato de capacidade compartilhada**: em vez de cada atividade ter seus próprios equipamentos dedicados, um conjunto de recursos é alocado ao projeto e distribuído entre atividades conforme a schedule.

```
pool_r = capacidade contratada do recurso r (ex: número de escavadeiras)
```

### 7.2 Requisitos por atividade

```
e_{i,r} = n_{eq,i} × Σ_{equip ∈ i} num_unidades_equip   ∀ r = tipo_recurso(equip)
```

### 7.3 Limites do pool

**Pool serial mínimo** (custo mínimo, prazo máximo):

```
pool_serial_r = max_i (e_{i,r})   [maior requisito individual]
```

**Pool de pico** (prazo mínimo, custo máximo):

```
pool_pico_r = max_t Σ_{i ativo em t} e_{i,r}   [pico de demanda simultânea]
```

### 7.4 Objetivos de dimensionamento

| Objetivo | Pool resultante | Comportamento |
|---|---|---|
| `minimizar_prazo` | `pool_pico` | Máxima paralelização; maior custo de pool |
| `minimizar_custo` | `pool_serial` | Mínimo contrato; maior duração |
| `balanceado` | `pool_bisect(α*)` | Menor pool que ainda atinge prazo-meta |

**Bisseção** (objetivo balanceado):

```
pool(α) = pool_serial + round(α × (pool_pico - pool_serial))   α ∈ [0, 1]

α* = min α : makespan(pool(α)) ≤ prazo_meta
```

Implementado com 12 iterações de bisseção sobre `α`.

### 7.5 Restrições de mercado

Após a inferência, limites de disponibilidade regional são aplicados:

```
pool_final_r = min(pool_inferido_r, disponibilidade_mercado_r)
```

Se `pool_final_r < e_{i,r}` para alguma atividade `i`, um aviso de inviabilidade é emitido.

---

## 8. Modelo de Três Camadas de Precificação (NEP-042)

### 8.1 Visão geral

O preço de venda de cada atividade é decomposto em três camadas analíticas, permitindo auditoria da diferença entre catálogo e realidade operacional.

```
N1: Catálogo puro         = PU_cat_i × Q_i
N2: Autônomo escalonado   = custo_aut_i  (= N1 + gap_escala_i)
N3: Pool instancial       = custo_pool_i  (= N2 + gap_praticabilidade_i ou < N2 por economia)
```

### 8.2 Camada 1 — Catálogo (N1)

```
N1_i = PU_cat_i × Q_i
```

Representa o valor de mercado da atividade: quanto custaria contratar no modelo de preço unitário de referência SINAPI/SBDI/catálogo.

**Agregado:**
```
N1 = Σ_i (PU_cat_i × Q_i)   [base de venda sem markup]
```

### 8.3 Camada 2 — Operacional Autônomo (N2)

```
PU_op_i = custo_aut_i / Q_i
         = C_fixo_i^{sem} / (P_i × h_sem × η_real_i) + C_comb_i^{sem} / (P_i × h_sem)
         = PU_fixo_cat_i / η_real_i + PU_comb_cat_i
```

A componente fixa (MO + EQ) é amplificada por `1/η_real` — ineficiência climática e de gestão.  
A combustível permanece proporcional à produção (não muda com eficiência).

**Gap de escala** — custo de arredondar frentes para cima:

```
gap_escala_i = custo_fixo_mensal_i × max(0, n_{eq,i} - 1) × T_nom_i

Onde T_nom_i = permanência nominal (meses planejados, sem eficiência)
```

O gap de escala representa o "aluguel extra" pago por frentes adicionais que não produzem proporcionalmente à capacidade contratada.

**Agregado:**
```
N2 = N1 + Σ_i gap_escala_i
```

### 8.4 Camada 3 — Pool Instancial (N3)

Cada atividade recebe uma fração do custo do contrato de pool proporcional ao seu uso (machine-weeks):

```
C_contrato_r = pool_r × custo_unit_semanal_r × semanas_contrato_r
             + custo_mob_desmob_r
             + custo_standby_r

fracao_{i,r} = MW_{i,r} / Σ_k MW_{k,r}   [proporção de uso do recurso r]

custo_pool_{i,r} = fracao_{i,r} × C_contrato_r
                 + custo_mob_imputado_{i,r}
                 + custo_ocioso_imputado_{i,r}

custo_pool_i = Σ_r custo_pool_{i,r}
```

**Gap de praticabilidade** — custo climático residual após escala:

```
gap_praticabilidade_i = (PU_MO_i + PU_EQ_i) × Q_i × (1/η_i - 1) × n_{eq,i}
```

**Economia de pool** (quando o pool é mais eficiente que autônomo):

```
economia_pool_i = custo_aut_i - custo_pool_i   [positivo = pool é mais barato]
```

**Agregado:**
```
N3 = Σ_i custo_pool_i + custos_mob_demob_globais
```

### 8.5 Bridge N1 → N2 → N3

```
ΔN12 = N2 - N1 = Σ_i gap_escala_i         [impacto de paralelismo]
ΔN23 = N3 - N2 = Σ_i gap_praticabilidade_i [impacto climático residual]
                - economia_pool_total       [ganho por compartilhamento]

fator_quantizacao   = N2 / N1   [amplificação por escala]
fator_praticabilidade = N3 / N2 [amplificação/redução por pool vs. autônomo]
```

O bridge é o instrumento analítico que explica **por que** o custo real difere do catálogo de referência.

---

## 9. Custo Indireto — Skill-07

Custos indiretos são organizados por categoria (administração, supervisão, mobilização, QSMS, etc.) com driver de distribuição temporal:

```
driver = "permanencia":
    custo_total_ind_k = custo_mensal_k × (n_semanas / S)
    distribuição = uniforme por semana (última absorve resíduo de arredondamento)

driver = "one_time" (mobilização/desmobilização):
    metade na semana 0, metade na semana final
```

**Decomposição por sub-categoria (ADR-090):**

```
custo_total_ind_k → proporcionalmente distribuído entre:
    c_MO_k     → BDI_MO
    c_EQ_k     → BDI_EQ
    c_COMB_k   → BDI_material
    c_verba_k  → BDI_indireto
    c_mob_k    → BDI_indireto
```

Encargos sobre MO indireta (NEP-037 D4):

```
τ_ind = ENCARGOS_MENSALISTA   [mensalistas na equipe de apoio]
c_encargos_ind_k = c_MO_k × τ_ind / (1 + τ_ind)
c_MO_base_ind_k  = c_MO_k - c_encargos_ind_k
```

---

## 10. BDI e Venda Final

### 10.1 Taxas de BDI por componente

```
BDI_MO       → taxa sobre mão-de-obra direta e indireta
BDI_EQ       → taxa sobre equipamentos (locação + manutenção)
BDI_material → taxa sobre material, combustível e consumíveis
BDI_indireto → taxa sobre verbas e mobilização
BDI_encargos → taxa sobre encargos sociais (NEP-037, ADR-012)
```

### 10.2 Venda direta com BDI (ADR-085, ADR-090)

Para cada atividade `i`, o preço de venda é calculado sobre o custo instancial de pool:

```
venda_i = Σ_r [
    C_inst_MO_{i,r}   × (1 + BDI_MO)
    + C_inst_EQ_{i,r}   × (1 + BDI_EQ)
    + C_inst_COMB_{i,r} × (1 + BDI_material)
    + C_inst_MAT_{i,r}  × (1 + BDI_material)
]

venda_direto_total = Σ_i venda_i
```

### 10.3 Venda indireta com BDI

```
venda_indireta = Σ_k [
    c_MO_k   × (1 + BDI_MO)
    + c_EQ_k   × (1 + BDI_EQ)
    + c_COMB_k × (1 + BDI_material)
    + c_verba_k × (1 + BDI_indireto)
    + c_mob_k   × (1 + BDI_indireto)
]
```

### 10.4 Resultado financeiro agregado

```
venda_total    = venda_direto_total + venda_indireta
custo_total    = custo_direto_total + custo_indireto_total
lucro_bruto    = venda_total - custo_total
margem_bruta   = lucro_bruto / venda_total   [%]
```

---

## 11. Breakdown e Agregações — Quadro de Referência

### 11.1 Breakdown por atividade (nível mais granular)

| Campo | Fórmula | Onde calculado |
|---|---|---|
| `custo_total_1fr` | `custo_aut_i / n_{eq,i}` | skill-05 |
| `custo_total` | `custo_total_1fr × n_{eq,i}` | agregação |
| `permanencia_efetiva` | `MW_i / S` | skill-05 |
| `eta_real` | `eMW_i / MW_i` | skill-05 |
| `PU_cat` | `Σ C_r^{sem} / (P_i × h_sem)` | skill-06 |
| `PU_operacional` | `custo_aut_i / Q_i` | skill-06 |
| `custo_pool` | `Σ_r (fracao_{i,r} × C_contrato_r)` | skill-05 |
| `gap_escala` | `c_fixo_mes_i × (n_{eq,i}-1) × T_nom_i` | skill-06 |
| `gap_praticabilidade` | `(PU_MO + PU_EQ) × Q_i × (1/η_i - 1) × n_{eq,i}` | skill-06 |

### 11.2 Breakdown categorial agregado

| Categoria | Inclui |
|---|---|
| `mao_obra` | MO + encargos CLT (de pool + autônomo) |
| `eq_aluguel` | Locação + manutenção + mob/demob + ocioso |
| `material` | Combustível + consumíveis + materiais |

Nota: combustível é classificado em `material` (ADR-090) por ser consumível — não equipamento.

### 11.3 Cadeia de agregação financeira

```
Nível atividade:
    custo_aut_i           → custo autônomo da atividade (1 frente × n_eq)
    custo_pool_i          → custo pool imputado à atividade

Nível direto:
    custo_direto_total    = Σ_i (custo_pool_i × n_{eq,i})
    venda_direto_total    = Σ_i venda_i

Nível projeto:
    N1 = Σ_i (PU_cat_i × Q_i)      [catálogo]
    N2 = N1 + Σ_i gap_escala_i      [autônomo escalado]
    N3 = N2 ± ajuste_pool           [pool instancial]
    N4 = custo_direto_total         [custo operacional real das equipes]
    venda_final = venda_direto + venda_indireta
```

---

## 12. Procedimento de Cálculo — Passo a Passo

### Passo 1 — Composição de equipe (catálogo)

Para cada atividade `i`, ler do catálogo:
- Funções de MO: `(w_r, τ_r, num_pessoas_r)`
- Equipamentos: `(locacao_r, manut_hora_r, consumo_r)`
- Produtividade: `P_i` e quantidade `Q_i`

Calcular `C_r^{sem}` para cada recurso e derivar `PU_cat_i`.

### Passo 2 — Cronograma (RCPSP)

1. Construir `ActivityDAG` com precedências e thresholds
2. Derivar `required_resources` por atividade (ADR-091 D4)
3. Se `n ≤ 200`: resolver com CP-SAT (exato, timeout 60s)  
   Se `n > 200`: resolver com LNS (Lagrangian + SSGS)
4. Obter `start_i`, `end_i`, `n_j` por semana

### Passo 3 — Pool e contratos (ADR-091)

1. Inferir pool: `minimizar_prazo`, `minimizar_custo` ou `balanceado` (bisseção)
2. Aplicar restrições de mercado
3. Re-resolver RCPSP com pool fixado → obter schedule definitivo
4. Imputar custo de pool por atividade (proporção de machine-weeks)

### Passo 4 — Custo operacional (skill-05)

Para cada atividade e cada semana do schedule:
1. Calcular `c_{ij}` usando `C_fixo_i^{sem}` e `η_j`
2. Acumular `custo_aut_i`, `MW_i`, `eMW_i`, `η_real_i`
3. Derivar permanência `T_i` e quantidade produzida `Q_i`
4. Armazenar `custo_total_1fr_i = custo_aut_i / n_{eq,i}`

### Passo 5 — Precificação e bridge (skill-06)

1. Calcular `N1 = Σ PU_cat × Q`
2. Calcular `gap_escala_i` para cada atividade
3. Calcular `N2 = N1 + Σ gap_escala`
4. Calcular `gap_praticabilidade_i` e `custo_pool_i`
5. Calcular `N3 = Σ custo_pool + mob_global`
6. Produzir bridge: `ΔN12`, `ΔN23`, fatores de quantização e praticabilidade

### Passo 6 — Indiretos e BDI (skill-07/08)

1. Calcular custo de cada categoria indireta por driver
2. Decompor em sub-categorias para BDI diferenciado
3. Calcular venda direta com BDI sobre custo pool instancial
4. Calcular venda indireta com BDI sobre custos indiretos
5. Agregar: `venda_total`, `custo_total`, `margem_bruta`

---

## 13. Calibração por Referência Externa (NEP-029)

Quando o catálogo fornece `custo_hora_total_referencia` (C_ref — custo horário observado em obra):

```
custo_mensal_ref = C_ref × h_sem × S

Decomposição por frações SBDI:
    f_MO    = PU_MO_sbdi / PU_total_sbdi
    f_EQ    = PU_EQ_sbdi / PU_total_sbdi
    f_COMB  = PU_diesel_sbdi / PU_total_sbdi

custo_MO_cal  = custo_mensal_ref × f_MO
custo_EQ_cal  = custo_mensal_ref × f_EQ
custo_COMB_cal = custo_mensal_ref × f_COMB
```

Esta calibração sobrepõe a composição teórica de equipe pelo custo observado em campo, mantendo as frações proporcionais do SBDI como distribuidor.

---

## 14. Limitações e Premissas Documentadas

| Premissa | Impacto se violada |
|---|---|
| Encargos CLT fixos por categoria sindical | Subestima custo se encargos reais diferem da tabela |
| Combustível proporcional à produção | Subestima custo em períodos de baixa eficiência com motor ocioso |
| Demanda flat no CP-SAT (sem ramp profile) | Schedule conservador; pico usado mesmo em semanas de ramp |
| `custo_hora_total_referencia` = custo da equipe inteira (não por frente) | Bug 3 NEP-043: dividir por n_max no pool path |
| Pool contract = custo proporcional a machine-weeks | Ignora efeitos de ordem de mobilização |
| Fator climático = `fator_clima × fator_calendario` | Pode não capturar variabilidade intra-semana |

---

*Documento gerado a partir do código-fonte do sistema Concilium (skill-04, skill-05, skill-06, skill-07, skill-08) e NEPs 042/043. Para dúvidas sobre implementação, consultar os ADRs referenciados.*
