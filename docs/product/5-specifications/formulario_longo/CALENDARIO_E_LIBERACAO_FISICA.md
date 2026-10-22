# P12-A — Calendário absoluto, duração e liberação física

**Status:** contrato matemático normativo para precedências semanais do tipo **Q–FS**. Este documento define o sinal físico de #12; #15 implementará e certificará o reescalonamento RCPSP. Tipos SS/FF e relógio intrassemanal só podem ser admitidos mediante contratos separados. Base de produtividade: [CAPACIDADE_E_RECURSOS.md](CAPACIDADE_E_RECURSOS.md).

## 1. Tempo discreto e produtividade única

Seja \(j\in\{1,\ldots,J_{\max}\}\) uma **semana absoluta** do projeto. Uma atividade \(i\), iniciada na semana \(s_i\), possui duração candidata inteira \(N_i\) e está mobilizada no intervalo semiaberto \([s_i,s_i+N_i)\). Uma semana \(j\) corresponde ao período civil que começa na fronteira \(j\) e termina na fronteira \(j+1\).

\(F_i(m)\) [unidade física de \(Q_i\)/h] é a **única** taxa de produção da composição mobilizada; nunca contém clima, calendário, fração de fechamento ou equipe não mobilizada. Escreva \(H_i\) [h/semana], \(p_j,c_j,a_i\in[0,1]\), com \(p\)=praticabilidade, \(c\)=disponibilidade calendárica, \(a\)=disponibilidade da jornada **somente se \(H_i\) ainda é nominal**:

\[
B_{ij}(s_i,N_i)=F_i(m_i(j-s_i;N_i))\,H_i\,p_j\,c_j\,a_i,\quad
q_{ij}=\min\{(Q_i-\sum_{k<j}q_{ik})_+,B_{ij}\}.
\]

Todos os fatores devem estar versionados; se não houver evidência suficiente para distinguir \(H_i\) nominal de horas já efetivas, o resultado é **UNKNOWN**, nunca \(a_i\) aplicado duas vezes. Fechamento \(\varphi_i=q_{i,j_i^1}/B_{i,j_i^1}\) não é perda física.

## 2. Busca de duração depende do início absoluto

Para \(s\) fixo e \(N\ge1\), \(\Pi_i(N;s)=\sum_{\tau=0}^{N-1}B_{i,s+\tau}(s,N)\). O teste de fechamento é \(\Pi_i(N;s)\ge Q_i\), limitado a \(s+N-1\le J_{\max}\), precedências, mobilização e recursos.

**É falso** que cada incremento de \(N\) gere produção estritamente positiva: um período pode ter \(p_j=0\) ou \(c_j=0\). E, se o ramp-profile depende de \(N\), nem a monotonicidade fraca de \(\Pi_i(N;s)\) é automática: ao mudar \(N\), \(m_i(\tau;N)\) pode mudar também em semanas anteriores. Por isso não se pode usar busca binária sem uma prova específica da monotonicidade para os parâmetros fixados. A enumeração limitada \(N=1,\ldots,J_{\max}-s+1\) é terminante, mas não dispensa **prova de viabilidade RCPSP**.

**Contraprova de início:** capacidade nominal \(F_i(m)H_i=100\,u/semana\), \(Q_i=100\,u\), calendário semanas 1,2,3 com praticabilidade \((0,1,1)\) e demais fatores iguais a 1. Início \(s=1\) exige \(N=2\); início \(s=2\) exige \(N=1\). Uma duração calculada antes de \(s_i\) não é em geral utilizável depois do deslocamento.

## 3. Limiar físico e fronteira de semana

Para predecessora \(b\) com \(Q_b>0\), \(\theta_{b\to i}\in(0,1]\), defina o progresso **após encerrar** a semana \(j\),

\[
S_b(j)=\sum_{k\le j}q_{bk},\quad
r_{b\to i}=\min\{j:S_b(j)\ge\theta_{b\to i}Q_b\}.
\]

Se esse conjunto for vazio, a aresta é **INVIÁVEL / não liberada**. Como \(S_b(j)\) só é conhecido no **fim** da semana \(j\), o sucessor **não** pode começar na mesma semana \(r_{b\to i}\) no modelo sem relógio intrassemanal.

Com lag não negativo \(\ell_{b\to i}\) contado em semanas inteiras **livres após a conclusão do limiar**, a precedência quantidade–fim/início é:

\[
\boxed{s_i\ge\max_{b\in\mathrm{pred}(i)}
\bigl(r_{b\to i}+1+\ell_{b\to i}\bigr).}
\]

Exemplo: \(Q_b=100\), quantidades semanais \((0,60,40)\), \(\theta=0.5\) e \(\ell=0\). O limiar é alcançado **ao fim da semana 2** e o sucessor só pode iniciar na semana **3**. Com \(\theta=1\), o predecessor termina ao fim da semana 3, liberando a semana 4. Semanas com \(q=0\) nunca antecipam a liberação.

Em arestas SS, FF, SF, com lags negativos ou progresso intrassemanal, as fórmulas acima **não** podem ser reaproveitadas implicitamente. Tais alternativas requerem tipo de evento e semântica próprios (pendente em #12/#15). Um predecessor com calendário terminado mas \(S_b<\theta Q_b\) não libera ninguém.

## 4. Revalidação conjunta com recursos

Após mover \(s_i\), \(N_i\) ou o perfil \(m_i\), é obrigatório recalcular todas as semanas e todos os predecessores afetados. Para recursos homogêneos \(g\), a viabilidade física semanal exige:

\[
\sum_{i:\;j\in[s_i,s_i+N_i)}a_{ig}(m_{ij})
\ \le\ \mathrm{disponibilidade}_{gj},\qquad \forall g,j.
\]

Se duas sucessoras forem deslocadas para a mesma semana e demandarem uma instância cada de um recurso com capacidade 1, a agenda deslocada é **inválida**, mesmo que cada atividade feche \(Q_i\) isoladamente. É necessário resolver de novo a contenção ou retornar NOGO.

O procedimento certificado é uma busca **limitada** sobre as escolhas de início, duração e mobilização, com checagem cumulativa de \(Q\), precedência física, capacidades e horizonte; uma heurística pode propor candidatos, mas não certifica soluções sem verificar todas as restrições. Exaustão sem solução é **INFEASIBLE**; falta de dado obrigatório é **UNKNOWN**; nenhuma delas autoriza GO.

## 5. Vetores que a implementação e o oráculo devem verificar

| Vetor | Entrada | Resultado |
|---|---|---|
| Início sensível ao calendário | \(Q=100\), \(B^{nom}=100\), \(p=(0,1,1)\) | \(N(s=1)=2\), \(N(s=2)=1\) |
| Limiar físico parcial | \(q_b=(0,60,40)\), \(\theta=0.5\), lag 0 | liberação **semana 3**, nunca semana 2 |
| Fechamento FS | \(q_b=(0,60,40)\), \(\theta=1\), lag 0 | liberação semana 4 |
| Predecessor não entregue | \(Q_b=100\), \(q_b=(0,0,0)\), \(\theta>0\) | não liberado / NOGO se não houver horizonte viável |
| Contenção pós-atraso | duas sucessoras usando um recurso cada, pool=1, mesma semana | reescalonar uma ou NOGO |
| Semana 100% impraticável | \(p_j=0\), \(F_i(m)>0\) | \(B_{ij}=q_{ij}=0\), **sem alterar** \(F_i(m)\) |

**Próximas provas:** P12-B adiciona os casos ao oráculo independente, #14 converte inviabilidade física em resultado fail-closed e #15 reexecuta RCPSP após qualquer mudança do calendário. Este documento, isoladamente, não emite certificado.
