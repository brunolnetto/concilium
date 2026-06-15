# Metodologia de Sweep de Campanha — Exploração Paramétrica do Espaço de Configuração

**Projeto:** Concilium — MendesLobo Construtora  
**Audiência:** Engenheiros de Planejamento, Orçamento e CEO  
**Versão:** 1.0 — 2026-06-12  
**Referências:** ADR-070, ADR-109, NEP-042

---

## 1. O que é uma Campanha

Uma **campanha** é a execução sistematizada de múltiplos cenários de um mesmo projeto, cada um com uma combinação diferente de parâmetros de planejamento. O objetivo é mapear como os resultados financeiros e operacionais se comportam diante de decisões como:

- Mais ou menos frentes de serviço por atividade?
- Regime de 8h ou 10h/dia?
- Pool de equipamentos dimensionado para prazo mínimo ou custo mínimo?
- DMT 2.000m ou DMT 3.000m para movimentação de terra?

Em vez de o engenheiro testar cada combinação manualmente — refazendo cronograma, pool e orçamento a cada rodada —, a campanha faz isso de forma exaustiva e sistemática, produzindo ao final uma **shortlist curada** dos cenários que melhor equilibram prazo e margem.

---

## 2. Setup Base e Espaço de Variação

### 2.1 Setup base

O **setup base** é a configuração de partida: o `referencia.json` do projeto, que contém EAP, cronograma, BDI, indiretos, localização e regime de trabalho. É o "cenário zero" — o projeto como está proposto.

Todo cenário da campanha é derivado do setup base com um ou mais parâmetros modificados. O que não está no sweep permanece exatamente como no setup base.

### 2.2 Alavancas de variação (levers)

As alavancas são os parâmetros que a campanha varia. Estão organizadas em cinco classes por risco e tipo de impacto:

| Classe | O que varia | Risco | Impacto |
|---|---|---|---|
| **1 — Frota** | Número de frentes (`n_max`, `n_inicial`), janela de mob/demob | Baixo | Prazo e custo de mobilização |
| **2 — Produtividade** | Regime de trabalho (horas/dia), produtividade por atividade | Médio | Prazo e custo direto |
| **3 — Pool** | Objetivo de dimensionamento, restrições de mercado | Baixo | Prazo e tamanho do contrato |
| **4 — CPU alternativo** | Composição da equipe por atividade (método construtivo) | Médio | Produtividade, PU de catálogo e custo |
| **5 — Financeiro** | BDI, regime tributário | Alto | Não sweepear — decisão de negócio |

### 2.3 Escopos de variação

Cada alavanca tem um **escopo** que determina como o parâmetro é aplicado aos itens da EAP:

| Escopo | Comportamento | Cardinalidade |
|---|---|---|
| `global` | O mesmo valor é aplicado a todos os itens simultaneamente | `k` (número de valores) |
| `per_item` | Cada item varia **independentemente** — todas as combinações entre itens são testadas | `k^n` (k valores elevado a n itens) |
| `cpu_alternativo` | Igual a `per_item`, mas substitui o `cpu_id` da atividade no catálogo | `k^n` |

**Exemplo concreto (escopo per_item):**  
Três atividades de terraplenagem, cada uma podendo operar com 75%, 100% ou 125% das frentes nominais → `3^3 = 27 combinações` só para essa alavanca.

---

## 3. Cardinalidade — Tamanho do Espaço

A cardinalidade é o número total de cenários que a campanha avalia:

```
|espaço| = Π kᵢ   para cada dimensão i

Para scope "global":           kᵢ = len(valores_i)
Para scope "per_item" ou "cpu_alternativo":  kᵢ = len(valores_i)^len(item_ids_i)
```

**Exemplo — AGIS Campanha v1:**

| Alavanca | Escopo | Valores | Itens | Contribuição |
|---|---|---|---|---|
| Regime de trabalho (horas_dia) | global | 2 | — | 2 |
| n_max (frentes máx.) | global | 3 (×0,75 / ×1,0 / ×1,25) | — | 3 |
| n_inicial (ramp-up) | global | 2 (×0,5 / ×1,0) | — | 2 |
| Restrições de mercado | global | 3 (sem / 1 tipo / 2 tipos) | — | 3 |
| **Total** | | | | **2 × 3 × 2 × 3 = 36** |

### 3.1 Fronteira de tratabilidade

```
≤ 10.000 cenários  →  busca exaustiva (todos os cenários são avaliados)
> 10.000 cenários  →  requer busca guiada (Latin Hypercube, Pareto progressivo, etc.)
```

Com 6 workers e ~60s por cenário, 10.000 cenários levam aproximadamente 28 horas. Acima disso, o engenheiro deve reduzir o número de alavancas ou restringir os ranges.

---

## 4. Estrutura de um Cenário

Cada cenário da campanha é descrito por:

```
cenario_id     →  hash determinístico dos parâmetros variados
parametros_variados  →  dict com o que mudou em relação ao setup base
                         ex: {"meta.regime_trabalho": {"horas_dia": 10}, 
                              "n_max": {"__scale__": 1.25}}
```

Os parâmetros são aplicados ao setup base antes de cada avaliação. A avaliação executa o **pipeline completo** — cronograma RCPSP, formação de pool, custo operacional, indiretos e resultado financeiro — exatamente como em uma execução normal do projeto.

### 4.1 Sintaxes de override

| Sintaxe | Significado | Exemplo |
|---|---|---|
| Valor direto | Substitui o campo pelo valor | `{"horas_dia": 10}` |
| `{"__scale__": k}` | Multiplica o valor existente por `k` | `n_max × 1.25` |
| `{"__add__": δ}` | Soma `δ` ao valor existente | `n_inicial + 1` |
| Wildcard `[*]` | Aplica a todos os itens da lista | `activities.[*].n_max` |

---

## 5. O Grid de Cenários

O grid é o produto cartesiano de todas as dimensões do sweep:

```
grid = {(v₁, v₂, ..., vₘ) : vᵢ ∈ valores_i}
```

Para um sweep com dimensões `A = {a₁, a₂}` e `B = {b₁, b₂, b₃}`, o grid tem 6 cenários:

```
(a₁, b₁), (a₁, b₂), (a₁, b₃)
(a₂, b₁), (a₂, b₂), (a₂, b₃)
```

Cada ponto do grid é um cenário completo, avaliado independentemente pela pipeline.

---

## 6. Execução da Campanha

### 6.1 Fluxo de execução

```
1. Carregar setup base (referencia.json)
2. Calcular cardinality() — alertar se > 10.000
3. Gerar grid de (36 / N) cenários
4. Para cada cenário (em paralelo, N workers):
    a. Aplicar overrides sobre cópia do setup base
    b. Executar pipeline completa (skills 01–08)
    c. Extrair vetores O e EF do canonical resultante
    d. Classificar O (IDEAL / ATENÇÃO / CRÍTICO)
    e. Classificar EF (DENTRO / ATENÇÃO / FORA da expectativa)
    f. Registrar viabilidade (APROVADO / REPROVADO)
5. Calcular fronteiras de Pareto em O e EF
6. Curar shortlist (top-k cenários recomendados)
7. Construir cubo analítico
8. Persistir: bundle.json, cube.json, report.md, report.pdf
```

### 6.2 Paralelismo

Os cenários são avaliados em paralelo por múltiplos workers. O número de workers é configurável (`CONCILIUM__CAMPAIGN_WORKERS`). Cada worker é independente — não há estado compartilhado entre avaliações.

---

## 7. Perfil de Expectativas

O perfil define os critérios contra os quais cada cenário é avaliado:

| Parâmetro | Default | Descrição |
|---|---|---|
| `meta_margem_pct` | 10% | Margem bruta mínima esperada |
| `tolerancia_margem` | 3 p.p. | Faixa de atenção abaixo da meta |
| `prazo_contratual_semanas` | derivado das datas | Prazo máximo do contrato |

O perfil é constante para toda a campanha — o que varia é o cenário, não o critério de avaliação.

---

## 8. Configuração da Campanha v1 — AGIS (Exemplo)

```json
{
  "campaign_version": "v1",
  "descricao": "Exploração Classe 1+2+3 — AGIS Ferrovia Transnordestina",
  "perfil_expectativas": {
    "meta_margem_pct": 0.10,
    "tolerancia_margem": 0.03,
    "prazo_contratual_semanas": 56
  },
  "sweep": [
    {
      "campo": "meta.regime_trabalho",
      "valores": [{"horas_dia": 8, "dias_semana": 6},
                  {"horas_dia": 10, "dias_semana": 6}]
    },
    {
      "campo": "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_max",
      "valores": [{"__scale__": 0.75}, {"__scale__": 1.0}, {"__scale__": 1.25}]
    },
    {
      "campo": "inputs_cronograma.rcpsp_spec.activities.[*].ramp_params.n_inicial",
      "valores": [{"__scale__": 0.5}, {"__scale__": 1.0}]
    },
    {
      "campo": "restricoes_mercado",
      "scope": "global",
      "valores": [
        {},
        {"EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 2},
        {"EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT2000": 2,
         "EQUIPE-CPU-TERRA-ESCO-CARGA-3CAT-DMT3000": 2}
      ]
    }
  ],
  "top_k": 5
}
```

**Leitura do sweep:**
- 2 regimes de trabalho × 3 níveis de frota × 2 ramp-ups × 3 restrições de mercado = **36 cenários**
- O parâmetro `restricoes_mercado` com valor `{}` corresponde ao "sem restrição" (setup base)
- O valor `{"__scale__": 0.75}` reduz as frentes máximas para 75% do nominal de catálogo

---

## 9. Limitações do Sweep Exaustivo

O sweep exaustivo garante cobertura completa do espaço definido, mas não otimiza — ele avalia todos os pontos igualmente, sem aprender com os resultados anteriores. Para espaços grandes (> 10.000 cenários), alternativas a considerar:

| Estratégia | Quando usar |
|---|---|
| Reduzir ranges | Quando há conhecimento prévio de qual região é promissora |
| Fixar alavancas menos sensíveis | Após análise marginal de uma campanha menor |
| Busca guiada (Latin Hypercube) | Quando o espaço é muito grande mas a região de interesse é desconhecida |
| Campanha sequencial (v1 → v2) | Usar resultados da v1 para refinar o sweep da v2 |
