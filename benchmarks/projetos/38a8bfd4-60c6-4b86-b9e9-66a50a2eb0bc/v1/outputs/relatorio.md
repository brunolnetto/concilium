# Relatorio Analitico -- AGIS - Ferrovia Nova Transnordestina (Supressao e Terraplanagem)

**Gerado em:** 2026-05-29 23:35:18  
**Framework:** concilium  

---

## Sumario Executivo

O orçamento contempla obra de terraplenagem denominada **AGIS - Ferrovia Nova Transnordestina (Supressao e Terraplanagem)**, localizada em Ceara, Brasil, com execução prevista para o período 2026-06-01 -> 2027-06-27, (status atual: RASCUNHO).

O preço de venda totaliza **R$ 80,358,255.08**, composto por custo direto de R$ 46,843,791.49 e custo indireto de R$ 19,584,539.27. O resultado bruto apurado é de **R$ -1,503,271.69**, correspondendo a uma margem de **-1.9%**, abaixo do mínimo aceitável.

O custo direto representa 57.2% do custo total, enquanto os custos indiretos correspondem a 23.9% (razão indireto/direto de 0.42).

---

## Resultado Financeiro

| Indicador | Valor |
|-----------|-------|
| Preço de venda (c/ BDI) | R$ 80,358,255.08 |
| Custo direto | R$ 46,843,791.49 |
| Custo indireto | R$ 19,584,539.27 |
| **Custo total** | **R$ 81,861,526.77** |
| **Resultado bruto** | **R$ -1,503,271.69** |

---

## Planejamento por EAP

| Item | Descricao | c/BDI (R$) |
|------|-----------|-----------:|
| eap-1_0 | Desmatamento e limpeza de area vegetada | R$ 2,477,673.16 |
| eap-1_1 | Esc/carg/transp 1aCat DMT<=2000m | R$ 992,406.46 |
| eap-1_2 | Esc/carg/transp 1aCat DMT<=3000m | R$ 3,441,418.84 |
| eap-1_3 | Esc/carg/transp 2aCat DMT<=2000m | R$ 1,280,091.96 |
| eap-1_4 | Esc/carg/transp 2aCat DMT<=3000m | R$ 7,597,204.52 |
| eap-1_5 | Esc/carg/transp 3aCat DMT<=2000m | R$ 5,452,981.76 |
| eap-1_6 | Esc/carg/transp 3aCat DMT<=3000m | R$ 14,870,246.89 |
| eap-1_7 | Compactacao aterros 100% Proctor Normal | R$ 12,156,798.29 |
| eap-1_8 | Compactacao aterros 100% Proctor Intermediario | R$ 411,657.26 |
| eap-1_9 | Construcao corpo aterro material 3a categoria | R$ 6,741,771.10 |
| eap-1_10 | Compactacao camada final aterro sobre rocha | R$ 415,123.69 |

---

## Ponto de Equilibrio

> **Como interpretar ERRO por item sem distorcer o saldo global do projeto?**
>
> O campo `Operacional (R$)` deve refletir **custo alocado por item**, nao o custo bruto do pool inteiro. Em pool compartilhado, a base coerente e a permanencia efetiva da instancia (team-weeks / team-months) e o custo operacional correspondente de cada equipamento/equipe no periodo.
>
> Essa abordagem evita dupla contagem entre atividades atendidas pelo mesmo pool e mantem consistencia entre PE por item e consolidacao financeira do contrato.
>
> **Em resumo:** quando o custo operacional e particionado pela permanencia/capacidade efetiva, o diagnostico por item fica financeiramente honesto e o saldo final volta a representar a alocacao enxuta do resource pool sem inflacao artificial de custo.
>
> **Parametros operacionais de calibracao:** produtividade de CPU, numero maximo de equipes por atividade e perfis de permanencia/ramp-up. **Fatores exogenos:** praticabilidade (clima/terreno) devem ficar explicitos no diagnostico.

| Item | Venda (R$) | Operacional (R$) | Margem Op. Direta | Margem Total Atribuida | Gap Produtivo (R$) | Gap Mob/Demob (R$) | Gap Ociosidade (R$) | Status |
|------|-----------:|-----------------:|-------------------:|------------------------:|-------------------:|--------------------:|---------------------:|--------|
| eap-1_0 | 2,477,673.16 | 2,943,567.46 | -18.80% | 17.33% | 456,587.48 | 9,306.82 | 0.00 | ERRO |
| eap-1_1 | 992,406.46 | 1,262,058.60 | -27.17% | 17.33% | 257,414.33 | 12,237.81 | 0.00 | ERRO |
| eap-1_2 | 3,441,418.84 | 3,912,391.00 | -13.69% | 17.33% | 463,858.47 | 7,113.69 | 0.00 | ERRO |
| eap-1_3 | 1,280,091.96 | 1,558,235.66 | -21.73% | 17.33% | 262,955.98 | 15,187.72 | 0.00 | ERRO |
| eap-1_4 | 7,597,204.52 | 8,681,592.84 | -14.27% | 17.33% | 1,073,262.07 | 11,126.25 | 0.00 | ERRO |
| eap-1_5 | 5,452,981.76 | 5,435,197.46 | 0.33% | 17.33% | 0.00 | 0.00 | 0.00 | ERRO |
| eap-1_6 | 14,870,246.89 | 12,319,790.68 | 17.15% | 17.33% | 0.00 | 0.00 | 0.00 | ERRO |
| eap-1_7 | 12,156,798.29 | 13,689,045.92 | -12.60% | 17.33% | 1,521,099.69 | 11,147.94 | 0.00 | ERRO |
| eap-1_8 | 411,657.26 | 293,333.47 | 28.74% | 17.33% | 0.00 | 0.00 | 0.00 | OK |
| eap-1_9 | 6,741,771.10 | 11,595,107.47 | -71.99% | 17.33% | 4,754,917.19 | 98,419.18 | 0.00 | ERRO |
| eap-1_10 | 415,123.69 | 586,666.94 | -41.32% | 17.33% | 146,492.08 | 25,051.17 | 0.00 | ERRO |

### Reconciliacao Itens -> Resultado Global

| Indicador | Soma Itens (R$) | Global (R$) | Delta (R$) |
|-----------|----------------:|------------:|-----------:|
| Receita | 55,837,373.93 | 80,358,255.08 | -24,520,881.15 |
| Custo Operacional / Total | 62,276,987.50 | 81,861,526.77 | -19,584,539.27 |
| Resultado | 13,929,924.31 | -1,503,271.69 | 15,433,196.00 |

> Observacao: `Margem Total Atribuida` e reconciliada por rateio de receita e custos globais (direto + indireto) com base na participacao de venda de cada item.
> Decomposicao do gap (itens deficitarios): produtivo=8,936,587.29, mob/demob=189,590.58, ociosidade=0.00.

---

## Insights Acionaveis

- **criticidade**: None
- **sensibilidade**: None
- **intervencao**: None

---

## Graficos Gerados

### area_tempo_componente.png
![area_tempo_componente.png](area_tempo_componente.png)

### bar_atividade_componente.png
![bar_atividade_componente.png](bar_atividade_componente.png)

### bar_categoria_componente.png
![bar_categoria_componente.png](bar_categoria_componente.png)

### bar_diesel_temporal.png
![bar_diesel_temporal.png](bar_diesel_temporal.png)

### bar_tempo_natureza.png
![bar_tempo_natureza.png](bar_tempo_natureza.png)

### dependencia_eap.png
![dependencia_eap.png](dependencia_eap.png)

### fluxo_financeiro.png
![fluxo_financeiro.png](fluxo_financeiro.png)

### gantt_cronograma.png
![gantt_cronograma.png](gantt_cronograma.png)

### hist_equipamentos.png
![hist_equipamentos.png](hist_equipamentos.png)

### hist_mao_obra.png
![hist_mao_obra.png](hist_mao_obra.png)

### linha_recursos_tempo.png
![linha_recursos_tempo.png](linha_recursos_tempo.png)

### painel_equilibrio.png
![painel_equilibrio.png](painel_equilibrio.png)

### pool_ciclo_vida.png
![pool_ciclo_vida.png](pool_ciclo_vida.png)

### pool_custo_estado.png
![pool_custo_estado.png](pool_custo_estado.png)

### pool_economia.png
![pool_economia.png](pool_economia.png)

### pool_utilizacao_temporal.png
![pool_utilizacao_temporal.png](pool_utilizacao_temporal.png)

### scurve_custo.png
![scurve_custo.png](scurve_custo.png)
