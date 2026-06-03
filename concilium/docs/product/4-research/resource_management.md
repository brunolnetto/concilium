# Formalização do Problema de Resource Management com Precedência e Perpetuação de Recursos

---

## 1. Estrutura do Projeto

### 1.1 DAG de Atividades

Seja o projeto representado por um grafo orientado acíclico (DAG):

$$\mathcal{G} = (\mathcal{A}, \mathcal{E})$$

onde $\mathcal{A} = \{1, \ldots, n\}$ é o conjunto de atividades e $\mathcal{E} \subseteq \mathcal{A} \times \mathcal{A}$ o conjunto de arestas de precedência, tal que $(i, j) \in \mathcal{E}$ significa que a atividade $i$ é predecessora imediata de $j$.

Defina:
- $\text{pred}(j) = \{i \in \mathcal{A} : (i,j) \in \mathcal{E}\}$ — predecessores imediatos de $j$
- $\text{succ}(i) = \{j \in \mathcal{A} : (i,j) \in \mathcal{E}\}$ — sucessores imediatos de $i$
- $\text{Pred}^*(j)$ — fecho transitivo dos predecessores de $j$

---

## 2. Recursos

### 2.1 Tipos de Recursos

Seja $\mathcal{R} = \mathcal{L} \cup \mathcal{Q}$ o conjunto total de tipos de recursos, onde:
- $\mathcal{L}$ — funções de mão-de-obra (e.g., operador, motorista, encarregado)
- $\mathcal{Q}$ — equipamentos (e.g., escavadeira, caminhão)

### 2.2 Equipe Padrão

Para cada atividade $i \in \mathcal{A}$, define-se uma **equipe padrão unitária** $\mathbf{e}_i \in \mathbb{Z}_{\geq 0}^{|\mathcal{R}|}$, onde:

$$e_{i,r} \in \mathbb{Z}_{\geq 0}, \quad \forall r \in \mathcal{R}$$

é a quantidade inteira do recurso $r$ por equipe padrão da atividade $i$.

### 2.3 Número de Equipes e Política de Ramp

Seja $k_i(t)$ o número de equipes alocadas à atividade $i$ no instante $t$, com:

$$k_i(t) \in \mathbb{Z}_{\geq 0}, \quad k_i(t) \leq K_i^{\max}$$

A política de **ramp-up/down linear** é definida por taxas $\rho_i^+ \in \mathbb{R}_{>0}$ (mobilização) e $\rho_i^- \in \mathbb{R}_{>0}$ (desmobilização), tal que:

$$k_i(t) = \begin{cases} \min\!\left(\lfloor \rho_i^+(t - s_i) \rfloor,\, K_i^{\max}\right) & \text{fase ramp-up} \\ K_i^{\max} & \text{fase plena} \\ \max\!\left(K_i^{\max} - \lfloor \rho_i^-(t - t_i^*) \rfloor,\, 0\right) & \text{fase ramp-down} \end{cases}$$

onde $s_i$ é o instante de início de $i$ e $t_i^*$ é o instante de início da desmobilização.

---

## 3. Instâncias de Recursos e Perpetuação

### 3.1 Instâncias Nominais

Sem perpetuação, o número máximo de instâncias distintas (workers/equipamentos) seria limitado pela soma:

$$R_r^{\text{naive}} = \sum_{i \in \mathcal{A}} K_i^{\max} \cdot e_{i,r}$$

Esta é a **cota conservadora** que ignora a estrutura de precedência.

### 3.2 Compatibilidade de Perpetuação

Dizemos que a atividade $j$ pode **herdar** instâncias do recurso $r$ a partir de $i$ se:

1. $(i, j) \in \mathcal{E}$ — relação de precedência direta (ou via fecho transitivo para perpetuação em cadeia)
2. $e_{i,r} > 0$ e $e_{j,r} > 0$ — ambas demandam o recurso $r$
3. Existe sobreposição ou continuidade temporal: $f_i \geq s_j - \delta$ para alguma tolerância $\delta \geq 0$, onde $f_i$ é o fim da atividade $i$

Formalize a **relação de perpetuação** como:

$$\Pi \subseteq \mathcal{A} \times \mathcal{A} \times \mathcal{R}$$

onde $(i, j, r) \in \Pi$ indica que instâncias do recurso $r$ são perpetuadas de $i$ para $j$.

### 3.3 Quantidade Perpetuada

Para cada tripla $(i, j, r) \in \Pi$, a quantidade perpetuada é:

$$\pi_{ij,r} = \min\!\left(K_j^{\max} \cdot e_{j,r},\; k_i(f_i) \cdot e_{i,r}\right) \in \mathbb{Z}_{\geq 0}$$

ou seja, o mínimo entre o que $j$ precisará ao início e o que $i$ libera ao fim — **sem criar novas instâncias**.

---

## 4. Modelo de Alocação com Perpetuação

### 4.1 Demanda Líquida de Novas Instâncias

Defina a demanda de instâncias **novas** (mobilização efetiva) do recurso $r$ para a atividade $j$:

$$\nu_{j,r} = K_j^{\max} \cdot e_{j,r} \;-\; \sum_{i \,:\, (i,j,r)\,\in\,\Pi} \pi_{ij,r}$$

com $\nu_{j,r} \geq 0$ por construção.

### 4.2 Bound Global de Instâncias

O número total de instâncias distintas do recurso $r$ ao longo do projeto é:

$$R_r^* = \max_{t}\; \sum_{i \in \mathcal{A}} k_i(t) \cdot e_{i,r} \cdot \mathbf{1}[i \text{ ativo em } t]$$

Este é o **pico de concorrência real**, sujeito ao calendário de execução. O número de instâncias que precisam ser **mobilizadas** (criadas) ao longo do projeto é:

$$M_r = \sum_{j \in \mathcal{A}} \nu_{j,r}$$

com $M_r \leq R_r^{\text{naive}}$, sendo a diferença a economia de mobilização via perpetuação.

---

## 5. Grafo de Perpetuação

Estenda o DAG $\mathcal{G}$ para um **grafo de perpetuação por recurso** $\mathcal{G}_r = (\mathcal{A}, \mathcal{E}_r)$, onde:

$$\mathcal{E}_r = \{(i,j) : (i,j,r) \in \Pi\}$$

Cada aresta $(i,j) \in \mathcal{E}_r$ carrega o peso $\pi_{ij,r}$.

**Propriedade chave:** Sendo $\mathcal{G}$ um DAG, $\mathcal{G}_r$ é também um DAG — logo, não há ciclos de perpetuação e o fluxo de instâncias é bem definido.

O **balanço de instâncias** em cada nó $j$ satisfaz:

$$\underbrace{K_j^{\max} \cdot e_{j,r}}_{\text{demanda de }j} = \underbrace{\nu_{j,r}}_{\text{novas instâncias}} + \underbrace{\sum_{i:(i,j)\in\mathcal{E}_r} \pi_{ij,r}}_{\text{herdadas}}$$

---

## 6. Síntese Estrutural

| Grandeza | Símbolo | Natureza |
|---|---|---|
| Atividades | $\mathcal{A}$ | Conjunto finito |
| Precedências | $\mathcal{E}$ | DAG |
| Recursos | $\mathcal{R} = \mathcal{L} \cup \mathcal{Q}$ | Funções + Equipamentos |
| Equipe padrão | $e_{i,r} \in \mathbb{Z}_{\geq 0}$ | Inteira, por tipo |
| Equipes alocadas | $k_i(t) \leq K_i^{\max}$ | Inteira, com ramp |
| Perpetuação | $\Pi \subseteq \mathcal{A} \times \mathcal{A} \times \mathcal{R}$ | Relação ternária |
| Instâncias novas | $\nu_{j,r} \geq 0$ | Demanda líquida |
| Pico de concorrência | $R_r^*$ | Bound operacional |
| Total mobilizado | $M_r \leq R_r^{\text{naive}}$ | Custo de mobilização |

O modelo assim formalizado permite distinguir três problemas canônicos:

1. **Scheduling** — determinar $s_i$ respeitando $\mathcal{E}$ para minimizar $R_r^*$
2. **Matching de instâncias** — determinar $\Pi$ ótimo dado o calendário
3. **Nivelamento** — suavizar $k_i(t)$ via ramp para minimizar picos e mobilizações redundantes