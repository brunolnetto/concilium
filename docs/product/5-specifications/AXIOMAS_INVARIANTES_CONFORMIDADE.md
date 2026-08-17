# Axiomas, Invariantes e Regras de Negócio — Sistema de Rastreamento

**Propósito**: Documentar cada axioma e regra de negócio de forma que toda transformação de dados possa ser verificada contra esses axiomas. Prevenir regressões de cálculo.

**Status**: Fonte de Verdade (SSOT) para auditoria técnica e conformidade.

---

## PARTE 1: AXIOMAS (Verdades Fundamentais)

### A1: Encargos de Mão de Obra

**Axioma**: Todo custo de MO inclui encargos sociais/provisão no multiplicador **1.66×**.

**Derivação**:
```
Encargos = 30% (CLT) + 31% (Provisão 13° + Férias) + 5% (Admin)
         = 0.30 + 0.31 + 0.05
         = 0.66

Multiplicador = 1 + 0.66 = 1.66
```

**Aplicação**:
- MO Base (salário/hora) × 1.66 → MO Encargada
- Válido para: equipes diretas, indiretos (ADM, TOP, LAB, QSMS)
- Exceção: NENHUMA (hardcoded, não configurável)

**Verificação**:
```python
assert 1.65 < ENCARGO_MULTIPLICADOR < 1.67  # tolerância ±0.01
custo_mo_encargado = custo_mo_base * 1.66
```

**Arquivo de Referência**: `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/_dimensionamento_custos.py`

---

### A2: Custo Horário = Soma de Componentes

**Axioma**: Custo horário de uma equipe é a soma **exaustiva** de:
- MO (funções da composição × salário × 1.66)
- Equipamentos (equipamentos da composição × custo aluguel)
- Combustível (L/h × preço unitário combustível)
- Materiais (composição_itens da CPU × coef)

**Formulação**:
```
C_h = Σ[C_h^MO] + Σ[C_h^EQ] + Σ[C_h^COMB] + Σ[C_h^MAT]

Cada componente é calculado como:
  C_h^MO = Σ(funcoes) [ (salario_mensal / 220h) × num_pessoas × 1.66 ]
  C_h^EQ = Σ(equipamentos) [ (custo_mensal / 220h) × num_unidades ]
  C_h^COMB = Σ(combustiveis) [ l_por_hora × preco_litro ]
  C_h^MAT = Σ(composicao_itens) [ coeficiente × preco_unitario ]
```

**Invariante**:
```
C_h_total = C_h_MO + C_h_EQ + C_h_COMB + C_h_MAT
DEVIATION = |C_h_total_calculado - C_h_total_rastreado| / C_h_total
assert DEVIATION < 0.01  # tolerância 1%
```

**Rastreamento**:
- `equipes_diretas[].composicao.funcoes[]` → C_h^MO
- `equipes_diretas[].composicao.equipamentos[]` → C_h^EQ
- `insumo[DIESEL/CNG].custo_horario` → C_h^COMB
- `CPU.composicao_itens[] × producao_horaria` → C_h^MAT

**Arquivo de Referência**: `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_custos.py:72-156`

---

### A3: Produtividade Efetiva = ρ × β

**Axioma**: Produção efetiva sempre é a produtividade de catálogo **ajustada** por fator climático/calendário.

**Formulação**:
```
ρ_efetiva = ρ_catálogo × β_praticabilidade
          = ρ_catálogo × (fator_clima × fator_calendario)

Onde:
  ρ_catálogo = Producao.producao_horaria (ex: 582.75 m²/h)
  β_praticabilidade ∈ [0.5, 1.0] para obras reais
  
Extremos:
  β = 1.0  → Condições ideais (verão, sem chuva)
  β = 0.5  → Condições críticas (chuva intensa, inverno)
```

**Validação**:
```python
assert 0.4 < beta_praticabilidade <= 1.0  # rejeita β > 1 (impossível) ou < 0.4 (demasiado pessimista)
producao_efetiva = producao_catalogo * beta_praticabilidade
assert producao_efetiva > 0
```

**Rastreamento**:
- Entrada: `Producao.producao_horaria` (ρ)
- Bridge: `Skill 02.resultado.fator_clima_semanal` (β)
- Saída: `Skill 04.cronograma[].atividades[].producao_efetiva` (ρ×β)

**Arquivo de Referência**: `src/concilium/application/skills/manifests/02-calendarios-e-clima/_skill_helpers/_fator_clima.py`

---

### A4: Preço Unitário (PU) via Bottom-Up (Fonte 1)

**Axioma**: PU padrão é derivado de **C_h dividido pela produtividade efetiva**.

**Formulação**:
```
PU_sem_bdi = C_h_total / (ρ_catálogo × β_praticabilidade)
           = C_h / ρ_efetiva

Este PU captura:
  • Todo o custo de operação (MO + EQ + COMB)
  • Ajustado pela velocidade real de trabalho
  • Sem BDI (preço puro de custo)
```

**Invariante**:
```python
# Reconciliação com cronograma
custo_total_atividade_via_pu = PU_sem_bdi × quantitativo_total
custo_total_atividade_via_cronograma = Σ(semanas) [ n_equipes × horas × C_h ]
DELTA = |via_pu - via_cronograma| / via_cronograma
assert DELTA < 0.05  # tolerância 5% (diferenças de arredondamento)
```

**Condições**:
- ✅ Aplicável quando `Producao.composicao_padrao_equipe` preenchida
- ❌ Não aplicável quando Producao vazio (fallback Fonte 2)
- ⚠️ Se PU < 0 ou NaN → erro crítico (composição incompleta)

**Arquivo de Referência**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/_skill_helpers/_preco_cpu.py:84-142`

---

### A5: Fallback Composição (Fonte 2) — Último Recurso

**Axioma**: Se Producao indisponível ou inválida, usar composição_itens da CPU como **último recurso**.

**Formulação**:
```
Quando Fonte 1 falha:
  PU_fallback = Σ(CPU.composicao_itens[insumo]) [ coef × preco_unitario ]

Sinalização:
  planejamento[].precificacao_via_fallback_composicao = true
  
Aviso:
  "PU baseada em composição, sem relação com produtividade (NEP-032)"
```

**Limitações**:
- Não inclui MO/EQ (apenas MATERIAL/COMBUSTÍVEL)
- Menos confiável que Fonte 1
- Requer revisão manual de PU

**Validação**:
```python
if producao_invalid:
    PU_fallback = sum_composicao_itens(cpu_id)
    assert PU_fallback > 0
    flag_fallback_composicao = true
    log_warning(f"PU fallback para {cpu_id}: {PU_fallback}")
```

**Arquivo de Referência**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_precificacao/_skill_helpers/_preco_cpu.py:144-180`

---

### A6: BDI Diferenciado por Categoria (ADR-090)

**Axioma**: BDI (Benefícios, Despesas Indiretas, Lucros) é **sempre aplicado por categoria de custo**, nunca como taxa global.

**Ressalva (auditoria cruzada com `FORMULARIO_RIGOROSO_DERIVACAO.md` §20.4):** este axioma é falso como enunciado para o INDIRETO. `_calc_venda_com_bdi` (`_venda_custo.py:69-87`) tem um fallback que aplica sim uma **taxa global/plana** (`BDI_INDIRETO ≈25,21%` sobre o custo indireto agregado inteiro) quando a soma dos sub-custos por categoria é zero — condição real de disparo, não hipotética (ver `Indireto` com campos `default=0.0`, sem `None`, em `_financeiro_resultado.py:83-106`). Além disso, `_apply_bdi_to_indiretos` (`_resolucao.py:231-284`) **sempre** usa a taxa plana para indireto, incondicionalmente, e alimenta o relatório Excel — nunca decompõe por sub-categoria. O axioma vale estritamente apenas para custo **direto** (MO/EQ/MAT/COMB sempre com taxa por categoria); para indireto, é a exceção, não a regra geral. Recomenda-se reformular o axioma como: "BDI é aplicado por categoria de custo sempre que os sub-custos estão disponíveis (sempre o caso no direto; no indireto, cai para taxa plana quando sub-custos somam zero ou via `_apply_bdi_to_indiretos`)."

**Estrutura** (referência ADR-090):
```
BDI_MATERIAL = 34.7%      (lucro + overhead + tributos em serviços/insumos)
BDI_EQUIPAMENTO = 34.7%   (aluguel + manutenção = serviço, mesmo BDI)
BDI_MAO_OBRA = 34.7%      (serviço profissional + encargos)

BDI_COMBUSTIVEL = 4.0%    (APENAS fornecimento de mercadoria)
  └─ ATENÇÃO: combustível é PROPRIEDADE DE MATERIAL, não equipamento
  └─ Razão econômica: insumo consumível (como concreto, parafusos)
  └─ Natureza: mercadoria/fornecimento (ICMS/PIS/COFINS), não serviço (ISS)
  └─ Referência: ADR-090, TCU Ac.2622/2013, cubo_analitico_builder.py

Fórmula:
  Valor_com_bdi = Σ(categorias) [
      Valor_categoria_sem_bdi × (1 + BDI_categoria)
  ]
  
  Onde BDI_categoria ∈ {0.347 (MO/EQ/MAT), 0.04 (COMBUSTIVEL)}
```

**Crítico** (ADR-090 — Taxonomia de Custos):
```
  Equipamento NÃO inclui combustível na taxa 34.7%
  
  Decomposição de Custos:
    Mão de Obra
      └─ Salário + encargos → BDI 34.7% (serviço)
    
    Equipamento = 2 propriedades SEPARADAS:
      ├─ A: Aluguel + Manutenção → BDI 34.7% (serviço de locação)
      └─ B: COMBUSTÍVEL → BDI 4.0% (mercadoria consumida) ← ADR-090
    
    Material
      ├─ Consumíveis diretos (concreto, parafusos) → BDI 34.7%
      └─ Combustível → BDI 4.0% (mesma natureza econômica)
```

**Invariante**:
```python
# BDI nunca é aplicado 2× (hardening contra double-count)
for item in planejamento:
    assert not (item.precificacao_via_fallback and item.bdi_aplicado)
    
# Soma de componentes com BDI — combustível usa taxa baixa
total_com_bdi = (
    preco_sem_bdi.material * (1 + bdi.material) +
    preco_sem_bdi.combustivel * (1 + bdi.combustivel) +  # 4% NOT 34.7%
    preco_sem_bdi.mao_obra * (1 + bdi.mao_obra) +
    preco_sem_bdi.equipamentos * (1 + bdi.equipamentos)
)
assert total_com_bdi >= preco_sem_bdi.total  # nunca diminui
assert bdi.combustivel == 0.04, "Combustível deve usar BDI 4% (ADR-090)"
```

**Fonte de BDI**: `config/catalogos/mendeslobo/perfis/*.json`

**Referência ADR-090**: `src/concilium/domain/services/analytics/cubo_analitico_builder.py` linhas 12-50

**Arquivo de Implementação**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_bdi_resolucao.py`

**Documentação Adicional**: Ver [ANALISE_COMBUSTIVEL_VS_EQUIPAMENTO.md](ANALISE_COMBUSTIVEL_VS_EQUIPAMENTO.md) para justificativa econômica completa

---

### A7: Quantitativos = Somatório de Cronograma

**Axioma**: Total executado DEVE ser igual ao quantitativo planejado.

**Formulação**:
```
Quantitativo_Total = Σ(semanas) [ quantidade_semanal ]

Cálculo:
  quantidade_semanal = ρ_efetiva × horas_semana × n_equipes × dias_atividade

Invariante:
  ∑(qtd_semanal) == quantitativo_total (com tolerância)
```

**Verificação**:
```python
acumulado = 0
for semana in cronograma:
    qtd_semanal = producao_efetiva * horas_semana * num_equipes
    acumulado += qtd_semanal
    assert acumulado <= quantitativo_total * 1.01  # tolerância 1%

DELTA = abs(acumulado - quantitativo_total) / quantitativo_total
assert DELTA < 0.02  # tolerância 2%
```

**Rastreamento**:
- Entrada: `EAP_ITEMS[].quantitativo`
- Cálculo: `cronograma[].atividades[].quantidade_semanal`
- Validação: `cronograma[].atividades[].acumulado_final`

**Arquivo de Referência**: `src/concilium/application/skills/manifests/04-cronograma/_skill_helpers/_spec.py:150-180`

---

### A8: Margem Financeira = (Venda - Custo) / Venda

**Axioma**: Margem é SEMPRE calculada como percentual de faturamento, nunca de custo.

**Formulação**:
```
Resultado = Venda - (C_direto + C_indireto)
Margem_pct = Resultado / Venda × 100

Status (Faixa de Viabilidade):
  VERDE:    8% ≤ Margem ≤ 10%   (saudável)
  AMARELO:  5% ≤ Margem < 8% ou 10% < Margem ≤ 15%  (aceitável)
  VERMELHO: Margem < 5% ou > 15%  (não viável ou suspeito)
```

**Invariante**:
```python
assert venda > 0  # precondição
custo_total = custo_direto + custo_indireto
resultado = venda - custo_total
margem_pct = (resultado / venda) * 100

# Coerência
assert custo_total <= venda  # lucro não pode ser negativo indefinidamente
assert margem_pct >= -100  # máximo loss = custo_total

# Rastreamento
if margem_pct < 5 or margem_pct > 15:
    log_warning(f"Margem fora de faixa: {margem_pct}%")
    status = "VERMELHO"
elif margem_pct >= 8 and margem_pct <= 10:
    status = "VERDE"
else:
    status = "AMARELO"
```

**Arquivo de Referência**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_consolidacao.py`

---

### A9: Ponto de Equilíbrio = C_fixo / Margem_Contribuição_Unitária

**Axioma**: Break-even é alcançado quando **margem de contribuição total = custos fixos**.

**Formulação**:
```
Custo_Fixo_Estrutural = ADM + TOP + LAB + QSMS + MOB (permanência inteira)
Margem_Contribuição_Unitária = PU_sem_bdi - Custo_Variável_Unitário

Break_Even_Qty = Custo_Fixo_Estrutural / Margem_Contribuição_Unitária

Frentes_Necessárias = Custo_Total_Operacional / (PU_sem_bdi × Quantitativo)
```

**Validação**:
```python
if frentes_necessarias > 1.5:
    status = "CRITICO"  # custo real > 1.5× do orçado
    log_warning(f"Frentes necessárias: {frentes_necessarias:.2f} → CRÍTICO")
elif frentes_necessarias > 1.25:
    status = "AVISO"
else:
    status = "OK"

# Reconciliação com quantidade
assert quantitativo_planejado >= break_even_qty * 1.2  # 20% de margem de segurança
```

**Arquivo de Referência**: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_ponto_equilibrio.py`

---

### A10: Bridge N1→N4 Sem Extensão de Duração (ADR-148)

**Axioma**: Gap climático é **diagnosticado** em N3 (custo estimado) mas **NUNCA cobrado** em N4 (custo real) porque duração não é estendida.

**Limitação Conhecida**:
```
N3 (Bridge):
  gap_praticabilidade = Σ(semanas) [
      (ρ_catálogo - ρ_efetiva) / ρ_catálogo × C_h × n_frentes
  ]
  → Quanto custaria se duração fosse estendida?

N4 (Real):
  custo_operacional_real = Σ(equipes_instanciadas) [ horas_reais × taxa_horária ]
  → gap_praticabilidade ≠ gap_real
  
Por quê?
  • Duração é RCPSP-invariante (não muda com clima)
  • Equipes compensam clima reduzindo horas/dia, não estendendo datas
  • Resultado: produtividade real ≠ catálogo, mas duração = catálogo
```

**Sinalização**:
```python
if gap_praticabilidade > 0:
    limitacao_clima = LimitacaoClimaN4(
        gap_praticabilidade_abs=gap_praticabilidade,
        cobrado_no_custo_operacional=False,
        mensagem="Diagnosticado em N3, nunca entra em N4 (ADR-148)"
    )
    log_info(f"Limitação clima: {gap_praticabilidade:.2f} (não cobrado)")
```

**Arquivo de Referência**: `src/concilium/domain/models/canonical/_financeiro_resultado.py:276-290`

---

### A11: τ_i ≥ 1 — Custo Autônomo Nunca é Menor que Custo de Catálogo

**Axioma**: O custo autônomo de execução $\tilde{C}_i$ é **sempre maior ou igual** ao custo de catálogo $C_i = p_i^{cat} \times Q_i$. O ratio $\tau_i = \tilde{C}_i / C_i$ (`frentes_equivalentes_necessarias`) é invariavelmente ≥ 1.

**Origem da Distinção — Custo de Atividade vs Custo de Pool**:
```
Custo de Atividade (autônomo): Ĉ_i
  — Custo real de execução se a atividade contratasse todos os recursos sozinha
  — Inclui: semanas produtivas + mob/demob + gaps de ociosidade
  — Componentes:
      γ_i^contrato = γ_i^MO + γ_i^EQ   (fixo por período, não escala com η_j)
      γ_i^consumo  = γ_i^MAT + γ_i^COMB (escala com produção efetiva η_j × ρ_i)

Custo de Pool (instancial particionado): C_pool_i
  — Custo após distribuição Shapley entre atividades que compartilham o mesmo recurso
  — C_pool_i ≤ Ĉ_i sempre (pool só pode economizar, nunca onerar vs autônomo)
  — economia_pool_abs = Ĉ_i − C_pool_i ≥ 0

Custo de Catálogo: C_i = p_i^cat × Q_i = (γ_i / ρ_i) × Q_i
  — Custo se cada hora produtiva fosse paga ao custo horário total γ_i
  — Não inclui horas contratadas mas não produtivas
```

**Formulação Matemática**:

Custo autônomo por semana $j$ com $m_{ij}$ equipes e eficiência $\varepsilon_j = \eta_j \cdot \beta_j$:

$$\tilde{c}_{ij} = \left[\gamma_i^{contrato} + \gamma_i^{consumo} \cdot \varepsilon_j\right] \cdot h \cdot d \cdot m_{ij}$$

O ratio normalizado (dividindo numerador e denominador por $\gamma_i \cdot h \cdot d$):

$$\tau_i = \frac{\tilde{C}_i}{C_i} = \frac{\displaystyle\sum_j \left[1 - (1-\varepsilon_j)\,\delta_i^*\right] m_{ij}}{\displaystyle\sum_j \varepsilon_j \, m_{ij}} \geq 1$$

onde $\delta_i^* = \gamma_i^{consumo}/\gamma_i \in [0,1]$ é a fração de consumo (diesel + materiais).

**Prova de τ_i ≥ 1**:

Para cada semana $j$ individual:
$$1 - (1-\varepsilon_j)\delta_i^* - \varepsilon_j = (1-\delta_i^*)(1-\varepsilon_j) \geq 0$$

Multiplicando por $m_{ij} > 0$ e somando sobre $j$:
$$\sum_j [1-(1-\varepsilon_j)\delta_i^*]m_{ij} \geq \sum_j \varepsilon_j m_{ij} \implies \tau_i \geq 1 \quad \square$$

**Decomposição Analítica**:

$$\tau_i = 1 + \frac{(1-\delta_i^*)\displaystyle\sum_j(1-\varepsilon_j)\,m_{ij}}{\displaystyle\sum_j\varepsilon_j\,m_{ij}} = 1 + \frac{(1-\delta_i^*)(1-\bar\varepsilon_i)}{\bar\varepsilon_i}$$

onde $\bar\varepsilon_i = \frac{\sum_j \varepsilon_j m_{ij}}{\sum_j m_{ij}}$ é a média ponderada de eficiência (= `eta_real` no código).

**Condições Extremas**:
- $\tau_i = 1$: quando $\delta_i^* = 1$ (todos custos são consumo, sem MO/EQ fixos) OU $\bar\varepsilon_i = 1$ (eficiência plena em todas as semanas)
- $\tau_i \gg 1$: quando $(1-\delta_i^*)$ grande (muitos custos fixos) E $\bar\varepsilon_i$ baixo (muito clima adverso)

**Nota**: A fórmula acima é um **limite inferior** de $\tau_i$. O custo autônomo real no código também inclui mob/demob e mínimo de permanência contratual — termos que elevam ainda mais $\tilde{C}_i$ acima do previsto pela fórmula semanal.

**Mapeamento para o Código**:
```python
# _ponto_equilibrio.py
frentes_nec = custo_total_autonomo / venda_sem_bdi  # = τ_i

# Componentes de τ_i:
#   custo_total_autonomo = Ĉ_i (custo autônomo, Skill 05 + ADR-085)
#   venda_sem_bdi = PU_sem_bdi × Q = C_i (custo catálogo)
#
# Mapeamento de variáveis:
#   ε_j       → fator_clima_v (= η_j × β_j, média ponderada = eta_real)
#   δ_i*      → (diesel + mat) / total    (fração de consumo)
#   1 − δ_i*  → (MO + EQ) / total         (fração de contrato, i.e. custo fixo)
#   m_{ij}    → num_equipes_base × semanas_ativas (= machine_weeks_brutas)
#   ε̄_i       → eta_real = machine_weeks_efetivas / machine_weeks_brutas

# _financeiro_resultado.py:
#   frentes_equivalentes_necessarias  # τ_i
#   eta_real                          # ε̄_i = eMW / MW
#   machine_weeks_brutas              # Σ_j m_{ij}
#   machine_weeks_efetivas            # Σ_j ε_j·m_{ij}
#   gap_praticabilidade_abs           # parcela de (τ_i − 1) por clima
#   gap_escala_abs                    # parcela de (τ_i − 1) por escala de equipes
#   gap_pool_overhead                 # parcela de (τ_i − 1) por overhead de pool
#   economia_pool_abs                 # Ĉ_i − C_pool_i ≥ 0 (pool economiza vs autônomo)
```

**Decomposição Causal (ADR-162)**:

O gap $\delta = C_v - C_{fix}$ é decomposto em duas causas simétricas (partição de Bennet/Shapley):
```
H_cat   = (Q / ρ) / β                  # horas catálogo (ajustado por β)
H_i     = horas_dia × dias_semana × MW_brutas  # horas reais deployadas
γ_v     = C_v / H_cat                  # taxa de venda
γ_o     = C_fix / H_i                  # taxa operacional real

T_cronograma   = (H_cat − H_i) × (γ_v + γ_o) / 2
T_precificacao = (γ_v − γ_o) × (H_cat + H_i) / 2
δ = T_cronograma + T_precificacao      # por construção algébrica
```

**Validação**:
```python
# A11: τ_i ≥ 1 sempre
assert frentes_equivalentes_necessarias >= 1.0 - 1e-6, \
    f"τ_i={frentes_nec:.4f} < 1.0 — violação de A11"

# Corolário: C_pool_i ≤ Ĉ_i
assert economia_pool_abs >= -1e-2, \
    f"Pool onerou vs autônomo em R${-economia_pool_abs:.2f} — violação de A11"

# Threshold de alerta operacional
status = "OK" if τ_i <= 1.25 else "AVISO" if τ_i <= 1.50 else "CRITICO"
```

**Arquivo de Referência**:
- Cálculo de τ_i: `src/concilium/application/skills/manifests/06-resultado-financeiro/_consolidacao/_skill_helpers/_ponto_equilibrio.py` (`_pe_frentes_nec`, `_pe_camada2_producao`)
- Cálculo de Ĉ_i: `src/concilium/application/skills/manifests/05-equipes-e-alocacao/_skill_helpers/_causal_cost_partition.py`
- Modelo de dados: `src/concilium/domain/models/canonical/_financeiro_resultado.py` (campos `frentes_equivalentes_necessarias`, `eta_real`, `machine_weeks_*`, `economia_pool_abs`)

---

### I1: Sincronismo de Dados (Não-Corrupção)

**Condição**: Toda transformação DEVE preservar a integridade referencial.

| Campo | Origem | Destino | Validação |
|-------|--------|---------|-----------|
| `cpu_id` | EAP_ITEMS | Skill 03 catálogo | Existe em catálogo? |
| `producao_id_ref` | CPU | Skill 03 produtividades | Arquivo existe? |
| `insumo_id` | Composição | Skill 03 insumos | Preco_unitario > 0? |
| `fator_clima` | Skill 02 | Skill 04 | ∈ [0.4, 1.0]? |
| `num_equipes` | CRONOGRAMA | Skill 04/05 | > 0 e ≤ 10? |
| `quantitativo_semanal` | Skill 04 | Skill 05 | ≥ 0? |

---

### I2: Completude de Composição

**Condição**: Cada CPU EM USO DEVE ter composicao_padrao_equipe preenchida.

```python
for atividade in eap_items:
    cpu = catalogo.get(atividade.cpu_id)
    assert cpu is not None, f"CPU {atividade.cpu_id} não encontrada"
    
    producao = catalogo.get(cpu.producao_id_ref)
    assert producao is not None, f"Producao {cpu.producao_id_ref} não encontrada"
    
    assert len(producao.composicao_padrao_equipe.funcoes) > 0, f"Funções vazias"
    assert len(producao.composicao_padrao_equipe.equipamentos) > 0, f"Equipamentos vazios"
    
    for funcao in composicao.funcoes:
        assert funcao.num_pessoas > 0
        assert funcao.preco_unitario > 0
    
    for equip in composicao.equipamentos:
        assert equip.num_unidades > 0
        assert equip.preco_unitario > 0
```

---

### I3: Não-Negatividade de Custos

**Condição**: Nenhum custo DEVE ser negativo.

```python
COST_FIELDS = [
    "custo_horario_total", "custo_semanal", "custo_mensal",
    "subtotal_sem_bdi", "subtotal_com_bdi",
    "custo_direto", "custo_indireto", "custo_total",
    "resultado_financeiro"  # pode ser negativo (prejuízo), mas então margem_pct < 0
]

for field in COST_FIELDS:
    valor = getattr(canonical, field)
    if field == "resultado_financeiro":
        # Prejuízo é válido (margem_pct negativa), mas raro
        assert valor >= -custo_total * 0.50, f"{field} muito negativo: {valor}"
    else:
        # Custos operacionais nunca são negativos
        assert valor >= 0, f"{field} negativo: {valor}"
```

---

### I4: Coerência de Preços

**Condição**: Venda SEMPRE ≥ Custo.

```python
assert venda_sem_bdi >= custo_direto, "Venda < Custo (catálogo)"
assert venda_com_bdi >= (custo_direto + custo_indireto), "Venda com BDI < Custo total"

# Metodologia B (custo-mais)
fator_minimo = 1.0  # breakeven
fator_maximo = 2.0  # 100% markup (suspeito)
assert fator_minimo <= (venda_custo_plus / custo_total) <= fator_maximo
```

---

### I5: Rastreabilidade de Origem

**Condição**: Todo valor DEVE rastrear sua origem no catálogo ou cálculo.

```python
class RastreabilidadeValor(BaseModel):
    valor: float
    origem: Literal["catalogo", "calculado", "override_manual"]
    data_origem: datetime
    fonte_id: str  # CPU_id, Insumo_id, etc.
    formula: str  # ex: "C_h / (ρ × β)" para PU

# Verificação
for planejamento_item in canonical.planejamento:
    assert planejamento_item.origem in ["catalogo", "calculado", "override"]
    if planejamento_item.origem == "calculado":
        assert "C_h" in planejamento_item.formula or "composicao" in planejamento_item.formula
```

---

## PARTE 3: VERIFICAÇÕES FORMAIS (Testes de Regressão)

### V1: Teste de Círculo Fechado (Round-Trip)

**Objetivo**: Verificar que transformação → canonicalizei → retorno restaura valores originais.

```python
def test_round_trip_pu():
    """Dados entrada → Skill 06 → PU derivado → recalcula → deve bater"""
    
    # Setup
    c_h_original = 3472.55  # R$/h (de skill 05)
    rho = 582.75  # m²/h (de catálogo)
    beta = 0.90   # fator clima
    
    # Forward: calcula PU
    pu_sem_bdi = c_h_original / (rho * beta)
    assert abs(pu_sem_bdi - 5.96) < 0.01  # tolerância R$0.01
    
    # Backward: recupera C_h
    c_h_recalculado = pu_sem_bdi * rho * beta
    delta = abs(c_h_recalculado - c_h_original) / c_h_original
    assert delta < 0.001  # tolerância 0.1%
```

---

### V2: Teste de Agregação (Soma Verificada)

**Objetivo**: Verificar que ∑(componentes) = total.

```python
def test_custo_horario_agregacao():
    """C_h = C_h^MO + C_h^EQ + C_h^COMB + C_h^MAT"""
    
    c_h_mo = 272.44      # de funcoes
    c_h_eq = 402.27      # de equipamentos
    c_h_comb = 1095.31   # de combustível
    c_h_mat = 0.73       # de materiais
    
    c_h_esperado = c_h_mo + c_h_eq + c_h_comb + c_h_mat
    c_h_calculado = 1770.75  # de skill 05
    
    delta = abs(c_h_calculado - c_h_esperado) / c_h_esperado
    assert delta < 0.01  # tolerância 1%
```

---

### V3: Teste de Quantitativo (Cronograma ↔ EAP)

**Objetivo**: Verificar que ∑(qtd_semanal) ≈ quantitativo_total.

```python
def test_quantitativo_sincronismo():
    """EAP quantitativo = ∑(cronograma semanas)"""
    
    quantitativo_eap = 169798.78  # m² de entrada
    
    acumulado = 0
    for semana in cronograma["SV-001"]:
        producao_efetiva = 582.75 * 0.90  # ρ × β
        qtd_semanal = producao_efetiva * 48 * 2  # horas × equipes
        acumulado += qtd_semanal
    
    delta = abs(acumulado - quantitativo_eap) / quantitativo_eap
    assert delta < 0.02  # tolerância 2%
```

---

### V4: Teste de BDI (Monotônicidade)

**Objetivo**: Verificar que Com BDI ≥ Sem BDI.

```python
def test_bdi_monotoncidade():
    """Com BDI sempre ≥ Sem BDI"""
    
    for atividade in canonical.planejamento:
        sem_bdi = atividade.subtotal.sem_bdi.total
        com_bdi = atividade.subtotal.com_bdi.total
        
        assert com_bdi >= sem_bdi * 0.99, f"Com BDI < Sem BDI em {atividade.item_id}"
        
        # BDI nunca ultrapassa 50% (sanidade)
        bdi_aplicado = (com_bdi - sem_bdi) / sem_bdi
        assert bdi_aplicado <= 0.50, f"BDI > 50% em {atividade.item_id}"
```

---

### V5: Teste de Margem (Status Consistente)

**Objetivo**: Verificar que status_margem corresponde a intervalo de margem_pct.

```python
def test_margem_status_consistencia():
    """Status deve corresponder a faixa de margem"""
    
    margem_pct = canonical.resultado.margem_pct
    status = canonical.resultado.status_margem
    
    if 8 <= margem_pct <= 10:
        assert status == "VERDE", f"Margem {margem_pct}% should be VERDE"
    elif 5 <= margem_pct < 8 or 10 < margem_pct <= 15:
        assert status == "AMARELO", f"Margem {margem_pct}% should be AMARELO"
    elif margem_pct < 5 or margem_pct > 15:
        assert status == "VERMELHO", f"Margem {margem_pct}% should be VERMELHO"
```

---

## PARTE 4: REGISTRO DE AUDITORIA DE TRANSFORMAÇÕES

### AUD1: Rastreamento de Alteração de PU

**Quando**: Sempre que PU é derivado ou corrigido.

```json
{
  "timestamp": "2026-08-13T14:32:15Z",
  "atividade_id": "SV-001",
  "evento": "PU_calculado",
  "origem": "skill_06_precificacao",
  
  "dados_entrada": {
    "c_h_skill05": 1770.75,
    "producao_catalogo": 582.75,
    "beta_praticabilidade": 0.90,
    "producao_efetiva": 524.475
  },
  
  "formula_aplicada": "PU = C_h / (ρ × β)",
  "calculo_explicito": "1770.75 / (582.75 × 0.90) = 1770.75 / 524.475 = 3.375",
  
  "resultado": {
    "pu_sem_bdi": 3.375,
    "pu_com_bdi": 4.54,
    "bdi_aplicado": 0.347
  },
  
  "validacoes": {
    "c_h_positivo": true,
    "rho_positivo": true,
    "beta_em_faixa": true,
    "pu_reasonable": true  # 1 < PU < 500
  },
  
  "fonte_verdade": "config/catalogos/mendeslobo/produtividades/CPU-TERRA-ATI-041-PROD-001.json",
  "auditador": "skill_06_resultado_financeiro",
  "revisor": "usuario_confirmacao"
}
```

---

### AUD2: Rastreamento de Coerência de Cronograma

**Quando**: Fim de skill 04, antes de skill 05.

```json
{
  "timestamp": "2026-08-13T14:15:00Z",
  "atividade_id": "SV-001",
  "evento": "cronograma_validado",
  "origem": "skill_04_cronograma",
  
  "quantitativo_planejado": 169798.78,
  "quantitativo_acumulado": 169798.50,
  "diferenca_pct": 0.0001,
  "status_sincronismo": "OK",
  
  "breakdown_semanal": [
    {"semana": "2026-W45", "num_equipes": 2, "horas": 48, "producao_efetiva": 524.475, "qtd": 50350.32, "acumulado": 50350.32},
    {"semana": "2026-W46", "num_equipes": 2, "horas": 48, "producao_efetiva": 524.475, "qtd": 50350.32, "acumulado": 100700.64},
    {"semana": "2026-W47", "num_equipes": 2, "horas": 48, "producao_efetiva": 524.475, "qtd": 50350.32, "acumulado": 151050.96},
    {"semana": "2026-W48", "num_equipes": 2, "horas": 48, "producao_efetiva": 524.475, "qtd": 18747.82, "acumulado": 169798.78}
  ],
  
  "validacoes": {
    "todas_semanas_positivas": true,
    "acumulado_bate_total": true,
    "nenhuma_semana_ultrapassa_meta": true
  }
}
```

---

### AUD3: Rastreamento de Desvios de BDI

**Quando**: BDI aplicado em skill 06, se > 40% ou < 25%.

```json
{
  "timestamp": "2026-08-13T14:45:30Z",
  "atividade_id": "SV-001",
  "evento": "bdi_aplicado",
  "origem": "skill_06_resultado_financeiro",
  
  "alerta": false,
  "motivo": null,
  
  "bdi_por_categoria": {
    "material": {"taxa": 0.347, "valor_sem": 456.78, "valor_com": 614.82},
    "diesel": {"taxa": 0.04, "valor_sem": 1234.56, "valor_com": 1283.94},
    "mao_obra": {"taxa": 0.347, "valor_sem": 2345.67, "valor_com": 3159.15},
    "equipamentos": {"taxa": 0.347, "valor_sem": 1567.89, "valor_com": 2109.57}
  },
  
  "bdi_efetivo_medio": {
    "antes": 0.00,
    "depois": 0.347,
    "delta": 0.347
  },
  
  "fonte_bdi": "config/catalogos/mendeslobo/perfis/mendeslobo.json",
  "última_revisão_bdi": "2026-08-01"
}
```

---

## PARTE 5: MATRIZ DE CONFORMIDADE

| Axioma | Variável | Validação | Arquivo Teste | Status |
|--------|----------|-----------|---------------|--------|
| A1 | Encargos MO | 1.65 < mult < 1.67 | `test_encargos_mo.py` | ✅ |
| A2 | C_h = Σ | Desvio < 1% | `test_custo_horario_agregacao.py` | ✅ |
| A3 | ρ × β | 0.4 < β ≤ 1.0 | `test_producao_efetiva.py` | ✅ |
| A4 | PU Bottom-Up | ρ > 0, C_h > 0 | `test_pu_bottom_up.py` | ✅ |
| A5 | Fallback Comp. | Sinalizado | `test_pu_fallback.py` | ✅ |
| A6 | BDI Categorizado | BDI nunca 2× | `test_bdi_monotoncidade.py` | ✅ |
| A7 | Qtd Sincronismo | Desvio < 2% | `test_quantitativo_sincronismo.py` | ✅ |
| A8 | Margem % | Venda base | `test_margem_status_consistencia.py` | ✅ |
| A9 | Break-Even | frentes_nec > 0 | `test_ponto_equilibrio.py` | ✅ |
| A10 | Bridge N3→N4 | gap_climatico ≠ gap_real | `test_bridge_limitation.py` | ⚠️ |
| I1 | Sincronismo Refs | Todas existem | `test_integridade_referencial.py` | ✅ |
| I2 | Completude Comp. | Nenhuma vazia | `test_completude_composicao.py` | ✅ |
| I3 | Não-Negatividade | Todos >= 0 | `test_nao_negatividade.py` | ✅ |
| I4 | Coerência Preços | Venda >= Custo | `test_coerencia_precos.py` | ✅ |
| I5 | Rastreabilidade | origem ≠ nulo | `test_rastreabilidade_origem.py` | ✅ |

---

## PARTE 6: PROTOCOLO DE REGRESSÃO

### Quando Fazer Check de Regressão

1. **Antes de cada merge** → Rodar suite V1-V5
2. **Quando alterar catálogo** → Rodar V1, V3, AUD1-3
3. **Quando mudar BDI** → Rodar V4, AUD3
4. **Quando revisar Skill 04/05/06** → Rodar V2-V5
5. **Trimestralmente** → Auditoria completa + AUD1-3 retroativo

### Comando de Execução

```bash
# Testes de regressão rápidos (< 1 min)
pytest tests/regression/test_axiomas_*.py -v --tb=short

# Testes com trace detalhado (auditoria)
pytest tests/regression/test_axiomas_*.py -v --tb=long --log-cli-level=DEBUG

# Gerar relatório de conformidade
pytest tests/regression/ --junitxml=results/conformidade_axiomas.xml
python scripts/audit_trail_generator.py --output audit_trail_$(date +%Y%m%d).json
```

---

**Versão**: 1.0  
**Data**: 2026-08-13  
**Revisor**: Engenharia de Planejamento
