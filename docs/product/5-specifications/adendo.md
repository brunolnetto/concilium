# Adendo v7.0 — Integração do Formalismo Semanal Granular (Notas MS-1/MS-2)

**Base:** este adendo pressupõe o documento normalizado fornecido (glossário de notação em vigor: $\gamma^{\text{pool}}$,
$\gamma^{\text{MAT+COMB}}$, $\beta_{\text{MAT}}$, $\text{Gr}^{(c)}$, $\chi_i$, $\mathcal{C}_p$, $\eta_{h,i}$, $G_k^*$,
$\beta_{\text{MO/EQ/MAT/IND}}$, $(u,v)\in E$, $\varepsilon_f$, $\bar\beta_{\text{proj}}$, $\mu^*$, $h_{\min}$ — chamado
aqui **v6.1**). **Não** repito as 30 seções — este adendo só acrescenta o que as duas páginas manuscritas (MS-1:
preço unitário operacional semanal; MS-2: equipe/pool por recurso) trazem de genuinamente novo, com os símbolos
adaptados para não colidir com o glossário já fixado.

Resultado líquido: as notas manuscritas **fecham três coisas que o v6.1 deixava em aberto** —
(1) a "fórmula elegante" de $R_i$ que §6–7 diziam não sair da álgebra de $c_m,c_h$; (2) a ligação entre $\rho_i$
primitivo e a Matriz de Eficiência $\eta_s\eta_p\eta_w$, que §1.1 só citava por analogia; (3) a equivalência entre
"pool por semana" (MS-2) e $d_k(t)$ já definido em §16.1 — confirmando que os dois formalismos (contínuo e
semanal) descrevem o mesmo objeto.

---

## A. Tabela de Renomeação — Notas Manuscritas → Notação v6.1

As notas foram escritas independentemente do glossário e reciclam símbolos já ocupados. Nenhuma dessas colisões
é grave sozinha, mas empilhadas no mesmo documento causam exatamente o tipo de ambiguidade que a normalização
v6.1 existe para evitar. Regra: **em caso de conflito, o símbolo do glossário v6.1 vence.**

| Símbolo nas notas | Papel nas notas | Colide com (v6.1) | Símbolo adotado | Seção de destino |
|---|---|---|---|---|
| $\eta_j,\ \delta_j,\ \lambda_j$ | três fatores de $\varepsilon_j=\eta_j\delta_j\lambda_j$ | $\delta_i(\varepsilon_i)$ fração-material (§27.2); $\lambda^{(c)}$ lucro (§29.3); $\lambda(p,r)$ do map-reduce (§25.4) | $\eta_{s,j},\ \eta_{p,j},\ \eta_{w,j}$ | §B |
| $E_i$ | conjunto de recursos da equipe $i$ | $E$ = arestas do DAG (§13.1) | reusa $\mathcal{R}_i$, já definido em §25.1 | §D |
| $R_j(r)=(n_j(r),\gamma_r)$ | pool de recursos contratuais na semana $j$ | $R_i=OC_i/CC_i$ (§6) | $n_j(r)$ mantido, identificado com $d_r(j)$ (§16.1) — sem novo símbolo de "pool" | §E |
| $A_j=\{A_i\mid j\in[j_i^0,j_i^1]\}$ | atividades ativas na semana $j$ | notação $a_{ki}$ (variável de alocação, §12.2, minúscula, papel diferente) | $\mathcal{V}_j$ (consistente com $V$ = conjunto de atividades) | §E |
| $g(A_k)=r$ | categoria do recurso $k$ | — | mantido como $\text{cat}(k)=r$ (mesmo padrão de `r.cat` já usado em §25.1) | §E |
| $P_i^c$ | preço de catálogo por unidade | $PU_i$ já é exatamente isso (§5.2) | $PU_i$ | §C |
| $P_i^{c,\text{cons}}$ | parcela consumível do preço de catálogo | — | $PU_i^{\text{MAT+COMB}} = \gamma_i^{\text{MAT+COMB}}/\rho_i$ | §C |
| $P_{ij}^o$ | preço unitário **operacional** semanal | — | $pu_{ij}^{\text{op}}$ (minúsculo — variável por semana, ao contrário de $PU_i$, constante de catálogo) | §C |
| $\tilde C_{ij}/C_{ij}$ (razão, chamada "$\Gamma_{ij}$" nas notas) | razão custo operacional/catálogo **por semana** | $\Gamma^k,\Gamma_l$ = agregados de categoria (§26.4, §29) | $R_{ij}$ — extensão natural de $R_i$ à granularidade semanal, mesmo padrão de $Q_i\to q_{ij}$ | §C |
| $\tau_{ij}=P_{ij}^o/P_{ij}^c$ | razão de **preço unitário** operacional/catálogo por semana | $\tau^{(c)}$ = fração de tributo (§29.3); $\tau_i$ já fora renomeado para $\eta_{h,i}$ na v6.1 | $R_{ij}^{PU}$ | §C |
| $\gamma_i^{\text{cont}}/\gamma_i^{\text{cons}}$ | pool/material | já renomeados na v6.1 | $\gamma_i^{\text{pool}}/\gamma_i^{\text{MAT+COMB}}$ (sem mudança de conteúdo, só de rótulo) | §D |
| $G_{E_i}$ | grafo de sinergia da equipe | — | $G_{\mathcal{R}_i}$ (mesma ideia, usando $\mathcal{R}_i$ renomeado acima) | §D |

---

## B. $\varepsilon_j = \eta_{s,j}\cdot\eta_{p,j}\cdot\eta_{w,j}$ — a Ligação que §1.1 Deixava Pendente

O v6.1 (§1.1) já registrava que o código decompõe $\eta=\eta_s\cdot\eta_p\cdot\eta_w$ (alocação × praticabilidade
× gestão) e que $\varepsilon=\beta\times\phi$ do documento **aproxima só $\eta_p$**, sem cobrir $\eta_s$ nem $\eta_w$.
As notas MS-1 introduzem, na granularidade semanal, exatamente os três fatores que faltavam:

$$q_{ij} = \rho_i\cdot\eta_{s,j}\cdot\eta_{p,j}\cdot\eta_{w,j}\cdot h\cdot d\cdot m_{ij} \;=\; \rho_i\cdot\varepsilon_j\cdot h\cdot d\cdot m_{ij}, \qquad \boxed{\varepsilon_j \equiv \eta_{s,j}\cdot\eta_{p,j}\cdot\eta_{w,j}}$$

Isto **fecha** a ressalva de §1.1: a eficiência semanal $\varepsilon_j$ usada em todo o formalismo de §25–29 não é
apenas $\eta_p$ (praticabilidade/clima) — é o produto completo, com $\eta_{s,j}$ (alocação, quantos recursos de
fato disponíveis vs. máximo naquela semana) e $\eta_{w,j}$ (gestão/utilização) entrando explicitamente. Duas
consequências práticas:

1. **O achado de §25.2 sobre diesel** (`_dimensionamento_itens.py` escala combustível por $\eta_w$, não por
   $\varepsilon$) deixa de ser uma "confusão de variável" e passa a ser **parcialmente correto por construção**:
   $\eta_w$ é um fator real de $\varepsilon_j$, só que um entre três — o código estaria certo em incluir $\eta_w$,
   errado em usar *só* $\eta_w$ e ignorar $\eta_{s,j}\eta_{p,j}$. O achado do Apêndice A (#5) deve ser reclassificado:
   não é "variável errada", é "fator incompleto".
2. **§9.2 (documento original)** perguntava, sem resposta, se $\varepsilon$ degrada com múltiplas frentes
   paralelas ($\varepsilon_f=\varepsilon_0-k(n-1)$). Com a decomposição $\eta_{s,j}$, essa degradação tem um
   candidato natural: $\eta_{s,j}$ (alocação) é exatamente o fator que cai quando recursos são divididos entre
   mais frentes — a questão em aberto de §9.2 e a Matriz de Eficiência do código podem ser a mesma coisa vista de
   dois ângulos. Isto **não fecha** a questão (ainda falta calibração empírica de $\eta_{s,j}$ como função de
   $n$ frentes), mas dá a ela uma direção formal específica, em vez de um "não está no modelo atual" solto.

---

## C. Fecho da Fórmula Elegante — $R_{ij}$, $R_{ij}^{PU}$ e a Reconciliação com §6–7

Este é o resultado central das notas. O documento v6.1 (§6.5, herdado de v5.7) afirmava:

> *"A fórmula $R_i = 1+(1-\delta)\eta_h/(1+\eta_h)$ não sai naturalmente [da álgebra de $c_m,c_h$]. Ela emerge se
> fizermos certas assunções sobre como $\delta$ é definido e aplicado."*

O motivo, como eu já havia apontado na revisão anterior (§0.5/§6 da minha v6.0): $c_m,c_h$ são primitivas de
**um recurso só**, sem partição pool/material — e é exatamente essa partição ($\gamma^{\text{pool}}$ vs.
$\gamma^{\text{MAT+COMB}}$, só disponível a partir de §25) que a fórmula precisa. As notas MS-1 derivam a razão
já no formalismo correto, e ela **fecha**.

### C.1 Custo Semanal e Preço Unitário Operacional

Do custo semanal já estabelecido em §25.2 (v6.1):

$$C_{ij} = \big(\gamma_i^{\text{pool}}+\varepsilon_j\gamma_i^{\text{MAT+COMB}}\big)\cdot h\,d\,m_{ij}$$

Dividindo pelo quantitativo semanal $q_{ij}=\rho_i\varepsilon_j hd\,m_{ij}$ (§25.2), o termo $hd\,m_{ij}$ cancela:

$$pu_{ij}^{\text{op}} \equiv \frac{C_{ij}}{q_{ij}} = \frac{\gamma_i^{\text{pool}}+\varepsilon_j\gamma_i^{\text{MAT+COMB}}}{\rho_i\,\varepsilon_j} = \frac{1}{\varepsilon_j}\cdot\frac{\gamma_i^{\text{pool}}}{\rho_i} + \frac{\gamma_i^{\text{MAT+COMB}}}{\rho_i}$$

Usando $PU_i=\gamma_i/\rho_i$ (§5.2) e $PU_i^{\text{MAT+COMB}}=\gamma_i^{\text{MAT+COMB}}/\rho_i$ (novo, §A):

$$\boxed{pu_{ij}^{\text{op}} = \frac{1}{\varepsilon_j}\,PU_i - \left(\frac{1}{\varepsilon_j}-1\right)PU_i^{\text{MAT+COMB}}}$$

**Checagem de limite:** em $\varepsilon_j=1$ (catálogo nominal), $pu_{ij}^{\text{op}}=PU_i$ ✓. Quando
$\varepsilon_j\to0$ (mobilizada, zero produção), $pu_{ij}^{\text{op}}\to\infty$ — o preço por unidade produzida
explode porque o denominador $q_{ij}\to0$ mais rápido que $C_{ij}$ (que tem o termo de pool fixo). Isto é o
mesmo fenômeno de $\bar\beta_i(\varepsilon_i)\to\beta_{\text{pool}}$ em $\varepsilon_i=0$ (§27.2 da v6.1) — os
dois limites descrevem a mesma degeneração (equipe parada = 100% pool, custo por unidade indefinido).

### C.2 Razão de Custo — $R_{ij}$

Custo de catálogo da semana (à eficiência nominal, $\varepsilon=1$): $c_{ij}=\gamma_i\cdot hd\,m_{ij}$. A razão:

$$R_{ij} \equiv \frac{C_{ij}}{c_{ij}} = \frac{\gamma_i^{\text{pool}}+\varepsilon_j\gamma_i^{\text{MAT+COMB}}}{\gamma_i}$$

Definindo a **fração de material do custo de catálogo** (constante, $\varepsilon$-independente — não confundir
com $\delta_i(\varepsilon_i)$ de §27.2, que é a fração *operacional*, ponderada por $\varepsilon$):

$$f_i^{\text{MAT+COMB}} \equiv \frac{\gamma_i^{\text{MAT+COMB}}}{\gamma_i} \qquad\text{(constante de catálogo, }\varepsilon=1)$$

$$\boxed{R_{ij} = 1 - (1-\varepsilon_j)\,f_i^{\text{MAT+COMB}}}$$

**Esta é a fórmula elegante, fechada.** Ela tem exatamente a forma que v5.7/v6.1 procuravam
($R=1+(1-\delta)(\ldots)$), só que com $f_i^{\text{MAT+COMB}}$ no lugar do $\delta$ nunca fechado de §1.3 — e com
$\varepsilon_j$, não $\eta_h$, como variável livre (as duas formas são intercambiáveis por $\eta_h=1/\varepsilon$,
mas a forma em $\varepsilon_j$ é mais direta aqui porque vem do quociente $C_{ij}/c_{ij}$, não de $\eta_h/(1+\eta_h)$).

### C.3 Razão de Preço Unitário — $R_{ij}^{PU}$

$$R_{ij}^{PU} \equiv \frac{pu_{ij}^{\text{op}}}{PU_i} = \frac{1}{\varepsilon_j}\left(1-f_i^{\text{MAT+COMB}}\right) + f_i^{\text{MAT+COMB}}$$

$$\boxed{R_{ij}^{PU} = \frac{1}{\varepsilon_j} - \left(\frac{1}{\varepsilon_j}-1\right)f_i^{\text{MAT+COMB}}}$$

**Relação entre as duas razões** — custo é preço×quantidade, e $q_{ij}$ escala com $\varepsilon_j$ enquanto
$c_{ij}$ (catálogo) não:

$$R_{ij} = \varepsilon_j\cdot R_{ij}^{PU}$$

(verificação direta: $\varepsilon_j\left[\frac{1}{\varepsilon_j}(1-f)+f\right]=(1-f)+\varepsilon_j f=1-(1-\varepsilon_j)f=R_{ij}$ ✓)

### C.4 Agregação — Recuperando $R_i$ de §6

Como $c_{ij}=\gamma_i hd\,m_{ij}$ é constante nas semanas ativas (só $m_{ij}\in\{0,1\}$ varia), $R_i$
(§6.1, $=OC_i/CC_i$, agora reinterpretado como razão **prevista**, §0.3 da minha v6.0) é a média simples de
$R_{ij}$ sobre as $N_i$ semanas ativas:

$$R_i = \frac{\sum_j C_{ij}}{\sum_j c_{ij}} = \frac{1}{N_i}\sum_{j:\,m_{ij}=1} R_{ij} = 1-(1-\bar\varepsilon_i)f_i^{\text{MAT+COMB}}, \qquad \bar\varepsilon_i \equiv \frac{1}{N_i}\sum_j \varepsilon_j m_{ij}$$

**Isto substitui a conclusão de §7 do documento original.** Note o que muda: $R_i$ aqui depende de
$\bar\varepsilon_i$ (eficiência média) e $f_i^{\text{MAT+COMB}}$ (mix pool/material da equipe) — **não** depende
de $Q_i$ diretamente. Isso parece contradizer §7.3 ("$R_i$ muda com quantitativo"), mas não contradiz: a
dependência de $Q$ em §7.3 vinha inteiramente do **arredondamento** $M=\lceil T_{\text{semanas}}/p_{\min}\rceil$
(permanência mínima contratual, discreta em meses) — um efeito que **não existe** no formalismo semanal de
§25–29, onde $N_i$ é usado diretamente, sem teto de mês contratual. Reconciliação:

$$R_i^{\text{semanal}} = 1-(1-\bar\varepsilon_i)f_i^{\text{MAT+COMB}} \qquad\text{(limite contínuo, "projeto grande" de §6.1/§10)}$$
$$R_i^{\text{mensal}} = R_i^{\text{semanal}} + \underbrace{\Delta_{\text{arred}}(Q_i, p_{\min})}_{\text{overhead de permanência mínima não amortizada, §7.3}}$$

— os dois resultados da v6.1 (o assintótico $R_i\approx1/\varepsilon$ de §10 e a fórmula elegante fechada aqui)
não competem: **a fórmula elegante É o limite de projeto grande**, com o termo de arredondamento de §7.3 como
correção aditiva só relevante para projetos pequenos (poucas semanas, permanência mínima não diluída). Verifica-se
que $R_i^{\text{semanal}}\to1/\bar\varepsilon_i$ quando $f_i^{\text{MAT+COMB}}\to0$ (equipe 100% pool, sem
material) — consistente com $R_i\approx1/\varepsilon$ de §6.1/§10 sendo o caso particular $f^{\text{MAT+COMB}}=0$.

---

## D. Equipe como Grafo de Sinergia — Extensão de $\rho_i$

MS-2 declara a equipe como conjunto de recursos com uma estrutura de sinergia entre eles:

$$\mathcal{R}_i = \{r\in\text{Cat.insumos}\mid(n_r,\gamma_r)\} \qquad\text{(idêntico a §25.1 — nenhuma mudança de conteúdo)}$$

$$G_{\mathcal{R}_i}:\text{grafo de sinergia sobre }\mathcal{R}_i \qquad\Longrightarrow\qquad \boxed{\rho_i = f(G_{\mathcal{R}_i})}$$

Isto é uma extensão real, não uma renotação: em todo o v6.1, $\rho_i$ é **primitiva** (§1.1, §12.2) — um dado de
entrada, nunca derivado. A proposta aqui é que a produtividade da equipe seja **função da composição e interação
dos recursos** ($n_r,\gamma_r$ por recurso, mais alguma estrutura de grafo — pares que se complementam ou
competem por capacidade).

**Isto não está formalizado nas notas** ($f(\cdot)$ não é especificada) e conecta diretamente com duas lacunas já
registradas no v6.1:

- §9.2: degradação de $\varepsilon$ com múltiplas frentes, "precisaria ser calibrado empiricamente. Não está no
  modelo atual."
- §B acima: $\eta_{s,j}$ (alocação) como candidato a explicar essa degradação.

Hipótese de trabalho (não implementada, registrada como pendência de modelagem, não de notação): se
$\rho_i=f(G_{\mathcal{R}_i})$ e a alocação de recursos entre frentes altera $G_{\mathcal{R}_i}$ (menos
sinergia disponível por frente quando os mesmos recursos são fatiados), então $\eta_{s,j}$ de §B poderia ser
formalmente definido como a razão $f(G_{\mathcal{R}_i}^{\text{alocado}})/f(G_{\mathcal{R}_i}^{\text{total}})$ —
mas isso é além do que as notas ou o documento sustentam hoje. Fica como extensão de modelo em aberto, não
como resultado.

---

## E. Pool Semanal de Recursos Contratuais — Equivalência com $d_k(t)$ de §16.1

MS-2 define, para a semana $j$ e categoria de recurso $r\in\{\text{EQ,MO}\}$:

$$n_j(r) = \sum_{i\in\mathcal{V}_j,\ \text{cat}(i,r)} n_r^i, \qquad \mathcal{V}_j = \{i\in V \mid j\in[s_i,e_i]\}$$

(renotado: $A_j\to\mathcal{V}_j$, $g(A_k)=r\to\text{cat}(i,r)$, por §A)

Isto **não é um conceito novo** — é a versão discretizada por semana de $d_k(t)$, já definida em §16.1:

$$d_k(t) = \sum_{i:\,t\in[s_i,e_i]} a_{ki}\cdot r_{ki} \qquad\Longrightarrow\qquad \boxed{n_j(r) \equiv d_r(j)}$$

com $a_{ki}\to$ indicador de $i\in\mathcal{V}_j$, $r_{ki}\to n_r^i$ (quantidade do recurso $r$ na atividade $i$).
O tamanho do pool, $qt_r=\max_j n_j(r)$, recupera exatamente $qt_k=\max_t d_k(t)$ de §16.1.

**Valor desta equivalência:** confirma que os dois formalismos do documento — o contínuo/DAG de §12–18 (pool,
perpetuação, cadeias $\mathcal{C}_p$) e o semanal/discreto de §25–29 (γ, $m_{ij}$, BDI instancial) — descrevem
**o mesmo objeto físico** em duas granularidades. Isto não estava explicitado no v6.1 (as duas seções corriam em
paralelo sem uma ponte formal equivalente à de §0.5/§11 para custo). A ponte é: $t\to j$ (contínuo→semana
discreta), $d_k(t)\to n_j(r)$, e o critério de perpetuação de §16.2 ($\text{gap}_{uv}<G_k^*$) se aplica
diretamente sobre a mesma janela $[s_i,e_i]$ usada para construir $\mathcal{V}_j$ — não são dois pools
diferentes, é um pool visto por instante vs. visto por semana.

---

## F. Cubo Analítico — Formalização (Pool, Estoque e Cronograma como Projeções)

O v6.1 menciona `cubo_analitico_builder.py` como achado de código (§25.6, §29.5) mas nunca formaliza o que é o
"cubo". Com §B–E acima, agora há material suficiente para defini-lo como estrutura, fechando essa lacuna.

### F.1 Definição do Tensor

Seja $\mathbf{T}$ um tensor com quatro eixos: **entidade** ($i\in V$ para direto, $l$ para indireto),
**semana** ($j\in\{0,\ldots,n-1\}$), **sub-categoria de BDI** ($k\in\{\text{EQ,MO,MAT,COMB}\}$, mais VM só para
indireto), e **natureza** (pool vs. material, derivada de $k$: $\{\text{EQ,MO}\}\to$ pool, $\{\text{MAT,COMB}\}\to$
material). A célula do tensor é exatamente o custo semanal por sub-categoria, já definido em §25/§28:

$$\mathbf{T}[i,j,k] = \gamma_i^{k}\cdot(1+\beta_k)\cdot\big[\mathbb{1}_{k\in\{\text{EQ,MO}\}} + \varepsilon_j\cdot\mathbb{1}_{k\in\{\text{MAT,COMB}\}}\big]\cdot h\,d\,m_{ij} \qquad (\text{direto, "fatia" de } \tilde C_{ij}^{\text{dir}})$$

$$\mathbf{T}[l,j,k] = \gamma_l^{k,\text{sem}}(j)\cdot(1+\beta_k)\cdot m_l(j) \qquad (\text{indireto, "fatia" de } \tilde C_{lj}^{\text{ind}})$$

Ou seja: $\tilde C_{ij}^{\text{dir}}=\sum_k\mathbf{T}[i,j,k]$ e $\tilde C_{lj}^{\text{ind}}=\sum_k\mathbf{T}[l,j,k]$
— o tensor não é um objeto novo, é a **desagregação por sub-categoria** dos custos semanais já somados em
$\tilde C_{ij}$/$\tilde C_{lj}$ (§28.7 da v6.1). O "cubo" é literalmente isso: uma tabela de 3–4 dimensões em vez
de uma soma já colapsada — o que explica por que o código o materializa (`cubo_analitico_builder.py`) como
estrutura de dados separada de `_calc_venda_com_bdi` (que só precisa da soma final).

### F.2 Três Projeções — Pool, Estoque, Cronograma

Cada visão que o documento já trata separadamente é uma soma parcial do mesmo $\mathbf{T}$:

| Visão | Soma parcial | Recupera |
|---|---|---|
| **Cronograma** (§25.2, RCPSP) | $\sum_k \mathbf{T}[i,j,k]$, mantendo $i,j$ | $\tilde C_{ij}$ por atividade-semana — a "linha do tempo" de custo de cada equipe |
| **Pool contratual** (§16–18) | $\sum_{k\in\{\text{EQ,MO}\}} \mathbf{T}[i,j,k]$, depois $\sum_i$ por semana | $C_{\text{pool}}^{\text{pool}}$ (§27.3) — projeção só nos eixos EQ+MO, somada por semana dá $n_j(r)$ (§E) quando dividida por $\gamma_r$ |
| **Estoque/material** (§17) | $\sum_{k\in\{\text{MAT,COMB}\}} \mathbf{T}[i,j,k]$ | $C_{\text{pool}}^{v}$ (§17.2) — fluxo de consumo $f^v(t)$ discretizado por semana, sem dependência de $\text{gap}_{uv}$ (§17.4, material não tem perpetuação porque não há standby de estoque) |
| **BDI por categoria** (§26, §29) | $\sum_i\sum_j \mathbf{T}[i,j,k]$, fixando $k$ | $\Gamma^k=\sum_i\gamma_i^k$ (§25.4) — a coluna "categoria" agregada sobre todo o projeto |
| **Preço total** (§28.7) | $\sum_i\sum_j\sum_k \mathbf{T}[i,j,k] + \sum_l\sum_j\sum_k \mathbf{T}[l,j,k]$ | $P_{\text{total}}$ — soma total do cubo (direto + indireto) |

**O que isto formaliza que o v6.1 não tinha:** pool (§16–18), estoque (§17) e cronograma (§25) eram apresentados
como três modelos com estruturas de derivação distintas (Euler/Shapley para pool, integral de fluxo para
estoque, RCPSP para cronograma). Com $\mathbf{T}$, os três são **a mesma tabela vista por eixos diferentes** —
pool = projeção nos eixos EQ/MO, estoque = projeção nos eixos MAT/COMB, cronograma = a tabela sem projetar
(mantendo $i,j$ intactos). Isto explica também por que §16.5 (partição de Euler/Shapley para $\chi_i$) e o
critério de perpetuação de §16.2 **não têm análogo** na parte de material (§17.3, "separável sem ambiguidade"):
a partição de Euler só é necessária porque o eixo pool, quando projetado, perde a granularidade de atividade
individual quando um recurso é compartilhado ($n_j(r)$ soma sobre $\mathcal{V}_j$) — enquanto o eixo material
nunca precisa dessa partição porque $\mathbf{T}[i,j,\text{MAT}]$ já é exclusivo de $i$ por construção (não há
"compartilhamento" de diesel entre atividades no mesmo instante).

### F.3 Lacuna Confirmada (não nova, já registrada no v6.1)

A formalização do cubo reforça, em vez de resolver, o achado de §29.8 (v6.1): o eixo "entidade" do lado indireto
é $l$ (categoria: ADM, TOP, MOB...), não $i$ (recurso individual) — o cubo indireto é, portanto, estruturalmente
**mais raso** que o direto (3 eixos efetivos: categoria×semana×sub-BDI, sem um quarto eixo de recurso
individual dentro da categoria). Isto é exatamente a "lacuna de granularidade instancial" já registrada no
Apêndice A (#8) — o formalismo do cubo não a resolve, só a torna mais visível: falta ao indireto o eixo que o
direto tem via $\mathcal{R}_i$ (§25.1)/`InstanciaRecurso`.

---

## G. Cadeia Final de Métricas — Do Cronograma ao Preço, com o Cubo como Espinha Dorsal

Consolidando A–F com o restante do documento (v6.1), a cadeia completa de cálculo, na ordem em que cada
quantidade depende das anteriores:

```
1. SCHEDULE (RCPSP, §25.2)
   Para cada atividade i∈V: [s_i,e_i], m_ij, N_i = |{j: m_ij=1}|
   Para cada semana j: 𝒱_j = {i∈V : j∈[s_i,e_i]}                              (§E)

2. EFICIÊNCIA SEMANAL (§B)
   ε_j = η_{s,j}·η_{p,j}·η_{w,j}  →  q_ij = ρ_i·ε_j·h·d·m_ij                   (§B)

3. CUBO γ — custo semanal por sub-categoria, direto e indireto                 (§F.1)
   T[i,j,k] , T[l,j,k]   k∈{EQ,MO,MAT,COMB,(VM p/ indireto)}

4. PROJEÇÕES DO CUBO                                                           (§F.2)
   Pool contratual:  Σ_k∈{EQ,MO} T[i,j,k]  →  n_j(r)=d_r(j)  →  qt_r, perpetuação (§16)
   Estoque/material: Σ_k∈{MAT,COMB} T[i,j,k]  →  C_pool^v (§17)
   Por categoria:    Σ_i,j T[i,j,k]  →  Γ^k                                    (§25.4)

5. RAZÕES R (§C)
   R_ij = 1-(1-ε_j)f_i^{MAT+COMB}     R_ij^PU = R_ij/ε_j
   R_i  = média(R_ij nas semanas ativas) = 1-(1-ε̄_i)f_i^{MAT+COMB}   [+ Δ_arred se M mensal, §7.3]

6. BDI EQUIVALENTE (§26–27, v6.1)
   δ_i(ε_i) = ε_i γ^{MAT+COMB}_i / (γ^{pool}_i + ε_i γ^{MAT+COMB}_i)
   β̄_i(ε_i) = (1-δ_i)β_pool,i + δ_i β_MAT      [β_pool,i = blend EQ/MO, §13.2]

7. PREÇO POR ENTIDADE
   P_i = CC_i · R_i · (1+β̄_i(ε_i))                                            (§26.6/§27.6)
   P^ind = Σ_l Σ_j Σ_k T[l,j,k]  = Σ_k Γ^k(1+β_k)                              (§28.5)

8. PREÇO TOTAL, PROPORÇÃO DIR/IND, VIABILIDADE
   P_total = P^dir + P^ind = Σ_i P_i + P^ind = Σ_i Σ_j Σ_k T[i,j,k] + Σ_l Σ_j Σ_k T[l,j,k]  (§F.2, §28.7)
   proporção direto = P^dir/P_total ; proporção indireto = P^ind/P_total
   Viável ⟺ BDI > R-1 (R=OC_total/CC_total)                                    (§14.3)
   μ = θ̄+λ̄+τ̄ - ΔOC/P_total                                                    (§29.6/§30.6)
```

Cada seta desta cadeia já estava no v6.1 individualmente; o que este adendo acrescenta é (i) o passo 2
totalmente explícito (antes $\varepsilon_j$ entrava sem decomposição), (ii) o passo 5 fechado algebricamente
(antes "não sai naturalmente"), e (iii) o passo 3–4 como estrutura de dados unificada explicando por que pool,
estoque e cronograma, apesar de derivados por métodos diferentes nas Seções 16–17 e 25, são views do mesmo
tensor — não três modelos coincidentes por acaso.

---

## Apêndice B — Itens Ainda Não Fechados (Herdados ou Novos)

| # | Item | Status | Origem |
|---|---|---|---|
| 1 | $f(G_{\mathcal{R}_i})$ — produtividade como função do grafo de sinergia | Não especificado nas notas; extensão de modelo em aberto | §D |
| 2 | Ligação formal $\eta_{s,j}\leftrightarrow$ degradação por múltiplas frentes (§9.2 do original) | Hipótese plausível, não calibrada | §B |
| 3 | $\Delta_{\text{arred}}(Q_i,p_{\min})$ — termo de correção de permanência mínima sobre $R_i^{\text{semanal}}$ | Identificado qualitativamente (§C.4), não derivado em fórmula fechada | §C.4 |
| 4 | Achado #5 do Apêndice A (v6.1) — diesel escalando por $\eta_w$ | Reclassificado de "variável errada" para "fator incompleto" (falta $\eta_s\eta_p$); ainda é uma divergência de código não corrigida | §B |
| 5 | Cubo indireto sem eixo de recurso individual | Confirma achado #8 do Apêndice A (v6.1), não resolve | §F.3 |