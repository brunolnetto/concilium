# NEP-038: Criticidade RCPSP e Teoria de Compressão de Cronograma

**Status:** Proposta  
**Prioridade:** 🟡 Alta  
**Área:** Scheduling e Otimização  
**Tipo:** Formalização + Feature  
**Esforço:** L  
**Identificado em:** 2026-06-01  
**Depende de:** ADR-071 (pool contracts), ADR-079 (ativação econômica), NEP-035 (η)

---

## Contexto

A análise de k-scaling do projeto AGIS revelou um fenômeno que o **CPM clássico não
consegue capturar**: a atividade DESMAT possui float de 21 semanas na solução RCPSP
atual, mas dobrar seus recursos (DESMAT×2→×4) reduz o makespan em **5 semanas** com
ROI de 96.8×. Isso acontece porque DESMAT é um **gateway de recursos** — ao liberar
suas máquinas 17 semanas mais cedo, o solver RCPSP encontra uma reconfiguração global
do schedule que avança o projeto inteiro.

O CPM (Critical Path Method) clássico pressupõe recursos ilimitados. O RCPSP
(Resource-Constrained PSP) impõe restrições de pool que criam dois fenômenos
adicionais inexistentes no CPM:

1. **Float de recurso**: atraso de uma atividade causado não por precedências, mas
   por contenção de recursos.
2. **Efeito gateway**: compressão de uma atividade libera recursos que permitem ao
   solver reotimizar o schedule global, reduzindo o makespan mesmo quando a atividade
   não está no caminho crítico CPM.

Esta NEP formaliza matematicamente o critério de criticidade no contexto RCPSP e
define como identificar, quantificar e explorar oportunidades de compressão.

---

## Modelo

### Notação

| Símbolo | Tipo | Significado |
|---------|------|-------------|
| G = (V, E) | DAG | Atividades V, precedências E |
| θ_{ij} ∈ (0,1] | Escalar | Threshold de completude em (i,j) ∈ E |
| d_i | Inteiro ≥ 1 | Duração produtiva da atividade i (semanas) |
| r_{ir} | Inteiro ≥ 0 | Recursos do tipo r necessários por i |
| R_r | Inteiro ≥ 1 | Pool disponível do tipo r |
| C_max | Inteiro | Makespan do projeto |
| S\* | Schedule | Solução ótima RCPSP |

### Fórmula de produção

A duração produtiva de cada atividade é determinada por:

```
d_i = ⌈ Q_i / (P_i · h · n_i · p_i) ⌉
```

onde Q_i é o quantitativo, P_i a produtividade nominal, h horas/semana, n_i o
número de equipes alocadas (controla r_{ir}) e p_i o fator de praticabilidade
(clima + calendário).

### k-Scaling

Dado um fator inteiro k ≥ 1 aplicado à atividade i:

```
d_i(k) = ⌈ d_i / k ⌉           # duração comprimida
r_ir(k) = k · r_ir              # k vezes mais recursos necessários
```

**Invariante fundamental**: o custo direto de execução é constante em k:

```
custo_direto_i(k) = k · c_i · d_i(k) ≈ c_i · d_i  (constante)
```

A multiplicação k × equipes cancela a divisão d_i/k de duração. O custo direto
por atividade não muda com k — apenas o custo de instâncias de pool muda.

---

## Duas Categorias de Criticidade

### P1: Criticidade CPM (sem restrição de recursos)

O CPM clássico calcula:

```
ES_i^CPM = max(0,  max_{(j,i)∈E} (EF_j^CPM · θ_{ji}))
EF_i^CPM = ES_i^CPM + d_i

LS_i^CPM = C_max^CPM - d_i,  propagado backward pelo grafo
LF_i^CPM = LS_i^CPM + d_i

TF_i^CPM = LS_i^CPM - ES_i^CPM  (float CPM)
```

**Atividade Precedência-Crítica (PC):** TF_i^CPM = 0.

Uma atividade PC pertence ao caminho mais longo do grafo. Comprimir 1 semana →
makespan cai 1 semana (sem restrição de recursos). Compressão yield = 1.

### P2: Criticidade RCPSP

Na solução ótima S\* do RCPSP:

```
start_i^* ≥ ES_i^CPM   (toda atividade começa após sua janela de precedência)
RD_i = start_i^* - ES_i^CPM ≥ 0   (atraso por recurso)
```

A partir de S\*, o backward pass produz:

```
LS_i^* = C_max^* - d_i,  propagado pelo grafo de precedência
TF_i^* = LS_i^* - start_i^*  (float na solução RCPSP)
```

**Atividade Recurso-Crítica (RC):** TF_i^* = 0 mas TF_i^CPM > 0.
Uma RC não é crítica por precedência mas seu start está encostado no limite —
qualquer atraso adicional aumenta o makespan.

**Atividade Gateway (GW):** TF_i^* > 0 mas comprimir d_i reduz C_max^*.
Contraintuitivo: mesmo com float positivo no schedule atual, a atividade é um
gargalo latente. O efeito ocorre porque comprimir i libera pool r_{ir} que permite
ao solver reorganizar outras atividades.

---

## Sensibilidade de Compressão

### Definição: Rendimento de Compressão γ

Para cada atividade i e fator k:

```
Δd_i(k) = d_i - d_i(k) = d_i · (1 - 1/k)           # redução de duração
ΔC_max(i,k) = C_max^* - C_max(d_i → d_i(k))        # redução de makespan

γ_i(k) = ΔC_max(i,k) / Δd_i(k)  ∈ [0, 1]
```

γ_i(k) é o **rendimento de compressão**: quantas semanas de makespan são ganhas
por semana de duração comprimida na atividade i.

| Tipo de atividade | γ_i(k) | Explicação |
|-------------------|---------|------------|
| Precedência-crítica (PC) | ≈ 1.0 | 1 semana de duração → 1 semana de makespan |
| Gateway (GW) | 0 < γ < 1 | Efeito indireto via reorganização do solver |
| Não-crítica livre | ≈ 0 | Float absorve a compressão, makespan não muda |
| Recurso-bloqueada | < 0 | Dobrar recursos satura pool e piora o schedule |

**Nota**: γ pode ser negativo quando k-scaling de i satura um tipo de recurso
compartilhado, impedindo o paralelismo que existia antes (exemplo: ESC-3CAT com
pool = 6 e 3 atividades cada uma usando 3 — dobrar qualquer uma para 6 bloqueia
as outras duas).

### Cálculo de γ por Perturbação

Dado o schedule S\*, o γ é computado por:

```python
def compute_gamma(i, k, dag, pool, scheduler) -> float:
    d_new = ceil(d_i / k)
    delta_d = d_i - d_new
    if delta_d == 0:
        return 0.0
    C_new = scheduler.solve(dag_with(d_i=d_new, r_ir=k*r_ir))
    return (C_max_star - C_new) / delta_d
```

Custo computacional: O(n × RCPSP) — n chamadas ao solver, viável para n ≤ ~20.

---

## Efeito Gateway: Por que TF > 0 não implica γ = 0

O RCPSP é um problema de otimização global. Quando d_i diminui, o solver tem
**mais graus de liberdade** para reposicionar todas as atividades que compartilham
recursos com i ou com os sucessores de i.

Formalizando: seja R(i) ⊆ V o conjunto de atividades que competem pelo mesmo pool
de recursos que i durante a execução de i:

```
R(i) = {j ∈ V : ∃ r tal que r_{ir} > 0, r_{jr} > 0,
                 [start_i^*, EF_i^*] ∩ [start_j^*, EF_j^*] ≠ ∅}
```

Se i é um "gateway" para um conjunto C ⊆ V de atividades de encerramento do
projeto, então comprimir i → os membros de C podem começar mais cedo → C_max cai.

O mecanismo completo tem três etapas:

```
1. d_i ↓  →  EF_i^* ↓                     (i termina mais cedo)
2. EF_i^* ↓  →  recursos r_{ir} liberados antes
3. solver reposiciona atividades em R(i),
   antecipando atividades downstream → C_max ↓
```

O passo 3 é o que o CPM não modela — ele assume que cada atividade começa no seu
ES independentemente, sem a reorganização global que o RCPSP solver faz.

---

## Fórmula de ROI de k-Scaling

### Custo de instâncias extras

```
Δcost_pool(i, k) = (k-1) · n_i · (c_mob + c_demob + c_idle · d_i(k) · α_idle)
```

onde:
- n_i = r_{ir_bot} com r_bot = tipo de recurso bottleneck da atividade i
- c_mob, c_demob = custos de mobilização e desmobilização por instância
- c_idle = custo semanal de standby por instância
- α_idle ≈ 0.20 = fração de idle estimado durante a atividade (conservador)

### ROI econômico

```
ROI(i, k) = [γ_i(k) · Δd_i(k) · C_semana] / Δcost_pool(i, k)
```

onde C_semana é o custo semanal do projeto (overhead + amortização de contratos):

```
C_semana = preco_venda_total / C_max^*
```

### Condição de break-even para k=2

Para k=2 com Δd ≈ d_i/2:

```
ROI(i, 2) > 1
⟺
γ_i(2) · (d_i/2) · C_semana > n_i · (c_mob + c_demob + c_idle · (d_i/2) · α)
⟺
γ_i(2) > γ_i^min(2) = 2·n_i·c_inst / (d_i · C_semana)
```

onde c_inst = c_mob + c_demob + c_idle · (d_i/2) · α.

**Interpretação**: γ_i^min é o rendimento de compressão mínimo necessário para
que k=2 seja economicamente justificável. Para projetos com C_semana alto (projetos
grandes), γ_i^min tende a zero — quase qualquer compressão vira lucrativa.

---

## Piso de Makespan

Dado k ilimitado (recursos ilimitados por atividade), o makespan mínimo é:

```
C_max^floor = CPM( { d_i^min } )   onde   d_i^min = ⌈ Q_i / (P_i · h · n_i^max · p_i) ⌉
```

C_max^floor é o comprimento do caminho crítico **de precedências** com as menores
durações possíveis. Ele representa o piso absoluto — não pode ser reduzido sem:
(a) alterar quantitativos Q_i, (b) mudar a praticabilidade p_i, ou (c) revisar
a estrutura de precedências do EAP.

Para k suficientemente grande mas finito, existe um k\* onde:

```
C_max(k*) = C_max^floor   e   γ_i(k > k*) = 0  ∀i
```

k\* é o fator que "satura" a compressão precedência-limitada.

---

## Algoritmo Ótimo de k-Scaling

### Procedimento Greedy com Re-análise

```
entrada: G, S*, pool, contratos, C_semana, budget B
saída:   {k_i}  com ROI ótimo dentro de B

1.  Inicializar k_i ← 1 para todo i
2.  Enquanto B > 0:
    a.  Para cada atividade i ∈ V:
          Calcular γ_i(k_i + 1) por perturbação do solver
          ROI_i ← [γ_i(k_i+1) · Δd_i · C_semana] / Δcost(i, k_i+1)
    b.  i* ← argmax ROI_i
    c.  Se ROI_{i*} ≤ 1: parar (retorno marginal abaixo do break-even)
    d.  k_{i*} ← k_{i*} + 1
        B ← B - Δcost(i*, k_{i*})
    e.  Re-resolver RCPSP com os k_i atuais → atualizar C_max^* e start_i^*
3.  Retornar {k_i}
```

**Complexidade**: O(|iterações| × n × RCPSP). Na prática, |iterações| é pequeno
porque γ_i(k) cai rapidamente após atingir o bottleneck de precedência.

### Heurística de Triagem a Priori (sem solver)

Para triagem barata antes de rodar o CP-SAT por atividade:

```
score_i = (d_i / C_max^*) · (Σ_r r_{ir}/R_r) / (1 + TF_i^*/C_max^*)
```

Atividades com score_i alto são candidatas prioritárias. O score combina:
- d_i / C_max^*: fração do makespan que a atividade consome
- Σ_r r_{ir}/R_r: carga relativa de recursos (saturação de pool)
- 1 / (1 + TF_i^*/C_max^*): inversamente proporcional ao float relativo

---

## Validação: Projeto AGIS

Resultados do CP-SAT com k=2 por atividade (baseline = 55w):

| Atividade | Recurso | d | d(k=2) | Makespan(k=2) | γ(k=2) | ROI(k=2) | Tipo |
|-----------|---------|---|--------|---------------|--------|----------|------|
| eap-1_0 | DESMAT×2 | 34w | 17w | 50w | **0.29** | **96.8×** | **Gateway** |
| eap-1_10 | ATERRO×1 | 6w | 3w | 53w | 0.67 | 39.2× | RC |
| eap-1_9 | ESC-3CAT×3 | 32w | 16w | 56w | **-0.06** | negativo | **Bloqueada** |
| eap-1_4 | ESC-2CAT×2 | 39w | 20w | 55w | 0 | — | Livre |
| outros | — | — | — | 55w | 0 | — | Livre |

**Insight do AGIS:**

DESMAT é um gateway puro: TF\* = 21w (não é precedência-crítica, não é recurso-
crítica), mas γ = 0.29 — cada semana comprimida de DESMAT rende 0.29 semanas de
makespan. Com d = 34w e k=2 (Δd=17w), o ganho total é 17 × 0.29 ≈ 5w.

ESC-3CAT (eap-1_9) é bloqueada (γ < 0): pool ESC-3CAT = 6 dividido entre 3
atividades × 3 unidades cada. Dobrar qualquer atividade para 6 unidades satura o
pool inteiro, eliminando o paralelismo existente e piorando o makespan.

**Platô de compressão DESMAT:**

| k | d(k) | C_max | γ(k) | ROI |
|---|------|-------|------|-----|
| 1 | 34w | 55w | — | — |
| 2 | 17w | 50w | 0.29 | 96.8× |
| 3 | 12w | 50w | 0 | — |
| 4 | 9w | 50w | 0 | — |

A compressão satura em k=2 — o bottleneck passa para a cadeia eap-1_4 → eap-1_3 →
eap-1_10 (caminho ESC-2CAT de 39+7+6=52w a partir da semana 1, finalizando na 50).
k=3,4 não adicionam valor marginal.

**Piso de makespan AGIS:** ~50w (limitado pela cadeia ESC-2CAT após compressão do DESMAT).

---

## Plano de Implementação

### Função principal

```python
# src/concilium/application/scheduling/compression_analysis.py

def compute_compression_sensitivities(
    sched_acts: dict[str, ScheduledActivity],
    dag: ActivityDAG,
    pool: ResourcePool,
    contratos: dict[str, ContratoRecurso],
    scheduler: BaseScheduler,
    k_values: list[int] = (2, 3),
) -> list[CompressionResult]:
    """
    Para cada atividade, calcula γ(k), ROI(k) e classifica como
    PC | RC | GW | Bloqueada | Livre.
    """
```

```python
@dataclass
class CompressionResult:
    activity_id: str
    tipo_recurso: str
    n_base: int
    duration_base: int
    criticality_class: str   # "PC" | "RC" | "GW" | "Bloqueada" | "Livre"
    by_k: dict[int, KScaleResult]

@dataclass
class KScaleResult:
    k: int
    duration_new: int
    makespan_new: int
    delta_makespan: int
    gamma: float             # rendimento de compressão ΔC_max/Δd
    cost_extra: float        # custo pool extra
    poupanca: float          # C_semana × ΔC_max
    roi: float
```

### Integração no pipeline

A análise de compressão deve ser acionada:
1. Como output do benchmark (após skill-04/skill-05)
2. Como ferramenta MCP `analyze_schedule_compression`
3. Nas comparações multi-cenário (ADR-075 compare CLI)

### DoD

- [ ] `compute_compression_sensitivities` implementada e testada com AGIS (γ_DESMAT ≈ 0.29)
- [ ] `CompressionResult` serializado no canônico como `compressao_cronograma`
- [ ] Seção "Oportunidades de Compressão" adicionada ao PDF (skill-09)
- [ ] Heurística de triagem a priori disponível (sem re-rodar RCPSP)
- [ ] Testes unitários: γ=1 para atividade isolada no CP, γ=0 para atividade livre

---

## Referências

- Brucker, P. et al. (1999). *Resource-constrained project scheduling: Notation,
  classification, models, and methods.* European Journal of Operational Research.
- Hartmann, S. & Briskorn, D. (2010). *A survey of variants and extensions of the
  resource-constrained project scheduling problem.* EJOR.
- ADR-071: Contratos de Pool (mob/demob/idle)
- ADR-079: Ativação Econômica de Compartilhamento
- NEP-035: Decomposição de Eficiência η_s × η_p × η_w
