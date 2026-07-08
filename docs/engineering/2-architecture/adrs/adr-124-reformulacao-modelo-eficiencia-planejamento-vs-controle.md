# ADR-124 — Reformulação do Modelo de Eficiência: Separação entre Fase de Planejamento e Controle

**Status:** ✅ Implementado  
**Data:** 2026-06-28  
**Contexto:** MendesLobo Construtora — Concilium  
**Dependências:** NEP-035, NEP-036, ADR-068, ADR-046

---

## Contexto

### Modelo atual

A NEP-035 materializou a decomposição `η = η_s · η_p · η_w` como três fatores
ortogonais de eficiência semanal por atividade:

| Componente | Fórmula | Definição original |
|---|---|---|
| `η_s` | `n_j / n_max` | Fração da força máxima planejada efetivamente alocada |
| `η_p` | `p_j^clima · p_j^cal` | Praticabilidade = clima × calendário (δ) |
| `η_w` | `m_ij / M_max` | Eficiência de gestão — utilização relativa ao melhor observável |

A NEP-036 materializou o campo matricial `E ∈ ℝ^{I×T}` com hierarquia de
observabilidade em 4 níveis, e ambas as NEPs foram implementadas e auditadas em
2026-06-08.

### Dois problemas estruturais identificados

#### P1 — η_s perdeu seu significado semântico com composição de pool sob demanda

A semântica original de `η_s` pressupõe um `n_max` **externo** ao modelo —
um plano fixo de equipes definido pelo projetista, contra o qual a alocação
real é medida. Com a adoção da composição de pool sob demanda via RCPSP
(ADR-046), `n_max` é derivado do próprio cronograma gerado:

```
n_max = max(n_j)  ∀j ∈ janela_atividade   [pico do RCPSP]
```

Consequências:
- Na semana de pico: `η_s = 1.0` por construção — não há "ineficiência"
- Nas semanas de rampa: `η_s < 1.0` reflete o **perfil de rampa planejado**, não subalocação real

`η_s` deixou de medir ineficiência e passou a descrever a forma temporal da
atividade — um dado determinístico do próprio plano, sem conteúdo diagnóstico
no planejamento.

#### P2 — η_w é uma métrica de controle, não de planejamento

`η_w` mede a razão entre produção realizada e capacidade disponível. No
planejamento, essa razão é **definida** como 1.0 (ou próxima disso via
clamping de remanescente na última semana). A variável só adquire conteúdo
informativo quando há dados de execução real para comparar com o plano —
fase de controle, ainda não implementada.

#### P3 — δ (calendário) está invisível dentro de η_p

`η_p = p_j^clima · p_j^cal` dobra dois fatores com semânticas distintas
em um único componente:

| Fator | Tipo | Controlabilidade |
|---|---|---|
| `p_j^clima` (η_clima) | Estocástico — série histórica de chuvas | Não controlável |
| `p_j^cal` (δ) | Determinístico — regime de trabalho, feriados, recessos | Controlável pelo gestor |

A ADR-068 já os implementa separadamente (`fator_chuva` e `fator_calendario`),
mas a decomposição de eficiência os apresenta fundidos, ocultando a alavanca
de decisão que δ representa.

---

## Decisão

### D1 — Definir dois modelos de eficiência com ciclos de vida distintos

**Modelo de Planejamento** (fase atual — aplicável):

```
η_plan_j = η_clima_j · δ_j

onde:
  η_clima_j = p_j^clima  ∈ (0, 1]   (praticabilidade climática)
  δ_j       = p_j^cal    ∈ (0, 1]   (coeficiente calendário semanal)
```

**Modelo de Controle** (fase futura — não aplicável ainda):

```
η_control_ij = η_s_j · η_plan_j · η_w_ij
```

O modelo de controle estende o de planejamento com dois fatores adicionais
que só têm conteúdo informativo com dados de execução real.

### D2 — Expor δ como campo first-class no CampoEficiencia

`CampoEficiencia` (NEP-036) passa a ter superfícies separadas para clima e calendário:

```python
@dataclass
class CampoEficiencia:
    # Planejamento (sempre disponíveis)
    Eta_clima: dict[str, dict[str, float]]  # η_clima_j por atividade+semana
    Delta:     dict[str, dict[str, float]]  # δ_j (fator_calendario) por atividade+semana
    Eta_plan:  dict[str, dict[str, float]]  # η_plan = η_clima · δ  (antigo P_r)

    # Controle (None enquanto não há execução real)
    S:  dict[str, dict[str, float]] | None  # η_s — ramp profile vs. n_max
    W:  dict[str, dict[str, float]] | None  # η_w — gestão residual
    E:  dict[str, dict[str, float]] | None  # η total (só em controle)

    # Produção (planejamento)
    Q:     dict[str, dict[str, float]]  # produção planejada q_ij
    Q_max: dict[str, dict[str, float]]  # capacidade teórica q_max_ij
```

### D3 — Redefinir η_obra para o contexto de planejamento

A série temporal de eficiência global passa a refletir apenas os fatores
disponíveis no planejamento:

```
η_obra_plan(j) = Σ_i (Q_ij) / Σ_i (Q_max_ij)
               = η_clima_j · δ_j          [quando η_s = η_w = 1 por construção]
```

O método `eta_obra()` mantém a assinatura mas retorna `η_plan` como fator
agregado.

### D4 — Redefinir a hierarquia de observabilidade para planejamento

| Nível | Métrica | Audiência | Período | Notas |
|---|---|---|---|---|
| 1 | `η_obra(j) = η_clima · δ` global | Diretoria | Semanal | Simplificado vs. NEP-036 |
| 2 | Decomposição η_clima / δ com séries separadas | Gestão | Mensal | Substitui waterfall η_s/η_p/η_w |
| 3 | Pareto de perda física por atividade (`q_max − q`) | Planejamento | Sprint | Inalterado |
| 4 | Heatmap η_clima e δ separados — top-N atividades | Engenharia | Sob demanda | δ destaca semanas com feriado/recesso |

### D5 — Marcar η_s e η_w como "controle" na documentação e no código

`DistribuicaoSemanal` mantém os campos `eta_s` e `eta_w` (retrocompatibilidade),
mas com docstring explícita:

```python
eta_s: float = 0.0   # CONTROLE: n_j/n_max — sem significado diagnóstico no planejamento
eta_w: float = 0.0   # CONTROLE: produção real / capacidade — requer dados de execução
```

O builder `EficienciaFieldBuilder` preenche `S=None` e `W=None` até que a
fase de controle seja implementada.

---

## Alternativas Rejeitadas

| ID | Alternativa | Motivo |
|---|---|---|
| A1 | Manter η_s e η_w como antes | η_s é trivialmente determinado pelo RCPSP; η_w não tem dado de entrada no planejamento. Seriam ruído, não informação. |
| A2 | Colapsar η_s em η_w | Os dois têm semânticas distintas no controle (alocação vs. gestão residual). Colapsar agora dificulta a separação futura. |
| A3 | Remover η_s e η_w do modelo permanentemente | O modelo de controle vai precisar deles. Manter com marcação explícita preserva o investimento da NEP-035. |
| A4 | Manter η_p = η_clima · δ fundidos | δ é uma alavanca de decisão (gestores podem renegociar feriados, regime de revezamento). Tornar invisível reduz a utilidade analítica. |

---

## Consequências

### Positivas

| Efeito | Descrição |
|---|---|
| Clareza de ciclo de vida | Planejamento e controle têm modelos explicitamente distintos; sem métricas vazias no planejamento |
| δ como alavanca visível | Gestores podem comparar semanas com δ = 0.85 (feriado) vs. δ = 1.0 e quantificar impacto no prazo |
| Retrocompatibilidade | `DistribuicaoSemanal.eta_s` e `eta_w` permanecem; NEP-035 não é quebrada, apenas reinterpretada |
| Extensibilidade | Quando fase de controle vier, basta popular `S`, `W`, `E` no builder — estrutura já está lá |

### Negativas / Riscos

| Risco | Mitigação |
|---|---|
| Testes existentes da NEP-035/036 esperam `S` e `W` populados | Atualizar asserções para aceitar `None` no modo planejamento; adicionar fixture de controle com dados simulados |
| ε_cross da decomposição causal perde sentido no nível 2 (só 2 fatores) | Remover o aviso de acoplamento cruzado do waterfall de planejamento; preservar para o futuro waterfall de controle |
| Documentação do produto ainda referencia η_s, η_p, η_w | Atualizar glossário e relatório executivo para nova nomenclatura |

---

## Plano de Implementação

| Fase | Entregas | Status |
|---|---|---|
| F1 — Modelo | Renomear `P_r → Eta_plan`; adicionar `Eta_clima` e `Delta` em `CampoEficiencia`; `S=None`, `W=None`, `E=None` no builder | ✅ Concluído |
| F2 — Visualizações | Atualizar `waterfall_causal.py` para mostrar η_clima / δ em vez de η_s / η_p / η_w; atualizar `heatmap_top_n.py` para aceitar `"Eta_clima"` e `"Delta"` como fatores | ✅ Concluído |
| F3 — Testes | Corrigir `test_nep036_campo_eficiencia.py`; adicionar cenário planning-mode vs. control-mode | ✅ Concluído |
| F4 — Documentação | Atualizar NEP-035, NEP-036, `formalizacao_teorica.md` e glossário do relatório executivo | ✅ Concluído |

---

## Definition of Done

### Fase 1
- [x] `CampoEficiencia` tem `Eta_clima`, `Delta`, `Eta_plan` como superfícies separadas
- [x] `S`, `W`, `E` são `None` no modo planejamento (builder não os popula)
- [x] `eta_obra()` retorna `η_plan = η_clima · δ` agregado por capacidade

### Fase 2
- [x] Waterfall nível 2 mostra duas barras: η_clima e δ (sem η_s, η_w, ε_cross)
- [x] Heatmap aceita `fator="Eta_clima"` e `fator="Delta"` como opções válidas

### Fase 3
- [x] Todos os testes da NEP-036 passam com nova estrutura
- [x] Teste explícito documenta: "η_s e η_w são None no planejamento"

### Fase 4
- [x] `formalizacao_teorica.md` seção 1 atualizada: `H_j = h · d_j · η_clima_j · δ_j`
- [x] Glossário do relatório executivo menciona fase de planejamento vs. controle

---

## Nota de Implementação (2026-07-08)

Implementado no branch `feat/adr-124-modelo-eficiencia`.

- O modelo (`CampoEficiencia`, `EficienciaFieldBuilder`) e as visualizações
  (`eta_obra.py`, `waterfall_causal.py`, `heatmap_top_n.py`) já expunham as
  superfícies `Eta_clima` / `Delta` / `Eta_plan` e mantinham `S`/`W`/`E = None`
  no planejamento. Esta entrega completou os itens remanescentes:
  - **D2/heatmap:** removido o alias legado `"P_r"` do mapa de fatores
    (`Eta_plan` é o nome canônico; η_plan = η_clima · δ). Nenhum chamador usava
    `fator="P_r"`.
  - **D5:** `DistribuicaoSemanal.eta_s` / `eta_w` marcados explicitamente como
    CONTROLE via docstring e comentários. **Decisão de retrocompatibilidade:**
    o `default` foi mantido em `1.0` (e não `0.0` como no exemplo ilustrativo da
    D5) para não introduzir regressão silenciosa em cronogramas já materializados
    — a decisão-chave da D5 é a *marcação* dos campos como controle, não o valor
    default.
  - **Testes:** `tests/unit/test_adr124_planejamento_vs_controle.py` trava
    η_plan = η_clima · δ, a equivalência de regressão `η_plan == P_r/η_p legado`
    e `S`/`W`/`E = None` no planejamento; heatmap ganhou casos para
    `fator="Eta_clima"` e `fator="Delta"`.
  - **Docs:** `formalizacao_teorica.md` §1, NEP-035, NEP-036 e o glossário
    metodológico do relatório executivo atualizados.

> **Pré-requisito do ADR-125** (Hierarquia de Custo C_prod/C_pool/Contrato):
> os nomes canônicos para consumo do próximo agente são `CampoEficiencia.Eta_plan`
> (η_plan de planejamento), `CampoEficiencia.Eta_clima`, `CampoEficiencia.Delta`,
> e `CampoEficiencia.S`/`W`/`E` (= None até a fase de controle). `eta_obra()`
> retorna η_plan agregado por capacidade.

---

## Relacionados

- NEP-035 — Decomposição causal η_s × η_p × η_w (implementado; reinterpretado por este ADR)
- NEP-036 — Campo matricial E ∈ ℝ^{I×T} (implementado; estrutura estendida por este ADR)
- ADR-068 — Calendário Operacional: `fator_calendario` = δ já implementado
- ADR-046 — RCPSP: composição de pool sob demanda (motivação de P1)
