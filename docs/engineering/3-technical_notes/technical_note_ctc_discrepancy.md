# Nota Técnica: Divergência de Orçamento de Referência - Projeto CTC

**Data:** 07 de Maio de 2026  
**Assunto:** Auditoria de Benchmark - Projeto CTC (Barra do Ribeiro - RS)  
**Status:** Anomalia Identificada (Referência Inflada)

---

## 1. Contexto do Diagnóstico
Durante a execução do ciclo de benchmarks do motor Concilium, o projeto **CTC** apresentou um desvio negativo de **-77.72%** (Concilium: R$ 16.7M vs Referência: R$ 75.1M). 

Uma auditoria profunda nos arquivos de origem revelou que esta divergência não decorre de erro de cálculo da ferramenta, mas sim de uma inconsistência estrutural no orçamento de referência fornecido.

## 2. Evidências Encontradas

### 2.1. Descolamento entre EAP e Resumo (Header)
Ao analisar o arquivo de origem `2025_08_12_PLANEJAMENTO_CTC_BARRA DO RIBEIRO (RS).xlsm`, observou-se:
*   **Aba "RESULTADO":** Declara um Custo Direto Total de **R$ 75.180.960,59**. Este é o valor capturado pelo benchmark como alvo (target).
*   **Aba "CURVA ABC":** Lista todos os itens de serviço com suas respectivas quantidades e preços unitários. A soma dos itens desta aba totaliza aproximadamente **R$ 17.2M**.

### 2.2. Comparação de Itens Críticos
Os itens de terraplenagem, que compõem o maior volume da obra, possuem preços unitários de mercado na Curva ABC:
*   **Aterro Compactado (1.5):** R$ 10,13/m³ (Total R$ 7,4M)
*   **Escavação/Carga/Transporte (1.2):** R$ 6,02/m³ (Total R$ 3,6M)

Para que o Custo Direto atingisse os R$ 75M declarados no cabeçalho, os preços unitários precisariam ser ~5x maiores (Ex: Aterro a R$ 50,00/m³), o que foge completamente aos parâmetros de mercado para este tipo de obra.

## 3. Conclusão e Recomendação Comercial

O valor de **R$ 75.1M** na referência do CTC é **comercialmente injustificável** com base na EAP de projeto anexada. 
*   **Hipótese provável:** O arquivo de referência é um template onde o quadro de "Resultado" foi preenchido com um valor de verba global ou meta comercial, enquanto a Curva ABC reflete o custo real orçado.
*   **Ação Recomendada:** O benchmark do CTC deve ser considerado **inválido** para fins de calibração de produtividade até que a base de referência seja saneada pela equipe comercial. O motor Concilium está operando com aderência correta em relação à EAP técnica (R$ 16.7M vs R$ 17.2M da referência real).

---
*Gerado por Antigravity - Senior Engineering Agent*
