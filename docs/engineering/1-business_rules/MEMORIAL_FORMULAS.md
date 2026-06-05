# Memorial de Fórmulas — Concilium

> **Propósito**: Fonte única de verdade para todas as fórmulas quantitativas
> implementadas na pipeline. Valores numéricos indicados são de referência
> (vigência abr/2026); parâmetros configuráveis estão marcados com ⚙.
>
> **Escopo**: BDI → Encargos → Custo CPU → Produtividade → Cronograma →
> Criticidade → Consolidação → Indiretos → Replanejamento.

---

## Índice

1. [Constantes Globais](#1-constantes-globais)
2. [BDI — Fórmula TCU](#2-bdi--fórmula-tcu)
3. [BDI — Tabela Padrão MendesLobo (abr/2026)](#3-bdi--tabela-padrão-mendeslobo-abr2026)
4. [Encargos Sociais](#4-encargos-sociais)
5. [Custo de Insumos](#5-custo-de-insumos)
6. [Custo da CPU — Composição](#6-custo-da-cpu--composição)
7. [Decomposição de Equipamento](#7-decomposição-de-equipamento)
8. [Produtividade e Rendimento](#8-produtividade-e-rendimento)
9. [Cronograma — Execução Semanal](#9-cronograma--execução-semanal)
10. [Criticidade — Análise de Esforço](#10-criticidade--análise-de-esforço)
11. [Criticidade — Análise de Custo (Pareto)](#11-criticidade--análise-de-custo-pareto)
12. [Consolidação — Margens](#12-consolidação--margens)
13. [Ponto de Equilíbrio (Reconciliação)](#13-ponto-de-equilíbrio-reconciliação)
14. [Controle de Gap de Margem](#14-controle-de-gap-de-margem)
15. [Indiretos — Distribuição Temporal](#15-indiretos--distribuição-temporal)
16. [Reconciliação de Recursos](#16-reconciliação-de-recursos)
17. [Sugestões de Replanejamento](#17-sugestões-de-replanejamento)
18. [Limiares e Thresholds de Controle](#18-limiares-e-thresholds-de-controle)
19. [Vocabulário Canônico de Unidades](#19-vocabulário-canônico-de-unidades)

---

## 1. Constantes Globais

| Constante | Valor | Convenção / Fonte |
|-----------|-------|-------------------|
| `HORAS_MES` | **220 h** | Valor em `integrate_market_research.py`; `concilium.yaml` adota 208 h (26d × 8h) para skill 03; diag scripts usam 205,71 h (30d × 6/7 × 8h) |
| `HORAS_DIA` | **8 h** | Jornada de trabalho padrão |
| `DIAS_UTEIS_SEMANA` | **5 dias** | Para cálculo de produção semanal |
| `DIAS_UTEIS_MES` | **≈ 25,71 dias** | = 30 × 6/7 (convenção "30 dias corridos menos domingos") |
| `SEMANAS_POR_MES` | **≈ 4,348 sem** | = 365,25 / (12 × 7) |
| `PRECO_DIESEL_REF` | R$ 6,50/L | Referência de mercado (calibração mai/2025) |

> **Nota de consistência HORAS_MES**: Existem três convenções no código —
> confirmar e unificar em uma única constante é item pendente no roadmap.
> A skill 03 usa 208 h (`26 × 8`); o catálogo foi gerado com 220 h.

---

## 2. BDI — Fórmula TCU

**Referência**: TCU Acórdão nº 2622/2013  
**Arquivo**: `concilium/src/concilium/domain/models/bdi.py` — `ComponentesBdi.bdi_total`

$$
\text{BDI} = \frac{1 + AC + DF + R + CR + L}{1 - T} - 1
$$

onde:

$$
T = \text{cofins} + \text{iss} + \text{pis} + \text{cssl} + \text{ir}
$$

| Símbolo | Campo | Descrição |
|---------|-------|-----------|
| $AC$ | `ac` | Administração central |
| $DF$ | `df` | Despesas financeiras |
| $R$ | `r` | Garantia / risco / seguro |
| $CR$ | `cr` | Contingência de risco |
| $L$ | `l` | Lucro |
| $T$ | `tributos` | Soma dos tributos (propriedade calculada) |

**Restrição**: $T < 1$ (denominador > 0). O modelo levanta `ValueError` caso contrário.

**Aplicação ao preço de venda**:

$$
P_{\text{venda}} = P_{\text{custo}} \times (1 + \text{BDI}_{\text{categoria}})
$$

---

## 3. BDI — Tabela Padrão MendesLobo (abr/2026)

**Arquivo**: `concilium/src/concilium/domain/models/bdi.py` — `DEFAULT_BDI_TABELA`  
**Vigência**: 2026-04-01

### 3.1 Componentes por Categoria

| Categoria | AC | DF | R | CR | L | cofins | iss | pis | cssl | ir | **BDI ≈** |
|-----------|----|----|---|----|---|--------|-----|-----|------|----|-----------|
| MAO_OBRA | 5,0% | 1,5% | 1,0% | 0% | 9,0% | 3,0% | 5,0% | 0,65% | 1,99% | 2,74% | **≈ 35,5%** |
| MATERIAL | 5,0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 0% | **≈ 5,3%** |
| SERVICOS | 5,0% | 1,5% | 1,0% | 0% | 9,0% | 3,0% | 5,0% | 0,65% | 1,99% | 2,74% | **≈ 35,5%** |
| INDIRETO | 4,0% | 0% | 0% | 0% | 2,0% | 3,0% | 5,0% | 0,65% | 1,99% | 2,74% | **≈ 15,5%** |
| DIESEL | 4,0% | 0% | 0% | 0% | 5,0% | 3,0% | 5,0% | 0,65% | 1,99% | 2,74% | **≈ 21,5%** |

> ⚙ Todos os valores são configuráveis por projeto via `PerfilTributarioProjeto` + `PerfilLucroProjeto` (ADR-023 §D6/D7).

### 3.2 BDI Ponderado para Equipamentos (fallback)

Quando não há `DecomposicaoEquipamento` explícita:

$$
\text{BDI}_{\text{equip}} = 0{,}70 \times \text{BDI}_{\text{MAO\_OBRA}} + 0{,}30 \times \text{BDI}_{\text{DIESEL}}
$$

---

## 4. Encargos Sociais

**Referência**: ADR-023 §D2  
**Arquivo**: `concilium/src/concilium/domain/models/bdi.py` — `DEFAULT_ENCARGOS`  
**Vigência**: 2026-04-01

$$
E_{\text{total}} = a + b + c + d + e + f + \text{judicial}
$$

### 4.1 Horistas — total **177,70%**

| Grupo | Fração | Descrição |
|-------|--------|-----------|
| $a$ | 37,80% | Básicos: INSS patronal, FGTS, salário-educação, SENAT, SEST |
| $b$ | 47,84% | Com incidência de $a$: férias + 1/3, 13º salário, DSR |
| $c$ | 40,53% | Sem incidência de $a$: aviso prévio, indenização adicional |
| $d$ | 19,07% | Reincidências de $b$ sobre $c$ |
| $e$ | 10,22% | Seguros, plano de saúde |
| $f$ | 19,24% | Vale-transporte, vale-alimentação |
| judicial | 3,00% | Despesas judiciais trabalhistas |
| **Total** | **177,70%** | |

### 4.2 Mensalistas — total **106,00%**

| Grupo | Fração |
|-------|--------|
| $a$ | 37,80% |
| $b$ | 9,94% |
| $c$ | 40,30% |
| $d$ | 4,74% |
| $e$ | 10,22% |
| $f$ | 0% (sem VT/VA) |
| judicial | 3,00% |
| **Total** | **106,00%** |

### 4.3 Custo Total de Mão de Obra com Encargos

$$
C_{\text{mo}} = S_{\text{mensal}} \times (1 + E_{\text{total}})
$$

onde $S_{\text{mensal}}$ é o salário mensal de convenção coletiva e $E_{\text{total}}$ é a fração de encargos do regime aplicável.

Para insumos com `unidade = "h"`:

$$
S_{\text{mensal}} = P_{\text{unitario}} \times \text{HORAS\_MES}
$$

O campo `atributos_especificos.custo_com_encargos` registra $C_{\text{mo}}$ calculado na importação da planilha.

---

## 5. Custo de Insumos

### 5.1 Mão de Obra (`unidade = "mes"`)

| Campo JSON | Valor | Descrição |
|---|---|---|
| `preco_unitario` | R$/mês | Salário mensal bruto de convenção |
| `atributos_especificos.custo_com_encargos` | R$/mês | = `custo_horario × horas_mes` (conforme planilha RFI) |
| `atributos_especificos.horas_mes` | h/mês | Jornada mensal contratual |

### 5.2 Equipamentos (`unidade = "h"`)

$$
C_{\text{eq/h}} = C_{\text{produtivo}} + C_{\text{manutencao}}
$$

$$
C_{\text{manutencao}} = C_{\text{produtivo}} \times \%_{\text{manutencao}}
$$

| Campo JSON | Valor | Descrição |
|---|---|---|
| `preco_unitario` | R$/h | Custo horário total = produtivo + manutenção |
| `atributos_especificos.custo_produtivo_hora` | R$/h | Custo produtivo (depreciação + remuneração) |
| `atributos_especificos.pct_manutencao` | fração | Percentual de manutenção sobre o produtivo |
| `atributos_especificos.custo_manutencao_hora` | R$/h | = `custo_produtivo × pct_manutencao` |
| `atributos_especificos.valor_locacao_mensal` | R$/mês | Para equipamentos locados |
| `atributos_especificos.horas_mes` | h/mês | = `valor_locacao_mensal / preco_unitario` (derivado) |

### 5.3 Materiais (`unidade` variável)

`preco_unitario` em R$ por unidade canônica do material (m³, t, m², m, kg, sc, etc.).

---

## 6. Custo da CPU — Composição

**Arquivo**: `scripts/integrate_market_research.py` — `_recalc_custo_total`

### 6.1 Custo sem BDI por Unidade de Serviço

$$
C_{\text{cpu}} = \sum_{i} \text{coef}_i \times P_i
$$

onde:
- $\text{coef}_i$ = coeficiente de consumo do insumo $i$ por unidade de serviço da CPU
- $P_i$ = `preco_unitario` do insumo $i$ (R$/unidade do insumo)

### 6.2 Coeficiente de Mão de Obra

Para um trabalhador com rendimento vinculado à `producao_horaria` da CPU:

$$
\text{coef}_{\text{mo}} = \frac{1}{\text{producao\_horaria}} \times \frac{1 + E_{\text{total}}}{\text{HORAS\_MES}}
$$

> Leitura: horas necessárias por unidade de serviço, convertidas para fração do mês, multiplicadas pelos encargos.  
> **Nota**: o campo `preco_unitario` de MO é o salário mensal; o coeficiente já embutiu a conversão h → mês.

Equivalentemente:

$$
\text{coef}_{\text{mo}} = \frac{1 + E_{\text{total}}}{\text{producao\_horaria} \times \text{HORAS\_MES}}
$$

### 6.3 Coeficiente de Equipamento

$$
\text{coef}_{\text{eq}} = \frac{1}{\text{producao\_horaria}}
$$

Unidade: h/unidade\_serviço. O `preco_unitario` do equipamento é R$/h.

### 6.4 Custo com BDI por Categoria

$$
C_{\text{categoria\_com\_BDI}} = C_{\text{categoria\_sem\_BDI}} \times (1 + \text{BDI}_{\text{categoria}})
$$

$$
C_{\text{cpu\_com\_BDI}} = \sum_{\text{categoria}} C_{\text{categoria\_com\_BDI}}
$$

---

## 7. Decomposição de Equipamento

**Referência**: ADR-023 §D3  
**Arquivo**: `concilium/src/concilium/domain/models/bdi.py` — `DecomposicaoEquipamento`

$$
C_{\text{h\_total}} = C_{\text{mo\_h}} + C_{\text{diesel\_h}} + C_{\text{mat\_h}} + C_{\text{capital\_h}}
$$

**Frações para aplicação de BDI correto:**

$$
f_{\text{mo}} = \frac{C_{\text{mo\_h}} + C_{\text{capital\_h}}}{C_{\text{h\_total}}}
\quad\rightarrow\quad \text{BDI}_{\text{MAO\_OBRA}}
$$

$$
f_{\text{diesel}} = \frac{C_{\text{diesel\_h}}}{C_{\text{h\_total}}}
\quad\rightarrow\quad \text{BDI}_{\text{DIESEL}}
$$

$$
f_{\text{mat}} = \frac{C_{\text{mat\_h}}}{C_{\text{h\_total}}}
\quad\rightarrow\quad \text{BDI}_{\text{MATERIAL}}
$$

**Restrição de integridade** (validado pelo Pydantic):

$$
|C_{\text{mo\_h}} + C_{\text{diesel\_h}} + C_{\text{mat\_h}} + C_{\text{capital\_h}} - C_{\text{h\_total}}| \leq R\$\,0{,}01
$$

**Custo do Diesel por hora:**

$$
C_{\text{diesel\_h}} = \text{consumo\_litros\_hora} \times P_{\text{diesel}}
$$

**Precedência para consumo de combustível** (ADR-030 D1, 4 níveis):

1. `EquipamentoEquipe.consumo_litros_hora` — override explícito do projeto
2. `EquipamentoEquipe.consumo_litros_hora_estimado` — especificação da CPU
3. `Insumo.atributos_especificos.consumo_litros_hora` — catálogo
4. Zero + alerta `VAL-EQUIP-COMB-03`

---

## 8. Produtividade e Rendimento

**Referência**: ADR-007  
**Arquivo**: `concilium/src/concilium/domain/models/` (vários)

### 8.1 Conversão de Granularidades

$$
Q_{\text{dia}} = Q_h \times H_{\text{dia}}
$$

$$
Q_{\text{semana}} = Q_h \times H_{\text{dia}} \times D_{\text{semana}}
$$

$$
Q_{\text{mes}} = Q_h \times \text{HORAS\_MES}
$$

onde $Q_h$ = `producao_horaria` (unidade\_serviço / h).

### 8.2 Custo Unitário a partir da Produção

$$
C_{\text{unitario}} = \frac{C_{\text{horario\_total}}}{Q_h}
$$

### 8.3 Produção com Múltiplas Equipes

$$
Q_{\text{n equipes}} = Q_{\text{semana}} \times n \times \eta
$$

onde $\eta$ = eficiência (0–1), $n$ = número de equipes.

---

## 9. Cronograma — Execução Semanal

**Referência**: Skill 02  
**Arquivo**: `concilium/src/concilium/application/skills/manifests/02-cronograma/skill.py`

### 9.1 Produção Executada por Semana

$$
\Delta Q_{\text{sem}} = Q_h \times H_{\text{dia}} \times D_{\text{semana}} \times \eta_{\text{sem}} \times n_{\text{equipes}}
$$

$$
\Delta Q_{\text{sem}}^{\text{real}} = \min\!\bigl(\Delta Q_{\text{sem}},\; \max(0,\; Q_{\text{total}} - Q_{\text{acum}})\bigr)
$$

### 9.2 Percentual de Completude

$$
\%_{\text{concluído}} = \frac{Q_{\text{acum}}}{Q_{\text{total}}}
$$

### 9.3 Permanência de Equipes (semanas → meses)

$$
\text{perm\_meses} = \frac{\text{semanas\_ativas}}{\text{SEMANAS\_POR\_MES}} = \frac{\text{semanas\_ativas}}{4{,}348}
$$

### 9.4 Custo Total de Equipe por Período

**Para distribuição semanal:**

$$
C_{\text{total}} = \sum_{\text{sem}} \frac{C_{\text{fixo\_mensal}}}{\text{SEMANAS\_POR\_MES}} \times n_{\text{equipes\_sem}}
$$

**Para distribuição mensal:**

$$
C_{\text{total}} = \sum_{\text{mes}} C_{\text{fixo\_mensal}} \times n_{\text{equipes\_mes}}
$$

### 9.5 Custo Fixo Mensal da Equipe (ADR-030 D3/D4)

$$
C_{\text{fixo\_mensal}} = C_{\text{mo\_mensal}} + C_{\text{eq\_mensal}} + C_{\text{comb\_mensal}} + C_{\text{mat\_mensal}}
$$

onde:

$$
C_{\text{mo\_mensal}} = \sum_{\text{funções}} C_{\text{unit\_mensal}} \times n_{\text{pessoas}}
$$

$$
C_{\text{eq\_mensal}} = \sum_{\text{equip}} C_{\text{unit\_h}} \times \text{HORAS\_MES} \times n_{\text{unidades}}
\quad (\text{excluindo combustível})
$$

$$
C_{\text{comb\_mensal}} = \sum_{\text{equip}} q_{\text{L/h}} \times \text{HORAS\_MES} \times P_{\text{diesel}} \times n_{\text{unidades}}
$$

$$
C_{\text{mat\_mensal}} = \sum_{\text{mat}} c_{\text{unit/h}} \times \text{HORAS\_MES} \times P_{\text{mat}}
$$

---

## 10. Criticidade — Análise de Esforço

**Referência**: ADR-020 + ADR-027  
**Arquivo**: skill 08

### 10.1 Score Ponderado

$$
S_{\text{crit}} = \alpha \cdot s_{\text{duracao}} + \beta \cdot s_{\text{gargalo}} + \gamma \cdot s_{\text{downstream}}
$$

**Pesos padrão** ⚙:

| Peso | Valor | Dimensão |
|------|-------|----------|
| $\alpha$ | **0,50** | Participação na duração total |
| $\beta$ | **0,30** | Razão de gargalo de recursos |
| $\gamma$ | **0,20** | Grau de dependências downstream (percentil normalizado) |

### 10.2 Participação de Duração

$$
s_{\text{duracao}} = \frac{d_{\text{atividade}}}{D_{\text{projeto}}}
$$

### 10.3 Score Normalizado Downstream

$$
s_{\text{downstream}} \in [0, 1] \quad \text{(percentil da contagem de dependências)}
$$

---

## 11. Criticidade — Análise de Custo (Pareto)

**Referência**: ADR-027  
**Arquivo**: skill 09

### 11.1 Sensibilidade ao Custo

$$
\sigma = \bigl(\alpha_e \cdot f_e + \alpha_m \cdot f_m + \alpha_s \cdot f_s + \alpha_o \cdot f_o\bigr) \times (1 + \phi \cdot 0{,}5)
$$

onde $(f_e + f_m + f_s + f_o = 1{,}0)$ é a decomposição simplex do custo:

| Componente | Fração | Peso $\alpha$ | Justificativa |
|---|---|---|---|
| Equipamento | $f_e$ | **0,70** | Diesel e depreciação são voláteis |
| Mão de obra | $f_m$ | **0,20** | Reajustes de CCT são previsíveis |
| Material | $f_s$ | **0,40** | IPCA, frete |
| Outros | $f_o$ | **0,40** | Mobilização, residual |

E $\phi$ = `fator_praticabilidade` ∈ [0, 1] (amplificação por risco sazonal).

**Pesos por categoria (volátilidade):**

```
DIESEL / COMBUSTIVEL → 1,00
EQUIPAMENTO          → 0,70
MATERIAL             → 0,40
MAO_OBRA             → 0,20
padrão               → 0,40
```

### 11.2 Dominância de Pareto

Item $a$ domina $b$ se e somente se:

$$
\forall d \in \{\text{custo}, \text{duracao}, \text{recurso}, \sigma\}:\; a_d \geq b_d
\quad\land\quad
\exists d:\; a_d > b_d
$$

### 11.3 Classificação ABC

Ranking lexicográfico: `custo DESC → recurso DESC → duração DESC → σ DESC`

| Classe | Critério |
|--------|---------|
| **A+** | Na fronteira Pareto **E** rank ≤ top 20% |
| **A** | Na fronteira Pareto **OU** rank ≤ top 40% |
| **B** | rank ≤ top 70% |
| **C** | rank > top 70% |

---

## 12. Consolidação — Margens

**Referência**: ADR-028  
**Arquivo**: skill 06

### 12.1 Receita

$$
R_{\text{sem\_BDI}} = \sum_i P_{\text{cpu},i}^{\text{sem\_BDI}} \times Q_i
$$

$$
R_{\text{com\_BDI}} = \sum_i P_{\text{cpu},i}^{\text{com\_BDI}} \times Q_i
$$

### 12.2 Custo Total

$$
C_{\text{direto}} = \sum_{\text{equipes}} C_{\text{total\_equipe}}
$$

$$
C_{\text{total}} = C_{\text{direto}} + \sum_{\text{categ}} C_{\text{indireto\_categ}}
$$

### 12.3 Resultado Financeiro e Margem

$$
\text{Resultado} = R_{\text{com\_BDI}} - C_{\text{total}}
$$

$$
m = \frac{\text{Resultado}}{R_{\text{com\_BDI}}}
$$

### 12.4 Semáforo de Margem ⚙

| Status | Condição |
|--------|----------|
| 🟢 VERDE | $m_{\text{alvo,min}} \leq m \leq m_{\text{alvo,max}}$ |
| 🟡 AMARELO | $m_{\text{aceit,min}} \leq m < m_{\text{alvo,min}}$ **ou** $m > m_{\text{alvo,max}}$ |
| 🔴 VERMELHO | $m < m_{\text{aceit,min}}$ **ou** $m > m_{\text{aceit,max}}$ |

---

## 13. Ponto de Equilíbrio (Reconciliação)

**Referência**: skill 06 — `limiar_ponto_equilibrio`  
**Arquivo**: `concilium/config/contextos/mendeslobo.json` / `agis.json`

$$
C_{\text{unit,real}} = \frac{C_{\text{total\_equipe}}}{Q}
$$

$$
\Delta_{\text{pct}} = \frac{|C_{\text{unit,real}} - P_{\text{cpu}}|}{C_{\text{unit,real}}}
$$

**Alerta** se $\Delta_{\text{pct}} > \theta_{\text{PE}}$ onde:

| Perfil | $\theta_{\text{PE}}$ |
|--------|---------------------|
| AGIS | **15%** (0,15) — elevado após calibração de praticabilidade |
| MendesLobo (padrão) | **5%** (0,05) |

---

## 14. Controle de Gap de Margem

**Referência**: ADR-028 — heurística de decomposição Fase 1A  
**Arquivo**: skill 06

### 14.1 Gap Total

$$
\text{gap} = \max\bigl(0,\; m_{\text{alvo,min}} - m_{\text{atual}}\bigr) \times 100 \;\text{(p.p.)}
$$

### 14.2 Decomposição do Gap

$$
\text{gap}_{\text{ext}} = \text{gap} \times p_{\text{ext}}
\qquad
\text{gap}_{\text{semi}} = \text{gap} \times p_{\text{semi}}
\qquad
\text{gap}_{\text{fecha}} = \text{gap} - \text{gap}_{\text{ext}} - \text{gap}_{\text{semi}}
$$

**Proporções heurísticas** ⚙:

$$
p_{\text{ext}} = \min\!\bigl(\rho_{\text{mob}} + \phi_{\text{prac}} \times 0{,}3,\; 0{,}50\bigr)
$$

$$
p_{\text{semi}} = \min\!\bigl(0{,}25,\; 1 - p_{\text{ext}}\bigr)
$$

$$
p_{\text{fecha}} = 1 - p_{\text{ext}} - p_{\text{semi}}
$$

onde $\rho_{\text{mob}}$ = participação de mobilização na receita e $\phi_{\text{prac}}$ = fator de perda por praticabilidade.

### 14.3 Viabilidade

$$
\text{viável} = (\text{gap}_{\text{fecha}} + \text{gap}_{\text{semi}}) \geq 0{,}95 \times \text{gap}
$$

---

## 15. Indiretos — Distribuição Temporal

**Referência**: ADR-009, ADR-023 §D4  
**Arquivo**: skill 05

### 15.1 Custo Semanal (driver = "permanencia")

$$
C_{\text{sem}} = \frac{C_{\text{fixo\_mensal}}}{4{,}33}
$$

$$
C_{\text{categ\_total}} = C_{\text{sem}} \times N_{\text{semanas}}
$$

### 15.2 Mobilização/Desmobilização (driver = "one_time")

$$
C_{\text{mob,sem0}} = \frac{C_{\text{total}}}{2}
\qquad
C_{\text{mob,sem\_final}} = \frac{C_{\text{total}}}{2}
$$

### 15.3 Aplicação do BDI INDIRETO

$$
C_{\text{indireto,com\_BDI}} = C_{\text{indireto}} \times (1 + \text{BDI}_{\text{INDIRETO}})
$$

### 15.4 Escalonamento por Política (DV4)

$$
C_{\text{final}} = C_{\text{calculado}} \times f_{\text{política}}
$$

| Política | $f_{\text{política}}$ |
|----------|-----------------------|
| lean | **0,85** |
| standard | **1,00** |
| robust | **1,15** |

---

## 16. Reconciliação de Recursos

**Referência**: ADR-030 — Skill 06A  
**Arquivo**: skill 06A-reconciliar-custos-recurso

### 16.1 Custo de Aquisição por Conflito

$$
C_{\text{aquis}} = n_{\text{excedente}} \times c_{\text{unit\_dia}} \times \Delta_{\text{dias}}
$$

$$
\Delta_{\text{dias}} = (\text{data\_fim} - \text{data\_inicio}).\text{days} + 1
$$

### 16.2 Margem Reconciliada

$$
C_{\text{rec}} = C_{\text{base}} + \sum_{\text{conflitos}} C_{\text{aquis}}
$$

$$
m_{\text{rec}} = \frac{R_{\text{com\_BDI}} - C_{\text{rec}}}{R_{\text{com\_BDI}}}
$$

---

## 17. Sugestões de Replanejamento

**Referência**: Skill 13  
**Arquivo**: skill 13-replan-advisor

### 17.1 Delta de Margem Necessário

$$
\delta_m = \begin{cases}
m_{\text{alvo,min}} - m_{\text{atual}} & \text{se status = AMARELO} \\
m_{\text{aceit,min}} - m_{\text{atual}} & \text{se status = VERMELHO}
\end{cases}
$$

### 17.2 Score de Sugestão

$$
S_{\text{sug}} = \delta_{m,\text{estimado}} \times w_{\text{confiança}}
$$

| Confiança | $w$ |
|-----------|-----|
| ALTA | **1,00** |
| MÉDIA | **0,70** |
| BAIXA | **0,40** |

---

## 18. Limiares e Thresholds de Controle

**Arquivo**: `concilium/config/concilium.yaml`

### 18.1 Schedule Performance Index (SPI)

| Status | Intervalo |
|--------|-----------|
| Adiantado | SPI > **1,05** |
| No prazo | **0,95** ≤ SPI ≤ **1,05** |
| Levemente atrasado | **0,80** ≤ SPI < **0,95** |
| Significativamente atrasado | SPI < **0,80** |

### 18.2 Thresholds de Replanejamento

| Tier | Gatilho | Valor |
|------|---------|-------|
| Tier 1 | Conclusão antecipada | 1 semana |
| Tier 1 | Folga aceitável | 2 semanas |
| Tier 1 | Pico de recursos | ≤ 95% |
| Tier 2 | Atraso | 1 semana |
| Tier 2 | Sustentação de recurso | 2 semanas |
| Tier 2 | Utilização de recurso | ≥ 100% |
| Tier 2 | Estouro de custo | 20% |
| Tier 2 | Deriva de produtividade | ≤ 80% por ≥ 2 semanas |
| Tier 3 | Buffer de risco de prazo | 1,0% |
| Tier 3 | Cascata | ≥ 8 atividades |
| Tier 3 | Marco de custo | 10% |

### 18.3 Validação de Produtividade

| Parâmetro | Valor |
|-----------|-------|
| Mínimo plausível | **0,1** unidade/h |
| Máximo plausível | **10.000** unidades/h |
| Confiança baixa | < 60% |
| Alerta de confiança | < 80% |

### 18.4 Validação de Progresso (VAL-PROG)

| Parâmetro | Valor |
|-----------|-------|
| Fator de superrelato | **1,5** × planejado |
| Limiar baixa eficiência | **30%** utilização |
| Semanas mínimas sustentadas | **2** semanas |
| Janela de detecção de duplicata | 7 dias |

### 18.5 Composição de Equipe (ADR-006)

| Parâmetro | Valor |
|-----------|-------|
| Razão mínima de técnico de segurança | 1 para cada **10** trabalhadores |
| Variância máxima de custo | **10%** acima do padrão |
| Eficiência padrão para equipe customizada | **80%** |

### 18.6 Pisos de Lucro por Categoria ⚙

| Categoria | Padrão | Mínimo |
|-----------|--------|--------|
| MAO_OBRA | 9,0% | 5,0% |
| MATERIAL | 5,0% | 2,0% |
| SERVICOS | 9,0% | 5,0% |
| INDIRETO | 2,0% | 1,0% |
| DIESEL | 5,0% | 2,0% |

### 18.7 Pesos de Qualidade do Cronograma

| Dimensão | Peso |
|----------|------|
| Makespan (duração total) | **0,50** |
| Nivelamento de recursos | **0,20** |
| Tempo ocioso | **0,15** |
| Utilização de recursos | **0,15** |

---

## 19. Vocabulário Canônico de Unidades

**Arquivo**: `concilium/src/concilium/domain/units.py`  
**Enforcement**: `@field_validator("unidade", mode="before")` em `Insumo` e `CPU`

| Unidade canônica | Dimensão | Aliases reconhecidos |
|-----------------|----------|----------------------|
| `m` | Comprimento | `M` |
| `km` | Comprimento | `KM` |
| `m²` | Área | `M²`, `M2`, `m2` |
| `m³` | Volume sólido | `M³`, `M3`, `m3` |
| `h` | Tempo | `H`, `hr`, `HR`, `hs`, `HS` |
| `mes` | Tempo | `MES`, `MÊS`, `mês`, `Mes` |
| `t` | Massa | `T` |
| `kg` | Massa | `KG` |
| `l` | Volume líquido | `L`, `LT`, `lt` |
| `unid` | Contagem | `UNID`, `UND`, `und`, `UN`, `un`, `Un`, `Unid` |
| `sc` | Embalagem | `SC` |
| `vb` | Verba (lump-sum) | `VB` |

**Regra de normalização**: qualquer alias é convertido silenciosamente para a forma canônica ao carregar via Pydantic. Unidade desconhecida levanta `ValueError` em tempo de carga.

---

*Gerado em: maio/2026 — Revisão: 1.0*  
*Fonte de código auditada: `concilium/src/`, `scripts/`, `concilium/config/concilium.yaml`*
