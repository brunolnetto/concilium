# P11-B — Projeção operacional auditável de eficiência realizada e custos K/V

**Predecessor:** P11-A [#89](https://github.com/brunolnetto/concilium/pull/89) (integrado); **issue:** [#11](https://github.com/brunolnetto/concilium/issues/11), Onda 0.

## Fonte operacional

O adaptador `application/scheduling/realized_financial_metrics.py` consome diretamente:

- `DistribuicaoSemanal` do Skill 04, incluindo `qtd_executada`, `qtd_acumulada`, `q_max_celula` e `capacidade_disponivel_semana`; exige cronologia contígua, soma exata `Σq=Q`, disponibilidade `q≤B≤R` e rejeita capacidade histórica ausente.
- `ExclusiveCostLedger` do livro P17/P18/P19, com `CostPosting.event_id`, natureza, categoria MO/EQ/MAT/COMB/IND, valor `Fraction` e semana ISO; a projeção é **read-only**, não gera custo, rateio ou evento adicional.
- Percentuais BDI por categoria, explicitamente tipados como `Fraction`, aplicados **uma única vez por lançamento**. Sem alíquotas completas, a operação falha.
- Opcionalmente um preço variável físico por saída `v [R$/u_i]`, obtido **independentemente do próprio custo V observado**, e **somente** para uma atividade isolada. Exige `V_j=v·q_j` comprovado, para então publicar `ζ/π` financeiros consistentes com `R_j`.

O retorno `RealizedFinancialProjection` contém realizações físicas por atividade, valores financeiros por semana, totais K/V/indiretos, `price_once_bdi`, `effective_bdi`, e as razões `ζ,π,ε_real` somente quando há condições para calculá-las sem dividir por zero.

### Fronteira determinística dos `float` da Skill 04

As células persistidas são `float` provenientes de `_build_dist_cell()`. Para permitir os casos reais `Q=0.3` e `Q=0.4`, a projeção verifica **sem tolerâncias ad hoc** as duas operações binárias daquele construtor:
`q_j = min(B_j, max(0, Q_float - acumulado_float_anterior))` e `acumulado_float_novo = acumulado_float_anterior + q_j`. Se qualquer igualdade binária for falsa, a célula é rejeitada. Após essa confirmação de origem, o mesmo contrato é recalculado em `Fraction` sobre `B_j` e `Q` decimais canônicos, recuperando quantidades 0.1 da terceira/quarta semanas sem criar produção superior à capacidade. Essa transformação é **restrita às células planejadas pelo Skill04** (`desempenho_observado=NAO_OBSERVADO`), não corrige medições externas não certificadas. O ledger físico V deve conciliar com o quantitativo canônico, sem arredondamento de preço.

## Distinções obrigatórias

`capacidade_disponivel_semana/q_max_celula` é a disponibilidade **nominal exógena**; `qtd_executada/q_max_celula` é **eficiência realizada**; `qtd_executada/capacidade_disponivel_semana` é a **fração de fechamento**. O campo persistido de controle `eficiencia` e `eta_s` não são utilizados como multiplicadores na projeção. A semana sem produção e com K contratado continua contabilizada. Com capacidade disponível zero, a fração de fechamento é `None`, não zero implícito.

A extensão `ExactFinancialReconciliation.project_skill04_realization()` oferece um ponto de integração operacional **após reconciliação física P17/P18/P19**. Essa entrada cruza os saldos `WeekFinancialBalance` com os lançamentos originais e rejeita snapshot adulterado.

**Múltiplas atividades:** somar `Q_i` entre unidades diferentes e repartir K compartilhado por item sem prova de propriedade seria incorreto. Assim, para múltiplas atividades a projeção conserva eficiência individual e custo **do projeto** por semana, mas retorna `activity_zeta=None`, `activity_pi=None` e `activity_efficiency=None` no agregado financeiro. Um rateio certificado exige evidência tipada de instância/atividade (#17/#20).

**Escopo de autoridade:** `P11_B_READ_ONLY_PREVIEW_NOT_PROJECT_GO`. O adaptador não altera `Resultado` de Skill 06 automaticamente, não gera `PROJECT_GO`, não certifica políticas de standby (#13), não testa contratos multilaterais de composição (#16/#17), nem substitui o journal de preços e BDI de #20/#21.

## Falsificadores do runtime

Testes com **instâncias reais** `DistribuicaoSemanal`, `CostPosting` e `ExactFinancialReconciliation` verificam: semana parcial, três semanas, semana de ausência climática com K integral, consistência de `Q/ΣR` e `ζ=ε_real·π`, BDI categorial once-only, multiatividade sem rateio inventado, V diferente do consumo físico esperado, ausência de semana zero, custo fora do período, cumulativo adulterado, capacidade insuficiente, escopo pendente, BDI incompleto, snapshot P20 fraudulento e event IDs duplicados.

O conjunto de testes usa `Fraction` e falha sobre discrepância exata; não arredonda valores intermediários, nem inventa tolerâncias. **Persistência/exportação de campos consolidados da Skill06 deve ser integrada por um estágio posterior**, sem mutação do ledger. Fechar #11 somente quando esse requisito original e demais critérios forem comprovados, não apenas após este adaptador.
