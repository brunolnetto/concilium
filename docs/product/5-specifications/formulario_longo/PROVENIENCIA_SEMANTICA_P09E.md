# P09-E — Fechamento de proveniência simbólica e paridade semântica

**Issue de referência:** [#9](https://github.com/brunolnetto/concilium/issues/9), [epic #8](https://github.com/brunolnetto/concilium/issues/8). Este pacote apenas protege a **classe normativa candidata**. Não altera matemática financeira condicional nem publica certificado global.

## Unidades, símbolos, fontes e saídas

O inventário P09-C registra 93 expressões do LONGO, com dimensões esperadas, categorias, origem e saída. A classificação mantém **21 candidatas normativas** e **72 condicionais**; P09-D provou dimensionalidade/tipos das 21 sob suas precondições explicitadas.

`NORMATIVE_SYMBOL_COVERAGE_P09E.json` vincula **21/21** candidatas a tokens explícitos da expressão, incluindo unidades, proveniência e consumidor. O verificador exige que cada token exista literalmente na sua expressão original, rejeita aliases duplicados por equação e exige assinatura exata nas provas independentes P09-D. Também inclui localizadores para os textos RESUMIDO/TeX e preserva aliases representacionais conhecidos:

- `m_i(\tau;N)` no RESUMIDO versus `m_i(\tau)` e `N_i` no LONGO/TeX;
- `\mathcal A_j` versus `\mathcal{A}_j` na lista semanal de atividades;
- `\sum_jq_{ij}=Q_i` no RESUMIDO versus `\sum_{j=j_i^0}^{j_i^1}q_{ij}=Q_i` no LONGO/TeX, sob atividade ativa no intervalo;
- `\varphi_i=q_{final}/B_{final}` e a expansão `B_{final}=F_i(m_i(N_i-1)) h_i d_i ε_{final}\) integrado por `Δw=1 semana`.

Os aliases são localizadores sintáticos para constatar a presença do contrato no formato alternativo. **Não substituem prova matemática por comparação de strings.** O teste de P09-D e seus falsificadores dimensionais continuam obrigatórios. Testes negativos eliminam a possibilidade de afirmar cobertura removendo uma equação ou reclassificando uma condicional como normativa.

## Política de aceite e fronteiras

O controle do contrato local de #9 exige unidade e proveniência para os símbolos do conjunto normativo e a distinção documentada das demais relações ainda condicionais (#11, #13, #16–#21). Isso não significa que **todos os símbolos de todas as equações condicionais** estejam certificados: os 53 símbolos de alta criticidade do P09-C e o inventário transversal cobrem as interfaces conhecidas; o detalhamento financeiro de cada relação condicional deve ocorrer nas suas issues de origem.

O fechamento de #9 somente poderá ser considerado após este PR integrar os testes, passar no CI do HEAD, receber revisão sem bloqueios, e uma auditoria humana conferir especialmente os domínios degenerados, precedência física, fronteira temporal, tolerâncias, divisão por zero, empate financeiro e correspondência das três representações.

**Não confundir critérios locais de especificação com certificação do sistema:** mesmo com #9 concluída, um `PROJECT_GO` exige todas as ondas, custo sem dupla contagem, execução/física válida, reconciliação financeira e evidências adversariais.

## Execução

```bash
python -m pytest --confcutdir=tests/reference_formalism tests/reference_formalism -q
```

Suíte independente, sem importar runtime de produção.
