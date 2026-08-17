# Modelo Rigoroso: Produtividade, Permanência e Custo Real vs Catálogo

**Objetivo:** Derivar de primeiros princípios como custos operacionais (real) se relacionam com custos de catálogo, sem forçar elegância matemática.

**Abordagem:** Partir do modelo de caixa (cash model), derivar algebricamente cada passo, identificar inconsistências, responder questões abertas.

---

## Seção 1: Definições de Base e Unidades

### 1.1 Variáveis Primitivas

| Variável | Símbolo | Unidade | Significado |
|----------|---------|---------|------------|
| **Quantitativo** | $Q$ | m², m³, etc. | Volume total de trabalho |
| **Produtividade Nominal** | $\rho$ | unid/hora | Saída por hora em condições ideais |
| **Fator Clima** | $\beta$ | adimensional | Multiplicador $\in [0,1]$, reduz produtividade em dias ruins |
| **Fator Técnico** | $\phi$ | adimensional | Multiplicador $\in [0,1]$, reduz produtividade por complexidade |
| **Produtividade Realizada** | $\varepsilon = \beta \times \phi$ | adimensional | Fração da produtividade nominal efetivamente alcançada |
| **Horas Nominais** | $H_{\text{nom}}$ | horas | Horas para executar $Q$ a $\rho$ nominal |
| **Horas Reais** | $H_{\text{real}}$ | horas | Horas realmente necessárias (com $\varepsilon < 1$) |
| **Permanência (meses)** | $M$ | meses | Quantos meses a equipe é contratada |

### 1.2 Custo por Elemento

| Elemento | Símbolo | Unidade | Tipo |
|----------|---------|---------|------|
| **Custo Contratado** | $c_m$ | R$/mês | Pagamento mensal fixo (MO + EQ aluguel) |
| **Custo Consumível** | $c_h$ | R$/hora | Custo por hora de operação real (diesel, desgaste) |

**Importante:** $c_m$ é pago por cada mês **independentemente de horas trabalhadas**. $c_h$ é pago apenas por horas realmente trabalhadas.

### 1.3 Fração Consumível

$$\delta = \text{Proporção de custos que são consumíveis (variáveis com uso)}$$

Se considerarmos um "custo composicional horário nominal":

$$c_{\text{comp}} = \frac{c_m}{h_m} + c_h$$

Onde $h_m = 4.33 \times 44 \approx 190$ horas/mês (aproximação grosseira).

Então:

$$\delta = \frac{c_h}{c_m/h_m + c_h}$$

Mas isto depende de como se rateia o mensal. **Deixaremos isto pendente por enquanto.**

---

## Seção 2: Cálculo de Horas

### 2.1 Horas Nominais (100% eficiência)

Se executássemos com produtividade nominal $\rho$ e zero ineficiência:

$$H_{\text{nom}} = \frac{Q}{\rho}$$

**Exemplo:** Q = 10.000 m², ρ = 20 m²/hora → H_nom = 500 horas.

### 2.2 Horas Reais (com eficiência $\varepsilon$)

A produtividade realizada é $\varepsilon \times \rho$. Logo:

$$H_{\text{real}} = \frac{Q}{\varepsilon \times \rho} = \frac{H_{\text{nom}}}{\varepsilon}$$

**Exemplo (continuando):** Se $\varepsilon = 0.42$, então $H_{\text{real}} = 500 / 0.42 = 1.190$ horas.

### 2.3 Relação: Inflação de Horas

Define-se o fator de inflação:

$$\eta_h = \frac{H_{\text{real}}}{H_{\text{nom}}} = \frac{1}{\varepsilon}$$

No exemplo: $\eta_h = 1 / 0.42 = 2.38$.

**Interpretação:** 2.38× mais horas são necessárias.

**Notação Critical:** Não use $\bar{\varepsilon}$ para isto; use $\eta_h$ ou "inflação de horas". É o **recíproco** de eficiência.

---

## Seção 3: Permanência e Contratação

### 3.1 Semanas Nominais vs Permanência Mínima

Sabendo $H_{\text{real}}$ e considerando que uma equipe trabalha $h_w = 44$ horas/semana:

$$T_{\text{semanas}} = \frac{H_{\text{real}}}{h_w}$$

**Exemplo:** $T = 1.190 / 44 \approx 27$ semanas.

Mas uma equipe é contratada com **permanência mínima** de $p_{\min}$ (tipicamente 1 mês = 4,33 semanas).

Quantos períodos de permanência mínima são necessários?

$$M = \left\lceil \frac{T_{\text{semanas}}}{p_{\min}} \right\rceil$$

**Exemplo:** $M = \lceil 27 / 4.33 \rceil = \lceil 6.23 \rceil = 7$ meses.

### 3.2 Ociosidade

Semanas de permanência: $M \times p_{\min}$  
Semanas de trabalho: $T_{\text{semanas}}$  
Semanas ociosas: $M \times p_{\min} - T_{\text{semanas}}$

**Exemplo:** $7 \times 4.33 = 30.31$ semanas disponíveis, mas apenas 27 trabalhadas → 3.31 semanas ociosas.

---

## Seção 4: Custo Operacional (Real)

### 4.1 Definição

O **custo operacional** é quanto você realmente paga:

$$OC = \text{(Custo contratado)} + \text{(Custo consumível)}$$

$$\boxed{OC = M \times c_m + H_{\text{real}} \times c_h}$$

**Primeiro termo:** Você contrata por $M$ meses, cada mês custa $c_m$.  
**Segundo termo:** Você trabalha $H_{\text{real}}$ horas, cada hora custa $c_h$.

### 4.2 Exemplo Numérico

Suponha:
- $c_m = 22.000$ R$/mês (MO 5k + EQ 15k + Overhead 2k)
- $c_h = 100$ R$/hora (diesel + desgaste)
- $M = 7$ meses
- $H_{\text{real}} = 1.190$ horas

$$OC = 7 \times 22.000 + 1.190 \times 100 = 154.000 + 119.000 = 273.000 \text{ R}$$

---

## Seção 5: Custo de Catálogo (Teórico)

### 5.1 Interpretação do Catálogo

Um catálogo de preços (tipo SINAPI, TCPO) fornece um **Preço Unitário (PU)** para cada serviço:

$$PU = \text{R}/\text{m}^2 \text{ (ou outra unidade)}$$

Este PU é calculado como:

$$PU = \frac{\text{Custo Composicional Total por Unidade de Trabalho}}{\text{1 unidade}}$$

Tipicamente, o PU é derivado de:
- Custo de mão de obra (com produtividade nominal)
- Custo de equipamento (com produtividade nominal)
- Custo de material/combustível (com produtividade nominal)

**Crítico:** O PU **assume 100% de eficiência** e uma certa estrutura de permanência do catálogo.

### 5.2 Modelo de PU: Enfoque Bottom-Up

Suponha que o PU foi calculado como:

$$PU = \frac{c_m}{p_{\min} \times h_w \times \rho} + \frac{c_h}{\rho}$$

**Interpretação:**
- Primeira fração: Custo mensal ratificado por (horas em 1 mês) × (produtividade) = trabalho nominal em 1 mês
- Segunda fração: Custo por hora / produtividade por hora = custo por unidade de saída

### 5.3 Custo Total de Catálogo

$$CC = PU \times Q$$

### 5.4 Exemplo Numérico

Continuando com os dados anteriores:

$$p_{\min} = 4,33 \text{ semanas}, \quad h_w = 44 \text{ h/sem}$$
$$h_{\min} = 4,33 \times 44 \approx 190 \text{ horas/mês}$$
$$\rho = 20 \text{ m}^2/\text{hora}$$
$$\text{Saída nominal por mês} = 190 \times 20 = 3.800 \text{ m}^2$$

$$PU = \frac{22.000}{3.800} + \frac{100}{20} = 5,79 + 5,00 = 10,79 \text{ R}/\text{m}^2$$

$$CC = 10,79 \times 10.000 = 107.900 \text{ R}$$

---

## Seção 6: Razão R_i — Derivação Rigorosa

### 6.1 Definição

$$R_i = \frac{OC}{CC}$$

### 6.2 Substituição Algébrica

$$R_i = \frac{M \times c_m + H_{\text{real}} \times c_h}{PU \times Q}$$

Sabemos que:

$$H_{\text{real}} = \frac{Q}{\varepsilon \times \rho}$$

$$PU = \frac{c_m}{h_{\min} \times \rho} + \frac{c_h}{\rho}$$

Onde $h_{\min} = p_{\min} \times h_w$ é a quantidade de horas em um período de permanência mínima.

### 6.3 Simplificação (Assumindo Aproximações)

**Aproximação 1:** Negligenciar o overhead de rateio de mês parcial. Assumir que $M$ é bem-definido e exato.

**Aproximação 2:** Decomposição de PU em dois termos.

$$R_i = \frac{M \times c_m + \frac{Q}{\varepsilon \rho} c_h}{\left( \frac{c_m}{h_{\min} \rho} + \frac{c_h}{\rho} \right) Q}$$

$$= \frac{M \times c_m + \frac{Q}{\varepsilon \rho} c_h}{\frac{c_m Q}{h_{\min} \rho} + \frac{c_h Q}{\rho}}$$

Multiplicar numerador e denominador por $\rho$:

$$R_i = \frac{M \times c_m \rho + \frac{Q}{\varepsilon} c_h}{\frac{c_m Q}{h_{\min}} + c_h Q}$$

### 6.4 Separação de Termos

Isto fica complicado. Vamos separar a contribuição contratada e consumível:

**Termo Contratado:**

$$\text{Numerador}_{\text{contratado}} = M \times c_m$$
$$\text{Denominador}_{\text{contratado}} = \frac{c_m Q}{h_{\min} \rho}$$

Razão:
$$\frac{M \times c_m}{\frac{c_m Q}{h_{\min} \rho}} = \frac{M \times h_{\min} \rho}{Q}$$

**Termo Consumível:**

$$\text{Numerador}_{\text{consumível}} = \frac{Q}{\varepsilon} c_h$$
$$\text{Denominador}_{\text{consumível}} = \frac{c_h Q}{\rho}$$

Razão:
$$\frac{\frac{Q}{\varepsilon} c_h}{\frac{c_h Q}{\rho}} = \frac{\rho}{\varepsilon}$$

### 6.5 Combinação

Se os termos fossem independentes (o que não são completamente):

$$R_i \approx \frac{\text{Contrib. Contratada} + \text{Contrib. Consumível}}{\text{Normalização}}$$

Mas isto requer pesos. **Esta é a dificuldade:**

O numerador mistura duas coisas pagas de forma diferente (contratado paga por mês, consumível por hora).  
O denominador assume um modelo de catálogo que rateia mês em horas.

**Conclusão:** A fórmula $R_i = 1 + (1-\delta)\frac{\eta_h}{1+\eta_h}$ (com $\eta_h = 1/\varepsilon$) não sai naturalmente. Ela emerge se fizermos certas assunções sobre como $\delta$ é definido e aplicado.

---

## Seção 7: Reconstrução com Acompanhamento de Unidades

### 7.1 Estratégia: Expressar Tudo em R$/unidade

Seja $U$ a unidade de trabalho (m², m³, etc.).

**Custo Operacional por Unidade:**

$$oc = \frac{OC}{Q} = \frac{M \times c_m + H_{\text{real}} \times c_h}{Q}$$

$$= \frac{M \times c_m}{Q} + \frac{H_{\text{real}}}{Q} \times c_h$$

$$= \frac{M \times c_m}{Q} + \frac{1}{\varepsilon \rho} \times c_h$$

**Custo de Catálogo por Unidade:**

$$cc = PU = \frac{c_m}{h_{\min} \rho} + \frac{c_h}{\rho}$$

### 7.2 Razão R_i

$$R_i = \frac{oc}{cc} = \frac{\frac{M \times c_m}{Q} + \frac{c_h}{\varepsilon \rho}}{\frac{c_m}{h_{\min} \rho} + \frac{c_h}{\rho}}$$

### 7.3 Problema Persiste: Dependência de Q em M

O termo $\frac{M \times c_m}{Q}$ depende de $Q$!

Isto significa: **R_i muda com quantitativo.**

Para um projeto pequeno (Q pequeno), M é fixo (ex: 1 mês), então $M \times c_m / Q$ é grande.  
Para um projeto grande (Q grande), M pode ser um pouco maior (ex: 2 meses), mas $M \times c_m / Q$ é menor.

**Isto é economicamente correto:** Um projeto pequeno tem proporcionalmente MAIS custo fixo (permanência mínima), logo R_i é maior.

### 7.4 Caso Especial: Projeto Muito Grande

Se $Q \to \infty$ e $M \propto T \propto Q/(\varepsilon \rho)$ (permanência cresce com tamanho):

$$M = \left\lceil \frac{H_{\text{real}}}{h_{\min}} \right\rceil \approx \frac{H_{\text{real}}}{h_{\min}} = \frac{Q/(\varepsilon \rho)}{h_{\min}}$$

Então:

$$\frac{M \times c_m}{Q} \approx \frac{c_m}{h_{\min} \varepsilon \rho}$$

E:

$$R_i \approx \frac{\frac{c_m}{h_{\min} \varepsilon \rho} + \frac{c_h}{\varepsilon \rho}}{\frac{c_m}{h_{\min} \rho} + \frac{c_h}{\rho}}$$

$$= \frac{\frac{1}{\varepsilon}(c_m / h_{\min} + c_h)}{\frac{1}{1}(c_m / h_{\min} + c_h)}$$

$$= \frac{1}{\varepsilon}$$

**Resultado importante:** Para projetos muito grandes, $R_i \approx 1/\varepsilon$, ou equivalentemente $R_i = \eta_h = H_{\text{real}} / H_{\text{nom}}$.

Isto faz sentido: Se você trabalha com eficiência $\varepsilon$, os custos escalam por $1/\varepsilon$.

---

## Seção 8: Interpretação de R_i

### 8.1 O Que R_i > 1 Significa

$R_i > 1$ significa: **O custo operacional real é MAIOR que o custo de catálogo.**

Isto NÃO significa automaticamente "inviável". Significa:
- Você está pagando mais que o preço tabelado
- Se o contratante cobre apenas até CC, você perde dinheiro
- Se o contratante cobre com markup/BDI suficiente, pode ser viável

### 8.2 Quando R_i Realmente Significa Inviabilidade

Se o preço de venda é fixado em $CC$ ou similar, então:

$$\text{Margem} = \text{Preço} - OC = CC - OC = CC(1 - R_i)$$

Se $R_i > 1$, margem < 0, projeto é deficitário.

Mas isto depende do **modelo de precificação**.

### 8.3 Fatores que Aumentam R_i

1. **Reduzir ε (eficiência pior)**
   - Clima ruim, terreno difícil
   - R_i = 1/ε para grandes projetos

2. **Aumentar c_m (custo contratado)**
   - Equipamento caro, overhead alto

3. **Aumentar c_h (custo consumível)**
   - Combustível caro

4. **Reduzir Q (projeto pequeno)**
   - Permanência mínima M não comprime com tamanho
   - R_i sobe

### 8.4 Fatores que Reduzem R_i

1. **Aumentar ε (eficiência melhor)**
   - Clima bom, terreno fácil, equipe experiente

2. **Reduzir c_m (custo contratado)**
   - Negociar aluguel, reduzir overhead

3. **Aumentar Q (projeto grande)**
   - Rateia permanência mínima sobre mais trabalho

4. **Paralelizar com outros projetos**
   - Compartilhar permanência mínima
   - Efetivamente reduzir M para cada projeto individual

---

## Seção 9: O Caso MATA_DENSA_SIMPLES

### 9.1 Dados Observados

- Q = 10.000 m²
- H_real ≈ 1.190 horas
- OC ≈ 336.103 R$
- CC ≈ 78.007 R$
- R_i ≈ 4.31

### 9.2 Interpretação Econômica

R_i = 4.31 significa que você pagou 4,31× o preço de catálogo pelos mesmos 10.000 m².

Possíveis razões:
1. **Permanência mínima não amortizada:** Projeto é curto, então M permanece em 1-2 meses, mesmo sendo pequeno
2. **Eficiência muito baixa:** ε ≈ 0.23 implica η_h = 1/0.23 ≈ 4.35, próximo a R_i observado
3. **Overhead concentrado:** Custos indiretos (mob, demob) não estão espalhados sobre múltiplas atividades

### 9.3 Conclusão para MATA_DENSA_SIMPLES

Não é que o modelo está "errado". É que:
- **Projeto é muito pequeno** (10k m², 1 semana de trabalho real)
- **Permanência contratada é longa** (7 meses)
- **Proporção de overhead é alta**

Resultado: R_i ≈ 4.31 é matematicamente correto, dado estas restrições.

Para viabilizar, seria necessário:
- Aumentar Q (paralelize com outro projeto)
- Reduzir permanência mínima (compartilhe equipe)
- Melhorar ε (condições melhores)

---

## Seção 10: Questões Abertas Reexaminadas

### 10.1 "Como R_i se comporta com múltiplas frentes?"

Se você tem $n$ frentes paralelas, cada uma com eficiência $\varepsilon_j$:

$$H_{\text{real, total}} = \sum_j \frac{Q_j}{\varepsilon_j \rho}$$

$$OC = M \times c_m + H_{\text{real, total}} \times c_h$$

Se todas as frentes compartilham a mesma permanência M (alocadas ao mesmo período):

$$R_i = \frac{M \times c_m + \sum_j H_j c_h}{\sum_j (PU_j Q_j)}$$

Isto **não fatora** em um R_i único por frente. Há economia de escala.

**Conclusão:** Múltiplas frentes com permanência compartilhada reduzem R_i agregado.

### 10.2 "A produtividade individual degrada com múltiplas frentes?"

Modelo proposto:
$$\varepsilon_j = \varepsilon_0 - k \times (n-1)$$

Onde $k$ é a taxa de degradação por frente adicional.

Isto precisaria ser calibrado empiricamente. **Não está no modelo atual.**

### 10.3 "Como classificar overhead como consumível vs contratado?"

**Overhead de Permanência** (ADM, TOP, mobilização):
- Melhor tratado como **contratado** (pago por mês alocado)

**Overhead de Consumo** (QSMS, LAB):
- Melhor tratado como **consumível** (escala com trabalho real)

Mas na prática, há overhead "semi-contratado" que varia indiretamente.

---

## Seção 11: Fórmula Simplificada para Grandes Projetos

Para projetos grandes onde M cresce com T (e T cresce com Q/ε):

$$\boxed{R_i \approx \frac{1}{\varepsilon} \quad \text{(para } Q \text{ grande)}}$$

Ou, em termos de horas:

$$\boxed{R_i \approx \frac{H_{\text{real}}}{H_{\text{nom}}} = \eta_h}$$

**Interpretação:** O custo real é amplificado simplesmente porque você precisa de mais horas para fazer o mesmo trabalho.

Para projetos pequenos, há também a parcela de overhead não-amortizado:

$$\boxed{R_i = \frac{1}{\varepsilon} + \text{(overhead fixo) / Q}}$$

A segunda parcela decresce com Q (projetos maiores amortizam melhor).

---

## Seção 12: Síntese de Derivação

```
COMEÇAR:
  Q (quantitativo)
  ρ (produtividade nominal)
  ε = β × φ (eficiência real)
  c_m (custo contratado/mês)
  c_h (custo consumível/hora)
  p_min (permanência mínima)

↓

CALCULAR HORAS:
  H_nom = Q / ρ
  H_real = Q / (ε × ρ) = H_nom / ε
  η_h = H_real / H_nom = 1/ε (inflação)

↓

CALCULAR PERMANÊNCIA:
  T_sem = H_real / h_w  (semanas de trabalho)
  M = ⌈T_sem / p_min⌉  (meses contratados)
  Ociosidade = M × p_min - T_sem

↓

CALCULAR CUSTOS:
  OC = M × c_m + H_real × c_h  (operacional real)
  CC = (c_m/(h_min×ρ) + c_h/ρ) × Q  (catálogo)

↓

CALCULAR RAZÃO:
  R_i = OC / CC
  
  Para Q grande: R_i ≈ 1/ε
  Para Q pequeno: R_i ≈ 1/ε + (M × c_m / Q) × (fator)

↓

INTERPRETAR:
  R_i > 1: Custo real exceeds catálogo
  Se preço fixado em CC: Margem = CC(1 - R_i)
  Se R_i >> 1 e margem negativa: Projeto inviável
  
  Soluções: Aumentar Q, melhorar ε, reduzir c_m, paralelizar
```

---

## Conclusão

O modelo original tem o **conceito certo** mas a **álgebra fraca**. A reconstrução rigorosa mostra:

1. ✅ R_i > 1 é possível e economicamente significativo
2. ✅ R_i depende tanto de ε quanto de Q (tamanho do projeto)
3. ✅ Para grandes projetos, R_i ≈ 1/ε (simples e elegante)
4. ✅ Para pequenos projetos, permanência mínima domina
5. ✅ Múltiplas atividades/frentes com permanência compartilhada reduzem R_i

A fórmula "elegante" $R_i = 1 + (1-\delta)(1-\eta_h)/\eta_h$ é **aproximação** válida em certos regimes, não uma verdade universal. E ainda requer definição consistente de δ em termos de c_m e c_h.

---

## Seção 13: Extensão para Múltiplas Atividades

### 13.1 Estrutura: DAG de Atividades

Um projeto real é um conjunto de atividades com possíveis dependências entre si. Formalmente:

- $V = \{1, \ldots, n\}$ — conjunto de atividades (nós)
- $E \subseteq V \times V$ — dependências $(i, j)$ significam "i deve terminar antes de j iniciar"
- O par $(V, E)$ forma um **grafo dirigido acíclico (DAG)**

Um projeto pode conter **múltiplos DAGs independentes** (componentes não conectados).

### 13.2 Recursos: Definição de Pool

Seja $K$ o conjunto de **recursos físicos** (cada recurso = uma dupla equipamento + operador).

Para cada recurso $k \in K$ e atividade $i \in V$, definimos:

| Variável | Símbolo | Significado |
|----------|---------|------------|
| Custo contratado do recurso $k$ | $c_m^{(k)}$ | R$/mês, pago por permanência |
| Custo consumível do recurso $k$ | $c_h^{(k)}$ | R$/hora de operação real |
| Recurso $k$ alocado à atividade $i$? | $a_{ki} \in \{0, 1\}$ | Variável de alocação |
| Horas reais de $k$ em $i$ | $H_{ki}$ | horas efetivas trabalhadas |

### 13.3 Custo Consumível (por atividade, por recurso)

O custo consumível é separável por atividade:

$$C^v_{ki} = H_{ki} \times c_h^{(k)}$$

$$C^v_{\text{total}} = \sum_{k \in K} \sum_{i \in V} a_{ki} \cdot C^v_{ki}$$

Onde:

$$H_{ki} = a_{ki} \cdot \frac{Q_i}{\varepsilon_i \cdot \rho_i} \cdot w_{ki}$$

com $w_{ki}$ a fração do tempo de $i$ atribuída ao recurso $k$ (necessário se múltiplos recursos fazem a mesma atividade em paralelo).

### 13.4 Custo Contratado (nível do pool)

Este é o ponto crítico: **o custo contratado não é separável por atividade**.

Para o recurso $k$, sua janela de permanência é determinada pelo **início mais cedo** e **fim mais tarde** entre todas as atividades que ele serve:

$$t^{\text{start}}_k = \min_{i : a_{ki}=1} \text{start}(i)$$
$$t^{\text{end}}_k = \max_{i : a_{ki}=1} \text{end}(i)$$
$$T_k = t^{\text{end}}_k - t^{\text{start}}_k$$

E o número de meses contratados, respeitando permanência mínima $p_{\min}$:

$$M_k = \left\lceil \frac{T_k}{p_{\min}} \right\rceil$$

$$C^c_{\text{pool}} = \sum_{k \in K} M_k \times c_m^{(k)}$$

**Consequência importante:** O custo contratado de um recurso que serve duas atividades sequenciais é menor do que a soma dos custos separados de duas contratações independentes.

### 13.5 Custo Operacional Total

$$\boxed{OC_{\text{total}} = C^c_{\text{pool}} + C^v_{\text{total}} = \sum_k M_k c_m^{(k)} + \sum_k \sum_i a_{ki} H_{ki} c_h^{(k)}}$$

### 13.6 Custo de Catálogo Total

O catálogo é separável por atividade (cada atividade tem PU independente):

$$CC_{\text{total}} = \sum_{i \in V} PU_i \times Q_i$$

### 13.7 Razão Agregada $R$

$$R = \frac{OC_{\text{total}}}{CC_{\text{total}}}$$

$R$ **não é** a média ponderada dos $R_i$ individuais quando há compartilhamento de recursos. O pool cria uma não-linearidade: a permanência de um recurso que serve $n$ atividades é (em geral) menor do que a soma das permanências individuais.

---

## Seção 14: Economia de Pool — Quando o Compartilhamento Ajuda

### 14.1 Caso Sem Compartilhamento

Se cada atividade contrata seu próprio recurso de forma independente:

$$C^c_{\text{isolado}} = \sum_i M_i^{\text{isolado}} \times c_m$$

Onde $M_i^{\text{isolado}} = \lceil T_i / p_{\min} \rceil$ e $T_i$ é a duração da atividade $i$ sozinha.

### 14.2 Caso Com Compartilhamento (Pool)

Se um único recurso $k$ serve atividades $i_1, i_2, \ldots$ sequencialmente:

$$T_k^{\text{pool}} = t^{\text{end}}_{\text{last}} - t^{\text{start}}_{\text{first}}$$

$$M_k^{\text{pool}} = \left\lceil \frac{T_k^{\text{pool}}}{p_{\min}} \right\rceil \leq \sum_i M_i^{\text{isolado}}$$

A **economia de pool** é:

$$\Delta C^c = C^c_{\text{isolado}} - C^c_{\text{pool}} = c_m \left( \sum_i M_i^{\text{isolado}} - M_k^{\text{pool}} \right) \geq 0$$

### 14.3 Quando o Compartilhamento Não Ajuda

O compartilhamento **não reduz** o custo contratado quando:
- As atividades são paralelas (não sequenciais): $T_k^{\text{pool}} \approx \sum T_i$ quando há sobreposição
- A permanência combinada não reduz $M_k$ abaixo da soma individual

### 14.4 Efeito das Dependências (DAG)

As arestas do DAG determinam o **sequenciamento forçado**. Para uma aresta $(i, j)$:
- $j$ não pode iniciar antes de $i$ terminar
- Isto cria uma oportunidade de reusar o recurso de $i$ em $j$

**Atividades no caminho crítico** têm menos flexibilidade para reutilização. **Atividades com folga** podem ser agendadas para maximizar a economia de pool.

---

## Seção 15: Camada BDI — O Que Resta

### 15.1 Estrutura de Preço

O preço de venda do projeto é:

$$P = CC_{\text{total}} \times (1 + \text{BDI})$$

O BDI (Benefícios e Despesas Indiretas) é um multiplicador sobre o custo de catálogo que cobre:
- Lucro
- Impostos
- Despesas comerciais
- Riscos

### 15.2 Margem Financeira

$$\text{Margem} = P - OC_{\text{total}} = CC_{\text{total}}(1 + \text{BDI}) - OC_{\text{total}}$$

### 15.3 Condição de Viabilidade

O projeto é viável se e somente se:

$$P > OC_{\text{total}}$$

$$CC_{\text{total}}(1 + \text{BDI}) > OC_{\text{total}}$$

$$1 + \text{BDI} > \frac{OC_{\text{total}}}{CC_{\text{total}}} = R$$

$$\boxed{\text{BDI} > R - 1}$$

**Interpretação:** O BDI mínimo para viabilidade é exatamente $R - 1$. O "ponto de equilíbrio" de BDI é o quanto o custo operacional excede o catálogo.

### 15.4 Relação entre BDI, R, e Margem

| Condição | Interpretação |
|----------|--------------|
| $\text{BDI} = R - 1$ | Ponto de equilíbrio (margem zero) |
| $\text{BDI} > R - 1$ | Viável — BDI absorve a diferença operacional e gera lucro |
| $\text{BDI} < R - 1$ | Inviável — mesmo com BDI, custo operacional excede preço |

Para uma margem alvo $m^*$ (ex: 10%):

$$\text{BDI}_{\min} = R - 1 + \frac{m^* \cdot OC_{\text{total}}}{CC_{\text{total}}} = R - 1 + m^* \cdot R = R(1 + m^*) - 1$$

### 15.5 Estrutura Completa do Modelo

A formulação completa conecta três camadas:

```
┌─────────────────────────────────────────────────────────┐
│ CAMADA 1: CATÁLOGO                                       │
│                                                         │
│   CC = Σ_i PU_i × Q_i                                  │
│   (assume ε=1, produtividade nominal)                   │
└─────────────────────────────────────────────────────────┘
           ↕  Razão R = OC/CC  (custo real vs catálogo)
┌─────────────────────────────────────────────────────────┐
│ CAMADA 2: POOL OPERACIONAL                              │
│                                                         │
│   OC = C^c_pool + C^v_total                            │
│                                                         │
│   C^c_pool = Σ_k M_k × c_m^(k)   ← permanência pool   │
│   C^v_total = Σ_k Σ_i H_ki × c_h^(k)  ← consumo real  │
│                                                         │
│   Estrutura: DAG(V, E) determina M_k via sequenciamento │
└─────────────────────────────────────────────────────────┘
           ↕  Margem = P - OC  (o que sobra para BDI)
┌─────────────────────────────────────────────────────────┐
│ CAMADA 3: BDI                                           │
│                                                         │
│   P = CC × (1 + BDI)                                   │
│   Viável ↔ BDI > R - 1                                 │
│   Alvo: BDI = R(1 + m*) - 1  para margem m*            │
└─────────────────────────────────────────────────────────┘
```

---

## Seção 16: Questões Abertas com Múltiplas Atividades

### 16.1 Problema de Alocação

Dado um DAG $(V, E)$ e um conjunto de recursos $K$, como atribuir $a_{ki}$ para minimizar $OC_{\text{total}}$?

Este é um **problema de otimização combinatória** (RCPSP — Resource-Constrained Project Scheduling Problem).

Minimizar: $OC_{\text{total}} = C^c_{\text{pool}} + C^v_{\text{total}}$  
Sujeito a: restrições de precedência $(i,j) \in E$, capacidade de recursos, janelas de tempo

### 16.2 Separação Contratado vs Consumível com Pool

Com o pool, como alocar $C^c_{\text{pool}}$ por atividade para calcular $R_i$ individual?

Uma atribuição natural é proporcional às horas consumidas:

$$C^c_i = C^c_{\text{pool}} \times \frac{H_{\text{real},i}}{H_{\text{real,total}}}$$

Mas existem outras (Shapley value, por precedência etc.). A escolha afeta a contabilidade por atividade mas não o $R$ agregado.

### 16.3 Impacto das Dependências em R

Para atividades sem dependência (DAG desconexo): $R$ pode ser calculado por componente independentemente.

Para atividades com dependência: $R$ do projeto inteiro pode ser menor que a média ponderada dos $R_i$ (economia de pool via sequenciamento).

**Questão:** Existe uma decomposição de $R$ que atribua a cada aresta $(i,j)$ uma "contribuição de economia"?

---

## Seção 17: Composição do Pool de Recursos Contratuais — Perpetuação

### 17.1 Pré-condição: Distribuição Temporal Conhecida

Após o algoritmo de scheduling (RCPSP), cada atividade $i$ tem:

$$[s_i, e_i] \subset [T_{\min}, T_{\max}]$$

onde $s_i$ e $e_i$ são índices de semana e a demanda instantânea por recurso tipo $k$ é:

$$d_k(t) = \sum_{i : t \in [s_i, e_i]} a_{ki} \cdot r_{ki}$$

O **tamanho do pool** é determinado pelo pico de demanda concorrente:

$$qt_k = \max_t \; d_k(t)$$

Isto é fixo — dado o schedule, o número de instâncias físicas é determinado.

### 17.2 Problema de Perpetuação

**Definição.** Uma instância do recurso $k$ pode ser perpetuada de $i$ para $j$ (com $e_i \leq s_j$) se o custo de manter a instância em standby durante o gap é menor que desobilizar e mobilizar novamente:

$$\text{gap}_{ij} = s_j - e_i$$

**Critério de perpetuação (baseado em custo, ADR-073):**

$$\underbrace{c_{\text{standby}} \times \text{gap}_{ij}}_{\text{custo de manter}} < \underbrace{c_{\text{mob}} + c_{\text{demob}}}_{\text{custo de rebater}}$$

$$\Leftrightarrow \quad \text{gap}_{ij} < \frac{c_{\text{mob}} + c_{\text{demob}}}{c_{\text{standby}}} \equiv \delta_k^*$$

O limiar $\delta_k^*$ é o **gap de indiferença econômica** — o número de semanas de standby que iguala o custo de re-mobilização.

**Critério de perpetuação alternativo (baseado em tempo, fallback):**

$$\text{gap}_{ij} \leq \delta_{\max}$$

Onde $\delta_{\max}$ é parâmetro de projeto (típico: 2 semanas).

**Cap absoluto (ADR-079):**

$$\text{gap}_{ij} > G_r^{\text{viável}} \Rightarrow \text{não perpetuar, independente de custo}$$

### 17.3 Estrutura de Cadeia

Uma **cadeia de perpetuação** $C_p$ é uma sequência de atividades:

$$C_p = (i_1 \to i_2 \to \ldots \to i_{n_p})$$

onde cada par consecutivo $(i_k, i_{k+1})$ satisfaz o critério de perpetuação.

**Uma cadeia = um contrato**:
- 1 mobilização no início ($c_{\text{mob}}$)
- 1 desmobilização no fim ($c_{\text{demob}}$)
- Standby durante os gaps internos: $c_{\text{standby}} \times \text{gap}_{i_k, i_{k+1}}$

**Custo total da cadeia $C_p$:**

$$\text{Custo}(C_p) = c_{\text{mob}} + c_{\text{demob}} + c_{\text{standby}} \sum_{k=1}^{n_p - 1} \text{gap}_{i_k, i_{k+1}} + c_{\text{sem}} \sum_{k=1}^{n_p} (e_{i_k} - s_{i_k})$$

### 17.4 Custo Contratual Total do Pool

O pool $K_r$ de recurso tipo $r$ tem $qt_r$ instâncias, cada uma formando uma cadeia. As cadeias $\{C_1, C_2, \ldots, C_{qt_r}\}$ particionam as atividades que usam o recurso:

$$C_{\text{pool}}^c = \sum_{p=1}^{qt_r} \text{Custo}(C_p)$$

**Relação com a janela global:**

$$C_{\text{pool}}^c = qt_r \times c_{\text{sem}} \times (T_{\max} - T_{\min}) + \underbrace{\sum_p (c_{\text{mob}} + c_{\text{demob}}) + \sum_p \sum_k c_{\text{standby}} \cdot \text{gap}_{i_k, i_{k+1}}}_{\text{overhead de perpetuação}}$$

Note que se apenas 1 cadeia cobre todos os $qt_r$ slots (perpetuação total), os overheads são $1 \times (c_{\text{mob}} + c_{\text{demob}}) + c_{\text{standby}} \times \text{gaps internos}$.

Se as atividades forem incompatíveis para perpetuação, teremos $qt_r$ cadeias independentes com $qt_r$ pares mob/demob — máximo custo overhead.

### 17.5 Partição por Atividade (ADR-084)

Dado o custo do pool $C_{\text{pool}}^c$, como atribuí-lo por atividade?

O código usa **diagrama de Euler** sobre os intervalos $[s_i, e_i]$ dentro de $[T_{\min}, T_{\max}]$:

| Região | Cardinalidade | Atribuição |
|--------|--------------|------------|
| $\bigcap_i [s_i,e_i]$ apenas para $i = i_0$ | exclusiva | 100% para $i_0$ |
| $[s_{i_0},e_{i_0}] \cap [s_{j_0},e_{j_0}]$ com $n$ ativas | sobreposição | $1/n$ para cada (Shapley simétrico) |
| $[T_{\min},T_{\max}] \setminus \bigcup_i [s_i,e_i]$ | gap | imputado ao **sucessor crítico** |

**Invariante:** $\sum_i \phi_i = C_{\text{pool}}^c$ (partição exata sem resíduo).

---

## Seção 18: Pool de Recursos Consumíveis — Estoque e Fluxo

### 18.1 Natureza Distinta

Recursos consumíveis (diesel, materiais) têm natureza **oposta** aos contratuais:

| Dimensão | Contratual | Consumível |
|----------|-----------|-----------|
| Unidade de cobrança | tempo (mês/semana) | uso (litro, hora) |
| Custo durante standby | sim ($c_{\text{standby}}$) | não (não há consumo) |
| Perpetuação | aplicável | sem sentido |
| Dependência de $\varepsilon$ | não (fixo no tempo) | sim (só gasto quando produz) |

### 18.2 Modelo de Estoque

O pool consumível é formalmente um **sistema de estoque** com:

- **Fluxo de entrada** (reabastecimento): discreto, em datas de entrega
- **Fluxo de saída** (consumo): contínuo, proporcional à produção real

**Taxa de consumo instantânea** no instante $t$:

$$f^v(t) = \sum_{i : t \in [s_i, e_i]} \varepsilon_i(t) \cdot r_i^v$$

Onde $r_i^v$ é a taxa de consumo nominal por hora de atividade $i$ e $\varepsilon_i(t)$ é a eficiência realizada no instante $t$.

**Custo total do pool consumível** no período $[T_{\min}, T_{\max}]$:

$$C_{\text{pool}}^v = \int_{T_{\min}}^{T_{\max}} f^v(t) \cdot c^v \, dt = c^v \sum_{i} H_{\text{real},i}$$

Onde $H_{\text{real},i} = Q_i / (\varepsilon_i \cdot \rho_i)$ são as horas reais da atividade $i$.

### 18.3 Separabilidade por Atividade

Ao contrário do pool contratual, o custo consumível é **separável por atividade** sem ambiguidade:

$$C_i^v = c^v \cdot H_{\text{real},i} = \frac{c^v \cdot Q_i}{\varepsilon_i \cdot \rho_i}$$

Não há problema de atribuição (gap, sobreposição, standby): cada litro consumido pertence à atividade que o usou.

### 18.4 Independência de Perpetuação

A decisão de perpetuação (Seção 17) **não afeta** $C_{\text{pool}}^v$:

$$C_{\text{pool}}^v = c^v \sum_i H_{\text{real},i} \quad \text{independente do número de cadeias}$$

Isto é esperado: não há diesel "em standby" — o recurso simplesmente não é consumido quando a equipe não está produzindo.

---

## Seção 19: Síntese — Dois Pools, Uma Janela, Uma Camada de BDI

### 19.1 Estrutura Final

Dado um DAG $(V, E)$ com schedule $\{(s_i, e_i)\}_{i \in V}$ e pool de recursos $K$:

$$\boxed{OC_{\text{total}} = C_{\text{pool}}^c + C_{\text{pool}}^v}$$

$$C_{\text{pool}}^c = \underbrace{qt \cdot c_{\text{sem}} \cdot (T_{\max} - T_{\min})}_{\text{envelope}} + \underbrace{\sum_p (c_{\text{mob}} + c_{\text{demob}}) + \sum c_{\text{standby}} \cdot \text{gap}}_{\text{perpetuação}}$$

$$C_{\text{pool}}^v = c^v \sum_{i \in V} \frac{Q_i}{\varepsilon_i \rho_i}$$

O custo de catálogo não envolve pool:

$$CC_{\text{total}} = \sum_{i \in V} PU_i \cdot Q_i = \sum_{i \in V} \frac{c_{\text{sem}} + c_h^v}{\rho_i} \cdot Q_i$$

E a camada BDI fecha o modelo:

$$P = CC_{\text{total}} \cdot (1 + \text{BDI})$$

$$\text{Viável} \iff P > OC_{\text{total}} \iff \text{BDI} > R - 1 \quad \text{onde } R = \frac{OC_{\text{total}}}{CC_{\text{total}}}$$

### 19.2 Fontes de Desvio R > 1

$R > 1$ (custo operacional excede catálogo) tem **três origens estruturais**:

| Fonte | Componente | Reduzido por |
|-------|-----------|-------------|
| **Envelope** | $qt \cdot c_{\text{sem}} \cdot (T_{\max} - T_{\min})$ vs. horas produtivas reais | Aumentar $\varepsilon_i$, compactar schedule |
| **Overhead de perpetuação** | mob/demob por cadeia, standby | Perpetuar cadeias, reduzir $c_{\text{mob}}$ |
| **Eficiência consumível** | $H_{\text{real},i} = H_{\text{nom},i}/\varepsilon_i$ | Aumentar $\varepsilon_i$ |

### 19.3 Relação entre Schedule e Custo Contratual

O schedule (RCPSP) determina $\{(s_i, e_i)\}$ e portanto:

- $T_{\min} = \min_i s_i$, $T_{\max} = \max_i e_i$ — janela total
- $qt_k = \max_t d_k(t)$ — tamanho do pool
- $\text{gap}_{ij}$ para todos os pares perpetuáveis — custo de perpetuação

**A compressão do schedule reduz $(T_{\max} - T_{\min})$ e portanto $C_{\text{pool}}^c$**, mas pode aumentar $qt_k$ (mais recursos paralelos) e comprometer perpetuação (atividades que antes eram sequenciais tornam-se paralelas).

Existe um **tradeoff** entre:
- Schedule longo: baixo $qt_k$, boa perpetuação, mas alto $(T_{\max} - T_{\min})$
- Schedule curto: alto $qt_k$, menos perpetuação, mas baixo $(T_{\max} - T_{\min})$

Este é o problema de compressão de cronograma com custo mínimo de pool.

---

## Seção 20: BDI — Estrutura Multiplicativa (TCU Acórdão 2622/2013)

### 20.1 Definição de Componentes por Categoria

Para cada categoria de custo $c \in \{\text{MO, MAT, EQ, IND, DIESEL}\}$, o BDI é definido por um vetor de componentes:

$$\vec{b}^{(c)} = (AC^{(c)},\ DF^{(c)},\ R^{(c)},\ CR^{(c)},\ L^{(c)},\ T^{(c)})$$

onde:
- $AC$ = Administração Central
- $DF$ = Despesas Financeiras
- $R$ = Garantia / Risco / Seguro
- $CR$ = Contingência de Risco
- $L$ = Lucro (margem)
- $T = T_{\text{COFINS}} + T_{\text{ISS}} + T_{\text{PIS}} + T_{\text{CSSL}} + T_{\text{IR}}$ = tributos totais sobre o preço de venda

### 20.2 Fórmula TCU Multiplicativa

$$\boxed{\text{BDI}^{(c)} = \frac{(1+AC^{(c)})(1+DF^{(c)})(1+R^{(c)})(1+CR^{(c)})(1+L^{(c)})}{1 - T^{(c)}} - 1}$$

**Nota:** A fórmula TCU usa produto dos fatores de overhead (não soma), o que garante que cada componente opera sobre o preço de venda acumulado. A forma aditiva $(1+AC+DF+R+L)$ subestima o BDI em $\approx 0,9\,\text{pp}$ para os valores típicos de terraplenagem.

### 20.3 Valores DEFAULT (calibrados contra planilha AGIS / Ferrovia Nova Transnordestina)

| Categoria | $AC$ | $DF$ | $R$ | $L$ | $T_{\text{ISS}}$ | $T_{\text{CSSL}}$ | $T_{\text{IR}}$ | **BDI** |
|-----------|------|------|-----|-----|---------|--------|------|---------|
| MÃO DE OBRA | 5% | 1,5% | 1% | 9% | 5% | 1,99% | 2,74% | **≈ 29,97%** |
| MATERIAL | 0% | 0% | 0% | 4% | 0% | 0% | 0% | **4,00%** |
| SERVIÇOS | 5% | 1,5% | 1% | 9% | 5% | 1,99% | 2,74% | **≈ 29,97%** |
| INDIRETO | 5% | 1% | 0% | 8% | 4,65% | 1,99% | 2,74% | **≈ 25,21%** |
| DIESEL | 0% | 0% | 0% | 4% | 0% | 0% | 0% | **4,00%** |

*COFINS e PIS: isentos para obras de infraestrutura ferroviária.*

---

## Seção 21: Partição de Custo por Categoria e Preço Bottom-Up

### 21.1 Partição do Custo Direto

O custo direto de cada atividade $i$ é decomposto nas categorias:

$$C_i^{\text{dir}} = C_i^{\text{MO}} + C_i^{\text{EQ}} + C_i^{\text{MAT}}$$

onde:
- $C_i^{\text{MO}}$ = mão de obra + encargos (salário × $(1 + \text{enc})$)
- $C_i^{\text{EQ}}$ = aluguel de equipamentos (locação + manutenção)
- $C_i^{\text{MAT}}$ = materiais consumíveis + combustível/diesel

### 21.2 Blend de Equipamentos (ADR-023 §D3)

Equipamentos têm natureza mista: locação paga como **material** (BDI = 4%), manutenção paga como **serviço** (BDI ≈ 29,97%). O BDI efetivo é uma média ponderada:

$$\boxed{BDI^{\text{EQ}} = f_{\text{loc}} \cdot BDI^{\text{MAT}} + (1 - f_{\text{loc}}) \cdot BDI^{\text{MO}}}$$

onde:

$$f_{\text{loc}} = \frac{\sum_i C_i^{\text{locacao}}}{\sum_i (C_i^{\text{locacao}} + C_i^{\text{manut}})} \in [0, 1]$$

**Casos extremos:**
- $f_{\text{loc}} = 1$ (apenas aluguel): $BDI^{\text{EQ}} = 4\%$
- $f_{\text{loc}} = 0$ (apenas manutenção própria): $BDI^{\text{EQ}} = BDI^{\text{MO}} \approx 30\%$

### 21.3 Preço de Venda Direto

$$P^{\text{dir}} = C^{\text{MO}} \cdot (1 + BDI^{\text{MO}}) + C^{\text{EQ}} \cdot (1 + BDI^{\text{EQ}}) + C^{\text{MAT}} \cdot (1 + BDI^{\text{MAT}})$$

onde $C^k = \sum_i C_i^k$ para $k \in \{\text{MO, EQ, MAT}\}$.

### 21.4 Preço de Venda Indireto

Os custos indiretos têm sub-categorias próprias:

$$P^{\text{ind}} = C_{\text{ind}}^{\text{MO}} \cdot (1 + r_{\text{MO}}) + C_{\text{ind}}^{\text{EQ}} \cdot (1 + r_{\text{EQ}}) + C_{\text{ind}}^{\text{COMB}} \cdot (1 + r_{\text{MAT}}) + (C_{\text{ind}}^{\text{verba}} + C_{\text{ind}}^{\text{mob}}) \cdot (1 + r_{\text{IND}})$$

**Fallback** (quando sub-custos não disponíveis): $P^{\text{ind}} = C^{\text{ind}} \cdot (1 + BDI^{\text{IND}})$

### 21.5 Preço Total e Resultado

$$\boxed{P_{\text{total}} = P^{\text{dir}} + P^{\text{ind}}}$$

$$\text{Resultado} = P_{\text{total}} - OC_{\text{total}} = P_{\text{total}} - (C^{\text{dir}} + C^{\text{ind}})$$

$$\text{Margem} = \frac{\text{Resultado}}{P_{\text{total}}}$$

**Implementação** (`_calc_venda_com_bdi` em `_venda_custo.py`):

```python
venda_direto_eq = (
    cat["mao_obra"] * (1 + bdi("mao_obra"))
    + cat["eq_aluguel"] * (1 + bdi("equipamentos"))
    + custo_material_total * (1 + bdi("material"))
)
```

---

## Seção 22: Invariante de Decomposição do Preço

### 22.1 Decomposição de 100% do Preço de Venda

Para cada categoria, dado $P^{(c)} = C^{(c)} \cdot (1 + BDI^{(c)})$, a fração de cada componente no preço é:

$$\frac{C^{(c)}}{P^{(c)}} = \frac{1}{1 + BDI^{(c)}} = \frac{1 - T^{(c)}}{(1+AC^{(c)})(1+DF^{(c)})(1+R^{(c)})(1+CR^{(c)})(1+L^{(c)})}$$

A decomposição do preço (ADR-056):

$$\frac{P^{(c)}}{P^{(c)}} = \underbrace{\frac{C^{(c)}}{P^{(c)}}}_{\text{custo direto}} + \underbrace{\sum_k \frac{OH_k^{(c)} \cdot C^{(c)}}{P^{(c)}}}_{\text{overhead}} + \underbrace{T^{(c)}}_{\text{tributos}} = 1$$

**Invariante:** A soma de custo direto + overhead (AC+DF+R+CR+L) + tributos = 100% do preço de venda.

### 22.2 Exemplo Numérico (MÃO DE OBRA, BDI = 29,97%)

Com $C^{\text{MO}} = R\$100{,}000$:

$$P^{\text{MO}} = 100{,}000 \times 1{,}2997 = R\$129{,}970$$

| Componente | % do Preço | R\$ |
|------------|-----------|-----|
| Custo direto | 76,95% | 99.960 |
| Overhead AC (5%) | 3,85% | 5.000 |
| Overhead DF (1,5%) | 1,15% | 1.500 |
| Overhead R (1%) | 0,77% | 1.000 |
| Margem L (9%) | 6,92% | 9.000 |
| Tributo ISS | 5,00% | 6.500 |
| Tributo CSSL | 1,99% | 2.590 |
| Tributo IR | 2,74% | 3.560 |
| **TOTAL** | **≈ 99,37%** ± arred. | **≈ R\$129.110** |

---

## Seção 23: Cadeia de Resolução do BDI

### 23.1 Árvore de Precedência

O BDI aplicado em produção segue uma cadeia de precedência decrescente:

```
Prioridade 1 — inputs.tax_scenario (ADR-055)
│  TaxSimulationScenario (CBS/IBS pós-reforma fiscal)
│  → Calcula BDI por alíquota de reforma CBS/IBS
│
Prioridade 2 — inputs.bdi_aplicado (override manual)
│  {mao_obra: 0.30, material: 0.04, ...}
│
Prioridade 3 — inputs.tabela_bdi (TabelaBdi serializada)
│  ├─ + inputs.perfil_bdi (PerfilBdiProjeto)  ← ajustes sobre a tabela
│  └─ + inputs.aliquotas_bdi_jurisdicao (ADR-038)  ← ISS/PIS/COFINS local
│
Fallback — DEFAULT_BDI_TABELA
   (calibrada contra AGIS/Ferrovia Nova Transnordestina, BDI_MO ≈ 29,97%)
```

### 23.2 Formalização da Resolução

Seja $\mathcal{B}$ o conjunto de fontes de BDI, ordenadas por prioridade:

$$\mathcal{B} = \{B_{\text{tax}},\, B_{\text{manual}},\, B_{\text{tabela}},\, B_{\text{default}}\}$$

O BDI efetivo é:

$$BDI^{(c)}_{\text{efetivo}} = B_k^{(c)} \quad \text{onde } k = \min\{j : B_j \text{ está presente}\}$$

**Implementação** (`_resolve_bdi_full` em `_bdi_resolucao.py`):

```python
result = _rbf_try_tax_scenario(inputs, validacoes, frac_locacao)   # P1
if result: return result
result = _rbf_try_manual_bdi(inputs, validacoes)                    # P2
if result: return result
tabela, ... = _rbf_resolve_tabela_perfil(inputs, validacoes)        # P3 + fallback
```

---

## Seção 24: Conexão BDI com o Modelo de Custo Operacional

### 24.1 Relação BDI Agregado vs Razão R

O BDI **não é homogêneo** — cada categoria de custo tem sua própria taxa. O "BDI agregado efetivo" $\overline{BDI}$ é implicitamente definido por:

$$P_{\text{total}} = C_{\text{cat}} \cdot (1 + \overline{BDI}) \quad \text{onde} \quad \overline{BDI} = \frac{P_{\text{total}}}{C_{\text{cat}}} - 1$$

e $C_{\text{cat}} = CC_{\text{total}}$ (custo de catálogo PU×Q).

### 24.2 Condição de Viabilidade

Da Seção 15:

$$\text{Viável} \iff P_{\text{total}} > OC_{\text{total}} \iff \overline{BDI} > R - 1$$

Com BDI heterogêneo, a condição se expande em termos de cada categoria:

$$\text{Margem} = \frac{P_{\text{total}} - OC_{\text{total}}}{P_{\text{total}}} = 1 - \frac{OC_{\text{total}}}{P_{\text{total}}}$$

### 24.3 Fluxo Completo: Schedule → Pool → BDI → Resultado

```
[Seções 1-12]              [Seções 13-19]             [Seções 20-24]
Schedule (DAG)    →    Pool (C_pool^c + C_pool^v)  →   BDI heterogêneo
                                                          ↓
H_i (horas reais)          M_k (permanência pool)    P = Σ_c C^(c)(1+BDI^(c))
ε_i (eficiência)    →      C_pool = qt×c×T_pool   →   OC = C_dir + C_ind
τ_i = 1/ε_i                Φ_i = φ_i (Euler)          Margem = (P-OC)/P
R_i = OC_i/CC_i            Perpetuação (δ_k)           Viável ↔ BDI > R-1
```

### 24.4 Impacto da Perpetuação no BDI Mínimo

A perpetuação reduz $OC_{\text{total}}$ ao minimizar eventos de mob/demob. Isso reduz $R = OC/CC$ e portanto o **BDI mínimo de viabilidade**:

$$\Delta BDI_{\min} = \Delta R = \frac{\Delta OC_{\text{total}}}{CC_{\text{total}}} = \frac{(N_{\text{autônomo}} - N_{\text{pool}}) \cdot (c_{\text{mob}} + c_{\text{demob}})}{CC_{\text{total}}}$$

onde $N_{\text{autônomo}}$ = total de eventos de mob/demob sem perpetuação, $N_{\text{pool}}$ = número de cadeias.

**Interpretação:** Cada evento de mob/demob evitado pela perpetuação reduz o BDI mínimo exigido em $\Delta BDI_{\min}$ — esse é o valor financeiro quantificável da perpetuação de recursos.

---

## Seção 25: Correção Crítica — BDI sobre Envelope Esperado, NÃO Custo Real

### 25.1 O Erro Conceitual

A forma **errada** (mascarando ineficiência):
$$P_{\text{errado}} = OC_{\text{real}} \times (1 + BDI)$$

**Problema:** Se $OC_{\text{real}} > CC_{\text{total}}$ (ineficiências planejadas), o preço sobe proporcionalmente e cria uma margem artificial positiva mesmo quando há prejuízo no negócio.

A forma **correta** (transparência operacional):
$$\boxed{P_{\text{mercado}} = CC_{\text{total}} \times R_i \times (1 + BDI)}$$

onde:
- $CC_{\text{total}}$ = envelope de escopo (catálogo PU×Q, sem ineficiências)
- $R_i$ = razão custo_esperado / custo_catalogo = razão de ineficiências **previstas** (prolongamento de cronograma, etc.)
- $BDI$ = cobre ineficiências **imprevistas** acima de $R_i$, mais tributos e lucro

### 25.2 Decomposição da Margem

$$\text{Margem}_{\text{real}} = \frac{P_{\text{mercado}} - OC_{\text{real}}}{P_{\text{mercado}}} = \frac{CC_{\text{total}} \times R_i \times (1 + BDI) - OC_{\text{real}}}{CC_{\text{total}} \times R_i \times (1 + BDI)}$$

Podem ocorrer três cenários:

| Cenário | Condição | Interpretação |
|---------|----------|----------------|
| **Tudo ok** | $OC_{\text{real}} = CC_{\text{total}} \times R_i$ | Execução conforme previsto; margem ≈ BDI / (1+BDI) |
| **Pior que esperado** | $OC_{\text{real}} > CC_{\text{total}} \times R_i$ | Ineficiências **imprevistas**; margem cai (ou negativa) |
| **Melhor que esperado** | $OC_{\text{real}} < CC_{\text{total}} \times R_i$ | Ganhos de produtividade; margem aumenta |

### 25.3 Relação com BDI Mínimo de Viabilidade

Da Seção 15 e 24, o BDI mínimo para não ter prejuízo é:

$$BDI_{\min} = R_{\text{global}} - 1 \quad \text{onde} \quad R_{\text{global}} = \frac{OC_{\text{total}}}{CC_{\text{total}}}$$

**Mas isso assume que $R_{\text{global}}$ é APENAS as ineficiências previstas.** Se a execução gerou ineficiências imprevistas, então:

$$R_{\text{global}} = \underbrace{R_i}_{\text{prevista}} + \underbrace{\Delta R}_{\text{imprevista}} = R_i + \frac{\Delta OC}{CC_{\text{total}}}$$

e o BDI necessário é:

$$BDI_{\text{necessário}} = R_i + \frac{\Delta OC}{CC_{\text{total}}} - 1$$

Se $\Delta OC > 0$ (ineficiências imprevistas) e BDI foi calibrado com base em $R_i$ apenas, então $BDI_{\text{necessário}} > BDI$ e há **prejuízo**.

### 25.4 Implementação Corrigida

O código deve:

1. **Calcular $CC_{\text{total}}$** do planejamento (sem ineficiências, catálogo puro)
2. **Calcular $R_i$** = OC_esperado / CC_total
   - OC_esperado = custo das equipes conforme cronograma **planejado** + indiretos esperados
3. **Calcular P_mercado** = CC_total × R_i × (1 + BDI_categorico)
4. **Calcular margem** = (P_mercado - OC_real) / P_mercado
   - Onde OC_real = custo pool realizado + indiretos realizados

**Transição conceitual:**
- Antes: `venda_catalogo_plus` = CC_total × (1+BDI)  ← IGNORA ineficiências previstas
- Depois: `venda_esperada` = CC_total × R_i × (1+BDI)  ← INCORPORA ineficiências previstas

---

## Seção 26: BDI Instancial — Distributividade e Map-Reduce

### 26.1 Custo de Equipe por Recurso Instancial

Cada equipe $i$ é composta por um conjunto de recursos $\mathcal{R}_i$. Para cada $r \in \mathcal{R}_i$ com categoria $r.\text{cat} \in \{\text{EQ, MO, MAT}\}$ e quantidade $n_r$:

$$c_r = \begin{cases}
c_h^{(r)} & \text{se } r.\text{cat} \in \{\text{EQ, MO, MAT}\} \\[6pt]
\text{consumo}_r \cdot P_{r.\text{tipo}} & \text{se } r.\text{cat} = \text{COMB}
\end{cases}$$

onde $\text{consumo}_r$ [L/h] é o consumo específico do equipamento e $P_{r.\text{tipo}}$ [R\$/L] é o preço do combustível do tipo do recurso.

Os agregados por categoria da equipe $i$ são:

$$\gamma_i^{k} = \sum_{r \in \mathcal{R}_i,\; r.\text{cat}=k} c_r \cdot n_r \qquad \forall k \in \{\text{EQ, MO, MAT, COMB}\}$$

### 26.2 Partição Canônica: Contrato vs Consumível

$$\gamma_i^{\text{cat}} = \underbrace{\gamma_i^{\text{MAT}} + \gamma_i^{\text{COMB}}}_{\gamma_i^c \;\text{(contrato)}} + \underbrace{\gamma_i^{\text{EQ}} + \gamma_i^{\text{MO}}}_{\gamma_i^v \;\text{(consumível)}}$$

**Via Operacional** (eficiência real $\varepsilon_i \in [0,1]$ por clima/praticabilidade):
$$\boxed{\gamma_i^{\text{op}} = \gamma_i^c + \varepsilon_i \cdot \gamma_i^v}$$

| Componente | Tipo | Escala com $\varepsilon_i$? | BDI típico |
|-----------|------|---------------------------|------------|
| MAT | Contrato (fornecimento) | Não | $\beta_{\text{MAT}} = 4\%$ |
| COMB | Contrato (fornecimento de combustível) | Não | $\beta_{\text{MAT}} = 4\%$ |
| EQ | Consumível (recurso operacional) | Sim | $\beta_{\text{EQ}} \approx 30\%$ |
| MO | Consumível (recurso operacional) | Sim | $\beta_{\text{MO}} \approx 30\%$ |

**Interpretação:** MAT e COMB têm preços fixados por contratos de fornecimento — a quantidade é prescrita pelo projeto, o BDI cobre apenas flutuações de mercado (4%). EQ e MO são os recursos operacionais consumidos pelo processo construtivo — escalam com $\varepsilon_i$ e carregam BDI alto ($\approx 30\%$) para cobrir risco de mão de obra e locação.

### 26.3 BDI Instancial — Aplicação no Recurso

O preço de venda de cada recurso $r$ com BDI $\beta_r = \beta_{r.\text{cat}}$:

$$p_r = c_r \cdot n_r \cdot (1 + \beta_{r.\text{cat}})$$

O preço de venda da equipe $i$ — **propriedade distributiva** da multiplicação sobre a adição:

$$P_i = \sum_{r \in \mathcal{R}_i} c_r \cdot n_r \cdot (1 + \beta_{r.\text{cat}})$$

**Reagrupando por categoria** — **propriedade associativa** da adição:

$$P_i = \underbrace{\left(\sum_{r:\,r.\text{cat}=\text{EQ}} c_r n_r\right)}_{\gamma_i^{\text{EQ}}} (1+\beta_{\text{EQ}}) \;+\; \underbrace{\left(\sum_{r:\,r.\text{cat}=\text{MO}} c_r n_r\right)}_{\gamma_i^{\text{MO}}} (1+\beta_{\text{MO}}) \;+\; \ldots$$

$$\boxed{P_i = \gamma_i^{\text{EQ}}(1+\beta_{\text{EQ}}) + \gamma_i^{\text{MO}}(1+\beta_{\text{MO}}) + \gamma_i^{\text{COMB}}(1+\beta_{\text{COMB}}) + \gamma_i^{\text{MAT}}(1+\beta_{\text{MAT}})}$$

### 26.4 Map-Reduce ao Nível do Projeto

O preço total do projeto é a composição de dois níveis de redução:

**Nível 1 — Map sobre recursos (por equipe):**
$$P_i \leftarrow \text{reduce}\left(\lambda(p, r) \rightarrow p + c_r \cdot n_r \cdot (1 + \beta_{r.\text{cat}}),\; \mathcal{R}_i,\; 0 \right)$$

**Nível 2 — Reduce sobre equipes (por projeto):**
$$P_{\text{total}} = \sum_{i \in V} P_i + P^{\text{ind}}$$

A equivalência com o cálculo por categoria é garantida pelas propriedades algébricas:

$$P_{\text{total}} = \sum_k \underbrace{\left(\sum_{i \in V} \gamma_i^k\right)}_{\Gamma^k} (1 + \beta_k) + P^{\text{ind}}$$

onde $\Gamma^k = \sum_i \gamma_i^k$ é o custo total do projeto na categoria $k$.

### 26.5 Combustível — Estrutura Interna da Categoria COMB

A categoria COMB não possui um $c_h^{(r)}$ diretamente — o custo por hora é derivado de dois parâmetros físicos independentes:

$$\gamma_i^{\text{COMB}} = \sum_{\substack{r \in \mathcal{R}_i \\ r.\text{cat}=\text{EQ}}} \underbrace{\text{consumo}_r}_{\text{[L/h]}} \cdot \underbrace{P_{r.\text{tipo}}}_{\text{[R\$/L]}} \cdot n_r$$

O BDI de combustível é $\beta_{\text{COMB}} = \beta_{\text{MAT}} = 4\%$ (ADR-090: diesel = fornecimento de mercadoria, não serviço).

Portanto, o preço de combustível da equipe $i$:

$$P_i^{\text{COMB}} = (1 + \beta_{\text{MAT}}) \sum_{\substack{r \in \mathcal{R}_i \\ r.\text{cat}=\text{EQ}}} \text{consumo}_r \cdot P_{r.\text{tipo}} \cdot n_r$$

Esta estrutura preserva a auditabilidade: variações em $P_{r.\text{tipo}}$ (preço do diesel) propagam-se diretamente ao preço sem necessidade de recalcular o BDI.

### 26.6 Invariante de Conservação

Dado que o BDI é aplicado por distributividade a cada recurso, a soma é exata:

$$\sum_{r \in \bigcup_i \mathcal{R}_i} c_r \cdot n_r \cdot (1 + \beta_{r.\text{cat}}) = \sum_k \Gamma^k (1 + \beta_k) = P_{\text{total}}^{\text{dir}}$$

Esta equivalência é verificada no código em `_calc_venda_com_bdi` (via `_build_custo_categorial_bottom_up`) — o resultado independe da ordem de avaliação (recurso-primeiro ou categoria-primeiro).

---

## Seção 28: BDI Equivalente como Função de $\varepsilon_i$

### 28.1 Custo Semanal com e sem BDI

Seja $m_{ij} \in \{0,1\}$ o indicador de atividade da equipe $i$ na semana $j$, e $h \cdot d$ as horas semanais. O custo semanal **sem BDI** da equipe $i$ na semana $j$:

$$C_{ij} = (\gamma_i^c + \varepsilon_i \cdot \gamma_i^v) \cdot h \cdot d \cdot m_{ij}$$

O custo semanal **com BDI**, aplicando $\beta_c$ sobre o componente contratado e $\beta_v$ sobre o consumível:

$$\tilde{C}_{ij} = (\gamma_i^c(1+\beta_c) + \varepsilon_i \cdot \gamma_i^v(1+\beta_v)) \cdot h \cdot d \cdot m_{ij}$$

### 28.2 BDI Equivalente da Atividade

O BDI equivalente da atividade $i$ é a razão do custo total com BDI pelo sem BDI, complementar a 1:

$$\bar{\beta}_i(\varepsilon_i) = \frac{\sum_j \tilde{C}_{ij}}{\sum_j C_{ij}} - 1$$

Como $h \cdot d \cdot m_{ij}$ cancela numerador e denominador:

$$\bar{\beta}_i(\varepsilon_i) = \frac{\gamma_i^c(1+\beta_c) + \varepsilon_i \gamma_i^v(1+\beta_v)}{\gamma_i^c + \varepsilon_i \gamma_i^v} - 1 = \frac{\gamma_i^c \beta_c + \varepsilon_i \gamma_i^v \beta_v}{\gamma_i^c + \varepsilon_i \gamma_i^v}$$

Definindo a **fração consumível efetiva**:

$$\delta_i(\varepsilon_i) = \frac{\varepsilon_i \gamma_i^v}{\gamma_i^c + \varepsilon_i \gamma_i^v}$$

obtemos:

$$\boxed{\bar{\beta}_i(\varepsilon_i) = (1 - \delta_i) \cdot \beta_c + \delta_i \cdot \beta_v}$$

**Propriedade:** $\bar{\beta}_i$ é função crescente de $\varepsilon_i$ quando $\beta_v > \beta_c$ (o que é sempre verdade: $30\% \gg 4\%$). Maior utilização dos recursos operacionais (EQ+MO) aumenta o BDI equivalente da atividade.

| $\varepsilon_i$ | $\delta_i$ | $\bar{\beta}_i$ | Interpretação |
|----------------|-----------|----------------|---------------|
| $0$ | $0$ | $\beta_c = 4\%$ | Apenas materiais consumidos |
| $0{,}5$ | $\frac{0{,}5 \gamma^v}{\gamma^c + 0{,}5\gamma^v}$ | Intermediário | Subutilização de EQ+MO |
| $1$ | $\frac{\gamma^v}{\gamma^c + \gamma^v} = \delta$ | $\delta \beta_v + (1-\delta)\beta_c$ | Catalog nominal |
| $> 1$ | $> \delta$ | $> \bar{\beta}_i(1)$ | Sobre-utilização |

### 28.3 BDI Equivalente do Pool Contratual

O pool de recursos **contratuais** (EQ+MO para a janela $\mathcal{T}_{\text{pool}}$) tem custo total:

$$C_{\text{pool}}^v = \sum_{i \in V} \varepsilon_i \gamma_i^v \cdot |\mathcal{T}_i|$$

Como todos os recursos consumíveis partilham o mesmo $\beta_v$, o BDI do pool consumível é simplesmente:

$$\bar{\beta}_{\text{pool}}^v = \frac{\tilde{C}_{\text{pool}}^v}{C_{\text{pool}}^v} - 1 = (1+\beta_v) - 1 = \beta_v$$

### 28.4 BDI Equivalente do Pool de Fornecimento

O pool de **fornecimento** (MAT+COMB, fixo por unidade produzida) tem custo total:

$$C_{\text{pool}}^c = \sum_{i \in V} \gamma_i^c \cdot |\mathcal{T}_i|$$

Igualmente, como todos os contratos de fornecimento partilham $\beta_c$:

$$\bar{\beta}_{\text{pool}}^c = \beta_c$$

### 28.5 BDI Equivalente Agregado do Escopo

O BDI de escopo é a média ponderada dos dois pools:

$$\bar{\beta}_{\text{proj}} = \frac{C_{\text{pool}}^c \cdot \beta_c + C_{\text{pool}}^v \cdot \beta_v}{C_{\text{pool}}^c + C_{\text{pool}}^v} = (1 - \Delta) \cdot \beta_c + \Delta \cdot \beta_v$$

onde:

$$\Delta = \frac{C_{\text{pool}}^v}{C_{\text{pool}}^c + C_{\text{pool}}^v} = \frac{\sum_i \varepsilon_i \gamma_i^v |\mathcal{T}_i|}{\sum_i (\gamma_i^c + \varepsilon_i \gamma_i^v) |\mathcal{T}_i|}$$

**Relação com $\delta_i$:** $\Delta$ é a média temporal-ponderada das frações consumíveis efetivas:

$$\Delta = \frac{\sum_i \delta_i(\varepsilon_i) \cdot \gamma_i^{\text{op}} \cdot |\mathcal{T}_i|}{\sum_i \gamma_i^{\text{op}} \cdot |\mathcal{T}_i|}$$

### 28.6 Implicação — Decomposição do Overhead R_i com BDI

Integrando $\bar{\beta}_i$ com $R_i$ (Seção 24.3):

$$P_i = CC_i \cdot R_i \cdot (1 + \bar{\beta}_i(\varepsilon_i))$$

Como $R_i \approx 1/\varepsilon_i$ para projetos grandes, e $\bar{\beta}_i$ cresce com $\varepsilon_i$:

$$\frac{\partial P_i}{\partial \varepsilon_i} = CC_i \cdot \left(\frac{-1}{\varepsilon_i^2}(1+\bar{\beta}_i) + \frac{1}{\varepsilon_i} \frac{\partial \bar{\beta}_i}{\partial \varepsilon_i}\right)$$

O efeito líquido de aumentar $\varepsilon_i$ (melhorar eficiência operacional) sobre o preço é **ambíguo** — reduz $R_i$ mas aumenta $\bar{\beta}_i$. O ponto ótimo depende da composição $\gamma_i^c / \gamma_i^v$.

---

## Seção 27: BDI Equivalente — Média Ponderada por Categoria

### 27.1 Definição do BDI Equivalente de Equipe

Análogo à eficiência média $\bar{\varepsilon}$ (Seção 6), definimos o **BDI equivalente** $\bar{\beta}_i$ de uma equipe $i$ como a taxa única que reproduz o preço total quando aplicada ao custo total:

$$P_i = \gamma_i (1 + \bar{\beta}_i) \quad \implies \quad \boxed{\bar{\beta}_i = \frac{P_i}{\gamma_i} - 1}$$

onde:
- $P_i = \sum_k \gamma_i^k (1 + \beta_k)$ — preço total da equipe (soma por categoria)
- $\gamma_i = \sum_k \gamma_i^k$ — custo total da equipe (todas as categorias)

### 27.2 Dedução — Média Ponderada por Fração de Custo

Expandindo a definição:

$$P_i = \gamma_i^{\text{EQ}}(1+\beta_{\text{EQ}}) + \gamma_i^{\text{MO}}(1+\beta_{\text{MO}}) + \gamma_i^{\text{COMB}}(1+\beta_{\text{MAT}}) + \gamma_i^{\text{MAT}}(1+\beta_{\text{MAT}})$$

Fatorando:

$$P_i = \gamma_i + \underbrace{\gamma_i^{\text{EQ}} \beta_{\text{EQ}} + \gamma_i^{\text{MO}} \beta_{\text{MO}} + \gamma_i^{\text{COMB}} \beta_{\text{MAT}} + \gamma_i^{\text{MAT}} \beta_{\text{MAT}}}_{\text{contribuição BDI}}$$

Portanto:

$$\bar{\beta}_i = \frac{P_i - \gamma_i}{\gamma_i} = \frac{\sum_k \gamma_i^k \beta_k}{\sum_k \gamma_i^k}$$

Definindo a **fração de custo** de cada categoria:

$$f_i^k = \frac{\gamma_i^k}{\gamma_i} \qquad \text{onde} \quad \sum_k f_i^k = 1$$

Obtemos:

$$\boxed{\bar{\beta}_i = \sum_k f_i^k \cdot \beta_k}$$

**Interpretação:** O BDI equivalente é a **média ponderada** dos BDIs de cada categoria, ponderada pela fração de custo que cada categoria representa na equipe.

### 27.3 Custo Horário com BDI

Seja $h_i$ o custo horário de catálogo (sem BDI) da equipe $i$:

$$h_i = \frac{\gamma_i}{H_i} \quad \text{onde } H_i \text{ são as horas nominais de catálogo}$$

O custo horário **operacional** (com prolongamento por ineficiências):

$$h_i^{\text{op}} = \frac{\gamma_i^{\text{op}}}{H_i} = h_i \cdot \tau_i \quad \text{onde } \tau_i = \frac{1}{\bar{\varepsilon}_i}$$

O **preço de venda horário** (operacional + BDI):

$$\boxed{p_i = h_i^{\text{op}} \cdot (1 + \bar{\beta}_i) = h_i \cdot \tau_i \cdot (1 + \bar{\beta}_i)}$$

**Dual do custo horário:**
- **Sem BDI:** $h_i$ (catálogo) → $h_i^{\text{op}} = h_i \cdot \tau_i$ (operacional)
- **Com BDI:** $h_i \cdot (1 + \bar{\beta}_i)$ (catálogo + BDI) → $p_i = h_i \cdot \tau_i \cdot (1 + \bar{\beta}_i)$ (operacional + BDI)

### 27.4 BDI Equivalente de Escopo (Projeto)

Análogo, o BDI equivalente do projeto completo:

$$\bar{\beta}_{\text{proj}} = \frac{P_{\text{total}} - \Gamma_{\text{total}}}{\Gamma_{\text{total}}} = \sum_k F^k \cdot \beta_k$$

onde:
- $\Gamma_{\text{total}} = \sum_{i \in V} \gamma_i$ — custo direto total do projeto
- $F^k = \frac{\Gamma^k}{\Gamma_{\text{total}}}$ — fração de custo da categoria $k$ no projeto
- $\Gamma^k = \sum_{i \in V} \gamma_i^k$ — custo total da categoria $k$

**Propriedade:** O BDI de escopo **não é** necessariamente a média dos $\bar{\beta}_i$ das equipes — depende da distribuição de categorias no projeto:

$$\bar{\beta}_{\text{proj}} = \sum_k \left(\sum_i \frac{\gamma_i^k}{\Gamma_{\text{total}}}\right) \beta_k = \sum_i \underbrace{\left(\sum_k f_i^k \beta_k\right)}_{\bar{\beta}_i} \frac{\gamma_i}{\Gamma_{\text{total}}}$$

Logo:

$$\boxed{\bar{\beta}_{\text{proj}} = \sum_{i \in V} w_i \cdot \bar{\beta}_i \quad \text{onde} \quad w_i = \frac{\gamma_i}{\Gamma_{\text{total}}}}$$

O BDI de escopo é a **média ponderada** dos BDIs de equipe, ponderada pelo custo de cada equipe.

### 27.5 Exemplo Numérico — Projeto com 2 Equipes

| Equipe | $\gamma^{\text{MO}}$ | $\gamma^{\text{EQ}}$ | $\gamma^{\text{MAT}}$ | $\gamma_i$ | $f^{\text{MO}}$ | $f^{\text{EQ}}$ | $f^{\text{MAT}}$ | $\bar{\beta}_i$ |
|--------|-----|-----|-----|--------|---------|---------|---------|---------|
| 1 (MO-intensiva) | 70k | 20k | 10k | 100k | 0,70 | 0,20 | 0,10 | 0,70×0,30 + 0,20×0,30 + 0,10×0,04 = **0,274** |
| 2 (MAT-intensiva) | 20k | 30k | 50k | 100k | 0,20 | 0,30 | 0,50 | 0,20×0,30 + 0,30×0,30 + 0,50×0,04 = **0,170** |

BDI de escopo:

$$\bar{\beta}_{\text{proj}} = \frac{100k}{200k} \times 0{,}274 + \frac{100k}{200k} \times 0{,}170 = 0{,}222 = 22{,}2\%$$

**Ou alternativamente, pela fração global:**

$$F^{\text{MO}} = \frac{90k}{200k} = 0{,}45, \quad F^{\text{EQ}} = \frac{50k}{200k} = 0{,}25, \quad F^{\text{MAT}} = \frac{60k}{200k} = 0{,}30$$

$$\bar{\beta}_{\text{proj}} = 0{,}45 \times 0{,}30 + 0{,}25 \times 0{,}30 + 0{,}30 \times 0{,}04 = 0{,}135 + 0{,}075 + 0{,}012 = 0{,}222$$

✓ **Ambos os caminhos convergem ao mesmo valor.**

### 27.6 Relação com a Razão $R_i$

A razão $R_i = OC_i / CC_i$ (Seção 15) e o BDI equivalente $\bar{\beta}_i$ operam em **domínios distintos** mas **complementares**:

- $R_i$ modula o **volume de custo** (prolongamento operacional)
- $\bar{\beta}_i$ modula a **taxa de markup** (cobertura de risco + lucro)

O preço final é o produto dos dois:

$$P_i = CC_i \times R_i \times (1 + \bar{\beta}_i)$$

**Condição de viabilidade** (reescrita com $\bar{\beta}_i$):

$$\text{Viável} \iff P_i > OC_i \iff CC_i \times R_i \times (1 + \bar{\beta}_i) > OC_i$$

Como $OC_i = CC_i \times R_i$ (definição), a condição se simplifica para:

$$1 + \bar{\beta}_i > 1 \quad \implies \quad \bar{\beta}_i > 0$$

Mas isso é **sempre verdade** (BDI é positivo por construção). A condição real de viabilidade é que o **BDI aplicado** cubra as ineficiências **imprevistas**:

$$\bar{\beta}_i \geq \frac{\Delta OC_i}{CC_i \times R_i}$$

onde $\Delta OC_i = OC_i^{\text{real}} - OC_i^{\text{esperado}}$.

---

**Versão:** 5.2 (Pool + Consumível + BDI Equivalente como Média Ponderada)  
**Data:** 2026-08-14  
**Status:** Formalização Completa: Schedule → Pool → Perpetuação → BDI → $\bar{\beta}$ ✅
