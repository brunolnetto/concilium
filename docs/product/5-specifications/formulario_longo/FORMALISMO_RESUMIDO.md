# Formulário White-Box — Atividades, Pool de Recursos e Custos Indiretos

---

## Parte I — Entrada: Definição das Atividades (formulário)

> **Contrato normativo P09-A:** unidades, domínios de mobilização, intervalos e política numérica são definidos em [CONVENCOES_NORMATIVAS.md](CONVENCOES_NORMATIVAS.md). As equações ainda em revisão permanecem explicitamente sinalizadas nas issues #10–#13.


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

> **Contrato normativo P10-A:** [CAPACIDADE_E_RECURSOS.md](CAPACIDADE_E_RECURSOS.md) substitui a eficiência de alocação η_s por capacidade física F_i(m). As fórmulas históricas de ρ·η_s·m e os custos derivados permanecem **não certificáveis** até #11.

#### I.3.2 Capacidade da composição efetivamente mobilizada

O grafo \(\mathcal G_i^D\) representa a transformação de recursos em unidades físicas de \(Q_i\). A capacidade de \(m\) frentes **efetivamente mobilizadas** respeita as restrições compartilhadas e, pelo teorema max-flow/min-cut, vale

$$\boxed{F_i(m)=\max\operatorname{fluxo}(s_i,t_i;\mathcal G_i^D|_m)
=\min_{C\text{ corte}}\sum_{e\in C}\operatorname{cap}_m(e)}
\quad[\mathrm{unid}_{Q_i}/h].$$

\(F_i(0)=0\). Para frentes **independentes**, \(F_i(m)=m\rho_i^{front}\); para processos compartilhados, \(F_i(m)\) pode saturar. A taxa \(\rho_i^{peak}=F_i(m_i^{max})\) é capacidade de pico **da configuração**, não por frente. Produtividade externa calibrada deve declarar a configuração de referência, sem extrapolação linear implícita.

$$\boxed{B_{ij}=h_id_i F_i(m_{ij})\eta_{p,j}\eta_{w,j},
\qquad q_{ij}=\min\{(Q_i-\sum_{k<j}q_{ik})_+,B_{ij}\}.}$$

**Não existe perda multiplicativa de alocação \(\eta_s\).** A escolha \(m_{ij}\) já entra em \(F_i(m_{ij})\); multiplicar por \(m\) outra vez equivale a dupla contagem. A razão \(\alpha_i(m)=F_i(m)/F_i(m_i^{max})\) é diagnóstico de capacidade, nunca penalidade adicional.

As frentes determinam recursos físicos por tipo \(g\): \(d_{gj}=\sum_i a_{ig}(m_{ij})\), onde \(a_{ig}(m)=m a_{ig}^{front}\) apenas em composições independentes. Presença contratual \(x_{gj}\ge d_{gj}\), standby \(s_{gj}=x_{gj}-d_{gj}\) e movimentos pertencem ao problema econômico §IX e **não** reduzem \(F_i(m)\).

**Contraprovas:** \(F(m)=10m\), \(m=2\), \(h_id_i=40\) => \(q=800\) unidades, mesmo se \(m_i^{max}=4\). Já \(F(m)=\min(10m,15)\) entrega \(600\) un/semana tanto com duas quanto com quatro frentes, mas quatro frentes requerem mais recursos. Ver [CAPACIDADE_E_RECURSOS.md](CAPACIDADE_E_RECURSOS.md) (#10/#16).

### I.4 Política de mobilização \(W_i\)

$$W_i=(m_i^0,\mu_i^+,m_i^1,\mu_i^-,m_i^{max})
\in\mathbb N_{>0}\times\mathbb N_{\ge0}\times\mathbb N_{>0}\times\mathbb N_{\ge0}\times\mathbb N_{>0}.$$

\(m_i^0,m_i^1\le m_i^{max}\), com rampas não negativas. Para \(\tau=j-j_i^0\in\{0,\ldots,N-1\}\):

$$\boxed{m_i(\tau;N)=\min\{m_i^0+\mu_i^+\tau,\ m_i^{max},\ m_i^1+\mu_i^-(N-1-\tau)\}.}$$

O retângulo de \(m_i^{max}\) frentes exige **simultaneamente** \(\mu_i^+=\mu_i^-=0\) e \(m_i^0=m_i^1=m_i^{max}\). Fora da atividade \(m_{ij}=0\) e \(F_i(0)=0\). A ocupação semanal \([j_i^0,j_i^0+N_i)\) é semiaberta.

Dado o início absoluto \(j_i^0\), a capacidade acumulada de uma duração candidata é

$$\Pi_i(N;j_i^0)=h_id_i\sum_{\tau=0}^{N-1}
F_i(m_i(\tau;N))\eta_{p,j_i^0+\tau}\eta_{w,j_i^0+\tau}.$$

A duração é o menor \(N\) admissível que fecha \(Q_i\) e satisfaz capacidade, predecessores e horizonte. O calendário absoluto deve ser conhecido **antes** da busca; mudar início ou duração exige revalidar restrições RCPSP. **Não declarar convergência garantida** sem produtividade futura e horizonte suficientes (#12/#15). A condição histórica \(r+d\le N\) está indefinida e não constitui gate.

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

## Parte III — Custo de Catálogo e Composição de Referência

O cadastro declara, por recurso \(g\), a taxa de presença contratual \(c_g^{K}\) [R$/h] e/ou preço de consumível \(p_g\) [R$/unidade física]. O custo horário **por frente independente** de cada categoria é \(\gamma_i^k=\sum_{r:\operatorname{cat}(r)=k}c_r n_r\), onde as dimensões devem ser homogêneas.

**Importante:** \(\gamma_i^k\) é da composição **de referência**, não necessariamente da configuração mobilizada \(m_{ij}\). Com \(F_i(m)\) não linear, dividir uma taxa horária por \(\rho_i^{peak}\) só tem significado após especificar qual \(m^{ref}\), quais recursos, qual jornada e quais quantidades físicas estão na base do catálogo.

Uma referência admissível deve declarar \((m_i^{ref},F_i(m_i^{ref}),a_{ig}(m_i^{ref}),H_i,\text{regime de consumo})\) e calcular seu custo por unidade a partir de **numerador e denominador dessa mesma configuração**. A forma histórica

$$p_i^{cat}=\frac{\gamma_i^{cat}}{\rho_i^{front}}$$

é **caso particular** de composição independente, taxa realmente **por frente** e custos unitários dimensionados nessa mesma base. Para gargalos compartilhados, tarifas de standby ou demanda não linear, não adotar a expressão como identidade universal. Reavaliação completa: #11/#18/#21.

---

## Parte IV — Cronograma Semanal

A produção da semana \(j\) é determinada uma única vez pela função física \(F_i(m_{ij})\) (§I.3.2):

$$\boxed{B_{ij}=F_i(m_{ij})H_i\eta_{p,j}\eta_{w,j},\qquad
q_{ij}=\min\left\{\left(Q_i-\sum_{k<j}q_{ik}\right)_+,B_{ij}\right\}},\quad H_i=h_id_i.$$

O fechamento satisfaz \(\sum_jq_{ij}=Q_i\) somente se a capacidade e o calendário disponíveis forem suficientes. Na última semana produtiva \(j_i^1\), com \(B_{i,j_i^1}>0\), seja

$$\boxed{\varphi_i=\frac{q_{i,j_i^1}}{B_{i,j_i^1}}\in(0,1].}$$

\(\varphi_i\) mede a **fração de capacidade usada para encerrar escopo**, não eficiência produtiva perdida. A contratação semanal vigente pode ser cobrada integralmente, mesmo se \(\varphi_i<1\); o consumo físico real deve respeitar seu regime próprio (§V e §X). Recursos pagos mas não demandados são \(s_{gj}\) do pool (§IX).

---

## Parte V — Custos Diretos Semanais: Recursos e Consumo Físico

Se \(a_{ig}(m_{ij})\) é a demanda de recursos contratados por \(i\), o custo semanal **ativo, por atividade** pode ser diagnosticado a partir das tarifas contratuais compatíveis:

$$C_{ij}^{K,act}=H_i\sum_{g\in K}c_g^{act}\,a_{ig}(m_{ij}),$$

quando \(c_g^{act}\) é em R$/h, sem presumir que a soma por atividades reconstrói contratos compartilhados. **O desembolso contratual autoritativo do projeto** vem do livro de instâncias \(x_{gj}\), incluindo standby (§IX), e não da simples soma de envelopes por atividade.

Para bem consumível \(g\), seja \(U_{gij}\ge0\) a quantidade **física** atribuída à atividade \(i\) na semana \(j\). Seu custo é

$$\boxed{C_{ij}^{V}=\sum_{g\in V}p_g\,U_{gij}.}$$

A quantidade \(U_{gij}\) deve decorrer de taxas com unidades verificáveis, tempo efetivo, produção realizada e hipóteses de perda/ociosidade. Sob regra *por unidade produzida* \(U_{gij}=\kappa_{ig}^{out}q_{ij}\); sob regra por **hora real de operação**, a demanda depende dessas horas e pode mudar com \(F_i(m)\) e clima. A identidade antiga \(\gamma_i^{V,cat}\,q_{ij}/\rho_i\) é válida **somente** se a relação consumível/quantidade usada para deduzi-la for comprovadamente constante (#11/#13/#18).

---

## Parte VI — Agregação e Invariância Condicionada

$$C_i^{V}=\sum_j C_{ij}^{V}=\sum_{g,j}p_gU_{gij},\qquad
C^{cons}=\sum_iC_i^V=\sum_g p_gU_g,\qquad U_g=\sum_{i,j}U_{gij}.$$

Se, e **somente se**, \(U_{gij}=\kappa_{ig}^{out}q_{ij}\) (sem perdas nem consumo em standby) e \(p_g,\kappa_{ig}^{out}\) forem constantes, então

$$C_i^V=Q_i\sum_gp_g\kappa_{ig}^{out},$$

e o custo variável é **invariante ao cronograma** para escopo fixo. Sob gargalo de throughput com consumo por hora de equipe, material desperdiçado ou combustível parado, a hipótese pode falhar e a invariância não deve ser alegada.

O custo contratual do projeto inclui horas ativas e semanas/horas contratadas sem demanda. A soma \(\sum_iC_i^{K,act}\) é apenas diagnóstico, não substitui \(C^{pool}\) nem autoriza contabilizar o mesmo contrato repetidamente. O preço unitário operacional por atividade exige atribuição contábil inequívoca, quando disponível: \(p_i^{op}=C_i^{attrib}/Q_i\) para \(Q_i>0\).

---

## Parte VII — Razões Operacionais e Referência Comparável

Defina \(C_{ij}^{ref}>0\) e \(q_{ij}^{ref}>0\) de **uma mesma configuração física de referência explicitamente documentada**. Com \(q_{ij}>0\) e custo operacional comparável \(C_{ij}^{op}\), definam-se:

$$\zeta_{ij}=\frac{C_{ij}^{op}}{C_{ij}^{ref}},\qquad
\pi_{ij}=\frac{C_{ij}^{op}/q_{ij}}{C_{ij}^{ref}/q_{ij}^{ref}},\qquad
\chi_{ij}=\frac{q_{ij}}{q_{ij}^{ref}}.$$

A identidade **algébrica exata** é

$$\boxed{\zeta_{ij}=\chi_{ij}\pi_{ij}}.$$

Não substituir \(\chi_{ij}\) por \(\eta_{p,j}\eta_{w,j}\) sem provar que a composição e o volume de referência tornam essas razões equivalentes; a diferença de equipes, gargalo e a fração \(\varphi_i<1\) impedem essa igualdade em geral. Com \(q_{ij}=0\), \(\pi_{ij}\) é **indefinida**, não zero.

---

## Parte VIII — BDI Granular e Frações Financeiras Reais

Se \(C^k\ge0\) é o custo de cada categoria **obtido de lançamentos únicos** de recurso/consumível/indireto, o valor com BDI é

$$C^{\beta}=\sum_k(1+\beta^k)C^k,\qquad
\beta^{eq}=\frac{C^\beta}{\sum_kC^k}-1
=\frac{\sum_k\beta^kC^k}{\sum_kC^k},\quad \sum_kC^k>0.$$

A participação variável efetiva de uma semana, quando os lançamentos da base são reconciliados, é

$$\boxed{\delta_{ij}=\frac{C_{ij}^{V}}{C_{ij}^{K}+C_{ij}^{V}}},$$

não uma função universal de \(\eta_s\) ou de uma eficiência média baseada em número de frentes. Se as taxas médias por bloco \(\beta^K,\beta^V\) são calculadas das **mesmas bases**, \(\beta^{eq}_{ij}=(1-\delta_{ij})\beta^K+\delta_{ij}\beta^V\). Esse resultado depende de **pesos financeiros efetivos**, não de uma hipótese física de produtividade linear.

Permanecem pendentes em #11 os detalhes de rateio de contratos compartilhados, fechamento semanal parcial e comparação com catálogo não linear; não emitir GO utilizando as identidades antigas \(\bar\varepsilon_i=Q_i/(\rho_i H_iM_i)\), \(\delta_i(\bar\varepsilon)\) ou \(R_i=f_i^V+(1-f_i^V)/\bar\varepsilon_i\) como se fossem universais.

---

## Parte IX — Pool de Recursos Contratuais (Perpetuação)

### IX.1 Presença e ociosidade são grandezas contratuais

Se \(a_{ig}(m)\) indica unidades do tipo \(g\) necessárias para operar \(m\) frentes, sejam

$$\boxed{d_{gj}=\sum_{i\in\mathcal A_j}a_{ig}(m_{ij}),\
x_{gj}\ge d_{gj},\ s_{gj}=x_{gj}-d_{gj}\ge0.}$$

\(d\) é demanda física; \(x\) é presença sob contrato; \(s\) é recurso **pago sem demanda**, não equipe que deixou de ser mobilizada. Frentes independentes obedecem \(a_{ig}(m)=m n_g^i\); infraestrutura compartilhada exige demanda específica.

### IX.2 Custo mínimo de permanência e movimentos

$$\boxed{\min \sum_{gj}\big(c_{gj}^{act}d_{gj}+c_{gj}^{idle}s_{gj}\big)
+\sum_{e\in E}(c_e^{mob}+c_e^{demob})}$$

sujeito às restrições de capacidade, cobertura, disponibilidade, permanência e lead time. Cada movimento entra **uma única vez** na função objetivo/diário. No regime-base homogêneo, \(c^{act}=c^{idle}=c^{sem}\), portanto \(C^{pool,o}=\sum_{gj}c_g^{sem}x_{gj}\), separando MOB/DEMOB para contabilização indireta; standby descontado ou off-hire exigem variante tipada (#13).

Entre blocos separados por \(k\) semanas **vazias**, manter é viável se \(k\le G_g^{viável}\) e economicamente preferível quando \(k\,c_g^{idle}\le c_g^{demob}+c_g^{mob}\). No empate, preferir menos movimentos. Exemplo: demanda de um equipamento nas semanas 1 e 3, standby R$100 na semana 2, remobilização R$160 => manter é ótimo, embora fisicamente ocioso. Com transições gratuitas, manter standby de custo positivo não é ótimo.

### IX.3 Utilização e limite do certificado

Para cadeia contratual \(r\), \(T_r^{perm}=T_r^{act}+T_r^{idle}\); a fração \(f_r^{idle}=T_r^{idle}/T_r^{perm}\) (se \(T_r^{perm}>0\)) é diagnóstico temporal, **não** perda produtiva. A decomposição em níveis da demanda garante ótimo exato apenas para **pool homogêneo fungível com \(m\) e cronograma fixados**; não prova ótimo global de escolha simultânea \(m+\)cronograma\(+\)pool (#16). O custo real é reconstruído das instâncias/semana, nunca de envelopes individuais contados em duplicidade (#17/#20).

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

Custo efetivo conciliado: \(C^D=C^{pool}+C^{cons}\), \(C^{tot}=C^D+C^I\); standby, MOB/DEMOB, estoque e indiretos são lançados **uma vez**. BDI granular por categoria não é reaplicado sobre a soma:

$$\boxed{P=C^{D,\beta}+C^{I,\beta},\qquad \mu=\frac{P-C^{tot}}P}\quad (P>0).$$

A base de catálogo \(C^{cat}>0\) só é válida após declarar a **composição física e a base contratual de referência** (#11/#21). Quando comparável:

$$R=\frac{C^{tot}}{C^{cat}},\quad
\mathrm{BDI}^{impl}=\frac P{C^{cat}}-1,\quad
\beta^{eq}=\frac P{C^{tot}}-1=\frac{1+\mathrm{BDI}^{impl}}R-1.$$

**Atingir o piso de BDI não garante rentabilidade.** É necessário testar \(P>C^{tot}\) (ou margem mínima contratual) independentemente: equivale a \(\mathrm{BDI}^{impl}>R-1\), condição que não decorre de \(\mathrm{BDI}^{impl}\ge\mathrm{BDI}_{min}\). O piso regulatório só pode ser comparado à base legal aplicável; base não compatível => \`UNKNOWN\`.

Certificação GO exige fechamento físico, capacidade/recursos/estoque factíveis, reconciliação financeira, rentabilidade aprovada e conformidade regulatória em bases válidas. Enquanto as identidades lineares por frente de §§III/V–VIII não forem rederivadas para \(F(m)\) não linear (#11), **não emitir GO no regime geral** (#21/#23).

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