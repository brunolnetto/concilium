# Metodologia de Planejamento — Visão do Engenheiro de Planejamento

**Projeto:** Concilium — MendesLobo Construtora  
**Audiência:** Engenheiros de Planejamento e Orçamento  
**Versão:** 1.0 — 2026-06-12

---

## 1. O que o sistema resolve

O sistema responde a uma pergunta que todo engenheiro de planejamento conhece:

> *Dado um conjunto de atividades com precedências, produtividades e um pool de equipamentos disponível — qual a distribuição de frentes ao longo do tempo que entrega a obra no prazo com o menor custo de pool?*

Essa pergunta tem nome formal: **RCPSP** (Resource-Constrained Project Scheduling Problem). O sistema a resolve computacionalmente, mas o resultado é interpretável em linguagem de planejamento: cronograma, histograma de recursos e curva de custo.

---

## 2. O cronograma como variável de decisão

### 2.1 O que é decidido

Para cada atividade `i`, o sistema determina:

- **Semana de início** (`start_i`) e **semana de término** (`end_i`)
- **Número de frentes paralelas** por semana (`n_j`) — quantas equipes idênticas operam simultaneamente

A semana é a unidade de tempo padrão do cronograma. A duração produtiva de cada atividade (`duration_i`, em semanas) é calculada a partir da produtividade de catálogo, da quantidade a executar e do número de frentes.

### 2.2 Precedências com threshold

O cronograma respeita **relações de precedência** entre atividades. A relação padrão é **FS (Finish-to-Start)**, mas o sistema suporta **ligas parciais**:

```
Atividade B pode iniciar quando A atingiu θ × 100% do seu progresso físico

    θ = 1,0  →  FS clássico: B começa após A terminar completamente
    θ = 0,5  →  B começa quando A está 50% concluída (mobilização adiantada)
    θ = 0,0  →  SS: B pode iniciar junto com A
```

O threshold permite modelar situações como *"a terraplanagem do trecho 2 pode iniciar quando o trecho 1 atingir 70% de conclusão"*, sem precisar criar sub-atividades artificiais na EAP.

### 2.3 Janela de execução

Cada atividade pode ter uma **janela de execução** — um prazo máximo de sazonalidade, contrato ou restrição de licença. Atividades que excedem sua janela geram conflito de viabilidade.

---

## 3. O histograma de recursos

O resultado do cronograma produz, para cada semana `j` e cada tipo de recurso `r`:

```
demanda_{r,j} = Σ_{atividades ativas na semana j} (frentes_i × unidades_r_por_frente_i)
```

Este é o **histograma de recursos** — equivalente ao que um engenheiro de planejamento lança manualmente no MS Project ou Primavera.

### 3.1 Restrição de pool

O histograma deve respeitar a **capacidade do pool**:

```
demanda_{r,j} ≤ pool_r     para toda semana j
```

O pool é o número máximo de unidades do recurso `r` disponíveis no canteiro (por exemplo, 3 escavadeiras, 2 caminhões-pipa).

Quando a demanda simultânea de atividades excederia o pool, o sistema **atrasa** algumas atividades — exatamente como o planejador faz no nivelamento de recursos manual, mas de forma sistemática e considerando todas as precedências.

### 3.2 Ramp-up e ramp-down

Atividades com **perfil de mobilização escalonada** têm demanda reduzida nas primeiras e últimas semanas. Uma escavadeira nova no contrato passa por inspeção e habilitação na primeira semana; uma desmobilização começa a liberar frentes antes do término formal. O histograma reflete essa variação semana a semana.

---

## 4. Frente-semana — a unidade de produção

O conceito central de agregação é a **frente-semana** (ou *machine-week* na notação técnica):

```
frente-semana = 1 equipe completa operando por 1 semana inteira
```

### 4.1 Frentes-semana brutas vs. efetivas

```
MW_brutas_i  = Σ_j n_j                      total de equipe-semanas contratadas
MW_efetivas_i = Σ_j (n_j × η_j)             total de equipe-semanas produtivas

η_j = fator_clima_j × fator_calendário_j     eficiência da semana j
```

Uma semana com 30% de chuva tem `η = 0,70`. A equipe esteve lá, consumiu salário e aluguel de máquina, mas produziu 70% do esperado.

### 4.2 Eficiência média da atividade

```
η_médio_i = MW_efetivas_i / MW_brutas_i
```

Este é o indicador de **aproveitamento do contrato**. Uma atividade com `η_médio = 0,80` teve 20% de perdas climáticas e operacionais ao longo de sua duração. O sistema usa este índice para calcular custo real vs. custo de catálogo.

---

## 5. Qualidade do cronograma

O sistema produz um **índice de qualidade** composto para comparar alternativas de alocação:

| Componente | Peso | O que mede |
|---|---|---|
| Aderência ao prazo | 50% | Quão próximo o makespan está do deadline |
| Nivelamento de recursos | 20% | Uniformidade do histograma (evitar picos) |
| Ociosidade | 15% | Semanas sem produção dentro do período do contrato |
| Utilização | 15% | Percentual médio de uso do pool disponível |

**Nivelamento** é medido pelo coeficiente de variação (CV) da carga semanal:

```
CV = desvio_padrão(carga_semanal) / média(carga_semanal)

Nivelamento = max(0, 1 − CV)
```

CV baixo → histograma uniforme → pool bem aproveitado → custo de mobilização/ociosidade menor.

---

## 6. O pool como contrato de capacidade

### 6.1 Pool dedicado vs. pool compartilhado

Na abordagem **autônoma** (sem pool), cada atividade tem seus próprios recursos. A escavadeira da atividade A fica parada esperando a atividade A terminar, mesmo que a atividade B precise de escavadeira ao mesmo tempo e esteja sem.

Na abordagem de **pool compartilhado**, o contrato é feito sobre a **capacidade total** — o número máximo de unidades necessárias simultaneamente em qualquer semana. Esse pico é determinado pelo cronograma:

```
pool_r = max_j (demanda_{r,j})    [dimensionamento pelo pico]
```

### 6.2 Dimensionamento do pool

Há três estratégias de dimensionamento, com tradeoff explícito entre prazo e custo:

| Estratégia | Pool contratado | Efeito |
|---|---|---|
| **Minimizar prazo** | Pico máximo (todas as atividades podem correr em paralelo) | Maior custo de pool, menor duração |
| **Minimizar custo** | Mínimo serial (maior requisito individual) | Menor contrato, maior duração |
| **Balanceado** | Interpolação por bisseção | Menor pool que ainda atinge o prazo-meta |

O dimensionamento balanceado é equivalente ao que um planejador experiente faz: encontra o menor "patamar" de recursos que ainda permite terminar dentro do prazo.

### 6.3 Custo de pool por atividade

Após definido o pool, o custo do contrato é **rateado entre as atividades proporcionalmente ao uso**:

```
fração_uso_{i,r} = frentes-semana da atividade i no recurso r
                   ────────────────────────────────────────────
                   total de frentes-semana de todos no recurso r

custo_pool_{i,r} = fração_uso_{i,r} × custo_total_contrato_r
                 + mob/demob imputado
                 + ociosidade imputada (gaps entre atividades ativas)
```

Este rateio é análogo ao **rateio de custo de mobilização** por item da EAP — prática conhecida em orçamentação de obras.

---

## 7. As Três Camadas de Precificação — N1, N2, N3

Esta é a estrutura analítica central do sistema. Ela explica, de forma auditável, **por que o custo real da obra difere do valor de referência de catálogo**.

### 7.1 N1 — Catálogo puro

```
N1 = Σ_i (PU_catalogo_i × Q_i)
```

É o valor que sairia se o contrato fosse por preço unitário de catálogo (SINAPI, SBDI, composição teórica), à eficiência plena, sem considerar o modelo real de operação. É a **linha de base de mercado**.

### 7.2 N2 — Custo autônomo (com escala e eficiência)

```
N2 = N1 + Σ_i gap_de_escala_i
```

**Gap de escala** é o custo adicional gerado por frentes paralelas. Quando uma atividade precisa de 3 frentes simultâneas, você contrata 3 equipes completas — mas a produtividade total raramente é exatamente 3× a de uma equipe. O excedente é o gap de escala.

Matematicamente, para atividades com `n` frentes:

```
gap_de_escala_i = custo_fixo_mensal_i × (n_frentes_i − 1) × permanência_nominal_i
```

A relação entre N1 e N2 revela o **impacto do paralelismo** no custo — quanto mais frentes simultâneas, maior a diferença.

**O custo autônomo total** é o que a atividade custaria se executada com equipes dedicadas, pagando cada frente pelo tempo inteiro de permanência na obra, incluindo perdas de eficiência climática:

```
custo_autônomo_i = MO + EQ fixos (por frente-semana contratada)
                 + COMB variável (por frente-semana produtiva × η_j)
```

### 7.3 N3 — Custo com pool instancial

```
N3 = Σ_i custo_pool_i
```

O pool compartilhado redistribui os recursos entre atividades, reduzindo o tempo ocioso de equipamentos. Quando bem dimensionado, `N3 < N2` — a **economia de pool** vem justamente de evitar que cada atividade carregue o custo integral de "sua" máquina parada nos intervalos.

**Gap de praticabilidade** é o custo climático residual — o que a ineficiência de η < 1 adiciona ao N2 antes do benefício do pool:

```
gap_de_praticabilidade_i = (custo_MO + custo_EQ) por unidade × Q_i × (1/η − 1) × n_frentes_i
```

É o custo de produzir a quantidade contratada em condições reais (com chuva, feriados) versus condições de catálogo (eficiência = 1).

### 7.4 Leitura do Bridge N1 → N2 → N3

```
N1   Base de catálogo (mercado)
+ ΔN12  Gap de escala (custo do paralelismo)
= N2   Custo autônomo escalado (o que custaria sem pool)
± ΔN23  Ajuste do pool (economia por compartilhamento − gap climático residual)
= N3   Custo instancial de pool (o custo real projetado)
```

| Situação | Leitura do bridge |
|---|---|
| N3 ≈ N1 | Obra simples, eficiência alta, pool bem calibrado |
| N3 > N2 | Pool mal dimensionado ou eficiência muito baixa — custa mais que autônomo |
| N2 >> N1 | Alto grau de paralelismo ou produto com composição diferente do catálogo |
| N3 << N2 | Pool muito eficiente — grande economia por compartilhamento |

---

## 8. Relação com o cronograma

O cronograma e o custo não são independentes — cada escolha de alocação de frentes afeta ambos:

```
Mais frentes → menor duração (N_i diminui) → menor permanência → menor custo fixo
            mas → maior pico de pool → maior contrato → maior custo de pool

Menos frentes → maior duração → maior permanência → maior custo fixo
             mas → menor pico de pool → menor contrato
```

O sistema resolve essa tensão simultaneamente: o cronograma minimiza a duração respeitando o pool, e o pool é dimensionado considerando a schedule. O resultado é um **ponto de equilíbrio** entre prazo e custo — o que o engenheiro de planejamento buscaria iterativamente numa planilha.

### 8.1 Criticidade das atividades

O cronograma classifica cada atividade por tipo de criticidade:

| Tipo | Condição | Interpretação |
|---|---|---|
| **Crítica de prazo (PC)** | Folga CPM ≈ 0 | Qualquer atraso atrasa a obra |
| **Crítica de recurso (RC)** | Folga RCPSP << folga CPM | Seria livre se tivesse mais pool |
| **Gateway** | Compressão de k frentes reduz makespan | Boa candidata para aceleração |
| **Bloqueada** | Mais frentes aumentam makespan | Aceleração contraproducente |
| **Livre** | Folga absorve variações | Sem impacto em prazo ou pool |

A distinção entre PC e RC é especialmente valiosa: uma atividade RC parece crítica mas na verdade só é crítica porque o pool está limitando — aumentar o pool a libera sem precisar mudar as precedências.

### 8.2 Análise de compressão

Para atividades candidatas à aceleração, o sistema calcula o **ROI de compressão**:

```
ROI_i(k) = semanas_economizadas_no_makespan(k frentes)
            ────────────────────────────────────────────
            custo_adicional_de_pool(k frentes)

k ∈ {2, 3, 4}   [múltiplos de frentes testados]
```

Um ROI alto significa que adicionar frentes nessa atividade comprime o cronograma de forma eficiente. Um ROI baixo (ou negativo) indica que a compressão não vale economicamente — ou a atividade não está no caminho crítico, ou a demanda adicional de pool gera custo maior que o benefício de prazo.

---

## 9. Ciclo analítico do planejador

O fluxo que o sistema executa corresponde ao ciclo que um engenheiro de planejamento percorreria manualmente:

```
1. Levantamento de quantitativos (Q_i) e produtividades (P_i)
        ↓
2. Definição de precedências e thresholds de avanço físico
        ↓
3. Cálculo de duração por atividade e montagem do cronograma base (CPM)
        ↓
4. Identificação do pico de demanda de recursos → dimensionamento do pool
        ↓
5. Nivelamento: deslocamento de atividades RC para reduzir pico
        ↓
6. Avaliação de trade-off prazo × custo de pool
        ↓
7. Cálculo de custo por atividade (autônomo → pool)
        ↓
8. Bridge N1 → N2 → N3: auditoria da diferença catálogo × realidade
        ↓
9. Aplicação de BDI e resultado de venda
```

Cada passo é auditável: o sistema preserva os valores intermediários (N1, N2, N3, gap de escala, gap de praticabilidade, frente-semana efetiva) para que qualquer número no resultado final possa ser rastreado até sua origem na composição de equipe.

---

## 10. O que o planejador controla

O sistema não substitui o julgamento do engenheiro de planejamento — ele o estrutura. Os parâmetros que o planejador define e que determinam o resultado são:

| Parâmetro | Impacto |
|---|---|
| **Precedências e thresholds** | Estrutura do cronograma e caminhos críticos |
| **Objetivo do pool** (prazo / custo / balanceado) | Dimensionamento do contrato |
| **Prazo-meta** | Ponto de corte para bisseção do pool |
| **Fatores de eficiência** (η_clima, η_calendário) | Custo real vs. catálogo |
| **Horas extras (he%)** | Multiplicador do custo de MO |
| **Overrides de consumo de combustível** | Calibração do COMB para condições específicas |
| **Custo de hora de referência (C_ref)** | Calibração por dado histórico de obra |

A calibração por `C_ref` é particularmente poderosa: quando o planejador tem dados históricos de custo/hora em condições reais (levantamento de campo, planilha de apontamento), esses dados substituem a composição teórica de catálogo, preservando apenas as frações relativas entre MO, EQ e COMB.
