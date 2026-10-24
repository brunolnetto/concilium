# P11-A — Referência corrigida de eficiência realizada, K/V e BDI

**Issue:** [#11](https://github.com/brunolnetto/concilium/issues/11), **epic:** [#8](https://github.com/brunolnetto/concilium/issues/8), Onda 0. Este documento tem precedência local sobre identidades históricas baseadas em \(\gamma/\rho\) quando elas usam a eficiência exógena de uma semana como se fosse a eficiência *realizada* após o fechamento de escopo. A substituição editorial definitiva e o consumo pelo runtime são controlados por P11-B.

## 1. Base temporal, capacidade e escopo

Considere a semana discreta \(j\) de uma composição física \(m_{ij}\), com \(\Delta w_j=1\) semana:

\[
R_{ij}=F_i(m_{ij})\,H_i\,\Delta w_j
\quad [u_i],\qquad
H_i=h_id_i\quad[h/\text{semana}].
\]

\(R_{ij}\) é a quantidade física **de referência da mesma composição**, sem restrições exógenas. Não introduzir multiplicador de frente ou \(\eta_s\) porque \(F_i(m)\) já inclui todas as frentes e gargalos. Defina \(\eta_{ij}^{nom}\in[0,1]\) como disponibilidade física exógena **não incluída em \(F_i\) ou \(H_i\)**, com quantidade realizável \(B_{ij}=\eta_{ij}^{nom}R_{ij}\) e quantidade efetivamente entregue \(0\le q_{ij}\le B_{ij}\).

Para \(R_{ij}>0\):

\[
\boxed{\varepsilon_{ij}^{real}=\frac{q_{ij}}{R_{ij}}\in[0,1].}
\]

Se \(B_{ij}>0\), a fração usada da capacidade exógena disponível é \(\varphi_{ij}=q_{ij}/B_{ij}\), logo \(\varepsilon_{ij}^{real}=\eta_{ij}^{nom}\varphi_{ij}\). Na semana final \(\varphi_{ij}\) coincide com o fechamento parcial do escopo. Se \(R=0\), ambas as razões dependentes de \(R\) são **UNDEFINED**; se \(R>0\), \(\eta^{nom}=0\), \(q=0\), então \(\varepsilon^{real}=0\), mas \(\varphi\) **não** existe (0/0).

## 2. Referência de custo financeiramente compatível

No regime K de contratação por semana completa, \(K_{ij}\ge0\) é custo contratado da célula semanal, **não** multiplicado pela fração de fechamento \(\varphi\). O custo variável real vem de compras efetivas \(V_{ij}=\sum_g p_g U_{gij}\), com \(U_{gij}\) em unidades do bem, preços comprovados em R$/unidade e sem dupla contagem de lançamentos.

**Hipótese condicional (não universal):** para preço/consumo unitários de saída constantes, sem desperdício ou consumo em idle, \(U_{gij}=\kappa^{out}_{ig}q_{ij}\) e \(V_{ij}=v_{ij}q_{ij}\), onde \(v_{ij}=\sum_g p_g\kappa^{out}_{ig}\) [R$/unidade de saída]. Sob composição e preço de referência *idênticos* na célula:

\[
C_{ij}^{op}=K_{ij}+v_{ij}q_{ij},\quad
C_{ij}^{ref}=K_{ij}+v_{ij}R_{ij}.
\]

A escolha da referência \((R,C^{ref})\) **deve ser simultânea**, associada à mesma composição física, jornada e base financeira. Se os recursos reais tiverem custos de standby/instâncias compartilhadas que divergem do envelope da atividade, o custo de catálogo da atividade é apenas diagnóstico; não substitui o livro de contratos do projeto.

Para \(C^{ref}>0, R>0\):

\[
\zeta_{ij}=\frac{C_{ij}^{op}}{C_{ij}^{ref}}.
\]

Para **também** \(q_{ij}>0\):

\[
\pi_{ij}=\frac{C_{ij}^{op}/q_{ij}}{C_{ij}^{ref}/R_{ij}},
\qquad
\boxed{\zeta_{ij}=\varepsilon_{ij}^{real}\,\pi_{ij}}.
\]

A igualdade é puramente algébrica e depende de **um único par consistente** \((R,C^{ref})\). Com \(q=0\), \(\pi\) é **UNDEFINED**, ainda que \(\zeta\) seja definido. Substituir \(\varepsilon^{real}\) por \(\eta^{nom}\) na semana parcial torna a igualdade falsa, salvo se \(\varphi=1\).

## 3. Agregação por atividade

Para células de uma mesma atividade, sem arredondamento intermediário, definam-se

\[
R_i^\Sigma=\sum_j R_{ij},\quad Q_i=\sum_jq_{ij},\quad
\bar{\varepsilon}_i^{real}=\frac{Q_i}{R_i^\Sigma}
=\frac{\sum_jR_{ij}\varepsilon_{ij}^{real}}{\sum_jR_{ij}}
\quad(R_i^\Sigma>0).
\]

Esse peso é a **capacidade física de referência**, não \(m_{ij}\) isolado. A média ponderada por frente-semana coincide somente se a produtividade por frente, a disponibilidade e as horas adotadas tornam \(R_{ij}\propto m_{ij}\).

Se \(K_i=\sum_j K_{ij}\), \(V_i=\sum_jV_{ij}\), \(C_i=K_i+V_i>0\):

\[
\boxed{\delta_i=\frac{V_i}{K_i+V_i}};\qquad
C_i=\sum_j(K_{ij}+V_{ij}),\quad
\frac{C_i}{\sum_j C_{ij}^{ref}}
=\frac{Q_i}{R_i^\Sigma}
\frac{C_i/Q_i}{\left(\sum_j C_{ij}^{ref}\right)/R_i^\Sigma}
\quad(Q_i>0).
\]

O custo de V por saída é invariante ao calendário **apenas sob o contrato físico** \(U_{gij}=\kappa^{out}_{ig}q_{ij}\), \(p_g\) estável e \(\sum_jq_{ij}=Q_i\). Com combustível proporcional a horas, perdas, ociosidade consumidora ou saturação de \(F(m)\) acompanhada de consumo-hora crescente, a invariância pode falhar.

## 4. BDI exatamente uma vez e bases zero

Para custos realmente lançados em categorias mutuamente exclusivas \(C_c\ge0\) (K, V, indiretos etc.), cada evento aparece **uma** vez e carrega **uma** categoria. Com BDI por categoria \(\beta_c\):

\[
P=\sum_c(1+\beta_c)C_c,\quad C=\sum_cC_c,\qquad
\boxed{\beta^{eq}=\frac{P}{C}-1=\frac{\sum_c\beta_c C_c}{C}}
\quad(C>0).
\]

Para duas classes K e V, \(\beta^{eq}=(1-\delta)\beta^K+\delta\beta^V\) **somente** se \(\delta\), \(\beta^K\), \(\beta^V\) vierem da mesma base reconciliada. Custos zero, categorias ausentes ou bases inconsistentes são **UNDEFINED/UNKNOWN**, nunca inventar BDI zero e emitir GO. O custo K da última semana parcial permanece integral no regime-base; variáveis por quantidade são cobradas pelo **q** físico.

## 5. Falsificadores independentes reproduzíveis

- **Uma semana parcial:** \(R=400, \eta^{nom}=1, Q=100, K=400, v=1\). \(C^{ref}=800,\ C^{op}=500,\ \varepsilon^{real}=1/4,\ \zeta=5/8,\ \pi=5/2,\ \delta=1/5\). Com \(\beta^K=30\%,\beta^V=10\%\), \(P=630,\beta^{eq}=13/50\). Substituir \(\eta^{nom}=1\) por \(\varepsilon^{real}=1/4\) torna \(\zeta=\eta^{nom}\pi\) **falso**.
- **Três semanas:** \(R=(400,400,400), q=(400,400,100)\), \(K=(400,400,400)\), \(v=1\). \(Q=900,\ \sum K=1200,\ \sum V=900,\ C=2100,\ C^{ref}=2400,\bar\varepsilon^{real}=3/4,\zeta_i=7/8,\pi_i=7/6,\delta_i=3/7\).
- **Semana intermediária sem produção:** \(R>0,\eta^{nom}=0,q=0,K>0,V=0\). \(\varepsilon^{real}=0\), \(\pi\) e \(\varphi\) indefinidas; **K continua devido**.
- **Semana cheia:** \(q=R,\eta^{nom}=1,\varphi=1\). \(\varepsilon^{real}=1,\zeta=\pi=1\) para a referência igual à execução.
- **F(m) saturado:** frentes 1→2, capacidade \(F(1)=F(2)=10\) unidades/h e insumo consumido por hora duplicado: consumo variável por unidade **dobra**, refutando \(V(Q)=\text{const}\) sem hipótese de \(\kappa^{out}\).

**Política:** valores racionais/decimais exatos com tolerância zero e verificações exatas de \(\sum q=Q\), custo e BDI no oráculo. Não alegar GO sem fontes de preço e equivalência de categorias/instâncias; P11-B integra runtime/Skill06 com estes contratos, e #20/#21 certificam o razão financeiro e o preço final.
