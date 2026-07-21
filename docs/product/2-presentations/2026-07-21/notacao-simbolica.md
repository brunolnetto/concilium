# Notação Simbólica — Concilium (deck 2026-07-17)

Catálogo canônico dos símbolos matemáticos usados na apresentação e sua ponte com os
campos do código. Regra editorial do deck: **nome de campo** em `\texttt{...}` (underscore
escapado: `\texttt{capacidade\_armazenamento}`); **variável em equação** usa o símbolo
desta tabela, com o campo citado na legenda do bloco.

## Catálogo · Produção · Preço

| Símbolo | Significado | Campo / fonte no código |
|---|---|---|
| $\rho_i$ | produtividade horária da CPU $i$ [un/h] | `Producao.valor_horario` |
| $\rho^{\text{sin}}$ | produtividade derivada pelo grafo de sinergia: $\min_e k_e n_e$ | `derivar_producao_horaria` (ADR-130) |
| $k_e$ | capacidade horária do elemento $e$ da equipe | `CapacidadeElemento.capacidade_horaria` |
| $\gamma_i$, $\gamma_r$ | custo horário da equipe $i$ / do recurso $r$; sobrescritos $^{mo},^{eq}$ decompõem | motor bottom-up (`derivar_precos_unitarios_sbdi`) |
| $n_r$ | quantidade do recurso $r$ na equipe | `num_pessoas` / `num_unidades` |
| $f_e$ | consumo de diesel do equipamento $e$ [L/h] | `consumo_litros_hora` |
| $c_{\text{dsl}}$ | preço do litro de diesel (API ANP por UF; offline → R\$ 6,50/l) | `resolver_preco_diesel_uf` (ADR-129) |
| $e_i = (R^{MO}_i, R^{EQ}_i, R^{MAT}_i)$ | composição-padrão da equipe | `composicao_padrao_equipe` |
| $p_i^c = \gamma_i/\rho_i$ | preço unitário de catálogo | `precos_unitarios_sbdi.total` |
| $p_i^o$ | preço unitário operacional | skill-06 |
| $\tau_i$ | razão operacional/catálogo — efeito líquido: eficiência empurra $>1$, partilha de pool empurra $<1$ (NEP-043: $C_{\text{inst}} \leq$ catálogo) | reconciliação (NEP-043) |
| $Q_i$ | quantitativo total da atividade | `EapItem.quantitativo` |

## Cronograma (RCPSP)

| Símbolo | Significado | Campo / fonte |
|---|---|---|
| $\theta_i \in [0,1]$ | completion threshold da precedência (fração da duração) | `ActivityDAG.thresholds` (ADR-081) |
| $S_r(t)$ | slots do tipo $r$ disponíveis no pool na semana $t$ | pool perpétuo (ADR-073) |
| $m_{ij}$ | alocação de equipes da atividade $i$ no mês $j$ | cronograma mensal |
| $h_j$, $h$ | horas úteis no mês $j$ / na semana | calendário operacional (ADR-068) |
| $\lambda_j$ | eficiência de clima (praticabilidade) do mês $j$ | ADR-124 |
| $d_j$ | dias produtivos da semana $j$ (quantidade física, calendário local) | calendário operacional (ADR-068) |
| $\delta_j$, $\delta$ | eficiência de dias produtivos (calendário) --- conceito agregado, distinto de $d_j$ | ADR-068 |
| $q_{ij} = m_{ij}\,\rho_i\,\lambda_j\,d_j\,h_j$ | quantidade executada de $i$ no mês $j$ ($\rho_i$: produtividade de catálogo; $d_j$ físico, não $\delta_j$; rampa embutida em $m_{ij}$) | distribuição física |
| $\eta_{\text{plan},j} = \lambda_j\cdot\delta_j$ | eficiência de planejamento --- métrica agregada (skill-06), não entra na distribuição física $q_{ij}$ | ADR-124 |

## Estoque de consumíveis (ADR-128/139)

| Símbolo | Significado | Campo / fonte |
|---|---|---|
| $E_t$, $E_0$ | estoque projetado na semana $t$; estoque inicial | `project_estoque_semanal`; `estoque_inicial` |
| $K$ | capacidade de armazenamento (tanque/pilha) | `capacidade_armazenamento` |
| $a_{\max}$ | taxa máxima de abastecimento **externo** (fornecedor/comboio) | `taxa_reabastecimento_max` |
| $g_t$ | geração **interna** na semana $t$ (produtor-consumidor) | `producao_por_semana` (ADR-139) |
| $u_t$ | consumo na semana $t$ | `consumo_por_semana` |
| — | balanço: $E_t = \min(E_{t-1} + a_{\max} + g_t,\; K) - u_t$ | `replenishable.py` |

## Ciclo de vida de equipes · Pool · Venda

| Símbolo | Significado | Campo / fonte |
|---|---|---|
| $c_{\text{mob}}$, $c_{\text{dem}}$ | custo de mobilização / desmobilização | ADR-136/137 |
| $\kappa \leq 1$ | fator de custo de equipamento em standby | ADR-080 |
| $n_p$, $n_s$ | semanas produtivas / de standby | lifecycle engine (ADR-136) |
| $C_{\text{prod},i} \leq C_{\text{pool},i} \leq \tilde{C}_i$ | custo produtivo ⊂ pool ⊂ total | skill-05/06 |
| $\tilde{C}^D$, $\tilde{C}^I$ | custo direto / indireto | skill-05/06 |
| $V$, $V_i^I = \sum_j\sum_{q\in B_i}\beta_q\gamma_q h\,d$ | valor de venda; venda de indiretos | BDI (ADR-057) |
| $\beta_q$, $B_i$ | fator BDI do componente $q$; cesta de componentes | ADR-023/057 |
| $T$ | tributos brutos no denominador do BDI (PIS+COFINS+ISS+CSLL+IR, regime atual) | `ComponentesBdi` (ADR-023) |
| $T_{\text{efetivo}}$ | tributos líquidos pós-crédito no regime CBS/IBS: $(\text{CBS+IBS})(1-\text{crédito}) + CSLL + IR$ | `ComponentesTributarios`/`TaxSimulationScenario` (ADR-055) |

## Colisões resolvidas nesta revisão

1. **$\tau$ sobrecarregado**: era `taxa_reabastecimento_max` ($\tau_{\max}$) *e* razão
   operacional/catálogo ($\tau_i$). Resolução: reabastecimento externo vira **$a_{\max}$**
   (abastecimento); $\tau_i$ mantém a razão (uso mais antigo no deck).
2. **$c_t$ ambíguo**: consumo (quantidade/semana) colidia com a família de custos
   $c_{\text{mob}}/c_{\text{eq}}$ (R$). Resolução: consumo vira **$u_t$** (uso). $q$ não
   serve: $q_{ij}$ já é quantidade executada.
3. **Convenção geral**: $c_\ast$ = custos unitários (R$); letras de fluxo semanal
   ($a, g, u$) = quantidades físicas; maiúsculas ($E, K, Q, C, V$) = estados/agregados.
