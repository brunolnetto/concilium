# ADR-133 — Oportunidade de Compartilhamento Paralelo de Recursos

**Status:** ✅ Implementado _(confirmado 2026-07-08 na renumeração de ADR-110 órfão: `_deteccao_paralelo.py`, `_skill_helpers_compartilhamento.py`, wired em `skill.py`, 26 testes)_  
**Data:** 2026-06-16  
**Revisão:** 2026-06-16 — reformulação de "declaração pelo usuário" para "detecção automática pós-RCPSP"  
**Contexto:** MendesLobo Construtora — Concilium

---

## Contexto

### O problema de campo

Em obras de terraplenagem e infraestrutura linear (ferrovias, rodovias), é comum que
múltiplas atividades corram em paralelo ao longo de diferentes frentes geográficas.
Uma situação recorrente: a Escavadeira Hidráulica de 22t que opera na frente A (corte)
pode, no mesmo período semanal, ser deslocada para a frente B (aterro) durante metade
do turno — especialmente quando a frente A aguarda caminhões ou o operador de B está
em pausa técnica.

O modelo atual (ADR-075, ADR-081, ADR-086) trata cada atividade como consumidora
**exclusiva** do recurso pelo período em que está ativa. Isso produz dimensionamentos
corretos na teoria, mas sistematicamente superdimensionados na prática: o planejador
de campo reduz a frota pela metade sabendo que duas escavadeiras nunca operam a
100% em paralelo na mesma semana.

### O que já existe no modelo

**ADR-016** introduziu a `ClasseCompartilhamento` no catálogo de insumos:

| Classe | Semântica | Campo |
|---|---|---|
| A — `exclusivo_dedicado` | 1 recurso : 1 atividade | `fracao_uso = 1.0` |
| B — `exclusivo_compartilhavel` | 1 recurso alterna entre atividades no período | `fracao_uso ∈ (0, 1)` |
| C — `concorrente_compartilhavel` | 1 recurso cobre N atividades simultâneas | `capacidade_cobertura ≥ 2` |

**ADR-078** introduziu `OportunidadeCompartilhamento` — detecção automática pós-RCPSP
de pares de atividades sequenciais onde perpetuar um recurso mobilizado é mais barato
que desmobar e remobar. O mecanismo é inteiramente automático: o solver serializa,
o pós-processamento detecta o gap, calcula `delta_c_pot` e apresenta como oportunidade.

**ADR-091** e **pool_inference** introduziram `objetivo: minimizar_prazo |
minimizar_custo | balanceado`, derivando automaticamente o pool ótimo sem entrada
manual do planejador.

### A lacuna restante

ADR-078 cobre o caso **sequencial com gap**: A termina, B começa depois, o recurso
fica ocioso no intervalo — vale mantê-lo mobilizado?

Existe um segundo caso ainda não coberto: A e B têm **janelas CPM sobrepostas** (sem
dependência lógica entre si) e o solver as serializa **exclusivamente por escassez de
pool** (pool = 1, demanda = 2). Nesse caso, a pergunta é diferente:

> "E se eu aceitasse que A e B rodassem ao mesmo tempo com a equipe **alternando**
> entre as frentes, em vez de executar em série com uma equipe dedicada a cada?"

Esse cenário é detectável automaticamente na solução RCPSP: as duas informações
necessárias (sobreposição CPM e causa da serialização) vivem inteiramente na saída do
solver, não dependem de nenhuma entrada do planejador.

### Por que não é possível resolver isso como entrada do solver

Duas razões fundamentais impedem um modelo declarativo de "grupos de compartilhamento":

**Razão 1 — Circularidade das frações.**  
Qualquer `fracao_i` depende de quantas atividades são simultâneas no período,
que só é conhecido depois da solução. Fixar `f = 1/n` a priori exige conhecer `n`
antes de rodar — criando dependência circular entre entrada e saída do RCPSP.

**Razão 2 — Papel do recurso na produtividade não está no catálogo.**  
O impacto de compartilhar na duração depende de o recurso ser gargalo ou suporte
na `composicao_padrao_equipe` (ADR-007, `Producao.limite_producao`). Enriquecer
o catálogo de insumos com `papel_producao: gargalo | suporte` por composição seria
tecnicamente correto mas cria responsabilidade de manutenção desnecessária neste
estágio: a detecção pós-otimização pode inferir o mesmo resultado sem novos campos.

---

## Decisão

### D1 — O compartilhamento paralelo é uma oportunidade pós-RCPSP, não uma entrada

O solver RCPSP roda com o modelo exclusivo atual (pool inteiro, demanda inteira).
Nenhum campo novo em `Activity`, `rcpsp_spec` ou no catálogo de insumos.

Após a solução, um detector automático identifica **candidatos a compartilhamento
paralelo** — pares `(i, j, r)` onde:

1. `i` e `j` usam o mesmo tipo de recurso `r`
2. Não existe aresta de precedência lógica entre `i` e `j` no DAG
3. O solver os serializa (`start_j = end_i` ou `start_i = end_j`) com pool = 1
4. A folga CPM de ambas é positiva — há espaço para acomodar a duração estendida

Quando todos os quatro critérios são satisfeitos, o par é um candidato. Para cada
candidato, o sistema computa o **balanço custo × prazo** da alternativa de
compartilhamento (§D2) e apresenta como oportunidade ao planejador.

### D2 — Cálculo do balanço custo × prazo para cada candidato

Dado o par candidato `(i, j, r)` com pool atual `m = 1`:

**Duração estendida (impacto no prazo):**

O impacto depende do papel do recurso `r` na produção de `i` e `j`, inferido de
`Producao.limite_producao` (ADR-007):

```
Se limite_producao == "equipamento" e r é o equipamento principal de i (ou j):
    # r é gargalo: dividir o recurso divide a produção
    duration_compartilhada[i] = ceil(duration_nominal[i] / (1/2))
                               = 2 × duration_nominal[i]

Se r não é o equipamento principal (recurso de suporte):
    # r não limita P: compartilhar não afeta duração
    duration_compartilhada[i] = duration_nominal[i]
```

A inferência usa `composicao_padrao_equipe.equipamentos[0]` da `Producao` vinculada
à CPU do item — convenção já estabelecida em `fator_producao()`. Nenhum campo novo.

**Delta de makespan:**

```
Δ_makespan = max(0,
    makespan_compartilhado(i, j) - makespan_rcpsp_base
)
```

onde `makespan_compartilhado` é calculado substituindo as durações nominais pelas
estendidas e re-verificando folgas CPM — sem re-executar o solver completo.

**Delta de custo direto de frota:**

Com compartilhamento, 1 unidade de `r` cobre as duas atividades em vez de 2.
A economia é o custo de mobilização + aluguel + manutenção de 1 unidade poupada:

```
Δ_custo_frota = custo_contrato(r) × semanas_cobertura_conjunta
```

onde `custo_contrato(r)` é obtido de `resource_costs` no `rcpsp_spec` (mesmo
campo usado por ADR-078 para `delta_c_pot`).

**Custo de indiretos pelo prazo adicional (quando r é gargalo):**

```
Δ_indiretos = custo_indireto_semana × Δ_makespan
```

**Balanço líquido:**

```
delta_liquido = Δ_custo_frota - Δ_indiretos
```

`delta_liquido > 0` → compartilhar é financeiramente vantajoso.  
`delta_liquido ≤ 0` → compartilhar aumenta custo total (indiretos superam economia de frota).

### D3 — Modelo de dados da oportunidade

Estender `OportunidadeCompartilhamento` (ADR-078) com o subtipo paralelo, ou criar
uma classe análoga no canonical:

```python
class OportunidadeCompartilhamentoParalelo(BaseModel):
    """Par de atividades paralelizáveis via compartilhamento de recurso — ADR-133.

    Detectado automaticamente pós-RCPSP. Nenhuma entrada do usuário necessária.
    """
    atividade_i: str           # item_id
    atividade_j: str           # item_id
    tipo_recurso_id: str       # tipo compartilhado
    recurso_e_gargalo: bool    # True = compartilhar estende duração
    delta_makespan_semanas: int
    delta_custo_frota: float   # R$ economizado em frota (positivo = economia)
    delta_indiretos: float     # R$ adicional em indiretos por prazo (positivo = custo)
    delta_liquido: float       # delta_custo_frota - delta_indiretos
    economicamente_viavel: bool  # delta_liquido > 0
```

O `RelatorioOportunidades` (ADR-078) passa a agregar ambos os subtipos:

```python
class RelatorioOportunidades(BaseModel):
    # ...campos existentes...
    oportunidades_paralelo: list[OportunidadeCompartilhamentoParalelo] = []
```

### D4 — Atribuição de custo no cubo pool (pós-decisão do planejador)

O planejador decide aceitar ou rejeitar cada oportunidade. Se aceita, o custo do
recurso `r` no período de sobreposição é particionado via Classe C existente
(`atribuir_custo_insumo` em `resource_pool_validator.py`):

```python
# Já implementado — nenhuma mudança necessária
custo_atribuido_i = atribuir_custo_insumo(
    insumo=r,
    n_atividades_simultaneas=2,   # i e j compartilham
    semanas_ativo=semanas_overlap,
)
# = custo_base / 2  (Classe C: concorrente_compartilhavel)
```

O campo `classe_compartilhamento` do insumo não precisa ser alterado para que a
atribuição funcione — o `n_atividades_simultaneas` é passado em tempo de execução
com base na decisão do planejador, não pré-fixado no catálogo.

### D5 — Nenhuma alteração no solver, no catálogo ou no rcpsp_spec

| Componente | Mudança |
|---|---|
| `Activity` / `ActivityDAG` | Nenhuma |
| `cpsat_scheduler.py` | Nenhuma |
| Catálogo `Insumo` / `Producao` | Nenhuma |
| `rcpsp_spec` | Nenhuma |
| `OportunidadeCompartilhamentoParalelo` | Nova classe no canonical |
| `RelatorioOportunidades` | Novo campo `oportunidades_paralelo` |
| Detector pós-RCPSP | Nova função em skill-05 ou serviço analítico |

---

## Alternativas Consideradas e Rejeitadas

### Alt-1 — Grupos de compartilhamento declarados pelo usuário no rcpsp_spec
O planejador declara `sharing_groups` com `fracao_minima` por atividade membro.
**Rejeitada:** cria circularidade (fração depende de `n` que só existe pós-solver),
exige enriquecimento do catálogo de insumos com `papel_producao` (manutenção
permanente), e transfere para o usuário uma decisão que o sistema pode inferir
automaticamente com informação equivalente. Toda a informação necessária existe
na saída do RCPSP e em `Producao.limite_producao`.

### Alt-2 — `fracao_uso = 1/n` universal no catálogo
Adotar `f = 1/n` como regra geral elimina a circularidade se `n` for conhecido.
**Rejeitada:** para recursos gargalo, `f = 1/2` dobra a duração, resultando
em prazo idêntico à execução serial — a economia de frota é parcialmente cancelada
pelo aumento de custos indiretos de permanência. O efeito líquido depende do
balanço específico do projeto, que não pode ser resolvido com uma regra universal
no catálogo.

### Alt-3 — Modificar CP-SAT com variáveis de alocação fracionada (FRCPSP)
Introduzir `FracaoEfetiva[i][r][t]` como variável de decisão inteira escalada (×100).
**Rejeitada:** transforma o RCPSP em FRCPSP — NP-Hard de ordem superior. O
timeout de 60s torna-se insuficiente para instâncias com `|A| > 30` e múltiplos
recursos compartilhados. O mesmo resultado analítico é obtido no pós-processamento
sem penalizar o solver principal.

---

## Consequências

### Positivas
- **Zero overhead para o usuário:** nenhum campo novo para preencher em spec ou catálogo.
- **Solver inalterado:** `cpsat_scheduler.py` não sofre modificação; performance
  e determinismo preservados.
- **Consistência com ADR-078:** o mecanismo de oportunidade paralela é análogo ao
  de oportunidade sequencial já existente — mesma UX, mesma estrutura de dados.
- **Catálogo limpo:** `Insumo` e `Producao` não recebem campos de compartilhamento;
  responsabilidade de manutenção não cresce.
- **Auditável:** a decisão de aceitar o compartilhamento fica registrada no canonical
  via `OportunidadeCompartilhamentoParalelo.economicamente_viavel`, com todos os
  deltas calculados e rastreáveis.

### Negativas / Riscos
- **Aproximação do balanço:** `delta_makespan` é estimado sem re-executar o solver;
  interações com outras restrições de recursos podem tornar a estimativa conservadora.
  Mitigação: re-executar RCPSP com duração estendida apenas para oportunidades
  marcadas como aceitas pelo planejador.
- **`composicao_padrao_equipe.equipamentos[0]` como gargalo:** a inferência do
  papel do recurso usa posição na lista, não semântica declarada. Se a composição
  for montada fora de ordem, o detector pode classificar incorretamente.
  Mitigação: `VAL-OPP-PARALELO-01` alerta quando `equipamentos` tem mais de um
  item com `num_unidades > 0` de mesmo tipo (composição ambígua).

### Trabalho necessário
| Fase | Escopo | Complexidade |
|---|---|---|
| **Fase 1** | `OportunidadeCompartilhamentoParalelo` no canonical; campo em `RelatorioOportunidades` | Baixa |
| **Fase 2** | Detector pós-RCPSP: critérios 1–4 de §D1, cálculo de `delta_liquido` | Média |
| **Fase 3** | Integração com skill-05: acionar detector após solução RCPSP, agregar ao `RelatorioOportunidades` | Média |
| **Fase 4** | Apresentação ao planejador: lista de oportunidades com balanço custo × prazo | Baixa |
| **Fase 5** | Custo pós-decisão: particionamento via `atribuir_custo_insumo` quando aceita | Baixa |

---

## Referências

- ADR-007 — `Producao.limite_producao` e `fator_producao()` — inferência do papel do recurso
- ADR-016 — `ClasseCompartilhamento` (A/B/C) — atribuição de custo pós-decisão (Classe C)
- ADR-075 — RCPSP com CP-SAT; saída usada como entrada do detector
- ADR-078 — `OportunidadeCompartilhamento` sequencial — padrão análogo ao desta ADR
- ADR-081 — Pool de recursos e thresholds de precedência
- ADR-086 — Cubo pool instancial: `custo_inst_*` particionado pós-decisão
- ADR-091 — `pool_inference`: `objetivo` como única entrada de negócio do planejador
