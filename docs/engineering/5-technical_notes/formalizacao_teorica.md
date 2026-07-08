# Formalização Completa do Modelo de Planejamento de Obras

---

## 1. Domínio Temporal

Adota-se uma **discretização semanal**. Seja:

$$\mathcal{T} = \{1, 2, \ldots, T\} \subset \mathbb{Z}_{>0}$$

o conjunto de semanas do horizonte de planejamento. Cada semana $j \in \mathcal{T}$ é caracterizada pelo par $(d_j, p_j)$ onde:

- $d_j \in \mathbb{Z}_{>0}$ — dias úteis disponíveis na semana $j$
- $p_j \in (0, 1]$ — fator de chuva estatístico da semana $j$

e por uma constante global $h \in \mathbb{R}_{>0}$ (horas diárias trabalhadas). Define-se:

$$H_j := h \cdot d_j \cdot p_j \qquad \text{(horas produtivas efetivas da semana } j\text{)}$$

> **Implementação (ADR-068):** o fator $p_j$ é decomposto em dois componentes independentes:
> $$p_j = p_j^{\text{clima}} \cdot p_j^{\text{cal}}$$
> onde $p_j^{\text{clima}} \in (0,1]$ é o fator de praticabilidade climática (chuvas) e $p_j^{\text{cal}} \in (0,1]$ captura eventos de calendário (feriados, recessos). O campo `fator_chuva` da `Praticabilidade` alimenta $p_j^{\text{clima}}$; `fator_calendario` do `CalendarioOperacionalSemanal` alimenta $p_j^{\text{cal}}$. No modelo de simulação (`WorkforcePolicySimulator`), o produto $p_j^{\text{clima}} \cdot p_j^{\text{cal}}$ é passado como `eficiencia` em cada `CurvaForcaSemanal`.

> **Reformulação (ADR-124):** o modelo de planejamento renomeia os dois fatores para
> $\eta_j^{\text{clima}} := p_j^{\text{clima}}$ (praticabilidade climática, estocástica, não controlável)
> e $\delta_j := p_j^{\text{cal}}$ (coeficiente de calendário, determinístico, controlável pelo gestor).
> As horas produtivas efetivas passam a ser expressas de forma explícita como:
> $$H_j = h \cdot d_j \cdot \eta_j^{\text{clima}} \cdot \delta_j$$
> A eficiência de planejamento agregada é $\eta_j^{\text{plan}} = \eta_j^{\text{clima}} \cdot \delta_j$
> (antigo $\eta_p$ / `P_r`). Os fatores $\eta_s$ (alocação $n_j/n_{\max}$) e $\eta_w$
> (gestão residual) são reclassificados como fatores de **controle** — sem conteúdo
> diagnóstico no planejamento e nulos (`None`) no `CampoEficiencia` até haver execução real.

---

## 2. Atividades e Modelo de Produção

### 2.1 Atividades

$\mathcal{A} = \{1, \ldots, n\}$ com cada atividade $i$ caracterizada por:
- $Q_i \in \mathbb{R}_{>0}$ — quantitativo total (unidade da atividade)
- $P_i \in \mathbb{R}_{>0}$ — produtividade horária por equipe $\left[\frac{\text{unid}}{\text{hora} \cdot \text{equipe}}\right]$
- $\mathcal{W}_i \subseteq \mathcal{T}$ — janela de execução, com $|\mathcal{W}_i| = n_i$ semanas

### 2.2 Produção Semanal

Seja $m_{ij} \in \mathbb{Z}_{\geq 0}$ o número de equipes alocadas à atividade $i$ na semana $j$. A produção na semana $j$ é:

$$q_{ij} = P_i \cdot H_j \cdot m_{ij} = P_i \cdot h \cdot d_j \cdot p_j \cdot m_{ij}$$

### 2.3 Restrição de Fechamento

$$\sum_{j \in \mathcal{W}_i} q_{ij} = Q_i \qquad \forall i \in \mathcal{A}$$

> **Nota:** O fechamento exato implica que a última semana pode ser fracionária, aceito como limitação v1. Formalmente, $q_{i,n_i}$ pode satisfazer $q_{i,n_i} \leq P_i \cdot H_{n_i} \cdot m_{i,n_i}$.

---

## 3. Grafo de Precedências Estendido

### 3.1 Tipos de Relação

O DAG $\mathcal{G} = (\mathcal{A}, \mathcal{E})$ admite arestas tipadas. Cada aresta $e = (i, j, \tau, \lambda) \in \mathcal{E}$ carrega:
- $\tau \in \{\text{FS}, \text{SS}, \text{FF}\}$ — tipo de relação
- $\lambda \in \mathbb{Z}_{\geq 0}$ — lag em semanas

Sendo $s_i = \min \mathcal{W}_i$ e $f_i = \max \mathcal{W}_i$ início e fim de $i$, as restrições induzidas são:

$$\begin{aligned}
\tau = \text{FS}: & \quad s_j \geq f_i + \lambda \\
\tau = \text{SS}: & \quad s_j \geq s_i + \lambda \\
\tau = \text{FF}: & \quad f_j \geq f_i + \lambda
\end{aligned}$$

### 3.2 Concorrência Temporal

Duas atividades $i, i'$ são **temporalmente concorrentes** se e somente se suas janelas se intersectam:

$$\text{conc}(i, i') := \mathcal{W}_i \cap \mathcal{W}_{i'} \neq \emptyset$$

A verificação de concorrência tem granularidade de **semana inteira** (limitação v1).

---

## 4. Recursos, Equipe Padrão e Instâncias

### 4.1 Tipos de Recurso

$$\mathcal{R} = \mathcal{L} \cup \mathcal{Q}$$

com $\mathcal{L}$ (funções de mão-de-obra) e $\mathcal{Q}$ (equipamentos) disjuntos.

### 4.2 Equipe Padrão

Para cada atividade $i$ e recurso $r$, define-se:

$$e_{i,r} \in \mathbb{Z}_{\geq 0}$$

a quantidade inteira do recurso $r$ por equipe padrão de $i$. O vetor $\mathbf{e}_i \in \mathbb{Z}_{\geq 0}^{|\mathcal{R}|}$ é a **equipe padrão completa** da atividade $i$.

### 4.3 Demanda de Recurso

A demanda bruta do recurso $r$ pela atividade $i$ na semana $j$ é:

$$D_{ij,r} := m_{ij} \cdot e_{i,r} \in \mathbb{Z}_{\geq 0}$$

---

## 5. Política de Ramp — Formalização Discreta

### 5.1 Parâmetros

Para cada atividade $i$, a política é definida pela tripla $(K_i^{\max}, r_i, d_i) \in \mathbb{Z}_{>0} \times \mathbb{Z}_{\geq 0} \times \mathbb{Z}_{\geq 0}$ com $r_i + d_i \leq n_i$, onde:
- $K_i^{\max}$ — número máximo de equipes no plateau
- $r_i$ — semanas de ramp-up
- $d_i$ — semanas de ramp-down

### 5.2 Função de Ramp

Seja $t = j - s_i \in \{0, 1, \ldots, n_i - 1\}$ o offset 0-indexado da semana dentro da atividade $i$. A política é parametrizada por $(K_i^{\max}, n_0, c_{\text{mob}}, c_{\text{demob}}, P_i^{\text{plateau}})$ onde:
- $n_0 \in \mathbb{Z}_{\geq 0}$ — equipes no instante de início ($t = 0$)
- $c_{\text{mob}} \in \mathbb{R}_{>0}$ — taxa de ramp-up (equipes/semana)
- $c_{\text{demob}} \geq 0$ — taxa de ramp-down (equipes/semana; 0 = sem ramp-down)
- $P_i^{\text{plateau}} \in \mathbb{Z}_{\geq 0} \cup \{\infty\}$ — semanas de plateau ($\infty$ = plateau até entrega de $Q_i$)

O número de equipes é:
$$m_{ij} = \begin{cases} \min\!\Bigl(\bigl\lfloor n_0 + t \cdot c_{\text{mob}} \bigr\rfloor,\; K_i^{\max}\Bigr) & \text{se } t < t_{\text{ramp}} \quad \text{(ramp-up)} \\[6pt] K_i^{\max} & \text{se } t_{\text{ramp}} \leq t < t_{\text{ramp}} + P_i^{\text{plateau}} \quad \text{(plateau)} \\[6pt] \max\!\Bigl(\bigl\lfloor K_i^{\max} - (t - t_{\text{ramp}} - P_i^{\text{plateau}}) \cdot c_{\text{demob}} \bigr\rfloor,\; 0\Bigr) & \text{caso contrário} \quad \text{(ramp-down)} \end{cases}$$

ononde $t_{\text{ramp}} = \lceil (K_i^{\max} - n_0) / c_{\text{mob}} \rceil$. Quando $r_i = 0$ ($c_{\text{mob}} \geq K_i^{\max}$), a atividade inicia diretamente em plateau.

> **Implementação:** o arredondamento é por $\lfloor \cdot \rfloor$ (conservador — nunca sobre-aloca), não pelo arredondamento simétrico $\lfloor \cdot + \frac{1}{2} \rfloor$. O plateau ilimitado ($P_i^{\text{plateau}} = \infty$, `semanas_plateau=None` no código) mantém $m_{ij} = K_i^{\max}$ até que $Q_i$ seja entregue, eliminando a necessidade de especificar $n_i$ a priori. Correspondência com o modelo clássico $(K_i^{\max}, r_i, d_i)$: $n_0 = 0$, $c_{\text{mob}} = K_i^{\max}/r_i$, $c_{\text{demob}} = K_i^{\max}/d_i$, $P_i^{\text{plateau}} = n_i - r_i - d_i$.

**Propriedade:** $m_{ij} \in \{0, 1, \ldots, K_i^{\max}\}$ e a sequência $(m_{ij})_{t=0}^{n_i-1}$ é unimodal por construção.

---

## 6. Estado de Recurso e Perpetuação

### 6.1 Estado de Instância

Cada instância $\omega$ do recurso $r$ possui, em cada semana $j$, um estado:

$$\sigma_{\omega, j} \in \Sigma := \{\texttt{prod},\; \texttt{idle},\; \texttt{demob}\}$$

onde:
- $\texttt{prod}$ — mobilizado e produtivo (alocado a alguma $i$ com $m_{ij} > 0$)
- $\texttt{idle}$ — mobilizado mas sem atividade produtiva (incorre custo de aluguel/diária)
- $\texttt{demob}$ — desmobilizado (não incorre custo operacional)

O conjunto de instâncias ativas (mobilizadas) do recurso $r$ na semana $j$ é:

$$\Omega_{r,j}^+ := \{\omega : \sigma_{\omega,j} \neq \texttt{demob}\}$$

com $|\Omega_{r,j}^+| = \sum_{i \in \mathcal{A}} D_{ij,r}$ para o caso sem compartilhamento.

### 6.2 Compatibilidade de Perpetuação

Dado o grafo de precedências $\mathcal{G}$, a **relação de perpetuação** é:

$$\Pi \subseteq \mathcal{A} \times \mathcal{A} \times \mathcal{R}$$

onde $(i, j, r) \in \Pi$ requer:

1. $j \in \text{succ}(i)$ — precedência direta em $\mathcal{G}$ (ou via fecho para perpetuação em cadeia)
2. $e_{i,r} > 0$ e $e_{j,r} > 0$
3. $\neg\,\text{conc}(i, j)$ — atividades não concorrentes
4. $f_i \leq s_j$ — instâncias liberadas antes da demanda (sem sobreposição produtiva)

### 6.3 Quantidade Perpetuada

$$\pi_{ij,r} = \min\!\left(D_{\,j,\,s_j,\,r},\; m_{i,\,f_i} \cdot e_{i,r}\right) \in \mathbb{Z}_{\geq 0}$$

onde $D_{j,s_j,r} = m_{j,s_j} \cdot e_{j,r}$ é a demanda de $j$ em sua semana de início.

### 6.4 Demanda Líquida de Mobilização

$$\nu_{j,r} = K_j^{\max} \cdot e_{j,r} - \sum_{i\,:\,(i,j,r)\in\Pi} \pi_{ij,r} \geq 0$$

---

## 7. Eventos de Mobilização e Desmobilização

### 7.1 Definição Formal de Evento

Para cada instância $\omega$ do recurso $r$, definem-se os indicadores:

$$\text{mob}_{\omega,j} := \mathbf{1}\!\left[\sigma_{\omega,j-1} = \texttt{demob} \;\wedge\; \sigma_{\omega,j} \neq \texttt{demob}\right]$$

$$\text{demob}_{\omega,j} := \mathbf{1}\!\left[\sigma_{\omega,j-1} \neq \texttt{demob} \;\wedge\; \sigma_{\omega,j} = \texttt{demob}\right]$$

### 7.2 Contagem Agregada de Eventos

O número total de eventos de mobilização do recurso $r$ ao longo do projeto é:

$$M_r^{\text{ev}} = \sum_{\omega} \sum_{j \in \mathcal{T}} \text{mob}_{\omega,j}$$

**Proposição:** O compartilhamento via perpetuação reduz $M_r^{\text{ev}}$: toda tripla $(i,j,r) \in \Pi$ com $\pi_{ij,r} = q$ elimina exatamente $q$ pares de eventos (desmob ao fim de $i$ + mob ao início de $j$).

---

## 8. Modelo de Custo

### 8.1 Custo de Mão-de-Obra

#### Encargos Sociais

O custo horário direto de cada função $\ell \in \mathcal{L}$ é:

$$c_\ell^h = \frac{w_\ell}{h \cdot \bar{d}} \cdot (1 + E_\ell)$$

onde $w_\ell \in \mathbb{R}_{>0}$ é o salário mensal, $\bar{d}$ são os dias úteis médios mensais, e $E_\ell \geq 0$ é o total de encargos sociais:

$$E_\ell = \underbrace{A + B + C + D}_{\text{grupos CLT}} + E + F + J$$

com $A$ (básicos: INSS, FGTS, RAT, terceiros), $B$ (férias, 13º, DSR — incidem sobre $A$), $C$ (aviso prévio, indenizações), $D$ (reincidências de $B$ sobre $C$), $E$ (saúde, vida, EPI), $F$ (vale-transporte, vale-refeição) e $J$ (provisão trabalhista), conforme base de encargos do projeto (fonte: `MemorialEncargos`, vigência configurável).

> **Nota:** $E_\ell$ (encargos sociais) refere-se ao custo de contratação — distinto do BDI, que é margem comercial aplicada ao **preço de venda** (ver abaixo).

#### BDI — Margem Comercial (Acórdão TCU 2622/2013)

O BDI converte custo direto em preço de venda. Para cada categoria de custo $k$ (mão-de-obra, equipamento, material, diesel):

$$\text{BDI}_k = \frac{(1+AC)(1+DF)(1+R)(1+CR)(1+L)}{1 - T} - 1$$

onde $T = cofins + iss + pis + cssl + ir$ são tributos sobre a receita bruta, e $(AC, DF, R, CR, L) \in [0,1)^5$ são os componentes de overhead (Administração Central, Despesas Financeiras, Garantia/Risco, Contingência e Lucro), todos configuráveis por projeto em `ComponentesBdi`.

$$PV_{ij}^{\mathcal{L}} = C_{ij}^{\mathcal{L}} \cdot (1 + \text{BDI}_{\text{mao\_obra}})$$

#### Custo de mão-de-obra da atividade $i$ na semana $j$:

$$C_{ij}^{\mathcal{L}} = \sum_{\ell \in \mathcal{L}} m_{ij} \cdot e_{i,\ell} \cdot c_\ell^h \cdot H_j$$

### 8.2 Custo de Equipamentos

Cada equipamento $q \in \mathcal{Q}$ possui:

$$\theta_q = (\rho_q,\, u_q,\, \mu_q,\, \phi_q,\, \psi_q)$$

onde:
- $\rho_q$ — taxa de aluguel; unidade definida por $u_q$ (`custo_mensal` em `EquipamentoEquipeDireta`)
- $u_q \in \{\texttt{hora\_prod}, \texttt{dia\_cal}, \texttt{mes}\}$ — modo de cobrança (`rental_unit`)
- $\mu_q \geq 0$ — taxa de manutenção ativa [R\$/hora produtiva]; incide apenas quando $\sigma = \texttt{prod}$ (`custo_manutencao_hora`)
- $\phi_q \geq 0$ — consumo de diesel [`consumo_litros_hora`]
- $\psi_q \in \{\texttt{hora}, \texttt{km}\}$ — unidade de consumo do combustível (tipicamente hora para equipamentos de canteiro)

#### Custo de aluguel por instância mobilizada na semana $j$:

$$c_q^{\text{alug}}(j, \sigma) = \begin{cases} \rho_q \cdot H_j & u_q = \texttt{hora\_prod},\; \sigma = \texttt{prod} \\ \rho_q \cdot d_j & u_q = \texttt{dia\_cal} \\ \rho_q / (52/12) & u_q = \texttt{mes} \end{cases}$$

> **Nota:** para $u_q = \texttt{hora\_prod}$ e $\sigma = \texttt{idle}$, o custo de aluguel é zero — a instância não fatura horas produtivas. Para $u_q \in \{\texttt{dia\_cal}, \texttt{mes}\}$, o custo incide independentemente do estado $\sigma \in \{\texttt{prod}, \texttt{idle}\}$. O custo de standby de uma campanha de equipamento (`CampanhaEquipamento.custo_standby_semanal`) é derivado do regime declarado em `RegimePermanencia` e representa o custo de $\sigma = \texttt{idle}$ para equipamentos em campanha.

#### Custo total de equipamento da atividade $i$ na semana $j$:

$$C_{ij}^{\mathcal{Q}} = \sum_{q \in \mathcal{Q}} |\Omega_{q,j}^{(i)}| \cdot \left[c_q^{\text{alug}}(j, \sigma_{q,j}) + \mu_q \cdot H_j \cdot \mathbf{1}[\sigma_{q,j} = \texttt{prod}]\right]$$

onde $|\Omega_{q,j}^{(i)}|$ são as instâncias do equipamento $q$ vinculadas à atividade $i$ na semana $j$.

### 8.3 Custo de Mobilização e Desmobilização

Para cada recurso $r \in \mathcal{R}$, sejam $c_r^{\text{mob}}, c_r^{\text{demob}} \in \mathbb{R}_{\geq 0}$ os custos fixos por evento. O custo total é:

$$C^{\text{mob}} = \sum_{r \in \mathcal{R}} (c_r^{\text{mob}} + c_r^{\text{demob}}) \cdot M_r^{\text{ev}}$$

> **Implementação:** para equipamentos ($r \in \mathcal{Q}$), $c_r^{\text{mob}}$ e $c_r^{\text{demob}}$ são declarados em `EquipamentoEquipeDireta.custo_mobilizacao` / `.custo_desmobilizacao`; a análise de campanhas (`CampanhaEquipamento`) detecta automaticamente grupos de atividades consecutivas onde a perpetuação $\pi_{ij,r} > 0$ reduz $M_r^{\text{ev}}$, computando a `economia_vs_dismissal`. Para mão-de-obra ($r \in \mathcal{L}$), o custo agregado de mob/desmob é acumulado em `EquipeDireta.custo_mob_desmob`.

### 8.4 Custo Total do Projeto

$$C^{\text{total}} = \underbrace{\sum_{i \in \mathcal{A}} \sum_{j \in \mathcal{W}_i} \left(C_{ij}^{\mathcal{L}} + C_{ij}^{\mathcal{Q}}\right)}_{\text{custo operacional}} + \underbrace{C^{\text{mob}}}_{\text{mob/desmob}}$$

---

## 9. Síntese — Estrutura Completa do Modelo

| Camada | Objeto formal | Implementação no código |
|---|---|---|
| Tempo | $\mathcal{T}$, $(d_j, p_j^{\text{clima}}, p_j^{\text{cal}}, H_j)$ | `CalendarioOperacionalSemanal`, `Praticabilidade` |
| Atividades | $\mathcal{A}$, $(Q_i, P_i, \mathcal{W}_i)$ | `EapItem`, `Atividade`, `Producao.valor_horario` |
| Precedências | $\mathcal{E}$ com $(\tau, \lambda)$ | `PrecedenciaItem`, `ArestaActivityDag`, `ActivityDag` |
| Recursos | $\mathcal{R} = \mathcal{L} \cup \mathcal{Q}$, $e_{i,r}$ | `ComposicaoPadraoEquipe` (funcoes + equipamentos) |
| Ramp | $(K_i^{\max}, n_0, c_{\text{mob}}, c_{\text{demob}}, P^{\text{plateau}}) \to m_{ij}$ | `MobilizacaoPolicy`, `WorkforcePolicySimulator` |
| Estados | $\sigma_{\omega,j} \in \Sigma$ | `CampanhaEquipamento` / `RegimePermanencia` (equip.) |
| Perpetuação | $\Pi$, $\pi_{ij,r}$, $\nu_{j,r}$ | `CampanhaEquipamentoBuilder` (equip.); MO via `custo_mob_desmob` |
| Custo MO | $c_\ell^h$ via encargos sociais $E_\ell$; BDI para PV | `MemorialEncargos`, `ComponentesBdi` |
| Custo Equip | $c_q^{\text{alug}}(j,\sigma)$ por $u_q$; $\mu_q$ produtivo | `rental_unit`, `custo_manutencao_hora` em `EquipamentoEquipeDireta` |
| Mob/Desmob | $M_r^{\text{ev}}$, $c_r^{\text{mob/demob}}$ | `custo_mobilizacao/desmobilizacao`; `CampanhaEquipamento.economia_vs_dismissal` |

O modelo assim especificado admite três classes de problema de otimização:

1. **Scheduling** — determinar $\mathcal{W}_i$ respeitando $\mathcal{E}$ e minimizando $C^{\text{total}}$ ou $\max_j \sum_i D_{ij,r}$
2. **Matching de instâncias** — determinar $\Pi$ ótimo dado o calendário, maximizando $\sum_{r,i,j} \pi_{ij,r}$ (perpetuações) para minimizar $C^{\text{mob}}$
3. **Nivelamento de recursos** — ajustar $(r_i, d_i)$ da política de ramp para minimizar picos $\max_j |\Omega_{r,j}^+|$ dado $\mathcal{W}_i$ fixo