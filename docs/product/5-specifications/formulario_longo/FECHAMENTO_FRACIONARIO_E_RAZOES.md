# P11-A — Demonstração de fechamento fracionário, razões e BDI

**Contrato candidato · 2026-10-22 · Refs #11 e #8.** Base física P10-A/P10-B: capacidade produtiva efetiva F(m), sem penalidade por frentes não mobilizadas.

## 1. Definições físicas e domínios

Para atividade i e semana j, H_i=h_i d_i>0 [horas/semana],
F_i(m_ij)>=0 [unidades produzidas/hora], com m_ij frentes mobilizadas.
A capacidade instalada é B0_ij = F_i(m_ij) H_i [unidades/semana].
O fator externo e_ij entre 0 e 1 inclui clima, calendário, jornada e **somente sob hipótese explícita** eventual desempenho de gestão; ausência de observação não prova eficiência de gestão igual a 1.

\[
 B_{ij}=B^0_{ij}e_{ij},\qquad
 r_{ij}=(Q_i-\sum_{k<j}q_{ik})_+,\qquad
 q_{ij}=\min\{r_{ij},B_{ij}\}.
\]

Fechamento exige \(\sum_jq_{ij}=Q_i\); saldo positivo sem horizonte/capacidade significa NOGO. Quando B_ij>0, \(\phi_{ij}=q_{ij}/B_{ij}\in[0,1]\); a semana final produtiva tem \(\phi\in(0,1]\). Se B_ij=0, a fração \(\phi\) é NOT_EVALUATED (não zero observado) e q=0.

Para B0_ij>0, a razão física efetiva é
\[
 \chi^{cap}_{ij}=\frac{q_{ij}}{B^0_{ij}}
 =e_{ij}\phi_{ij}\quad\text{se }B_{ij}>0,
\]
e se B_ij=0 mas B0_ij>0, \(\chi^{cap}=0\), sem inferir phi. Se B0_ij=0, a razão é UNKNOWN. A razão \(\chi^{cap}\) não é uma eficiência de alocação por equipes. A redução de capacidade por gargalos e composição de frentes já está contida em F_i(m).

## 2. Diário de custos: presença contratual K e consumo real V

Custos K são lançados pelo livro autoritativo de instâncias do pool (ativo, idle, movimentos classificados separadamente), sem aplicar desconto phi na semana de fechamento. O custo K_ij atribuído à atividade só é autoritativo se for respaldado por rateio sem duplicação. O envelope \(H_i\sum_g c_g^K a_{ig}(m_{ij})\) é apenas diagnóstico quando contratos são compartilhados.

Para consumível g de preço p_g [R$/unidade física],
\[
 U_{gij}\ge0,\qquad V_{ij}=\sum_gp_gU_{gij},\qquad
 C_{ij}^{op}=K_{ij}+V_{ij}.
\]
Se e somente se o regime físico é *por unidade produzida*,
\(U_{gij}=\kappa_{ig}^{out}q_{ij}\), sem perdas nem standby, e as taxas e preços são constantes, então
\(V_{ij}=v_i q_{ij}\), \(v_i=\sum_gp_g\kappa_{ig}^{out}\),
e \(V_i=v_iQ_i\) sob fechamento completo. Esta invariância **não vale universalmente** quando U depende de horas de equipe, espera, perdas ou gargalos compartilhados.

## 3. Razões semanais exatas

Toda referência comparável registra **a mesma configuração e horizonte** de quantidade \(q_{ij}^{ref}>0\) e custo \(C_{ij}^{ref}>0\), com id de proveniência física e contábil. Não inferir esses valores de \(\gamma/\rho\) de bases diferentes.

Quando \(q_{ij}>0\), defina:
\[
 \zeta_{ij}=\frac{C_{ij}^{op}}{C_{ij}^{ref}},\quad
 \pi_{ij}=\frac{C_{ij}^{op}/q_{ij}}{C_{ij}^{ref}/q_{ij}^{ref}},\quad
 \chi_{ij}=\frac{q_{ij}}{q_{ij}^{ref}}.
\]
\[
 \boxed{\zeta_{ij}=\chi_{ij}\pi_{ij}}.
\]
Prova algébrica: \((q/q^{ref})[(C/q)/(C^{ref}/q^{ref})]=C/C^{ref}\).
Se q=0, a razão pi é UNKNOWN (divisão por zero), ainda que zeta exista; não certificar multiplicando zero por UNKNOWN.

A igualdade \(\chi=e\phi\) só vale para referência \(q^{ref}=B^0\) e \(B>0\). Portanto a expressão histórica \(\zeta=e\pi\) vale **apenas se phi=1**, e não é identidade para semana parcial.

## 4. Agregação por atividade e médias

Defina um conjunto J_i de semanas comparáveis que **não descarte semanas com K contratado e q=0**. Sob as mesmas bases de referência, suponha
\(C_i^{op}=\sum_jC_{ij}^{op}\), \(C_i^{ref}=\sum_jC_{ij}^{ref}>0\),
\(Q_i^{op}=\sum_jq_{ij}>0\), \(Q_i^{ref}=\sum_jq_{ij}^{ref}>0\).
Então
\[
 \zeta_i=\frac{C_i^{op}}{C_i^{ref}},\quad
 \chi_i=\frac{Q_i^{op}}{Q_i^{ref}},\quad
 \pi_i=\frac{C_i^{op}/Q_i^{op}}{C_i^{ref}/Q_i^{ref}},\quad
 \boxed{\zeta_i=\chi_i\pi_i}.
\]
Não somar razões semanais nem substituir chi por média da eficiência externa ponderada pelo número de equipes. Com referência física q_ref=B0, a utilização acumulada é a média **ponderada por capacidade física**:
\[
 \chi_i^{cap}=\frac{\sum_jq_{ij}}{\sum_jB^0_{ij}}
 =\frac{\sum_{j:B^0>0}B^0_{ij}\chi^{cap}_{ij}}
        {\sum_jB^0_{ij}},
\]
quando o denominador for positivo. A expressão continua válida se F_i(m) for não linear e se houver semana interior de produção zero.

## 5. Fração variável real, BDI e denominadores

Somente para bases reconciliadas e \(K_{ij}+V_{ij}>0\),
\[
 \delta_{ij}=\frac{V_{ij}}{K_{ij}+V_{ij}},\qquad
 \delta_i=\frac{\sum_jV_{ij}}{\sum_j(K_{ij}+V_{ij})}.
\]
Se cada lançamento financeiro pertence a exatamente uma categoria k,
\[
 C_{ij}^{op,\beta}=\sum_k(1+\beta^k)C_{ij}^k,\quad
 \beta_{ij}^{eq}=
 \frac{\sum_k\beta^k C_{ij}^k}{\sum_kC_{ij}^k},\quad
 \sum_k C_{ij}^k>0.
\]
Se BDI de K e V for ponderado **nas próprias bases realizadas**,
\(\beta_{ij}^{eq}=(1-\delta_{ij})\beta_{ij}^K+\delta_{ij}\beta_{ij}^V\).
Se K ou V for zero, a taxa do bloco nulo é indefinida; a soma de contribuições por categoria permanece válida. O BDI da atividade é ponderado por lançamentos, não pela média de eficiência. BDI é aplicado **uma única vez por lançamento**.

## 6. Contraexemplos e casos de aceitação exatos

Hipóteses: H=40 h, F(1)=10 un/h, capacidade instalada semanal B0=400; referência comparável por semana \(q^{ref}=400\), \(C^{ref}=800\); tarifa semanal **integral** K=400; taxa física \(V=q\) (1 R$/un); \(\beta_K=30\%\), \(\beta_V=4\%\).

| Caso | Quantidades semanais q | K total | V total | C operacional | C referência | chi | zeta | pi |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Parcial Q=100 | 100 | 400 | 100 | 500 | 800 | 1/4 | 5/8 | 5/2 |
| Três semanas Q=900 | 400,400,100 | 1200 | 900 | 2100 | 2400 | 3/4 | 7/8 | 7/6 |
| Interior zero Q=900 | 400,0,400,100 | 1600 | 900 | 2500 | 3200 | 9/16 | 25/32 | 25/18 |
| Semana cheia Q=400 | 400 | 400 | 400 | 800 | 800 | 1 | 1 | 1 |

Na primeira linha, phi=1/4, e=1, zeta=5/8 **não** é e*pi=5/2.
Delta variável é 100/500=1/5, custo com BDI é
\(400(1{,}30)+100(1{,}04)=624\), e
\(\beta^{eq}=624/500-1=31/125=24{,}8\%\).
Semana interior com q=0, K=400: pi indefinida; não descartar K da agregação.

Os exemplos são testados em
tests/reference_formalism/test_fractional_ledger_identities.py
com frações racionais puras, sem importar o runtime.

## 7. Limites de certificação

Estas são identidades algébricas **condicionadas** à proveniência de referência e ao rateio de custos. O runtime financeiro só receberá certificado após P11-B, #17, #18, #20 e #23. A existência de F(m) no cronograma não comprova a reconciliação financeira nem viabilidade global RCPSP (#14/#15).
