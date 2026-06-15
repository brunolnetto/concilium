# Metodologia de Análise de Campanha — Interpretação de Resultados

**Projeto:** Concilium — MendesLobo Construtora  
**Audiência:** Engenheiros de Planejamento, Orçamento e CEO  
**Versão:** 1.0 — 2026-06-12  
**Referências:** ADR-070, ADR-109, ADR-108

---

## 1. Dois Espaços de Avaliação

Cada cenário avaliado é caracterizado por métricas em **dois espaços distintos**:

```
Espaço O  (Operacional)   →  como o projeto se executa
Espaço EF (Econômico-Financeiro)  →  como o projeto remunera
```

A separação é intencional: um cenário pode ser operacionalmente excelente (termina no prazo, frentes bem utilizadas) mas financeiramente insatisfatório (margem abaixo da meta), ou vice-versa. A análise trabalha os dois espaços em conjunto.

---

## 2. Espaço O — Dimensões Operacionais

O espaço O mede a **viabilidade e eficiência de execução** do cronograma e do pool.

### 2.1 Métricas do vetor O

| Métrica | Definição | Direção |
|---|---|---|
| `prazo_semanas` | Makespan do cronograma RCPSP (semanas totais) | Minimizar |
| `folga_semanas` | `prazo_contratual − prazo` (positivo = dentro do prazo) | Maximizar |
| `fe_nec_medio` | Frentes equivalentes necessárias, médio por atividade | Minimizar |
| `itens_criticos_pct` | Fração de atividades com `fe_nec > 1,25` (sobrecarregadas) | Minimizar |
| `gap_pool_total` | Overhead de custo por sub-aproveitamento do pool | Minimizar |
| `custo_mob_window_total` | Custo total de mobilização/desmobilização | Minimizar |
| `utilizacao_recursos_pct` | Semanas produtivas / semanas mobilizadas | Maximizar |
| `paralelismo_medio` | Atividades ativas simultaneamente (média semanal) | Informativo |
| `idle_pool_pct` | Proporção de semanas com pool ocioso | Minimizar |

### 2.2 Frentes Equivalentes Necessárias (`fe_nec`)

O `fe_nec` é o indicador central do espaço O. Ele mede **quantas frentes seriam necessárias** para executar a quantidade de serviço dentro do prazo, comparado às frentes que o cronograma alocou:

```
fe_nec_i = Q_i / (P_i × h_sem × eMW_i_disponível)

fe_nec = 1,0  →  atividade bem calibrada (frentes certas para o prazo)
fe_nec < 1,0  →  folga operacional (frentes em excesso ou prazo folgado)
fe_nec > 1,0  →  pressão operacional (faltam frentes para o prazo)
fe_nec > 1,25 →  item crítico (>25% de sobrecarga — gatilho de alerta)
```

O `fe_nec_medio` é a média ponderada por item, e o `itens_criticos_pct` é a fração de itens acima de 1,25.

### 2.3 Classificação do espaço O

| Classificação | Critério |
|---|---|
| **IDEAL** | `folga ≥ 0` E `fe_nec ≤ 1,0` E `itens_críticos = 0%` |
| **ATENÇÃO** | Alguma dimensão fora do ideal mas sem criticidade: `−2 ≤ folga < 0` OU `1,0 < fe_nec ≤ 1,25` OU `0% < itens_críticos ≤ 20%` |
| **CRÍTICO** | `folga < −2` OU `fe_nec > 1,25` OU `itens_críticos > 20%` |

Regra de propagação: se **qualquer** dimensão é CRÍTICO → cenário é CRÍTICO no espaço O.

---

## 3. Espaço EF — Dimensões Econômico-Financeiras

O espaço EF mede a **rentabilidade e aderência aos objetivos de negócio** do cenário.

### 3.1 Métricas do vetor EF

| Métrica | Definição | Direção |
|---|---|---|
| `margem_pct` | Lucro bruto / venda total (com BDI) | Maximizar |
| `custo_execucao_pool` | Custo operacional real das equipes (N3) | Minimizar |
| `custo_indireto` | Soma dos custos indiretos (ADM, TOP, LAB, QSMS, MOB) | Minimizar |
| `preco_venda` | Venda total com BDI | Informativo |
| `ratio_pool_vs_cat` | `custo_pool / PU_cat × Q` — eficiência vs. catálogo | Minimizar |
| `fidelidade_gates` | Todos os quality gates da pipeline aprovados? | Maximizar (booleano) |
| `share_mo_pct` | Participação de MO no custo direto total | Informativo |
| `share_eq_pct` | Participação de equipamentos no custo direto | Informativo |
| `share_comb_pct` | Participação de combustível no custo direto | Informativo |
| `concentracao_atividade` | Índice HHI de concentração de custo por atividade | Minimizar |

### 3.2 Ratio pool vs. catálogo

O `ratio_pool_vs_cat` é a relação entre o custo real de pool (N3) e o valor de catálogo puro (N1):

```
ratio = custo_pool (N3) / (PU_cat × Q) (N1)

ratio < 1,0  →  pool economiza vs. catálogo (esperado em obras de médio-grande porte)
ratio = 1,0  →  pool custa exatamente como catálogo
ratio > 1,0  →  pool é mais caro que catálogo (sinal de superdimensionamento ou baixa eficiência)
```

Valores acima de 1,10 são tratados como ATENÇÃO; acima de 1,10 como FORA_EXPECTATIVA.

### 3.3 Concentração de custo (HHI)

O Índice Herfindahl-Hirschman adaptado mede o quanto o custo do projeto está concentrado em poucas atividades:

```
HHI = Σᵢ (custo_i / custo_total)²

HHI = 1/N  →  custo uniformemente distribuído entre N atividades
HHI = 1,0  →  todo o custo em 1 atividade
```

Alta concentração (HHI próximo de 1) indica dependência de poucas atividades — risco operacional relevante.

### 3.4 Classificação do espaço EF

Com perfil padrão (`meta_margem = 10%`, `tolerância = 3 p.p.`):

| Classificação | Critério |
|---|---|
| **DENTRO_EXPECTATIVA** | `margem ≥ 10%` E `ratio_pool ≤ 1,0` E `fidelidade = True` |
| **ATENÇÃO** | `7% ≤ margem < 10%` OU `1,0 < ratio ≤ 1,10` |
| **FORA_EXPECTATIVA** | `margem < 7%` OU `ratio > 1,10` OU `fidelidade = False` |

O perfil é parametrizável por campanha — projetos com expectativa diferente usam metas diferentes.

---

## 4. Fronteiras de Pareto

A fronteira de Pareto identifica os cenários que não podem ser melhorados em nenhuma dimensão sem piorar outra. Um cenário `A` **domina** o cenário `B` quando:

```
Em O-space (minimização de prazo, fe_nec e gap_pool):
    A domina B ↔ A é ≤ B em todas as três dimensões
                 E  A é < B em pelo menos uma

Em EF-space (maximização de margem, minimização de custo indireto):
    A domina B ↔ A tem margem ≥ B
                 E  A tem custo_indireto ≤ B
                 E  A é estritamente melhor em pelo menos uma
```

Os cenários não dominados formam a **fronteira de Pareto** de cada espaço. Eles representam os melhores trade-offs disponíveis no espaço amostrado.

### 4.1 Interpretação das fronteiras

```
Pareto O        →  cenários com melhor desempenho operacional
Pareto EF       →  cenários com melhor desempenho financeiro
Pareto interseção →  cenários bons nos dois espaços simultaneamente
```

A **interseção** é o conjunto mais valioso: cenários que nenhum outro consegue superar nem em prazo/eficiência nem em margem/custo.

---

## 5. Shortlist — Cenários Recomendados

A shortlist contém os `top_k` cenários recomendados para análise pelo engenheiro. A curadoria segue esta hierarquia:

### 5.1 Seleção de pool

```
1. Se existe interseção Pareto O ∩ EF  →  usar apenas cenários da interseção
2. Se não há interseção                →  usar cenários do Pareto EF
                                          (ou todos os viáveis se nenhum está em Pareto EF)
```

### 5.2 Ordenação dentro do pool

```
1. Classificação O = IDEAL vem antes de ATENÇÃO e CRÍTICO
2. Classificação EF = DENTRO_EXPECTATIVA vem antes de ATENÇÃO e FORA
3. Maior margem_pct
4. Menor prazo_semanas
5. Menor fe_nec_medio
6. cenario_id (desempate determinístico)
```

### 5.3 Motivo de inclusão

Cada cenário da shortlist traz o **motivo de inclusão**:

| Motivo | Significado |
|---|---|
| `pareto_intersecao` | Melhor dos dois mundos — nenhum outro é melhor em O e EF simultaneamente |
| `pareto_EF` | Melhor financeiro disponível — não está na interseção mas lidera o espaço EF |
| `melhor_viavel` | Nenhum cenário chegou ao Pareto — é o melhor entre os viáveis |

### 5.4 Status do bundle

O status da campanha como um todo sintetiza o que foi encontrado:

| Status | Condição | Interpretação |
|---|---|---|
| **SUCESSO** | ≥ 1 cenário em Pareto interseção | Existem configurações que dominam nos dois espaços |
| **SUCESSO_PARCIAL** | Viáveis existem, mas sem interseção | Há trade-off obrigatório entre prazo e margem |
| **FRONTEIRA_ÚNICA** | Pareto O e EF separados, sem interseção | O espaço está polarizado — ganhar em um custa no outro |
| **INFEASIBLE** | Nenhum cenário viável | Todas as configurações testadas violam os gates de viabilidade |
| **ABORTADO** | Todas as avaliações falharam com erro | Problema de dados ou configuração |

---

## 6. Cubo Analítico — Análise Multidimensional

O cubo organiza os resultados de forma que cada combinação de valores dos levers corresponde a uma célula com as métricas dos espaços O e EF.

### 6.1 Estrutura

```
Dimensões  →  os levers do sweep (ex: regime_trabalho, n_max, n_inicial)
Células    →  cada combinação de valores dos levers
Faces      →  projeções 2D: para cada par de dimensões, uma grade com uma métrica
Resumos marginais  →  para cada dimensão, a média de cada métrica por valor
```

### 6.2 Faces do cubo

Uma **face** é uma projeção 2D que mostra como uma métrica varia ao cruzar duas dimensões. Por exemplo:

```
Face: regime_trabalho × n_max, métrica: prazo_semanas

              n_max=0,75  n_max=1,0  n_max=1,25
  8h/dia          34          28          24
  10h/dia         28          22          18
```

Cada face permite visualizar interações entre levers: o regime de trabalho mais intenso (10h) e mais frentes (×1,25) juntos levam ao prazo mais curto (18 semanas).

Métricas disponíveis no cubo:

| Espaço | Métricas |
|---|---|
| O | prazo_semanas, fe_nec_medio, itens_criticos_pct, gap_pool_total, utilizacao_recursos_pct, paralelismo_medio |
| EF | margem_pct, ratio_pool_vs_cat, custo_indireto, share_mo_pct, share_eq_pct, share_comb_pct, concentracao_atividade |

### 6.3 Resumos marginais e tendência

Para cada lever e cada métrica, o cubo calcula a **média da métrica para cada valor do lever**, mantendo todos os outros fixos em média. Isso permite identificar o efeito **marginal** de cada parâmetro:

```
Tendências possíveis:
  crescente       →  métrica melhora à medida que o valor do lever aumenta
  decrescente     →  métrica piora à medida que o lever aumenta
  não_monotona    →  existe um ponto ótimo intermediário (côncavo ou convexo)
  indeterminado   →  dados insuficientes ou relação irregular
```

**Exemplo de leitura:**  
Se o resumo marginal de `n_max` sobre `prazo_semanas` é **decrescente**, significa que aumentar as frentes reduz o prazo consistentemente em todos os cenários testados. Se a tendência é **não_monotona**, existe um ponto de saturação — acima de certo n_max, adicionar frentes não reduz mais o prazo (e aumenta custo desnecessariamente).

---

## 7. Leitura Integrada dos Resultados

### 7.1 Fluxo de interpretação recomendado

```
1. Status do bundle
   ├── SUCESSO         →  focar nos cenários da interseção Pareto
   ├── FRONTEIRA_ÚNICA →  decidir: priorizar prazo ou margem?
   └── INFEASIBLE      →  revisar setup base (BDI, indiretos, EAP)

2. Shortlist (top-k)
   ├── Ler motivo de inclusão de cada cenário
   ├── Comparar destaques O e destaques EF
   └── Identificar alertas (fe_nec alto, idle elevado, ratio > 1)

3. Análise marginal (resumos do cubo)
   ├── Qual lever tem maior impacto em prazo? → priorizar na negociação
   ├── Qual lever tem maior impacto em margem? → cuidado na proposta
   └── Há levers com tendência não_monotona? → existe ponto ótimo a precisar

4. Faces do cubo
   └── Verificar interações entre os 2 levers mais sensíveis
```

### 7.2 Quadro de leitura rápida

| Indicador | Verde | Amarelo | Vermelho |
|---|---|---|---|
| `folga_semanas` | ≥ 0 | −2 a 0 | < −2 |
| `fe_nec_medio` | ≤ 1,0 | 1,0–1,25 | > 1,25 |
| `itens_criticos_pct` | 0% | ≤ 20% | > 20% |
| `margem_pct` | ≥ 10% | 7–10% | < 7% |
| `ratio_pool_vs_cat` | ≤ 1,0 | 1,0–1,10 | > 1,10 |
| `fidelidade_gates` | True | — | False |
| `concentracao_atividade` (HHI) | < 0,25 | 0,25–0,50 | > 0,50 |

---

## 8. Exemplo — AGIS Campanha v1 (36 cenários)

**Resultado obtido:**

| Métrica | Valor |
|---|---|
| Status do bundle | **SUCESSO** |
| Cenários avaliados | 12/12 (100%) — *versão anterior da campanha* |
| Cenários viáveis | 12/12 (100% APROVADO) |
| Cenários em Pareto interseção | ≥ 1 |

**Shortlist rank #1:**

| Espaço O | Valor | Classificação |
|---|---|---|
| Prazo | 25 semanas (folga: +31) | IDEAL |
| fe_nec_medio | 0,652 | IDEAL |
| Itens críticos | 0% | IDEAL |

| Espaço EF | Valor | Classificação |
|---|---|---|
| Margem | 12,48% | DENTRO_EXPECTATIVA |
| Custo pool | R$ 29,4M | — |
| ratio_pool_vs_cat | < 1,0 | DENTRO_EXPECTATIVA |
| fidelidade_gates | True | DENTRO_EXPECTATIVA |

**Parâmetros do cenário vencedor:**
- Regime: 10h/dia × 6d/semana
- n_max: ×1,25 (25% mais frentes que o nominal)
- n_inicial: ×0,5 (ramp-up mais suave — metade das frentes na mobilização)
- Restrições de mercado: nenhuma

**Leitura:** Aumentar o regime de trabalho para 10h e ampliar as frentes máximas em 25% reduz o prazo para apenas 25 semanas (vs. 56 contratadas), com margem 2,48 p.p. acima da meta. O ramp-up mais suave (×0,5 frentes iniciais) reduz o custo de mobilização sem comprometer o prazo — a folga de 31 semanas absorve o atraso inicial.
