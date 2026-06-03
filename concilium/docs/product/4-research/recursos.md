# Estrutura de Custo de Equipe e Compartilhamento de Recursos

**Documento:** Análise Estrutural — Pré-condição do ADR-75
**Data:** 2026-05-25
**Contexto:** MendesLobo Construtora — Concilium

---

## 1. Equipe como Bundle Contratado

### 1.1 Definição formal

O formalismo base representa a composição de recursos de uma atividade como um vetor
plano `e_i ∈ Z_{≥0}^{|R|}`, onde `e_{i,r}` é a quantidade do recurso `r` por equipe
padrão. Essa representação é suficiente para o cálculo de demanda agregada, mas é
insuficiente para raciocinar sobre custo de contratação e oportunidades de
compartilhamento.

A equipe padrão de uma atividade `i` é um **bundle contratado como unidade**:

$$\text{crew}_i := \{ (r,\, e_{i,r}) \mid r \in \mathcal{R},\; e_{i,r} > 0 \}$$

Contratar `m` equipes da atividade `i` significa contratar simultaneamente todas as
funções e equipamentos que compõem `crew_i`, em múltiplos de `m`. Descontratar uma
equipe significa liberar o bundle inteiro — não é possível liberar parcialmente os
componentes de uma única equipe dentro do período de vigência contratual.

**Consequência imediata:** o custo de mobilização e desmobilização incide sobre o bundle,
não sobre os recursos individualmente. O custo de contratar `K_i^{\max}` equipes é:

$$C_i^{\text{mob}} = K_i^{\max} \cdot \sum_{r \in \mathcal{R}} e_{i,r} \cdot c_r^{\text{mob}}$$

e é fixo — independente de como a política de ramp distribui equipes ao longo de `W_i`.

### 1.2 Instâncias e fungibilidade

Dentro de um mesmo tipo de recurso `r`, todas as instâncias são **fungíveis**: uma
instância de escavadeira hidráulica é idêntica a outra do mesmo modelo para fins de
alocação. Isso justifica tratar a perpetuação como transferência de `π_{ij,r}` unidades
anônimas do recurso `r`, sem rastrear identidade de instância.

A fungibilidade não se estende entre recursos distintos: um operador de escavadeira
`ℓ_1` não é substituto de um motorista de caminhão `ℓ_2`, mesmo que ambos sejam mão
de obra. O índice `r` é o nível atômico de fungibilidade.

---

## 2. Modelo de Custo da Atividade Isolada

### 2.1 Decomposição em três componentes

Para uma atividade `i` executada em isolamento — sem nenhum compartilhamento de recursos
com outras atividades — o custo total decompõe-se em três termos estruturalmente
distintos:

$$C_i^{\text{total}} = C_i^{\text{mob}} + C_i^{\text{op}} + C_i^{\text{demob}}$$

**Componente 1 — Mobilização (contratação):**

$$C_i^{\text{mob}} = K_i^{\max} \cdot \sum_{r \in \mathcal{R}} e_{i,r} \cdot c_r^{\text{mob}}$$

Pago uma única vez no início de `W_i`. Proporcional ao pico `K_i^{\max}`, não à média
de equipes ao longo da atividade.

**Componente 2 — Operacional:**

$$C_i^{\text{op}} = \sum_{j \in \mathcal{W}_i} \sum_{r \in \mathcal{R}} m_{ij} \cdot e_{i,r} \cdot \kappa_r(j)$$

onde `κ_r(j)` é o custo unitário do recurso `r` na semana `j`:

$$\kappa_r(j) = \begin{cases}
c_r^h \cdot H_j & r \in \mathcal{L} \quad \text{(mão de obra — horas produtivas)} \\
c_r^{\text{alug}}(j, \texttt{prod}) & r \in \mathcal{Q} \quad \text{(equipamento em produção)}
\end{cases}$$

Este é o único componente afetado pela política de ramp `m_ij`. Um ramp suave
(longas semanas de ramp-up/down) reduz `C_i^{\text{op}}` ao reduzir o número médio
de equipes, mas não reduz `C_i^{\text{mob}}` nem `C_i^{\text{demob}}`.

**Componente 3 — Desmobilização (descontratação):**

$$C_i^{\text{demob}} = K_i^{\max} \cdot \sum_{r \in \mathcal{R}} e_{i,r} \cdot c_r^{\text{demob}}$$

Pago uma única vez ao fim de `W_i`. Simetria com `C_i^{\text{mob}}`.

### 2.2 O efeito do ramp sobre o custo operacional

Seja `K_i^{\max}` o pico e `\bar{m}_i = \frac{1}{n_i} \sum_{j \in \mathcal{W}_i} m_{ij}` a
média de equipes. O ramp introduz uma **eficiência operacional**:

$$\eta_i^{\text{op}} = \frac{\bar{m}_i}{K_i^{\max}} \in (0, 1]$$

com `η_i^{\text{op}} = 1` apenas para ramp zero (plateau puro) e
`η_i^{\text{op}} → 0.5` para ramp triangular simétrico máximo.

O custo operacional pode ser reescrito como:

$$C_i^{\text{op}} = \eta_i^{\text{op}} \cdot K_i^{\max} \cdot \sum_{j \in \mathcal{W}_i} \sum_{r \in \mathcal{R}} e_{i,r} \cdot \kappa_r(j)$$

Portanto, suavizar o ramp **reduz** `C_i^{\text{op}}` mas **não altera** os custos fixos
de mob/demob — que são proporcionais ao pico, não à média. Para atividades onde
`C_i^{\text{mob}} + C_i^{\text{demob}}` domina `C_i^{\text{op}}`, a política de ramp
tem impacto secundário no custo total.

### 2.3 Custo unitário de equipe

Define-se o **custo por equipe-semana** da atividade `i` na semana `j`:

$$\gamma_{ij} = \sum_{r \in \mathcal{R}} e_{i,r} \cdot \kappa_r(j)$$

de forma que `C_i^{\text{op}} = \sum_{j \in \mathcal{W}_i} m_{ij} \cdot \gamma_{ij}`.

Este escalar resume o custo operacional de uma equipe por semana e é útil para
comparar o peso relativo de mob/demob versus operação:

$$\rho_i = \frac{C_i^{\text{mob}} + C_i^{\text{demob}}}{C_i^{\text{op}}}$$

Quando `ρ_i ≫ 1`, a atividade é dominada por custos de transação — cada evento de
mob/demob é proporcionalmente caro. Quando `ρ_i ≪ 1`, o custo operacional domina e
o compartilhamento de recursos tem impacto relativo menor.

---

## 3. Custo de Recursos Ociosos

### 3.1 O estado idle e sua origem

Uma instância do recurso `r` perpetuada de `i` para `j` — isto é, mantida mobilizada
entre o fim de `W_i` e o início de `W_j` — permanece em estado `idle` durante o gap:

$$\text{gap}_{ij} = s_j - f_i \geq 0 \quad \text{(semanas)}$$

O custo de uma instância em estado `idle` depende da unidade de faturamento do recurso:

$$c_r^{\text{idle}}(j) = \begin{cases}
0 & u_r = \texttt{hora\_prod} \quad \text{(não fatura sem produção)} \\
\rho_r \cdot d_j & u_r = \texttt{dia\_cal} \quad \text{(fatura por dia calendário)} \\
\rho_r / (52/12) & u_r = \texttt{mes} \quad \text{(fatura mensalmente)}
\end{cases}$$

Para mão-de-obra `r ∈ L`, o custo idle é o salário mensal integral — trabalhador
mobilizado mas sem atividade produtiva incorre custo de folha.

### 3.2 Custo total de idle para uma perpetuação

Para `π_{ij,r}` instâncias perpetuadas com gap `gap_{ij}` semanas, o custo idle
acumulado é:

$$C_{ij,r}^{\text{idle}} = \pi_{ij,r} \cdot \sum_{j' = f_i + 1}^{s_j} c_r^{\text{idle}}(j')$$

Para gaps pequenos e recursos com `u_r = \texttt{hora\_prod}`, `C_{ij,r}^{\text{idle}} = 0`
— não há custo de ociosidade. Para equipamentos pesados com diária e mão-de-obra
especializada, o custo idle por semana pode ser comparável ao custo operacional semanal.

---

## 4. Economia Real do Compartilhamento

### 4.1 Economia bruta vs. economia real

O modelo de Matching atual maximiza `Σ π_{ij,r}` (perpetuações), capturando a
**economia bruta**:

$$\Delta C_{ij,r}^{\text{bruto}} = \pi_{ij,r} \cdot (c_r^{\text{mob}} + c_r^{\text{demob}})$$

Mas a **economia real** desconta o custo idle gerado pela perpetuação:

$$\Delta C_{ij,r}^{\text{real}} = \pi_{ij,r} \cdot \left[(c_r^{\text{mob}} + c_r^{\text{demob}}) - \sum_{j'=f_i+1}^{s_j} c_r^{\text{idle}}(j')\right]$$

### 4.2 Condição de viabilidade econômica da perpetuação

A perpetuação `(i, j, r)` é **economicamente viável** somente se:

$$\Delta C_{ij,r}^{\text{real}} > 0 \iff (c_r^{\text{mob}} + c_r^{\text{demob}}) > \sum_{j'=f_i+1}^{s_j} c_r^{\text{idle}}(j')$$

Define-se o **gap máximo economicamente viável** para o recurso `r`:

$$\text{gap}_r^{\max} = \max\left\{ g \in \mathbb{Z}_{\geq 0} \;\middle|\; (c_r^{\text{mob}} + c_r^{\text{demob}}) > \sum_{j'=1}^{g} c_r^{\text{idle}}(j') \right\}$$

Para `gap_{ij} > gap_r^{max}`, perpetuar o recurso `r` entre `i` e `j` aumenta
`C_total` — a aresta `(i, j, r)` deve ser **removida do grafo `G_r` antes do Matching**.

### 4.3 Índice de eficiência da perpetuação

Para cada aresta `(i, j, r)` com `gap_{ij} ≤ gap_r^{max}`, define-se:

$$\eta_{ij,r} = 1 - \frac{\displaystyle\sum_{j'=f_i+1}^{s_j} c_r^{\text{idle}}(j')}{c_r^{\text{mob}} + c_r^{\text{demob}}} \in (0, 1]$$

com `η_{ij,r} = 1` para perpetuação sem gap (atividades adjacentes) e
`η_{ij,r} → 0` quando o gap se aproxima de `gap_r^{max}`.

A economia real esperada de uma perpetuação é então:

$$\Delta C_{ij,r}^{\text{real}} = \pi_{ij,r} \cdot \eta_{ij,r} \cdot (c_r^{\text{mob}} + c_r^{\text{demob}})$$

---

## 5. Sobreposição de Composição de Equipe

### 5.1 Motivação

Dois pares de atividades podem ter o mesmo `π_{ij,r}^{\max}` para um recurso `r`, mas
diferir substancialmente em quantos recursos do bundle total podem ser compartilhados.
O par que compartilha mais recursos do bundle tem maior potencial de redução de
`C^{\text{mob}}` total, e portanto maior valor de serialização no Scheduling.

### 5.2 Vetor de sobreposição por recurso

Para um par `(i, j)` com precedência em `G`, a sobreposição por recurso é:

$$\text{ov}_{ij,r} = \min(e_{i,r},\, e_{j,r}) \in \mathbb{Z}_{\geq 0}$$

`ov_{ij,r} = 0` quando um dos dois não usa o recurso `r`. O **vetor de sobreposição**
`ov_{ij} ∈ Z_{≥0}^{|R|}` captura quais componentes do bundle são compartilháveis.

### 5.3 Índice de sobreposição econômica

Para agregar o vetor de sobreposição em um escalar que reflita valor econômico,
pondera-se pelo custo de mob/demob de cada recurso:

$$\Omega_{ij} = \frac{\displaystyle\sum_{r \in \mathcal{R}} \text{ov}_{ij,r} \cdot (c_r^{\text{mob}} + c_r^{\text{demob}})}{\displaystyle\sum_{r \in \mathcal{R}} \max(e_{i,r}, e_{j,r}) \cdot (c_r^{\text{mob}} + c_r^{\text{demob}})} \in [0, 1]$$

`Ω_{ij} = 1` indica que as equipes de `i` e `j` são idênticas — todo o bundle é
compartilhável. `Ω_{ij} = 0` indica que não há nenhum recurso em comum — a serialização
não gera nenhum benefício de compartilhamento.

### 5.4 Economia potencial máxima do par

Combinando o índice de sobreposição com `K_i^{max}` e `K_j^{max}`, a **economia
potencial máxima** de serializar o par `(i, j)` — supondo perpetuação sem gap — é:

$$\Delta C_{ij}^{\text{pot}} = \min(K_i^{\max},\, K_j^{\max}) \cdot \sum_{r \in \mathcal{R}} \text{ov}_{ij,r} \cdot \eta_{ij,r} \cdot (c_r^{\text{mob}} + c_r^{\text{demob}})$$

Este escalar é calculável em tempo de compilação do grafo, antes de qualquer
otimização, e serve como **limite superior** para o ganho de Matching sobre o par `(i, j)`.

---

## 6. Grafo de Oportunidades de Compartilhamento

### 6.1 Definição

Define-se o **grafo de oportunidades** `H = (A, F)` como o subgrafo do grafo de
precedências `G` onde cada aresta `(i, j)` é ponderada por `ΔC_{ij}^{pot}` e anotada
com o vetor de sobreposição `ov_{ij}`:

$$F = \left\{ (i, j) \in \mathcal{E} \;\middle|\; \Delta C_{ij}^{\text{pot}} > 0 \right\}$$

Arestas com `ΔC_{ij}^{pot} = 0` são removidas — serializar esse par não gera nenhum
benefício de compartilhamento.

### 6.2 Grafo por recurso com poda de gap

Para cada recurso `r`, o subgrafo viável é:

$$G_r^{\text{viável}} = \left\{ (i, j, r) \in G_r \;\middle|\; \text{gap}_{ij} \leq \text{gap}_r^{\max} \;\wedge\; e_{i,r} > 0 \;\wedge\; e_{j,r} > 0 \right\}$$

Este é o grafo que alimenta o oráculo de Matching no ADR-75 — em vez do grafo `G_r`
completo. A poda estática remove arestas não-viáveis antes do min-cost flow, reduzindo
o problema e eliminando perpetuações prejudiciais.

---

## 7. Pré-processamento Estrutural

### 7.1 Pipeline de pré-processamento

O pré-processamento é executado uma única vez após a validação do `RampProfile`,
antes do início do Scheduling. Produz os artefatos que alimentam o motor de otimização:

```
Entradas: RampProfile[], GrafoPrecedencias G, ParâmetrosCusto

(1) Para cada atividade i:
    → Calcular γ_ij (custo equipe-semana)
    → Calcular ρ_i (razão mob-demob / operacional)
    → Calcular C_i^mob, C_i^demob, C_i^op (custo isolado)

(2) Para cada recurso r:
    → Calcular gap_r^max a partir de c_r^idle e (c_r^mob + c_r^demob)

(3) Para cada aresta (i, j) em G com e_{i,r} > 0 e e_{j,r} > 0:
    → Calcular ov_{ij,r} e ov_{ij}
    → Calcular Ω_{ij} (índice de sobreposição econômica)
    → Calcular η_{ij,r} (eficiência de perpetuação por recurso)
    → Calcular ΔC_{ij}^pot (economia potencial máxima)
    → Podar aresta se gap_{ij} > gap_r^max ou ΔC_{ij}^pot = 0

(4) Construir G_r^viável para cada recurso r

(5) Gerar λ_0 inicial para o Scheduling (ver §7.2)

Saídas: G_r^viável[], λ_0, RelatorioOportunidades
```

### 7.2 Inicialização de `λ_0` a partir da estrutura

O Scheduling no Modo B do ADR-75 usa penalidades `λ_k` sobre pares concorrentes
para aproximar `C_mob`. O pré-processamento permite inicializar `λ_0` com informação
estrutural real — em vez de zero:

$$\lambda_0(i, j) = \Delta C_{ij}^{\text{pot}} \cdot \Omega_{ij}$$

Pares com alta sobreposição e alta economia potencial recebem penalidade inicial alta,
orientando o Scheduling a serializá-los desde a primeira iteração. Isso reduz o número
de iterações necessárias para convergência.

### 7.3 Relatório de oportunidades

O pré-processamento produz um relatório estático legível pelo planejador antes da
execução da otimização:

| Par `(i, j)` | `Ω_{ij}` | `ΔC_{ij}^{pot}` | `gap_r^{max}` (menor) | Recursos compartilháveis |
|---|---|---|---|---|
| (Terraplenagem, Drenagem) | 0.82 | R$ 45.000 | 3 semanas | Escavadeira, Operador, Caminhão |
| (Drenagem, Pavimentação) | 0.31 | R$ 12.000 | 1 semana | Caminhão |
| (Estrutura A, Estrutura B) | 1.00 | R$ 78.000 | 5 semanas | Bundle completo |

Este relatório tem valor independente da otimização: informa ao planejador quais pares
de atividades têm maior incentivo econômico para serialização, podendo influenciar
decisões de sequenciamento antes mesmo de rodar o motor.

---

## 8. Síntese — Relação com o ADR-75

O pré-processamento estrutural não altera a arquitetura de otimização do ADR-75 —
é uma camada anterior que a torna mais eficiente e economicamente correta:

| Problema identificado | Solução estrutural | Impacto no ADR-75 |
|---|---|---|
| Matching pode recomendar perpetuações prejudiciais (gap > `gap_r^max`) | Poda estática de `G_r` | `G_r^viável` substitui `G_r` no oráculo de Matching |
| `λ_0 = 0` ignora informação estrutural disponível | Inicialização via `ΔC_{ij}^{pot} · Ω_{ij}` | Reduz iterações do Modo B de 4–10 para 2–4 |
| Custo de mob/demob calculado sobre pico `K_max`, não média | Separação explícita `C^mob + C^op + C^demob` | Corrige `C_total` reportado por atividade |
| Planejador não tem visibilidade de oportunidades antes da otimização | Relatório de oportunidades | Artefato de saída do pré-processamento |

O pré-processamento torna-se a **Fase 0** do plano de implementação do ADR-75,
executada antes das Fases 1–5 existentes, e seus artefatos (`G_r^viável`, `λ_0`,
relatório) são pré-condições formais das fases subsequentes.