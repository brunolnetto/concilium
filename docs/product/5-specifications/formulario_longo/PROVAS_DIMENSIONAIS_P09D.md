# P09-D — Prova dimensional das candidatas normativas

**Contexto:** epic #8 → issue #9, Onda 0. P09-A/B [#28/#43](https://github.com/brunolnetto/concilium/issues/9) e P09-C [#86](https://github.com/brunolnetto/concilium/pull/86) já forneceram convenções, falsificadores, inventário de equações e símbolos.

## Modelo de prova

O inventário de P09-C contém **93 equações display**, das quais 21 são `NORMATIVE_CANDIDATE` e **72 permanecem `CONDITIONAL_OR_UNCERTIFIED`**. O arquivo `NORMATIVE_DIMENSION_PROOFS_P09D.json` fornece regra e cópia exata da expressão para cada uma das 21 candidatas. `test_p09d_normative_dimension_proofs.py` exige correspondência bijetiva, identidade textual e prova independente para cada regra, sem importar módulos de produção.

A álgebra de dimensões utiliza bases independentes **R$**, saída física `u_i`, bem físico `unid_g`, frente, hora, dia, semana e mês. Há provas e contraexemplos verificáveis para tarifa mensal (R$/mês)→horária (R$/h), `κ [unid_g/h]·p [R$/unid_g]`, vazão `F_i(m) [u_i/h]`, incremento de rampa `μ [frentes/semana]`, fechamento `φ` adimensional, soma física Q e BDI adimensional. Identidades de conjuntos/tuplas/enums são testadas por contratos de tipo, não por atribuição de unidades físicas arbitrárias.

## Regra temporal corrigida

`F_i(m) [u_i/h] × (h_i d_i) [h/semana]` tem dimensão de **taxa semanal** `u_i/semana`. Para produzir `q_ij` e `B_ij` em `u_i` por **célula**, há integração pelo comprimento `Δw_j=1 semana`. A notação abreviada da referência sempre incorpora essa célula; isso foi explicitado em LONGO, RESUMIDO, TeX e CONVENCOES. Da mesma forma, `K = taxa horária × horas/semana × Δw_j`, enquanto a fração final `φ<1` não cria abatimento automático em contrato semanal.

Sem a duração da célula, os tipos `u_i/semana` e `u_i` são **distintos** e o teste falha. As limitações sobre semanas não produtivas, calendário inatingível ou alteração do horizonte continuam em #14/#15. Valores de `h_i d_i` e `F_i(m)` pressupõem horas efetivamente disponíveis e não aplicam disponibilidade duas vezes.

## O que a prova não estabelece

- **Aritmética dimensional não prova viabilidade ou correspondência com a implementação de produção.** Um calendário incapaz de entregar Q ainda é NOGO mesmo com dimensões corretas.
- Os **72 casos condicionais** dependem principalmente de #11/#13 e da validação do pool, consumo físico, estoque, diário e BDI em #16–#21. Não são certificados por este conjunto de testes.
- Regra de markup regulatório, preço, lucratividade, persistência de certificado e E2E pertencem a ondas posteriores. Nenhum resultado aqui autoriza `PROJECT_GO`.
- O inventário de 53 símbolos contém interfaces de alto impacto, mas ainda é necessário verificar aliases e sub/sobrescritos de todas as representações, erros de base/tolerância e hipóteses contratuais. Esta PR não deve fechar automaticamente #9.

## Aceitação deste pacote

1. Exatamente 21 candidatas, cada qual com regra/expressão rastreáveis; nenhuma condicional promovida por engano.
2. Falha intencional para taxa temporal confundida com quantidade semanal e para preço físico inferido de proxy monetário.
3. Paridade documental da largura temporal da célula nas quatro representações.
4. Testes de referência independentes verdes, suíte CI/Ruff/ty/lock no HEAD, revisão e ausência de findings antes do merge.

**Sequência:** integração P09-D → auditoria integral dos símbolos/aliases restantes em #9 → somente então possível encerramento de #9 e ativação da #11.
