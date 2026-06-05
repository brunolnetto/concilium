# ADR-061: Inversão do Cálculo de PE e Validação por Backtracking

**Status:** Implementado  
**Data:** 2026-05-17  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-060 (Diagnóstico PE), ADR-054 (WMP), ADR-023 (BDI), ADR-039 (Bridge)

---

## 1. Contexto

ADR-060 define como calcular o gap do Ponto de Equilíbrio e decompô-lo em fatores causais ($F_1$, $F_\eta$, $F_\text{ind}$, $\varepsilon_\text{cross}$). O passo seguinte é **inverter** esse cálculo: dado um alvo (PE\_gap = 0 ou qualquer outro), encontrar os parâmetros que o atingem.

Esta inversão cumpre dois papéis distintos:

1. **Prático:** diz ao planejador *qual parâmetro ajustar e em quanto* para fechar o gap
2. **Validação:** se $\text{forward}(\theta^*) \neq \text{alvo}$, há inconsistência no modelo que deve ser corrigida antes de qualquer implementação

---

## 2. Formulação formal

### 2.1 O problema direto

$$\text{PE\_gap}(\theta) = \underbrace{C_\text{cat}(\theta)\cdot(1+\text{BDI}(\theta))\cdot Q}_{PV(\theta)} - \underbrace{C_\text{real}(\theta)}_{C(\theta)}$$

onde $\theta = (P, n(t), p(t), L, t_0^\text{ramp})$ é o vetor de parâmetros controláveis.

### 2.2 O problema inverso

$$\theta^* = \text{argmin}_\theta \|\text{PE\_gap}(\theta)\|^2 \quad \text{s.t. restrições operacionais}$$

O problema é **subdeterminado** (um escalar = 0, múltiplas variáveis livres). Existem infinitas soluções — o objetivo é enumerar os **pontos extremos** (cada parâmetro ajustado sozinho) e a **fronteira de Pareto** das combinações ótimas.

### 2.3 A invariante de roundtrip

Para qualquer inverso $\text{inv}_i$:

$$\left|\text{forward}\left(\text{inv}_i\left(\text{PE\_gap}_\text{alvo}\right)\right) - \text{PE\_gap}_\text{alvo}\right| < \varepsilon_\text{tol}$$

Se esta invariante for violada, o modelo tem inconsistência numérica ou estrutural — **nenhum resultado deve ser apresentado ao usuário** até a falha ser resolvida.

---

## 3. Inversas fechadas

### 3.1 Inversa de L (componente de margem do BDI)

A mais simples: $L$ é linear no preço de venda.

**Forward:**
$$PV = C_\text{cat}\cdot Q \cdot \frac{1+\text{OH}}{1-T_\text{ef}}$$
onde $\text{OH} = AC + DF + R + CR + L$.

**Inversa:**
$$\boxed{L^* = L_\text{atual} + \frac{|\text{PE\_gap}|}{C_\text{cat}\cdot Q\cdot\frac{1}{1-T_\text{ef}}}}$$

**Roundtrip:** $PV(L^*) - C_\text{real} = 0$ — exato, sem aproximação.

**Interpretação:** $L^*$ é o menor L que fecha o gap sem alterar nenhum outro parâmetro. É o "preço de se conviver com a ineficiência" — repassa ao cliente.

### 3.2 Inversa de η (eficiência efetiva da campanha)

Do gap de custo direto (ADR-060 §2.4):

$$\Delta C_\text{dir} = \frac{c_\text{fixo}}{S}\cdot\tilde{Q}\cdot\left(\frac{1}{\eta} - \frac{\lceil F\rceil}{F}\right)$$

Isolando $\eta$:

$$\boxed{\eta^* = \frac{1}{\dfrac{\lceil F\rceil}{F} + \dfrac{S\cdot\Delta C_\text{dir}^*}{c_\text{fixo}\cdot\tilde{Q}}}}$$

onde $\Delta C_\text{dir}^* = \frac{c_\text{fixo}}{S}\tilde{Q}\cdot\frac{\lceil F\rceil}{F} + \frac{\text{PE\_gap\_alvo}}{1+c_\text{diesel}/c_\text{fixo}}$ é o custo direto máximo compatível com o alvo.

**Roundtrip:** Dado $\eta^*$, verificar $N_\text{total}^* = \tilde{Q}/\eta^*$ e $C_\text{real}^* = c_\text{fixo}/S \cdot N_\text{total}^* + c_\text{diesel}/S \cdot \tilde{Q}$, então $PV - C_\text{real}^* = \text{PE\_gap\_alvo} \pm \varepsilon_\text{tol}$.

### 3.3 Inversa de P (produtividade da CPU)

$P$ afeta $\tilde{Q} = Q/(P\cdot m\cdot h)$ e, indiretamente, $T_\text{real}$ (via produção por semana). Para $\eta$ aproximadamente constante quando $P$ varia (válido quando a distribuição $n(t)/p(t)$ não muda):

$$\tilde{Q}^* = \eta^* \cdot N_\text{total}^*$$

$$\boxed{P^* = \frac{Q}{m\cdot h\cdot N_\text{total}^*\cdot\eta^*}}$$

onde $N_\text{total}^* = \tilde{Q}^* / \eta^*$.

**Roundtrip:** Substituir $P^*$ no simulador WMP e verificar $N_\text{total}(\text{WMP}, P^*) = N_\text{total}^*$ ± tolerância. Se divergir, a aproximação de η constante não vale e a iteração numérica é necessária.

**Interpretação:** $P^*$ é a produtividade mínima da CPU que equilibra o item sem mudança de BDI — é a meta de calibração do catálogo.

### 3.4 Inversa de $n_\text{max}$ (via custos indiretos)

Como demonstrado em ADR-060 §2.6, aumentar $n_\text{max}$ não muda $N_\text{total}$ diretamente — só reduz $T_\text{real}$. A inversa age sobre $F_\text{ind}$:

**Forward:**
$$F_\text{ind} = c_\text{ind/sem}\cdot(T_\text{real} - T_\text{ref})$$

$$T_\text{real} \approx T_\text{ramp} + \frac{\tilde{Q} - \tilde{Q}_\text{ramp}}{n_\text{max}\cdot\bar{p}_\text{est}}$$

**Inversa:**
$$\boxed{n_\text{max}^* = \frac{\tilde{Q} - \tilde{Q}_\text{ramp}}{\bar{p}_\text{est}\cdot(T_\text{alvo\_ind} - T_\text{ramp})}}$$

onde $T_\text{alvo\_ind} = T_\text{ref} + F_\text{ind}^\text{máx}/c_\text{ind/sem}$.

**Roundtrip:** Simular WMP com $n_\text{max}^*$ e verificar $T_\text{real} = T_\text{alvo\_ind}$ ± 1 semana (tolerância de discretização).

**Interpretação:** $n_\text{max}^*$ é o mínimo de equipes paralelas que fecha o gap de indiretos por duração.

### 3.5 Inversa de timing do ramp (cross-term)

O cross-term $\varepsilon_\text{cross} \propto \text{Cov}(n, p)$. O timing ótimo $t_0^*$ que zera o cross-term:

$$\boxed{t_0^* = \arg\min_{t_0 \in \mathcal{T}} \left|\sum_{t} p(t)\cdot n(t - t_0) - \bar{p}\cdot\sum_t n(t)\right|}$$

onde $\mathcal{T}$ é o conjunto de datas de início factíveis (considerando precedência de atividades).

**Equivalente intuitivo:** iniciar o ramp-up na data em que a praticabilidade média durante o ramp é igual à praticabilidade média do restante do projeto.

**Roundtrip:** Calcular $\text{Cov}(n(\cdot - t_0^*), p)$ e verificar $|\varepsilon_\text{cross}^*| < \varepsilon_\text{tol}$.

---

## 4. Algoritmo de backtracking

O backtracking percorre a cadeia de causalidade ao contrário:

```
Entrada: PE_gap_alvo, canonical (run atual), prioridade_parametro

Passo 1 — Decompor o gap
    (F1, F_η, F_ind, ε_cross) = DiagnosticoPEBuilder.build(canonical)

Passo 2 — Para cada parâmetro, computar o inverso
    L*    = inv_L(PE_gap_alvo, F_η, F_ind, ε_cross)
    η*    = inv_eta(PE_gap_alvo, F_ind, ε_cross)
    P*    = inv_P(η*, N_total_atual)
    n*    = inv_n_max(F_ind_alvo=0, T_ramp)
    t0*   = inv_timing(ε_cross_alvo=0, praticabilidade)

Passo 3 — Validação roundtrip para cada solução
    para θ_i em {L*, η*(P*), η*(n*), η*(t0*)}:
        PE_gap_recalc = forward_analitico(θ_i, canonical)
        assert |PE_gap_recalc - PE_gap_alvo| < ε_tol
        se falhar: emitir VAL-INV-ROUNDTRIP-FAIL(θ_i)

Passo 4 — Enumerar soluções válidas
    retornar SolucoesInversas(
        l_star, p_star, n_max_star, t0_star,
        status_roundtrip_por_solucao
    )
```

### 4.1 Tolerância de roundtrip

$$\varepsilon_\text{tol} = \max\left(R\$\,10{,}00,\; 0.01\% \cdot |\text{PE\_gap}|\right)$$

Valores menores que R\$10 são ruído numérico. A tolerância relativa de 0,01% captura erros de discretização de semanas.

### 4.2 Hierarquia de confiança das soluções

| Solução | Tipo de inversa | Roundtrip | Confiança |
|---------|----------------|-----------|-----------|
| $L^*$ | Analítica exata | Sempre válida | ★★★★★ |
| $\eta^*$ (via $P^*$) | Analítica com aprox. | Válida se $\eta$ constante | ★★★★ |
| $t_0^*$ (timing) | Numérica (otimização 1D) | Válida após simulação | ★★★ |
| $n_\text{max}^*$ (via $F_\text{ind}$) | Analítica com aprox. | Válida se $p$ estacionária | ★★★ |
| $\eta^*$ (via múltiplos params.) | Fronteira de Pareto | Iterativo | ★★ |

---

## 5. Fronteira de Pareto — trade-offs entre soluções

Para cada item em déficit, há uma **fronteira de Pareto** no espaço ($\Delta P$, $\Delta L$, $\Delta n_\text{max}$, $\Delta t_0$):

```
Eixo X: impacto no preço de venda ao cliente (Δ% — repasse de custo)
Eixo Y: impacto na produtividade necessária (ΔP/P — esforço de calibração)
Eixo Z: impacto na duração (Δn_max — mobilização de recursos)

Fronteira de Pareto: soluções onde nenhum eixo pode ser melhorado sem piorar outro
```

**Soluções extremas:**
- **A — só L:** fecha o gap via preço. Zero esforço operacional, máximo repasse ao cliente.
- **B — só P:** fecha via produtividade. Zero repasse, requer calibração ou upgrade de CPU.
- **C — só n_max:** fecha via compressão de prazo. Zero repasse, requer mais recursos simultâneos.
- **D — só timing:** fecha via sincronização. Zero custo, requer flexibilidade de cronograma.

---

## 6. Modelo de dados

```python
@dataclass(frozen=True)
class SolucaoInversa:
    parametro: str           # "L" | "P" | "n_max" | "t0_ramp" | "combinada"
    descricao: str
    valor_atual: float
    valor_requerido: float
    delta_pct: float         # variação percentual necessária
    pe_gap_recalculado: float  # resultado do roundtrip
    roundtrip_valido: bool
    erro_roundtrip: float    # |pe_gap_recalc - alvo|
    impacto_preco_pct: float   # repasse ao cliente
    impacto_produtividade_pct: float
    impacto_recursos_pct: float
    confianca: int           # 1–5 estrelas

@dataclass(frozen=True)
class BacktrackingPEItem:
    atividade_id: str
    pe_gap_atual: float
    pe_gap_alvo: float
    solucoes: tuple[SolucaoInversa, ...]   # ordenadas por confiança desc
    solucao_recomendada: SolucaoInversa    # menor Σ impactos
    pareto_dominante: tuple[SolucaoInversa, ...]  # Pareto front

@dataclass(frozen=True)
class BacktrackingPERelatorio:
    projeto_id: str
    gerado_em: str
    alvo_pe_gap: float        # 0.0 por padrão
    itens: tuple[BacktrackingPEItem, ...]
    roundtrips_falharam: tuple[str, ...]  # item_ids com VAL-INV-ROUNDTRIP-FAIL
    consistencia_global: bool # True se todos os roundtrips passaram
```

---

## 7. Propostas de UI

### 7.1 Painel "🎯 Recalibração Inversa" no Overview

Exibido apenas quando há itens em déficit:

```
╔════════════════════════════════════════════════════════════════════╗
║  🎯 RECALIBRAÇÃO INVERSA — Caminhos para PE = 0                   ║
║  3 itens em déficit | Gap total: R$12.4k                          ║
╠════════════════════════════════════════════════════════════════════╣
║  Item: eap-03 (Escavação 2ª cat.)  Gap: R$7.4k                   ║
║                                                                    ║
║  SOLUÇÕES DISPONÍVEIS                     Repasse  Esforço  Prazo ║
║  ─────────────────────────────────────    ──────   ──────   ───── ║
║  A  Ajustar L: 9.0% → 11.3%  ★★★★★       +2.3%     —       —    ║
║  B  Ajustar P: 233 → 268 un/h  ★★★★      —         +15%    −18% ║
║  C  Ajustar n_max: 3 → 5 eq.   ★★★       —         +67%    −22% ║
║  D  Deslocar ramp: semana 24→32 ★★★      —         —       ±0%  ║
║  E  Combinação (A+D)  ★★★              +1.1%     —       ±0%  ║
║                                                                    ║
║  [Roundtrip: ✅ todas válidas]  [Aplicar A]  [Aplicar E]  [Pareto]║
╚════════════════════════════════════════════════════════════════════╝
```

O botão "Pareto" abre o gráfico de trade-offs. Cada botão "Aplicar" cria uma nova versão com o parâmetro pré-preenchido e a hipótese documentada.

### 7.2 Indicador de consistência de roundtrip

No rodapé do diagnóstico, sempre visível:

```
✅ Consistência numérica: todas as soluções passaram no roundtrip (ε < R$0,01)
```
ou:
```
⚠️ VAL-INV-ROUNDTRIP-FAIL: solução C para eap-05 divergiu em R$0.47
   Causa: aproximação de η constante inválida para este item.
   Solução C removida das opções disponíveis.
```

### 7.3 Wizard de nova versão aprimorado

Ao clicar "Criar versão a partir de vN":

```
╔══════════════════════════════════════════════════════════════════╗
║  NOVA VERSÃO — Escolha a solução ou explore livre               ║
║                                                                  ║
║  Soluções disponíveis para fechar PE gap (R$12.4k):             ║
║                                                                  ║
║  ● [A] Ajustar L: +2,3pp → fecha via preço         [Aplicar]   ║
║  ○ [B] Ajustar P: +15% → fecha via produtividade   [Aplicar]   ║
║  ○ [D] Deslocar ramp para semana 32 → fecha cross   [Aplicar]  ║
║  ○ [E] Combinação mínima A+D → +1,1pp preço         [Aplicar]  ║
║  ○ Exploração livre                                             ║
║                                                                  ║
║  Roundtrip status: ✅ A ✅ B ✅ D ✅ E                           ║
╚══════════════════════════════════════════════════════════════════╝
```

Cada "Aplicar" documenta automaticamente a hipótese na versão criada.

### 7.4 Indicador de consistência global no footer da aba Planejamento

```
┌─────────────────────────────────────────────────────────────┐
│ 🔬 Consistência de cálculo: ✅ Roundtrip OK (v7)  |  η=0.82 │
└─────────────────────────────────────────────────────────────┘
```

Sempre visível no rodapé do Painel de Controle. Verde = sistema consistente. Amarelo = alguma solução inversa falhou no roundtrip (mas forward está OK). Vermelho = inconsistência no forward (nunca deve acontecer — bug crítico se ocorrer).

---

## 8. Propriedades de validação

### 8.1 Invariante de roundtrip por nível

| Nível | Invariante | Obrigatório? |
|-------|-----------|-------------|
| Diesel | $\Delta C_\text{diesel}(θ^*) = c_\text{diesel}\tilde{Q}/S$ independente de $\theta$ | ✅ Sempre |
| F1 | $F_1(\lceil F\rceil) \geq 0$ e $F_1(F\in\mathbb{Z})=0$ | ✅ Sempre |
| $\eta$ | $\eta \in (0, 1]$ e $\eta = 1 \iff p(t)=1\;\forall t$ | ✅ Sempre |
| Roundtrip L | $\|PV(L^*) - C_\text{real}\| < \varepsilon_\text{tol}$ | ✅ Exato |
| Roundtrip P | $\|C_\text{real}(P^*) - C_\text{alvo}\| < \varepsilon_\text{tol}$ | ✅ Se η const. |
| Roundtrip timing | $\|\varepsilon_\text{cross}(t_0^*)\| < \varepsilon_\text{tol}$ | ✅ Após simulação |
| Normalização | $F_1 + F_\eta + F_\text{ind} + \varepsilon_\text{cross} = \text{gap\_total} \pm 1\%$ | ✅ Sempre |

### 8.2 Detecção de inconsistências

Emissão automática de alertas:

- `VAL-INV-ROUNDTRIP-FAIL`: solução inversa não satisfaz a invariante — solução descartada
- `VAL-INV-ETA-VIOLATION`: $\eta^* > 1$ (impossível fisicamente) — modelo com erro estrutural
- `VAL-INV-P-DIVERGE`: estimativa de P* requer iteração (η não é constante)
- `VAL-INV-NORM-FAIL`: $|F_1 + F_\eta + F_\text{ind} + \varepsilon_\text{cross} - \text{gap}| > 1\%$ — inconsistência na decomposição

---

## 9. Plano de implementação

| Fase | Entrega | Arquivo |
|------|---------|---------|
| 1 | `SolucaoInversa`, `BacktrackingPEItem`, `BacktrackingPERelatorio` | `domain/models/backtracking_pe.py` |
| 2 | `BacktrackingPEBuilder.build(diagnostico, alvo)` com todos os inversos | `domain/services/backtracking_pe_builder.py` |
| 3 | Validação roundtrip integrada ao builder | dentro do builder |
| 4 | `canonical.backtracking_pe` + geração em Skill 08 | `canonical.py`, `08/.../skill.py` |
| 5 | UI-1: Painel de Recalibração Inversa no Overview | `organisms/layout.py` |
| 6 | UI-3: Wizard de versão com soluções pré-preenchidas | `organisms/layout.py` |
| 7 | UI-4: Footer de consistência global | `templates/project_page.py` |
| 8 | Testes: roundtrip para cada inverso, casos de falha | `tests/unit/test_adr061_backtracking_pe.py` |

## Definition of Done

- [x] Inversa de L: roundtrip exato (ε = 0 analiticamente)
- [x] Inversa de η (via P): roundtrip ≤ 0.01%
- [x] Inversa de n_max: roundtrip ≤ 1 semana de T_real
- [x] Inversa de timing: Cov(n,p) ≤ ε após otimização
- [x] `VAL-INV-ROUNDTRIP-FAIL` emitido quando roundtrip falha
- [x] `VAL-INV-NORM-FAIL` emitido quando decomposição não soma ao gap
- [x] η invariante: nunca > 1 nem ≤ 0 em produção
- [x] Testes: PE_gap = 0 exato para solução L; PE_gap ≤ ε para outras
- [x] Pareto front corretamente ordenado por trade-off
- [x] Footer de consistência visível em todos os runs
