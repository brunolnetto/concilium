# NEP-036: Campo de Eficiência Matricial E ∈ ℝ^{I×T} e Decomposição Log-Linear

**Status:** Implementado ✅ _(auditado 2026-06-08)_  
**Prioridade:** 🟠 Alto  
**Área:** Arquitetura e Skills  
**Tipo:** Feature + Dados  
**Esforço:** XL  
**Identificado em:** 2026-06-01  
**Depende de:** NEP-035

> **Nota de auditoria (2026-06-08):** `eficiencia_field_builder.py` com `CampoEficiencia`
> implementado em `src/concilium/domain/services/`. Visualizações `eta_obra.py`,
> `waterfall_causal.py`, `pareto_perdas.py`, `heatmap_top_n.py` presentes.

> **Reinterpretação (ADR-124, 2026-06-28):** o `CampoEficiencia` foi reformulado para
> separar **planejamento** de **controle**. As superfícies de planejamento passam a ser
> `Eta_clima` (η_clima), `Delta` (δ) e `Eta_plan` (η_plan = η_clima · δ, antigo `P_r`).
> As superfícies de controle `S` (η_s), `W` (η_w) e `E` (η_total) são `None` no modo
> planejamento — populadas apenas quando houver dados de execução real. O waterfall de
> nível 2 mostra η_clima e δ (sem η_s/η_w/ε_cross) e o heatmap de nível 4 aceita
> `fator="Eta_clima"` e `fator="Delta"`.

---

## Contexto

A NEP-035 materializa os três componentes causais `η_s`, `η_p`, `η_w` em cada
célula semanal. Com isso, o canônico de um projeto contém implicitamente a
estrutura

```
E[i, j] = η_s_ij · η_p_j · η_w_ij     ∈ ℝ^{I×T}
```

onde `I` = número de atividades e `T` = número de semanas da obra.

O campo `E` é uma **superfície de eficiência** sobre o domínio
(atividade, semana). Cada fator `S`, `P_r`, `W` gera uma superfície
independente:

```
S[i,j]   = η_s_j              (alocação — varia por semana, igual para todas as atividades)
P_r[i,j] = η_p_j              (praticabilidade — idem)
W[i,j]   = η_w_ij             (gestão — varia por atividade e semana)
E = S ⊙ P_r ⊙ W               (Hadamard element-wise product)
```

A representação matricial permite:
- Agregações exatas por capacidade (sem acoplamento de fatores).
- Transformação logarítmica `log E = log S + log P_r + log W` que lineariza a
  decomposição e abre caminho para regressão, ANOVA e modelos de efeitos mistos.
- Série temporal `η_obra(t)` como indicador executivo de nível 1.
- Visualizações não-heatmap: waterfall causal, Pareto de perdas, sparklines.

---

## Problemas

### P1 — Não há estrutura de dados para o campo de eficiência

Os dados de eficiência existem nas células `DistribuicaoSemanal` do cronograma,
mas não há nenhuma estrutura que os consolide como campo `E[i, j]`. Qualquer
análise cross-atividade requer iteração manual sobre o canônico.

### P2 — η_obra (eficiência global da obra) não é computada

Não existe métrica de nível 1: `η_obra(t) = Σ_i Q_i(t) / Σ_i Q_max_i`. Sem
ela, a série temporal de desempenho da obra fica invisível.

### P3 — Médias simples distorcem o diagnóstico global

Quando múltiplas atividades são agregadas sem ponderação por `q_max`, o
diagnóstico global mistura atividades de alto volume (dominantes na obra) com
atividades menores de forma equânime. A Seção 5 do modelo formal demonstra:

```
η_{agregado} ≠ η̄_s · η̄_p · η̄_w   (os fatores acoplam via pesos α_j)
```

Só a decomposição no **nível semanal** é exata. No agregado, o termo cruzado
`Cov(n, p) / n̄` deve ser reportado.

### P4 — Heatmaps completos são ilegíveis em escala

Para 200 atividades × 80 semanas = 16 000 células (× 3 fatores = 48 000). A
abordagem de visualização deve preservar a decomposição semanal para diagnóstico
e expor apenas agregados para o executivo.

---

## Objetivo

1. Criar `CampoEficiencia` (modelo de domínio) que materializa `E`, `S`, `P_r`,
   `W` a partir do canônico.
2. Implementar `EficienciaFieldBuilder` que constrói o campo a partir de
   `canonical.cronograma.scheduled_activities`.
3. Expor `η_obra(t)` como série temporal semanal (nível 1 da hierarquia).
4. Suportar decomposição log-linear para análise estatística.
5. Definir o protocolo de 4 níveis de observabilidade como contrato de domínio.

---

## Decisão

### D1 — Modelo `CampoEficiencia`

```python
@dataclass
class CampoEficiencia:
    """Campo de eficiência E ∈ ℝ^{I×T} materializado do canônico."""

    # Sparse: {item_id: {semana_iso: valor}}
    E:    dict[str, dict[str, float]]   # η total = η_s · η_p · η_w
    S:    dict[str, dict[str, float]]   # η_s (alocação) — mesmo valor para todas as atividades
    P_r:  dict[str, dict[str, float]]   # η_p (praticabilidade)
    W:    dict[str, dict[str, float]]   # η_w (gestão)
    Q:    dict[str, dict[str, float]]   # produção realizada q_ij
    Q_max: dict[str, dict[str, float]]  # capacidade máxima q_max_ij

    def eta_obra(self) -> dict[str, float]:
        """Série temporal η_obra(t) = Σ_i Q[i,t] / Σ_i Q_max[i,t]."""

    def perda_fisica(self) -> dict[str, dict[str, float]]:
        """Perda física L[i,t] = Q_max[i,t] - Q[i,t] (em unidades de q)."""

    def pareto_perdas(self, top_n: int = 10) -> list[dict]:
        """Top N atividades por perda física total (nível 3 da hierarquia)."""

    def decomposicao_causal(self) -> dict[str, float]:
        """Contribuição ponderada de cada fator para a eficiência global."""

    def log_linear(self) -> dict[str, dict[str, float]]:
        """log(E), log(S), log(P_r), log(W) para análise aditiva."""
```

### D2 — `EficienciaFieldBuilder`

```python
class EficienciaFieldBuilder:
    def build(self, canonical: CanonicalModel) -> CampoEficiencia:
        """Constrói o campo a partir de canonical.cronograma.scheduled_activities.
        
        Requer que as células tenham sido populadas pela NEP-035
        (campos eta_s, eta_p, eta_w, q_max_celula).
        """
```

Localização: `src/concilium/domain/services/eficiencia_field_builder.py`.

### D3 — Protocolo de 4 Níveis de Observabilidade

O contrato de domínio define o que cada nível expõe e para quem:

```
Nível 1 (Global): η_obra(t) — série temporal semanal
    → CampoEficiencia.eta_obra() → dict[semana_iso, float]
    → Público: Diretoria, Planejamento executivo

Nível 2 (Causal): waterfall η_s / η_p / η_w global
    → CampoEficiencia.decomposicao_causal() → dict com η_s_global, η_p_global, η_w_global, eps_cross
    → Aviso quando |eps_cross| > 5% (acoplamento não desprezível)

Nível 3 (Atividades críticas): Pareto de perdas físicas
    → CampoEficiencia.pareto_perdas(top_n) → lista ordenada por L_i = Σ_t L_ij
    → Permite drill-down: "eap-1_7 causou 3.500 m³ de perda"

Nível 4 (Fatorial): (η_s, η_p, η_w) por atividade+semana
    → CampoEficiencia.E, .S, .P_r, .W diretamente
    → Uso sob demanda por engenharia
```

### D4 — Decomposição Log-Linear

```
log(E_ij) = log(η_s_j) + log(η_p_j) + log(η_w_ij)
           = s_j + p_j + w_ij
```

Propriedade analítica: `log E` é aditivo, permitindo
- ANOVA de duas vias (atividade × semana)
- Modelos de efeitos fixos: `e_ij = μ + α_i + β_j + ε_ij`
- Estimativa de impactos marginais: `∂E/∂S = E · (1/S)` (elasticidade)

Implementado como método `log_linear()` sem dependência de numpy (dict puro).

### D5 — Visualizações dos 4 Níveis

| Nível | Chart | Arquivo |
|---|---|---|
| 1 | Linha série temporal η_obra(t) com banda de intervalo [η_min, η_max] semanal | `visualizations/eficiencia/eta_obra.py` |
| 2 | Waterfall causal: barra de perda total, decomposta em S/P_r/W + eps_cross | `visualizations/eficiencia/waterfall_causal.py` |
| 3 | Bar horizontal Pareto de perda física (m³/R$) | `visualizations/eficiencia/pareto_perdas.py` |
| 4 | Heatmap **restrito** ao Top-N atividades × semanas ativas (não grid completo) | `visualizations/eficiencia/heatmap_top_n.py` |

---

## Escopo

### Incluído

1. `CampoEficiencia` dataclass (D1).
2. `EficienciaFieldBuilder` (D2).
3. `η_obra(t)` série temporal (D3 nível 1).
4. `decomposicao_causal()` com `eps_cross` (D3 nível 2).
5. `pareto_perdas()` (D3 nível 3).
6. `log_linear()` (D4).
7. Visualizações dos 4 níveis (D5).
8. Testes unitários do builder e dos métodos analíticos.

### Excluído

1. Modelos estatísticos de efeitos mistos (requer numpy/statsmodels).
2. Previsão de eficiência futura (`η(t+k)`).
3. Integração com MCP como tool de análise.

---

## Plano de Implementação

### Fase 1 — Modelo e builder

1. Criar `CampoEficiencia` e `EficienciaFieldBuilder` em
   `src/concilium/domain/services/eficiencia_field_builder.py`.
2. Implementar `eta_obra()`, `perda_fisica()`, `pareto_perdas()`.
3. Implementar `decomposicao_causal()` com ponderação por `q_max`.
4. Implementar `log_linear()`.
5. Testes em `tests/unit/test_nep036_campo_eficiencia.py`.

### Fase 2 — Visualizações

1. Linha `eta_obra(t)` com banda de variância.
2. Waterfall causal dos 3 fatores.
3. Pareto de perdas (físico em m³, custo via PU_catalogo × perda).
4. Heatmap Top-N restrito.
5. Registrar na skill-09 (artefatos do relatório).

### Fase 3 — Integração no pipeline

1. Computar `CampoEficiencia` na skill-15 (relatório executivo).
2. Expor `η_obra` e decomposição causal no `resumo_executivo.md`.
3. Incluir Pareto de perdas físicas no relatório padrão.

---

## Critério de Aceite

1. `EficienciaFieldBuilder.build(canonical)` retorna `CampoEficiencia` válido
   para o canônico AGIS.
2. `Σ_i Σ_j Q[i,j] ≈ Σ_i Q_i` (soma das células = produção total por atividade).
3. `η_obra(t)` é série temporal com `T` entradas, valores em (0, 1].
4. `pareto_perdas()` retorna lista ordenada por `L_i` decrescente.
5. `|exp(log_linear()[E][i][j]) − E[i][j]| < 1e-9` (roundtrip log-exp exato).
6. Heatmap restrito ao Top-10 (não ao grid completo).
7. Benchmark AGIS produz `η_obra` semanal sem exception.

---

## Riscos

1. `q_max_celula = 0` para atividades sem produção → log(0) indefinido em
   `log_linear`. Mitigação: substituir por `float('nan')` e excluir do
   aggregate.
2. Atividades com `distribuicao_semanal` ausente (canônicos antigos).
   Mitigação: skip silencioso no builder.
3. Visualização do heatmap Top-N pode enganar (parece completo).
   Mitigação: título explícito "Top-N atividades por perda".

---

## Notas Técnicas

- `src/concilium/domain/services/eficiencia_field_builder.py` (novo)
- `src/concilium/application/runtime/deliverables/visualizations/eficiencia/` (novo)
- `src/concilium/application/skills/manifests/15-relatorio-executivo/skill.py`
- `src/concilium/application/runtime/deliverables/reports/executive_summary.py`
- Referência matemática: Seções 1–24 do modelo de eficiência (arquivo de projeto)

---

## Resultado Esperado

Ao final da NEP-036, o canônico de qualquer projeto expõe um campo de
eficiência `E[i, j]` com decomposição causal exata, série temporal global
`η_obra(t)` para o executivo, Pareto de perdas físicas para planejamento e
suporte a análise log-linear para engenharia. A hierarquia de 4 níveis é
respeitada: diagnóstico exato no nível semanal; agregados comportamentais no
nível global, com termo cruzado reportado quando relevante.
