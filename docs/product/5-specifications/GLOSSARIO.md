# Variáveis, Estruturas e Equações — Formulário White-Box

---

## §0 — Notação

| Slot | Valores |
|---|---|
| 1º natureza | $\mathrm{K}$ (contratual: EQ+MO) · $\mathrm{V}$ (consumível: MAT+COMB) |
| 2º regime | $\mathrm{cat}$ (catálogo, $\varepsilon=1$) · $\mathrm{op}$ (operacional, $\varepsilon_{ij}$ realizado) |
| 3º markup | $\beta$ (com BDI) · ausente (sem BDI) |

---

## Parte I — Estruturas de Entrada

$$\mathcal{A} = \{A_i\}_{i=1}^{n_{\text{ativ}}}, \qquad A_i = (Q_i,\ E_i,\ W_i,\ B_i)$$

| Campo | Tipo |
|---|---|
| $Q_i$ | quantitativo total [un] |
| $E_i=(\mathcal{G}_i,R_i)$ | equipe |
| $W_i$ | política de mobilização |
| $B_i,\theta_i$ | predecessores + completude |
| $j_i^0$ | semana de início (derivado) |
| $N_i$ | duração em semanas (derivado) |
| $(h_i,d_i)$ | jornada, $d_i\in\{4,5,6\}$, $h_i\in\{6,8\}$ |

**Recurso $r\in R_i$:**

| Campo | Significado |
|---|---|
| $\text{cat}(r)\in\{EQ,MO,MAT,COMB\}$ | categoria BDI |
| $n_r$ | quantidade por frente |
| $V_r^{\text{mensal}}$ | custo contratual mensal (regime `mensal`) |
| $\kappa_r$ | taxa de consumo [unid$_g$/h] (regime `consumo`) |
| $p_{g(r)}$ | preço de aquisição [R\$/unid$_g$] |

$$c_r = \begin{cases}\dfrac{V_r^{\text{mensal}}}{s_{\text{mes}}\,d_i\,h_i} & \text{cat}(r)\in\{EQ,MO\}\\[8pt]\kappa_r\,p_{g(r)} & \text{cat}(r)\in\{MAT,COMB\}\end{cases}$$

MAT legado: $\kappa_r=1$, $p_{g(r)}=c_r$.

**Grafo de sinergia** $\mathcal{G}_i=(V_i,A_i^{\text{syn}},\text{cap})$, domínio $D$, fonte $s_i$, sorvedouro $t_i$:

$$\boxed{\rho_i = \max\text{-fluxo}(s_i\to t_i,\mathcal{G}_i^D) = \min_{C\in\text{cortes}}\sum_{(u,v)\in C}\text{cap}(u,v)}$$

| Topologia | $\rho_i$ |
|---|---|
| Série | $\min_{(u,v)\in\text{caminho}}\text{cap}(u,v)$ |
| Paralelo | $\sum_r\text{cap}(s_i,r)$ |
| Misto | Ford-Fulkerson |

$$\boxed{\eta_{s,ij} = \frac{\max\text{-fluxo}(\mathcal{G}_i^D\!\mid_{m_{ij}})}{\max\text{-fluxo}(\mathcal{G}_i^D\!\mid_{m_i^{\max}})}} \qquad (=m_{ij}/m_i^{\max}\text{ se }\mathcal{G}_i\text{ ausente ou paralelo})$$

$$\varepsilon_{ij} = \eta_{s,ij}\cdot\eta_{p,j}\cdot\eta_{w,j}$$

**Mobilização:** $W_i=(m_i^0,\mu_i^+,m_i^1,\mu_i^-,m_i^{\max})\in\mathbb{N}_{>0}^5$

$$\boxed{m_i(\tau) = \min\!\big(m_i^0+\mu_i^+\tau,\ m_i^{\max},\ m_i^1+\mu_i^-(N_i-1-\tau)\big)}, \qquad \tau=j-j_i^0$$

Degenerado ($\mu^+=\mu^-=0$): $m_i(\tau)=m_i^{\max}=m_i^0=m_i^1\ \forall\tau$.

$$m_{ij} = \begin{cases}m_i(j-j_i^0) & j\in[j_i^0,j_i^0+N_i-1]\\0 & \text{cc}\end{cases} \qquad r+d\le N_i$$

**Predecessores:** $B_i\subseteq\mathcal{A}\setminus\{A_i\}$, $\theta_i:B_i\to(0,1]$

$$\Phi_b(j) = \frac{1}{Q_b}\sum_{j'=j_b^0}^{j}q_{b,j'} \qquad\qquad \boxed{j_i^0 \ge \max_{b\in B_i}\min\{j:\Phi_b(j)\ge\theta_i(b)\}}$$

| Tipo | Condição |
|---|---|
| Q (adotado) | $\Phi_b(j)\ge\theta_i(b)$ |
| T | $j\ge j_b^0+\theta_i(b)N_b$ |

---

## Parte II — Parâmetros Globais

$$s_{\text{mes}} = \frac{1461}{336}\approx4{,}3482\ \text{sem/mês}$$

$$d_i\in\{4,5,6\},\quad h_i\in\{6,8\}$$

$$\beta^{EQ},\ \beta^{MO}\ (\approx29{,}97\%),\ \beta^{MAT},\ \beta^{COMB}\ (\approx4\%),\ \beta^{IND}\ (\approx25{,}21\%)$$

---

## Parte III — Custo Horário de Catálogo

$$\gamma_i^{k} = \sum_{r:\text{cat}(r)=k}c_r n_r,\quad k\in\{EQ,MO,MAT,COMB\}$$

$$\gamma_i^{\mathrm{K,cat}}=\gamma_i^{EQ}+\gamma_i^{MO},\qquad \gamma_i^{\mathrm{V,cat}}=\gamma_i^{MAT}+\gamma_i^{COMB},\qquad \gamma_i^{\mathrm{cat}}=\gamma_i^{\mathrm{K,cat}}+\gamma_i^{\mathrm{V,cat}}$$

$$f_i^{\mathrm V}=\gamma_i^{\mathrm{V,cat}}/\gamma_i^{\mathrm{cat}}, \qquad p_i^{\mathrm{cat}}=\gamma_i^{\mathrm{cat}}/\rho_i$$

$$\boxed{C_i^{\mathrm{cat}} = p_i^{\mathrm{cat}}Q_i = \gamma_i^{\mathrm{cat}}Q_i/\rho_i}$$

---

## Parte IV — Cronograma Semanal

$$q_{ij}=\rho_i\varepsilon_{ij}h_id_im_{ij}\ \ (j<j_i^1)$$

$$q_{i,j_i^1} = Q_i-\sum_{j=j_i^0}^{j_i^1-1}q_{ij}, \qquad j_i^1\equiv j_i^0+N_i-1$$

$$\boxed{\varphi_i \equiv \frac{q_{i,j_i^1}}{\rho_i\varepsilon_{i,j_i^1}h_id_im_i(N_i-1)}\in(0,1]}$$

$$\boxed{\sum_{j=j_i^0}^{j_i^1}q_{ij}=Q_i}\ \ \text{(exato)}$$

$$M_i\equiv\sum_jm_{ij}, \qquad N_i=|\{j:m_{ij}>0\}|, \qquad \mathcal{A}_j\coloneqq\{A_i:j\in[j_i^0,j_i^0+N_i-1]\}$$

---

## Parte V — Custo Direto Semanal

$$C_{ij}^{\mathrm{K,op}}=\gamma_i^{\mathrm{K,cat}}h_id_im_{ij}, \qquad C_{ij}^{\mathrm{V,op}}=\gamma_i^{\mathrm{V,cat}}\cdot\frac{q_{ij}}{\rho_i}, \qquad C_{ij}^{\mathrm{op}}=C_{ij}^{\mathrm{K,op}}+C_{ij}^{\mathrm{V,op}}$$

---

## Parte VI — Custo Direto Total por Atividade

$$C_i^{\mathrm{K,cat}}=\frac{Q_i\gamma_i^{\mathrm{K,cat}}}{\rho_i}, \qquad C_i^{\mathrm{V,cat}}=\frac{Q_i\gamma_i^{\mathrm{V,cat}}}{\rho_i}$$

$$C_i^{\mathrm{K,op}}=\gamma_i^{\mathrm{K,cat}}h_id_iM_i, \qquad C_i^{\mathrm{V,op}}=\sum_jC_{ij}^{\mathrm{V,op}}, \qquad C_i^{\mathrm{op}}=C_i^{\mathrm{K,op}}+C_i^{\mathrm{V,op}}, \qquad p_i^{\mathrm{op}}=C_i^{\mathrm{op}}/Q_i$$

$$\boxed{C_i^{\mathrm{V,op}}\equiv C_i^{\mathrm{V,cat}} = \frac{Q_i\gamma_i^{\mathrm{V,cat}}}{\rho_i}}$$

$$R_i \equiv \frac{C_i^{\mathrm{op}}}{C_i^{\mathrm{cat}}} \qquad\qquad \boxed{\Delta_i^{\mathrm{cat}} \equiv C_i^{\mathrm{op}}-C_i^{\mathrm{cat}} = (R_i-1)\,C_i^{\mathrm{cat}}}$$

---

## Parte VII — Razões Operacional/Catálogo

$$C_{ij}^{\mathrm{cat}}=\gamma_i^{\mathrm{cat}}h_id_im_{ij}, \qquad p_{ij}^{\mathrm{op}}=C_{ij}^{\mathrm{op}}/q_{ij}$$

$$\zeta_{ij}=\frac{C_{ij}^{\mathrm{op}}}{C_{ij}^{\mathrm{cat}}}=\frac{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{cat}}}, \qquad \pi_{ij}=\frac{p_{ij}^{\mathrm{op}}}{p_i^{\mathrm{cat}}}=\frac{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}}{\varepsilon_{ij}\gamma_i^{\mathrm{cat}}}$$

$$\boxed{\zeta_{ij}=\varepsilon_{ij}\pi_{ij}}$$

$$\zeta_{ij}=1-(1-\varepsilon_{ij})f_i^{\mathrm V}, \qquad \pi_{ij}=\frac{1}{\varepsilon_{ij}}-\left(\frac{1}{\varepsilon_{ij}}-1\right)f_i^{\mathrm V}$$

---

## Parte VIII — Camada BDI (atividade)

$$\gamma_i^{\mathrm{K,cat},\beta}=(1+\beta^{EQ})\gamma_i^{EQ}+(1+\beta^{MO})\gamma_i^{MO}, \qquad \gamma_i^{\mathrm{V,cat},\beta}=(1+\beta^{MAT})\gamma_i^{MAT}+(1+\beta^{COMB})\gamma_i^{COMB}$$

$$C_{ij}^{\mathrm{K,op},\beta}=\gamma_i^{\mathrm{K,cat},\beta}h_id_im_{ij}, \qquad C_{ij}^{\mathrm{V,op},\beta}=\gamma_i^{\mathrm{V,cat},\beta}\cdot\frac{q_{ij}}{\rho_i}$$

$$\beta_i^{\mathrm K}\equiv\frac{\gamma_i^{EQ}\beta^{EQ}+\gamma_i^{MO}\beta^{MO}}{\gamma_i^{\mathrm{K,cat}}}, \qquad \beta_i^{\mathrm V}\equiv\frac{\gamma_i^{MAT}\beta^{MAT}+\gamma_i^{COMB}\beta^{COMB}}{\gamma_i^{\mathrm{V,cat}}}$$

$$\delta_{ij}\equiv\frac{\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{K,cat}}+\varepsilon_{ij}\gamma_i^{\mathrm{V,cat}}} \qquad\qquad \boxed{\beta_{ij}=(1-\delta_{ij})\beta_i^{\mathrm K}+\delta_{ij}\beta_i^{\mathrm V}}$$

$$C_i^{\mathrm{K,op},\beta}=\gamma_i^{\mathrm{K,cat},\beta}h_id_iM_i, \qquad C_i^{\mathrm{V,op},\beta}=\gamma_i^{\mathrm{V,cat},\beta}\cdot\frac{Q_i}{\rho_i}, \qquad C_i^{D,\beta}\equiv C_i^{\mathrm{K,op},\beta}+C_i^{\mathrm{V,op},\beta}$$

$$\bar\varepsilon_i\equiv\frac{Q_i}{\rho_ih_id_iM_i}, \qquad \delta_i=\frac{\bar\varepsilon_i\gamma_i^{\mathrm{V,cat}}}{\gamma_i^{\mathrm{K,cat}}+\bar\varepsilon_i\gamma_i^{\mathrm{V,cat}}}$$

$$\boxed{\beta_i^{\mathrm{eq}}\equiv\frac{C_i^{D,\beta}}{C_i^{\mathrm{op}}}-1=(1-\delta_i)\beta_i^{\mathrm K}+\delta_i\beta_i^{\mathrm V}} \qquad\qquad \boxed{R_i = f_i^{\mathrm V} + \frac{1-f_i^{\mathrm V}}{\bar\varepsilon_i}}$$

---

## Parte IX — Pool de Recursos Contratuais

$$n_j(\tau)=\sum_{i:j\in[j_i^0,j_i^0+N_i-1]}m_{ij}\cdot n_\tau^i, \qquad qt_\tau=\max_jn_j(\tau)$$

$$\min_{\{r\},\{[j_r^0,j_r^1]\}}\sum_r\sum_jc_r^{\text{ativo/standby}}(j)+\sum_r(c_r^{\text{mob}}+c_r^{\text{demob}})$$
$$\text{s.a.}\ \ |\{r:\text{type}(r)=\tau,j\in[j_r^0,j_r^1]\}|\ge n_j(\tau)$$

$$\text{gap}_{uv}<G_r^*\equiv\frac{c_r^{\text{mob}}+c_r^{\text{demob}}}{c_r^{\text{sem}}} \qquad\text{(cap absoluto: }\text{gap}_{uv}>G_r^{\text{viável}}\Rightarrow\text{não perpetuar)}$$

Cadeia $\mathcal{C}_p=(i_1\to\cdots\to i_{n_p})$:

$$T_r^{\text{ativo}}=\sum_kN_{i_k}, \qquad T_r^{\text{standby}}=\sum_k\text{gap}_{i_k,i_{k+1}}, \qquad T_r^{\text{perm}}=T_r^{\text{ativo}}+T_r^{\text{standby}}$$

$$\boxed{f_r^{\text{standby}}=T_r^{\text{standby}}/T_r^{\text{perm}}\in[0,1)}, \qquad \boxed{\bar{c}_r=c_r^{\text{sem}}}$$

$$\boxed{C^{\text{pool},o}=\sum_rT_r^{\text{perm}}c_r^{\text{sem}}}, \qquad C^{\text{pool},\beta}=\sum_r(1+\beta_{\text{cat}(r)})T_r^{\text{perm}}c_r^{\text{sem}}$$

$$C^{MOB,eq,o}=\sum_rN_{\text{chains}}^r(c_r^{\text{mob}}+c_r^{\text{demob}}), \qquad C^{MOB,eq,\beta}=(1+\beta^{IND})C^{MOB,eq,o}$$

$$\boxed{C^{\mathrm{pool}}\ge\sum_iC_i^{\mathrm{K,op}}}$$

---

## Parte X — Consumíveis: Aquisição, Demanda e Reposição

$$\boxed{C^{\mathrm{cons}}=\sum_i\frac{Q_i\gamma_i^{\mathrm{V,cat}}}{\rho_i}=\sum_gc_g^{\mathrm{cons}}U_g}, \qquad C^{\mathrm{cons},\beta}=\sum_i\gamma_i^{\mathrm{V,cat},\beta}\cdot\frac{Q_i}{\rho_i}$$

**Demanda física derivada:**

$$\kappa_i^g \equiv \sum_{r\in R_i:g(r)=g}n_r\kappa_r \qquad[\text{unid}_g/\text{h}]$$

$$\boxed{D_{g,ij}=\kappa_i^g\cdot\frac{q_{ij}}{\rho_i}}, \qquad \boxed{D_{g,j}=\sum_{i\in\mathcal{A}_j}D_{g,ij}}, \qquad \sum_jD_{g,j}=\sum_i\kappa_i^g\cdot\frac{Q_i}{\rho_i}\equiv U_g$$

**Balanço de estoque:** $O_{g,j}=X_{g,j-L_g}$

$$\boxed{S_{g,j}=S_{g,j-1}+O_{g,j}-D_{g,j}}\qquad\text{s.a.}\ S_{g,j}\ge0$$

**Reposição ótima (Wagner–Whitin), por bem $g$, decompondo em lotes $[a,b]$:**

$$\min_{\{X_{g,j}\ge0\}}\sum_j\big[c_g^{\text{ped}}\mathbb{1}[X_{g,j}>0]+c_g^{\text{hold}}S_{g,j}\big]$$

$$\boxed{\mathrm{Custo}(a,b)=c_g^{\text{ped}}+c_g^{\text{hold}}\sum_{k=a+1}^b(k-a)D_{g,k}}$$

$$\boxed{f(b)=\min_{a\in[j_{\min}^g,b]}\big[f(a-1)+\mathrm{Custo}(a,b)\big]}, \qquad f(j_{\min}^g-1)\equiv0$$

$$\boxed{C^{\mathrm{inv}}=\sum_g\big(f(j_{\max}^g)-n_g^{\text{ped}}c_g^{\text{ped}}\big)}, \qquad \boxed{C^{\mathrm{PED}}=\sum_gn_g^{\text{ped}}c_g^{\text{ped}}}, \qquad C^{\mathrm{PED},\beta}=(1+\beta^{IND})C^{\mathrm{PED}}$$

---

## Parte XI — Custo Direto Total do Projeto

$$C^D=C^{\mathrm{pool}}+C^{\mathrm{cons}}, \qquad C^{D,\beta}=C^{\mathrm{pool},\beta}+C^{\mathrm{cons},\beta}, \qquad \beta^D=C^{D,\beta}/C^D-1$$

---

## Parte XII — Custos Indiretos

$$\mathcal{L}=\{ADM,TOP,LAB,QSMS,MOB^{\text{site}},\ldots\}, \qquad \text{driver}(l)\in\{\texttt{perm},\texttt{onetime}\}$$

$$n=j^{\max}-j^{\min}$$

**Driver `perm`:** $\gamma_l^{k,\text{sem}}=\Gamma_l^{k,\text{mensal}}/s_{\text{mes}}$, $m_l(j)=1$

**Driver `onetime`:** $\gamma_l^{VM,\text{sem}}(j)=c_l^{\text{mob}}\mathbb{1}[j=j^{\min}]+c_l^{\text{demob}}\mathbb{1}[j=j^{\max}-1]$

$$C_{lj}^{I,o}=\big(\gamma_l^{MO,\text{sem}}+\gamma_l^{EQ,\text{sem}}+\gamma_l^{COMB,\text{sem}}+\gamma_l^{VM,\text{sem}}(j)\big)m_l(j)$$

$$\boxed{C_{lj}^{I,\beta}=\big[\gamma_l^{MO,\text{sem}}(1+\beta^{MO})+\gamma_l^{EQ,\text{sem}}(1+\beta^{EQ})+\gamma_l^{COMB,\text{sem}}(1+\beta^{COMB})+\gamma_l^{VM,\text{sem}}(j)(1+\beta^{IND})\big]m_l(j)}$$

$$C_l^{I,o}=\sum_jC_{lj}^{I,o}, \qquad C_l^{I,\beta}=\Gamma_l^{MO}(1+\beta^{MO})+\Gamma_l^{EQ}(1+\beta^{EQ})+\Gamma_l^{COMB}(1+\beta^{COMB})+\Gamma_l^{VM}(1+\beta^{IND})$$

$$\boxed{C^{MOB,eq,o}=\sum_rN_{\text{chains}}^r(c_r^{\text{mob}}+c_r^{\text{demob}})}, \qquad C^{MOB,eq,\beta}=(1+\beta^{IND})C^{MOB,eq,o}$$

$$C^I=\sum_lC_l^{I,o}+C^{MOB,eq,o}+C^{\mathrm{PED}}+C^{\mathrm{inv}}, \qquad C^{I,\beta}=\sum_lC_l^{I,\beta}+C^{MOB,eq,\beta}+C^{\mathrm{PED},\beta}+C^{\mathrm{inv}}(1+\beta^{IND})$$

$$\bar\beta^I=C^{I,\beta}/C^I-1$$

---

## Parte XIII — Síntese

$$C^{\mathrm{cat}}=\sum_iC_i^{\mathrm{cat}}=\sum_i\frac{\gamma_i^{\mathrm{cat}}Q_i}{\rho_i}, \qquad C^{\mathrm{tot}}=C^D+C^I$$

$$P\equiv C^{D,\beta}+C^{I,\beta}$$

$$\boxed{\mathrm{BDI}\equiv\frac{P}{C^{\mathrm{cat}}}-1}$$

$$R=C^{\mathrm{tot}}/C^{\mathrm{cat}}, \qquad \beta^{\mathrm{eq}}=P/C^{\mathrm{tot}}-1, \qquad \mu=(P-C^{\mathrm{tot}})/P$$

$$\boxed{\mathrm{BDI}\ge\mathrm{BDI}_{\mathrm{TCU,min}}}$$