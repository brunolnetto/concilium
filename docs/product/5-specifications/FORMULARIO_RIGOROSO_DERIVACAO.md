# Modelo Rigoroso: Produtividade, Permanência e Custo Real vs Catálogo

**Objetivo:** Derivar de primeiros princípios como custos operacionais (real) se relacionam com custos de catálogo, sem forçar elegância matemática.

**Abordagem:** Partir do modelo de caixa (cash model), derivar algebricamente cada passo, identificar inconsistências, responder questões abertas.

## Mapa de Navegação (30 seções)

| Se você procura... | Vá para |
|---|---|
| Definições base (Q, ρ, ε, custo de pool/material) | §1 |
| Cálculo de horas nominais/reais, permanência, custo operacional | §2–4 |
| Custo de catálogo (PU) e razão $R_i$ (real vs catálogo) | §5–12 |
| Múltiplas atividades, DAG, economia de pool | §13–14 |
| BDI — estrutura, perpetuação, resolução de precedência | §15, §17–19, §20, §23 |
| Partição de custo direto/indireto por categoria (bottom-up) | §21 |
| **Quantitativo e custo semanal (direto)** — $q_{ij}$, pool vs material | **§26** |
| **Custo semanal do indireto** — $m_l(j)$, drivers permanência/one\_time | **§29** |
| BDI equivalente ($\bar\beta$) como função de categoria/$\varepsilon$ | §27–28 |
| Margem — lucro vs overhead vs tributos, por categoria | §30 |
| Achados de auditoria contra código (não corrigidos) | §21.4, §25.4, §26.6, §30.5 |

---

## Glossário de Notação (normalizado em 2026-08-17)

Este documento cresceu por 30 seções ao longo de várias rodadas; alguns símbolos foram reaproveitados sem aviso para conceitos diferentes. Esta seção é a referência canônica — em caso de dúvida, o símbolo aqui vale sobre qualquer uso anterior no texto corrido.

### Renomeações aplicadas nesta normalização

| Símbolo antigo | Símbolo novo | Motivo | Onde |
|---|---|---|---|
| $\gamma^{c}$ / $\gamma^{v}$ | $\gamma^{\text{pool}}$ / $\gamma^{\text{MAT+COMB}}$ | direção de $\varepsilon$ estava invertida (auditoria v5.7) | §26.2, 28, 29 |
| $\gamma^{\text{mat}}$ (agregado, minúsculo) | $\gamma^{\text{MAT+COMB}}$ | colidia visualmente com $\gamma^{\text{MAT}}$ (categoria crua, só materiais sem combustível) | §26.2, 28, 29 |
| $\beta_{\text{mat}}$ (minúsculo) | $\beta_{\text{MAT}}$ (maiúsculo) | é literalmente a mesma taxa da categoria MATERIAL (4%), não uma taxa "de agregado" própria | §26–29 |
| $R^{(c)}$ (componente do vetor BDI) | $\text{Gr}^{(c)}$ (Garantia/Risco) | colidia com $R_i=OC_i/CC_i$ (razão custo/catálogo, §6+) | §20–22, 30 |
| $\phi_i$ (partição de custo de pool, Euler/Shapley) | $\chi_i$ | colidia com $\phi$ = fator técnico (§1.1) | §17.5 |
| $C_p$ (cadeia de perpetuação) | $\mathcal{C}_p$ | "C" já denota custo em R\$ em todo o resto do documento | §17.3–17.4 |
| $\tau_i = 1/\bar\varepsilon_i$ | $\eta_{h,i}$ | duplicava $\eta_h$ (§2.3); citação cruzada apontava para seção errada; colidia com $\tau^{(c)}$ de §30.3 | §27.3 |
| $\delta_k^*$, $\delta_{\max}$ (gap em **semanas**) | $G_k^*$, $G_{\max}$ | $\delta$ sem qualificador já denota fração $\in[0,1]$ em §28.2 (unidade diferente!) | §17.2 |
| $r_{\text{MO}}, r_{\text{EQ}}, r_{\text{MAT}}, r_{\text{IND}}$ | $\beta_{\text{MO}}, \beta_{\text{EQ}}, \beta_{\text{MAT}}, \beta_{\text{IND}}$ | §29.4–29.5 provam ser exatamente a mesma taxa; símbolo duplicado sem necessidade | §21.4 |
| $(i,j)\in E$ (aresta de DAG) | $(u,v)\in E$ | $i,j$ reservados para atividade/semana a partir de §26 ($m_{ij}$, $q_{ij}$) | §13, §16, §17 (gap$_{uv}$) |
| $\varepsilon_j$ (frente paralela) | $\varepsilon_f$ | mesmo motivo — $j$ é semana a partir de §26 | §10.1 |
| $\overline{BDI}$ | $\bar\beta_{\text{proj}}$ | mesmo conceito e fórmula de §27.4, macro LaTeX diferente | §24.1 |
| $m^*$ (margem alvo) | $\mu^*$ | alinhado com $\mu$ = margem financeira realizada (§30.6) | §15.4 |
| $h_m$ | $h_{\min}$ | mesma constante ($p_{\min}\times h_w$), nome órfão de versão anterior | §1.3 |

### Símbolos que convivem com dois papéis — mantidos, mas com nota no texto

| Símbolo | Papel 1 | Papel 2 | Risco prático |
|---|---|---|---|
| $\beta$ (bare) | Fator clima, §1.1 | Raiz de taxa de BDI, §20+ | Baixo — as duas "eras" não aparecem na mesma fórmula (nota em §1.1) |
| $k$ | Recurso físico $k\in K$, §13–19 | Categoria de custo $k\in\{\text{EQ,MO,MAT,COMB}\}$, §26–28 | Baixo — contexto/sub-superscrito sempre desambigua ($M_k$ vs. $\gamma_i^k$) |
| $c$ | Custo em R\$ ($c_m$, $c_h$, $c_r$...), §1–19 | Índice de categoria $(c)$ em superscrito, §20–30 | Baixo — índice sempre vem entre parênteses como superscrito, custo nunca |
| IND (maiúsculo) vs. ind (minúsculo) | $\beta_{\text{IND}}$ = taxa específica do bloco verba+mob | $P^{\text{ind}}$, $C^{\text{ind}}$ = categoria indireta inteira | Baixo, mas não estava documentado — regra: macro=minúsculo, sub-taxa específica=maiúsculo |
| $p_{\min}$ vs. $s_{\text{mes}}$ | Permanência mínima contratual, §3.1 | Semanas/mês para rateio do indireto, §29.3 | Mesma constante numérica (4,33); nota cruzada adicionada em §29.3 |
| $\tau^{(c)}$ (§30.3) | Fração de tributo no preço, $=T^{(c)}$ por definição | — | Não confundir com $\tau_i$ de §27.3 (já removido/renomeado) nem com $\tau_i$ de `AXIOMAS_INVARIANTES_CONFORMIDADE.md` (=$R_i$ deste documento, símbolo diferente entre os dois arquivos) |

### Convenções fixas (não mudam ao longo do documento)

- $\tilde{x}$ = "com BDI" ($\tilde C_{ij}$, $\tilde C_{lj}$). $\bar{x}$ = "média/agregado/equivalente" ($\bar\varepsilon_i$, $\bar\beta_i$, $\bar\theta,\bar\lambda,\bar\tau$). $\hat{x}$ não é usado.
- Categorias de recurso/custo (MO, EQ, MAT, COMB, IND, pool, dir, ind) sempre em `\text{}` no sub/sobrescrito: $\gamma_i^{\text{MO}}$, nunca $\gamma_i^{MO}$.
- $i$ = atividade/equipe; $j$ = semana (a partir de §26); $u,v$ = nós de uma aresta de DAG (§13–17); $f$ = frente paralela (§10.1); $l$ = categoria indireta (§29); $r$ = recurso físico individual (§13, §26).
- $(c)$ como superscrito entre parênteses = índice de categoria de BDI (§20–30): $AC^{(c)}$, $P^{(c)}$, $\text{Gr}^{(c)}$.

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

**Nota — $\beta$ tem dois papéis neste documento:** aqui (§1.1) é o fator clima, adimensional $\in[0,1]$. A partir de §20, $\beta$ vira a raiz genérica de taxa de BDI ($\beta_{\text{pool}}$, $\beta_{\text{MAT}}$, $\beta_{\text{MO}}$...) — conceito totalmente diferente (uma taxa de markup, não um multiplicador de produtividade). As duas "eras" do documento raramente aparecem na mesma fórmula, mas não confunda um pelo outro.

**Relação com a Matriz de Eficiência do código (NEP-035):** o código real decompõe eficiência como $\eta = \eta_s \cdot \eta_p \cdot \eta_w$ — $\eta_s$ = alocação ($n_j/n_{\max}$), $\eta_p$ = praticabilidade (fator clima × calendário), $\eta_w$ = gestão/utilização ($m_{ij}/M_{\max}$). O $\varepsilon=\beta\times\phi$ deste documento **aproxima-se de $\eta_p$** (praticabilidade), mas não é formalmente equivalente ($\phi$ "técnico/complexidade" não tem definição 1:1 com "calendário"), e **não cobre** $\eta_s$ nem $\eta_w$. Isso importa na prática: é $\eta_w$ — não $\varepsilon$ — que aparece multiplicando combustível em parte do código (§26.2). Sempre que "eficiência" aparecer neste documento, é $\varepsilon \approx \eta_p$ que está em jogo, nunca $\eta_s$ ou $\eta_w$.

### 1.2 Custo por Elemento

| Elemento | Símbolo | Unidade | Tipo |
|----------|---------|---------|------|
| **Custo de Pool** | $c_m$ | R$/mês | Pagamento mensal fixo — MO + EQ (aluguel **e** manutenção) |
| **Custo de Material** | $c_h$ | R$/hora nominal | Combustível/diesel — consumido em proporção ao que é produzido |

**Importante:** $c_m$ é pago por cada mês em que a equipe/equipamento está mobilizado, **independentemente de quanto se produziu naquele mês** — inclui manutenção (é serviço ligado a ter o equipamento disponível, não ao volume produzido). $c_h$ é o custo de material por hora **na produtividade nominal** $\rho$ — o total de material para produzir $Q$ é $c_h \times Q/\rho$, **não** $c_h \times H_{\text{real}}$ (ver correção em §4.1: combustível escala com o que foi produzido, não com quantas horas reais foram necessárias para produzir — confirmado em NEP-043 e formalizado em §26.2 como partição pool/material). "Desgaste" de equipamento, ao contrário de versões anteriores desta tabela, é tratado como manutenção — parte do custo de **pool** ($c_m$), não de material.

### 1.3 Fração Consumível

$$\delta = \text{Proporção de custos que são consumíveis (variáveis com uso)}$$

Se considerarmos um "custo composicional horário nominal":

$$c_{\text{comp}} = \frac{c_m}{h_{\min}} + c_h$$

Onde $h_{\min} = 4{,}33 \times 44 \approx 190$ horas/mês (aproximação grosseira; mesma constante formalizada com rigor em §5.4/§6.2 como $h_{\min}=p_{\min}\times h_w$ — unificado aqui, era "$h_m$" nesta seção).

Então:

$$\delta = \frac{c_h}{c_m/h_{\min} + c_h}$$

Mas isto depende de como se rateia o mensal. **Deixaremos isto pendente por enquanto.** (Nunca é retomado com este símbolo — §28.2 define um $\delta_i(\varepsilon_i)$ com papel análogo, mas fórmula diferente; não confundir os dois.)

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

Aqui, ao contrário do custo de material (§1.2, §4.1), usar $H_{\text{real}}$ está correto: a equipe precisa estar **fisicamente mobilizada** pelo tempo real de execução, não pelo tempo nominal — permanência é sobre calendário, não sobre produção. Esta é exatamente a definição de $N_i$ (número de semanas ativas) retomada com mais rigor em §26.2: $T_{\text{semanas}} \equiv N_i$.

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

$$OC = \text{(Custo de pool)} + \text{(Custo de material)}$$

$$\boxed{OC = M \times c_m + H_{\text{nom}} \times c_h}$$

**Primeiro termo:** Você contrata por $M$ meses (calculado a partir de $H_{\text{real}}$, §3.1 — a mobilização segue o tempo real), cada mês custa $c_m$.
**Segundo termo:** Material é consumido em proporção ao que foi **produzido** ($Q$), não a quantas horas reais foram necessárias para produzir — por isso usa-se $H_{\text{nom}} = Q/\rho$, não $H_{\text{real}}$. O total de material para o mesmo $Q$ não muda com a eficiência: $H_{\text{nom}} \times c_h$ é constante em $\varepsilon$ (confirmado em `_pe_gap_praticabilidade_abs`, NEP-043: "diesel constante em $Q$"; formalizado com rigor em §26.2, onde o mesmo resultado sai da soma de $\varepsilon_i\gamma_i^{\text{MAT+COMB}}$ ao longo das semanas).

Esta é uma correção em relação a versões anteriores desta seção, que usavam $H_{\text{real}} \times c_h$ — herdando a suposição (incorreta, contrariada por NEP-043) de que material escala com horas reais de operação em vez de com produção.

### 4.2 Exemplo Numérico

Suponha:
- $c_m = 22.000$ R$/mês (MO 5k + EQ 15k, aluguel+manutenção + Overhead 2k)
- $c_h = 100$ R$/hora nominal (diesel/combustível)
- $M = 7$ meses (de $H_{\text{real}} = 1.190$ horas, §3.1 — permanência não muda)
- $H_{\text{nom}} = 500$ horas (de $Q=10.000$ m², $\rho=20$ m²/hora, §2.1 — usado aqui, não $H_{\text{real}}$)

$$OC = 7 \times 22.000 + 500 \times 100 = 154.000 + 50.000 = 204.000 \text{ R}$$

(Valor anterior, com $H_{\text{real}}\times c_h$: R\$273.000 — a diferença de R\$69.000 é exatamente o "excesso" de material que a fórmula antiga cobrava por ineficiência, que NEP-043 mostra não acontecer na prática.)

**Escopo desta correção:** ela cobre §1–4 (definições e $OC$). As Seções 5–12 (derivação de $R_i$, síntese) usam $OC$ apenas simbolicamente — não hardcodeiam o valor 273.000 — então a álgebra ali não quebra, mas foi **escrita assumindo** a convenção antiga ($H_{\text{real}}\times c_h$ para material). O caso real MATA_DENSA_SIMPLES (§9, $R_i\approx4{,}31$) usa números de projeto observados, não recalculados aqui — se a análise original daquele projeto também assumiu diesel escalando com $H_{\text{real}}$, uma parte do $R_i$ observado pode ser esse mesmo efeito (não recomputado; ficaria como revisão futura). Seções 13 em diante (pool multi-atividade, BDI) já foram auditadas contra código em rodada anterior e usam a convenção corrigida.

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

Se você tem $n$ frentes paralelas indexadas por $f$ (não $j$ — reservado para semana a partir de §26, e não $i$ — reservado para atividade), cada uma com eficiência $\varepsilon_f$:

$$H_{\text{real, total}} = \sum_f \frac{Q_f}{\varepsilon_f \rho}$$

$$OC = M \times c_m + H_{\text{real, total}} \times c_h$$

Se todas as frentes compartilham a mesma permanência M (alocadas ao mesmo período):

$$R_i = \frac{M \times c_m + \sum_f H_f c_h}{\sum_f (PU_f Q_f)}$$

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
- $E \subseteq V \times V$ — dependências $(u, v)$ significam "$u$ deve terminar antes de $v$ iniciar" (índices $u,v$, não $i,j$ — reservamos $i,j$ para atividade/semana a partir de §26)
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

As arestas do DAG determinam o **sequenciamento forçado**. Para uma aresta $(u, v)$:
- $v$ não pode iniciar antes de $u$ terminar
- Isto cria uma oportunidade de reusar o recurso de $u$ em $v$

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

Para uma margem alvo $\mu^*$ (ex: 10% — símbolo alinhado com $\mu$, a margem financeira realizada formalizada em §30.6; era "$m^*$" nesta seção):

$$\text{BDI}_{\min} = R - 1 + \frac{\mu^* \cdot OC_{\text{total}}}{CC_{\text{total}}} = R - 1 + \mu^* \cdot R = R(1 + \mu^*) - 1$$

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
Sujeito a: restrições de precedência $(u,v) \in E$, capacidade de recursos, janelas de tempo

### 16.2 Separação Contratado vs Consumível com Pool

Com o pool, como alocar $C^c_{\text{pool}}$ por atividade para calcular $R_i$ individual?

Uma atribuição natural é proporcional às horas consumidas:

$$C^c_i = C^c_{\text{pool}} \times \frac{H_{\text{real},i}}{H_{\text{real,total}}}$$

Mas existem outras (Shapley value, por precedência etc.). A escolha afeta a contabilidade por atividade mas não o $R$ agregado.

### 16.3 Impacto das Dependências em R

Para atividades sem dependência (DAG desconexo): $R$ pode ser calculado por componente independentemente.

Para atividades com dependência: $R$ do projeto inteiro pode ser menor que a média ponderada dos $R_i$ (economia de pool via sequenciamento).

**Questão:** Existe uma decomposição de $R$ que atribua a cada aresta $(u,v)$ uma "contribuição de economia"?

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

**Definição.** Uma instância do recurso $k$ pode ser perpetuada da atividade $u$ para a atividade $v$ (com $e_u \leq s_v$) se o custo de manter a instância em standby durante o gap é menor que desobilizar e mobilizar novamente:

$$\text{gap}_{uv} = s_v - e_u$$

(Índices $u,v$ — não $i,j$ — para não colidir com $i,j$ como índice de semana usado em §26–29, $m_{ij}$/$q_{ij}$.)

**Critério de perpetuação (baseado em custo, ADR-073):**

$$\underbrace{c_{\text{standby}} \times \text{gap}_{uv}}_{\text{custo de manter}} < \underbrace{c_{\text{mob}} + c_{\text{demob}}}_{\text{custo de rebater}}$$

$$\Leftrightarrow \quad \text{gap}_{uv} < \frac{c_{\text{mob}} + c_{\text{demob}}}{c_{\text{standby}}} \equiv G_k^*$$

O limiar $G_k^*$ é o **gap de indiferença econômica** — o número de semanas de standby que iguala o custo de re-mobilização. (Renomeado de "$\delta_k^*$" — mede semanas, não a fração $\delta_i(\varepsilon_i)$ de §28.2; consistente com $G_k^{\text{viável}}$ abaixo.)

**Critério de perpetuação alternativo (baseado em tempo, fallback):**

$$\text{gap}_{uv} \leq G_{\max}$$

Onde $G_{\max}$ é parâmetro de projeto (típico: 2 semanas).

**Cap absoluto (ADR-079):**

$$\text{gap}_{uv} > G_k^{\text{viável}} \Rightarrow \text{não perpetuar, independente de custo}$$

### 17.3 Estrutura de Cadeia

Uma **cadeia de perpetuação** $\mathcal{C}_p$ (script, para não colidir com a família $C$ = custo em R\$ usada no resto do documento) é uma sequência de atividades:

$$\mathcal{C}_p = (i_1 \to i_2 \to \ldots \to i_{n_p})$$

onde cada par consecutivo $(i_k, i_{k+1})$ satisfaz o critério de perpetuação.

**Uma cadeia = um contrato**:
- 1 mobilização no início ($c_{\text{mob}}$)
- 1 desmobilização no fim ($c_{\text{demob}}$)
- Standby durante os gaps internos: $c_{\text{standby}} \times \text{gap}_{i_k, i_{k+1}}$

**Custo total da cadeia $\mathcal{C}_p$:**

$$\text{Custo}(\mathcal{C}_p) = c_{\text{mob}} + c_{\text{demob}} + c_{\text{standby}} \sum_{k=1}^{n_p - 1} \text{gap}_{i_k, i_{k+1}} + c_{\text{sem}} \sum_{k=1}^{n_p} (e_{i_k} - s_{i_k})$$

### 17.4 Custo Contratual Total do Pool

O pool $K_r$ de recurso tipo $r$ tem $qt_r$ instâncias, cada uma formando uma cadeia. As cadeias $\{\mathcal{C}_1, \mathcal{C}_2, \ldots, \mathcal{C}_{qt_r}\}$ particionam as atividades que usam o recurso:

$$C_{\text{pool}}^c = \sum_{p=1}^{qt_r} \text{Custo}(\mathcal{C}_p)$$

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

Seja $\chi_i$ a fatia de $C_{\text{pool}}^c$ atribuída à atividade $i$ pela regra acima (renomeado de "$\phi_i$" — colidia com o fator técnico $\phi$ de §1.1).

**Invariante:** $\sum_i \chi_i = C_{\text{pool}}^c$ (partição exata sem resíduo).

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
- $\text{gap}_{uv}$ para todos os pares perpetuáveis — custo de perpetuação

**A compressão do schedule reduz $(T_{\max} - T_{\min})$ e portanto $C_{\text{pool}}^c$**, mas pode aumentar $qt_k$ (mais recursos paralelos) e comprometer perpetuação (atividades que antes eram sequenciais tornam-se paralelas).

Existe um **tradeoff** entre:
- Schedule longo: baixo $qt_k$, boa perpetuação, mas alto $(T_{\max} - T_{\min})$
- Schedule curto: alto $qt_k$, menos perpetuação, mas baixo $(T_{\max} - T_{\min})$

Este é o problema de compressão de cronograma com custo mínimo de pool.

---

## Seção 20: BDI — Estrutura Multiplicativa (TCU Acórdão 2622/2013)

### 20.1 Definição de Componentes por Categoria

Para cada categoria de custo $c \in \{\text{MO, MAT, EQ, IND, DIESEL}\}$, o BDI é definido por um vetor de componentes:

$$\vec{b}^{(c)} = (AC^{(c)},\ DF^{(c)},\ \text{Gr}^{(c)},\ C\text{Gr}^{(c)},\ L^{(c)},\ T^{(c)})$$

onde:
- $AC$ = Administração Central
- $DF$ = Despesas Financeiras
- $\text{Gr}$ = Garantia / Risco / Seguro (renomeado de "$R$" — colidia com a razão $R_i=OC_i/CC_i$ de §6+)
- $CR$ = Contingência de Risco
- $L$ = Lucro (margem)
- $T = T_{\text{COFINS}} + T_{\text{ISS}} + T_{\text{PIS}} + T_{\text{CSSL}} + T_{\text{IR}}$ = tributos totais sobre o preço de venda

### 20.2 Fórmula TCU Multiplicativa

$$\boxed{\text{BDI}^{(c)} = \frac{(1+AC^{(c)})(1+DF^{(c)})(1+\text{Gr}^{(c)})(1+C\text{Gr}^{(c)})(1+L^{(c)})}{1 - T^{(c)}} - 1}$$

**Nota:** A fórmula TCU usa produto dos fatores de overhead (não soma), o que garante que cada componente opera sobre o preço de venda acumulado. A forma aditiva $(1+AC+DF+\text{Gr}+L)$ subestima o BDI em $\approx 0,9\,\text{pp}$ para os valores típicos de terraplenagem.

### 20.3 Valores DEFAULT (calibrados contra planilha AGIS / Ferrovia Nova Transnordestina)

| Categoria | $AC$ | $DF$ | $\text{Gr}$ | $L$ | $T_{\text{ISS}}$ | $T_{\text{CSSL}}$ | $T_{\text{IR}}$ | **BDI** |
|-----------|------|------|-----|-----|---------|--------|------|---------|
| MÃO DE OBRA | 5% | 1,5% | 1% | 9% | 5% | 1,99% | 2,74% | **≈ 29,97%** |
| MATERIAL | 0% | 0% | 0% | 4% | 0% | 0% | 0% | **4,00%** |
| SERVIÇOS | 5% | 1,5% | 1% | 9% | 5% | 1,99% | 2,74% | **≈ 29,97%** |
| INDIRETO | 5% | 1,5% | 1% | 5% | 5% | 1,99% | 2,74% | **≈ 25,21%** |
| DIESEL | 0% | 0% | 0% | 4% | 0% | 0% | 0% | **4,00%** |

*COFINS e PIS: isentos para obras de infraestrutura ferroviária.*

Os valores de $AC/DF/\text{Gr}/L/T_{\text{ISS}}$ da linha INDIRETO são conferidos contra `DEFAULT_BDI_TABELA.indireto` (`_components.py`): mesmos $AC/DF/\text{Gr}$ de MÃO DE OBRA, diferindo apenas no lucro $L$ (ver §29.4 e §30).

---

## Seção 21: Partição de Custo por Categoria e Preço Bottom-Up

### 21.1 Partição do Custo Direto

O custo direto de cada atividade $i$ é decomposto nas categorias:

$$C_i^{\text{dir}} = C_i^{\text{MO}} + C_i^{\text{EQ}} + C_i^{\text{MAT}}$$

onde:
- $C_i^{\text{MO}}$ = mão de obra + encargos (salário × $(1 + \text{enc})$)
- $C_i^{\text{EQ}}$ = aluguel de equipamentos (locação + manutenção)
- $C_i^{\text{MAT}}$ = materiais consumíveis + combustível/diesel

**Exceção ao bottom-up (ADR-175):** esta partição, e a de §21.4/§26–29, descrevem a composição bottom-up como universal (sempre derivada de recurso/função). Na prática, **custo indireto tem um mecanismo de produto (ADR-175) que desliga o bottom-up por categoria**: se o usuário preenche um valor manual (override) para uma categoria de indireto no `ProjetoSpec`, esse valor **substitui integralmente** a composição bottom-up daquela categoria — não é somado, não coexiste (`_resolve_categoria_comp`, `_resolucao.py:29-45`, retorna o override diretamente; a decisão explícita do ADR rejeitou somar override + bottom-up). Esta seção, e as Seções 13/26–29 que formalizam a composição por recurso, não mencionavam essa exceção — o formalismo bottom-up vale apenas quando não há override manual ativo para a categoria.

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

Os custos indiretos têm sub-categorias próprias, com as **mesmas** taxas de BDI do direto (§29.4/29.5 provam $r_k \equiv \beta_k$ — unificado aqui, sem símbolo $r$ duplicado):

$$P^{\text{ind}} = C_{\text{ind}}^{\text{MO}} \cdot (1 + \beta_{\text{MO}}) + C_{\text{ind}}^{\text{EQ}} \cdot (1 + \beta_{\text{EQ}}) + C_{\text{ind}}^{\text{COMB}} \cdot (1 + \beta_{\text{MAT}}) + (C_{\text{ind}}^{\text{verba}} + C_{\text{ind}}^{\text{mob}}) \cdot (1 + \beta_{\text{IND}})$$

**Fallback** (quando sub-custos não disponíveis): $P^{\text{ind}} = C^{\text{ind}} \cdot (1 + BDI^{\text{IND}})$

**Condição real do fallback e risco de silêncio:** o gatilho não é uma flag explícita de "sub-custos indisponíveis" — é a soma dos cinco campos de sub-custo (`custo_mao_obra+custo_equipamentos+custo_combustivel+custo_verba+custo_mobilizacao`) dar **exatamente zero** (`_venda_custo.py:69-87`). Como `Indireto` (`_financeiro_resultado.py:83-106`) tem esses campos com `default=0.0` (não `None`), qualquer código que construa um `Indireto` sem popular os sub-custos (import legado, teste, novo caminho) cai neste fallback **sem log, sem `ValidacaoItem`, sem alerta** — ao contrário do fallback de taxa de BDI ausente na mesma função, que loga. Há ainda um **segundo caminho, independente e sempre-plano**: `_apply_bdi_to_indiretos` (`_resolucao.py:231-284`) aplica `BDI_INDIRETO` (≈25,21%) a **toda** categoria, sempre, e alimenta o campo `indiretos_com_bdi` consumido pelo **relatório Excel** (`excel/sheets/resultado/_indiretos.py:28`) — enquanto o preço de venda real usa `_calc_venda_com_bdi` (granular por sub-categoria, §21.4). Os dois nunca são comparados (`_resultado.py:65` só chama `_calc_venda_com_bdi`). Sempre que a composição real de uma categoria divergir da média que produz 25,21% (a regra, não exceção — o exemplo de §29.6 já mostra BDI equivalente real de 26,4%, não 25,21%), **o Excel entregue mostra um BDI/preço de indireto diferente do que efetivamente compõe o preço de venda**. Não corrigido nesta formalização — registrado como achado.

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

$$\frac{C^{(c)}}{P^{(c)}} = \frac{1}{1 + BDI^{(c)}} = \frac{1 - T^{(c)}}{(1+AC^{(c)})(1+DF^{(c)})(1+\text{Gr}^{(c)})(1+C\text{Gr}^{(c)})(1+L^{(c)})}$$

A decomposição do preço (ADR-056):

$$\frac{P^{(c)}}{P^{(c)}} = \underbrace{\frac{C^{(c)}}{P^{(c)}}}_{\text{custo direto}} + \underbrace{\sum_k \frac{OH_k^{(c)} \cdot C^{(c)}}{P^{(c)}}}_{\text{overhead}} + \underbrace{T^{(c)}}_{\text{tributos}} = 1$$

**Invariante:** A soma de custo direto + overhead (AC+DF+Gr+CR+L) + tributos = 100% do preço de venda.

### 22.2 Exemplo Numérico (MÃO DE OBRA, BDI = 29,97%)

Com $C^{\text{MO}} = R\$100{,}000$:

$$P^{\text{MO}} = 100{,}000 \times 1{,}2997 = R\$129{,}970$$

| Componente | % do Preço | R\$ |
|------------|-----------|-----|
| Custo direto | 76,95% | 99.960 |
| Overhead AC (5%) | 3,85% | 5.000 |
| Overhead DF (1,5%) | 1,15% | 1.500 |
| Overhead Gr (1%) | 0,77% | 1.000 |
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

O BDI **não é homogêneo** — cada categoria de custo tem sua própria taxa. O "BDI agregado efetivo" $\bar\beta_{\text{proj}}$ (mesmo símbolo formalizado depois em §27.4 — unificado aqui, era "$\overline{BDI}$" nesta seção) é implicitamente definido por:

$$P_{\text{total}} = C_{\text{cat}} \cdot (1 + \bar\beta_{\text{proj}}) \quad \text{onde} \quad \bar\beta_{\text{proj}} = \frac{P_{\text{total}}}{C_{\text{cat}}} - 1$$

e $C_{\text{cat}} = CC_{\text{total}}$ (custo de catálogo PU×Q).

### 24.2 Condição de Viabilidade

Da Seção 15:

$$\text{Viável} \iff P_{\text{total}} > OC_{\text{total}} \iff \bar\beta_{\text{proj}} > R - 1$$

Com BDI heterogêneo, a condição se expande em termos de cada categoria:

$$\text{Margem} = \frac{P_{\text{total}} - OC_{\text{total}}}{P_{\text{total}}} = 1 - \frac{OC_{\text{total}}}{P_{\text{total}}}$$

### 24.3 Fluxo Completo: Schedule → Pool → BDI → Resultado

```
[Seções 1-12]              [Seções 13-19]             [Seções 20-24]
Schedule (DAG)    →    Pool (\mathcal{C}_pool^c + \mathcal{C}_pool^v)  →   BDI heterogêneo
                                                          ↓
H_i (horas reais)          M_k (permanência pool)    P = Σ_c C^(c)(1+BDI^(c))
ε_i (eficiência)    →      \mathcal{C}_pool = qt×c×T_pool   →   OC = C_dir + C_ind
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

### 25.4 Estado Real da Implementação

A premissa da Seção 25 precisa de uma ressalva importante: **hoje não existe `OC_real` no sistema**. O Concilium é inteiramente uma ferramenta de orçamento/proposta **pré-execução** — não há ingestão de custo pós-obra (medição, apontamento, EVM/valor agregado, as-built). Toda ocorrência de "custo real"/"custo realizado" no código (`custo_operacional_real`, `custo_total_autonomo`, etc.) é, na verdade, custo **bottom-up simulado a partir do cronograma planejado (RCPSP)** — ou seja, já é conceitualmente `OC_esperado`, nunca um dado de execução com desvio não previsto.

Dado isso, os 4 passos prescritos originalmente não descrevem o que falta implementar; eles descrevem uma separação explícita que **nunca foi construída como tal**:

1. ~~Calcular $CC_{\text{total}}$ do planejamento (catálogo puro)~~ — não existe isolado; `_build_custo_categorial_bottom_up` (`_categorial.py:136-173`) já retorna um custo pós-cronograma (equivalente a $CC \times R_i$), não catálogo puro.
2. ~~Calcular $R_i$ = OC_esperado/CC_total~~ — o análogo existe (`frentes_equivalentes_necessarias`/`fe_nec`, `_ponto_equilibrio.py:42-53`, definido exatamente como $OC/CC$), mas vive **só na trilha de diagnóstico** do Ponto de Equilíbrio (gera avisos como `VAL-FRENTES-NECESSARIAS-ALTA`) — nunca é lido por `_calc_venda_com_bdi` para ajustar o preço.
3. ~~Calcular $P_{\text{mercado}} = CC_{\text{total}} \times R_i \times (1+BDI)$ como dois fatores explícitos~~ — `_calc_venda_com_bdi` (`_venda_custo.py:22-89`) aplica BDI diretamente sobre `cat[...]` (o custo bottom-up pós-cronograma), sem nunca isolar $CC$ e $R_i$ como dois números auditáveis separados. O efeito é equivalente na prática (porque `cat[...]` já embute as ineficiências previstas), mas **não é auditável** — não há como, olhando o preço final, decompor "quanto veio do catálogo" vs. "quanto veio da ineficiência prevista do cronograma".
4. ~~Calcular margem = (P_mercado − OC_real)/P_mercado~~ — sem `OC_real`, esta margem não pode ser calculada; o que existe é `PontoEquilibrio` comparando `venda_por_item` (já com BDI) contra `custo_operacional_agregado` (o mesmo `OC_esperado`), o que mede a mesma coisa que a razão $R$/BDI mínimo de §15, não um resultado pós-execução.

**Conclusão revisada:** a Seção 25 continua correta como **princípio** (não aplicar BDI ingenuamente sobre um custo que já contém ineficiência sem reconhecer isso explicitamente) e, por sorte estrutural, o sistema não comete o erro descrito porque não existe caminho para `OC_real` (pós-execução) entrar na precificação — mas a "correção" formal ($CC$ e $R_i$ como dois fatores isolados e auditáveis) **nunca foi implementada**. Fica como pendência real: se o produto algum dia ganhar um loop de acompanhamento de execução (medição de campo realimentando o preço), a arquitetura atual de `_calc_venda_com_bdi` não tem onde plugar `OC_real` sem essa separação explícita — precisaria ser construída então, não corrigida agora.

---

## Seção 26: Quantitativo e Custo Semanal (Direto) — Partição Pool/Material e BDI Instancial

### 26.1 Custo de Equipe por Recurso Instancial

**Notação temporal usada de §26 a §29:** $h$ = horas por dia útil, $d$ = dias úteis por semana, com $h\cdot d \equiv h_w$ (horas/semana já definido em §3.1, tipicamente $44$h/semana). $j$ passa a indexar **semana** (não atividade — reservado a partir daqui, distinto do $u,v$ de aresta de DAG em §13–16 e do $f$ de frente paralela em §10.1).

Cada equipe $i$ é composta por um conjunto de recursos $\mathcal{R}_i$. Para cada $r \in \mathcal{R}_i$ com categoria $r.\text{cat} \in \{\text{EQ, MO, MAT}\}$ e quantidade $n_r$:

$$c_r = \begin{cases}
c_h^{(r)} & \text{se } r.\text{cat} \in \{\text{EQ, MO, MAT}\} \\[6pt]
\text{consumo}_r \cdot P_{r.\text{tipo}} & \text{se } r.\text{cat} = \text{COMB}
\end{cases}$$

onde $\text{consumo}_r$ [L/h] é o consumo específico do equipamento e $P_{r.\text{tipo}}$ [R\$/L] é o preço do combustível do tipo do recurso.

Os agregados por categoria da equipe $i$ são:

$$\gamma_i^{k} = \sum_{r \in \mathcal{R}_i,\; r.\text{cat}=k} c_r \cdot n_r \qquad \forall k \in \{\text{EQ, MO, MAT, COMB}\}$$

### 26.2 Quantitativo Semanal e Partição Pool vs Material

**Quantitativo semanal.** Seja $q_{ij}$ o quantitativo físico (m², m³, ...) que a equipe $i$ efetivamente produz na semana $j$, na eficiência realizada $\varepsilon_i$:

$$q_{ij} = \varepsilon_i \cdot \rho_i \cdot h \cdot d \cdot m_{ij}$$

O cronograma (skill-04, RCPSP) escolhe o número de semanas ativas $N_i = |\{j : m_{ij}=1\}|$ de modo que a soma feche exatamente o escopo da atividade:

$$\sum_j q_{ij} = \varepsilon_i \rho_i h d \cdot N_i = Q_i \quad\Longrightarrow\quad N_i = \frac{Q_i}{\varepsilon_i \rho_i h d} = \frac{H_{\text{real},i}}{h\,d}$$

— recupera $T_{\text{semanas}}$ de §3.1. Este é o mecanismo real de propagação de $\varepsilon_i$ para o custo: baixa eficiência não penaliza a semana em si, ela **aumenta $N_i$** (mais semanas para fechar o mesmo $Q_i$) — confirmado em `_pe_gap_praticabilidade_abs` (NEP-043).

**Partição pool (mobilização) vs material (produção):**

$$\gamma_i^{\text{pool}} = \gamma_i^{\text{EQ}} + \gamma_i^{\text{MO}} \qquad\qquad \gamma_i^{\text{MAT+COMB}} = \gamma_i^{\text{MAT}} + \gamma_i^{\text{COMB}}$$

$$\boxed{C_{ij} = \gamma_i^{\text{pool}} \cdot h \cdot d \cdot m_{ij} \;+\; \varepsilon_i \cdot \gamma_i^{\text{MAT+COMB}} \cdot h \cdot d \cdot m_{ij}}$$

| Componente | Cobrado por | Escala com $\varepsilon_i$ dentro da semana? | BDI típico |
|-----------|------|---------------------------|------------|
| Pool (EQ+MO) | semana mobilizada ($m_{ij}$) | Não — só indiretamente via $N_i$ | $\beta_{\text{pool}} \approx 30\%$ |
| Material (MAT+COMB) | produção realizada ($\varepsilon_i$ daquela semana) | Sim, diretamente | $\beta_{\text{MAT}} = 4\%$ |

**Interpretação:** pool (EQ+MO) é uma taxa semanal **fixa** — paga por estar mobilizado naquela semana, independente de quanto se produziu; é o custo de disponibilidade, não de produção. Material (MAT+COMB) é consumido em proporção ao que foi de fato produzido naquela semana — por isso escala diretamente com $\varepsilon_i$. Somando as $N_i$ semanas, o total de material é $\varepsilon_i\gamma_i^{\text{MAT+COMB}}hd N_i = \gamma_i^{\text{MAT+COMB}} Q_i/\rho_i$ — **independente de $\varepsilon_i$** (mesmo total para o mesmo $Q_i$, confirmando "diesel constante em $Q$", NEP-043), enquanto o total de pool é $\gamma_i^{\text{pool}}hd N_i$, que **cresce com $N_i$** conforme a eficiência piora.

**Nota de implementação — dois caminhos de código divergem sobre diesel:**

| Caminho | Comportamento | Variável |
|---|---|---|
| `_ponto_equilibrio.py` (`_pe_gap_praticabilidade_abs`, NEP-043) — modelo desta seção | Constante, função de $Q$ | — |
| `_dimensionamento_itens.py:590,608` (alimenta `EquipeDireta.custo_total`, o que entra em `_calc_venda_com_bdi`) | Escala diretamente por uma variável de eficiência | $\eta_w$ (utilização de gestão, não $\varepsilon$/clima) |
| `cubo_analitico_builder.py:75` | Idem | mesma $\eta_w$ |

$\eta_w$ é um dos três fatores da Matriz de Eficiência $\eta=\eta_s\cdot\eta_p\cdot\eta_w$ (NEP-035/036) — uma variável diferente de $\varepsilon=\beta\times\phi$ (clima/técnico, §1.1). Esta formalização segue o modelo declarado em NEP-043 (fonte de verdade do gap de praticabilidade); a divergência entre os dois caminhos de código, e a confusão $\eta_w$ vs. $\varepsilon$, são inconsistências de implementação não resolvidas aqui.

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

Esta equivalência é **garantida algebricamente por construção** (soma distributiva simples — não é uma propriedade emergente que possa quebrar silenciosamente) e é consistente com a forma como `_calc_venda_com_bdi`/`_build_custo_categorial_bottom_up` agregam custo por categoria. Não há, porém, um teste de regressão em `tests/` que exercite explicitamente as duas ordens de avaliação (recurso-primeiro vs. categoria-primeiro) — os testes existentes cobrem outros casos (taxa de BDI ausente, agregação básica). Recomenda-se um teste de round-trip dedicado.

---

## Seção 27: BDI Equivalente — Média Ponderada por Categoria

### 27.1 Definição do BDI Equivalente de Equipe

Análogo à eficiência média $\bar{\varepsilon}_i$ (§27.3), definimos o **BDI equivalente** $\bar{\beta}_i$ de uma equipe $i$ como a taxa única que reproduz o preço total quando aplicada ao custo total:

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

Eficiência média da atividade $i$ ao longo de suas $N_i$ semanas ativas (§26.2):

$$\bar{\varepsilon}_i = \frac{\sum_j \varepsilon_j \, m_{ij}}{N_i}$$

O custo horário **operacional** (com prolongamento por ineficiências) usa a inflação de horas $\eta_h$ já definida em §2.3 ($\eta_h=1/\varepsilon$), aqui por atividade:

$$h_i^{\text{op}} = \frac{\gamma_i^{\text{op}}}{H_i} = h_i \cdot \eta_{h,i} \quad \text{onde } \eta_{h,i} = \frac{1}{\bar{\varepsilon}_i}$$

(Esta subseção usava anteriormente o símbolo $\tau_i$ para $\eta_{h,i}$, citando "Seção 6" para a definição de $\bar\varepsilon_i$ — mas Seção 6 não a define, e $\tau_i$ colide com o $\tau^{(c)}$ de tributos em §30.3. Unificado em $\eta_{h,i}$, consistente com $\eta_h$ de §2.3.)

O **preço de venda horário** (operacional + BDI):

$$\boxed{p_i = h_i^{\text{op}} \cdot (1 + \bar{\beta}_i) = h_i \cdot \eta_{h,i} \cdot (1 + \bar{\beta}_i)}$$

**Dual do custo horário:**
- **Sem BDI:** $h_i$ (catálogo) → $h_i^{\text{op}} = h_i \cdot \eta_{h,i}$ (operacional)
- **Com BDI:** $h_i \cdot (1 + \bar{\beta}_i)$ (catálogo + BDI) → $p_i = h_i \cdot \eta_{h,i} \cdot (1 + \bar{\beta}_i)$ (operacional + BDI)

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

## Seção 28: Custo Semanal com BDI — Equivalente como Função de $\varepsilon_i$

### 28.1 Custo Semanal com e sem BDI

Retomando §26.2 — $\gamma_i^{\text{pool}}$ (EQ+MO, taxa fixa por semana mobilizada) e $\gamma_i^{\text{MAT+COMB}}$ (MAT+COMB, escala com produção realizada). O custo semanal **sem BDI** da equipe $i$ na semana $j$:

$$C_{ij} = (\gamma_i^{\text{pool}} + \varepsilon_i \cdot \gamma_i^{\text{MAT+COMB}}) \cdot h \cdot d \cdot m_{ij}$$

O custo semanal **com BDI**, aplicando $\beta_{\text{pool}}$ sobre o componente de pool e $\beta_{\text{MAT}}$ sobre o material:

$$\tilde{C}_{ij} = (\gamma_i^{\text{pool}}(1+\beta_{\text{pool}}) + \varepsilon_i \cdot \gamma_i^{\text{MAT+COMB}}(1+\beta_{\text{MAT}})) \cdot h \cdot d \cdot m_{ij}$$

### 28.2 BDI Equivalente da Atividade

O BDI equivalente da atividade $i$ é a razão do custo total com BDI pelo sem BDI, complementar a 1:

$$\bar{\beta}_i(\varepsilon_i) = \frac{\sum_j \tilde{C}_{ij}}{\sum_j C_{ij}} - 1$$

Como $h \cdot d \cdot m_{ij}$ cancela numerador e denominador:

$$\bar{\beta}_i(\varepsilon_i) = \frac{\gamma_i^{\text{pool}}(1+\beta_{\text{pool}}) + \varepsilon_i \gamma_i^{\text{MAT+COMB}}(1+\beta_{\text{MAT}})}{\gamma_i^{\text{pool}} + \varepsilon_i \gamma_i^{\text{MAT+COMB}}} - 1 = \frac{\gamma_i^{\text{pool}} \beta_{\text{pool}} + \varepsilon_i \gamma_i^{\text{MAT+COMB}} \beta_{\text{MAT}}}{\gamma_i^{\text{pool}} + \varepsilon_i \gamma_i^{\text{MAT+COMB}}}$$

Definindo a **fração de material efetiva** (fração do custo semanal que é produção, não mobilização):

$$\delta_i(\varepsilon_i) = \frac{\varepsilon_i \gamma_i^{\text{MAT+COMB}}}{\gamma_i^{\text{pool}} + \varepsilon_i \gamma_i^{\text{MAT+COMB}}}$$

obtemos:

$$\boxed{\bar{\beta}_i(\varepsilon_i) = (1 - \delta_i) \cdot \beta_{\text{pool}} + \delta_i \cdot \beta_{\text{MAT}}}$$

**Propriedade:** $\bar{\beta}_i$ é função **decrescente** de $\varepsilon_i$, pois $\beta_{\text{pool}} > \beta_{\text{MAT}}$ ($30\% \gg 4\%$) e $\delta_i$ cresce com $\varepsilon_i$. Quanto mais a equipe produz por semana (maior $\varepsilon_i$), maior a fração do custo semanal em material (BDI baixo) relativa ao pool fixo (BDI alto) — o BDI equivalente da atividade cai.

| $\varepsilon_i$ | $\delta_i$ | $\bar{\beta}_i$ | Interpretação |
|----------------|-----------|----------------|---------------|
| $0$ | $0$ | $\beta_{\text{pool}} \approx 30\%$ | Equipe mobilizada, zero produção — custo é 100% pool parado |
| $0{,}5$ | $\frac{0{,}5\gamma^{\text{MAT+COMB}}}{\gamma^{\text{pool}} + 0{,}5\gamma^{\text{MAT+COMB}}}$ | Intermediário | Produção parcial |
| $1$ | $\frac{\gamma^{\text{MAT+COMB}}}{\gamma^{\text{pool}}+\gamma^{\text{MAT+COMB}}} = \delta$ | $(1-\delta)\beta_{\text{pool}} + \delta\beta_{\text{MAT}}$ | Catálogo nominal |
| $\to\infty$ | $\to 1$ | $\to \beta_{\text{MAT}} \approx 4\%$ | Produção domina o custo semanal |

### 28.3 BDI Equivalente do Pool de Mobilização

O pool de recursos **de mobilização** (EQ+MO para a janela $\mathcal{T}_{\text{pool}}$) tem custo total:

$$C_{\text{pool}}^{\text{pool}} = \sum_{i \in V} \gamma_i^{\text{pool}} \cdot |\mathcal{T}_i|$$

Como todos os recursos de pool partilham o mesmo $\beta_{\text{pool}}$, o BDI do pool de mobilização é simplesmente:

$$\bar{\beta}_{\text{pool}}^{\text{pool}} = \beta_{\text{pool}}$$

### 28.4 BDI Equivalente do Pool de Material

O pool de **material** (MAT+COMB, escala com produção) tem custo total:

$$C_{\text{pool}}^{\text{MAT+COMB}} = \sum_{i \in V} \varepsilon_i \gamma_i^{\text{MAT+COMB}} \cdot |\mathcal{T}_i|$$

Igualmente, como todo material partilha $\beta_{\text{MAT}}$:

$$\bar{\beta}_{\text{pool}}^{\text{MAT+COMB}} = \beta_{\text{MAT}}$$

### 28.5 BDI Equivalente Agregado do Escopo

O BDI de escopo é a média ponderada dos dois pools:

$$\bar{\beta}_{\text{proj}} = \frac{C_{\text{pool}}^{\text{pool}} \cdot \beta_{\text{pool}} + C_{\text{pool}}^{\text{MAT+COMB}} \cdot \beta_{\text{MAT}}}{C_{\text{pool}}^{\text{pool}} + C_{\text{pool}}^{\text{MAT+COMB}}} = (1 - \Delta) \cdot \beta_{\text{pool}} + \Delta \cdot \beta_{\text{MAT}}$$

onde:

$$\Delta = \frac{C_{\text{pool}}^{\text{MAT+COMB}}}{C_{\text{pool}}^{\text{pool}} + C_{\text{pool}}^{\text{MAT+COMB}}} = \frac{\sum_i \varepsilon_i \gamma_i^{\text{MAT+COMB}} |\mathcal{T}_i|}{\sum_i (\gamma_i^{\text{pool}} + \varepsilon_i \gamma_i^{\text{MAT+COMB}}) |\mathcal{T}_i|}$$

**Relação com $\delta_i$:** $\Delta$ é a média temporal-ponderada das frações de material efetivas:

$$\Delta = \frac{\sum_i \delta_i(\varepsilon_i) \cdot \gamma_i^{\text{op}} \cdot |\mathcal{T}_i|}{\sum_i \gamma_i^{\text{op}} \cdot |\mathcal{T}_i|} \qquad \gamma_i^{\text{op}} \equiv \gamma_i^{\text{pool}} + \varepsilon_i\gamma_i^{\text{MAT+COMB}}$$

### 28.6 Implicação — R_i e BDI Equivalente Se Reforçam (Não Competem)

Integrando $\bar{\beta}_i$ com $R_i$ (Seção 24.3):

$$P_i = CC_i \cdot R_i \cdot (1 + \bar{\beta}_i(\varepsilon_i))$$

Como $R_i \approx 1/\varepsilon_i$ para projetos grandes (decrescente em $\varepsilon_i$) e $\bar{\beta}_i$ agora também **decresce** com $\varepsilon_i$ (§28.2):

$$\frac{\partial P_i}{\partial \varepsilon_i} = CC_i \cdot \left(\underbrace{\frac{-1}{\varepsilon_i^2}(1+\bar{\beta}_i)}_{< 0} + \underbrace{\frac{1}{\varepsilon_i} \frac{\partial \bar{\beta}_i}{\partial \varepsilon_i}}_{< 0}\right) < 0$$

Os dois termos têm o mesmo sinal — **não há mais ambiguidade**: melhorar a eficiência operacional reduz tanto $R_i$ (menos semanas de pool) quanto $\bar{\beta}_i$ (mais peso em material de BDI baixo), e os dois efeitos se reforçam na direção de reduzir o preço necessário. Não existe um "ponto ótimo" intermediário de $\varepsilon_i$ a buscar — eficiência maior é estritamente melhor para o preço, dado $CC_i$ fixo.

---

## Seção 29: Custo Semanal do Indireto com BDI — Simetria com o Direto e Integral Discreta Unificada

As Seções 26/28 formalizam o custo semanal **direto** com BDI, $\tilde{C}_{ij}$, e o preço $P^{\text{dir}}$ como soma (integral discreta) desse custo sobre semanas e equipes. Esta seção estende a mesma construção ao **indireto**, mostrando que a fórmula estática $P^{\text{ind}}$ (§21.4) é o mesmo tipo de integral discreta — só que sobre um objeto temporal diferente.

### 29.1 Custo Semanal Direto com BDI (Retomando §26.2/§28.1)

O custo direto semanal com BDI, já estabelecido em §28.1:

$$\boxed{\tilde{C}_{ij}^{\text{dir}} = \Big(\gamma_i^{\text{pool}}(1+\beta_{\text{pool}}) + \varepsilon_i \cdot \gamma_i^{\text{MAT+COMB}}(1+\beta_{\text{MAT}})\Big) \cdot h \cdot d \cdot m_{ij}}$$

$\gamma_i^{\text{pool}}$ (EQ+MO) é cobrado por semana mobilizada, sem depender de $\varepsilon_i$ dentro da semana — o efeito da eficiência sobre esse termo é inteiramente indireto, via $N_i = |\{j:m_{ij}=1\}|$ (§26.2). $\gamma_i^{\text{MAT+COMB}}$ (MAT+COMB) escala diretamente com $\varepsilon_i$ — é consumido em proporção à produção real daquela semana. A seguir, generalizamos a mesma estrutura (custo semanal × indicador de atividade × BDI por sub-categoria) para o indireto, que não tem quantitativo físico associado (§29.2) mas segue o mesmo padrão de soma no tempo.

### 29.2 Estrutura Temporal do Indireto — o Análogo Categorial de $m_{ij}$

O código não trata custo indireto como verba estática: `IndiretoSemanal` (`_indiretos_insumos.py:50-61`) é uma série por **categoria × semana**:

```python
class IndiretoSemanal(BaseModel):
    semana: int
    categoria: str          # ADM, TOP, LAB, QSMS, MOB, ...
    custo_mao_de_obra: float
    custo_equipamentos: float
    custo_verbas: float
    custo_semanal: float
    ativa: bool = True
```

`n` (número de semanas) vem do makespan real do RCPSP, não do prazo contratual (`skill.py:230-234`). Cada categoria $l$ segue um de dois **drivers** (`_breakdown.py`), que definem um indicador binário $m_l(j)$ análogo ao $m_{ij}$ das equipes diretas, mas aplicado à categoria inteira em vez de a um recurso individual:

$$m_l(j) = \begin{cases}
1 \quad \forall j \in \{0, \ldots, n-1\} & \text{driver = permanência (ADM, TOP, LAB, QSMS)} \\
\mathbb{1}[j \in \{0,\, n-1\}] & \text{driver = one\_time (MOB)}
\end{cases}$$

Ou seja: overhead de permanência é rateado igualmente por toda semana do projeto (ativa sempre); overhead de mobilização/desmobilização concentra-se nas duas semanas de borda — exatamente o mesmo tipo de indicador liga/desliga temporal usado para pool, só que na granularidade de categoria, não de recurso individual (ver §29.8).

### 29.3 Custo Semanal por Sub-categoria de BDI

Cada categoria indireta $l$ é decomposta nas mesmas quatro sub-categorias de BDI usadas no direto — MO, EQ, COMB (fornecimento, mesma taxa $\beta_{\text{MAT}}$ do direto) — mais uma quinta, **VM** (verba + mobilização), que não existe no lado direto:

**Driver permanência** — rateio do custo mensal por $s_{\text{mes}}$ (semanas/mês, ≈ 4,33 — mesma constante que $p_{\min}$ de §3.1, mas usada aqui como conversão de calendário para o rateio do indireto, não como parâmetro contratual de permanência mínima):

$$\gamma_l^{k,\text{sem}} = \frac{\Gamma_l^{k,\text{mensal}}}{s_{\text{mes}}} \qquad k \in \{\text{MO, EQ, COMB, VM}\}$$

**Driver one\_time (MOB)** — evento único por borda, reaproveitando a notação de mobilização/desmobilização de §17.2:

$$\gamma_l^{\text{VM,sem}}(j) = \begin{cases} c_{\text{mob}}^{(l)} & j = 0 \\ c_{\text{demob}}^{(l)} & j = n-1 \\ 0 & \text{caso contrário} \end{cases}$$

O custo semanal total da categoria $l$ (campo `custo_semanal` de `IndiretoSemanal`) é:

$$C_{lj}^{\text{ind}} = \sum_{k \in \{\text{MO,EQ,COMB,VM}\}} \gamma_l^{k,\text{sem}}(j) \cdot m_l(j)$$

**Nota:** ao contrário do pool direto (§29.1), o indireto **não tem fator $\varepsilon$** — é um custo de calendário puro, presente ou ausente por semana, independente de quanto as equipes diretas produziram naquela semana. Esta é uma diferença estrutural real, não uma omissão: ADM e TOP são pagos por estarem mobilizados, não por produtividade de terceiros.

### 29.4 Camada BDI sobre o Custo Semanal do Indireto

Aplicando BDI por sub-categoria — **as mesmas taxas $\beta_{\text{MO}}, \beta_{\text{EQ}}, \beta_{\text{MAT}}$ do custo direto** (mesmo dicionário `bdi_rates`, construído uma única vez em `_resolve_bdi_full`, `_bdi_resolucao.py:280-305` — não há dessincronia de taxa entre direto e indireto para MO/EQ/MAT) **mais uma taxa própria $\beta_{\text{IND}}$ para o bloco VM**:

$$\boxed{\tilde{C}_{lj}^{\text{ind}} = \Big(\gamma_l^{\text{MO,sem}}(1+\beta_{\text{MO}}) + \gamma_l^{\text{EQ,sem}}(1+\beta_{\text{EQ}}) + \gamma_l^{\text{COMB,sem}}(1+\beta_{\text{MAT}}) + \gamma_l^{\text{VM,sem}}(j)\,(1+\beta_{\text{IND}})\Big) \cdot m_l(j)}$$

$\beta_{\text{IND}} \approx 25{,}21\%$ é uma linha própria da tabela BDI (`DEFAULT_BDI_TABELA.indireto`, `_components.py:151-219`), com a mesma fórmula multiplicativa TCU de §20.2, diferindo de $\beta_{\text{MO}}$ **apenas no lucro** ($L=5\%$ vs $L=9\%$) — não é o mesmo $\beta_{\text{MAT}}$ (4%) nem uma média dos outros três.

**Implementação** (`_calc_venda_com_bdi`, `_venda_custo.py:61-88`):

```python
venda_indireto += (
    c_mo * (1 + r_mo) + c_eq * (1 + r_eq) + c_comb * (1 + r_mat)
    + (c_verba + c_mob) * (1 + r_indir)
)
```

### 29.5 Recuperação da Fórmula Estática — Prova de Consistência

Somando $\tilde{C}_{lj}^{\text{ind}}$ sobre todas as semanas $j$, cada termo colapsa em seu agregado total, pois $\sum_j \gamma_l^{k,\text{sem}} \cdot m_l(j) = \Gamma_l^k$ por construção (rateio mensal × meses totais, ou soma de mob+demob):

$$P_l^{\text{ind}} = \sum_{j=0}^{n-1} \tilde{C}_{lj}^{\text{ind}} = \Gamma_l^{\text{MO}}(1+\beta_{\text{MO}}) + \Gamma_l^{\text{EQ}}(1+\beta_{\text{EQ}}) + \Gamma_l^{\text{COMB}}(1+\beta_{\text{MAT}}) + \Gamma_l^{\text{VM}}(1+\beta_{\text{IND}})$$

Somando sobre todas as categorias $l$ (ADM, TOP, LAB, QSMS, MOB, ...) e definindo $\Gamma^k = \sum_l \Gamma_l^k$:

$$\boxed{P^{\text{ind}} = \sum_{l}\sum_{j} \tilde{C}_{lj}^{\text{ind}} = \Gamma^{\text{MO}}(1+\beta_{\text{MO}}) + \Gamma^{\text{EQ}}(1+\beta_{\text{EQ}}) + \Gamma^{\text{COMB}}(1+\beta_{\text{MAT}}) + \Gamma^{\text{VM}}(1+\beta_{\text{IND}})}$$

Esta é exatamente a fórmula estática de §21.4 ($P^{\text{ind}} = C_{\text{ind}}^{\text{MO}}(1+\beta_{\text{MO}}) + C_{\text{ind}}^{\text{EQ}}(1+\beta_{\text{EQ}}) + C_{\text{ind}}^{\text{COMB}}(1+\beta_{\text{MAT}}) + (C_{\text{ind}}^{\text{verba}}+C_{\text{ind}}^{\text{mob}})(1+\beta_{\text{IND}})$ — código usa `r_mo`/`r_eq`/`r_mat`/`r_indir`, mesmos valores, ver bloco abaixo), confirmada em código por `_calc_venda_com_bdi` (§29.4). **A fórmula estática já em produção é, por construção, a integral discreta do modelo semanal** — não uma aproximação dela. A mesma prova por distributividade/associatividade de §26.4 se aplica aqui.

### 29.6 Exemplo Numérico — Categoria ADM (permanência) + MOB (one\_time)

Projeto com $n = 13$ semanas (makespan RCPSP), $s_{\text{mes}} = 4{,}33$:

| Categoria | Driver | $\Gamma^{\text{MO}}$ | $\Gamma^{\text{EQ}}$ | $\Gamma^{\text{VM}}$ |
|---|---|---|---|---|
| ADM | permanência (12k/4k/2k por mês) | 36.028 | 12.009 | 6.005 |
| MOB | one\_time ($c_{\text{mob}}=c_{\text{demob}}=$ 20k) | — | — | 40.000 |
| **Total** | | **36.028** | **12.009** | **46.005** |

Com $\beta_{\text{MO}} = 29{,}97\%$, $\beta_{\text{EQ}} = 20\%$ (ilustrativo), $\beta_{\text{IND}} = 25{,}21\%$:

$$P^{\text{ind}} = 36.028 \times 1{,}2997 + 12.009 \times 1{,}20 + 46.005 \times 1{,}2521 \approx 46.824 + 14.411 + 57.601 = 118.836$$

sobre um custo indireto sem BDI de $\Gamma^{\text{ind}} = 94.042$ — BDI equivalente do indireto: $\bar{\beta}^{\text{ind}} = 118.836/94.042 - 1 \approx 26{,}4\%$ (entre $\beta_{\text{EQ}}$ e $\beta_{\text{IND}}$, pela média ponderada de §27.2 aplicada às sub-categorias do indireto).

### 29.7 Fórmula Unificada — Preço Total como Integral Discreta Dupla

Combinando §28.1 (direto) e §29.4 (indireto), o preço total do projeto é a soma de **duas** integrais discretas independentes — uma sobre equipes diretas $i \in V$, outra sobre categorias indiretas $l$ — cada uma sobre o mesmo eixo de semanas $j$:

$$\boxed{P_{\text{total}} = \underbrace{\sum_{i \in V}\sum_{j} \tilde{C}_{ij}^{\text{dir}}}_{P^{\text{dir}}} + \underbrace{\sum_{l}\sum_{j} \tilde{C}_{lj}^{\text{ind}}}_{P^{\text{ind}}}}$$

Isto reconcilia as duas visões do modelo (§15/§21.5, estática, e §26–29, temporal): $P_{\text{total}} = P^{\text{dir}} + P^{\text{ind}}$ **é**, termo a termo, a integral discreta de $\tilde{C}_{ij}^{\text{dir}} + \tilde{C}_{lj}^{\text{ind}}$ sobre semana e sobre recurso/categoria — não uma coincidência algébrica, mas a mesma estrutura (custo semanal × indicador de atividade × fator de BDI por sub-categoria) instanciada duas vezes. A diferença estrutural entre os dois lados: no direto, $\varepsilon_i$ atua em **dois** pontos — diretamente no termo de material (§28.1) e indiretamente em quantas semanas $m_{ij}=1$ (via extensão de cronograma, §26.2); no indireto, não há $\varepsilon$ nenhum — o número de semanas ativas é determinado apenas pelos drivers de §29.2 (permanência/one\_time), porque indireto não produz quantitativo físico.

### 29.8 Lacuna Estrutural — Indireto Não Tem Granularidade Instancial

A simetria de §29.1–29.7 é exata no nível **categoria × semana**, mas não desce ao nível **recurso individual × semana** que o pool direto tem via `InstanciaRecurso` (`_pool_recursos.py:202+`, timeline $\sigma_k(j) \in \{\text{prod, idle, off}\}$ por instância). O modelo `Indireto` (`_financeiro_resultado.py:83-106`) usa `funcoes`/`equipamentos`/`verbas_mensais` como `list[dict]` sem schema tipado — a decomposição $\gamma_l^k$ desta seção existe apenas ao nível agregado de categoria, reconstruída em `IndiretoSemanal` por rateio (§29.2), não observada instância a instância como em `EquipeDireta`/`InstanciaRecurso`.

**Consequência:** o BDI equivalente do indireto ($\bar{\beta}^{\text{ind}}$, §29.6) é auditável por categoria (ADM, TOP, MOB, ...), mas não por pessoa/equipamento individual dentro da categoria — ao contrário do direto, onde §26.1–26.3 decompõem até o recurso $r$. Fechar essa lacuna exigiria estender `Indireto` com uma lista tipada de recursos (à semelhança de `FuncaoEquipeDireta`), o que está fora do escopo desta formalização.

---

## Seção 30: Decomposição Estrita de Margem — Lucro, Overhead e Tributos Não São a Mesma Coisa

O documento usa "margem" em pelo menos dois sentidos incompatíveis. Esta seção define, para cada categoria de BDI, três grandezas separadas e mutuamente exclusivas — e mostra que o próprio código já tem uma via de contaminação entre elas.

### 30.1 O Problema — Dois "Margem" Diferentes no Mesmo Documento

1. **Lucro contratual** ($L^{(c)}$, §20.1): uma taxa fixa por categoria, definida na tabela de BDI, que não muda com o desempenho do projeto.
2. **"Margem" financeira realizada** (§15.2, §24.2, §25.2, §27.6): $\text{Margem} = (P - OC)/P$ — o que sobra do preço depois do custo operacional *real*. Essa grandeza **mistura** recuperação de overhead (AC+DF+Gr+CR), tributos (T), lucro (L) **e** o efeito de ineficiências operacionais não previstas ($\Delta OC$, §25.3).

Chamar as duas coisas de "margem" sem qualificação é exatamente o risco apontado: alguém lê "$L_{\text{MO}}=9\%$" em §20.3 e "Margem $=(P-OC)/P$" em §15.2 e conclui, errado, que são a mesma taxa. Não são — a segunda **contém** a primeira, mais tributo, mais overhead administrativo, mais/menos desvio operacional.

### 30.2 Decomposição em Cascata (Waterfall) — a Forma Aditiva Exata

A fórmula TCU (§20.2) aplica os componentes **multiplicativamente**, em cascata, sobre o custo direto $C^{(c)}$, e divide por $(1-T^{(c)})$ ao final (gross-up de tributos). A decomposição aditiva **exata** de $P^{(c)} = C^{(c)}(1+BDI^{(c)})$ replica essa mesma cascata, passo a passo:

$$P_0 = C^{(c)} \quad\to\quad P_1 = P_0(1+AC^{(c)}) \quad\to\quad P_2 = P_1(1+DF^{(c)}) \quad\to\quad P_3 = P_2(1+\text{Gr}^{(c)}) \quad\to\quad P_4 = P_3(1+C\text{Gr}^{(c)})$$
$$P_5 = P_4(1+L^{(c)}) \qquad P^{(c)} = P_6 = \frac{P_5}{1-T^{(c)}}$$

Cada passo contribui exatamente a diferença que introduz:

$$\boxed{\text{Overhead}^{(c)} = P_4 - P_0 \qquad \text{Lucro}^{(c)} = P_5 - P_4 \qquad \text{Tributos}^{(c)} = P^{(c)} - P_5}$$

com a identidade exata (por telescopagem, sem aproximação):

$$C^{(c)} + \text{Overhead}^{(c)} + \text{Lucro}^{(c)} + \text{Tributos}^{(c)} = P^{(c)}$$

### 30.3 Três Taxas Puras por Categoria — Definições Canônicas

$$\theta^{(c)} = \frac{\text{Overhead}^{(c)}}{P^{(c)}} \qquad \boxed{\lambda^{(c)} = \frac{\text{Lucro}^{(c)}}{P^{(c)}}} \qquad \tau^{(c)} = \frac{\text{Tributos}^{(c)}}{P^{(c)}} = T^{(c)}$$

$\tau^{(c)}$ não precisa da cascata — tributo é, por definição do gross-up, sempre exatamente a fração $T^{(c)}$ do preço, qualquer que seja a ordem dos outros componentes. **Apenas $\lambda^{(c)}$ deve ser chamado "margem de lucro"** — $\theta^{(c)}$ é recuperação de despesa administrativa/financeira/risco (obrigação contratual, não lucro), e $\tau^{(c)}$ é repasse de tributo (obrigação fiscal, não lucro). Invariante:

$$\frac{C^{(c)}}{P^{(c)}} + \theta^{(c)} + \lambda^{(c)} + \tau^{(c)} = 1$$

### 30.4 Tabela de Referência — Valores DEFAULT, Decomposição Exata

| Categoria | Custo/P | $\theta$ (overhead) | $\lambda$ (lucro) | $\tau$ (tributos) | BDI |
|---|---|---|---|---|---|
| MÃO DE OBRA | 76,94% | 5,88% | **7,45%** | 9,73% | 29,97% |
| SERVIÇOS | 76,94% | 5,88% | **7,45%** | 9,73% | 29,97% |
| INDIRETO | 79,87% | 6,10% | **4,30%** | 9,73% | 25,21% |
| MATERIAL | 96,15% | 0,00% | **3,85%** | 0,00% | 4,00% |
| DIESEL | 96,15% | 0,00% | **3,85%** | 0,00% | 4,00% |

(valores calculados diretamente de `DEFAULT_BDI_TABELA`, cascata de §30.2; INDIRETO usa a linha corrigida de §20.3)

### 30.5 Achado — `ComponentesBdi.decomposicao_no_preco()` Usa Overhead Aditivo, Não a Cascata

O código (`_components.py`) tem **dois métodos com bases matemáticas diferentes** para a mesma tabela de BDI:

- `bdi_total` — cascata multiplicativa (§20.2/§30.2), é o que **efetivamente precifica** (`bdi_rates` em `_resolve_bdi_full`, consumido por `_calc_venda_com_bdi`).
- `decomposicao_no_preco()` — trata overhead como **soma simples** ($OH = AC+DF+r+CR+L$, campo `r` do código = nosso $\text{Gr}$, sem cascata) e calcula $c_{pv} = (1-T)/(1+OH)$. A própria docstring da classe já avisa: *"a forma aditiva... subestima o BDI em ~0,9 pp"*.

O gap medido (cascata − aditivo, sobre `DEFAULT_BDI_TABELA`):

| Categoria | $\lambda$ cascata (exato) | `margem_l` aditivo (código) | Gap |
|---|---|---|---|
| MÃO DE OBRA / SERVIÇOS | 7,45% | 6,97% | **0,48 pp** |
| INDIRETO | 4,30% | 4,01% | **0,29 pp** |
| MATERIAL / DIESEL | 3,85% | 3,85% | 0,00 pp (só há 1 termo de overhead — sem cascata para divergir) |

Isto **não é** apenas uma divergência acadêmica — `decomposicao_no_preco()["margem_l"]` está em produção em:

- `skill.py:240` (`06-resultado-financeiro/_precificacao`) — alimenta a validação `VAL-BDI-MARGEM-INSUFICIENTE`, que compara a margem líquida embutida contra `inputs.lucro_minimo_pct`. Com o método aditivo, a margem reportada é **sistematicamente menor** que a real (embutida no preço efetivamente cobrado via `bdi_total`) — o gate pode soar alarme (ou deixar de soar, perto do limiar) usando um número ~0,3–0,5pp mais pessimista do que o lucro real.
- `memorial_bdi_builder.py:232` e `infrastructure/.../excel/sheets/memorial/_bdi.py:140` — o memorial de BDI (relatório entregue ao negócio/cliente) reporta "margem líquida" pelo método aditivo, que não soma com os demais itens do mesmo jeito que a cascata que gerou o preço realmente cobrado.
- `cubo_analitico_builder.py:203-207` — mesma base aditiva na granularidade do cubo analítico.

**Isto não foi corrigido nesta formalização** — é uma decisão de produto (qual convenção usar como "a" margem oficial reportada) que toca um gate de validação e relatórios já entregues. Fica registrado como pendência a decidir, não como bug silenciosamente corrigido.

### 30.6 Reconciliação com a "Margem" Financeira Realizada ($\mu$)

Renomeando por clareza a "Margem" de §15.2/§24.2/§25.2/§27.6 como **$\mu$** (resultado financeiro realizado, não lucro), e agregando §30.3 por categoria com peso $w^{(c)} = C^{(c)}/C_{\text{total}}$:

$$\bar\theta = \sum_c w^{(c)}\theta^{(c)} \qquad \bar\lambda = \sum_c w^{(c)}\lambda^{(c)} \qquad \bar\tau = \sum_c w^{(c)}\tau^{(c)}$$

Se a execução ocorre exatamente conforme previsto ($OC_{\text{real}} = C_{\text{total}}$, base do BDI):

$$\mu = \bar\theta + \bar\lambda + \bar\tau$$

Com desvio operacional imprevisto $\Delta OC = OC_{\text{real}} - OC_{\text{esperado}}$ (§25.1–25.3):

$$\boxed{\mu = \bar\theta + \bar\lambda + \bar\tau - \frac{\Delta OC}{P_{\text{total}}}}$$

**Consequência prática:** $\mu$ pode cair a zero ou ficar negativo mesmo com $\bar\lambda > 0$ — o lucro contratual ($L$) continua embutido na estrutura de preço e é repassado a tributo/overhead independentemente de $\Delta OC$; quem "perde" com ineficiência imprevista é o resultado do caixa ($\mu$), não a taxa de lucro contratual ($\lambda$), que é fixa por definição. Reportar "$\mu = 5\%$" como se fosse "$\lambda = 5\%$" (ou vice-versa) é exatamente o tipo de agregação indevida que esta seção evita.

---

**Versão:** 5.8 (Notação normalizada: glossário canônico adicionado; 12 colisões de símbolo resolvidas por renomeação — $\gamma^{c/v}\to\gamma^{\text{pool/MAT+COMB}}$, $R^{(c)}\to\text{Gr}^{(c)}$, $\phi_i\to\chi_i$, $C_p\to\mathcal{C}_p$, $\tau_i\to\eta_{h,i}$, $\delta_k^*/\delta_{\max}\to G_k^*/G_{\max}$, $r_k\to\beta_k$, $(i,j)_{\text{DAG}}\to(u,v)$, $\varepsilon_j\to\varepsilon_f$, $\overline{BDI}\to\bar\beta_{\text{proj}}$, $m^*\to\mu^*$, $h_m\to h_{\min}$ — e 5 colisões de baixo risco documentadas sem renomear. Mantém v5.7: §1–4 com material em $H_{\text{nom}}$, quantitativo semanal $q_{ij}$, direção de $\varepsilon$ em §26–29)  
**Data:** 2026-08-17  
**Status:** Formalização Completa, Auditada contra Código e com Notação Normalizada: §1–12 (Fundamentos) → §13–19 (Pool) → §20–25 (BDI) → §26–29 (Quantitativo Semanal, Pool/Material, Indireto) → §30 (Margem θ/λ/τ) ✅
