# ADR-060: Diagnóstico de Ponto de Equilíbrio — Decomposição Causal e Recalibração de BDI

**Status:** Implementado  
**Data:** 2026-05-17  
**Autor:** Engenheiro Sênior  
**Relacionado:** ADR-023 (BDI), ADR-039 (The Bridge), ADR-054 (WMP), ADR-056 (Débito Técnico), ADR-057 (Memorial BDI), ADR-058 (Analiticidade), ADR-059 (Permanência de Recursos)

---

## 1. Contexto

O sistema calcula `ponto_equilibrio` por item da EAP (Skill 08) e sinaliza déficits. O diagnóstico atual responde **"o quê"** — quais itens não equilibram — mas não **"por quê"** nem **"quanto cada fator contribui"** nem **"o que mudar para melhorar"**.

---

## 2. Análise matemática rigorosa

### 2.1 A equação fundamental

Para cada semana $t$ da atividade $i$:

$$q(t) = P \cdot m \cdot h \cdot p(t) \cdot n(t)$$

onde $P$ é a produtividade horária, $m \cdot h$ o regime semanal, $p(t) \in (0,1]$ a praticabilidade e $n(t)$ as equipes alocadas.

Condição de completude: $\sum_t q(t) = Q_i$. Normalizando:

$$\tilde{Q} = \frac{Q_i}{P \cdot m \cdot h} \quad \text{[equipe-semanas produtivas necessárias]}$$

### 2.2 Estrutura de custo (ADR-030)

O custo por equipe por semana tem dois componentes:

$$c_\text{sem} = \frac{c_\text{fixo}}{S} + \frac{c_\text{diesel}}{S} \cdot p(t)$$

onde $c_\text{fixo} = c_\text{MO} + c_\text{EQ}$ (fixo, independente de $p$) e $S = \text{SEMANAS\_POR\_MES}$.

**Custo total real:**

$$C_\text{real} = \frac{c_\text{fixo}}{S}\underbrace{\sum_t n(t)}_{N_\text{total}} + \frac{c_\text{diesel}}{S}\underbrace{\sum_t p(t)n(t)}_{\tilde{Q}}$$

**Observação crítica:** o diesel é sempre $\frac{c_\text{diesel}}{S}\tilde{Q}$, independente de $n(t)$ e $p(t)$. **O diesel cancela no gap de custo.** O gap de custo direto é determinado inteiramente por $N_\text{total}$.

### 2.3 O fator unificador η

**Definição:** eficiência efetiva da campanha:

$$\eta = \frac{\sum_t p(t)n(t)}{\sum_t n(t)} = \frac{\tilde{Q}}{N_\text{total}}$$

$\eta$ é a **média de $p(t)$ ponderada por $n(t)$**, não a média temporal simples. Portanto:

$$N_\text{total} = \frac{\tilde{Q}}{\eta}$$

### 2.4 Gap de custo direto — forma exata

$$\boxed{\Delta C_\text{direto} = \frac{c_\text{fixo}}{S}\cdot\tilde{Q}\cdot\left(\frac{1}{\eta_\text{real}} - \frac{\lceil F \rceil}{F}\right)}$$

onde $F = \tilde{Q}/T_\text{horizonte}$ são as equipes contínuas necessárias. O termo $\lceil F \rceil/F \geq 1$ é o fator de quantização (sempre $\geq 1$, só depende de $Q_i$, $P$, $T$).

### 2.5 Por que F2 e F3 não são desacoplados em geral

Pelo teorema da covariância:

$$\eta = E_n[p(t)] = \bar{p}_\text{uniforme} + \frac{\text{Cov}(n, p)}{\bar{n}}$$

onde $\bar{p}_\text{uniforme}$ é a média temporal simples de $p(t)$ e $\bar{n} = N_\text{total}/T$.

**Casos-limite que demonstram o acoplamento:**

| Cenário | $\eta$ | Interpretação |
|---------|--------|---------------|
| $p(t) = 1$ (sem clima), WMP ramp qualquer | $\eta = 1$ | Ramp sozinho não cria gap de custo **direto** |
| $n(t) = n_\text{max}$ constante, $p(t)$ variável | $\eta = \bar{p}_\text{uniforme}$ | Clima age puramente sobre o custo direto |
| Ramp-up coincide com chuva ($\text{Cov}(n,p) < 0$) | $\eta < \bar{p}$ | **Penalidade dupla:** ambos pioram η simultaneamente |
| Ramp-up coincide com seca ($\text{Cov}(n,p) > 0$) | $\eta > \bar{p}$ | **Benefício da sincronia:** ramp durante seca melhora η |

**Conclusão:** "F2" e "F3" não existem como fatores diretos separados. O fator real é $\eta_\text{real}$.

### 2.6 Separação entre custos diretos e indiretos

O WMP ramp **não** afeta custos diretos quando $p=1$: se $p(t) = 1$, então $\tilde{Q} = N_\text{total}$ independentemente do perfil $n(t)$ — qualquer curva de ramp que entregue $\tilde{Q}$ tem o mesmo $N_\text{total}$.

O WMP ramp **afeta** os custos indiretos via duração:

$$\Delta C_\text{indireto} = c_\text{ind/sem} \cdot (T_\text{real} - T_\text{ref})$$

Onde $\Delta T$ é aproximadamente separável quando as fases não se sobrepõem:

$$\Delta T \approx \underbrace{\Delta T_\text{clima}}_{\text{estacionário mais longo}} + \underbrace{\Delta T_\text{ramp}}_{\text{semanas de mobilização}}$$

### 2.7 Decomposição formal correta: 3 fatores

$$\Delta C_\text{total} = \underbrace{F_1}_{\text{quantização}} + \underbrace{F_\eta}_{\text{ineficiência efetiva}} + \underbrace{F_\text{ind}}_{\text{indiretos por duração}}$$

**$F_1$ — Quantização (exato, desacoplado de $\eta$):**

$$F_1 = \frac{c_\text{fixo}}{S}\cdot\tilde{Q}\cdot\left(\frac{\lceil F \rceil}{F} - 1\right)$$

Determinístico dado $Q_i$, $P$, $n_\text{max}$. Não pode ser eliminado sem mudar o escopo ou a produtividade.

**$F_\eta$ — Ineficiência efetiva (joint WMP + clima):**

$$F_\eta = \frac{c_\text{fixo}}{S}\cdot\tilde{Q}\cdot\left(\frac{1}{\eta_\text{real}} - 1\right)$$

**Aproximação aditiva** (válida quando $|\text{Cov}(n,p)/(\bar{n}\cdot\bar{p})| < \delta$):

$$F_\eta \approx \underbrace{F_\eta^{(p)}}_{\text{componente climática}} + \underbrace{F_\eta^\text{cross}}_{\text{cross-term de timing}}$$

onde $F_\eta^{(p)} \approx \frac{c_\text{fixo}}{S}\tilde{Q}(1/\bar{p}-1)$ e o cross-term é:

$$\varepsilon_\text{cross} = -\frac{c_\text{fixo}}{S}\cdot\tilde{Q}\cdot\frac{\text{Cov}(n,p)}{\eta_\text{real}\cdot\bar{p}\cdot\bar{n}}$$

Se $\varepsilon_\text{cross} > 0$: ramp-up em período chuvoso (piora o PE).
Se $\varepsilon_\text{cross} < 0$: ramp-up em período seco (melhora η além da praticabilidade média).

**$F_\text{ind}$ — Indiretos por duração:**

$$F_\text{ind} = c_\text{ind/sem}\cdot(\Delta T_\text{clima} + \Delta T_\text{ramp})$$

Aproximação aditiva válida quando $T_\text{ramp} \ll T_\text{total}$.

### 2.8 Métricas do DiagnosticoPEBuilder

| Métrica | Fórmula | Separável? |
|---------|---------|-----------|
| $F_1$ (quantização) | $\frac{c_\text{fixo}}{S}\tilde{Q}(\lceil F\rceil/F - 1)$ | ✅ Exato |
| $\eta_\text{real}$ | $\tilde{Q}/N_\text{total}$ | ✅ Exato |
| $\bar{p}_\text{uniforme}$ | $\sum p(t)/T$ | ✅ Exato |
| $\text{Cov}(n,p)$ | $\sum(n-\bar{n})(p-\bar{p})/T$ | ✅ Exato |
| $\varepsilon_\text{cross}$ | $\eta_\text{real} - \bar{p} + \text{Cov}/\bar{N}$ | ✅ Exato |
| $\Delta T_\text{ramp}$ | semanas extras por mobilização | ≈ Separável |
| $\Delta T_\text{clima}$ | semanas extras por praticabilidade | ≈ Separável |
| $L_\text{req}$ | $L + |gap|/(C_\text{cat}(1-T_\text{ef}))$ | ✅ Exato |

**Condição de validade da aproximação aditiva:**

$$\left|\frac{\text{Cov}(n,p)}{\bar{n}\cdot\bar{p}}\right| < 5\% \quad \text{(threshold configurável)}$$

Se violada, emitir `VAL-PE-CROSS-TERM` com o valor de $\varepsilon_\text{cross}$.

### 2.9 BDI requerido

O componente L que equilibraria o item:

$$L_\text{req} = L_\text{aplicado} + \frac{|\Delta C_\text{total}|}{C_\text{catalogo}\cdot(1 - T_\text{efetivo})}$$

---

## 3. Modelo de dados

```python
@dataclass(frozen=True)
class DiagnosticoPEItem:
    atividade_id: str
    cpu_id: str
    descricao: str
    preco_venda: float
    custo_realizado: float
    gap_rs: float               # preco_venda - custo_realizado (negativo = déficit)
    pct_gap_sobre_venda: float

    # Métricas primárias (exatas)
    eta_real: float             # eficiência efetiva η = Q̃/N_total
    p_medio_uniforme: float     # média temporal de p(t)
    cov_n_p: float              # Cov(n(t), p(t)) — cross-term
    eps_cross: float            # desvio da aproximação aditiva
    validade_aproximacao: bool  # True se |Cov/(n̄×p̄)| < threshold

    # Decomposição de custo direto (exata)
    f1_quantizacao_rs: float    # c_fixo × Q̃ × (⌈F⌉/F − 1)
    f_eta_rs: float             # c_fixo × Q̃ × (1/η − 1) [total, inclui cross-term]

    # Decomposição de custo indireto (aproximada)
    f_ind_clima_rs: float       # c_ind × ΔT_clima
    f_ind_ramp_rs: float        # c_ind × ΔT_ramp

    # Cross-term explícito
    f_cross_rs: float           # εcross — penalidade/benefício de timing WMP×clima

    # Recalibração
    l_aplicado: float
    l_requerido: float
    delta_l: float

@dataclass(frozen=True)
class DiagnosticoPERelatorio:
    projeto_id: str
    gerado_em: str
    n_itens_deficit: int
    gap_total_rs: float
    fator_dominante: str        # "F1" | "F_ETA" | "F_IND_CLIMA" | "F_IND_RAMP" | "F_CROSS"
    aviso_cross_term: bool      # True se algum item tem cross-term significativo
    itens_deficit: tuple[DiagnosticoPEItem, ...]
    l_medio_requerido: float
    recomendacoes: tuple[str, ...]
```

---

## 4. Design de UX — Decisões de ramificação de versão

### 4.1 O problema de orientação

O usuário vê uma lista de versões e não sabe **por que** cada versão foi criada, **o que mudou** em relação à anterior, nem **se o objetivo foi atingido**. Cada run produz uma versão e o usuário perde o fio condutor das decisões.

### 4.2 Modelo mental proposto: "Ciclo de hipótese → experimento → resultado"

Cada versão representa uma **hipótese de melhoria** sobre o PE. O fluxo visual deve comunicar:

```
Hipótese formulada → Parâmetros alterados → Run executado → PE delta observado
```

### 4.3 Componente: Linha do tempo de versões anotada

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LINHA DO TEMPO DE VERSÕES                                           [↗ exp] │
│                                                                              │
│  v1 ──────────────── v2 ────────────── v3 ──────── v4 (atual)              │
│  [baseline]          ↑                 ↑            ↑                        │
│  PE: R$ -45k         WMP n_ini=1→3     L: 9%→11%   CPU prod. +15%           │
│  η: 0.71             PE: R$ -28k       PE: R$ -12k  PE: R$ -3k              │
│  Margin: 8.1%        η: 0.82           η: 0.82      η: 0.86                 │
│                      Alvo: F_η↓        Alvo: L↑     Alvo: η↑                │
│                      ✅ F_η: -38%      ✅ gap↓       ✅ quase equil.         │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Cada nó da linha do tempo mostra:**
1. O **alvo declarado** da hipótese (o que o planejador queria melhorar)
2. O **parâmetro alterado** (WMP / BDI / CPU / Composição)
3. O **resultado medido** (delta PE, delta η, delta margin)
4. O **ícone de avaliação** (✅ melhorou / ⚠️ melhorou parcialmente / ❌ piorou)

### 4.4 Componente: Wizard de criação de nova versão

Quando o usuário clica "✚ Nova versão a partir de [vN]", em vez de abrir diretamente o painel de planejamento, um wizard guiado aparece:

```
╔═══════════════════════════════════════════════════════════════════════╗
║  NOVA VERSÃO — Qual é a hipótese de melhoria?                        ║
║                                                                       ║
║  Diagnóstico atual (v3):                                              ║
║  ┌──────────────────┬──────────┬───────────┬────────────┐           ║
║  │ Fator            │ Gap R$   │ % do gap  │ Reduzível? │           ║
║  ├──────────────────┼──────────┼───────────┼────────────┤           ║
║  │ F1 Quantização   │ R$ 2.1k  │  18%      │ Parcial    │           ║
║  │ Fη Inef. efetiva │ R$ 7.4k  │  62%      │ Sim ←      │           ║
║  │  ↳ componente p̄  │ R$ 5.1k  │  43%      │ Sazonal    │           ║
║  │  ↳ cross-term    │ R$ 2.3k  │  19%      │ ⚠️ Timing  │           ║
║  │ Find Indiretos   │ R$ 2.4k  │  20%      │ Parcial    │           ║
║  └──────────────────┴──────────┴───────────┴────────────┘           ║
║                                                                       ║
║  O que você quer atacar?                                              ║
║                                                                       ║
║  ○ Fη — Melhorar eficiência efetiva (η = 0.82 → alvo 0.90)          ║
║    → Recomendado: ajustar WMP ou produtividade de CPU                ║
║    → Previsão: PE gap −R$3.2k se η atingir 0.90                     ║
║                                                                       ║
║  ○ Cross-term — Sincronizar mobilização com estação seca             ║
║    → Ramp-up atual coincide com chuva (Cov(n,p) = −0.18)            ║
║    → Previsão: PE gap −R$2.3k se ramp-up deslocado 8 semanas        ║
║                                                                       ║
║  ○ L — Recalibrar margem no BDI                                      ║
║    → L atual: 9.0% | L requerido: 11.3%                             ║
║    → Previsão: fecha PE gap completamente (impacto no preço: +2.3%) ║
║                                                                       ║
║  ○ Exploração livre                                                   ║
║    → Abre painel de planejamento sem foco específico                 ║
║                                                                       ║
║              [Cancelar]        [Criar versão com foco →]             ║
╚═══════════════════════════════════════════════════════════════════════╝
```

Após selecionar o alvo, o painel de planejamento abre com:
- O acordeão relevante **expandido e destacado**
- O campo-alvo **pré-preenchido** com o valor sugerido pelo diagnóstico
- Um indicador de previsão de impacto inline antes de executar o run

### 4.5 Componente: Preview de impacto antes do run

No acordeão correspondente, após editar qualquer parâmetro relacionado ao diagnóstico:

```
╔════════════════════════════════════════════╗
║  PREVISÃO DE IMPACTO (estimativa)          ║
║                                            ║
║  Parâmetro alterado: n_max 3 → 5           ║
║  Efeito esperado:                          ║
║   • η estimado: 0.82 → 0.89               ║
║   • Fη estimado: R$7.4k → R$3.2k (−57%)  ║
║   • PE gap estimado: −R$12k → −R$7k       ║
║                                            ║
║  ⚠️ Cross-term ainda presente             ║
║  Sugestão adicional: deslocar ramp-up     ║
║  para semana 32 (início da estação seca)  ║
╚════════════════════════════════════════════╝
```

Esta previsão usa o `DiagnosticoPEBuilder` com os parâmetros editados mas **sem rodar o pipeline completo** — é uma estimativa analítica direta da fórmula de η.

### 4.6 Componente: Comparação causal entre versões

Na aba "🔀 Comparar versões", além dos deltas financeiros existentes, adicionar o **diff causal**:

```
╔═════════════════════════════════════════════════════════════════════╗
║  DIFF CAUSAL: v2 → v3                                              ║
║                                                                     ║
║  Hipótese v3: "Aumentar L para cobrir gap climático"               ║
║  Parâmetro: L(MO) 9% → 11%                                        ║
║                                                                     ║
║  Fator          │ v2        │ v3        │ Delta      │ ✓/✗        ║
║  ─────────────────────────────────────────────────────────         ║
║  F1 Quantização │ R$2.1k   │ R$2.1k   │    —       │  ─          ║
║  Fη (η: 0.82)   │ R$7.4k   │ R$7.4k   │    —       │  ─          ║
║  Find Indiretos │ R$2.4k   │ R$2.4k   │    —       │  ─          ║
║  BDI (L)        │ 9.0%     │ 11.0%    │ +2.0pp     │  ✅          ║
║  PE gap total   │ −R$12k   │ −R$2k    │ −R$10k     │  ✅          ║
║  Margem         │  9.3%    │ 11.2%    │ +1.9pp     │  ✅          ║
║  Preço venda    │  base    │ +2.3%    │            │  ⚠️ atenção  ║
║                                                                     ║
║  Conclusão: L fechou o gap financeiro mas via repasse ao cliente.  ║
║  O η permanece em 0.82 — ineficiência operacional persiste.        ║
║  Próxima hipótese sugerida: atacar η pela sincronização do ramp.   ║
╚═════════════════════════════════════════════════════════════════════╝
```

---

## 5. Plano de implementação

| Fase | Entrega | Arquivo |
|------|---------|---------|
| 1 | `DiagnosticoPEItem`, `DiagnosticoPERelatorio` (frozen dataclasses) | `domain/models/diagnostico_pe.py` |
| 2 | `DiagnosticoPEBuilder` — F1, F_η, F_ind, F_cross, L_req | `domain/services/diagnostico_pe_builder.py` |
| 3 | `canonical.diagnostico_pe` field + Skill 08 | `domain/models/canonical.py`, `08/.../skill.py` |
| 4 | Linha do tempo anotada (UI Overview) | `organisms/layout.py` |
| 5 | Wizard de criação de versão com foco | `organisms/layout.py` |
| 6 | Preview de impacto inline nos acordeões | `organisms/layout.py` |
| 7 | Diff causal na aba Comparação | `organisms/layout.py` |
| 8 | Excel: aba `DIAGNOSTICO.PE` | `infrastructure/adapters/excel_adapter.py` |
| 9 | Testes unitários | `tests/unit/test_adr060_diagnostico_pe.py` |

## Definition of Done

- [x] η_real calculado exatamente como Q̃/N_total
- [x] Cov(n,p) calculado e cross-term reportado
- [x] VAL-PE-CROSS-TERM emitido quando |Cov/(n̄×p̄)| > threshold
- [x] L_requerido exato pela fórmula §2.9
- [x] Wizard de criação de versão com diagnóstico e previsão
- [x] Linha do tempo com hipótese/resultado por versão
- [x] Diff causal na comparação
- [x] Preview de impacto (analítico, sem pipeline) inline
- [x] Invariante: F1 + F_η + F_ind + F_cross ≈ gap_total (±1% por arredondamento)
- [x] Testes cobrem: cross-term positivo, negativo, zero; η=1; F1=0 (Q exato em equipes)
