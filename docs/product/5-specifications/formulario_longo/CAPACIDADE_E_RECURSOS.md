# Contrato físico da mobilização: capacidade, recurso e ociosidade (P10-A)

**Estado:** correção normativa de §I.3.2, §IV e §XIV.1; custos derivados de §§III/V–VIII permanecem **não certificados** até a rederivação de #11. Dependências: #9, #10, #11, #13, #15, #16, #22.

## Definição 1 — Capacidade instalada

Em cada semana \(j\), \(m_{ij}\in\{0,\ldots,m_i^{max}\}\) é uma **decisão inteira sobre frentes realmente em operação**, não um coeficiente de eficiência. Para o grafo físico do processo, \(\mathcal G_i^D|_m\), defina

\[
F_i(m)=\operatorname{maxflow}(s_i,t_i;\mathcal G_i^D|_m)\quad [u_i/h],
\qquad F_i(0)=0.
\]

O grafo considera recursos realmente alocados. Arestas de infraestrutura compartilhada não são multiplicadas por \(m\). \(F_i\) é não decrescente se a mobilização acrescentar recursos sem retirar os anteriores, mas pode saturar por gargalos. Distinguem-se \(\rho_i^{front}\) (capacidade de **uma** frente independente, quando provada) e \(\rho_i^{peak}=F_i(m_i^{max})\), que são parâmetros distintos. Só no caso linear \(F_i(m)=m\rho_i^{front}\).

Há **uma única definição de produtividade física**: \(F_i(m)\) [\(u_i/h\)], estabelecida pela composição de recursos efetivamente mobilizada. Nem a praticabilidade nem o calendário mudam a definição de \(F\); eles limitam as horas/produtividade **disponíveis no período**. Defina \(H_i=h_i d_i\) [h/semana contratual], \(p_j\in[0,1]\) como praticabilidade da semana, \(c_j\in[0,1]\) como disponibilidade de calendário, e \(a_i\in[0,1]\) como fração efetiva de jornada, se ainda não estiver embutida em \(H_i\). Então

\[
\boxed{\rho_{ij}^{efetiva}=F_i(m_{ij})p_jc_ja_i\ [u_i/h],\qquad
B_{ij}=H_i\rho_{ij}^{efetiva},\qquad
q_{ij}=\min\left\{\left(Q_i-\sum_{k<j}q_{ik}\right)_+,B_{ij}\right\}.}
\]

Esta é a única transformação de produtividade usada em MANUAL, AUTO e WMP.
A disponibilidade do calendário da semana ISO é transmitida também ao
WMP. \(\rho^{efetiva}\) depende de \(F(m)\) da composição, praticabilidade e
calendário; o fechamento por saldo não é uma nova perda de produtividade.

A convenção anterior \(\varepsilon_{ij}^{exog}=\eta_{p,j}\eta_{w,j}\) é **somente abreviação** do produto exógeno \(p_jc_ja_i\); não introduz outra produtividade nem um multiplicador de alocação de equipes. Quando \(H_i\) já é a jornada efetiva, adota-se \(a_i=1\) para não contar a perda de horas duas vezes. Os multiplicadores **não** podem já estar incorporados na taxa calibrada \(F_i(m)\), a menos que haja normalização explícita por condições de referência.

O clima/praticabilidade e o calendário são estados semanais auditáveis; o fechamento \(\varphi_i=q_{i,j_i^1}/B_{i,j_i^1}\) é somente uso do escopo e não reduz \(F_i(m)\) nem os custos de permanência de recursos.

**Não existe perda por alocação de equipes \(\eta_s\)** multiplicando \(q\). A quantidade \(\alpha_i(m)=F_i(m)/F_i(m_i^{max})\) é uma razão de capacidade **diagnóstica**, nunca uma eficiência adicional. A fração \(\varphi_i=q_{i,j_i^1}/B_{i,j_i^1}\in(0,1]\) mede apenas fechamento físico; não é perda de produtividade. \(B=0\) e \(Q_{rest}>0\) => semana improdutiva; horizonte sem capacidade suficiente => inviabilidade, não GO.

## Definição 2 — Demanda e presença contratual

Para tipo homogêneo de recurso \(g\), defina \(a_{ig}(m)\) = unidades necessárias para \(m\) frentes da atividade \(i\). No regime de composição independente \(a_{ig}(m)=m a_{ig}^{front}\); infraestrutura compartilhada pode demandar função diferente e explícita.

\[
d_{gj}=\sum_i a_{ig}(m_{ij}),\quad
x_{gj}\ge d_{gj},\quad s_{gj}=x_{gj}-d_{gj}\ge0.
\]

\(d\) é **demanda de uso**, \(x\) é recurso contratado presente e \(s\) é standby pago não utilizado. Uma frente **não mobilizada** \((m_i^{max}-m_{ij})\) não equivale a standby: ela não gera, por si só, custo ou perda. Saturação de \(F_i(m)\) por um gargalo também não equivale a standby contratual.

## Problema 1 — Otimização economicamente disciplinada

Escolher \(m\), datas e contratos sujeitos ao escopo \(\sum_j q_{ij}=Q_i\), disponibilidade, precedência física, horizonte, restrições trabalhistas e mobilização, minimizando

\[
\sum_{gj} [c_{gj}^{act}d_{gj}+c_{gj}^{idle}s_{gj}]
+\sum_{\text{eventos}} (c^{mob}+c^{demob})+C^{cons}+C^{ind,other}.
\]

MOB/DEMOB é contabilizado **uma única vez** no objetivo e no diário, mesmo quando classificado como indireto. Em regime-base \(c^{act}=c^{idle}=c^{sem}\), a parcela de presença vale \(\sum_{gj}c^{sem}_{gj}x_{gj}\).

**Proposição:** Se \(c^{idle}>0\), não há mínimo contratual nem custo/tempo de transição, e é permitido desligar toda instância ociosa, qualquer ótimo tem \(s_{gj}=0\). Prova: reduzir \(x_{gj}\) até \(d_{gj}\) não altera a produção nem viola restrição e reduz estritamente o objetivo. **O resultado não vale** com custo de mobilização positivo ou mínimo de permanência.

**Contraexemplo:** necessidade de 1 equipamento nas semanas 1 e 3, nenhum na semana 2; semana standby R$100, demob+remob R$160. Manter custo marginal R$100 e é ótimo, embora \(s_{g,2}=1\). Se demob+remob custa zero, manter não é ótimo. Minimizar ociosidade *fisicamente* e minimizar custo *economicamente* não são problemas idênticos.

**Hierarquia de provas:** o otimizador por nível de demanda do §IX é exato para o pool fungível **condicionado a** \(m\) e schedule fixos; essa prova não certifica ótimo global de \(m\), schedule e pool simultâneos. Uma decisão sobre equipes extras sem aumento de produção pode ser economicamente dominada sem necessidade de penalidade \(\eta_s\).

## Casos analíticos obrigatórios no oráculo

| \(F(m)\) | \(m\) | \(H\) | \(q\) exógeno 1 | Demanda com 1 unidade de recurso por frente |
|---|---:|---:|---:|---:|
| \(10m\) | 2 | 40 | 800 | 2 |
| \(10m\) | 4 | 40 | 1600 | 4 |
| \(\min(10m,15)\) | 2 | 40 | 600 | 2 |
| \(\min(10m,15)\) | 4 | 40 | 600 | 4 |

A terceira e quarta linhas têm produção idêntica, mas mobilizar quatro frentes usa mais recursos; otimizar frentes é uma decisão custo/prazo, não aplicação de perda de eficiência ao valor de \(F(m)\).

## Invalidação de identidades derivadas

As expressões anteriores de \(q=\rho\,\eta_s\,H\,m\) e suas deduções para \(C^V\), \(\zeta\), \(\pi\), \(\delta\), BDI equivalente e invariância absoluta de consumíveis são **suspensas** enquanto não houver prova no caso de \(F(m)\) não linear e fechamento \(\varphi<1\). A identidade \(C^V=\gamma^V Q/\rho^{front}\) só decorre, sob hipótese de consumível proporcional ao produto e sem perdas, de uma razão unitária independente de \(m\); se o gargalo satura \(F\) enquanto os custos físicos por hora crescem com \(m\), essa hipótese não vale.

O PR P10-B deverá propagar \(F(m)\), \(m\), \(\eta_p\), \(\eta_w\), \(\varphi\), \(d\), \(x\) e \(s\) como grandezas distintas e testá-las contra este contrato.


## Protocolo observável da produtividade física única — #10 / #23

Para cada atividade e semana, a **única produtividade física horária**
continua sendo \(F_i(m_{ij})\), registrada em
**produtividade_fisica_horaria** em unidade_i/h, quando as horas
contratuais \(H_i>0\) são conhecidas. **q_max_celula=F_i(m_{ij})H_i**
é capacidade instalada. Praticabilidade, calendário e jornada produzem
uma capacidade distinta, mas **não uma segunda produtividade**:

\[
\text{capacidade_disponivel_semana} =
\text{q_max_celula}\ p_jc_ja_i,\qquad
q_{ij}=\min(\text{saldo},\text{capacidade_disponivel_semana}).
\]

A fração de fechamento mede o saldo entregue; não é desempenho observado.
O registro conserva a origem da capacidade com os valores
GRAFO_FLUXO, GRAFO_ELEMENTOS, TAXA_POR_FRENTE_ASSUMIDA,
FALLBACK_ARBITRARIO ou NAO_DECLARADA. **Fonte não é certificação:**
estado_calibracao=NAO_CERTIFICADA até #23 atrelar versão, composição e
evidência independente. O fallback de preview de 1000 unidades/h
não é uma calibração e **nunca sustenta GO**.

desempenho_observado=NAO_OBSERVADO distingue planejamento e controle.
Os campos legados eta_s, eta_w, eficiencia=1.0 continuam neutros por
compatibilidade: não são medições. Artefatos antigos sem horas contratuais,
sem F_i(m) horário ou capacidade disponível conservam None/NAO_DECLARADA.
Não inventar zeros ou produtividades retroativamente.

O certificado #23 exige origem e calibração válidas para GO; a
factibilidade de escopo, precedência, recursos e calendário continua
responsabilidade de #14/#15, e a prova diferencial pertence a #22.
