# P13-A — Regimes econômicos de presença contratual (ativo, standby, off-hire)

**Issue:** [#13](https://github.com/brunolnetto/concilium/issues/13), **epic:** [#8](https://github.com/brunolnetto/concilium/issues/8), **onda:** W0. A integração P13-B é posterior e obrigatória para fechar #13. Nenhum regime deste documento emite certificado GO.

## 1. Separação física × comercial

Considere o recurso homogêneo de tipo \(g\), com demanda física \(d_{gj}\) instâncias por semana, presença contratual \(x_{gj}\ge d_{gj}\) e standby \(s_{gj}=x_{gj}-d_{gj}\). Off-hire significa **ausência de contrato e de presença física paga**; não é standby de custo zero. A capacidade física \(F_i(m)\), os gargalos e as relações de precedência independem das tarifas.

O modelo temporal de P16 usa cadeias de presença com início e fim, respeitando quantidade de instâncias, limite de gap \(\mathrm{max\_idle\_gap}\), tarifas e eventos de mobilização. Para um contrato sem escalonamento de valores, os custos de presença são

\[
K^{presence}=\sum_{g,j}\left(c_g^{act} d_{gj}+c_g^{idle}s_{gj}\right);
\qquad
K^{mov}=\sum_{\mathrm{cadeias}}\left(c_g^{mob}+c_g^{demob}\right).
\]

A natureza de contabilização de \(K^{mov}\) é **IND / MOBILIZATION_EVENT / DEMOBILIZATION_EVENT** no livro P17, não o componente semanal K definido como custo de presença ativa + standby. Logo o custo econômico total de contrato é \(K^{presence}+K^{mov}\), mas um mesmo evento não pode ser adicionado mais de uma vez a resultados ou BDI.

## 2. Seletor econômico explícito e hipóteses

Os nomes de regime **não** podem ser inferidos implicitamente da magnitude de uma tarifa:

- \`FULL_RATE_STANDBY\` — **baseline normativo**. \(c_g^{act}=c_g^{idle}\ge0\); a igualdade implica \(K^{presence}=\sum_{g,j} c_g^{act}x_{gj}\). Pressupõe recursos homogêneos fungíveis dentro de cada \(g\), tarifas lineares fixas, e ausência de desconto contratual por ociosidade.
- \`DISCOUNTED_STANDBY\` — variante contratual válida. \(0\le c_g^{idle}<c_g^{act}\) com ambas as tarifas declaradas no contrato; não utilizar a identidade baseline \(K=c^{act}\sum x\). Off-hire antes/depois de uma cadeia tem custo de presença nulo **somente porque o contrato foi efetivamente encerrado**, com movimentos e restrições pertinentes modelados.
- \`EXPLICIT_OFF_HIRE\` — regime com períodos desligados declarados e permitidos pelas condições do contrato; não permite escolher arbitrariamente \(x=d\) para ocultar permanência obrigatória, lead time ou a taxa de remobilização. Tarifas presenciais continuam explícitas. Não reinterpretar semana idle como off-hire.
- \`UNKNOWN_CONTRACT\` — **não avaliável**; nenhum custo total, EBITDA, BDI ou certificado pode ser computado com fallback gratuito. A ausência de \`regime\`, tarifa, unidade monetária, horizonte ou origem/propriedade do contrato mantém a decisão \`NOT_EVALUATED\`.

O P13-B introduzirá/propagará o seletor tipado para o modelo canônico e os adapters financeiros; este P13-A é referência matemática e oráculo **independente do runtime**. O \`ResourceTariff\` atual de P16 distingue \`active_week\`, \`idle_week\`, \`mobilize\`, \`demobilize\`, mas sem promover automaticamente esses valores a uma certificação documental do regime comercial de um projeto.

## 3. Decisão intertemporal e custo contrafactual

Um recurso exigido por uma semana, depois não exigido por \(k\) semanas e exigido novamente deve comparar exatamente

\[
C_{\mathrm{keep}}=k\,c_g^{idle}
\quad\text{versus}\quad
C_{\mathrm{split}}=c_g^{demob}+c_g^{mob},
\]

desde que \(\mathrm{max\_idle\_gap}\ge k\), desligamento/remobilização admissíveis e não exista mínimo de permanência ou lead time não cumprido. Se \(C_{\mathrm{keep}}<C_{\mathrm{split}}\), manter standby é economicamente ótimo; se maior, separar contratos é melhor; **em empate e com ambas as estratégias viáveis, manter a cadeia (KEEP) é o desempate determinístico canônico**, evitando transições desnecessárias (CONVENCOES_NORMATIVAS.md, §4). Se houver restrições adicionais não verificadas, a escolha é NOT_EVALUATED, nunca um KEEP presumido. Sob outras condições, o contrafactual pode ser **inviável**, não apenas mais caro. Standby economicamente ótimo não implica perda de produtividade \(\eta_s\).

Falsificador: \(k=2\), \(c^{act}=100\), \(c^{idle}=25\), \(c^{mob}=40\), \(c^{demob}=40\). Manter custa 50 e separar custa 80; \(\sum x\,c^{act}\) seria 200 nas duas semanas idle, portanto a igualdade do baseline é **falsa** no regime descontado. No baseline \(c^{idle}=100\), manter custa 200 e separar custa 80, de modo que a decisão ótima pode se inverter.

Para custos fixos \(c^{mob}\), \(c^{demob}\) e taxas não negativas, a diferença de custo entre as duas estratégias é \(k c^{idle}-(c^{mob}+c^{demob})\). A escala física \(d_{gj}\), a quantidade entregue \(q_{ij}\) e os limites \(F_i(m)\) permanecem invariantes sob simples troca de tarifa, desde que a política de contratação não altere a viabilidade da agenda.

## 4. Separação MAT/COMB e propriedade do custo

O custo contratual MO/EQ **não** incorpora automaticamente consumíveis por hora. Os bens \`MAT\` e \`COMB\` são medidos em unidades físicas e adquiridos por \`PhysicalPurchase\`, segundo base de consumo e preço próprios (P18); os pagamentos são identificados por \`event_id\` e categoria e não podem ser relançados como standby K.

Consumo exclusivamente proporcional à entrega \(U_{gij}=\kappa_{g,i}^{out} q_{ij}\) e preço constante implica \(V(Q)\) invariante à partição semanal. Consumo em idle, perdas no estoque, combustível de mobilização, desperdício produtivo e suprimento externo **quebram potencialmente essa identidade**; P13-B especifica um seletor de consumo operacional distinto do contrato de presença, com contabilização não sobreposta a ACQUISITION, HOLDING e MOB/DEMOB.

Para o baseline, a invariância \(V(Q)=\sum_g p_g\kappa_{g,i}^{out} Q_i\) é **condicional à taxa física por saída declarada**, não universal. Preço ou quantidade nulos sem prova não autorizam lançamento de zero. A falta de medição deve produzir \`UNKNOWN\`/ \`NOT_EVALUATED\`.

## 5. Identidades e falsificadores de aceite

| Invariante | Baseline FULL_RATE_STANDBY | DISCOUNTED_STANDBY | OFF_HIRE permitido |
| --- | --- | --- | --- |
| \(s=x-d\ge0\) | Sempre | Sempre | Sempre, com presença contratual real |
| \(K^{presence}=\sum c^{act}x\) | Sim | **Não** | Somente se active=idle no período de presença |
| \(K^{presence}=\sum(c^{act}d+c^{idle}s)\) | Sim | Sim | Sim sobre semanas efetivamente contratadas |
| MOB/DEMOB | Eventos exclusivos | Eventos exclusivos | Eventos exclusivos em cada nova cadeia |
| Custos MAT/COMB | Journal físico separado | Journal físico separado | Journal físico separado |
| \(V(Q)\) invariante | Apenas com \(\kappa^{out}\) e preços fixos | Mesma hipótese | Mesma hipótese |
| GO com regime ausente | Não | Não | Não |

Os testes independentes de P13-A cobrem custo baseline, desconto, troca ótima keep/split, empate, falta de tarifa e classificação de custo. Não importam otimizador de produção, Skill 06 ou dados de catálogo e não declaram GO. O aceite integral da issue #13 depende de P13-B e da paridade LONGO/RESUMIDO/TeX.
