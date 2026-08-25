# Formulário White-Box — Atividades, Pool de Recursos e Custos Indiretos

---

## Parte I — Entrada: Definição das Atividades (formulário)

### I.1 Conjunto de atividades

$$\mathcal{A} = \{A_i\}_{i=1}^{n_{\text{ativ}}}$$

### I.2 Tupla da atividade

Na prática, cada atividade representa uma frente de trabalho do projeto — escavação, concretagem, lançamento de base, e assim por diante — com sua própria meta física, sua equipe e suas dependências de outras atividades. Os quatro campos abaixo resumem tudo que precisa ser fornecido; os demais campos da tabela são calculados automaticamente a partir deles.

$$A_i = (Q_i,\ E_i,\ W_i,\ B_i)$$

| Campo | Tipo | Preenchido por |
|---|---|---|
| $Q_i$ | quantitativo total [un] | usuário |
| $E_i$ | equipe (§I.3) | usuário |
| $W_i$ | política de mobilização (§I.4) | usuário |
| $B_i$ | predecessores + completude parcial (§I.5) | usuário |
| $j_i^0$ | semana de início | **derivado** (schedule, §I.5) |
| $N_i$ | duração em semanas | **derivado** (fecho de escopo exato via busca monotônica, Parte IV/XIV) |
| $(h_i, d_i)$ | regime de jornada da equipe | usuário, $d_i\in\{4,5,6\}$, $h_i\in\{6,8\}$ |

### I.3 Equipe $E_i = (\mathcal{G}_i, R_i)$

#### I.3.1 Composição de recursos

$R_i = \{r\}$, cada recurso descrito por:

| Campo | Significado |
|---|---|
| $\text{cat}(r) \in \{EQ, MO, MAT, COMB\}$ | categoria de BDI |
| $n_r$ | quantidade do recurso $r$ dentro de **uma** frente |
| regime | `mensal` (EQ/MO) ou `consumo` (MAT/COMB) |
| $V_r^{\text{mensal}}$ | custo contratual mensal [R\$/mês], se regime = `mensal` |
| $\kappa_r$ | taxa física de consumo [unid$_g$/unid$_{\text{tempo}}$], se regime = `consumo` |
| $g(r)$ | tipo físico do bem consumível, se regime = `consumo` |
| $p_{g(r)}$ | preço de aquisição [R\$/unid$_g$], se regime = `consumo` |

**Custo horário de catálogo do recurso $r$** — agnóstico em unidade física:

$$c_r = \begin{cases}
\dfrac{V_r^{\text{mensal}}}{s_{\text{mes}}\cdot d_i\cdot h_i} & \text{cat}(r)\in\{EQ,MO\}\quad\text{(diluição contratual)}\\[10pt]
\kappa_r \cdot p_{g(r)} & \text{cat}(r)\in\{MAT,COMB\}\quad\text{(consumo: taxa física × preço unitário)}
\end{cases}$$

onde:
- $\kappa_r$ [unid$_g$ / h$_{\text{op}}$]: taxa de consumo do bem $g(r)$ por hora de operação do recurso $r$
- $p_{g(r)}$ [R\$/unid$_g$]: preço de aquisição por unidade física do bem $g$
- **unid$_g$** é declarada no cadastro do bem e não é fixada neste formulário

*Exemplos de instâncias da mesma fórmula:* combustível → $\kappa_r$ [L/h], $p_g$ [R\$/L]; agregado → $\kappa_r$ [t/h], $p_g$ [R\$/t]; explosivo → $\kappa_r$ [kg/h], $p_g$ [R\$/kg]; cimento → $\kappa_r$ [kg/h], $p_g$ [R\$/kg].

**MAT legado.** Quando `atributos_especificos.consumo_horario_fisico` e `atributos_especificos.unidade_fisica` estão ausentes no cadastro do bem, trata-se do caso degenerado $\kappa_r = 1\ [\text{unid}_g/\text{h}]$, $p_{g(r)} = c_r\ [\text{R\$}/\text{h}]$ — a fórmula $c_r = \kappa_r \cdot p_{g(r)}$ permanece válida com a unidade física colapsada. Quando os atributos estão presentes, a decomposição é auditável por tipo físico, retrocompatível com catálogos que não distinguem taxa de consumo e preço unitário.

#### I.3.2 Grafo de sinergia e produtividade (§32 da referência)

O **grafo de sinergia** $\mathcal{G}_i = (V_i,\ A_i^{\text{syn}},\ \text{cap})$ é um dígrafo ponderado sobre os recursos da equipe:

| Elemento | Descrição |
|---|---|
| $V_i \supseteq R_i$ | nós: recursos + etapas intermediárias de produção |
| $A_i^{\text{syn}} \subseteq V_i \times V_i$ | arestas: dependências de produção (fluxo de insumo para produto) |
| $\text{cap}: A_i^{\text{syn}} \to \mathbb{R}_{>0}$ | capacidade da aresta [unid$_Q$ / unid$_{\text{tempo}}$] |
| $D \subseteq V_i$ | **domínio de produção**: subgrafo que efetivamente gera a saída $Q_i$ |
| $s_i$ | fonte virtual (insumos brutos) |
| $t_i$ | sorvedouro virtual (produto final na unidade de $Q_i$) |

**Produtividade via min-corte sobre $D$** (teorema max-fluxo / min-corte):

$$\boxed{\rho_i = \max\text{-fluxo}(s_i \to t_i,\ \mathcal{G}_i^D) = \min_{C \,\in\, \text{cortes}(s_i,t_i)} \sum_{(u,v)\in C} \text{cap}(u,v) \qquad \text{[unid}_Q\text{/h]}}$$

**Casos práticos** (topologias típicas de equipes de construção):

| Topologia | Estrutura de $\mathcal{G}_i^D$ | Fórmula fechada |
|---|---|---|
| **Série** (gargalo único) | $r_1 \to r_2 \to \cdots \to r_k$ | $\rho_i = \min_{(u,v)\,\in\,\text{caminho}} \text{cap}(u,v)$ |
| **Paralelo** (aditivo) | $s_i \rightrightarrows \{r_1,\ldots,r_k\} \rightrightarrows t_i$ | $\rho_i = \sum_{r} \text{cap}(s_i,r)$ |
| **Misto** | combinação de série e paralelo | algoritmo Ford-Fulkerson sobre $\mathcal{G}_i^D$ |

**Derivação de $\rho_i$.** Quando o grafo de sinergia $\mathcal{G}_i$ está presente no cadastro da equipe, $\rho_i$ é derivado por `producao_from_grafo(G_i)` via min-corte — o campo `producao_horaria` no artefato `Producao` funciona como cache auditável do resultado. Quando ausente, $\rho_i$ é entrada direta, calibrada externamente (ficha técnica). A calibração das capacidades $\text{cap}(\cdot)$ das arestas permanece sempre externa a este formulário; a incerteza do modelo reside nas capacidades unitárias declaradas, não na fórmula de derivação de $\rho_i$ a partir delas.

**Alocação por atividade e semana.** A eficiência que multiplica a produção de cada atividade é indexada por atividade **e** por semana:

$$\varepsilon_{ij} = \eta_{s,ij}\cdot\eta_{p,j}\cdot\eta_{w,j}$$

decompondo um fator de alocação específico da equipe $i$ ($\eta_{s,ij}$) e dois fatores de calendário global — desempenho e clima —, comuns a todas as atividades ativas na semana $j$. O fator de alocação é definido diretamente a partir do grafo de sinergia: é a razão entre a capacidade efetiva de $\mathcal{G}_i$ quando apenas $m_{ij}$ frentes (de $m_i^{\max}$ possíveis) estão mobilizadas na semana $j$, e a capacidade plena do grafo com $m_i^{\max}$ frentes:

$$\boxed{\eta_{s,ij} = \frac{\max\text{-fluxo}(s_i\to t_i,\ \mathcal{G}_i^{D}\!\mid_{m_{ij}})}{\max\text{-fluxo}(s_i\to t_i,\ \mathcal{G}_i^{D}\!\mid_{m_i^{\max}})}}$$

onde $\mathcal{G}_i^D\!\mid_m$ denota o subgrafo de produção com a capacidade das arestas de fonte escalada para $m$ frentes concorrentes. Para topologias paralelas puras (aditivas), $\eta_{s,ij}=m_{ij}/m_i^{\max}$ por linearidade das capacidades; para topologias em série ou mistas, a razão captura a degradação por gargalo interno quando múltiplas frentes disputam etapas intermediárias de capacidade fixa (ex.: uma britagem centralizada alimentando várias frentes de escavação). Quando $\mathcal{G}_i$ não está presente (produtividade calibrada externamente), adota-se $\eta_{s,ij}\equiv m_{ij}/m_i^{\max}$ como aproximação linear padrão.

### I.4 Política de mobilização $W_i$

$$W_i = (m_i^0,\ \mu_i^+,\ m_i^1,\ \mu_i^-,\ m_i^{\max}) \in \mathbb{N}_{>0}^5$$

| Símbolo | Significado |
|---|---|
| $m_i^0$ | nº de frentes na semana de início |
| $\mu_i^+$ | taxa de ramp-up [frentes/semana] |
| $m_i^{\max}$ | nº máximo de frentes concorrentes (platô) |
| $\mu_i^-$ | taxa de ramp-down [frentes/semana] |
| $m_i^1$ | nº de frentes na última semana (piso final, nunca zero) |

**Perfil trapezoidal** — mínimo de três retas, semana relativa $\tau = j - j_i^0 \in \{0,\ldots,N_i-1\}$:

$$\boxed{m_i(\tau) = \min\!\Big(m_i^0 + \mu_i^+\tau,\quad m_i^{\max},\quad m_i^1 + \mu_i^-(N_i-1-\tau)\Big)}$$

**Caso degenerado retangular** — quando $\mu_i^+ = \mu_i^- = 0$:

$$\mu_i^+ = \mu_i^- = 0 \implies m_i(\tau) = m_i^{\max} \quad \forall\,\tau \in \{0,\ldots,N_i-1\}$$

com $m_i^0 = m_i^1 = m_i^{\max}$, reduzindo $W_i$ a um único parâmetro de frota: frota constante durante toda a atividade.

$$m_{ij} = \begin{cases} m_i(j-j_i^0) & j\in[j_i^0,\,j_i^0+N_i-1] \\ 0 & \text{caso contrário}\end{cases}$$

**Determinação de $N_i$.** Para perfis não-retangulares, $N_i$ não possui fórmula fechada. A busca que a resolve não é circular: para cada duração candidata $N$, o perfil $m_i(\tau;N)$ acima é uma função de $\tau$ inteiramente determinada — nada nela depende de um $N_i$ ainda desconhecido —, de modo que a produção acumulada $\Pi(N)\equiv\sum_{\tau=0}^{N-1}\rho_i\varepsilon_{i\tau}(N)h_id_im_i(\tau;N)$ pode ser calculada exatamente para qualquer $N$ testado. O que não se conhece de antemão é apenas em qual $N$ essa soma cruza $Q_i$ — a mesma situação de qualquer grandeza definida como "o menor $N$ tal que uma condição monotônica se satisfaz", sem mistério adicional.

A validade da busca depende de $\Pi$ ser monotônica em $N$ — e essa monotonicidade precisa ser justificada com cuidado, porque $N$ aparece dentro do próprio perfil (no termo de ramp-down), de modo que aumentar $N$ não apenas acrescenta uma semana: redesenha o perfil inteiro. Ainda assim, a conclusão se sustenta. Fixado qualquer $\tau$, apenas o terceiro termo do $\min$ que define $m_i(\tau;N)$ depende de $N$, e depende de forma crescente ($m_i^1+\mu_i^-(N-1-\tau)$ cresce com $N$ quando $\mu_i^->0$); os outros dois termos ficam parados. Um mínimo em que um termo só sobe e os demais são fixos não pode diminuir, logo $m_i(\tau;N)$ é não-decrescente em $N$ para cada $\tau$ fixo — as semanas "antigas" podem crescer ao alongar o horizonte, nunca encolher. Como $\eta_{s,i\tau}$ é um max-fluxo com a capacidade de fonte escalada por $m_i(\tau;N)$ (§I.3.2), e max-fluxo é não-decrescente em qualquer capacidade de aresta, $\varepsilon_{i\tau}(N)$ herda essa monotonicidade, e portanto também cada $q_{i\tau}(N)=\rho_i\varepsilon_{i\tau}(N)h_id_im_i(\tau;N)$. Somando as $N$ semanas "antigas" (que só podem ter crescido) à semana nova — que cai exatamente no piso $m_i^1\ge1$ e contribui $\rho_i\varepsilon_{i,N}h_id_im_i^1>0$, salvo calendário morto —, obtém-se $\Pi(N+1)>\Pi(N)$: $\Pi$ é estritamente crescente a cada passo, inclusive no caso degenerado retangular, onde a semana nova sozinha já garante o aumento. Uma função inteira estritamente monotônica cruza qualquer limiar $Q_i$ em exatamente um ponto, o que garante a convergência da busca por incremento simples (Parte XIV, Fase 1) — a busca binária é uma alternativa equivalente quando o custo de reavaliação por semana for relevante.

O perfil testado em cada tentativa não precisa estar "certo" antes de $N_i$ convergir: ele é, por definição, o perfil correto para aquele $N$ testado, e é descartado assim que falha o teste de limiar — nada é reaproveitado entre tentativas. O perfil que sobra, construído em $N=N_i^\star$, é o único que os cálculos das partes seguintes utilizam: $\{m_{ij}\} \leftarrow \text{RampProfile.build}(N_i, W_i)$ é exato, sem resíduo das tentativas rejeitadas. Restrição de consistência: $r + d \le N_i$.

Um detalhe de ordem é necessário para que essa busca sequer possa consultar $\eta_{p,j}, \eta_{w,j}$ (indexados pela semana **absoluta** $j$): $j_i^0$ precisa estar definido antes de a busca por $N_i$ começar. Como $j_i^0$ (§I.5) depende apenas de atividades predecessoras — já resolvidas pela ordem topológica em que as atividades são processadas —, nunca de $N_i$ ou $\{m_{ij}\}$ da própria atividade $i$, ele pode e deve ser calculado primeiro, sem gerar dependência circular alguma com a busca que vem a seguir (Parte XIV, Fase 1).

### I.5 Predecessores e completude parcial

$$B_i \subseteq \mathcal{A}\setminus\{A_i\}, \qquad \theta_i : B_i \to (0,1]$$

Para $b\in B_i$, $\theta_i(b)$ é a fração de escopo de $b$ exigida antes que $A_i$ possa iniciar.

**Medida de completude em quantitativo:**

$$\Phi_b(j) = \frac{1}{Q_b}\sum_{j'=j_b^0}^{j} q_{b,j'}$$

**Restrição de início:**

$$\boxed{j_i^0 \;\ge\; \max_{b\in B_i}\ \min\!\{j : \Phi_b(j) \ge \theta_i(b)\}}$$

**Tipo de $\theta_i(b)$** — declarar por aresta, pois a semântica difere sob $\varepsilon_{ij}$ variável:

| Tipo | Condição de início | Formulação | Quando usar |
|---|---|---|---|
| **Q** (quantidade) | $\sum_{j'\le j} q_{b,j'} \ge \theta_i(b)\,Q_b$ | $\Phi_b(j) \ge \theta_i(b)$ | progresso físico real (defensável) |
| **T** (tempo) | $j \ge j_b^0 + \theta_i(b)\,N_b$ | fração de calendário | representação Gantt / MS Project |

Sob $\varepsilon_{ij}$ variável as duas **não coincidem**: tipo T libera o sucessor mais cedo que o fisicamente entregue quando há semanas improdutivas. Tipo Q é o adotado neste formulário — restrição exata via rastreamento da produção acumulada realizada $q_{b,j'}$ no solver, incluindo o fechamento fracionário da última semana (Parte IV). O caso $\theta_i(b)=1$ recupera a precedência fim-início clássica em ambos os tipos.

---

## Parte II — Parâmetros e Constantes Globais

Esta seção reúne constantes e faixas de valores compartilhadas por todo o projeto. Nenhuma delas é calculada a partir de outra parte do formulário — todas são definidas pelo usuário ou pela política comercial da empresa antes de o cálculo começar.

$$s_{\text{mes}} = \frac{365\times3+366}{4\times12\times7} = \frac{1461}{336} \approx 4{,}3482 \ \text{semanas/mês}$$

$s_{\text{mes}}$ converte uma taxa mensal em uma taxa semanal. Como nem todo mês tem o mesmo número de semanas, e o ano tem, em média, um pouco mais que 52 semanas por causa dos anos bissextos, usar simplesmente "4 semanas por mês" introduziria um viés sistemático ao longo do tempo. Esta constante usa a média de um ciclo de quatro anos — três anos comuns de 365 dias mais um bissexto de 366 — para obter o fator de conversão correto. É o mesmo número usado, por exemplo, para diluir o aluguel mensal de um equipamento (§I.3.1) em um custo por semana.

$$d_i \in \{4,5,6\}\ \text{dias úteis/semana}, \qquad h_i \in \{6,8\}\ \text{horas/dia}, \qquad h_id_i \equiv \text{horas/semana da equipe }i$$

$d_i$ e $h_i$ descrevem o regime de jornada de cada equipe: quantos dias por semana e quantas horas por dia ela efetivamente opera. Esses valores variam por atividade porque dependem de acordos trabalhistas, turnos e da política operacional de cada frente — uma equipe em regime de 6 dias/semana com turnos de 8 horas tem uma capacidade semanal bem diferente de uma em 4 dias/semana com turnos de 6 horas, mesmo que o custo mensal contratual seja parecido.

Taxas de BDI (entrada; valores de referência do modelo AGIS entre parênteses):

$$\beta^{EQ},\ \beta^{MO}\ (\approx29{,}97\%),\ \beta^{MAT},\ \beta^{COMB}\ (\approx4\%),\ \beta^{IND}\ (\approx25{,}21\%)$$

Os $\beta$ são as taxas de BDI (Benefícios e Despesas Indiretas) associadas a cada categoria de custo: o percentual que se soma ao custo direto para cobrir despesas administrativas, riscos e lucro. Cada categoria carrega uma taxa diferente porque a estrutura de custo indireto por trás dela é diferente — mão de obra, por exemplo, tradicionalmente carrega encargos trabalhistas e riscos de gestão de pessoal mais pesados que a simples compra de um material bruto, o que explica $\beta^{MO}$ ser muito maior que $\beta^{MAT}$ nos valores de referência.

---

## Parte III — Custo Horário de Catálogo ($\gamma$)

O custo de catálogo é o preço "de tabela" de uma equipe: quanto ela custaria por hora se operasse exatamente como planejado, sem atrasos, perdas de eficiência ou imprevistos de canteiro. É o ponto de partida antes de qualquer ajuste pela realidade da obra — as próximas partes mostram como esse valor se transforma quando a produção real entra em cena.

$$\gamma_i^{EQ} = \sum_{r\in R_i,\,\text{cat}(r)=EQ} c_r n_r \qquad \text{(análogo para } MO, MAT, COMB\text{)}$$

Somando o custo horário de cada recurso ($c_r$, calculado em §I.3.1) multiplicado por quantos desse recurso existem em uma frente ($n_r$), chega-se ao custo horário de cada categoria.

$$\gamma_i^{\mathrm{K,cat}} \equiv \gamma_i^{EQ}+\gamma_i^{MO} \qquad\text{[contratual: cobrado por semana mobilizada]}$$
$$\gamma_i^{\mathrm{V,cat}} \equiv \gamma_i^{MAT}+\gamma_i^{COMB} \qquad\text{[consumível: escala com produção]}$$
$$\gamma_i^{\mathrm{cat}} = \gamma_i^{\mathrm{K,cat}}+\gamma_i^{\mathrm{V,cat}}\qquad\text{[R\$/h]}$$

Agrupando as quatro categorias nos dois blocos de §0, chega-se ao custo horário total "de tabela" da equipe — e à divisão entre a parte que é fixa por semana (K) e a parte que varia com a produção (V).

$$f_i^{\mathrm V} = \gamma_i^{\mathrm{V,cat}}/\gamma_i^{\mathrm{cat}} \qquad\text{[fração consumível do custo de catálogo]}$$

$f_i^{\mathrm V}$ resume, num único número, o "perfil de risco" da equipe: uma equipe com $f_i^{\mathrm V}$ alto é mais sensível ao preço de combustível e material; uma equipe com $f_i^{\mathrm V}$ baixo é mais sensível a quanto tempo permanece mobilizada, independentemente do quanto produz.

$$p_i^{\mathrm{cat}} = \gamma_i^{\mathrm{cat}}/\rho_i \qquad\text{[R\$/un — preço unitário de catálogo]}$$

$$\boxed{C_i^{\mathrm{cat}} \equiv p_i^{\mathrm{cat}}\,Q_i = \frac{\gamma_i^{\mathrm{cat}}\,Q_i}{\rho_i}}\qquad\text{[R\$]}$$

$C_i^{\mathrm{cat}}$ é o custo de catálogo da atividade — base para diagnósticos e para o envelope de catálogo do projeto inteiro (Parte XIII). Dividindo o custo horário pela produção horária ($\rho_i$, §I.3.2), chega-se ao preço de tabela por unidade produzida; multiplicando pelo quantitativo total da atividade, chega-se ao custo de catálogo da atividade inteira — o número contra o qual toda ineficiência real será depois comparada.

---

## Parte IV — Cronograma Semanal

Até aqui, os custos foram tratados como se toda semana fosse igualmente produtiva. Esta seção introduz o calendário real: quantas unidades cada atividade efetivamente produz, semana a semana, considerando quantas frentes estão mobilizadas e quão eficiente é o trabalho naquela semana específica.

Eficiência semanal por atividade: $\varepsilon_{ij} = \eta_{s,ij}\cdot\eta_{p,j}\cdot\eta_{w,j}\in[0,1]$ (§30 da referência; $\eta_{s,ij}$ conforme §I.3.2).

$$q_{ij} = \rho_i\,\varepsilon_{ij}\,h_id_i\,m_{ij}\qquad\text{[un] — semanas interiores}$$

**Fechamento exato de escopo.** Seja $j_i^1 \equiv j_i^0+N_i-1$ a última semana ativa de $A_i$, obtida pela busca monotônica em $N_i$ (Parte XIV, Fase 1) sobre o perfil nominal $\{m_i(\tau)\}$ de $W_i$. Nas semanas interiores $j<j_i^1$, a produção usa o perfil nominal integralmente. Na última semana, o quantitativo residual fecha exatamente o escopo:

$$q_{i,j_i^1} = Q_i - \sum_{j=j_i^0}^{j_i^1-1} q_{ij}$$

Por construção da busca monotônica ($N_i$ é o menor inteiro tal que a produção acumulada nominal atinge $Q_i$, e a semana adicionada mais recentemente é a primeira em que isso ocorre), o residual satisfaz $0 < q_{i,j_i^1} \le \rho_i\varepsilon_{i,j_i^1}h_id_im_i(N_i-1)$ — nunca excede a produção nominal da última semana, e a semana de fechamento sempre tem $\varepsilon_{i,j_i^1}>0$ (uma semana com $\varepsilon=0$ não altera a produção acumulada, de modo que a busca automaticamente avança para a semana seguinte). Define-se a **fração de fechamento**:

$$\varphi_i \equiv \frac{q_{i,j_i^1}}{\rho_i\,\varepsilon_{i,j_i^1}\,h_id_i\,m_i(N_i-1)} \in (0,1]$$

representando a fração da capacidade nominal da última semana efetivamente utilizada para completar o escopo. A frota mobilizada ($m_{ij}$, e portanto o custo contratual $C_{ij}^{\mathrm{K,op}}$, Parte V) permanece no valor nominal do perfil na última semana — recursos contratuais (EQ/MO) são cobrados pela semana mobilizada independentemente da fração de produção efetivamente necessária naquela semana (§0). Apenas o consumível é prorateado pela produção realizada, via $\varphi_i$, garantindo o fecho exato do escopo:

$$\sum_{j=j_i^0}^{j_i^1} q_{ij} = Q_i \qquad\text{(exato, por construção)}$$

Contadores: $M_i \equiv \sum_j m_{ij}$ (frente-semanas totais, ao valor nominal — inclui a última semana integralmente), $N_i = |\{j:m_{ij}>0\}|$ (semanas de calendário ativas).

$$\mathcal{A}_j \coloneqq \{A_i\in\mathcal{A} : j\in[j_i^0,\,j_i^0+N_i-1]\}$$

---

## Parte V — Custo Direto Semanal (sem BDI)

Esta seção converte os quantitativos semanais da Parte IV em valores monetários, separando o que é cobrado independentemente da produção (o bloco contratual, K) do que acompanha exatamente o que foi produzido (o bloco consumível, V) — a mesma distinção introduzida em §0.

$$C_{ij}^{\mathrm{K,op}} = \gamma_i^{\mathrm{K,cat}}\,h_id_i\,m_{ij}\qquad\text{[R\$] — nominal em toda semana ativa, inclusive a última}$$

$C_{ij}^{\mathrm{K,op}}$ é o custo contratual da semana: o valor pago pelas frentes mobilizadas, que depende apenas do regime de jornada e de quantas frentes estão em campo — não de quanto foi produzido. É como alugar um equipamento por semana: o valor é o mesmo, tenha a equipe produzido muito ou pouco naquela semana.

$$C_{ij}^{\mathrm{V,op}} = \gamma_i^{\mathrm{V,cat}}\cdot\frac{q_{ij}}{\rho_i}\qquad\text{[R\$]}$$

$C_{ij}^{\mathrm{V,op}}$ é o custo consumível da semana: proporcional ao quanto foi de fato produzido ($q_{ij}$), e por isso já incorpora, de forma implícita, tanto a eficiência da semana quanto o fechamento fracionário da última semana (Parte IV). É como pagar por combustível: quanto mais se produz, mais se consome, e vice-versa.

Nas semanas interiores, $q_{ij}/\rho_i \equiv \varepsilon_{ij}h_id_im_{ij}$ por definição de $q_{ij}$ (Parte IV) — a formulação acima generaliza a forma tempo-a-tempo e permanece exata na semana de fechamento, onde $q_{ij}$ é o residual e não $\varepsilon_{ij}h_id_im_{ij}$ diretamente.

$$C_{ij}^{\mathrm{op}} = C_{ij}^{\mathrm{K,op}}+C_{ij}^{\mathrm{V,op}}\qquad\text{[R\$]}$$

Somando os dois blocos, chega-se ao custo direto daquela semana específica — a peça básica a partir da qual todos os totais das próximas partes são construídos.

---

## Parte VI — Custo Direto Total por Atividade (sem BDI)

Somando os custos semanais da Parte V ao longo de toda a duração da atividade, chega-se ao seu custo direto total — e a uma das identidades mais úteis deste formulário, detalhada logo abaixo.

$$C_i^{\mathrm{K,cat}} = \frac{Q_i\,\gamma_i^{\mathrm{K,cat}}}{\rho_i}\qquad\text{[R\$] — catálogo, parcela contratual, à eficiência nominal}$$
$$C_i^{\mathrm{V,cat}} = \frac{Q_i\,\gamma_i^{\mathrm{V,cat}}}{\rho_i}\qquad\text{[R\$] — catálogo, parcela consumível}$$
$$C_i^{\mathrm{K,op}} = \sum_{j} C_{ij}^{\mathrm{K,op}} = \gamma_i^{\mathrm{K,cat}}\,h_id_i\,M_i\qquad\text{[R\$]}$$
$$C_i^{\mathrm{V,op}} = \sum_{j} C_{ij}^{\mathrm{V,op}} = \frac{\gamma_i^{\mathrm{V,cat}}}{\rho_i}\sum_j q_{ij}\qquad\text{[R\$]}$$
$$C_i^{\mathrm{op}} = C_i^{\mathrm{K,op}}+C_i^{\mathrm{V,op}}\qquad\text{[R\$]}$$
$$p_i^{\mathrm{op}} = C_i^{\mathrm{op}}/Q_i\qquad\text{[R\$/un]}$$

**Identidade — invariância do consumível.** Usando o fecho de escopo exato $\sum_jq_{ij}=Q_i$ (Parte IV):

$$\boxed{C_i^{\mathrm{V,op}} \equiv C_i^{\mathrm{V,cat}} = \frac{Q_i\,\gamma_i^{\mathrm{V,cat}}}{\rho_i}}\qquad\text{(exato, por construção do fechamento de escopo)}$$

O consumível operacional **é** o consumível de catálogo — não há inflação por ineficiência. O total de material/combustível depende apenas de $Q_i$, nunca de quantas semanas foram necessárias para executar. Esta identidade **não vale** para o contratual: $C_i^{\mathrm{K,op}}=\gamma_i^{\mathrm{K,cat}}h_id_iM_i$ cresce quando a eficiência piora (mais frente-semanas $M_i$ para fechar o mesmo $Q_i$, já que $M_i$ conta a semana de fechamento integralmente, não prorateada).

**Desvio de catálogo por atividade.** Comparando $C_i^{\mathrm{op}}$ com $C_i^{\mathrm{cat}}$ (Parte III), obtém-se uma leitura de quanto a atividade se desviou do plano de catálogo — em termos relativos e absolutos:

$$R_i \equiv \frac{C_i^{\mathrm{op}}}{C_i^{\mathrm{cat}}} \qquad\qquad \boxed{\Delta_i^{\mathrm{cat}} \equiv C_i^{\mathrm{op}}-C_i^{\mathrm{cat}} = (R_i-1)\,C_i^{\mathrm{cat}}}\qquad\text{[R\$]}$$

$\Delta_i^{\mathrm{cat}}>0$ significa que a atividade custou mais do que o catálogo previa; $\Delta_i^{\mathrm{cat}}<0$, que custou menos. $R_i$ é a mesma leitura em forma adimensional, mais direta para comparar o grau de desvio entre atividades de portes diferentes — é o análogo, em nível de atividade, do $R=C^{\mathrm{tot}}/C^{\mathrm{cat}}$ de projeto (Parte XIII). Sua forma fechada, em função da eficiência média realizada, é dada na Parte VIII, logo após $\bar\varepsilon_i$ ser definida com exatidão.

Uma advertência sobre como (não) recalcular esse desvio sob uma produtividade revisada — por exemplo, ao incorporar um $\rho_i$ observado em campo, diferente do calibrado originalmente: a identidade $C_i^{\mathrm{V,op}}\equiv\gamma_i^{\mathrm{V,cat}}Q_i/\rho_i$ (acima) é, por construção, invariante ao cronograma, então substituir $\rho_i$ por um $\rho_i'$ revisado nessa fórmula sozinha ainda produz um número correto. Mas $C_i^{\mathrm{K,op}}=\gamma_i^{\mathrm{K,cat}}h_id_iM_i$ depende de $M_i$, resultado da busca por $N_i$ (Parte XIV, Fase 1) *sob o $\rho_i$ original*. Trocar $\rho_i$ por $\rho_i'$ nas fórmulas de custo sem refazer essa busca deixa $M_i$ preso a um cronograma que, sob a nova produtividade, não fecha mais o escopo $Q_i$ (Parte IV) — o modelo estaria implicitamente descrevendo uma atividade que produz uma quantidade diferente de $Q_i$. Recalcular $\Delta_i^{\mathrm{cat}}$ sob produtividade revisada exige rederivar $N_i$, $\{m_{ij}\}$ e $\varphi_i$ a partir de $\rho_i'$ (Fases 0–3), não apenas substituir $\rho_i$ nas fórmulas de custo mantendo o cronograma antigo.

---

## Parte VII — Razões Operacional/Catálogo (semanais)

As razões desta seção comparam o que a atividade realmente custou e produziu em uma dada semana com o que o catálogo previa — funcionam como um termômetro semanal de quão perto (ou longe) a operação ficou do planejado.

Custo semanal de catálogo (pool e consumível à taxa nominal, sem desconto de $\varepsilon_{ij}$):

$$C_{ij}^{\mathrm{cat}} = \gamma_i^{\mathrm{cat}}\,h_id_i\,m_{ij}\qquad\text{[R\$]}$$

Preço unitário operacional semanal:

$$p_{ij}^{\mathrm{op}} = C_{ij}^{\mathrm{op}}/q_{ij}\qquad\text{[R\$/un]}$$

Razões:

$$\zeta_{ij} = \frac{C_{ij}^{\mathrm{op}}}{C_{ij}^{\mathrm{cat}}} = \frac{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{cat}}}\qquad[\ ]$$

$$\pi_{ij} = \frac{p_{ij}^{\mathrm{op}}}{p_i^{\mathrm{cat}}} = \frac{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}}{\varepsilon_{ij}\,\gamma_i^{\mathrm{cat}}}\qquad[\ ]$$

$$\boxed{\zeta_{ij} = \varepsilon_{ij}\cdot\pi_{ij}}$$

Em palavras simples: $\zeta_{ij}$ compara custos totais — quanto se gastou frente ao previsto —, enquanto $\pi_{ij}$ compara preços unitários — quanto custou cada unidade produzida frente ao preço de tabela. Como uma semana ineficiente ainda paga o custo contratual cheio mas produz menos, $\pi_{ij}$ tende a subir quando $\varepsilon_{ij}$ cai: produzir menos encarece cada unidade entregue.

Usando a fração consumível $f_i^{\mathrm V}$ (Parte III):

$$\zeta_{ij} = 1-(1-\varepsilon_{ij})\,f_i^{\mathrm V}, \qquad \pi_{ij} = \frac{1}{\varepsilon_{ij}}-\left(\frac{1}{\varepsilon_{ij}}-1\right)f_i^{\mathrm V}$$

$\zeta_{ij}$ é diagnóstico local por semana — não deve ser somado ingenuamente para recuperar um "$\zeta_i$" de atividade.

---

## Parte VIII — Camada BDI (direta, por atividade)

Esta seção aplica as taxas de BDI da Parte II sobre os custos de catálogo e operacionais já calculados, chegando ao custo de cada atividade como ele efetivamente entra na proposta comercial — e a um BDI equivalente por atividade, que varia semana a semana conforme muda a mistura entre custo contratual e consumível.

$$\gamma_i^{\mathrm{K,cat},\beta} = (1+\beta^{\mathrm{EQ}})\gamma_i^{\mathrm{EQ}}+(1+\beta^{\mathrm{MO}})\gamma_i^{\mathrm{MO}}$$
$$\gamma_i^{\mathrm{V,cat},\beta} = (1+\beta^{\mathrm{MAT}})\gamma_i^{\mathrm{MAT}}+(1+\beta^{\mathrm{COMB}})\gamma_i^{\mathrm{COMB}}$$
$$\gamma_i^{\mathrm{cat},\beta} = \gamma_i^{\mathrm{K,cat},\beta}+\gamma_i^{\mathrm{V,cat},\beta}$$

$$C_{ij}^{\mathrm{K,op},\beta} = \gamma_i^{\mathrm{K,cat},\beta}\,h_id_i\,m_{ij}$$
$$C_{ij}^{\mathrm{V,op},\beta} = \gamma_i^{\mathrm{V,cat},\beta}\cdot\frac{q_{ij}}{\rho_i}$$
$$C_{ij}^{\mathrm{op},\beta} = C_{ij}^{\mathrm{K,op},\beta}+C_{ij}^{\mathrm{V,op},\beta}$$

**Taxas ponderadas por pool.** O BDI equivalente de cada bloco (K e V) é a média de $\beta$ das suas categorias, ponderada pela composição de custo de catálogo da equipe:

$$\beta_i^{\mathrm K} \equiv \frac{\gamma_i^{\mathrm{EQ}}\beta^{\mathrm{EQ}}+\gamma_i^{\mathrm{MO}}\beta^{\mathrm{MO}}}{\gamma_i^{\mathrm{K,cat}}}, \qquad \beta_i^{\mathrm V} \equiv \frac{\gamma_i^{\mathrm{MAT}}\beta^{\mathrm{MAT}}+\gamma_i^{\mathrm{COMB}}\beta^{\mathrm{COMB}}}{\gamma_i^{\mathrm{V,cat}}}$$

de modo que, por construção, $\gamma_i^{\mathrm{K,cat},\beta}=\gamma_i^{\mathrm{K,cat}}(1+\beta_i^{\mathrm K})$ e $\gamma_i^{\mathrm{V,cat},\beta}=\gamma_i^{\mathrm{V,cat}}(1+\beta_i^{\mathrm V})$.

Fração consumível efetiva da semana $j$:

$$\delta_{ij} \equiv \frac{\varepsilon_{ij}\,\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\,\gamma_i^{\mathrm{V,cat}}}$$

$$\boxed{\beta_{ij} = (1-\delta_{ij})\,\beta_i^{\mathrm K} + \delta_{ij}\,\beta_i^{\mathrm V}}$$

Decrescente em $\varepsilon_{ij}$ sempre que $\beta_i^{\mathrm V}<\beta_i^{\mathrm K}$ (caso típico, dado $\beta^{MAT},\beta^{COMB}\ll\beta^{EQ},\beta^{MO}$ nos valores de referência): maior eficiência aloca mais custo ao bloco consumível, de BDI mais baixo, reduzindo o BDI equivalente semanal.

**Totais por atividade:**

$$C_i^{\mathrm{K,op},\beta} = \gamma_i^{\mathrm{K,cat},\beta}\,h_id_i\,M_i \qquad C_i^{\mathrm{V,op},\beta} = \gamma_i^{\mathrm{V,cat},\beta}\cdot\frac{Q_i}{\rho_i}$$

$$C_i^{D,\beta} \equiv C_i^{\mathrm{K,op},\beta}+C_i^{\mathrm{V,op},\beta} \qquad\text{[R\$] — total direto da atividade com BDI}$$

**Eficiência média ponderada por frente-semana** — agrega o efeito de $\varepsilon_{ij}$ ao longo de toda a atividade em um único fator. Definida diretamente a partir do fecho de escopo exato (Parte IV), a agregação vale mesmo com o fechamento fracionário da última semana:

$$\bar\varepsilon_i \equiv \frac{Q_i}{\rho_i\,h_id_i\,M_i}$$

Fora da semana de fechamento, isso equivale à soma $\sum_j\varepsilon_{ij}m_{ij}/M_i$ termo a termo; na semana de fechamento, o termo correspondente entra como $\varphi_i\varepsilon_{i,j_i^1}m_{i,j_i^1}$ em vez de $\varepsilon_{i,j_i^1}m_{i,j_i^1}$ — a fração de fechamento $\varphi_i$ (Parte IV) é exatamente essa correção, de modo que a definição acima já a incorpora, sem tratamento à parte.

$$\delta_i = \frac{\bar\varepsilon_i\,\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{K,cat}}+\bar\varepsilon_i\,\gamma_i^{\mathrm{V,cat}}} \;\left(=\frac{C_i^{\mathrm{V,op}}}{C_i^{\mathrm{op}}}\text{, exato}\right)$$

$$\boxed{\beta_i^{\mathrm{eq}} \equiv \frac{C_i^{D,\beta}}{C_i^{\mathrm{op}}}-1 = (1-\delta_i)\,\beta_i^{\mathrm K}+\delta_i\,\beta_i^{\mathrm V}}$$

Com $\bar\varepsilon_i$ exato, o desvio de catálogo por atividade $R_i\equiv C_i^{\mathrm{op}}/C_i^{\mathrm{cat}}$ (Parte VI) também ganha forma fechada:

$$\boxed{R_i = f_i^{\mathrm V} + \frac{1-f_i^{\mathrm V}}{\bar\varepsilon_i}}$$

$R_i=1$ exatamente quando $\bar\varepsilon_i=1$: todo o desvio de catálogo nasce da diferença entre a eficiência média realizada e a eficiência nominal de catálogo — nunca da composição K/V da equipe isoladamente.

---

## Parte IX — Pool de Recursos Contratuais (Perpetuação)

Até aqui, cada atividade foi tratada isoladamente. Na prática, porém, o mesmo equipamento ou a mesma equipe frequentemente passa de uma atividade para outra sem ser desmobilizado, evitando o custo e o tempo de tirá-lo do canteiro e trazê-lo de volta depois. Esta seção trata desse aproveitamento entre atividades: quando vale a pena manter um recurso parado por alguns dias esperando a próxima frente de trabalho, e quando é mais barato desmobilizar e remobilizar.

### IX.1 Tipos, instâncias e demanda semanal

$\mathcal{T}$ = conjunto de tipos de recurso (união de categorias e especificação sobre todos os $R_i$).

**Demanda semanal por tipo:**

$$n_j(\tau) = \sum_{i\,:\,j\in[j_i^0,\,j_i^0+N_i-1]} m_{ij}\cdot n_{\tau}^{i}$$

**Pool físico** $\{r\}$: conjunto de instâncias com $\text{type}(r)\in\mathcal{T}$, taxa semanal $c_r^{\text{sem}}$ (igual em semanas ativas e ociosas — §IX.3), e custos $c_r^{\text{mob}}$, $c_r^{\text{demob}}$.

$$qt_\tau = \max_j n_j(\tau) \qquad\text{[tamanho do pool de tipo }\tau\text{]}$$

### IX.2 Problema de minimização e condição de perpetuação

$$\min_{\{r\},\{[j_r^0,j_r^1]\}} \ \underbrace{\sum_r\sum_{j=j_r^0}^{j_r^1} c_r^{\text{ativo/standby}}(j)}_{\text{permanência}} + \underbrace{\sum_r (c_r^{\text{mob}}+c_r^{\text{demob}})}_{\text{mob/demob}}$$

$$\text{s.a.}\quad \bigl|\{r:\text{type}(r)=\tau,\ j\in[j_r^0,j_r^1]\}\bigr| \ge n_j(\tau) \quad\forall j,\,\forall\tau$$

Para tipo único fungível (instâncias perfeitamente substituíveis, com custo de permanência e de mob/demob homogêneos), a Parte XIV (Fase 4) apresenta um algoritmo exato por decomposição em níveis do perfil de demanda.

**Condição de perpetuação** (entre duas alocações consecutivas, com gap em semanas):

$$\text{gap}_{uv} < G_r^* \equiv \frac{c_r^{\text{mob}}+c_r^{\text{demob}}}{c_r^{\text{sem}}} \quad\Longleftrightarrow\quad c_r^{\text{mob}}+c_r^{\text{demob}} > c_r^{\text{sem}}\cdot\text{gap}_{uv}\qquad\text{[$c_r^{\text{sem}}$ em R\$/sem]}$$

**Cap absoluto:** $\text{gap}_{uv} > G_r^{\text{viável}} \Rightarrow$ não perpetuar, independente de custo.

**Estrutura de cadeia** $\mathcal{C}_p = (i_1 \to i_2 \to \cdots \to i_{n_p})$: cada par consecutivo $(i_k, i_{k+1})$ satisfaz o critério. Uma cadeia gera **um** par $(c_r^{\text{mob}}, c_r^{\text{demob}})$ mais standby nos gaps internos.

### IX.3 Frações invariantes por recurso

Como o custo dos recursos contratuais é definido a partir do **tempo de permanência** ($c_r^{\text{sem}}$ por semana ativa, $c_r^{\text{standby}}$ por semana de gap), a separação em fração ativa e fração standby é um **invariante temporal** de cada instância — completamente determinado pela cadeia de perpetuação, sem dependência de parâmetros de custo.

Para cada instância $r$ com cadeia $\mathcal{C}_p = (i_1 \to \cdots \to i_{n_p})$:

$$T_r^{\text{ativo}} = \sum_{k=1}^{n_p} N_{i_k} \qquad\text{[semanas produtivas]}$$

$$T_r^{\text{standby}} = \sum_{k=1}^{n_p-1} \text{gap}_{i_k,i_{k+1}} \qquad\text{[semanas de standby interno]}$$

$$T_r^{\text{perm}} = T_r^{\text{ativo}} + T_r^{\text{standby}} \qquad\text{[total de semanas de permanência]}$$

$$\boxed{f_r^{\text{standby}} = \frac{T_r^{\text{standby}}}{T_r^{\text{perm}}} \in [0,1), \qquad f_r^{\text{ativo}} = 1 - f_r^{\text{standby}}}$$

**Propriedade invariante:** dados o schedule $\{(j_i^0, N_i)\}$ e as cadeias de perpetuação, $f_r^{\text{standby}}$ é completamente determinado. Não depende de $c_r^{\text{sem}}$, $c_r^{\text{standby}}$, $c_r^{\text{mob}}$ nem $c_r^{\text{demob}}$ — é uma grandeza puramente temporal, intrínseca ao padrão de implantação do recurso.

**Casos:**

| Situação | $f_r^{\text{standby}}$ |
|---|---|
| Cadeia singleton ($n_p=1$, sem perpetuação) | $0$ |
| Perpetuação com gaps pequenos | $\in(0,1)$, próximo de 0 quando atividades são densas |
| Recurso em standby quase todo tempo | $\to 1$ (não deve ocorrer: perpetuação só é racional quando gap $< G_r^*$) |

**Taxa efetiva semanal.** A separação pool/estoque implica $c_r^{\text{standby}} = c_r^{\text{sem}}$: EQ (aluguel) e MO (salário + CLT) custam igual em semanas ativas e ociosas — os consumíveis, que escalariam com produção, já foram segregados em $C^{\text{estoque}}$. Portanto:

$$\boxed{\bar{c}_r = c_r^{\text{sem}} \qquad \text{(pool puro: standby = ativo)}}$$

A fração $f_r^{\text{standby}}$ é **diagnóstico temporal** puro — não afeta o custo, quantifica o grau de ociosidade da instância. O benefício da perpetuação é exclusivamente a redução de $C^{MOB,eq,o}$ (mob/demob evitados), ao custo de semanas adicionais de permanência a $c_r^{\text{sem}}$.

### IX.4 Custo do pool

$$\boxed{C^{\text{pool},o} = \sum_r T_r^{\text{perm}} \cdot c_r^{\text{sem}}}$$

$$C^{\text{pool},\beta} = \sum_r (1+\beta_{\text{cat}(r)})\cdot T_r^{\text{perm}}\cdot c_r^{\text{sem}}$$

**Custo indireto de mob/demob do pool** (por cadeia, com $\beta^{IND}$):

$$C^{MOB,eq,o} = \sum_r N_{\text{chains}}^r \cdot (c_r^{\text{mob}}+c_r^{\text{demob}}), \qquad C^{MOB,eq,\beta} = (1+\beta^{IND})\cdot C^{MOB,eq,o}$$

**Reconciliação com a Parte VI:**

$$\boxed{C^{\mathrm{pool}} \;\ge\; \sum_i C_i^{\mathrm{K,op}}}$$

com igualdade apenas se nenhum recurso é perpetuado entre atividades distintas e $f_r^{\text{standby}}=0\ \forall r$: a soma por atividade conta apenas semanas ativas ($M_i$), enquanto $C^{\mathrm{pool}}=\sum_rT_r^{\text{perm}}c_r^{\text{sem}}$ inclui também as semanas de standby interno das cadeias perpetuadas ($T_r^{\text{standby}}$) — custo real de permanência sem contrapartida de produção. $C_i^{\mathrm{K,op}}$ permanece grandeza de diagnóstico por atividade (quanto cada atividade consumiria de recurso contratual se operasse isoladamente); o desembolso contratual real do projeto — incluindo o custo de manter recursos parados entre mobilizações — é $C^{\mathrm{pool}}$.

**Escopo do algoritmo de dimensionamento.** A decomposição por níveis empregada na Parte XIV, Fase 4 é exata para um tipo de recurso fungível homogêneo — instâncias perfeitamente substituíveis entre si, com custo de permanência e de mobilização/desmobilização idênticos. Variantes multi-tipo com recursos não perfeitamente substituíveis (capacidades ou custos heterogêneos dentro do mesmo tipo nominal) constituem um problema de otimização combinatória distinto, de complexidade superior à do caso fungível (cf. Bertossi, Carraresi & Gallo 1987); nesses casos, os tipos devem ser subdivididos em subtipos homogêneos antes de aplicar o algoritmo desta seção.

---

## Parte X — Consumíveis: Aquisição, Demanda e Reposição

Consumíveis passam por três contas diferentes, ligadas por uma cadeia de derivação: quanto custou comprar o material ou combustível efetivamente usado na produção (aquisição, direto), quanto foi fisicamente consumido semana a semana (demanda física, derivada do cronograma) e quanto custa manter estoque parado no canteiro entre a compra e o consumo (posse, indireto) — esta última agora resultado de uma política de reposição ótima, não um dado externo solto, em consistência com o restante do formulário: a Parte IX, por exemplo, não aceita "quantas instâncias de recurso contratual existem" como dado solto — deriva isso de uma condição de perpetuação aplicada sobre a demanda semanal já calculada. O mesmo tratamento vale para consumíveis.

### X.1 Aquisição

Separável por atividade sem ambiguidade. Por identidade direta $C_i^{\mathrm{V,op}} \equiv C_i^{\mathrm{V,cat}}$ (Parte VI):

$$\boxed{C^{\mathrm{cons}} = \sum_{i\in\mathcal{A}} \frac{Q_i\,\gamma_i^{\mathrm{V,cat}}}{\rho_i} = \sum_g c_g^{\mathrm{cons}}\, U_g}\qquad\text{[R\$ — direto, entra em $C^D$]}$$

$$C^{\mathrm{cons},\beta} = \sum_{i\in\mathcal{A}} \gamma_i^{\mathrm{V,cat},\beta}\cdot\frac{Q_i}{\rho_i}$$

Diferente do contratual, $C^{\mathrm{cons}}$ não requer otimização de cadeias — a soma por atividade é exata, e coincide exatamente com a produção realizada dado o fechamento de escopo da Parte IV. $U_g$ (unidades físicas do bem $g$ usadas no projeto inteiro) é recuperado com exatidão em §X.2, não apenas como total agregado.

### X.2 Demanda física derivada

O restante desta parte deriva $U_g$ semana a semana — necessário para qualquer decisão de quando comprar, não apenas quanto. Para cada atividade $i$ e bem físico $g$, a **taxa de consumo agregada** do bem $g$ por hora-equivalente de $i$ soma os recursos consumíveis de $R_i$ que consomem $g$ (§I.3.1) — mesmo dado de cadastro que já alimenta $\gamma_i^{\mathrm{V,cat}}$ (Parte III), nenhum insumo novo:

$$\kappa_i^g \equiv \sum_{r\in R_i\,:\,g(r)=g} n_r\,\kappa_r \qquad [\text{unid}_g/\text{h}]$$

Usando a mesma razão $q_{ij}/\rho_i$ que torna $C_{ij}^{\mathrm{V,op}}$ exata inclusive na semana de fechamento (Parte V) — ela já generaliza corretamente "horas efetivas" nas semanas interiores e no residual —, o consumo físico de $g$ pela atividade $i$ na semana $j$ segue a mesma construção, só trocando a taxa monetária pela taxa física:

$$\boxed{D_{g,ij} = \kappa_i^g\cdot\frac{q_{ij}}{\rho_i}}\qquad[\text{unid}_g] \qquad\qquad \boxed{D_{g,j} = \sum_{i\,\in\,\mathcal{A}_j} D_{g,ij}}\qquad[\text{unid}_g]$$

com $\mathcal{A}_j$ o conjunto de atividades ativas na semana $j$ (Parte IV). Nenhum cálculo novo além de agregação: $q_{ij}$ e $\rho_i$ já são saída da Fase 3.

**Identidade de consistência.** Somando sobre toda a vida do projeto e usando o fecho de escopo exato $\sum_jq_{ij}=Q_i$:

$$\sum_j D_{g,j} = \sum_i\kappa_i^g\cdot\frac{Q_i}{\rho_i} \equiv U_g$$

recuperando exatamente o $U_g$ de §X.1 — a demanda física total já era implicitamente conhecida pelo formulário original; faltava sua distribuição semana a semana.

### X.3 Balanço de estoque

Seja $X_{g,j}\ge0$ a quantidade pedida do bem $g$ na semana $j$, e $L_g\ge0$ seu lead time de entrega (semanas, cadastral). A quantidade recebida na semana $j$ é $O_{g,j}=X_{g,j-L_g}$, e a trajetória de estoque satisfaz o balanço padrão:

$$\boxed{S_{g,j} = S_{g,j-1}+O_{g,j}-D_{g,j}}\qquad\text{s.a.}\quad S_{g,j}\ge0\ \ \forall j$$

com $S_{g,j_{\min}-1}=S_g^0$ (tipicamente $0$, salvo estoque de mobilização declarado à parte). A restrição $S_{g,j}\ge0$ é a condição de **não-ruptura**: nenhuma semana consome mais do que já chegou. Esta recursão conecta $D_{g,j}$ (§X.2, já derivado) à decisão de compra $X_{g,j}$ (§X.4, a otimizar), produzindo $S_{g,j}$ como saída — não mais como dado de entrada.

### X.4 Política ótima de reposição (Wagner–Whitin)

$D_{g,j}$ é, por construção, não estacionária (perfis trapezoidais de mobilização, atividades sobrepostas com datas distintas) e inteiramente conhecida de antemão, já determinada na Fase 1 — não é problema de previsão sob incerteza, mas de lot-sizing determinístico, com solução exata por programação dinâmica (Wagner & Whitin, 1958). O problema decompõe por bem $g$, isoladamente — mesma lógica de decomposição do dimensionamento de pool (Parte IX/Fase 4), sem restrição de capital compartilhado:

$$\min_{\{X_{g,j}\ge0\}}\ \sum_j\Big[c_g^{\text{ped}}\cdot\mathbb{1}[X_{g,j}>0]+c_g^{\text{hold}}\,S_{g,j}\Big]\qquad\text{s.a. balanço de §X.3},\ S_{g,j}\ge0$$

onde $c_g^{\text{ped}}$ é o custo fixo de colocar um pedido (frete, mínimo de fatura, administração de compra) — cadastral por bem, análogo em papel a $c_r^{\text{mob}}+c_r^{\text{demob}}$ da Parte IX.

**Propriedade de estoque zero.** Existe solução ótima em que todo pedido chega com estoque zero — nunca é ótimo pedir enquanto ainda há saldo positivo (resultado clássico de Wagner–Whitin). O horizonte de demanda particiona-se em lotes consecutivos $[a,b]$: um único pedido, colocado na semana $a-L_g$, cobre a demanda de $a$ até $b$. O estoque ao final da semana $j\in[a,b]$ é o saldo ainda não consumido dentro do lote, $S_{g,j}=\sum_{k=j+1}^bD_{g,k}$; somando o custo de posse ao longo do lote, cada $D_{g,k}$ contribui $(k-a)$ vezes (uma semana para cada $j<k$ em que ainda estava em estoque):

$$\boxed{\mathrm{Custo}(a,b) = c_g^{\text{ped}} + c_g^{\text{hold}}\sum_{k=a+1}^{b}(k-a)\,D_{g,k}}$$

computável exatamente para qualquer $(a,b)$ candidato, sem depender de lotes vizinhos — mesma lógica de "cada tentativa é recalculada do zero, sem resíduo" já usada na busca de $N_i$ (§I.4).

**Recursão.** Seja $[j_{\min}^g,j_{\max}^g]$ o intervalo de semanas com $D_{g,j}>0$, e $f(j_{\min}^g-1)\equiv0$:

$$\boxed{f(b) = \min_{a\,\in\,[j_{\min}^g,\,b]}\big[f(a-1)+\mathrm{Custo}(a,b)\big]}$$

O custo ótimo de reposição de $g$ é $f(j_{\max}^g)$; a partição ótima em lotes — logo as semanas de pedido e $X_{g,a-L_g}=\sum_{k=a}^bD_{g,k}$ — é recuperada por backtracking do argumento minimizador em cada passo. Complexidade $O(n^2)$ no número de semanas com demanda; refinamento $O(n\log n)$ existe via teorema do horizonte de planejamento (Wagelmans, Van Hoesel & Kolen, 1992), desnecessário na escala típica de um cronograma de obra. O lead time $L_g$ não altera a estrutura — apenas desloca cada semana de pedido $a$ para $a-L_g$; se isso cai antes do início do cronograma, sinaliza necessidade de pedido de pré-mobilização (verificado em §XIV.9).

Como o preço $p_{g(r)}$ permanece constante (sem desconto por volume, §X.6), o custo de **aquisição** $C^{\mathrm{cons}}$ (§X.1) é inalterado pela política de lotes — depende só de $U_g$, invariante ao cronograma. A política de reposição determina exclusivamente a repartição do custo de **posse** e introduz o custo de **pedido**, nunca o total de material comprado.

### X.5 Custo de posse, custo de pedido e atualização do indireto

O custo de posse passa a ser saída da otimização, não soma sobre $S_{g,j}$ dado:

$$\boxed{C^{\mathrm{inv}} = \sum_g\Big(f(j_{\max}^g)-n_g^{\text{ped}}\cdot c_g^{\text{ped}}\Big)}\qquad\text{[R\$ — indireto, com $\beta^{\mathrm{IND}}$]}$$

com $n_g^{\text{ped}}$ o número de lotes (pedidos) na partição ótima de $g$ — subtrair seu custo de $f(j_{\max}^g)$ isola exatamente a parcela de posse. O custo de pedidos ganha categoria própria — é logística de suprimento, não posse, e carrega $\beta^{\mathrm{IND}}$ pela mesma razão que $C^{MOB,eq}$ (Parte XII.5):

$$\boxed{C^{\mathrm{PED}} = \sum_g n_g^{\text{ped}}\cdot c_g^{\text{ped}}}\qquad\qquad C^{\mathrm{PED},\beta} = (1+\beta^{\mathrm{IND}})\cdot C^{\mathrm{PED}}$$

Os totais do indireto (Parte XII.6) passam a incluir esse termo:

$$C^I = \sum_{l\in\mathcal{L}} C_l^{I,o} + C^{MOB,eq,o} + C^{\mathrm{PED}} + C^{\mathrm{inv}}$$
$$C^{I,\beta} = \sum_{l\in\mathcal{L}} C_l^{I,\beta} + C^{MOB,eq,\beta} + C^{\mathrm{PED},\beta} + C^{\mathrm{inv}}\,(1+\beta^{\mathrm{IND}})$$

Nenhuma outra parte do formulário muda: $C^D$, $C^{\mathrm{cat}}$, $\mathrm{BDI}$, $R$ mantêm suas fórmulas originais (Partes XI e XIII), apenas com $C^I$ recomputado.

### X.6 Escopo

Ficam fora deste formulário, como extensões independentes: decomposição de $c_g^{\text{hold}}$ em capital/armazenagem/risco; desconto por volume de compra ($p_g$ permanece constante — introduzi-lo trocaria $\mathrm{Custo}(a,b)$ por uma função não necessariamente separável, exigindo variante do Wagner–Whitin com custo marginal decrescente); estoque de segurança sob incerteza (a formulação é inteiramente determinística, coerente com $D_{g,j}$ já ser conhecida a partir do cronograma resolvido — introduzir variância exigiria propagar incerteza de $\eta_{p,j},\eta_{w,j}$ até $D_{g,j}$, adendo de natureza distinta); e perecibilidade/validade de lote. Cada um é tratável como extensão adicional sobre a base agora estabelecida por $D_{g,j}$ e pela recursão de balanço (§X.2–X.3).

---

## Parte XI — Custo Direto Total do Projeto

Esta seção apenas soma os dois grandes blocos de custo direto calculados até aqui: o pool de recursos contratuais (Parte IX) e os consumíveis (Parte X). Não há cálculo novo — é a consolidação, em nível de projeto, do que já foi apurado por atividade e por recurso.

$$C^D = C^{\mathrm{pool}}+C^{\mathrm{cons}}\qquad\text{[R\$ — sem BDI]}$$
$$C^{D,\beta} = C^{\mathrm{pool},\beta}+C^{\mathrm{cons},\beta}\qquad\text{[R\$ — com BDI; nível projeto, distinto de }C_i^{D,\beta}\text{ (atividade)}$$
$$\beta^D = C^{D,\beta}/C^D-1$$

$\beta^D$ é o BDI médio implícito nesse bloco direto — um diagnóstico intermediário útil antes de somar os custos indiretos na Parte XIII.

---

## Parte XII — Custos Indiretos

Custos indiretos são aqueles que existem para viabilizar o projeto como um todo, não para produzir uma atividade específica — administração central, topografia, laboratório, QSMS, mobilização de canteiro. Diferente do custo direto, que só existe enquanto uma atividade está efetivamente em produção, a maior parte do indireto é cobrada pelo simples fato de o projeto estar em andamento, semana a semana, do início ao fim do cronograma.

### XII.1 Estrutura: categorias e drivers

$$\mathcal{L} = \{ADM, TOP, LAB, QSMS, MOB^{\text{site}}, \ldots\}\quad\text{(conjunto extensível)}$$

$$\text{driver}(l)\in\{\texttt{perm},\ \texttt{onetime}\}$$

- `perm`: custo mensal fixo enquanto o projeto está mobilizado (ADM, TOP, LAB, QSMS)
- `onetime`: evento único de borda — mobilização/desmobilização de canteiro ($MOB^{\text{site}}$)

Em outras palavras: categorias `perm` (como administração central) geram custo toda semana em que o projeto está ativo, proporcional ao makespan do cronograma; categorias `onetime` (como mobilização de canteiro) geram custo pontual, uma vez no início e uma vez no fim, independentemente de quanto tempo o projeto durar.

$n = j^{\max}-j^{\min}$ (makespan do projeto em semanas). $j^{\min}=\min_i j_i^0$, $j^{\max}=\max_i(j_i^0+N_i)$.

### XII.2 Entrada por categoria

$$l = \Bigl(\text{driver}(l),\ \{\Gamma_l^{k,\text{mensal}}\}_{k\in\{MO,EQ,COMB\}},\ (c_l^{\text{mob}},c_l^{\text{demob}})\ \text{ou}\ \Gamma_l^{VM,\text{mensal}}\Bigr)$$

### XII.3 Custo semanal por sub-categoria

**Driver `perm`:**

$$\gamma_l^{k,\text{sem}} = \frac{\Gamma_l^{k,\text{mensal}}}{s_{\text{mes}}}, \qquad m_l(j)=1 \ \ \forall j\in\{0,\ldots,n-1\}$$

**Driver `onetime`:**

$$\gamma_l^{VM,\text{sem}}(j) = c_l^{\text{mob}}\,\mathbb{1}[j=j^{\min}] + c_l^{\text{demob}}\,\mathbb{1}[j=j^{\max}-1]$$

*(para $n=1$: mob e demob caem na mesma semana, somando-se)*

$$C_{lj}^{I,o} = \Bigl(\gamma_l^{MO,\text{sem}}+\gamma_l^{EQ,\text{sem}}+\gamma_l^{COMB,\text{sem}}+\gamma_l^{VM,\text{sem}}(j)\Bigr)\cdot m_l(j)$$

### XII.4 Camada BDI do indireto

$$\boxed{C_{lj}^{I,\beta} = \Bigl[\gamma_l^{MO,\text{sem}}(1+\beta^{MO})+\gamma_l^{EQ,\text{sem}}(1+\beta^{EQ})+\gamma_l^{COMB,\text{sem}}(1+\beta^{COMB})+\gamma_l^{VM,\text{sem}}(j)(1+\beta^{IND})\Bigr]\cdot m_l(j)}$$

**Totais por categoria:**

$$C_l^{I,o} = \sum_j C_{lj}^{I,o}$$
$$C_l^{I,\beta} = \Gamma_l^{MO}(1+\beta^{MO})+\Gamma_l^{EQ}(1+\beta^{EQ})+\Gamma_l^{COMB}(1+\beta^{COMB})+\Gamma_l^{VM}(1+\beta^{IND})$$

### XII.5 Mobilização do pool de equipamento (indireta, por cadeia)

$$\boxed{C^{MOB,eq,o} = \sum_r N_{\text{chains}}^r\cdot(c_r^{\text{mob}}+c_r^{\text{demob}})}, \qquad C^{MOB,eq,\beta} = (1+\beta^{IND})\cdot C^{MOB,eq,o}$$

### XII.6 Totais do indireto

$$C^I = \sum_{l\in\mathcal{L}} C_l^{I,o} + C^{MOB,eq,o} + C^{\mathrm{inv}}$$
$$C^{I,\beta} = \sum_{l\in\mathcal{L}} C_l^{I,\beta} + C^{MOB,eq,\beta} + C^{\mathrm{inv}}\,(1+\beta^{\mathrm{IND}})$$
$$\bar\beta^I = C^{I,\beta}/C^I-1$$

---

## Parte XIII — Síntese: Preço Total e Viabilidade

Esta seção final reúne tudo que foi calculado: soma-se o custo direto e indireto, com e sem BDI, compara-se o resultado com o envelope de catálogo, e verifica-se se a proposta comercial resultante é viável frente ao piso regulatório.

**Custo de catálogo** (agregado por atividade):

$$C^{\mathrm{cat}} = \sum_{i\in\mathcal{A}} C_i^{\mathrm{cat}} = \sum_{i\in\mathcal{A}} \frac{\gamma_i^{\mathrm{cat}}\,Q_i}{\rho_i}\qquad\text{[R\$ — envelope de catálogo, base de precificação]}$$

$$C^{\mathrm{tot}} = C^D+C^I \qquad\text{[R\$ — custo operacional total, sem BDI]}$$

**Preço de venda e BDI implícito.** O preço é a soma dos blocos direto e indireto já com a camada granular de $\beta$ aplicada (Partes VIII e XII):

$$P \equiv C^{D,\beta}+C^{I,\beta} \qquad\text{[R\$ — preço de venda]}$$

O BDI não é um segundo parâmetro de markup somado independentemente sobre $C^{\mathrm{cat}}$: é a taxa agregada, **derivada**, resultante de aplicar a camada granular de $\beta$'s — uma por categoria de recurso ($\beta^{EQ},\beta^{MO},\beta^{MAT},\beta^{COMB},\beta^{IND}$) — e agregá-la ao nível do envelope de catálogo:

$$\boxed{\mathrm{BDI} \equiv \frac{P}{C^{\mathrm{cat}}}-1}$$

Não há dupla contagem: existe uma única camada de markup, aplicada item a item nas Partes VIII e XII; o BDI é apenas a leitura agregada dessa mesma camada, útil para comparação com o piso regulatório. Categorias de custo indireto que fisicamente compõem a estrutura clássica de BDI (administração central, canteiro) já estão computadas dentro de $C^{I,\beta}$ com seu próprio $\beta^{IND}$ — não devem ser adicionadas novamente como percentual do BDI agregado; $\mathrm{BDI}_{\mathrm{TCU,min}}$ funciona como **piso de verificação** sobre a taxa agregada resultante, não como um segundo insumo a ser somado.

$$R = C^{\mathrm{tot}}/C^{\mathrm{cat}}, \qquad \beta^{\mathrm{eq}} = P/C^{\mathrm{tot}}-1, \qquad \mu = (P-C^{\mathrm{tot}})/P$$

**Condição de viabilidade:**

$$\boxed{\mathrm{BDI} \;\ge\; \mathrm{BDI}_{\mathrm{TCU,min}}}$$

$\mathrm{BDI}_{\mathrm{TCU,min}}$ é determinado pela fórmula multiplicativa TCU (overhead não capturado nos $\beta$'s granulares, lucro mínimo e tributos) — é o único piso de verificação que este formulário exige.

Poderia parecer que uma segunda verificação também é necessária: garantir que o preço pelo menos cubra o custo realmente incorrido, isto é, $\mathrm{BDI}\ge R-1$ (equivalente a $P\ge C^{\mathrm{tot}}$). Essa condição, porém, não é uma segunda verificação independente — é consequência aritmética automática de $\mathrm{BDI}$ e $R$, ambos já calculados, não um novo insumo a se checar à parte. Substituindo $P=C^{\mathrm{cat}}(1+\mathrm{BDI})$ e $C^{\mathrm{tot}}=R\cdot C^{\mathrm{cat}}$ em $\beta^{\mathrm{eq}}=P/C^{\mathrm{tot}}-1$:

$$\beta^{\mathrm{eq}} = \frac{C^{\mathrm{cat}}(1+\mathrm{BDI})}{R\cdot C^{\mathrm{cat}}}-1 = \frac{1+\mathrm{BDI}}{R}-1$$

logo $\beta^{\mathrm{eq}}>0 \iff 1+\mathrm{BDI}>R \iff \mathrm{BDI}>R-1$ — as duas expressões descrevem exatamente a mesma coisa, apenas escritas de formas diferentes. Verificar $\mathrm{BDI}\ge\mathrm{BDI}_{\mathrm{TCU,min}}$ já é suficiente; não há necessidade de comparar $\mathrm{BDI}$ com $R-1$ à parte. $R$ permanece útil como **diagnóstico**, não como insumo de decisão: evidencia quanto do custo provém de ineficiência prevista, ajudando a explicar por que o BDI resultante ficou alto ou baixo — não substitui nem complementa a verificação regulatória.

---

## Parte XIV — Algoritmo

O algoritmo a seguir é a receita passo a passo que implementa todas as fórmulas das partes anteriores, na ordem correta de dependência: cada fase usa apenas resultados já calculados pelas fases anteriores, nunca antecipa um valor que ainda não existe. Quem já entendeu as Partes I a XIII pode ler esta seção como um mapa de onde cada fórmula entra no processo.

O algoritmo opera em **10 fases sequenciais** (incluindo a Fase 4b, dinâmica de estoque e reposição). As Fases 0 e 1 requerem solvers externos; as demais são computações exatas dadas as saídas anteriores — a própria Fase 4b resolve um problema de programação dinâmica de solução exata conhecida (Wagner–Whitin), não uma heurística.

```
══════════════════════════════════════════════════════════════════════
ENTRADA
══════════════════════════════════════════════════════════════════════

  A = {A_i}_{i=1}^{n_ativ}        — conjunto de atividades

  Para cada i:
    Q_i                            — quantitativo total [un]
    G_i = (V_i, A_i^syn, cap)      — grafo de sinergia da equipe
    R_i = {r: (cat_r, n_r, V_r^mensal ou (κ_r, p_{g(r)}))}
    W_i = (m_i^0, μ_i^+, m_i^max, μ_i^-, m_i^1)
    B_i, θ_i: B_i → (0,1]
    (h_i, d_i)                     — regime de jornada

  Parâmetros globais:
    β^EQ, β^MO, β^MAT, β^COMB, β^IND, s_mes
    {η_{p,j}, η_{w,j}}              — calendário global de desempenho e clima
    // η_{s,ij} é derivado por atividade a partir de G_i e do perfil {m_ij} (Fase 1)
    // ε_{ij} = η_{s,ij} · η_{p,j} · η_{w,j}

  Para cada recurso r:
    c_r^mob, c_r^demob             — custos de mobilização/desmobilização
    G_r^viável                     — gap máximo absoluto [semanas]
    // c_r^standby ≡ c_r^sem: pool é custo de permanência puro (§IX.3)

  Categorias indiretas:
    {(l, driver(l), {Γ_l^{k,mensal}}, c_l^mob, c_l^demob)}_{l ∈ L}

  Para cada bem físico g (consumível, cf. g(r) em R_i):
    c_g^hold, c_g^ped, L_g          — custo de posse [R$/unid_g/sem], custo de pedido [R$], lead time [sem]
    j^{procure,min}                 — semana mais cedo em que um pedido pode ser colocado (opcional)
```

### XIV.0 — Fase 0: Resolução de Produtividade

Em termos simples: aqui se calcula quanto cada equipe consegue produzir por hora, a partir do grafo de sinergia ou de um valor calibrado externamente.

```
Para cada i ∈ A:
  Se i.grafo_sinergia está presente:
    Identificar topologia de G_i:
      série    → ρ_i = min_{(u,v) ∈ caminho_crítico} cap(u,v)
      paralelo → ρ_i = Σ_{(s_i,v) ∈ A_i^syn} cap(s_i, v)
      misto    → ρ_i = max-fluxo(s_i → t_i, G_i^D)  [Ford-Fulkerson]
    Armazenar ρ_i como producao_horaria  [cache auditável]
  Senão:
    ρ_i ← i.producao_horaria             [entrada direta calibrada externamente]

  Validar ρ_i > 0  [equipe inviável se algum corte tem capacidade zero]

SAÍDA: {ρ_i} ∀i
```

### XIV.1 — Fase 1: Cronograma (interface com solver RCPSP externo)

Em termos simples: aqui se determina quantas semanas cada atividade vai durar e como as frentes de trabalho se distribuem ao longo do tempo, até fechar exatamente o quantitativo contratado.

```
Pré-condição: {ρ_i} disponível ∀i

Para cada i em ordem topológica de B_i:

  // j_i^0 depende só de predecessores, já resolvidos — calculado antes da busca por N_i,
  // pois a busca abaixo precisa de semanas absolutas j para consultar η_{p,j}, η_{w,j}
  j_i^0 ← max_{b ∈ B_i} min{j : Φ_b(j) ≥ θ_i(b)}  [restrição exata de quantidade]
    com Φ_b(j) = (1/Q_b) · Σ_{j'=j_b^0}^{j} q_{b,j'}
    // q_{b,j'} vem da DistribuicaoSemanal já calculada dos predecessores b, já com
    // fechamento fracionário aplicado

  N_i ← max(1, ⌈Q_i / (ρ_i · h_i · d_i · m_i^max)⌉)   // chute inicial (eficiência plena)

  Repetir:
    {m_i(τ)}_{τ=0}^{N_i-1} ← RampProfile.build(N_i, m_i^0, μ_i^+, m_i^max, μ_i^-, m_i^1)
    // perfil inteiramente determinado pelo N_i testado — nenhuma incógnita nesta avaliação

    Para τ = 0, ..., N_i-1:
      j ← j_i^0 + τ                                    // semana absoluta, para consultar o calendário
      Se i.grafo_sinergia presente:
        η_{s,iτ} ← max-fluxo(G_i^D | m_i(τ)) / max-fluxo(G_i^D | m_i^max)
      Senão:
        η_{s,iτ} ← m_i(τ) / m_i^max
      ε_{iτ} ← η_{s,iτ} · η_{p,j} · η_{w,j}

    prod ← Σ_τ ρ_i · ε_{iτ} · h_i · d_i · m_i(τ)

    Se prod ≥ Q_i:
      convergiu; {m_{ij}} ← {m_i(τ)}; {ε_{ij}} ← {ε_{iτ}}
    Senão:
      Se ε_{iτ} = 0 para toda semana τ futura alcançável dentro do calendário disponível:
        Marcar A_i INVIÁVEL; interromper busca (→ Fase 9, NOGO)
      Senão:
        N_i ← N_i + 1
        // Π(N) = prod acumulado é estritamente crescente em N (ver §I.4): a cada
        // incremento, as semanas já existentes só podem crescer (o piso de ramp-down
        // relaxa) e a semana nova soma ≥ ρ_i · ε_{i,N-1} · h_i · d_i · m_i^1 > 0 —
        // convergência garantida sempre que o calendário não anula ε indefinidamente.
        // Cada tentativa é recalculada do zero a partir da fórmula de m_i(τ;N); nenhum
        // valor de uma tentativa rejeitada é reaproveitado na seguinte.

  // Fechamento exato de escopo — última semana ativa (τ relativo, 0-indexado)
  τ^1 ← N_i − 1
  q_residual ← Q_i − Σ_{τ=0}^{τ^1-1} ρ_i · ε_{i,τ} · h_i · d_i · m_i(τ)
  φ_i ← q_residual / (ρ_i · ε_{i,τ^1} · h_i · d_i · m_i(τ^1))

  Verificar: r + d ≤ N_i  [consistência com W_i]

Armazenar (j_i^0, N_i, {m_{ij}}, {ε_{ij}}, φ_i)

SAÍDA: {j_i^0, N_i, {m_{ij}}, {ε_{ij}}, φ_i} ∀i
```

### XIV.2 — Fase 2: Taxas Horárias de Catálogo

Em termos simples: aqui se traduz o cadastro de cada recurso — aluguel mensal, taxa de consumo, preço de insumo — em um custo por hora, e depois esse custo é agregado por equipe.

```
Para cada i ∈ A:
  Para cada r ∈ R_i:
    Se cat(r) ∈ {EQ, MO}:
      c_r ← V_r^mensal / (s_mes · d_i · h_i)          [R$/h]
    Se cat(r) ∈ {MAT, COMB}:
      c_r ← κ_r · p_{g(r)}                             [R$/h_op, agnóstico em unid_g]

  Para k ∈ {EQ, MO, MAT, COMB}:
    γ_i^k ← Σ_{r: cat(r)=k} c_r · n_r

  γ_i^{K,cat} ← γ_i^EQ + γ_i^MO
  γ_i^{V,cat} ← γ_i^MAT + γ_i^COMB
  γ_i^{cat}   ← γ_i^{K,cat} + γ_i^{V,cat}
  f_i^V       ← γ_i^{V,cat} / γ_i^{cat}
  p_i^{cat}   ← γ_i^{cat} / ρ_i                       [R$/un — PU de catálogo]

SAÍDA: {γ_i^k, γ_i^{K,cat}, γ_i^{V,cat}, γ_i^{cat}, f_i^V, p_i^{cat}} ∀i
```

### XIV.3 — Fase 3: Quantitativos e Custos Semanais Diretos

Em termos simples: aqui se calcula, semana a semana, quanto cada atividade produziu e quanto isso custou — e se confere que a soma bate exatamente com o quantitativo contratado.

```
Para cada i ∈ A, para cada j ∈ [j_i^0, j_i^0 + N_i - 1]:
  Se j < j_i^0 + N_i - 1:
    q_{ij} ← ρ_i · ε_{ij} · h_i · d_i · m_{ij}          [semana interior]
  Senão:
    q_{ij} ← q_residual                                  [semana de fechamento, da Fase 1]

  C_{ij}^{K,op}   ← γ_i^{K,cat} · h_i · d_i · m_{ij}       [nominal — não prorateado]
  C_{ij}^{V,op}   ← γ_i^{V,cat} · q_{ij} / ρ_i             [prorateado exatamente pelo quantitativo]
  C_{ij}^{op}     ← C_{ij}^{K,op} + C_{ij}^{V,op}

Para cada i:
  M_i          ← Σ_j m_{ij}
  C_i^{K,op}  ← γ_i^{K,cat} · h_i · d_i · M_i
  C_i^{V,op}  ← γ_i^{V,cat} · Q_i / ρ_i           [= Σ_j C_{ij}^{V,op}, exato]
  C_i^{op}    ← C_i^{K,op} + C_i^{V,op}
  p_i^{op}    ← C_i^{op} / Q_i                      [R$/un]

Verificação obrigatória:
  ∀i: Σ_j q_{ij} = Q_i                               [fecho de escopo exato]

C_i^{cat} ← γ_i^{cat} · Q_i / ρ_i
C^{cat}   ← Σ_i C_i^{cat}                            // envelope de catálogo

SAÍDA: {q_{ij}, C_{ij}^{op}, C_i^{op}, M_i, p_i^{op}, C_i^{cat}} ∀i
       C^{cat}
```

### XIV.4 — Fase 4: Dimensionamento e Custo do Pool

Em termos simples: aqui se decide, para cada tipo de recurso contratual, quantas instâncias contratar e quando vale a pena mantê-las paradas entre duas atividades em vez de desmobilizar e remobilizar.

```
// Decomposição por nível (histograma): para um tipo fungível homogêneo, a alocação
// ótima decompõe-se em decisões independentes por "fatia" de altura unitária — cada
// fatia corresponde a uma cadeia de perpetuação da Parte IX. Ref.: SDVSP — Freling,
// Wagelmans & Paixão (2001).

C^{pool} ← 0; C^{pool,β} ← 0; C^{MOB,eq} ← 0; C^{MOB,eq,β} ← 0

Para cada tipo τ ∈ T:
  n_j(τ) ← Σ_{i: j ∈ [j_i^0, j_i^0+N_i-1]} m_{ij} · n_τ^i   ∀j
  n_max(τ) ← max_j n_j(τ)
  G_τ^* ← (c_τ^mob + c_τ^demob) / c_τ^sem

  sem_τ ← 0; trips_τ ← 0

  Para ℓ = 1, 2, ..., n_max(τ):                       // uma "fatia" por unidade de fleet
    on_ℓ ← {j : n_j(τ) ≥ ℓ}                             // semanas em que a ℓ-ésima instância é exigida
    blocos ← intervalos maximais consecutivos de on_ℓ
    Fundir blocos consecutivos [b_k, b_{k+1}] cujo gap = início(b_{k+1}) − fim(b_k)
      satisfaça gap ≤ min(G_τ^*, G_τ^viável)            // perpetuação da instância desta fatia
    Para cada bloco fundido (após a fusão):
      sem_τ   ← sem_τ + duração(bloco)                  // inclui gaps internos perpetuados
      trips_τ ← trips_τ + 1                               // um par mob/demob por bloco fundido

  C^{pool}     ← C^{pool}     + sem_τ · c_τ^sem
  C^{pool,β}   ← C^{pool,β}   + (1 + β_{cat(τ)}) · sem_τ · c_τ^sem
  C^{MOB,eq}   ← C^{MOB,eq}   + trips_τ · (c_τ^mob + c_τ^demob)
  C^{MOB,eq,β} ← C^{MOB,eq,β} + (1 + β^IND) · trips_τ · (c_τ^mob + c_τ^demob)

SAÍDA: C^{pool}, C^{pool,β}, C^{MOB,eq}, C^{MOB,eq,β}
```

### XIV.4b — Fase 4b: Dinâmica de Estoque e Reposição (Wagner–Whitin)

Em termos simples: aqui se decide, para cada bem consumível, quando e quanto comprar, cobrindo exatamente a demanda derivada do cronograma ao menor custo combinado de pedido e posse.

```
Pré-condição: {q_ij, ρ_i} disponíveis (Fase 3); {κ_i^g} do cadastro (Fase 2, via R_i)

Para cada bem físico g:

  // Demanda derivada — nenhum novo insumo, só agregação (§X.2)
  Para cada j:
    D_{g,j} ← Σ_{i ∈ A_j} κ_i^g · q_{ij} / ρ_i

  [j_min^g, j_max^g] ← intervalo de semanas com D_{g,j} > 0

  // Programação dinâmica (Wagner-Whitin) — solução exata, não heurística
  f(j_min^g - 1) ← 0
  Para b = j_min^g, ..., j_max^g:
    f(b) ← min_{a ∈ [j_min^g, b]} [ f(a-1) + c_g^ped + c_g^hold · Σ_{k=a+1}^{b} (k-a)·D_{g,k} ]
    a*(b) ← argmin correspondente

  // Backtracking — recupera a partição ótima em lotes
  lotes_g ← {}; b ← j_max^g
  Enquanto b ≥ j_min^g:
    a ← a*(b)
    lotes_g ← lotes_g ∪ {[a, b]}
    X_{g, a - L_g} ← Σ_{k=a}^{b} D_{g,k}          // pedido colocado L_g semanas antes de a
    b ← a - 1

  // Reconstrução da trajetória de estoque (§X.4)
  Para cada lote [a,b] ∈ lotes_g, para j = a, ..., b:
    S_{g,j} ← Σ_{k=j+1}^{b} D_{g,k}

  n_g^ped ← |lotes_g|
  C_g^{inv} ← c_g^hold · Σ_j S_{g,j}
  C_g^{PED} ← n_g^ped · c_g^ped

  Verificar: ∀ lote [a,b] ∈ lotes_g: a - L_g ≥ j_min   [senão, sinalizar pedido de pré-mobilização]

C^{inv} ← Σ_g C_g^{inv}
C^{PED} ← Σ_g C_g^{PED}
C^{PED,β} ← (1 + β^IND) · C^{PED}

SAÍDA: {D_{g,j}, S_{g,j}, X_{g,j}} ∀g,j ; C^{inv}, C^{PED}, C^{PED,β}
```

### XIV.5 — Fase 5: Estoque (Consumíveis)

Em termos simples: aqui se soma o custo de material e combustível efetivamente consumido por todas as atividades do projeto.

```
C^{cons} ← Σ_i γ_i^{V,cat} · Q_i / ρ_i
  // Exato por construção: Σ_i γ_i^{V,cat}·Q_i/ρ_i ≡ Σ_i C_i^{V,op} (fecho de escopo, Parte IV)

Para cada i:
  γ_i^{V,cat,β} ← (1+β^MAT) · γ_i^MAT + (1+β^COMB) · γ_i^COMB

C^{cons,β} ← Σ_i γ_i^{V,cat,β} · Q_i / ρ_i

// C^{inv} e C^{PED} já disponíveis da Fase 4b — não recalculados aqui

SAÍDA: C^{cons}, C^{cons,β}
```


### XIV.6 — Fase 6: Custo Direto Total

Em termos simples: aqui se somam os dois blocos calculados nas fases anteriores — pool de recursos e consumíveis — para chegar ao custo direto do projeto inteiro.

```
C^D    ← C^{pool} + C^{cons}
C^{D,β} ← C^{pool,β} + C^{cons,β}
β^D    ← C^{D,β} / C^D − 1

SAÍDA: C^D, C^{D,β}, β^D
```

### XIV.7 — Fase 7: Custos Indiretos

Em termos simples: aqui se calculam os custos que existem para viabilizar o projeto como um todo — administração, canteiro, mobilização de equipamento — a partir do makespan do cronograma.

```
j_min ← min_i j_i^0
j_max ← max_i (j_i^0 + N_i)
n     ← j_max − j_min    [makespan em semanas]

Para cada l ∈ L:
  Se driver(l) = 'perm':
    Para k ∈ {MO, EQ, COMB}:
      Γ_l^k ← Γ_l^{k,mensal} · (n / s_mes)
    Γ_l^VM ← 0

  Se driver(l) = 'onetime':
    Γ_l^VM ← c_l^mob + c_l^demob
    Γ_l^k  ← 0  para k ∈ {MO, EQ, COMB}

  C_l^{I,o} ← Σ_k Γ_l^k + Γ_l^VM
  C_l^{I,β} ← Γ_l^MO·(1+β^MO) + Γ_l^EQ·(1+β^EQ)
               + Γ_l^COMB·(1+β^COMB) + Γ_l^VM·(1+β^IND)

// C^{inv} e C^{PED} já calculados na Fase 4b — apenas consumidos aqui
C^I    ← Σ_l C_l^{I,o} + C^{MOB,eq,o} + C^{PED} + C^{inv}
C^{I,β} ← Σ_l C_l^{I,β} + C^{MOB,eq,β} + C^{PED,β} + C^{inv}·(1+β^IND)
β^I    ← C^{I,β} / C^I − 1

SAÍDA: C^I, C^{I,β}, β^I
```

### XIV.8 — Fase 8: Síntese e Preço Total

Em termos simples: aqui se reúnem todos os blocos de custo em um preço de venda final, e se calcula o BDI agregado resultante.

```
C^{tot} ← C^D + C^I
P       ← C^{D,β} + C^{I,β}
BDI     ← P / C^{cat} − 1                          // taxa agregada derivada, não insumo livre
R       ← C^{tot} / C^{cat}                          // razão custo real vs catálogo
β^eq   ← P / C^{tot} − 1
μ       ← (P − C^{tot}) / P

SAÍDA:
  C^D, C^I, C^{tot}       — custos sem BDI (base operacional)
  C^{D,β}, C^{I,β}, P    — preços com BDI (base de venda)
  BDI, R, β^eq, μ         — indicadores  [verificar BDI ≥ BDI_TCU_min; R = diagnóstico]
```

### XIV.9 — Fase 9: Validação e Diagnóstico

Em termos simples: aqui se checa se todos os resultados fazem sentido — se o escopo fechou exatamente, se o BDI atinge o piso regulatório, se nenhum recurso ficou parado o tempo todo — antes de aprovar a proposta.

```
Verificações obrigatórias:
  [V1] ∀i: Σ_j q_{ij} = Q_i                           — fecho de escopo exato
  [V2] BDI ≥ BDI_TCU_min                                — cobertura mínima de overhead+lucro+tributos
  [V3] ∀r: f_standby(r) < 1                             — nenhum recurso 100% standby
  [V4] P > 0  e  C^{tot} > 0                            — consistência numérica
  [V5] ∀i: ρ_i > 0                                     — nenhuma equipe com gargalo de capacidade zero
  [V6] ∀i: busca de N_i convergiu sem sinalização de inviabilidade (Fase 1) — calendário viável
  [V7] ∀g,j: S_{g,j} ≥ 0                                — nenhuma ruptura de estoque na solução ótima (§X.3)
  [V8] ∀g: Σ_j D_{g,j} = U_g                            — consistência entre demanda física e consumo total (§X.2)
  [V9] ∀g, ∀ lote [a,b] ∈ lotes_g: a − L_g ≥ j_min      — viabilidade de prazo de pedido (senão, pré-mobilização)

Diagnósticos opcionais:
  [D1] taxa_util_τ = Σ_j n_j(τ) / (n · n_max(τ)) por tipo τ
         → próximo de 1: pool bem dimensionado; baixo: excesso de standby
  [D2] R_i = C_i^{op} / C_i^{cat} = f_i^V + (1 − f_i^V) · (1/ε̄_i)   [Parte VI/VIII]
         → razão custo operacional / catálogo por atividade
  [D2'] Δ_i^{cat} = C_i^{op} − C_i^{cat} = (R_i−1)·C_i^{cat}   [R$, Parte VI]
         → desvio de catálogo por atividade, em valor monetário
  [D3] {p_i^{op}} por atividade — custo unitário operacional [R$/un]
  [D4] Proporção direto/indireto: C^D/C^{tot}
  [D5] β_i^{eq} = (1−δ_i)·β_i^K + δ_i·β_i^V   — BDI equivalente por equipe
  [D6] n_g^ped e tamanho médio de lote por bem — fragmentação da política de reposição:
         muitos pedidos pequenos (custo de pedido domina) vs. poucos grandes (posse domina)

Saída final:
  GO   se [V1]–[V9] aprovadas
  NOGO + lista de violações  caso contrário
```

---

## Convenções de Notação

Antes de qualquer fórmula, vale entender como os símbolos são montados: cada grandeza carrega até três informações no seu sobrescrito, o que evita ambiguidade sem exigir nomes de variáveis longos. Uma vez internalizado esse código, o resto do formulário se lê quase como texto corrido.

**Regra de três slots** no superscrito. Nenhum símbolo carrega dois papéis.

| Slot | Valores | Significado |
|---|---|---|
| 1º — natureza | $\mathrm{K}$ | **contratual**: EQ + MO. Cobrado por semana mobilizada, não escala com produção |
| | $\mathrm{V}$ | **consumível**: MAT + COMB. Escala com produção realizada |
| 2º — regime | $\mathrm{cat}$ | **catálogo**: nominal, $\varepsilon = 1$ |
| | $\mathrm{op}$ | **operacional**: com $\varepsilon_{ij}$ realizado |
| 3º — markup | $\beta$ | com BDI aplicado. Ausente = sem BDI |

Exemplos: $\gamma_i^{\mathrm{K,cat}}$ · $C_{ij}^{\mathrm{V,op},\beta}$ · $\zeta_{ij} = C^{\mathrm{op}}_{ij}/C^{\mathrm{cat}}_{ij}$