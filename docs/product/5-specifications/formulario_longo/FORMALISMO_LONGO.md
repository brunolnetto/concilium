# Formulário White-Box — Atividades, Pool de Recursos e Custos Indiretos

---

## §0 — Convenções de Notação [DERIVADO]

> **Contrato normativo P09-A:** unidades, domínios de mobilização, intervalos e política numérica são definidos em [CONVENCOES_NORMATIVAS.md](CONVENCOES_NORMATIVAS.md). As equações ainda em revisão permanecem explicitamente sinalizadas nas issues #10–#13.


**Regra de três slots** no superscrito. Nenhum símbolo carrega dois papéis.

| Slot | Valores | Significado |
|---|---|---|
| 1º — natureza | $\mathrm{K}$ | **contratual**: EQ + MO. Cobrado por semana mobilizada, não escala com produção |
| | $\mathrm{V}$ | **consumível**: MAT + COMB. Escala com produção realizada |
| 2º — regime | $\mathrm{cat}$ | **catálogo**: nominal, $\varepsilon = 1$ |
| | $\mathrm{op}$ | **operacional**: com $\varepsilon_{ij}$ realizado |
| 3º — markup | $\beta$ | com BDI aplicado. Ausente = sem BDI |

Exemplos: $\gamma_i^{\mathrm{K,cat}}$ · $C_{ij}^{\mathrm{V,op},\beta}$ · $\zeta_{ij} = C^{\mathrm{op}}_{ij}/C^{\mathrm{cat}}_{ij}$

---

## Parte I — Entrada: Definição das Atividades (formulário)

### I.1 Conjunto de atividades

$$\mathcal{A} = \{A_i\}_{i=1}^{n_{\text{ativ}}}$$

### I.2 Tupla da atividade

$$A_i = (Q_i,\ E_i,\ W_i,\ B_i)$$

| Campo | Tipo | Preenchido por |
|---|---|---|
| $Q_i$ | quantitativo total [un] | usuário |
| $E_i$ | equipe (§I.3) | usuário |
| $W_i$ | política de mobilização (§I.4) | usuário |
| $B_i$ | predecessores + completude parcial (§I.5) | usuário |
| $j_i^0$ | semana de início | **derivado** (schedule, §I.5) |
| $N_i$ | duração em semanas | **derivado** (fecho físico por enumeração limitada de duração e verificação do calendário, Parte IV/XIV) |
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

**MAT legado (proxy monetário, não volume físico).** Na ausência de `atributos_especificos.consumo_horario_fisico` e `atributos_especificos.unidade_fisica`, o catálogo pode fornecer somente `c_r` [R$/h] como **proxy de custo horário**. Não existem `κ_r` [unid_g/h] nem `p_g` [R$/unid_g] verificáveis nessa entrada: atribuir `κ_r=1` e `p_g=c_r` [R$/h] é dimensionalmente inválido. O proxy deve permanecer `UNVERIFIED`, sem volume físico inferido, preço unitário fictício nem autorização de GO. A identidade `c_r=κ_r·p_g` só é aplicável quando ambos os fatores físicos, suas unidades compatíveis e a procedência do preço estiverem declarados (ver #18/#23).

#### I.3.2 Produtividade como capacidade efetiva do grafo mobilizado

**Contrato normativo P10-A:** [Capacidade física, recurso e ociosidade](CAPACIDADE_E_RECURSOS.md). Equipes são a decisão de **capacidade**, não um fator extra de perda.

$$\boxed{F_i(m)=\max\text{-fluxo}(s_i,t_i;\mathcal G_i^D|_m)\quad[\mathrm{unid}_{Q_i}/h]}.$$

O grafo contém as frentes efetivamente alocadas e preserva gargalos físicos compartilhados. Para frentes independentes pode valer $F_i(m)=m\rho_i^{front}$; para grafos mistos, $F_i(m)$ pode saturar. A capacidade de pico $\rho_i^{peak}=F_i(m_i^{max})$ não pode ser confundida com a produtividade de uma única frente.

$\boxed{\varepsilon_{ij}^{exog}=\eta_{p,j}\eta_{w,j},\qquad B_{ij}=F_i(m_{ij})h_id_i\varepsilon_{ij}^{exog}}.$

**Definição única de produtividade (P10-B):** somente \(F_i(m)\) [unidades/h] é produtividade física. A praticabilidade \(p_j\), o calendário \(c_j\) e a disponibilidade da jornada \(a_i\) formam um **único fator de disponibilidade** \(\varepsilon_{ij}^{exog}=p_jc_ja_i\); no esquema legado isso corresponde a \(\eta_{p,j}\eta_{w,j}\), com qualquer \(\eta_w\) neutro na ausência de perda operacional realmente observada. Em particular, fatores já incorporados em horas efetivas ou na base da taxa não devem ser reaplicados. Calendário e praticabilidade alteram \(B_{ij}\), **não** o valor de \(F_i(m)\); \(\varphi_i\) não é eficiência.


Não se multiplica $B$ por $m$ novamente e não existe um fator $\eta_s$ de perda por número de equipes. A razão opcional $\alpha_i(m)=F_i(m)/F_i(m_i^{max})$ é **diagnóstico de capacidade**, não redutor da produção.

A composição de equipes determina simultaneamente a demanda $d_{gj}=\sum_i a_{ig}(m_{ij})$ de recursos físicos. Recurso contratado presente $x_{gj}$ e standby $s_{gj}=x_{gj}-d_{gj}\ge0$ pertencem ao problema de pool, não ao cálculo de eficiência de produção. Veja definições, prova de ótima ausência de standby sob transição gratuita e contraexemplo com perpetuação econômica no contrato P10-A.

### I.4 Política de mobilização $W_i$

$$W_i = (m_i^0,\ \mu_i^+,\ m_i^1,\ \mu_i^-,\ m_i^{\max}) \in \mathbb{N}_{>0}\times\mathbb{N}_{\ge0}\times\mathbb{N}_{>0}\times\mathbb{N}_{\ge0}\times\mathbb{N}_{>0}$$

| Símbolo | Significado |
|---|---|
| $m_i^0$ | nº de frentes na semana de início |
| $\mu_i^+$ | taxa de ramp-up [frentes/semana] |
| $m_i^{\max}$ | nº máximo de frentes concorrentes (platô) |
| $\mu_i^-$ | taxa de ramp-down [frentes/semana] |
| $m_i^1$ | nº de frentes na última semana (piso final, nunca zero) |

**Perfil trapezoidal** — mínimo de três retas, semana relativa $\tau = j - j_i^0 \in \{0,\ldots,N_i-1\}$:

$$\boxed{m_i(\tau) = \min\!\Big(m_i^0 + \mu_i^+\tau,\quad m_i^{\max},\quad m_i^1 + \mu_i^-(N_i-1-\tau)\Big)}$$

**Caso degenerado retangular** — somente com rampas nulas **e** extremos iguais ao máximo:

$$\bigl(\mu_i^+=\mu_i^-=0\bigr)\land\bigl(m_i^0=m_i^1=m_i^{\max}\bigr)\implies m_i(\tau)=m_i^{\max}\quad\forall\,\tau\in\{0,\ldots,N_i-1\}$$

Quando as rampas são nulas mas os extremos não coincidem com o máximo, vale apenas $m_i(\tau)=\min(m_i^0,m_i^1,m_i^{\max})$; por exemplo, $(m_i^0,m_i^1,m_i^{\max})=(1,1,4)$ produz uma frente, **não** quatro. A forma retangular no máximo exige as três igualdades; nessas condições, $W_i$ reduz-se a um único parâmetro de frota, constante durante toda a atividade.

$$m_{ij} = \begin{cases} m_i(j-j_i^0) & j\in[j_i^0,\,j_i^0+N_i-1] \\ 0 & \text{caso contrário}\end{cases}$$

**Determinação de \(N_i\) condicionada ao início absoluto (P12-A).** Fixado \(s=j_i^0\), a capacidade acumulada de uma duração candidata é \(\Pi_i(N;s)=\sum_{\tau=0}^{N-1}F_i(m_i(\tau;N))H_i p_{s+\tau}c_{s+\tau}a_i\). Os fatores são aplicados uma única vez; se \(H_i\) já representa horas efetivas, usar \(a_i=1\). Alterar o início absoluto altera as disponibilidades das semanas testadas e pode mudar \(N_i\).

**Monotonicidade demonstrada, porém somente da capacidade isolada.** Sob a rampa canônica com \(\mu_i^\pm\ge0\), \(m_i(\tau;N+1)\ge m_i(\tau;N)\) para \(\tau<N\). Sendo \(F_i(m)\) não decrescente e a disponibilidade semanal não negativa, \(\Pi_i(N+1;s)\ge\Pi_i(N;s)\) para **início absoluto fixo**. A prova está em [CALENDARIO_E_LIBERACAO_FISICA.md](CALENDARIO_E_LIBERACAO_FISICA.md). Não existe crescimento **estrito** universal: clima nulo ou gargalo saturado geram igualdade. A busca binária é admissível apenas para o subproblema escalar de fechar \(Q_i\) com essa prova; recursos compartilhados, lags e RCPSP podem destruir monotonicidade da **viabilidade conjunta**, que exige enumeração/solver e validação explícita. Rejeitar resultado se o horizonte não fecha \(Q_i\), ou se recursos/predecessores são incompatíveis. A antiga condição \(r+d\le N_i\) não define suas variáveis e não constitui gate.

**Contrato e vetores:** [CALENDARIO_E_LIBERACAO_FISICA.md](CALENDARIO_E_LIBERACAO_FISICA.md) (#12/#15).

### I.5 Predecessores e completude parcial

$$B_i \subseteq \mathcal{A}\setminus\{A_i\}, \qquad \theta_i : B_i \to (0,1]$$

Para $b\in B_i$, $\theta_i(b)$ é a fração de escopo de $b$ exigida antes que $A_i$ possa iniciar.

**Medida de completude em quantitativo:**

$$\Phi_b(j) = \frac{1}{Q_b}\sum_{j'=j_b^0}^{j} q_{b,j'}$$

**Restrição de início:**

$\boxed{j_i^0\ge\max_{b\in B_i}\Big(1+\ell_{b\to i}+\min\{j:\Phi_b(j)\ge\theta_i(b)\}\Big)}$

**Fronteira de semana (Q–FS):** \(\Phi_b(j)\) mede a produção **acumulada ao fim** da semana \(j\). O sucessor não pode iniciar na própria semana em que a predecessora atinge o limiar; o primeiro começo admissível é \(j+1+\ell_{b\to i}\), com \(\ell_{b\to i}\in\mathbb N_0\) semanas livres adicionais. Arestas com limiar não atingido são inviáveis. Arestas SS/FF, lags negativos ou execução sub-semanal exigem outra semântica explícita, não esta fórmula. Ver [CALENDARIO_E_LIBERACAO_FISICA.md](CALENDARIO_E_LIBERACAO_FISICA.md).

**Tipo de $\theta_i(b)$** — declarar por aresta, pois a semântica difere sob $\varepsilon_{ij}$ variável:

| Tipo | Condição de início | Formulação | Quando usar |
|---|---|---|---|
| **Q** (quantidade) | $\sum_{j'\le j} q_{b,j'} \ge \theta_i(b)\,Q_b$ | $\Phi_b(j) \ge \theta_i(b)$ | progresso físico real (defensável) |
| **T** (tempo) | $j \ge j_b^0 + \theta_i(b)\,N_b$ | fração de calendário | representação Gantt / MS Project |

Sob $\varepsilon_{ij}$ variável as duas **não coincidem**: tipo T libera o sucessor mais cedo que o fisicamente entregue quando há semanas improdutivas. Tipo Q é o adotado neste formulário — restrição exata via rastreamento da produção acumulada realizada $q_{b,j'}$ no solver, incluindo o fechamento fracionário da última semana (Parte IV). O caso $\theta_i(b)=1$ recupera a precedência fim-início clássica em ambos os tipos.

---

## Parte II — Parâmetros e Constantes Globais

$$s_{\text{mes}} = \frac{365\times3+366}{4\times12\times7} = \frac{1461}{336} \approx 4{,}3482 \ \text{semanas/mês}$$

$$d_i \in \{4,5,6\}\ \text{dias úteis/semana}, \qquad h_i \in \{6,8\}\ \text{horas/dia}, \qquad h_id_i \equiv \text{horas/semana da equipe }i$$

Taxas de BDI (entrada; valores de referência do modelo AGIS entre parênteses):

$$\beta^{EQ},\ \beta^{MO}\ (\approx29{,}97\%),\ \beta^{MAT},\ \beta^{COMB}\ (\approx4\%),\ \beta^{IND}\ (\approx25{,}21\%)$$

---

## Parte III — Custo Horário de Catálogo ($\gamma$)

**Regime de validade restrita — #11:** as identidades históricas de custo que usam $\gamma/\rho$ exigem escala linear de capacidade por frente e consumo unitário efetivo invariável. Elas **não** são normativas para $F_i(m)$ não linear, variação de tarifa por composição ou fechamento parcial até rederivação e teste pelo oráculo; não usar estas relações, isoladamente, para emitir GO.

$$\gamma_i^{EQ} = \sum_{r\in R_i,\,\text{cat}(r)=EQ} c_r n_r \qquad \text{(análogo para } MO, MAT, COMB\text{)}$$

$$\gamma_i^{\mathrm{K,cat}} \equiv \gamma_i^{EQ}+\gamma_i^{MO} \qquad\text{[contratual: cobrado por semana mobilizada]}$$
$$\gamma_i^{\mathrm{V,cat}} \equiv \gamma_i^{MAT}+\gamma_i^{COMB} \qquad\text{[consumível: escala com produção]}$$
$$\gamma_i^{\mathrm{cat}} = \gamma_i^{\mathrm{K,cat}}+\gamma_i^{\mathrm{V,cat}}\qquad\text{[R\$/h]}$$

$$f_i^{\mathrm V} = \gamma_i^{\mathrm{V,cat}}/\gamma_i^{\mathrm{cat}} \qquad\text{[fração consumível do custo de catálogo]}$$

$$p_i^{\mathrm{cat}} = \gamma_i^{\mathrm{cat}}/\rho_i \qquad\text{[R\$/un — preço unitário de catálogo]}$$

$$\boxed{C_i^{\mathrm{cat}} \equiv p_i^{\mathrm{cat}}\,Q_i = \frac{\gamma_i^{\mathrm{cat}}\,Q_i}{\rho_i}} \qquad\text{[R\$ — custo de catálogo da atividade; base para diagnósticos e para o envelope do projeto, Parte XIII]}$$

---

## Parte IV — Cronograma Semanal

**Base dimensional da semana (P09-D).** A notação `F_i(m_ij) h_i d_i ε_ij` é abreviação do integral por célula de uma semana: `F_i(m_ij) [u_i/h] × h_i d_i [h/semana] × Δw_j [semana] × ε_ij`, com **`Δw_j = 1 semana`**, resultando em `B_ij [u_i]` e `q_ij [u_i]`. Não interpretar a taxa `u_i/semana` como quantidade antes de integrar a célula. `φ_i` não multiplica K da semana contratada.


Eficiência exógena semanal: $\varepsilon_{ij}^{exog}=\eta_{p,j}\eta_{w,j}\in[0,1]$. A capacidade instalada já inclui todas as equipes e gargalos:

$\boxed{B_{ij}=F_i(m_{ij})h_id_i\varepsilon_{ij}^{exog},\qquad q_{ij}=\min\{(Q_i-\sum_{k<j}q_{ik})_+,B_{ij}\}}.$

**Fechamento exato de escopo.** Seja $j_i^1 \equiv j_i^0+N_i-1$ a última semana ativa de $A_i$, obtida pela busca limitada em $N_i$ e verificação de viabilidade (Parte XIV, Fase 1) sobre o perfil nominal $\{m_i(\tau)\}$ de $W_i$. Nas semanas interiores $j<j_i^1$, a produção usa o perfil nominal integralmente. Na última semana, o quantitativo residual fecha exatamente o escopo:

$$q_{i,j_i^1} = Q_i - \sum_{j=j_i^0}^{j_i^1-1} q_{ij}$$

A semana de fechamento precisa possuir capacidade positiva. A fração de fechamento é uma métrica de uso do escopo, não perda física de produtividade:

$$\boxed{\varphi_i=\frac{q_{i,j_i^1}}{F_i(m_i(N_i-1))h_id_i\varepsilon_{i,j_i^1}^{exog}}\in(0,1]}$$

representando a fração da capacidade nominal da última semana efetivamente utilizada para completar o escopo. A frota mobilizada ($m_{ij}$, e portanto o custo contratual $C_{ij}^{\mathrm{K,op}}$, Parte V) permanece no valor nominal do perfil na última semana — recursos contratuais (EQ/MO) são cobrados pela semana mobilizada independentemente da fração de produção efetivamente necessária naquela semana (§0). Apenas o consumível é prorateado pela produção realizada, via $\varphi_i$, garantindo o fecho exato do escopo:

$$\sum_{j=j_i^0}^{j_i^1} q_{ij} = Q_i \qquad\text{(exato, por construção)}$$

Contadores: $M_i \equiv \sum_j m_{ij}$ (frente-semanas totais, ao valor nominal — inclui a última semana integralmente), $N_i = |\{j:m_{ij}>0\}|$ (semanas de calendário ativas).

$$\mathcal{A}_j \coloneqq \{A_i\in\mathcal{A} : j\in[j_i^0,\,j_i^0+N_i-1]\}$$

---

## Parte V — Custo Direto Semanal (sem BDI)

**Regime de validade restrita — #11:** as identidades históricas de custo que usam $\gamma/\rho$ exigem escala linear de capacidade por frente e consumo unitário efetivo invariável. Elas **não** são normativas para $F_i(m)$ não linear, variação de tarifa por composição ou fechamento parcial até rederivação e teste pelo oráculo; não usar estas relações, isoladamente, para emitir GO.

$$C_{ij}^{\mathrm{K,op}} = \gamma_i^{\mathrm{K,cat}}\,h_id_i\,m_{ij}\qquad\text{[R\$] — nominal em toda semana ativa, inclusive a última}$$

$$C_{ij}^{\mathrm{V,op}} = \gamma_i^{\mathrm{V,cat}}\cdot\frac{q_{ij}}{\rho_i}\qquad\text{[R\$]}$$

Nas semanas interiores, $q_{ij}/\rho_i \equiv \varepsilon_{ij}h_id_im_{ij}$ por definição de $q_{ij}$ (Parte IV) — a formulação acima generaliza a forma tempo-a-tempo e permanece exata na semana de fechamento, onde $q_{ij}$ é o residual e não $\varepsilon_{ij}h_id_im_{ij}$ diretamente.

$$C_{ij}^{\mathrm{op}} = C_{ij}^{\mathrm{K,op}}+C_{ij}^{\mathrm{V,op}}\qquad\text{[R\$]}$$

---

## Parte VI — Custo Direto Total por Atividade (sem BDI)

$$C_i^{\mathrm{K,cat}} = \frac{Q_i\,\gamma_i^{\mathrm{K,cat}}}{\rho_i}\qquad\text{[R\$] — catálogo, parcela contratual, à eficiência nominal}$$
$$C_i^{\mathrm{V,cat}} = \frac{Q_i\,\gamma_i^{\mathrm{V,cat}}}{\rho_i}\qquad\text{[R\$] — catálogo, parcela consumível}$$
$$C_i^{\mathrm{K,op}} = \sum_{j} C_{ij}^{\mathrm{K,op}} = \gamma_i^{\mathrm{K,cat}}\,h_id_i\,M_i\qquad\text{[R\$]}$$
$$C_i^{\mathrm{V,op}} = \sum_{j} C_{ij}^{\mathrm{V,op}} = \frac{\gamma_i^{\mathrm{V,cat}}}{\rho_i}\sum_j q_{ij}\qquad\text{[R\$]}$$
$$C_i^{\mathrm{op}} = C_i^{\mathrm{K,op}}+C_i^{\mathrm{V,op}}\qquad\text{[R\$]}$$
$$p_i^{\mathrm{op}} = C_i^{\mathrm{op}}/Q_i\qquad\text{[R\$/un]}$$

**Identidade — invariância do consumível.** Usando o fecho de escopo exato $\sum_jq_{ij}=Q_i$ (Parte IV):

$$\boxed{C_i^{\mathrm{V,op}} \equiv C_i^{\mathrm{V,cat}} = \frac{Q_i\,\gamma_i^{\mathrm{V,cat}}}{\rho_i}}\qquad\text{(exato, por construção do fechamento de escopo)}$$

O consumível operacional **é** o consumível de catálogo — não há inflação por ineficiência. O total de material/combustível depende apenas de $Q_i$, nunca de quantas semanas foram necessárias para executar. Esta identidade **não vale** para o contratual: $C_i^{\mathrm{K,op}}=\gamma_i^{\mathrm{K,cat}}h_id_iM_i$ cresce quando a eficiência piora (mais frente-semanas $M_i$ para fechar o mesmo $Q_i$, já que $M_i$ conta a semana de fechamento integralmente, não prorateada).

---

## Parte VII — Razões Operacional/Catálogo (semanais)

**Regime de validade restrita — #11:** as identidades históricas de custo que usam $\gamma/\rho$ exigem escala linear de capacidade por frente e consumo unitário efetivo invariável. Elas **não** são normativas para $F_i(m)$ não linear, variação de tarifa por composição ou fechamento parcial até rederivação e teste pelo oráculo; não usar estas relações, isoladamente, para emitir GO.

Custo semanal de catálogo (pool e consumível à taxa nominal, sem desconto de $\varepsilon_{ij}$):

$$C_{ij}^{\mathrm{cat}} = \gamma_i^{\mathrm{cat}}\,h_id_i\,m_{ij}\qquad\text{[R\$]}$$

Preço unitário operacional semanal:

$$p_{ij}^{\mathrm{op}} = C_{ij}^{\mathrm{op}}/q_{ij}\qquad\text{[R\$/un]}$$

Razões:

$$\zeta_{ij} = \frac{C_{ij}^{\mathrm{op}}}{C_{ij}^{\mathrm{cat}}} = \frac{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{cat}}}\qquad[\ ]$$

$$\pi_{ij} = \frac{p_{ij}^{\mathrm{op}}}{p_i^{\mathrm{cat}}} = \frac{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}}{\varepsilon_{ij}\,\gamma_i^{\mathrm{cat}}}\qquad[\ ]$$

$$\boxed{\zeta_{ij} = \varepsilon_{ij}\cdot\pi_{ij}}$$

Usando a fração consumível $f_i^{\mathrm V}$ (Parte III):

$$\zeta_{ij} = 1-(1-\varepsilon_{ij})\,f_i^{\mathrm V}, \qquad \pi_{ij} = \frac{1}{\varepsilon_{ij}}-\left(\frac{1}{\varepsilon_{ij}}-1\right)f_i^{\mathrm V}$$

$\zeta_{ij}$ é diagnóstico local por semana — não deve ser somado ingenuamente para recuperar um "$\zeta_i$" de atividade.

---

## Parte VIII — Camada BDI (direta, por atividade)

**Regime de validade restrita — #11:** as identidades históricas de custo que usam $\gamma/\rho$ exigem escala linear de capacidade por frente e consumo unitário efetivo invariável. Elas **não** são normativas para $F_i(m)$ não linear, variação de tarifa por composição ou fechamento parcial até rederivação e teste pelo oráculo; não usar estas relações, isoladamente, para emitir GO.

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

**Eficiência média ponderada por frente-semana** — agrega $\delta_{ij}$ em um único fator por atividade:

$$\bar\varepsilon_i \equiv \frac{\sum_j\varepsilon_{ij}\,m_{ij}}{M_i}$$

$$\delta_i = \frac{\bar\varepsilon_i\,\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{K,cat}}+\bar\varepsilon_i\,\gamma_i^{\mathrm{V,cat}}} \;\left(=\frac{C_i^{\mathrm{V,op}}}{C_i^{\mathrm{op}}}\right)$$

$$\boxed{\beta_i^{\mathrm{eq}} \equiv \frac{C_i^{D,\beta}}{C_i^{\mathrm{op}}}-1 = (1-\delta_i)\,\beta_i^{\mathrm K}+\delta_i\,\beta_i^{\mathrm V}}$$

---

## Parte IX — Pool de Recursos Contratuais (Perpetuação)

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

## Parte X — Consumíveis: Aquisição e Posse

Separável por atividade sem ambiguidade. Por identidade direta $C_i^{\mathrm{V,op}} \equiv C_i^{\mathrm{V,cat}}$ (Parte VI):

**Custo de aquisição** ($C^{\mathrm{cons}}$) — **direto**, entra em $C^D$:

$$\boxed{C^{\mathrm{cons}} = \sum_{i\in\mathcal{A}} \frac{Q_i\,\gamma_i^{\mathrm{V,cat}}}{\rho_i} = \sum_g c_g^{\mathrm{cons}}\, U_g}$$

$$C^{\mathrm{cons},\beta} = \sum_{i\in\mathcal{A}} \gamma_i^{\mathrm{V,cat},\beta}\cdot\frac{Q_i}{\rho_i}$$

**Custo de posse** ($C^{\mathrm{inv}}$) — **indireto**, entra em $C^{ind}$ com $\beta^{\mathrm{IND}}$:

$$\boxed{C^{\mathrm{inv}} = \sum_g\sum_j c_g^{\mathrm{hold}}\, S_{g,j}}$$

Posse de estoque não é consumo produtivo — é infraestrutura de suprimento, análogo ao bloco VM. **Não** entra em $C^D$.

Diferente do contratual, $C^{\mathrm{cons}}$ não requer otimização de cadeias — a soma por atividade é exata, e coincide exatamente com a produção realizada dado o fechamento de escopo da Parte IV.

---

## Parte XI — Custo Direto Total do Projeto

$$C^D = C^{\mathrm{pool}}+C^{\mathrm{cons}}\qquad\text{[R\$ — sem BDI]}$$
$$C^{D,\beta} = C^{\mathrm{pool},\beta}+C^{\mathrm{cons},\beta}\qquad\text{[R\$ — com BDI; nível projeto, distinto de }C_i^{D,\beta}\text{ (atividade)}$$
$$\beta^D = C^{D,\beta}/C^D-1$$

---

## Parte XII — Custos Indiretos

### XII.1 Estrutura: categorias e drivers

$$\mathcal{L} = \{ADM, TOP, LAB, QSMS, MOB^{\text{site}}, \ldots\}\quad\text{(conjunto extensível)}$$

$$\text{driver}(l)\in\{\texttt{perm},\ \texttt{onetime}\}$$

- `perm`: custo mensal fixo enquanto o projeto está mobilizado (ADM, TOP, LAB, QSMS)
- `onetime`: evento único de borda — mobilização/desmobilização de canteiro ($MOB^{\text{site}}$)

$n = j^{\max}-j^{\min}$ (makespan do projeto em semanas). $j^{\min}=\min_i j_i^0$, $j^{\max}=\max_i(j_i^0+N_i)$.

### XII.2 Entrada por categoria

$$l = \Bigl(\text{driver}(l),\ \{\Gamma_l^{k,\text{mensal}}\}_{k\in\{MO,EQ,COMB\}},\ (c_l^{\text{mob}},c_l^{\text{demob}})\ \text{ou}\ \Gamma_l^{VM,\text{mensal}}\Bigr)$$

### XII.3 Custo semanal por sub-categoria

**Driver `perm`:**

$$\gamma_l^{k,\text{sem}} = \frac{\Gamma_l^{k,\text{mensal}}}{s_{\text{mes}}}, \qquad m_l(j)=1 \ \ \forall j\in\{0,\ldots,n-1\}$$

**Driver `onetime`:**

$$\gamma_l^{VM,\text{sem}}(j) = c_l^{\text{mob}}\,\mathbb{1}[j=j^{\min}] + c_l^{\text{demob}}\,\mathbb{1}[j=j^{\max}-1]$$

*(para $n=1$: mob e demob caem na mesma semana, somando-se)*

$$C_{lj}^{\text{ind},o} = \Bigl(\gamma_l^{MO,\text{sem}}+\gamma_l^{EQ,\text{sem}}+\gamma_l^{COMB,\text{sem}}+\gamma_l^{VM,\text{sem}}(j)\Bigr)\cdot m_l(j)$$

### XII.4 Camada BDI do indireto

$$\boxed{C_{lj}^{\text{ind},\beta} = \Bigl[\gamma_l^{MO,\text{sem}}(1+\beta^{MO})+\gamma_l^{EQ,\text{sem}}(1+\beta^{EQ})+\gamma_l^{COMB,\text{sem}}(1+\beta^{COMB})+\gamma_l^{VM,\text{sem}}(j)(1+\beta^{IND})\Bigr]\cdot m_l(j)}$$

**Totais por categoria:**

$$C_l^{\text{ind},o} = \sum_j C_{lj}^{\text{ind},o}$$
$$C_l^{\text{ind},\beta} = \Gamma_l^{MO}(1+\beta^{MO})+\Gamma_l^{EQ}(1+\beta^{EQ})+\Gamma_l^{COMB}(1+\beta^{COMB})+\Gamma_l^{VM}(1+\beta^{IND})$$

### XII.5 Mobilização do pool de equipamento (indireta, por cadeia)

$$\boxed{C^{MOB,eq,o} = \sum_r N_{\text{chains}}^r\cdot(c_r^{\text{mob}}+c_r^{\text{demob}})}, \qquad C^{MOB,eq,\beta} = (1+\beta^{IND})\cdot C^{MOB,eq,o}$$

### XII.6 Totais do indireto

$$C^{ind} = \sum_{l\in\mathcal{L}} C_l^{\text{ind},o} + C^{MOB,eq,o} + C^{\mathrm{inv}}$$
$$C^{ind,\beta} = \sum_{l\in\mathcal{L}} C_l^{\text{ind},\beta} + C^{MOB,eq,\beta} + C^{\mathrm{inv}}\,(1+\beta^{\mathrm{IND}})$$
$$\bar\beta^{ind} = C^{ind,\beta}/C^{ind}-1$$

---

## Parte XIII — Síntese: Preço Total e Viabilidade

**Custo de catálogo** (agregado por atividade):

$$C^{\mathrm{cat}} = \sum_{i\in\mathcal{A}} C_i^{\mathrm{cat}} = \sum_{i\in\mathcal{A}} \frac{\gamma_i^{\mathrm{cat}}\,Q_i}{\rho_i}\qquad\text{[R\$ — envelope de catálogo, base de precificação]}$$

$$C^{\mathrm{tot}} = C^D+C^{ind} \qquad\text{[R\$ — custo operacional total, sem BDI]}$$

**Preço de venda e BDI implícito.** O preço é a soma dos blocos direto e indireto já com a camada granular de $\beta$ aplicada (Partes VIII e XII):

$$P \equiv C^{D,\beta}+C^{ind,\beta} \qquad\text{[R\$ — preço de venda]}$$

O BDI não é um segundo parâmetro de markup somado independentemente sobre $C^{\mathrm{cat}}$: é a taxa agregada, **derivada**, resultante de aplicar a camada granular de $\beta$'s — uma por categoria de recurso ($\beta^{EQ},\beta^{MO},\beta^{MAT},\beta^{COMB},\beta^{IND}$) — e agregá-la ao nível do envelope de catálogo:

$$\boxed{\mathrm{BDI} \equiv \frac{P}{C^{\mathrm{cat}}}-1}$$

Não há dupla contagem: existe uma única camada de markup, aplicada item a item nas Partes VIII e XII; o BDI é apenas a leitura agregada dessa mesma camada, útil para comparação com o piso regulatório. Categorias de custo indireto que fisicamente compõem a estrutura clássica de BDI (administração central, canteiro) já estão computadas dentro de $C^{ind,\beta}$ com seu próprio $\beta^{IND}$ — não devem ser adicionadas novamente como percentual do BDI agregado; $\mathrm{BDI}_{\mathrm{TCU,min}}$ funciona como **piso de verificação** sobre a taxa agregada resultante, não como um segundo insumo a ser somado.

$$R = C^{\mathrm{tot}}/C^{\mathrm{cat}}, \qquad \beta^{\mathrm{eq}} = P/C^{\mathrm{tot}}-1, \qquad \mu = (P-C^{\mathrm{tot}})/P$$

**Condição de viabilidade:**

$$\boxed{\mathrm{BDI} \;\ge\; \mathrm{BDI}_{\mathrm{TCU,min}}}$$

$\mathrm{BDI}_{\mathrm{TCU,min}}$ é determinado pela fórmula multiplicativa TCU (overhead não capturado nos $\beta$'s granulares, lucro mínimo e tributos). A expressão $\mathrm{BDI}>R-1$ não é condição independente: substituindo $P=C^{\mathrm{cat}}(1+\mathrm{BDI})$ e $C^{\mathrm{tot}}=R\cdot C^{\mathrm{cat}}$ obtém-se $\beta^{\mathrm{eq}}>0$, que é a definição de $P>C^{\mathrm{tot}}$ reescrita — sem conteúdo analítico além da própria premissa. $R$ é **diagnóstico**: evidencia quanto do custo provém de ineficiência prevista.

---

## Parte XIV — Algoritmo

O algoritmo opera em **9 fases sequenciais**. As Fases 0 e 1 requerem solvers externos; as Fases 2–9 são computações exatas dadas as saídas anteriores.

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
    // F_i(m_ij) deriva da composição física mobilizada, sem penalidade η_s
    // ε_exog_ij = η_{p,j} · η_{w,j}; demanda d_gj deriva do mesmo m_ij

  Para cada recurso r:
    c_r^mob, c_r^demob             — custos de mobilização/desmobilização
    G_r^viável                     — gap máximo absoluto [semanas]
    // c_r^standby ≡ c_r^sem: pool é custo de permanência puro (§IX.3)

  Categorias indiretas:
    {(l, driver(l), {Γ_l^{k,mensal}}, c_l^mob, c_l^demob)}_{l ∈ L}
```

**Status de conformidade:** as fases produtivas devem derivar capacidade via $F_i(m)$ (contrato P10-A); derivadas financeiras da fórmula antiga estão bloqueadas por #11 até certificação.

### XIV.0 — Fase 0: Função de capacidade da composição

```
Para cada i:
  Se grafo sinergia G_i presente:
    Para m ∈ {0,...,m_i^max}:
      F_i(m) ← max-fluxo(G_i^D | m)  // gargalos compartilhados preservados
  Se há taxa externa certificada rho_i^front POR FRENTE independente:
    F_i(m) ← m · rho_i^front
  Se taxa calibrada para configuração inteira m_cal:
    Exigir modelo explícito que mapeie m→F_i(m), sem extrapolação implícita

  Validar F_i(m)>0 para as configurações com produção requerida.
  F_i(0) ← 0
  rho_i^peak ← F_i(m_i^max)  // apenas diagnóstico, não fator multiplicativo

SAÍDA: {F_i(m)} por atividade, com fontes/capacidades auditáveis.
```

### XIV.1 — Fase 1: Início absoluto, produção semanal e calendário

```text
Pré-condição: F_i(m) e fontes de capacidade, calendário e horizonte J_max.
Para cada atividade i em ordem topológica de precedências Q–FS:
  Para cada predecessor b:
    release_b ← menor semana j em que Σ_{k≤j}q_bk ≥ θ_{b→i}Q_b
    Se inexistente: INFEASIBLE (não liberar)
  s_i ← max_b (release_b + 1 + lag_{b→i})  // semana seguinte ao limiar
  Se sem predecessores: s_i ← primeira semana admissível do horizonte

  Para N em {1, ..., J_max−s_i+1}:  // enumerar, sem binária implícita
    perfil ← RampProfile.build(N,W_i)
    Para τ em {0,...,N−1}:
      j ← s_i+τ
      B_ij ← F_i(perfil[τ]) H_i p_j c_j a_i
    Se Σ_j B_ij < Q_i: continuar para N+1
    Se capacidade RCPSP/conflito/release for inválida: re-solver
    Senão: aceitar N e perfil; sair
  Se nenhuma combinação é factível: INFEASIBLE / NOGO

  saldo ← Q_i
  Para j∈[s_i,s_i+N_i) em ordem:
    q_ij ← min(saldo,B_ij); saldo ← saldo−q_ij
  Exigir saldo≈0 dentro da tolerância declarada, sem arredondamento físico
  j_i^1 ← última semana com produção positiva
  φ_i ← q_i,j_i^1/B_i,j_i^1, com B_i,j_i^1>0
  Revalidar recursos compartilhados e liberações APÓS cada deslocamento.
  Sem solução dentro dos limites ⇒ INFEASIBLE; dado ausente ⇒ UNKNOWN.
SAÍDA: (s_i,N_i,m_ij,F_i(m_ij),B_ij,q_ij,φ_i) e evidência RCPSP.
```

A execução completa de reescalonamento e prova de todas as restrições compete a #15; este documento define a obrigação e **não certifica que o runtime atual a satisfaz**.

### XIV.2 — Fase 2: Taxas Horárias de Catálogo

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

**Suspensão de certificação financeira:** as atribuições de custos nesta fase ainda representam a hipótese linear por frente, **não** o caso geral de F(m) com gargalo ou despesa variável por composição. A fase física corrigida é normativa; as contas financeiras dependem de #11/#17/#20 para certificação, como demonstrado no contrato P10-A.

```
Para cada i ∈ A, para cada j ∈ [j_i^0, j_i^0 + N_i - 1]:
  Se j < j_i^0 + N_i - 1:
    q_{ij} ← F_i(m_{ij}) · ε_exog_ij · h_i · d_i        [semana interior; sem η_s]
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

```
// Decomposição por nível (histograma): para um tipo fungível homogêneo, a alocação
// ótima decompõe-se em decisões independentes por "fatia" de altura unitária — cada
// fatia corresponde a uma cadeia de perpetuação da Parte IX. Ref.: SDVSP — Freling,
// Wagelmans & Paixão (2001).

C^{pool} ← 0; C^{pool,β} ← 0; C^{MOB,eq} ← 0; C^{MOB,eq,β} ← 0

Para cada tipo τ ∈ T:
  n_j(τ) ← Σ_{i: j ∈ [j_i^0, j_i^0+N_i-1]} a_iτ(m_ij) ∀j // linear: a_iτ(m)=m·n_τ^i
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

**Reconciliação:** no regime de tarifas distintas, o livro de instâncias deve publicar tanto $C^{pool}=\sum_{gj}(c_{gj}^{act}d_{gj}+c_{gj}^{idle}s_{gj})$ quanto $C^{pool,\beta}=\sum_{gj}(1+\beta_{cat(g)})(c_{gj}^{act}d_{gj}+c_{gj}^{idle}s_{gj})$, com tarifas normalizadas para a mesma base semanal. $C^{MOB/DEMOB}$ e $C^{MOB/DEMOB,\beta}$ entram somente no livro de indiretos. No regime homogêneo-base, a expressão anterior $\sum_\tau sem_\tau c_\tau^{sem}$ é caso particular.

**Limite de optimalidade:** a minimização de cadeias por nível é exata somente **condicionada ao perfil de equipes e cronograma fixados**. A otimização global de {m, cronograma, pool} permanece questão conjunta (#15/#16). Standby é presença paga não demandada, não eficiência de produção.

### XIV.5 — Fase 5: Estoque (Consumíveis)

```
C^{cons} ← Σ_i γ_i^{V,cat} · Q_i / ρ_i
  // Exato por construção: Σ_i γ_i^{V,cat}·Q_i/ρ_i ≡ Σ_i C_i^{V,op} (fecho de escopo, Parte IV)

Para cada i:
  γ_i^{V,cat,β} ← (1+β^MAT) · γ_i^MAT + (1+β^COMB) · γ_i^COMB

C^{cons,β} ← Σ_i γ_i^{V,cat,β} · Q_i / ρ_i

// C^{inv} calculado na Fase 7 (Indireto) a partir de S_{g,j} disponível após Fase 3

SAÍDA: C^{cons}, C^{cons,β}
```

### XIV.6 — Fase 6: Custo Direto Total

```
C^D    ← C^{pool} + C^{cons}
C^{D,β} ← C^{pool,β} + C^{cons,β}
β^D    ← C^{D,β} / C^D − 1

SAÍDA: C^D, C^{D,β}, β^D
```

### XIV.7 — Fase 7: Custos Indiretos

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

C^{inv} ← Σ_g Σ_j c_g^hold · S_{g,j}              // Custo de posse (β^IND no preço)
C^I    ← Σ_l C_l^{I,o} + C^{MOB,eq,o} + C^{inv}
C^{I,β} ← Σ_l C_l^{I,β} + C^{MOB,eq,β} + C^{inv}·(1+β^IND)
β^I    ← C^{I,β} / C^I − 1

SAÍDA: C^I, C^{I,β}, β^I
```

### XIV.8 — Fase 8: Síntese e Preço Total

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

```
Verificações obrigatórias:
  [V1] ∀i: Σ_j q_{ij} = Q_i                           — fecho de escopo exato
  [V2] BDI ≥ BDI_TCU_min                                — cobertura mínima de overhead+lucro+tributos
  [V3] ∀r: f_standby(r) < 1                             — nenhum recurso 100% standby
  [V4] P > 0  e  C^{tot} > 0                            — consistência numérica
  [V5] ∀i: ρ_i > 0                                     — nenhuma equipe com gargalo de capacidade zero
  [V6] ∀i: busca de N_i convergiu sem sinalização de inviabilidade (Fase 1) — calendário viável

Diagnósticos opcionais:
  [D1] taxa_util_τ = Σ_j n_j(τ) / (n · n_max(τ)) por tipo τ
         → próximo de 1: pool bem dimensionado; baixo: excesso de standby
  [D2] R_i = C_i^{op} / C_i^{cat} = f_i^V + (1 − f_i^V) · (1/ε̄_i)
         → razão custo operacional / catálogo por atividade
  [D3] {p_i^{op}} por atividade — custo unitário operacional [R$/un]
  [D4] Proporção direto/indireto: C^D/C^{tot}
  [D5] β_i^{eq} = (1−δ_i)·β_i^K + δ_i·β_i^V   — BDI equivalente por equipe

Saída final:
  GO   se [V1]–[V6] aprovadas
  NOGO + lista de violações  caso contrário
```